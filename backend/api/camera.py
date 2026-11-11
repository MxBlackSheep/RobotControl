"""
RobotControl Backend - Camera API Endpoints

Provides comprehensive camera access through REST API and WebSocket connections.
Integrates with the unified CameraService for all camera operations.

Features:
- Camera listing and status
- Live streaming via HTTP and WebSocket
- Recording management (start/stop)
- Video archive access
- Real-time camera feeds
"""

import os
import logging
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, Header, Request
from fastapi.responses import FileResponse

# Import services with relative imports (within backend directory)
from backend.services.auth import get_current_user, get_current_admin_user
from backend.api.dependencies import ConnectionContext, get_connection_context
from backend.services.camera import get_camera_service
from backend.services.live_streaming import get_live_streaming_service
from backend.services.h264_encoder import EncoderUnavailable

# Import types and config with proper package resolution
from backend.models import ApiResponse

from backend.config import CAMERA_CONFIG
from backend.services.storage_manager import get_storage_manager

from backend.constants import ERROR_MESSAGES, WS_HEARTBEAT_INTERVAL

# Import standardized response formatter

# Configure logging
logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/camera", tags=["camera"])


class CameraSelectionRequest(BaseModel):
    device_identity: str = Field(min_length=1, max_length=4096)


def _camera_operation(action, **kwargs):
    try:
        operation = get_camera_service().runtime.submit(action, **kwargs)
        return {"success": True, "data": {"operation": operation}}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/control-status")
async def camera_control_status(current_user: dict = Depends(get_current_user)):
    # Read cached state only: status polling never opens or reconnects hardware.
    return {"success": True, "data": get_camera_service().get_camera_status()}


@router.post("/devices/refresh", status_code=202)
async def refresh_camera_devices(current_user: dict = Depends(get_current_admin_user)):
    return _camera_operation("refresh")


@router.patch("/selection", status_code=202)
async def select_camera(body: CameraSelectionRequest, current_user: dict = Depends(get_current_admin_user)):
    return _camera_operation("select", identity=body.device_identity)


@router.post("/connect", status_code=202)
async def connect_camera(current_user: dict = Depends(get_current_admin_user)):
    return _camera_operation("connect")


@router.post("/reconnect", status_code=202)
async def reconnect_camera(current_user: dict = Depends(get_current_admin_user)):
    return _camera_operation("reconnect")


@router.post("/recording/start", status_code=202)
async def start_selected_camera(current_user: dict = Depends(get_current_admin_user)):
    return _camera_operation("start")


@router.post("/recording/stop", status_code=202)
async def stop_selected_camera(current_user: dict = Depends(get_current_admin_user)):
    return _camera_operation("stop")

# Camera system paths




def _resolve_recording_file_path(recording_id: str) -> Optional[Path]:
    """Resolve a recording ID to a concrete file path in rolling or experiment storage."""
    # Security check - prevent directory traversal
    if '..' in recording_id or '/' in recording_id or '\\' in recording_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid recording ID"
        )

    if ".partial." in recording_id:
        raise HTTPException(status_code=409, detail="Recording is incomplete and is not available as a finalized clip")

    # Check rolling clips first
    rolling_path = get_storage_manager().rolling_clips_path / recording_id
    if rolling_path.exists() and rolling_path.is_file():
        return rolling_path

    # Check experiment folders recursively (archives may contain nested folders).
    candidates: List[Path] = []
    if get_storage_manager().experiments_path.exists():
        for root, _, files in os.walk(get_storage_manager().experiments_path):
            if recording_id in files:
                candidates.append(Path(root) / recording_id)

    if candidates:
        # If duplicates exist across folders, prefer the most recently modified file.
        if len(candidates) > 1:
            logger.warning(
                "Multiple recordings found for '%s'; selecting newest match among %s candidates",
                recording_id,
                len(candidates),
            )
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    return None


