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
import cv2
import threading
import time
import logging
import shutil
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from backend.config import CAMERA_CONFIG, VIDEO_PATH
from backend.constants import CAMERA_STREAM_FPS, VIDEO_CODEC, CAMERA_DETECTION_TIMEOUT
from backend.models import CameraRecordingModel
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
        self.recording_threads: Dict[int, threading.Thread] = {}
        self.stop_events: Dict[int, threading.Event] = {}
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

        # Lazy-loaded storage manager for experiment archiving
        self._storage_manager = None
        
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
    
    def _load_existing_clips(self):
        """Load existing clip files into rolling_clips to prevent orphan deletion on startup"""
        try:
            # Get all existing clip files sorted by creation time
            clip_files = list(self.rolling_clips_path.glob("clip_*.avi"))
            
            if not clip_files:
                logger.debug("No existing clips found on startup")
                return
            
            # Sort by creation time (oldest first)
            clip_files.sort(key=lambda f: f.stat().st_ctime)
            
            # Keep only the most recent clips up to the limit
            if len(clip_files) > self.rolling_clips_count:
                # Too many files - keep only the newest ones
                clips_to_keep = clip_files[-self.rolling_clips_count:]
                clips_to_delete = clip_files[:-self.rolling_clips_count]
                
                logger.info(f"Startup: Found {len(clip_files)} clips, keeping {len(clips_to_keep)}, deleting {len(clips_to_delete)} old ones")
                
                # Delete old clips
                for old_clip in clips_to_delete:
                    try:
                        os.remove(str(old_clip))
                        logger.debug(f"Deleted old clip during startup: {old_clip.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete old clip during startup: {e}")
                
                clip_files = clips_to_keep
            
            # Load remaining clips into memory
            for clip_file in clip_files:
                try:
                    # Parse timestamp from filename: clip_YYYYMMDD_HHMMSS.avi
                    filename = clip_file.stem
                    timestamp_str = filename.split("_", 1)[1]  # Remove "clip_" prefix
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    
                    # Create clip entry
                    clip_entry = {
                        "path": str(clip_file),
                        "timestamp": timestamp,
                        "camera_id": 0,  # Assume camera 0
                        "frame_count": 1500,  # Approximate
                        "actual_duration": 60.0  # Approximate
                    }
                    
                    self.rolling_clips.append(clip_entry)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse existing clip {clip_file}: {e}")
            
            logger.info(f"Loaded {len(self.rolling_clips)} existing clips into memory")
                    
        except Exception as e:
            logger.error(f"Error loading existing clips: {e}")
    
    def detect_cameras(self) -> List[Dict[str, Any]]:
        """
        Detect available cameras on the system
        
        Returns:
            List of camera information dictionaries
        """
        cameras = []
        
        try:
            for camera_id in range(self.max_cameras):
                # Try to open camera with DirectShow backend (Windows)
                cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
                
                if cap.isOpened():
                    # Get camera properties
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    
                    camera_info = {
                        "id": camera_id,
                        "name": f"Camera {camera_id}",
                        "width": width,
                        "height": height,
                        "fps": fps,
                        "status": "available"
                    }
                    
                    cameras.append(camera_info)
                    self.cameras[camera_id] = camera_info
                    
                    logger.info(f"Detected camera {camera_id}: {width}x{height} @ {fps}fps")
                
                cap.release()
                
        except Exception as e:
            logger.error(f"Error detecting cameras: {e}")
        
        logger.info(f"Found {len(cameras)} available cameras")
        return cameras
    
    def start_recording(self, camera_id: int) -> bool:
        """
        Start recording from specified camera
        
        Args:
            camera_id: ID of the camera to start recording
            
        Returns:
            True if recording started successfully
        """
        try:
            with self.camera_lock:
                if camera_id in self.recording_threads:
                    logger.warning(f"Camera {camera_id} is already recording")
                    return False
                
                if camera_id not in self.cameras:
                    logger.error(f"Camera {camera_id} not found")
                    return False
                
                # Create stop event and frame lock for this camera
                stop_event = threading.Event()
                self.stop_events[camera_id] = stop_event
                if not self.streaming_integration_enabled:
                    self.enable_streaming_integration()

                # Start recording thread
                recording_thread = threading.Thread(
                    target=self._recording_worker,
                    args=(camera_id, stop_event),
                    name=f"CameraRecorder-{camera_id}"
                )
                recording_thread.daemon = True
                recording_thread.start()
                
                self.recording_threads[camera_id] = recording_thread
                
                logger.info(f"Started recording on camera {camera_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to start recording on camera {camera_id}: {e}")
            return False
    
    def stop_recording(self, camera_id: int) -> bool:
        """
        Stop recording from specified camera
        
        Args:
            camera_id: ID of the camera to stop recording
            
        Returns:
            True if recording stopped successfully
        """
        try:
            with self.camera_lock:
                if camera_id not in self.recording_threads:
                    logger.warning(f"Camera {camera_id} is not recording")
                    return False
                
                # Signal stop and wait for thread to finish
                if camera_id in self.stop_events:
                    self.stop_events[camera_id].set()
                
                thread = self.recording_threads[camera_id]
                # Give more time during shutdown to ensure video files are properly saved
                # MP4 files need extra time to write metadata (moov atom)
                thread.join(timeout=15)
                
                if thread.is_alive():
                    logger.warning(f"Recording thread for camera {camera_id} did not stop gracefully within 15 seconds")
                
                # Cleanup
                del self.recording_threads[camera_id]
                if camera_id in self.stop_events:
                    del self.stop_events[camera_id]
                logger.info(f"Stopped recording on camera {camera_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to stop recording on camera {camera_id}: {e}")
            return False
    
    def _recording_worker(self, camera_id: int, stop_event: threading.Event):
        """
        Worker thread for camera recording
        
        Args:
            camera_id: ID of the camera to record from
            stop_event: Event to signal recording stop
        """
        cap = None
        out = None
        
        try:
            # Initialize camera
            cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
            if not cap.isOpened():
                logger.error(f"Failed to open camera {camera_id}")
                return
            
            # Set camera properties for stability
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            
            # Detect actual camera FPS by measuring frame capture rate
            logger.info(f"Detecting actual camera FPS for camera {camera_id}...")
            fps_test_start = time.time()
            fps_test_frames = 0
            while fps_test_frames < 60 and (time.time() - fps_test_start) < 5:  # Test for max 5 seconds or 60 frames
                ret, frame = cap.read()
                if ret:
                    fps_test_frames += 1
                else:
                    time.sleep(0.01)  # Brief pause if frame read fails
            
            fps_test_duration = time.time() - fps_test_start
            actual_fps = fps_test_frames / fps_test_duration if fps_test_duration > 0 else 20
            actual_fps = max(1.0, min(30.0, actual_fps))  # Clamp between 1-30 FPS for stability
            target_fps = min(7.5, actual_fps)
            logger.info(
                "Camera %s FPS detected: actual=%.1f (tested %s frames in %.1fs) | target rolling clip fps=%.1f",
                camera_id,
                actual_fps,
                fps_test_frames,
                fps_test_duration,
                target_fps,
            )
            
            # Recording loop with scheduled timing for consistent 60-second clips
            next_clip_time = time.time()  # Initialize first clip time
            
            while not stop_event.is_set():
                # Calculate precise timing for this clip
                current_time = time.time()
                if current_time < next_clip_time:
                    # Wait until it's time for the next clip (handles processing delays)
                    wait_time = next_clip_time - current_time
                    if wait_time > 0.001:  # Only sleep if meaningful delay needed
                        time.sleep(wait_time)
                
                # Schedule next clip exactly 60 seconds from now
                clip_start_time = time.time()
                next_clip_time = clip_start_time + self.recording_duration
                
                # Create new clip file - use precise timestamp for this scheduled start
                timestamp = datetime.fromtimestamp(clip_start_time).strftime("%Y%m%d_%H%M%S")
                clip_filename = f"clip_{timestamp}.avi"
                clip_path = self.rolling_clips_path / clip_filename
                
                # Initialize video writer with MJPEG codec (more robust for interruptions)
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                out = cv2.VideoWriter(str(clip_path), fourcc, target_fps, (640, 480))
                
                if not out.isOpened():
                    logger.error(f"Failed to create video writer for {clip_path}")
                    # Schedule next attempt in 1 second to avoid tight loop
                    next_clip_time = time.time() + 1.0
                    continue
                
                frame_count = 0
                frame_interval = 1.0 / target_fps if target_fps > 0 else (1.0 / 7.5)
                next_frame_write_time = time.time()
                
                # Record for specified duration
                logger.info(f"Starting to record clip: {clip_filename}")
                while time.time() < next_clip_time and not stop_event.is_set():
                    ret, frame = cap.read()
                    
                    if not ret:
                        logger.warning(f"Failed to read frame from camera {camera_id}")
                        time.sleep(0.1)
                        continue
                    
                    # Write frame to file
                    now = time.time()
                    if now >= next_frame_write_time or frame_count == 0:
                        out.write(frame)
                        frame_count += 1
                        while next_frame_write_time <= now:
                            next_frame_write_time += frame_interval
                    else:
                        sleep_time = min(0.005, next_frame_write_time - now)
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                    
                    if self.streaming_integration_enabled and self.shared_frame_buffer:
                        try:
                            # Send frame to shared buffer - recording has priority access
                            self.shared_frame_buffer.put_frame(frame)
                            # Log every 300th frame to reduce spam (once per ~15 seconds at ~20fps)
                            if frame_count % 300 == 0:
                                logger.debug(f"Sent frame {frame_count} to SharedFrameBuffer")
                        except Exception as e:
                            logger.error(f"Error sending frame to shared buffer: {e}")
                    
                    # NEW: Update priority manager with current recording FPS
                    if self.streaming_integration_enabled and self.shared_frame_buffer:
                        try:
                            # Calculate current recording FPS
                            if frame_count > 0 and clip_start_time > 0:
                                elapsed = time.time() - clip_start_time
                                current_fps = frame_count / elapsed if elapsed > 0 else 0
                                # Would send this to priority manager for monitoring
                        except Exception as e:
                            logger.debug(f"Error updating priority manager: {e}")
                    
                # Finalize clip immediately (minimize processing delay for next clip)
                actual_duration = time.time() - clip_start_time
                if out:
                    # Force flush any remaining frames to disk
                    try:
                        logger.info(
                            "Finalizing video clip: %s (%s frames, %.1fs, target %.1ffps)",
                            clip_filename,
                            frame_count,
                            actual_duration,
                            target_fps,
                        )
                        # Release video writer quickly - AVI format doesn't need moov atom processing
                        out.release()
                        out = None
                        # Minimal delay for AVI format (much less than MP4's 0.5s requirement)
                        time.sleep(0.05)  # 50ms instead of 500ms
                    except Exception as e:
                        logger.error(f"Error releasing video writer: {e}")
                        out = None
                
                # Add to rolling clips if it has content (fast operation)
                if clip_path.exists() and frame_count > 0:
                    with self.clips_lock:
                        self.rolling_clips.append({
                            "path": str(clip_path),
                            "timestamp": datetime.fromtimestamp(clip_start_time),
                            "camera_id": camera_id,
                            "frame_count": frame_count,
                            "actual_duration": actual_duration
                        })
                        
                        # Immediate cleanup if we exceed limit (don't wait for 10-min interval)
                        if len(self.rolling_clips) > self.rolling_clips_count:
                            excess = len(self.rolling_clips) - self.rolling_clips_count
                            logger.info(f"Buffer exceeded limit ({len(self.rolling_clips)}/{self.rolling_clips_count}), removing {excess} old clips")
                            for _ in range(excess):
                                old_clip = self.rolling_clips.popleft()
                                old_path = Path(old_clip["path"])
                                if old_path.exists():
                                    try:
                                        os.remove(str(old_path))
                                        logger.debug(f"Immediately deleted old clip: {old_path.name}")
                                    except Exception as e:
                                        logger.warning(f"Failed to delete old clip: {e}")
                    
                    if stop_event.is_set():
                        logger.info(f"Saved final clip on shutdown: {clip_filename} ({frame_count} frames)")
                    else:
                        logger.info(f"Created clip: {clip_filename} ({frame_count} frames, {actual_duration:.1f}s)")
                    
                    # Also check for periodic cleanup (every 1 minute) for any orphaned files
                    current_time = time.time()
                    with self.cleanup_lock:
                        if current_time - self.last_cleanup_time >= self.cleanup_interval:
                            self.last_cleanup_time = current_time
                            # Run filesystem cleanup in background
                            self.executor.submit(self._cleanup_orphaned_files)
                            logger.info("Triggered 1-minute filesystem cleanup check")
                elif frame_count > 0:
                    # If file doesn't exist but we have frames, log warning
                    logger.warning(f"Clip {clip_filename} not saved properly ({frame_count} frames recorded)")
                
                # If stop was requested, break out of recording loop
                if stop_event.is_set():
                    logger.info(f"Stop requested for camera {camera_id}, finishing recording")
                    break
                
        except Exception as e:
            logger.error(f"Recording worker error for camera {camera_id}: {e}")
            
        finally:
            # Cleanup resources with extra safety
            try:
                if out:
                    logger.info(f"Final cleanup: Releasing video writer for camera {camera_id}")
                    out.release()
                    # Extra time for file system to complete write (important for MP4 metadata)
                    time.sleep(1.0)
            except Exception as e:
                logger.error(f"Error in final video writer cleanup: {e}")
            
            try:
                if cap:
                    cap.release()
            except Exception as e:
                logger.error(f"Error releasing camera: {e}")
            
            logger.info(f"Recording worker stopped for camera {camera_id}")
    
    def _cleanup_orphaned_files(self):
        """Check filesystem and maintain exactly 120 clips by deleting oldest files"""
        try:
            # Get all clip files in directory sorted by creation time (oldest first)
            all_files = list(self.rolling_clips_path.glob("clip_*.avi"))
            
            if not all_files:
                logger.debug("No clips found in directory during cleanup")
                return
            
            # Sort by creation time (oldest first)
            all_files.sort(key=lambda f: f.stat().st_ctime)
            
            current_count = len(all_files)
            logger.info(f"Filesystem cleanup check: {current_count} files in directory (limit: {self.rolling_clips_count})")
            
            if current_count > self.rolling_clips_count:
                # Delete excess files (oldest ones)
                files_to_delete = current_count - self.rolling_clips_count
                oldest_files = all_files[:files_to_delete]
                
                logger.info(f"Deleting {files_to_delete} oldest clips to maintain {self.rolling_clips_count} file limit")
                
                deleted_count = 0
                for old_file in oldest_files:
                    try:
                        os.remove(str(old_file))
                        deleted_count += 1
                        logger.debug(f"Deleted old clip: {old_file.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete old clip {old_file}: {e}")
                
                if deleted_count > 0:
                    logger.info(f"Filesystem cleanup completed: Deleted {deleted_count} old clips")
                
                # Update in-memory rolling_clips to match filesystem
                self._sync_memory_with_filesystem()
            else:
                logger.debug(f"No filesystem cleanup needed - {current_count} files within limit")
                
        except Exception as e:
            logger.error(f"Error during filesystem cleanup: {e}")
    
    def _sync_memory_with_filesystem(self):
        """Sync the in-memory rolling_clips with what's actually on disk"""
        try:
            # Get all current files on disk
            all_files = list(self.rolling_clips_path.glob("clip_*.avi"))
            all_files.sort(key=lambda f: f.stat().st_ctime)
            
            # Clear and rebuild rolling_clips from filesystem
            with self.clips_lock:
                self.rolling_clips.clear()
                
                for clip_file in all_files:
                    try:
                        # Parse timestamp from filename
                        filename = clip_file.stem
                        timestamp_str = filename.split("_", 1)[1]
                        timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        
                        clip_entry = {
                            "path": str(clip_file),
                            "timestamp": timestamp,
                            "camera_id": 0,
                            "frame_count": 1500,  # Approximate
                            "actual_duration": 60.0
                        }
                        
                        self.rolling_clips.append(clip_entry)
                        
                    except Exception as e:
                        logger.warning(f"Failed to parse clip {clip_file} during sync: {e}")
                
                logger.debug(f"Synced memory with filesystem: {len(self.rolling_clips)} clips in memory")
                
        except Exception as e:
            logger.error(f"Error syncing memory with filesystem: {e}")
    
    def _cleanup_old_clips(self):
        """Clean up old clips beyond the rolling buffer limit"""
        try:
            with self.clips_lock:
                current_count = len(self.rolling_clips)
                logger.info(f"Auto-cleanup check: {current_count}/{self.rolling_clips_count} clips in buffer")
                
                # More aggressive cleanup - maintain exactly at limit, not over it
                if current_count > self.rolling_clips_count:
                    # Remove excess clips from filesystem
                    clips_to_remove = current_count - self.rolling_clips_count
                    logger.info(f"Removing {clips_to_remove} old clips to maintain limit of {self.rolling_clips_count}")
                    
                    removed_count = 0
                    for _ in range(clips_to_remove):
                        if self.rolling_clips:
                            old_clip = self.rolling_clips.popleft()
                            clip_path = Path(old_clip["path"])
                            
                            if clip_path.exists():
                                try:
                                    # Use os.remove for permanent deletion (bypasses recycle bin)
                                    os.remove(str(clip_path))
                                    removed_count += 1
                                    logger.debug(f"Permanently deleted old clip: {clip_path.name}")
                                except Exception as e:
                                    logger.warning(f"Failed to permanently delete old clip {clip_path}: {e}")
                    
                    if removed_count > 0:
                        logger.info(f"Cleanup completed: Permanently deleted {removed_count} old clips")
                else:
                    logger.info(f"No cleanup needed - within limit ({current_count} <= {self.rolling_clips_count})")
                                    
        except Exception as e:
            logger.error(f"Error cleaning up old clips: {e}")
    
    def get_live_frame(self, camera_id: int) -> Optional[bytes]:
        """
        Get the latest frame from camera for live streaming
        
        Args:
            camera_id: ID of the camera
            
        Returns:
            JPEG encoded frame bytes or None
        """
        try:
            from backend.services.live_streaming import get_live_streaming_service
            streaming_service = get_live_streaming_service()
            frame_bytes = streaming_service.get_latest_frame_bytes(timeout=0.05)
            if frame_bytes:
                return frame_bytes

            return None
                
        except Exception as e:
            logger.debug(f"Error getting live frame from camera {camera_id}: {e}")
            return None
    
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
    
    def get_camera_status(self) -> Dict[str, Any]:
        """
        Get status of all cameras and recording state
        
        Returns:
            Dictionary containing camera system status
        """
        status = {
            "cameras_detected": len(self.cameras),
            "cameras_recording": len(self.recording_threads),
            "rolling_clips_count": len(self.rolling_clips),
            "video_storage_path": str(self.video_path),
            "cameras": []
        }
        
        for camera_id, camera_info in self.cameras.items():
            camera_status = {
                **camera_info,
                "recording": camera_id in self.recording_threads,
                "has_live_stream": self.streaming_integration_enabled and self.shared_frame_buffer is not None
            }
            status["cameras"].append(camera_status)
        
        return status
    
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
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on camera system
        
        Returns:
            Health check results
        """
        try:
            # Check directory access
            storage_accessible = self.video_path.exists() and os.access(self.video_path, os.W_OK)
            
            # Check camera threads
            active_threads = sum(1 for thread in self.recording_threads.values() if thread.is_alive())
            
            # Check disk space
            try:
                disk_usage = shutil.disk_usage(self.video_path)
                free_space_gb = disk_usage.free / (1024**3)
            except:
                free_space_gb = 0
            
            return {
                "healthy": storage_accessible and active_threads == len(self.recording_threads),
                "storage_accessible": storage_accessible,
                "active_recording_threads": active_threads,
                "total_cameras": len(self.cameras),
                "free_disk_space_gb": round(free_space_gb, 2),
                "rolling_clips_count": len(self.rolling_clips)
            }
            
        except Exception as e:
            logger.error(f"Camera health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }
    
    def shutdown(self):
        """Shutdown camera service and cleanup resources"""
        logger.info("Shutting down camera service...")
        
        # Stop all recordings
        camera_ids = list(self.recording_threads.keys())
        for camera_id in camera_ids:
            self.stop_recording(camera_id)
        
        # Shutdown thread pool
        self.executor.shutdown(wait=True)
        
        logger.info("Camera service shutdown complete")


# Global instance
_camera_service = None

def get_camera_service() -> CameraService:
    """Get the global camera service instance"""
    global _camera_service
    if _camera_service is None:
        _camera_service = CameraService()
    return _camera_service
