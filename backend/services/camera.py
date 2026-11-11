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

import threading
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from backend.config import CAMERA_CONFIG
from backend.services.camera_runtime import CameraRuntime
from backend.services.clip_transcoder import ClipTranscoder, finalized_clips
from backend.services.shared_frame_buffer import get_shared_frame_buffer

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
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        
        # Configuration
        self.recording_duration = CAMERA_CONFIG["recording_duration_minutes"] * 60  # Convert to seconds
        
        # Auto-cleanup configuration
        self.cleanup_lock = threading.Lock()
        
        from backend.services.storage_manager import get_storage_manager
        self._storage_manager = get_storage_manager()
        self.video_path = self._storage_manager.video_path
        self.rolling_clips_path = self._storage_manager.rolling_clips_path
        self.experiments_path = self._storage_manager.experiments_path
        self.clips_lock = self._storage_manager.clips_lock
        # Finalized MJPEG clips are re-stored as H.264 MP4 by a low-priority ffmpeg child.
        self.clip_transcoder = ClipTranscoder(self.rolling_clips_path, self.clips_lock,
                                              CAMERA_CONFIG["clip_h264_kbps"], CAMERA_CONFIG["clip_denoise_filter"])
        
        # Integration with new live streaming system
        self.shared_frame_buffer = get_shared_frame_buffer()
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._cleanup_future = None

        
        self.runtime = CameraRuntime(self.rolling_clips_path, self.recording_duration,
                                     self._publish_frame, self._accept_clip)
        self.runtime.no_frame_seconds = CAMERA_CONFIG.get("no_frame_seconds", 10)
        self.runtime.startup_seconds = CAMERA_CONFIG.get("startup_seconds", 20)
        self.runtime.capture_fps = CAMERA_CONFIG["capture_fps"]
        logger.info("CameraService initialized")
    
    def _publish_frame(self, frame):
        if frame is None:
            self.shared_frame_buffer.clear()
        else:
            self.shared_frame_buffer.put_frame(frame)

    def _accept_clip(self, clip):
        with self.cleanup_lock:
            if self._cleanup_future is None or self._cleanup_future.done():
                self._cleanup_future = self.executor.submit(self.cleanup_rolling_clips)
        self.clip_transcoder.wake()

    def wait_for_stored_clips(self, minutes, timeout=60.0):
        """Before archiving the last `minutes`, give their pending H.264 conversion time to finish.

        On timeout or failure the archive copies the MJPEG files instead; nothing is skipped.
        """
        cutoff = datetime.now() - timedelta(minutes=minutes)
        with self.clips_lock:
            recent = [Path(clip["path"]) for clip in self._storage_manager._read_finalized_clips()
                      if clip.get("timestamp") and clip["timestamp"] >= cutoff]
        if not self.clip_transcoder.wait_for(recent, timeout):
            logger.warning("Archiving before every recent clip was stored as H.264: %s",
                           self.clip_transcoder.status())

    def detect_cameras(self):
        devices = self.runtime.run("refresh")
        return devices

    def start_recording(self, camera_id):
        try:
            self.runtime.run("start", camera_id=camera_id)
            return True
        except Exception as exc:
            logger.error("Camera recording start failed: %s", exc)
            return False

    def stop_recording(self, camera_id):
        if camera_id != self.runtime.camera_id or not self.runtime.recording_requested:
            return False
        try:
            self.runtime.run("stop")
            return True
        except Exception as exc:
            logger.error("Camera stop failed: %s", exc)
            return False

    def cleanup_rolling_clips(self):
        return self._storage_manager.cleanup_rolling_clips()

    def get_camera_status(self):
        health = self.runtime.status()
        cameras = self.runtime.devices
        return {"health": health, "clip_storage": self.clip_transcoder.status(), "cameras": cameras}

    def shutdown(self):
        self.runtime.shutdown()
        self.clip_transcoder.stop()
        self.executor.shutdown(wait=True)


# Global instance
_camera_service = None

def get_camera_service() -> CameraService:
    """Get the global camera service instance"""
    global _camera_service
    if _camera_service is None:
        _camera_service = CameraService()
    return _camera_service
