"""
Data path management for RobotControl executable.
Handles creating and resolving data directories relative to executable location.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class DataPathManager:
    """Manages data directories for RobotControl executable deployment"""
    
    def __init__(self):
        self.base_path: Optional[Path] = None
        self._data_dirs: Dict[str, Path] = {}
        self._initialize_paths()
    
    def _initialize_paths(self):
        """Initialize base path and create data directory structure"""
        # Detect if running as compiled executable
        if is_compiled_mode():
            # Running as PyInstaller executable
            self.base_path = Path(sys.executable).parent
            logger.info(f"Compiled mode: Using executable directory: {self.base_path}")
        else:
            # Running in development mode
            # Find project root (where main.py would be relative to backend/)
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent  # backend/utils -> backend -> project_root
            self.base_path = project_root
            logger.info(f"Development mode: Using project root: {self.base_path}")
        
        # Define data directory structure
        self._data_dirs = {
            'data': self.base_path / 'data',
            'backups': self.base_path / 'data' / 'backups',
            'videos': self.base_path / 'data' / 'videos',
            'logs': self.base_path / 'data' / 'logs',
            'config': self.base_path / 'data' / 'config',
            'temp': self.base_path / 'data' / 'temp'
        }
        
        for name, path in self._data_dirs.items():
            setattr(self, f"{name}_path", path)

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


def is_compiled_mode() -> bool:
    """Check if running in compiled executable mode"""
    return bool(getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'))
