"""
RobotControl Simplified Backend - Camera API Endpoints

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
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, Response

# Import services with relative imports (within backend directory)
from backend.services.auth import get_current_user, get_current_admin_user
from backend.services.camera import get_camera_service

# Import types and config with proper package resolution
try:
    from backend.models import UserModel, ApiResponse
except ImportError:  # pragma: no cover - fallback for legacy packaging
    from models import UserModel, ApiResponse

try:
    from backend.config import VIDEO_PATH, CAMERA_CONFIG
except ImportError:  # pragma: no cover - fallback for legacy packaging
    from config import VIDEO_PATH, CAMERA_CONFIG

try:
    from backend.constants import ERROR_MESSAGES, WS_HEARTBEAT_INTERVAL
except ImportError:  # pragma: no cover - fallback for legacy packaging
    from constants import ERROR_MESSAGES, WS_HEARTBEAT_INTERVAL

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error
)

# Configure logging
logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/camera", tags=["camera"])

# Camera system paths
VIDEO_BASE_PATH = Path(VIDEO_PATH)
ROLLING_CLIPS_PATH = VIDEO_BASE_PATH / "rolling_clips"
EXPERIMENTS_PATH = VIDEO_BASE_PATH / "experiments"


@router.get("/cameras")
async def list_cameras(current_user: UserModel = Depends(get_current_user)):
    """
    Get list of available cameras and their current status
    
    Returns comprehensive camera information including detection status,
    recording state, and live stream availability.
    """
    start_time = time.time()
    
    try:
        camera_service = get_camera_service()
        
        # Detect available cameras if not already done
        if not camera_service.cameras:
            camera_service.detect_cameras()
        
        camera_status = camera_service.get_camera_status()
        
        cameras = []
        for camera_info in camera_status["cameras"]:
            camera_data = {
                "id": camera_info["id"],
                "name": camera_info["name"],
                "width": camera_info.get("width", 640),
                "height": camera_info.get("height", 480),
                "fps": camera_info.get("fps", 30),
                "status": "active" if camera_info["recording"] else "available",
                "is_recording": camera_info["recording"],
                "has_live_stream": camera_info["has_live_stream"]
            }
            cameras.append(camera_data)
        
        response_data = {
            "cameras": cameras,
            "total_count": len(cameras),
            "recording_count": camera_status["cameras_recording"],
            "system_status": "healthy" if len(cameras) > 0 else "no_cameras"
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "list_cameras")
        metadata.add_metadata("user_id", getattr(current_user, 'user_id', current_user.get('user_id') if isinstance(current_user, dict) else None))
        metadata.add_metadata("camera_count", len(cameras))
        metadata.add_metadata("recording_count", camera_status["cameras_recording"])
        
        return ResponseFormatter.success(
            data=response_data,
            metadata=metadata,
            message=f"Found {len(cameras)} cameras"
        )
        
    except Exception as e:
        logger.error(f"Error listing cameras: {e}")
        return ResponseFormatter.server_error(
            message="Failed to retrieve camera list",
            details=str(e)
        )


@router.get("/stream/{camera_id}")
async def get_camera_stream(
    camera_id: int,
    current_user: UserModel = Depends(get_current_user)
):
    """
    Get live MJPEG stream from specified camera
    
    Returns continuous MJPEG stream compatible with web browsers.
    Camera must be recording to provide live stream.
    """
    try:
        camera_service = get_camera_service()
        
        # Validate camera exists
        if camera_id not in camera_service.cameras:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )
        
        # Check if camera is recording (required for live stream)
        if camera_id not in camera_service.recording_threads:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Camera {camera_id} is not recording. Start recording first."
            )
        
        async def generate_mjpeg_stream():
            """Generate MJPEG stream from camera frames"""
            try:
                frame_count = 0
                while True:
                    # Get latest frame from camera service
                    frame_data = camera_service.get_live_frame(camera_id)
                    
                    if frame_data:
                        yield (
                            b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n' + 
                            frame_data + b'\r\n'
                        )
                        frame_count += 1
                    else:
                        # Send placeholder frame if no data available
                        yield (
                            b'--frame\r\n'
                            b'Content-Type: text/plain\r\n\r\n'
                            b'Camera feed temporarily unavailable\r\n'
                        )
                    
                    # Control stream frame rate
                    await asyncio.sleep(1/15)  # 15 FPS for web streaming
                    
            except Exception as e:
                logger.error(f"Error generating camera stream: {e}")
                yield (
                    b'--frame\r\n'
                    b'Content-Type: text/plain\r\n\r\n'
                    b'Stream error occurred\r\n'
                )
        
        return StreamingResponse(
            generate_mjpeg_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting camera stream for camera {camera_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stream for camera {camera_id}"
        )


@router.post("/start-recording/{camera_id}")
async def start_camera_recording(
    camera_id: int,
    current_user: UserModel = Depends(get_current_admin_user)
):
    """
    Start recording on specified camera (Admin only)
    
    Begins continuous recording with rolling clips and enables live streaming.
    """
    try:
        camera_service = get_camera_service()
        
        # Detect cameras if not already done
        if not camera_service.cameras:
            camera_service.detect_cameras()
        
        # Validate camera exists
        if camera_id not in camera_service.cameras:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )
        
        # Start recording
        success = camera_service.start_recording(camera_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Failed to start recording on camera {camera_id}. It may already be recording."
            )
        
        logger.info(f"Recording started on camera {camera_id} by user {current_user.username}")
        
        return ApiResponse(
            success=True,
            message=f"Recording started on camera {camera_id}",
            data={
                "camera_id": camera_id,
                "status": "recording",
                "started_by": current_user.username,
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting recording on camera {camera_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start camera recording"
        )


@router.post("/stop-recording/{camera_id}")
async def stop_camera_recording(
    camera_id: int,
    current_user: UserModel = Depends(get_current_admin_user)
):
    """
    Stop recording on specified camera (Admin only)
    """
    try:
        camera_service = get_camera_service()
        
        # Validate camera exists
        if camera_id not in camera_service.cameras:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )
        
        # Stop recording
        success = camera_service.stop_recording(camera_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Failed to stop recording on camera {camera_id}. It may not be recording."
            )
        
        logger.info(f"Recording stopped on camera {camera_id} by user {current_user.username}")
        
        return ApiResponse(
            success=True,
            message=f"Recording stopped on camera {camera_id}",
            data={
                "camera_id": camera_id,
                "status": "stopped",
                "stopped_by": current_user.username,
                "stop_time": datetime.utcnow().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping recording on camera {camera_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop camera recording"
        )


@router.get("/recordings")
async def list_recordings(
    camera_id: Optional[int] = None,
    recording_type: Optional[str] = None,
    limit: int = 50,
    current_user: UserModel = Depends(get_current_user)
):
    """
    Get list of camera recordings with optional filtering
    
    Args:
        camera_id: Filter by specific camera
        recording_type: Filter by type (rolling, experiment, manual)
        limit: Number of recordings to return
    """
    try:
        camera_service = get_camera_service()
        
        # Get recent clips from camera service
        clips = camera_service.get_recent_clips(limit=limit)
        
        # Filter by camera_id if specified
        if camera_id is not None:
            clips = [clip for clip in clips if clip["camera_id"] == camera_id]
        
        # Get experiment recordings organized by folder (max 20 folders)
        experiment_folders = []
        if recording_type is None or recording_type == "experiment":
            if EXPERIMENTS_PATH.exists():
                # Get all experiment directories, sorted by modification time (newest first)
                exp_dirs = [d for d in EXPERIMENTS_PATH.iterdir() if d.is_dir()]
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


        # Combine and sort recordings
        all_recordings = []
        
        # Add rolling clips
        if recording_type is None or recording_type == "rolling":
            for clip in clips:
                all_recordings.append({
                    **clip,
                    "type": "rolling",
                    "path": str(ROLLING_CLIPS_PATH / clip["filename"])
                })
        
        # Sort recordings by timestamp (newest first)
        all_recordings.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Apply limit to rolling clips
        all_recordings = all_recordings[:limit]
        
        return ApiResponse(
            success=True,
            message=f"Found {len(all_recordings)} rolling clips and {len(experiment_folders)} experiment folders",
            data={
                "recordings": all_recordings,
                "experiment_folders": experiment_folders,
                "total_rolling_clips": len(all_recordings),
                "total_experiment_folders": len(experiment_folders),
                "filters": {
                    "camera_id": camera_id,
                    "recording_type": recording_type,
                    "limit": limit
                },
                "available_types": ["rolling", "experiment"]
            }
        )
        
    except Exception as e:
        logger.error(f"Error listing recordings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve recordings list"
        )


@router.get("/recording/{recording_id}")
async def download_recording(
    recording_id: str,
    current_user: UserModel = Depends(get_current_user)
):
    """
    Download a specific recording file
    
    Searches in rolling clips and experiment folders for the specified recording.
    """
    try:
        # Security check - prevent directory traversal
        if '..' in recording_id or '/' in recording_id or '\\' in recording_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recording ID"
            )
        
        file_path = None
        
        # Check rolling clips first
        rolling_path = ROLLING_CLIPS_PATH / recording_id
        if rolling_path.exists() and rolling_path.is_file():
            file_path = rolling_path
        
        # Check experiment folders
        if not file_path and EXPERIMENTS_PATH.exists():
            for exp_dir in EXPERIMENTS_PATH.iterdir():
                if exp_dir.is_dir():
                    exp_file = exp_dir / recording_id
                    if exp_file.exists() and exp_file.is_file():
                        file_path = exp_file
                        break
        
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recording '{recording_id}' not found"
            )
        
        def iter_file(file_path: Path):
            """Stream file in chunks"""
            with open(file_path, mode="rb") as file_obj:
                while True:
                    chunk = file_obj.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    yield chunk
        
        # Determine content type based on file extension
        content_type = "video/mp4"
        if file_path.suffix.lower() == ".avi":
            content_type = "video/x-msvideo"
        
        return StreamingResponse(
            iter_file(file_path),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={recording_id}",
                "Content-Length": str(file_path.stat().st_size)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading recording '{recording_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download recording '{recording_id}'"
        )


@router.delete("/recording/{recording_id}")
async def delete_recording(
    recording_id: str,
    current_user: UserModel = Depends(get_current_admin_user)
):
    """
    Delete a specific recording file (Admin only)
    """
    try:
        # Security check
        if '..' in recording_id or '/' in recording_id or '\\' in recording_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recording ID"
            )
        
        deleted = False
        
        # Check rolling clips
        rolling_path = ROLLING_CLIPS_PATH / recording_id
        if rolling_path.exists():
            rolling_path.unlink()
            deleted = True
            logger.info(f"Deleted rolling clip '{recording_id}' by user {current_user.username}")
        
        # Check experiment folders
        if not deleted and EXPERIMENTS_PATH.exists():
            for exp_dir in EXPERIMENTS_PATH.iterdir():
                if exp_dir.is_dir():
                    exp_file = exp_dir / recording_id
                    if exp_file.exists():
                        exp_file.unlink()
                        deleted = True
                        logger.info(f"Deleted experiment recording '{recording_id}' by user {current_user.username}")
                        break
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recording '{recording_id}' not found"
            )
        
        return ApiResponse(
            success=True,
            message=f"Recording '{recording_id}' deleted successfully",
            data={
                "recording_id": recording_id,
                "deleted_by": current_user.username,
                "delete_time": datetime.utcnow().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recording '{recording_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete recording '{recording_id}'"
        )


@router.websocket("/ws/{camera_id}")
async def camera_websocket(websocket: WebSocket, camera_id: int):
    """
    WebSocket endpoint for real-time camera streaming
    
    Provides real-time camera frames and status updates via WebSocket.
    Supports heartbeat for connection monitoring.
    """
    await websocket.accept()
    logger.info(f"WebSocket camera connection established for camera {camera_id}")
    
    camera_service = get_camera_service()
    client_id = f"ws_{id(websocket)}"
    
    try:
        # Validate camera exists
        if camera_id not in camera_service.cameras:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Camera {camera_id} not found"
            }))
            await websocket.close()
            return
        
        # Check if camera is recording
        if camera_id not in camera_service.recording_threads:
            await websocket.send_text(json.dumps({
                "type": "warning",
                "message": f"Camera {camera_id} is not recording. No live frames available."
            }))
        
        # Send initial status
        await websocket.send_text(json.dumps({
            "type": "connected",
            "camera_id": camera_id,
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        last_heartbeat = datetime.utcnow()
        
        # Main communication loop
        while True:
            try:
                # Check for client messages (non-blocking)
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(), 
                        timeout=1.0
                    )
                    
                    data = json.loads(message)
                    
                    if data.get("type") == "ping":
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                        last_heartbeat = datetime.utcnow()
                        
                    elif data.get("type") == "request_frame":
                        # Client requesting a frame
                        frame_data = camera_service.get_live_frame(camera_id)
                        if frame_data:
                            # Send frame as base64 data
                            import base64
                            frame_b64 = base64.b64encode(frame_data).decode('utf-8')
                            await websocket.send_text(json.dumps({
                                "type": "frame",
                                "camera_id": camera_id,
                                "data": frame_b64,
                                "timestamp": datetime.utcnow().isoformat()
                            }))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "no_frame",
                                "camera_id": camera_id,
                                "message": "No frame available"
                            }))
                
                except asyncio.TimeoutError:
                    # No message received, continue with periodic tasks
                    pass
                
                # Send heartbeat if needed
                now = datetime.utcnow()
                if (now - last_heartbeat).seconds >= WS_HEARTBEAT_INTERVAL:
                    await websocket.send_text(json.dumps({
                        "type": "heartbeat",
                        "camera_id": camera_id,
                        "timestamp": now.isoformat(),
                        "recording_status": camera_id in camera_service.recording_threads
                    }))
                    last_heartbeat = now
                
                # Short sleep to prevent high CPU usage
                await asyncio.sleep(0.1)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket camera error: {e}")
                try:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Internal error occurred"
                    }))
                except:
                    pass
                break
    
    except Exception as e:
        logger.error(f"WebSocket camera connection error: {e}")
    
    finally:
        logger.info(f"WebSocket camera connection closed for camera {camera_id}")
        try:
            await websocket.close()
        except:
            pass


@router.get("/status")
async def get_camera_system_status(
    current_user: UserModel = Depends(get_current_user)
):
    """
    Get comprehensive camera system status
    
    Returns detailed information about camera system health,
    recording status, and storage information.
    """
    try:
        camera_service = get_camera_service()
        
        # Get camera status
        camera_status = camera_service.get_camera_status()
        
        # Get health check results
        health_info = camera_service.health_check()
        
        # Get storage information
        storage_info = {}
        if VIDEO_BASE_PATH.exists():
            try:
                import shutil
                disk_usage = shutil.disk_usage(VIDEO_BASE_PATH)
                storage_info = {
                    "total_gb": round(disk_usage.total / (1024**3), 2),
                    "used_gb": round((disk_usage.total - disk_usage.free) / (1024**3), 2),
                    "free_gb": round(disk_usage.free / (1024**3), 2),
                    "usage_percent": round((disk_usage.total - disk_usage.free) / disk_usage.total * 100, 1)
                }
            except Exception as e:
                logger.warning(f"Could not get storage info: {e}")
                storage_info = {"error": "Unable to retrieve storage information"}
        
        # Get automation status if available
        automation_status = None
        try:
            from services.automatic_recording import get_automatic_recording_service
            auto_recording_service = get_automatic_recording_service()
            automation_status = auto_recording_service.get_automation_status().to_dict()
        except Exception as e:
            logger.debug(f"Could not get automation status: {e}")
            automation_status = {
                "is_active": False,
                "state": "unavailable",
                "error": "Automatic recording service not available"
            }
        
        return ApiResponse(
            success=True,
            message="Camera system status retrieved",
            data={
                "system_health": health_info,
                "camera_status": camera_status,
                "storage_info": storage_info,
                "automation_status": automation_status,
                "configuration": {
                    "max_cameras": CAMERA_CONFIG["max_cameras"],
                    "recording_duration_minutes": CAMERA_CONFIG["recording_duration_minutes"],
                    "archive_duration_minutes": CAMERA_CONFIG["archive_duration_minutes"],
                    "rolling_clips_count": CAMERA_CONFIG["rolling_clips_count"]
                },
                "paths": {
                    "video_base": str(VIDEO_BASE_PATH),
                    "rolling_clips": str(ROLLING_CLIPS_PATH),
                    "experiments": str(EXPERIMENTS_PATH)
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting camera system status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve camera system status"
        )


@router.get("/health")
async def camera_health_check():
    """
    Camera service health check endpoint
    
    Public endpoint for monitoring camera service health.
    """
    try:
        camera_service = get_camera_service()
        health_info = camera_service.health_check()
        
        if health_info["healthy"]:
            return ApiResponse(
                success=True,
                message="Camera service is healthy",
                data=health_info
            )
        else:
            return Response(
                content=json.dumps({
                    "success": False,
                    "message": "Camera service is unhealthy",
                    "data": health_info
                }),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="application/json"
            )
            
    except Exception as e:
        logger.error(f"Camera health check error: {e}")
        return Response(
            content=json.dumps({
                "success": False,
                "message": "Camera health check failed",
                "data": {"error": str(e)}
            }),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )


# ============================================================================
# AUTOMATIC RECORDING AUTOMATION ENDPOINTS
# ============================================================================

@router.get("/automation/status")
async def get_automation_status(current_user: UserModel = Depends(get_current_user)):
    """
    Get current automatic recording automation status
    
    Returns comprehensive status including configuration, statistics, and current state.
    Available to all authenticated users for monitoring purposes.
    """
    try:
        from services.automatic_recording import get_automatic_recording_service
        
        auto_recording_service = get_automatic_recording_service()
        automation_status = auto_recording_service.get_automation_status()
        
        return ApiResponse(
            success=True,
            message="Automation status retrieved successfully",
            data=automation_status.to_dict()
        )
        
    except ImportError:
        logger.error("CameraAPI | event=automation_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Automatic recording service not available"
        )
    except Exception as e:
        logger.error(f"Error getting automation status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve automation status"
        )


@router.post("/automation/start")
async def start_automation(
    camera_id: Optional[int] = None,
    current_user: UserModel = Depends(get_current_admin_user)
):
    """
    Manually start automatic recording (Admin only)
    
    Args:
        camera_id: Optional camera ID to use (uses primary camera if not specified)
        
    Bypasses startup delay and begins recording immediately.
    Useful for restarting after manual stops or configuration changes.
    """
    try:
        from services.automatic_recording import get_automatic_recording_service
        
        auto_recording_service = get_automatic_recording_service()
        
        # Handle manual override to start recording
        result = auto_recording_service.handle_manual_override("start", camera_id)
        
        if result["success"]:
            logger.info(f"Manual automation start by user {current_user.username}: {result}")
            
            return ApiResponse(
                success=True,
                message=result["message"],
                data={
                    "action": result["action"],
                    "camera_id": result.get("camera_id"),
                    "manual_override": result.get("manual_override", False),
                    "started_by": current_user.username,
                    "start_time": datetime.utcnow().isoformat()
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result["message"]
            )
        
    except ImportError:
        logger.error("CameraAPI | event=automation_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Automatic recording service not available"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting automation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start automatic recording"
        )


@router.post("/automation/stop") 
async def stop_automation(current_user: UserModel = Depends(get_current_admin_user)):
    """
    Manually stop automatic recording (Admin only)
    
    Stops automatic recording and prevents automatic restart.
    Recording can be restarted manually using the start endpoint.
    """
    try:
        from services.automatic_recording import get_automatic_recording_service
        
        auto_recording_service = get_automatic_recording_service()
        
        # Handle manual override to stop recording
        result = auto_recording_service.handle_manual_override("stop")
        
        if result["success"]:
            logger.info(f"Manual automation stop by user {current_user.username}: {result}")
            
            return ApiResponse(
                success=True,
                message=result["message"],
                data={
                    "action": result["action"],
                    "manual_override": result.get("manual_override", False),
                    "stopped_by": current_user.username,
                    "stop_time": datetime.utcnow().isoformat()
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result["message"]
            )
        
    except ImportError:
        logger.error("CameraAPI | event=automation_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Automatic recording service not available"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping automation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop automatic recording"
        )


# ========== LIVE STREAMING ENDPOINTS ==========

@router.post("/streaming/session")
async def create_streaming_session(
    quality: Optional[str] = "adaptive",
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new live streaming session for the authenticated user.
    
    Args:
        quality: Initial quality setting (high/medium/low/adaptive)
        
    Returns:
        Streaming session information
    """
    try:
        from backend.services.live_streaming import get_live_streaming_service
        
        streaming_service = get_live_streaming_service()
        
        # Create session
        session = await streaming_service.create_session(
            user_id=current_user["user_id"],
            user_name=current_user["username"],
            client_ip="127.0.0.1",  # Would be extracted from request in production
            quality=quality or "adaptive"
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
        
    except ImportError:
        logger.error("StreamingAPI | event=service_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live streaming service not available"
        )
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
        from backend.services.live_streaming import get_live_streaming_service
        
        streaming_service = get_live_streaming_service()
        
        # Handle the complete WebSocket session
        await streaming_service.handle_websocket_session(session_id, websocket)
        
        logger.info(f"Streaming WebSocket session {session_id} completed")
        
    except ImportError:
        logger.error("StreamingAPI | event=service_unavailable")
        await websocket.close(code=4503, reason="Service unavailable")
    except Exception as e:
        logger.error(f"Error in streaming WebSocket {session_id}: {e}")
        try:
            await websocket.close(code=4500, reason="Internal error")
        except:
            pass


@router.get("/streaming/status")
async def get_streaming_status(
    current_user: UserModel = Depends(get_current_user)
):
    """
    Get overall streaming service status.
    Includes active sessions, resource usage, and priority mode.
    
    Returns:
        Streaming service status
    """
    try:
        from backend.services.live_streaming import get_live_streaming_service
        
        streaming_service = get_live_streaming_service()
        service_status = streaming_service.get_status()
        
        # Include additional system information
        resource_usage = streaming_service.get_resource_usage()
        
        return ApiResponse(
            success=True,
            message="Streaming service status retrieved",
            data={
                "status": service_status.to_dict(),
                "resource_usage": resource_usage
            }
        )
        
    except ImportError:
        logger.error("StreamingAPI | event=service_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live streaming service not available"
        )
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
        from backend.services.live_streaming import get_live_streaming_service
        
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
        
    except ImportError:
        logger.error("StreamingAPI | event=service_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live streaming service not available"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping streaming session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop streaming session"
        )
