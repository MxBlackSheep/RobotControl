"""
RobotControl Camera Service

Consolidated camera management service that combines functionality from:
- SimpleCameraRecorder: Recording and streaming
- SimpleExperimentArchiver: Experiment video archiving

Features:
- Camera detection and management
- Video recording with rolling clips
- Live streaming capabilities  
- Experiment video archiving
- Thread-safe operations
"""

import os
import json
import threading
import time
import logging
import shutil
from datetime import datetime
from collections import deque
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from backend.config import CAMERA_CONFIG, VIDEO_PATH
from backend.services.camera_runtime import CameraRuntime
from backend.services.shared_frame_buffer import get_shared_frame_buffer
from backend.services.storage_manager import get_storage_manager
from backend.utils.data_paths import get_videos_path, is_compiled_mode

# Configure logging
logger = logging.getLogger(__name__)

class CameraService:
    """
    Simplified camera service for unified camera management
    
    Singleton service that provides:
    - Camera detection and initialization
    - Video recording with rolling clips
    - Live streaming support
    - Experiment video archiving
    - Camera health monitoring
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(CameraService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        
        # Configuration
        self.max_cameras = CAMERA_CONFIG["max_cameras"]
        self.recording_duration = CAMERA_CONFIG["recording_duration_minutes"] * 60  # Convert to seconds
        self.archive_duration = CAMERA_CONFIG["archive_duration_minutes"] * 60
        self.rolling_clips_count = CAMERA_CONFIG["rolling_clips_count"]
        
        # Auto-cleanup configuration
        self.cleanup_interval = 1 * 60  # 1 minute for debugging
        self.last_cleanup_time = time.time()
        self.cleanup_lock = threading.Lock()
        
        # Paths - use data path manager for portable deployment
        # Initialize video paths with fallbacks for modular design
        if is_compiled_mode():
            self.video_path = get_videos_path()
            logger.info("Compiled mode - using packaged video directory: %s", self.video_path)
        else:
            configured = Path(VIDEO_PATH) if VIDEO_PATH else get_videos_path()
            if not configured.is_absolute():
                project_root = Path(__file__).resolve().parents[2]  # repo root
                configured = (project_root / configured).resolve()
            self.video_path = configured
            logger.info("Development mode - using video path: %s", self.video_path)
        self.rolling_clips_path = self.video_path / "rolling_clips"
        self.experiments_path = self.video_path / "experiments"
        
        # Create directories
        self._create_directories()
        
        # Camera management
        self.cameras: Dict[int, Dict[str, Any]] = {}
        # Don't use maxlen - we need to track what gets removed for file deletion
        self.rolling_clips: deque = deque()
        
        # Load existing clips into memory to prevent orphan deletion on startup
        self._load_existing_clips()
        
        # Thread safety
        self.camera_lock = threading.Lock()
        self.clips_lock = threading.Lock()
        
        # Integration with new live streaming system
        self.streaming_integration_enabled = False
        self.shared_frame_buffer = None
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._cleanup_future = None

        # Lazy-loaded storage manager for experiment archiving
        self._storage_manager = None
        
        self.runtime = CameraRuntime(self.rolling_clips_path, self.recording_duration,
                                     self._publish_frame, self._accept_clip)
        self.runtime.no_frame_seconds = CAMERA_CONFIG.get("no_frame_seconds", 10)
        self.runtime.startup_seconds = CAMERA_CONFIG.get("startup_seconds", 20)
        logger.info("CameraService initialized")
    
    def enable_streaming_integration(self):
        """
        Enable integration with the new live streaming system.
        Called during startup to connect with SharedFrameBuffer for live streaming.
        """
        try:
            self.shared_frame_buffer = get_shared_frame_buffer()
            self.streaming_integration_enabled = True
            logger.info("Streaming integration enabled")
        except Exception as exc:
            logger.error("Failed to enable streaming integration: %s", exc)
    
    def disable_streaming_integration(self):
        """
        Disable streaming integration.
        Called during shutdown or if streaming is disabled.
        """
        self.streaming_integration_enabled = False
        self.shared_frame_buffer = None
        logger.info("Streaming integration disabled")

    def _get_storage_manager(self):
        """Lazily load the storage manager used for archiving experiment clips."""
        if self._storage_manager is None:
            self._storage_manager = get_storage_manager()
        return self._storage_manager
    
    def _create_directories(self):
        """Create necessary directories for video storage"""
        try:
            self.video_path.mkdir(parents=True, exist_ok=True)
            self.rolling_clips_path.mkdir(parents=True, exist_ok=True)
            self.experiments_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Video directories created at: {self.video_path}")
        except Exception as e:
            logger.error(f"Failed to create video directories: {e}")
    
    def _read_finalized_clips(self):
        clips = []
        for path in sorted(self.rolling_clips_path.glob("clip_*.avi")):
            if ".partial." in path.name:
                continue
            try:
                sidecar = path.with_suffix(".json")
                if sidecar.exists():
                    clip = json.loads(sidecar.read_text(encoding="utf-8"))
                    clip["path"] = str(path)
                    clip["timestamp"] = datetime.fromisoformat(clip["timestamp"])
                else:
                    # Legacy clips remain usable; unknown metadata stays unknown.
                    stamp = datetime.strptime(path.stem.split("_", 1)[1], "%Y%m%d_%H%M%S")
                    clip = {"path": str(path), "timestamp": stamp, "camera_id": None,
                            "frame_count": None, "actual_duration": None}
                clips.append(clip)
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("Cannot read finalized clip %s: %s", path.name, exc)
        return clips

    def _load_existing_clips(self):
        self.rolling_clips.extend(self._read_finalized_clips())

    @property
    def recording_threads(self):
        # Compatibility for legacy stream routes; ownership lives only in runtime.
        if self.runtime.status()["recording_state"] == "recording":
            return {self.runtime.camera_id: self.runtime.process}
        return {}

    def _publish_frame(self, frame):
        if not self.streaming_integration_enabled:
            self.enable_streaming_integration()
        if frame is None:
            self.shared_frame_buffer.clear()
        else:
            self.shared_frame_buffer.put_frame(frame)

    def _accept_clip(self, clip):
        clip = dict(clip)
        clip["timestamp"] = datetime.fromisoformat(clip["timestamp"])
        with self.clips_lock:
            if not any(item["path"] == clip["path"] for item in self.rolling_clips):
                self.rolling_clips.append(clip)
        with self.cleanup_lock:
            if self._cleanup_future is None or self._cleanup_future.done():
                self._cleanup_future = self.executor.submit(self._cleanup_orphaned_files)

    def detect_cameras(self):
        devices = self.runtime.run("refresh")
        self.cameras = {device["id"]: device for device in devices}
        return devices

    def start_recording(self, camera_id):
        try:
            self.runtime.run("start", camera_id=camera_id)
            self.cameras = {device["id"]: device for device in self.runtime.devices}
            return True
        except Exception as exc:
            logger.error("Camera recording start failed: %s", exc)
            return False

    def prepare_automatic_recording(self, callback):
        self.runtime.recording_requested = True
        self.runtime.on_recording_started = callback

    def automatic_camera_id(self, fallback):
        if self.runtime.identity:
            from backend.services.camera_devices import resolve_device
            return resolve_device(self.runtime.devices, self.runtime.identity)["id"]
        return fallback

    def stop_recording(self, camera_id):
        if camera_id != self.runtime.camera_id or not self.runtime.recording_requested:
            return False
        try:
            self.runtime.run("stop")
            return True
        except Exception as exc:
            logger.error("Camera stop failed: %s", exc)
            return False

    def _cleanup_orphaned_files(self):
        with self.clips_lock:
            clips = self._read_finalized_clips()
            for clip in clips[:-self.rolling_clips_count]:
                path = Path(clip["path"])
                try:
                    path.unlink(missing_ok=True)
                    path.with_suffix(".json").unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Cannot remove old clip %s: %s", path.name, exc)
            self.rolling_clips.clear()
            self.rolling_clips.extend(c for c in clips if Path(c["path"]).exists())

    def _sync_memory_with_filesystem(self):
        with self.clips_lock:
            self.rolling_clips.clear()
            self.rolling_clips.extend(self._read_finalized_clips())

    def archive_experiment_videos(self, experiment_id: int, method_name: str) -> str:
        """
        Archive recent rolling clips for an experiment without re-encoding.

        Copies clips into an experiment-specific directory and returns that path.
        """
        try:
            storage_manager = self._get_storage_manager()
            if not storage_manager:
                logger.error("Storage manager unavailable; cannot archive experiment videos")
                return ""

            result = storage_manager.archive_experiment_videos(
                experiment_id=str(experiment_id),
                method_name=method_name,
                rolling_clips=self.rolling_clips,
                clips_lock=self.clips_lock,
            )

            if result.success:
                size_mb = result.archive_size_bytes / (1024 * 1024) if result.archive_size_bytes else 0.0
                logger.info(
                    "Archived %s clips for experiment %s into %s (%.1f MB)",
                    result.clips_archived,
                    method_name,
                    result.archive_path,
                    size_mb,
                )
            else:
                logger.warning(
                    "Archive operation incomplete for experiment %s: %s",
                    method_name,
                    result.error_message or "unknown error",
                )
                if result.warnings:
                    for warning in result.warnings:
                        logger.debug("Archive warning: %s", warning)

            return result.archive_path or ""

        except Exception as e:
            logger.error(f"Failed to archive experiment videos: {e}")
            return ""
    
    def get_camera_status(self):
        health = self.runtime.status()
        cameras = self.runtime.devices
        self.cameras = {device["id"]: device for device in cameras}
        recording = health["recording_state"] == "recording"
        return {"cameras_detected": len(cameras), "cameras_recording": int(recording),
                "rolling_clips_count": len(self.rolling_clips), "video_storage_path": str(self.video_path),
                "health": health,
                "cameras": [{**camera, "recording": recording and camera["id"] == health["camera_id"],
                    "has_live_stream": health["capture_state"] == "connected" and camera["id"] == health["camera_id"]}
                    for camera in cameras]}

    def get_recent_clips(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get list of recent video clips
        
        Args:
            limit: Maximum number of clips to return
            
        Returns:
            List of clip information dictionaries
        """
        with self.clips_lock:
            recent_clips = list(self.rolling_clips)[-limit:]
            
        return [
            {
                "filename": Path(clip["path"]).name,
                "timestamp": clip["timestamp"].isoformat(),
                "camera_id": clip["camera_id"],
                "frame_count": clip["frame_count"],
                "size_bytes": Path(clip["path"]).stat().st_size if Path(clip["path"]).exists() else 0
            }
            for clip in reversed(recent_clips)
        ]
    
    def health_check(self):
        health = self.runtime.status()
        accessible = self.video_path.exists() and os.access(self.video_path, os.W_OK)
        try:
            free = shutil.disk_usage(self.video_path).free / 1024**3
        except OSError:
            free = 0
        return {**health, "healthy": accessible and health["capture_state"] == "connected",
                "storage_accessible": accessible, "active_recording_threads": len(self.recording_threads),
                "total_cameras": len(self.runtime.devices), "free_disk_space_gb": round(free, 2),
                "rolling_clips_count": len(self.rolling_clips)}

    def shutdown(self):
        self.runtime.shutdown()
        self.executor.shutdown(wait=True)


# Global instance
_camera_service = None

def get_camera_service() -> CameraService:
    """Get the global camera service instance"""
    global _camera_service
    if _camera_service is None:
        _camera_service = CameraService()
    return _camera_service