@router.get("/recordings")
async def list_recordings(current_user: dict = Depends(get_current_user)):
    """List retained experiment folders and their finalized videos."""
    try:
        # Get experiment recordings organized by folder (max 20 folders)
        experiment_folders = []
        if get_storage_manager().experiments_path.exists():
            # Get all experiment directories, sorted by modification time (newest first)
            exp_dirs = [d for d in get_storage_manager().experiments_path.iterdir() if d.is_dir()]
            exp_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Limit to max 20 folders
            for exp_dir in exp_dirs[:20]:
                folder_videos = []
                folder_size = 0
                
                # Get all video files in the folder hierarchy (support both .mp4 and .avi)
                latest_timestamp = None
                for pattern in ["*.mp4", "*.avi"]:
                    for video_file in exp_dir.rglob(pattern):
                        if not video_file.is_file():
                            continue
                        file_stat = video_file.stat()
                        file_size = file_stat.st_size
                        file_timestamp = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                        folder_videos.append({
                            "filename": video_file.name,
                            "path": str(video_file),
                            "timestamp": file_timestamp,
                            "size_bytes": file_size
                        })
                        folder_size += file_size
                        if latest_timestamp is None or file_timestamp > latest_timestamp:
                            latest_timestamp = file_timestamp

                if folder_videos:  # Only add folders with video files
                    folder_videos.sort(key=lambda item: item["timestamp"], reverse=True)
                    experiment_folders.append({
                        "folder_name": exp_dir.name,
                        "folder_path": str(exp_dir),
                        "creation_time": latest_timestamp or datetime.fromtimestamp(exp_dir.stat().st_mtime).isoformat(),
                        "video_count": len(folder_videos),
                        "total_size_bytes": folder_size,
                        "videos": folder_videos,
                        "type": "experiment_folder"
                    })


        return ApiResponse(
            success=True,
            message=f"Found {len(experiment_folders)} experiment folders",
            data={"experiment_folders": experiment_folders,
                  "total_experiment_folders": len(experiment_folders)},
        )

    except Exception as e:
        logger.error(f"Error listing recordings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve recordings list"
        )


@router.get("/recording/{recording_id}")
@router.head("/recording/{recording_id}")
async def download_recording(
    recording_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Download a specific recording file
    
    Searches in rolling clips and experiment folders for the specified recording.
    """
    try:
        file_path = _resolve_recording_file_path(recording_id)
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recording '{recording_id}' not found"
            )

        return FileResponse(
            file_path, filename=recording_id,
            media_type="video/x-msvideo" if file_path.suffix.lower() == ".avi" else "video/mp4",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading recording '{recording_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download recording '{recording_id}'"
        )


# ========== LIVE STREAMING ENDPOINTS ==========

@router.post("/streaming/session")
async def create_streaming_session(
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Create a new live streaming session for the authenticated user (one shared H.264 stream).
    503 with the reason when the encoder (ffmpeg.exe) is missing.
    """
    try:

        streaming_service = get_live_streaming_service()

        # Create session
        session = await streaming_service.create_session(
            user_id=current_user["user_id"],
            user_name=current_user["username"],
            client_ip=connection.client_ip or "unknown",
        )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Cannot create streaming session - service at capacity or user already has active session"
            )
        
        logger.info("StreamingAPI | event=session_created | session=%s | user=%s", session.session_id, current_user['username'])
        
        return ApiResponse(
            success=True,
            message="Streaming session created successfully",
            data=session.to_dict()
        )
        
    except EncoderUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.error("StreamingAPI | event=session_create_error | error=%s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create streaming session"
        )


@router.websocket("/streaming/video/{session_id}")
async def streaming_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live video streaming.
    Handles the streaming session lifecycle and frame delivery.
    
    Args:
        websocket: WebSocket connection
        session_id: Streaming session identifier
    """
    try:
        
        streaming_service = get_live_streaming_service()
        
        # Handle the complete WebSocket session
        await streaming_service.handle_websocket_session(session_id, websocket)
        
        logger.info(f"Streaming WebSocket session {session_id} completed")
        
    except Exception as e:
        logger.error(f"Error in streaming WebSocket {session_id}: {e}")
        try:
            await websocket.close(code=4500, reason="Internal error")
        except:
            pass


@router.get("/streaming/status")
async def get_streaming_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get overall streaming service status.
    Includes active sessions, resource usage, and priority mode.
    
    Returns:
        Streaming service status
    """
    try:
        
        streaming_service = get_live_streaming_service()
        service_status = streaming_service.get_status()
        
        return ApiResponse(success=True, message="Streaming service status retrieved",
                           data={"status": service_status})

    except Exception as e:
        logger.error(f"Error getting streaming status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get streaming status"
        )


@router.delete("/streaming/session/{session_id}")
async def stop_streaming_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Stop a streaming session.
    
    Args:
        session_id: Streaming session identifier
        
    Returns:
        Success confirmation
    """
    try:
        
        streaming_service = get_live_streaming_service()
        
        # Stop the session (idempotent - succeeds even if session already terminated)
        success = await streaming_service.stop_session(session_id, current_user["user_id"])
        
        if not success:
            # Check if session was already terminated (common case due to WebSocket disconnect)
            # In this case, treat as successful since the goal (stop session) was achieved
            logger.info(f"Streaming session {session_id} already terminated or not found - treating as successful")
            # Don't raise 404, return success since session is effectively stopped
        
        if success:
            logger.info(f"Explicitly stopped streaming session {session_id} for user {current_user['username']}")
        else:
            logger.info(f"Streaming session {session_id} already stopped for user {current_user['username']}")
        
        return ApiResponse(
            success=True,
            message="Streaming session stopped successfully",
            data={"session_id": session_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping streaming session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop streaming session"
        )
