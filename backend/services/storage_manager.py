"""
Storage Manager for Automatic Camera Recording

Manages video storage operations including rolling clips cleanup,
experiment folder management, and video archiving. Extracted from
camera service for modular storage management.
"""

import json
import shutil
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from backend.config import AUTO_RECORDING_CONFIG, VIDEO_PATH
from backend.services.clip_transcoder import clip_files, finalized_clips
from dataclasses import dataclass, field


@dataclass
class ArchiveResult:
    success: bool
    archive_path: Optional[str] = None
    clips_archived: int = 0
    archive_size_bytes: int = 0
    error_message: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# Configure logging
logger = logging.getLogger(__name__)


class StorageManager:
    """
    Manages video storage operations for automatic recording system.
    
    Handles:
    - Rolling clips cleanup with configurable limits
    - Experiment folder cleanup and management  
    - Video archiving for completed experiments
    - Thread-safe file operations with proper error handling
    """
    
    def __init__(self):
        """Initialize storage manager with configuration from backend config"""
        
        # Load configuration
        self.rolling_clips_limit = AUTO_RECORDING_CONFIG["rolling_clips_limit"]
        self.experiment_folders_limit = AUTO_RECORDING_CONFIG["experiment_folders_limit"]
        self.archive_duration_minutes = AUTO_RECORDING_CONFIG["archive_duration_minutes"]
        
        # Setup paths with data path manager for portable deployment
        self._setup_storage_paths()
        
        # Thread safety for file operations
        self.storage_lock = threading.Lock()
        self.clips_lock = threading.Lock()
        self.cleanup_rolling_clips()
        
        logger.info(f"StorageManager initialized - Rolling clips limit: {self.rolling_clips_limit}, "
                   f"Experiment folders limit: {self.experiment_folders_limit}")
    
    def _setup_storage_paths(self):
        """Setup storage paths with fallback for different deployment modes"""
        self.video_path = Path(VIDEO_PATH)

        # Define standard subdirectories
        self.rolling_clips_path = self.video_path / "rolling_clips"
        self.experiments_path = self.video_path / "experiments"
        
        # Ensure directories exist
        self._ensure_directories_exist()
    
    def _ensure_directories_exist(self):
        """Ensure all necessary storage directories exist"""
        try:
            self.video_path.mkdir(parents=True, exist_ok=True)
            self.rolling_clips_path.mkdir(parents=True, exist_ok=True)
            self.experiments_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Storage directories verified at: {self.video_path}")
        except Exception as e:
            logger.error(f"Failed to create storage directories: {e}")
            raise
    
    def _read_finalized_clips(self):
        clips = []
        for path in finalized_clips(self.rolling_clips_path):
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

    def cleanup_rolling_clips(self) -> int:
        """Keep the newest finalized clip names under the archive/transcode lock."""
        removed = 0
        try:
            with self.clips_lock:
                clips = finalized_clips(self.rolling_clips_path)
                clips_to_remove = max(0, len(clips) - self.rolling_clips_limit)
                for clip_file in clips[:clips_to_remove]:
                    try:
                        files = clip_files(clip_file)
                        for path in files:
                            path.unlink()
                        clip_file.with_suffix(".json").unlink(missing_ok=True)
                        removed += 1
                    except OSError as exc:
                        error_msg = f"Failed to remove rolling clip {clip_file}: {exc}"
                        logger.warning(error_msg)
        except Exception as exc:
            error_msg = f"Error during rolling clips cleanup: {exc}"
            logger.error(error_msg)
        if removed:
            logger.info("Rolling clips cleanup removed %s clips", removed)
        return removed

    def cleanup_experiment_folders(self, max_folders: Optional[int] = None) -> int:
        """
        Clean up old experiment folders to maintain storage limits
        
        Args:
            max_folders: Maximum folders to keep (uses config default if None)
            
        Returns:
            Number of folders removed
        """
        removed = 0
        
        if max_folders is None:
            max_folders = self.experiment_folders_limit
        
        try:
            with self.storage_lock:
                # Get all experiment folders sorted by creation time (oldest first)
                experiment_folders = []
                if self.experiments_path.exists():
                    for exp_dir in self.experiments_path.iterdir():
                        if exp_dir.is_dir():
                            try:
                                stat = exp_dir.stat()
                                experiment_folders.append((exp_dir, stat.st_ctime))
                            except (OSError, FileNotFoundError) as e:
                                logger.warning(f"Could not stat experiment folder {exp_dir}: {e}")
                
                # Sort by creation time (oldest first) 
                experiment_folders.sort(key=lambda x: x[1])
                
                # Remove excess folders
                folders_to_remove = len(experiment_folders) - max_folders
                if folders_to_remove > 0:
                    logger.info(f"Cleaning up {folders_to_remove} old experiment folders (limit: {max_folders})")
                    
                    for exp_dir, _ in experiment_folders[:folders_to_remove]:
                        try:
                            shutil.rmtree(exp_dir)
                            removed += 1
                            logger.info(f"Removed old experiment folder: {exp_dir.name}")
                        except Exception as e:
                            error_msg = f"Failed to remove experiment folder {exp_dir}: {e}"
                            logger.warning(error_msg)
                
        except Exception as e:
            error_msg = f"Error during experiment folders cleanup: {e}"
            logger.error(error_msg)
        
        if removed:
            logger.info("Experiment folders cleanup removed %s folders", removed)
        return removed

    def archive_experiment_videos(
        self, 
        experiment_id: str, 
        method_name: str, 
    ) -> ArchiveResult:
        """
        Archive the last N minutes of rolling clips for an experiment
        
        Args:
            experiment_id: Unique experiment identifier (RunGUID)
            method_name: Name of the experimental method
            
        Returns:
            ArchiveResult with archiving statistics and outcome
        """
        result = ArchiveResult(success=False)
        
        try:
            # Create experiment archive directory with RunID + method + timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Extract method name from full path and clean it for filesystem
            clean_method_name = method_name.split('\\')[-1].replace('.hsl', '') if '\\' in method_name else method_name
            archive_dir_name = f"{experiment_id}_{clean_method_name}_{timestamp}"
            archive_dir = self.experiments_path / archive_dir_name
            
            logger.info(f"Starting experiment video archive for {experiment_id} -> {archive_dir_name}")
            
            # Calculate cutoff time for archiving (last N minutes)
            cutoff_time = datetime.now() - timedelta(minutes=self.archive_duration_minutes)
            
            # Archive qualifying clips with thread safety
            archived_count = 0
            skipped_count = 0
            total_size = 0
            
            with self.clips_lock:  # Serialize archive selection/copying with retention and transcoding
                clips_to_archive = []
                
                # Collect clips within archive window
                for clip in self._read_finalized_clips():
                    if clip.get("timestamp") and clip["timestamp"] >= cutoff_time and ".partial." not in Path(clip["path"]).name:
                        clips_to_archive.append(clip)
                
                # Sort clips by timestamp for organized archiving
                clips_to_archive.sort(key=lambda x: x.get("timestamp", datetime.min))
                
                logger.info(f"Found {len(clips_to_archive)} clips to archive from last {self.archive_duration_minutes} minutes")
                
                # Copy clips to archive directory
                for clip in clips_to_archive:
                    try:
                        source_path = Path(clip["path"])
                        
                        if not source_path.exists():
                            skipped_count += 1
                            result.warnings.append(f"Source clip not found: {source_path}")
                            continue
                        
                        # Generate archive filename with timestamp prefix for ordering
                        clip_timestamp = clip.get("timestamp", datetime.now())
                        timestamp_prefix = clip_timestamp.strftime("%Y%m%d_%H%M%S")
                        archive_filename = f"{timestamp_prefix}_{source_path.name}"
                        dest_path = archive_dir / archive_filename
                        
                        # Skip if destination already exists
                        if dest_path.exists():
                            skipped_count += 1
                            result.warnings.append(f"Archive file already exists: {archive_filename}")
                            continue
                        
                        # Do not consume retention for a run with no copyable clips.
                        archive_dir.mkdir(parents=True, exist_ok=True)
                        result.archive_path = str(archive_dir)
                        shutil.copy2(source_path, dest_path)
                        
                        # Update statistics
                        archived_count += 1
                        file_size = dest_path.stat().st_size
                        total_size += file_size
                        
                        logger.debug(f"Archived clip: {source_path.name} -> {archive_filename} ({file_size} bytes)")
                        
                    except Exception as e:
                        skipped_count += 1
                        error_msg = f"Failed to archive clip {clip.get('path', 'unknown')}: {e}"
                        logger.warning(error_msg)
                        result.warnings.append(error_msg)
            
            # Update result statistics
            result.success = archived_count > 0
            result.clips_archived = archived_count
            result.archive_size_bytes = total_size
            
            if result.success:
                logger.info(f"Successfully archived {archived_count} clips for experiment {experiment_id} "
                           f"({total_size / (1024*1024):.1f}MB) to {archive_dir_name}")
            else:
                result.error_message = "No clips were successfully archived"
                logger.warning(f"Failed to archive any clips for experiment {experiment_id}")
                
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.error(f"Error archiving experiment videos for {experiment_id}: {e}")
        
        return result
    
# Global instance management
_storage_manager = None
_storage_lock = threading.Lock()


def get_storage_manager() -> StorageManager:
    """Get the global storage manager instance (singleton pattern)"""
    global _storage_manager
    if _storage_manager is None:
        with _storage_lock:
            if _storage_manager is None:
                _storage_manager = StorageManager()
    return _storage_manager