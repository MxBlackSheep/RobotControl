"""
Data path management for RobotControl executable.
Handles creating and resolving data directories relative to executable location.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class DataPathManager:
    """Manages data directories for RobotControl executable deployment"""
    
    def __init__(self):
        self._base_path: Optional[Path] = None
        self._data_dirs: Dict[str, Path] = {}
        self._initialize_paths()
    
    def _initialize_paths(self):
        """Initialize base path and create data directory structure"""
        # Detect if running as compiled executable
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running as PyInstaller executable
            self._base_path = Path(sys.executable).parent
            logger.info(f"Compiled mode: Using executable directory: {self._base_path}")
        else:
            # Running in development mode
            # Find project root (where main.py would be relative to backend/)
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent  # backend/utils -> backend -> project_root
            self._base_path = project_root
            logger.info(f"Development mode: Using project root: {self._base_path}")
        
        # Define data directory structure
        self._data_dirs = {
            'data': self._base_path / 'data',
            'backups': self._base_path / 'data' / 'backups',
            'videos': self._base_path / 'data' / 'videos',
            'logs': self._base_path / 'data' / 'logs',
            'config': self._base_path / 'data' / 'config',
            'temp': self._base_path / 'data' / 'temp'
        }
        
        # Create directories if they don't exist
        self._create_directories()
    
    def _create_directories(self):
        """Create all required data directories"""
        for dir_name, dir_path in self._data_dirs.items():
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Data directory ready: {dir_name} -> {dir_path}")
            except Exception as e:
                logger.error(f"Failed to create directory {dir_name} at {dir_path}: {e}")
                # Continue with other directories even if one fails
    
    @property
    def base_path(self) -> Path:
        """Get the base path (executable directory or project root)"""
        return self._base_path
    
    @property
    def data_path(self) -> Path:
        """Get the main data directory path"""
        return self._data_dirs['data']
    
    @property
    def backups_path(self) -> Path:
        """Get the backups directory path"""
        return self._data_dirs['backups']
    
    @property
    def videos_path(self) -> Path:
        """Get the videos directory path"""
        return self._data_dirs['videos']
    
    @property
    def logs_path(self) -> Path:
        """Get the logs directory path"""
        return self._data_dirs['logs']
    
    @property
    def config_path(self) -> Path:
        """Get the config directory path"""
        return self._data_dirs['config']
    
    @property
    def temp_path(self) -> Path:
        """Get the temp directory path"""
        return self._data_dirs['temp']
    
    def get_path(self, path_type: str) -> Path:
        """Get a specific data path by type"""
        if path_type not in self._data_dirs:
            raise ValueError(f"Unknown path type: {path_type}. Available: {list(self._data_dirs.keys())}")
        return self._data_dirs[path_type]
    
    def get_backup_file_path(self, filename: str) -> Path:
        """Get full path for a backup file"""
        return self.backups_path / filename
    
    def get_video_file_path(self, filename: str) -> Path:
        """Get full path for a video file"""
        return self.videos_path / filename
    
    def get_log_file_path(self, filename: str) -> Path:
        """Get full path for a log file"""
        return self.logs_path / filename
    
    def get_config_file_path(self, filename: str) -> Path:
        """Get full path for a config file"""
        return self.config_path / filename
    
    def is_compiled_mode(self) -> bool:
        """Check if running in compiled executable mode"""
        return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
    
    def get_directory_info(self) -> Dict[str, str]:
        """Get information about all data directories"""
        return {
            'base_path': str(self._base_path),
            'mode': 'compiled' if self.is_compiled_mode() else 'development',
            'directories': {name: str(path) for name, path in self._data_dirs.items()}
        }

# Global instance for easy access
_path_manager: Optional[DataPathManager] = None

def get_path_manager() -> DataPathManager:
    """Get the global DataPathManager instance"""
    global _path_manager
    if _path_manager is None:
        _path_manager = DataPathManager()
    return _path_manager

# Convenience functions for common operations
def get_data_path() -> Path:
    """Get the main data directory path"""
    return get_path_manager().data_path

def get_backups_path() -> Path:
    """Get the backups directory path"""
    return get_path_manager().backups_path

def get_videos_path() -> Path:
    """Get the videos directory path"""
    return get_path_manager().videos_path

def get_logs_path() -> Path:
    """Get the logs directory path"""
    return get_path_manager().logs_path

def get_config_path() -> Path:
    """Get the config directory path"""
    return get_path_manager().config_path

def get_backup_file_path(filename: str) -> Path:
    """Get full path for a backup file"""
    return get_path_manager().get_backup_file_path(filename)

def is_compiled_mode() -> bool:
    """Check if running in compiled executable mode"""
    return get_path_manager().is_compiled_mode()