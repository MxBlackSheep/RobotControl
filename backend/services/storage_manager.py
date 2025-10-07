"""
Storage Manager for Automatic Camera Recording

Manages video storage operations including rolling clips cleanup,
experiment folder management, and video archiving. Extracted from
camera service for modular storage management.
"""

import os
import shutil
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import deque
import time

from backend.config import AUTO_RECORDING_CONFIG, CAMERA_CONFIG, VIDEO_PATH
from backend.services.automatic_recording_types import (
    ArchiveResult, StorageCleanupResult
)

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
        
        logger.info(f"StorageManager initialized - Rolling clips limit: {self.rolling_clips_limit}, "
                   f"Experiment folders limit: {self.experiment_folders_limit}")
    
    def _setup_storage_paths(self):
        """Setup storage paths with fallback for different deployment modes"""
        try:
            from backend.utils.data_paths import get_videos_path, is_compiled_mode
            if is_compiled_mode():
                self.video_path = get_videos_path()
                logger.info(f"Compiled mode - using local video directory: {self.video_path}")
            else:
                self.video_path = Path(VIDEO_PATH)
                logger.info(f"Development mode - using configured video path: {self.video_path}")
        except ImportError:
            self.video_path = Path(VIDEO_PATH)
            logger.warning(f"Data path manager not available, using fallback: {self.video_path}")
        
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
    
    def cleanup_rolling_clips(self, max_clips: Optional[int] = None) -> StorageCleanupResult:
        """
        Clean up old rolling clips to maintain storage limits
        
        Args:
            max_clips: Maximum clips to keep (uses config default if None)
            
        Returns:
            StorageCleanupResult with cleanup statistics and any errors
        """
        cleanup_start = time.time()
        result = StorageCleanupResult()
        
        if max_clips is None:
            max_clips = self.rolling_clips_limit
        
        try:
            with self.storage_lock:
                # Get all rolling clips sorted by modification time (oldest first)
                clips = []
                if self.rolling_clips_path.exists():
                    # Look for both mp4 and avi files (camera can create either format)
                    for pattern in ["*.mp4", "*.avi"]:
                        for clip_file in self.rolling_clips_path.glob(pattern):
                            if clip_file.is_file():
                                try:
                                    stat = clip_file.stat()
                                    clips.append((clip_file, stat.st_mtime, stat.st_size))
                                except (OSError, FileNotFoundError) as e:
                                    logger.warning(f"Could not stat rolling clip {clip_file}: {e}")
                
                # Sort by modification time (oldest first)
                clips.sort(key=lambda x: x[1])
                
                # Remove excess clips
                clips_to_remove = len(clips) - max_clips
                if clips_to_remove > 0:
                    logger.info(f"Cleaning up {clips_to_remove} old rolling clips (limit: {max_clips})")
                    
                    for clip_file, _, size_bytes in clips[:clips_to_remove]:
                        try:
                            clip_file.unlink()
                            result.rolling_clips_removed += 1
                            result.storage_freed_bytes += size_bytes
                            logger.debug(f"Removed old rolling clip: {clip_file.name}")
                        except Exception as e:
                            error_msg = f"Failed to remove rolling clip {clip_file}: {e}"
                            logger.warning(error_msg)
                            result.rolling_clips_errors.append(error_msg)
                
        except Exception as e:
            error_msg = f"Error during rolling clips cleanup: {e}"
            logger.error(error_msg)
            result.rolling_clips_errors.append(error_msg)
        
        result.cleanup_duration_seconds = time.time() - cleanup_start
        logger.info(f"Rolling clips cleanup completed - Removed: {result.rolling_clips_removed}, "
                   f"Freed: {result.storage_freed_bytes / (1024*1024):.1f}MB")
        
        return result
    
    def cleanup_experiment_folders(self, max_folders: Optional[int] = None) -> StorageCleanupResult:
        """
        Clean up old experiment folders to maintain storage limits
        
        Args:
            max_folders: Maximum folders to keep (uses config default if None)
            
        Returns:
            StorageCleanupResult with cleanup statistics and any errors
        """
        cleanup_start = time.time()
        result = StorageCleanupResult()
        
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
                                # Calculate folder size
                                folder_size = sum(
                                    f.stat().st_size 
                                    for f in exp_dir.rglob('*') 
                                    if f.is_file()
                                )
                                experiment_folders.append((exp_dir, stat.st_ctime, folder_size))
                            except (OSError, FileNotFoundError) as e:
                                logger.warning(f"Could not stat experiment folder {exp_dir}: {e}")
                
                # Sort by creation time (oldest first) 
                experiment_folders.sort(key=lambda x: x[1])
                
                # Remove excess folders
                folders_to_remove = len(experiment_folders) - max_folders
                if folders_to_remove > 0:
                    logger.info(f"Cleaning up {folders_to_remove} old experiment folders (limit: {max_folders})")
                    
                    for exp_dir, _, folder_size in experiment_folders[:folders_to_remove]:
                        try:
                            shutil.rmtree(exp_dir)
                            result.experiment_folders_removed += 1
                            result.storage_freed_bytes += folder_size
                            logger.info(f"Removed old experiment folder: {exp_dir.name}")
                        except Exception as e:
                            error_msg = f"Failed to remove experiment folder {exp_dir}: {e}"
                            logger.warning(error_msg)
                            result.experiment_folders_errors.append(error_msg)
                
        except Exception as e:
            error_msg = f"Error during experiment folders cleanup: {e}"
            logger.error(error_msg)
            result.experiment_folders_errors.append(error_msg)
        
        result.cleanup_duration_seconds = time.time() - cleanup_start
        logger.info(f"Experiment folders cleanup completed - Removed: {result.experiment_folders_removed}, "
                   f"Freed: {result.storage_freed_bytes / (1024*1024):.1f}MB")
        
        return result
    
    def archive_experiment_videos(
        self, 
        experiment_id: str, 
        method_name: str, 
        rolling_clips: deque,
        clips_lock: threading.Lock
    ) -> ArchiveResult:
        """
        Archive the last N minutes of rolling clips for an experiment
        
        Args:
            experiment_id: Unique experiment identifier (RunGUID)
            method_name: Name of the experimental method
            rolling_clips: Deque of rolling clips from camera service
            clips_lock: Thread lock for accessing rolling clips
            
        Returns:
            ArchiveResult with archiving statistics and outcome
        """
        archive_start_time = datetime.now()
        result = ArchiveResult(success=False, archive_start_time=archive_start_time)
        
        try:
            # Create experiment archive directory with RunID + method + timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Extract method name from full path and clean it for filesystem
            clean_method_name = method_name.split('\\')[-1].replace('.hsl', '') if '\\' in method_name else method_name
            archive_dir_name = f"{experiment_id}_{clean_method_name}_{timestamp}"
            archive_dir = self.experiments_path / archive_dir_name
            
            logger.info(f"Starting experiment video archive for {experiment_id} -> {archive_dir_name}")
            
            # Create archive directory
            archive_dir.mkdir(parents=True, exist_ok=True)
            result.archive_path = str(archive_dir)
            
            # Calculate cutoff time for archiving (last N minutes)
            cutoff_time = datetime.now() - timedelta(minutes=self.archive_duration_minutes)
            
            # Archive qualifying clips with thread safety
            archived_count = 0
            skipped_count = 0
            total_size = 0
            
            with clips_lock:  # Use camera service's clips lock for thread safety
                clips_to_archive = []
                
                # Collect clips within archive window
                for clip in list(rolling_clips):
                    if clip.get("timestamp") and clip["timestamp"] >= cutoff_time:
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
                        
                        # Copy file with metadata preservation
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
            result.clips_skipped = skipped_count
            result.archive_size_bytes = total_size
            result.archive_duration_seconds = (datetime.now() - archive_start_time).total_seconds()
            
            if result.success:
                logger.info(f"Successfully archived {archived_count} clips for experiment {experiment_id} "
                           f"({total_size / (1024*1024):.1f}MB) to {archive_dir_name}")
            else:
                result.error_message = "No clips were successfully archived"
                logger.warning(f"Failed to archive any clips for experiment {experiment_id}")
                
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            result.archive_duration_seconds = (datetime.now() - archive_start_time).total_seconds()
            logger.error(f"Error archiving experiment videos for {experiment_id}: {e}")
        
        return result
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive storage statistics
        
        Returns:
            Dictionary with storage information and statistics
        """
        stats = {
            "video_path": str(self.video_path),
            "rolling_clips_path": str(self.rolling_clips_path),
            "experiments_path": str(self.experiments_path),
            "rolling_clips_count": 0,
            "experiment_folders_count": 0,
            "total_storage_bytes": 0,
            "rolling_clips_size_bytes": 0,
            "experiments_size_bytes": 0
        }
        
        try:
            # Count rolling clips and calculate size
            if self.rolling_clips_path.exists():
                rolling_clips = []
                # Look for both mp4 and avi files (camera can create either format)
                for pattern in ["*.mp4", "*.avi"]:
                    rolling_clips.extend(list(self.rolling_clips_path.glob(pattern)))
                stats["rolling_clips_count"] = len(rolling_clips)
                stats["rolling_clips_size_bytes"] = sum(
                    f.stat().st_size for f in rolling_clips if f.is_file()
                )
            
            # Count experiment folders and calculate size
            if self.experiments_path.exists():
                experiment_folders = [d for d in self.experiments_path.iterdir() if d.is_dir()]
                stats["experiment_folders_count"] = len(experiment_folders)
                
                experiments_size = 0
                for exp_dir in experiment_folders:
                    try:
                        experiments_size += sum(
                            f.stat().st_size 
                            for f in exp_dir.rglob('*') 
                            if f.is_file()
                        )
                    except Exception as e:
                        logger.debug(f"Could not calculate size for {exp_dir}: {e}")
                
                stats["experiments_size_bytes"] = experiments_size
            
            # Calculate total storage
            stats["total_storage_bytes"] = (
                stats["rolling_clips_size_bytes"] + 
                stats["experiments_size_bytes"]
            )
            
            # Add human-readable sizes
            stats["rolling_clips_size_mb"] = round(stats["rolling_clips_size_bytes"] / (1024*1024), 1)
            stats["experiments_size_mb"] = round(stats["experiments_size_bytes"] / (1024*1024), 1)
            stats["total_storage_mb"] = round(stats["total_storage_bytes"] / (1024*1024), 1)
            
        except Exception as e:
            logger.error(f"Error calculating storage statistics: {e}")
            stats["error"] = str(e)
        
        return stats
    
    def cleanup_all_storage(self) -> StorageCleanupResult:
        """
        Perform complete storage cleanup (rolling clips + experiment folders)
        
        Returns:
            Combined StorageCleanupResult from all cleanup operations
        """
        logger.info("Starting complete storage cleanup")
        cleanup_start = time.time()
        
        # Cleanup rolling clips
        rolling_result = self.cleanup_rolling_clips()
        
        # Cleanup experiment folders
        folders_result = self.cleanup_experiment_folders()
        
        # Combine results
        combined_result = StorageCleanupResult()
        combined_result.rolling_clips_removed = rolling_result.rolling_clips_removed
        combined_result.rolling_clips_errors = rolling_result.rolling_clips_errors
        combined_result.experiment_folders_removed = folders_result.experiment_folders_removed
        combined_result.experiment_folders_errors = folders_result.experiment_folders_errors
        combined_result.storage_freed_bytes = (
            rolling_result.storage_freed_bytes + folders_result.storage_freed_bytes
        )
        combined_result.cleanup_duration_seconds = time.time() - cleanup_start
        
        logger.info(f"Complete storage cleanup finished - Total items removed: {combined_result.total_items_removed}, "
                   f"Storage freed: {combined_result.storage_freed_bytes / (1024*1024):.1f}MB")
        
        return combined_result


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