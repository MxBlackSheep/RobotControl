"""
PyRobot Simplified Camera Service

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
from typing import List, Dict, Optional, Any, Generator
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    from backend.config import CAMERA_CONFIG, VIDEO_PATH
except ImportError:
    try:
        from config import CAMERA_CONFIG, VIDEO_PATH
    except ImportError:
        # Fallback for missing config
        CAMERA_CONFIG = {"default_fps": 30, "default_resolution": [640, 480], "max_cameras": 2, "recording_duration_minutes": 1, "archive_duration_minutes": 15, "rolling_clips_count": 120}
        VIDEO_PATH = "data/videos"

# Import types and constants (with fallbacks for modular design)
try:
    from backend.models import CameraRecordingModel
except ImportError:
    try:
        from models import CameraRecordingModel
    except ImportError:
        # Fallback for missing types
        from dataclasses import dataclass
        from datetime import datetime as dt
        from typing import Dict, Any
        
        @dataclass
        class CameraRecordingModel:
            camera_id: int
            filename: str
            timestamp: dt
            duration_seconds: int
            file_size_bytes: int
            recording_type: str

try:
    from backend.constants import CAMERA_STREAM_FPS, VIDEO_CODEC, CAMERA_DETECTION_TIMEOUT
except ImportError:
    try:
        from constants import CAMERA_STREAM_FPS, VIDEO_CODEC, CAMERA_DETECTION_TIMEOUT
    except ImportError:
        # Fallback constants
        CAMERA_STREAM_FPS = 15
        VIDEO_CODEC = 'mp4v'
        CAMERA_DETECTION_TIMEOUT = 5

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
        try:
            try:
                from backend.utils.data_paths import get_videos_path, is_compiled_mode
            except ImportError:  # pragma: no cover - fallback for legacy packaging
                from utils.data_paths import get_videos_path, is_compiled_mode
            if is_compiled_mode():
                self.video_path = get_videos_path()
                logger.info(f"Compiled mode - using local video directory: {self.video_path}")
            else:
                # Ensure we use the project root data directory, not backend subdirectory
                project_root = Path(__file__).parent.parent.parent  # /backend/services/camera.py -> project root
                self.video_path = project_root / "data" / "videos"
                logger.info(f"Development mode - using project root video path: {self.video_path}")
        except ImportError:
            # Fallback - use project root calculation
            project_root = Path(__file__).parent.parent.parent  
            self.video_path = project_root / "data" / "videos"
            logger.info(f"Data path manager not available, using project root fallback: {self.video_path}")
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
        
        # Shared frames for streaming (legacy)
        self.shared_frames: Dict[int, Optional[bytes]] = {}
        self.frame_locks: Dict[int, threading.Lock] = {}
        
        # Integration with new live streaming system
        self.streaming_integration_enabled = False
        self.shared_frame_buffer = None
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        logger.info("CameraService initialized")
    
    def enable_streaming_integration(self):
        """
        Enable integration with the new live streaming system.
        Called during startup to connect with SharedFrameBuffer for live streaming.
        """
        try:
            # Import streaming components
            from backend.services.shared_frame_buffer import get_shared_frame_buffer
            
            self.shared_frame_buffer = get_shared_frame_buffer()
            self.streaming_integration_enabled = True
            
            logger.info("Streaming integration enabled")
            
        except ImportError as e:
            logger.warning(f"Streaming integration not available: {e}")
        except Exception as e:
            logger.error(f"Failed to enable streaming integration: {e}")
    
    def disable_streaming_integration(self):
        """
        Disable streaming integration.
        Called during shutdown or if streaming is disabled.
        """
        self.streaming_integration_enabled = False
        self.shared_frame_buffer = None
        logger.info("Streaming integration disabled")
    
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
                self.frame_locks[camera_id] = threading.Lock()
                self.shared_frames[camera_id] = None

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
                if camera_id in self.frame_locks:
                    del self.frame_locks[camera_id]
                if camera_id in self.shared_frames:
                    del self.shared_frames[camera_id]
                
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
            actual_fps = min(30.0, max(15.0, actual_fps))  # Clamp between 15-30 FPS for stability
            logger.info(f"Camera {camera_id} actual FPS detected: {actual_fps:.1f} (tested {fps_test_frames} frames in {fps_test_duration:.1f}s)")
            
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
                out = cv2.VideoWriter(str(clip_path), fourcc, actual_fps, (640, 480))
                
                if not out.isOpened():
                    logger.error(f"Failed to create video writer for {clip_path}")
                    # Schedule next attempt in 1 second to avoid tight loop
                    next_clip_time = time.time() + 1.0
                    continue
                
                frame_count = 0
                
                # Record for specified duration
                logger.info(f"Starting to record clip: {clip_filename}")
                while time.time() < next_clip_time and not stop_event.is_set():
                    ret, frame = cap.read()
                    
                    if not ret:
                        logger.warning(f"Failed to read frame from camera {camera_id}")
                        time.sleep(0.1)
                        continue
                    
                    # Write frame to file
                    out.write(frame)
                    frame_count += 1
                    
                    # Update shared frame for streaming (legacy system)
                    try:
                        with self.frame_locks[camera_id]:
                            # Encode frame as JPEG for streaming
                            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            self.shared_frames[camera_id] = buffer.tobytes()
                    except Exception as e:
                        logger.debug(f"Error updating shared frame: {e}")
                    
                    # NEW: Send frame to shared buffer for live streaming
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
                    
                    # Precise frame rate control - only sleep if we're ahead of schedule
                    expected_frame_time = clip_start_time + (frame_count / actual_fps)
                    current_time = time.time()
                    if current_time < expected_frame_time:
                        time.sleep(expected_frame_time - current_time)
                
                # Finalize clip immediately (minimize processing delay for next clip)
                actual_duration = time.time() - clip_start_time
                if out:
                    # Force flush any remaining frames to disk
                    try:
                        logger.info(f"Finalizing video clip: {clip_filename} ({frame_count} frames, {actual_duration:.1f}s, {actual_fps:.1f}fps)")
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
            # First check old system for backward compatibility
            if camera_id in self.frame_locks:
                with self.frame_locks[camera_id]:
                    old_frame = self.shared_frames.get(camera_id)
                    if old_frame:
                        return old_frame
            
            # Get frame from new SharedFrameBuffer system
            if self.streaming_integration_enabled and self.shared_frame_buffer:
                latest_frame = self.shared_frame_buffer.get_latest_frame()
                if latest_frame and latest_frame.frame is not None:
                    # Encode frame as JPEG for WebSocket transmission
                    import cv2
                    _, buffer = cv2.imencode('.jpg', latest_frame.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    return buffer.tobytes()
            
            return None
                
        except Exception as e:
            logger.debug(f"Error getting live frame from camera {camera_id}: {e}")
            return None
    
    def archive_experiment_videos(self, experiment_id: int, method_name: str) -> str:
        """
        Archive the last N minutes of video clips for an experiment
        Joins all clips into a single compressed MP4 file
        
        Args:
            experiment_id: ID of the experiment
            method_name: Name of the experimental method
            
        Returns:
            Path to the archive file
        """
        try:
            # Create experiment archive directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Extract just the filename from the full method path for directory name
            clean_method_name = Path(method_name).stem  # Gets filename without extension
            archive_dir = self.experiments_path / f"{clean_method_name}_{timestamp}"
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            # Get clips from the last archive_duration minutes, or all available clips if less than requested
            cutoff_time = datetime.now() - timedelta(seconds=self.archive_duration)
            
            archived_count = 0
            total_clips = len(self.rolling_clips)
            
            with self.clips_lock:
                clips_to_archive = []
                
                # First try to get clips from the last 15 minutes
                for clip in list(self.rolling_clips):
                    if clip["timestamp"] >= cutoff_time:
                        clips_to_archive.append(clip)
                
                # If we have fewer than expected clips (less than 15 minutes worth), get the most recent clips up to the limit
                expected_clips = self.archive_duration // self.recording_duration  # 15 * 60 / 60 = 15 clips
                max_clips_to_archive = 15  # Hard limit to keep file size manageable
                
                if len(clips_to_archive) < expected_clips and total_clips > 0:
                    logger.warning(f"Only {len(clips_to_archive)} clips available from last 15 minutes, getting most recent clips up to {max_clips_to_archive}")
                    # Get the most recent clips, but respect the maximum limit
                    all_clips_by_time = sorted(list(self.rolling_clips), key=lambda x: x["timestamp"], reverse=True)
                    clips_to_archive = all_clips_by_time[:max_clips_to_archive]
                    # Re-sort chronologically for proper video ordering
                    clips_to_archive.sort(key=lambda x: x["timestamp"])
                elif len(clips_to_archive) > max_clips_to_archive:
                    # If we have more than the limit from the time window, take the most recent ones
                    logger.info(f"Found {len(clips_to_archive)} clips in time window, limiting to {max_clips_to_archive} most recent")
                    clips_to_archive.sort(key=lambda x: x["timestamp"], reverse=True)
                    clips_to_archive = clips_to_archive[:max_clips_to_archive]
                    # Re-sort chronologically for proper video ordering
                    clips_to_archive.sort(key=lambda x: x["timestamp"])
                
                # Copy clips to temporary location for processing
                temp_clips = []
                for clip in clips_to_archive:
                    try:
                        source_path = Path(clip["path"])
                        if source_path.exists():
                            temp_path = archive_dir / source_path.name
                            shutil.copy2(source_path, temp_path)
                            temp_clips.append(str(temp_path))
                            archived_count += 1
                            
                    except Exception as e:
                        logger.warning(f"Failed to copy clip {clip['path']}: {e}")
            
            if archived_count == 0:
                logger.warning(f"No clips available to archive for experiment {experiment_id}")
                return str(archive_dir)
            
            # Join and compress clips into single MP4 file
            # Use clean method name for filename (already extracted as clean_method_name)
            output_filename = f"{clean_method_name}_{timestamp}_experiment_{experiment_id}.mp4"
            output_path = archive_dir / output_filename
            
            if self._join_and_compress_videos(temp_clips, str(output_path)):
                # Delete individual AVI clips after successful join
                for clip_path in temp_clips:
                    try:
                        os.remove(clip_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary clip {clip_path}: {e}")
                
                # Get final file size
                if output_path.exists():
                    file_size_mb = output_path.stat().st_size / (1024 * 1024)
                    logger.info(f"Created compressed archive: {output_filename} ({file_size_mb:.1f} MB)")
                    logger.info(f"Archived {archived_count} clips for experiment {experiment_id} into {output_path}")
                    return str(output_path)
            else:
                logger.warning(f"Failed to join videos, keeping individual clips in {archive_dir}")
                return str(archive_dir)
            
        except Exception as e:
            logger.error(f"Failed to archive experiment videos: {e}")
            return ""
    
    def _join_and_compress_videos(self, input_files: List[str], output_path: str) -> bool:
        """
        Join multiple video files into a single compressed MP4 using OpenCV
        
        Args:
            input_files: List of input video file paths
            output_path: Output MP4 file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not input_files:
                logger.warning("No input files to join")
                return False
            
            logger.info(f"Joining {len(input_files)} videos using OpenCV...")
            
            # Sort files to maintain chronological order
            sorted_files = sorted(input_files)
            
            # Read first video to get properties
            first_cap = cv2.VideoCapture(sorted_files[0])
            if not first_cap.isOpened():
                logger.error(f"Failed to open first video: {sorted_files[0]}")
                return False
            
            # Get video properties from first clip
            original_fps = first_cap.get(cv2.CAP_PROP_FPS)
            original_width = int(first_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(first_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            first_cap.release()
            
            # Apply compression settings to reduce file size to under 100MB
            # Strategy: Skip every other frame and reduce output FPS accordingly
            # This maintains proper timing while reducing file size by ~50%
            
            frame_skip_ratio = 2  # Skip every other frame
            fps = (original_fps / frame_skip_ratio) if original_fps > 0 else (26.7 / frame_skip_ratio)
            
            # Optionally reduce resolution if very large (keep reasonable quality)  
            if original_width > 640 or original_height > 480:
                # Scale down maintaining aspect ratio
                aspect_ratio = original_width / original_height
                if aspect_ratio > 1:  # Landscape
                    width = min(640, original_width)
                    height = int(width / aspect_ratio)
                else:  # Portrait or square
                    height = min(480, original_height)
                    width = int(height * aspect_ratio)
                logger.info(f"Scaling video from {original_width}x{original_height} to {width}x{height} for compression")
            else:
                width = original_width
                height = original_height
            
            logger.info(f"Compression settings: {width}x{height} @ {fps:.1f}fps (skip ratio: {frame_skip_ratio}, original: {original_fps:.1f}fps)")
            
            # Use H.264 codec if available, otherwise fall back to XVID
            # Try multiple codec options for better compatibility
            codecs_to_try = [
                ('mp4v', 'MP4V'),  # MPEG-4 codec (widely supported)
                ('XVID', 'XVID'),  # Xvid codec (good compression)
                ('MJPG', 'MJPG'),  # Motion JPEG (larger but reliable)
            ]
            
            out = None
            used_codec = None
            
            # Try different codecs until one works
            for codec_name, fourcc_str in codecs_to_try:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                    # For MP4 format, ensure output path has .mp4 extension
                    if not output_path.endswith('.mp4'):
                        output_path = output_path.rsplit('.', 1)[0] + '.mp4'
                    
                    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                    if out.isOpened():
                        used_codec = codec_name
                        logger.info(f"Using {codec_name} codec for compression")
                        break
                    else:
                        out.release()
                        out = None
                except Exception as e:
                    logger.debug(f"Codec {codec_name} not available: {e}")
                    if out:
                        out.release()
                        out = None
            
            if not out or not out.isOpened():
                logger.error("Failed to create video writer with any available codec")
                return False
            
            try:
                total_frames = 0
                
                # Process each input video
                for i, input_file in enumerate(sorted_files):
                    logger.info(f"Processing clip {i+1}/{len(sorted_files)}: {Path(input_file).name}")
                    
                    cap = cv2.VideoCapture(input_file)
                    if not cap.isOpened():
                        logger.warning(f"Failed to open video: {input_file}")
                        continue
                    
                    # Use the global frame skip ratio for compression
                    # This was set earlier based on target compression
                    
                    frame_count = 0
                    frames_written = 0
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        
                        # Skip frames to reduce file size (every other frame)
                        if frame_count % frame_skip_ratio == 0:
                            # Resize frame if needed for compression
                            if frame.shape[1] != width or frame.shape[0] != height:
                                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                            
                            out.write(frame)
                            frames_written += 1
                            total_frames += 1
                        
                        frame_count += 1
                    
                    cap.release()
                    logger.debug(f"Processed clip {i+1}: {frame_count} frames read, {frames_written} frames written (skip ratio: {frame_skip_ratio})")
                
                # Release the output video
                out.release()
                
                # Verify output file was created
                output_path_obj = Path(output_path)
                if output_path_obj.exists() and output_path_obj.stat().st_size > 0:
                    # Calculate compression statistics
                    original_size = sum(Path(f).stat().st_size for f in sorted_files if Path(f).exists())
                    compressed_size = output_path_obj.stat().st_size
                    compression_ratio = (1 - compressed_size/original_size) * 100 if original_size > 0 else 0
                    
                    logger.info(f"Successfully joined {len(sorted_files)} videos into {output_path}")
                    logger.info(f"Total frames: {total_frames}, Codec: {used_codec}")
                    logger.info(f"Original size: {original_size/(1024*1024):.1f} MB")
                    logger.info(f"Compressed size: {compressed_size/(1024*1024):.1f} MB")
                    logger.info(f"Compression ratio: {compression_ratio:.1f}% reduction")
                    
                    return True
                else:
                    logger.error("Output file was not created or is empty")
                    return False
                    
            finally:
                if out:
                    out.release()
                    
        except Exception as e:
            logger.error(f"Error joining videos with OpenCV: {e}")
            # Try simpler approach: just copy files without compression
            try:
                logger.info("Falling back to simple concatenation without compression")
                # At least keep them organized in the archive directory
                return False  # Signal that compression failed but files are preserved
            except:
                return False
    
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
                "has_live_stream": camera_id in self.shared_frames
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