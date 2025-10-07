"""
Portable path resolution for single-exe deployment.
Handles relative paths, read-only media, and temp directory fallbacks.
"""

import os
import sys
import tempfile
import logging
from pathlib import Path
from typing import Optional, Union
import shutil

logger = logging.getLogger(__name__)

class PathResolver:
    """Resolves paths for portable executable deployment."""
    
    def __init__(self):
        self._exe_dir = self._get_executable_directory()
        self._is_portable = self._detect_portable_mode()
        self._temp_fallback = None
        
        logger.info(f"PathResolver initialized: exe_dir={self._exe_dir}, portable={self._is_portable}")
    
    def _get_executable_directory(self) -> Path:
        """Get the directory containing the executable."""
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller bundle
                return Path(sys.executable).parent
            else:
                # Nuitka or other
                return Path(sys.executable).parent
        else:
            # Running as script - use project root
            return Path(__file__).parent.parent.parent
    
    def _detect_portable_mode(self) -> bool:
        """Detect if running in portable mode (e.g., from USB drive)."""
        try:
            # Try to create a test file in the exe directory
            test_file = self._exe_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            return False  # Can write, not read-only
        except (PermissionError, OSError):
            logger.info("Read-only media detected - enabling portable mode")
            return True
    
    def get_data_directory(self, create: bool = True) -> Path:
        """
        Get the data directory for the application.
        
        Args:
            create: Whether to create the directory if it doesn't exist
            
        Returns:
            Path to data directory
        """
        if self._is_portable:
            # Use temp directory for portable mode
            if self._temp_fallback is None:
                self._temp_fallback = Path(tempfile.gettempdir()) / "PyRobot_Portable"
            data_dir = self._temp_fallback / "data"
        else:
            # Use relative to executable
            data_dir = self._exe_dir / "data"
        
        if create and not data_dir.exists():
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created data directory: {data_dir}")
            except Exception as e:
                logger.error(f"Failed to create data directory {data_dir}: {e}")
                # Fallback to temp
                data_dir = Path(tempfile.gettempdir()) / "PyRobot_Data"
                data_dir.mkdir(parents=True, exist_ok=True)
                logger.warning(f"Using fallback data directory: {data_dir}")
        
        return data_dir
    
    def get_logs_directory(self, create: bool = True) -> Path:
        """
        Get the logs directory for the application.
        
        Args:
            create: Whether to create the directory if it doesn't exist
            
        Returns:
            Path to logs directory
        """
        if self._is_portable:
            # Use temp directory for portable mode
            if self._temp_fallback is None:
                self._temp_fallback = Path(tempfile.gettempdir()) / "PyRobot_Portable"
            logs_dir = self._temp_fallback / "logs"
        else:
            # Use relative to executable
            logs_dir = self._exe_dir / "logs"
        
        if create and not logs_dir.exists():
            try:
                logs_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created logs directory: {logs_dir}")
            except Exception as e:
                logger.error(f"Failed to create logs directory {logs_dir}: {e}")
                # Fallback to temp
                logs_dir = Path(tempfile.gettempdir()) / "PyRobot_Logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                logger.warning(f"Using fallback logs directory: {logs_dir}")
        
        return logs_dir
    
    def get_config_directory(self, create: bool = True) -> Path:
        """
        Get the config directory for the application.
        
        Args:
            create: Whether to create the directory if it doesn't exist
            
        Returns:
            Path to config directory
        """
        if self._is_portable:
            # Try to use exe directory first, fallback to temp
            config_dir = self._exe_dir / "config"
            if not self._can_write_to_path(config_dir.parent):
                if self._temp_fallback is None:
                    self._temp_fallback = Path(tempfile.gettempdir()) / "PyRobot_Portable"
                config_dir = self._temp_fallback / "config"
        else:
            # Use relative to executable
            config_dir = self._exe_dir / "config"
        
        if create and not config_dir.exists():
            try:
                config_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created config directory: {config_dir}")
            except Exception as e:
                logger.error(f"Failed to create config directory {config_dir}: {e}")
                # Fallback to temp
                config_dir = Path(tempfile.gettempdir()) / "PyRobot_Config"
                config_dir.mkdir(parents=True, exist_ok=True)
                logger.warning(f"Using fallback config directory: {config_dir}")
        
        return config_dir
    
    def _can_write_to_path(self, path: Path) -> bool:
        """Check if we can write to a path."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            return True
        except (PermissionError, OSError):
            return False
    
    def resolve_path(self, path: Union[str, Path], path_type: str = "data") -> Path:
        """
        Resolve a path relative to the appropriate base directory.
        
        Args:
            path: Path to resolve (can be relative or absolute)
            path_type: Type of path ("data", "logs", "config")
            
        Returns:
            Resolved absolute path
        """
        path = Path(path)
        
        if path.is_absolute():
            return path
        
        # Get base directory based on type
        if path_type == "data":
            base_dir = self.get_data_directory()
        elif path_type == "logs":
            base_dir = self.get_logs_directory()
        elif path_type == "config":
            base_dir = self.get_config_directory()
        else:
            # Default to exe directory
            base_dir = self._exe_dir
        
        return base_dir / path
    
    def ensure_path_writable(self, path: Path) -> Path:
        """
        Ensure a path is writable, creating fallback if necessary.
        
        Args:
            path: Path to check/ensure
            
        Returns:
            Writable path (may be different from input if fallback was used)
        """
        try:
            # Try to create parent directories
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            if path.exists():
                # Test by trying to append
                if path.is_file():
                    with open(path, 'a') as f:
                        pass
                return path
            else:
                # Test by creating then removing
                if path.suffix:
                    # It's a file
                    path.write_text("test")
                    path.unlink()
                else:
                    # It's a directory
                    path.mkdir(exist_ok=True)
                return path
        except (PermissionError, OSError) as e:
            logger.warning(f"Path {path} not writable: {e}")
            
            # Create fallback in temp directory
            fallback_path = Path(tempfile.gettempdir()) / "PyRobot_Fallback" / path.name
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Using fallback path: {fallback_path}")
            return fallback_path
    
    def cleanup_temp_directories(self):
        """Clean up temporary directories created during portable execution."""
        if self._temp_fallback and self._temp_fallback.exists():
            try:
                # Only clean up if it's in temp directory
                if str(self._temp_fallback).startswith(tempfile.gettempdir()):
                    shutil.rmtree(self._temp_fallback)
                    logger.info(f"Cleaned up temporary directory: {self._temp_fallback}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {e}")
    
    @property
    def exe_directory(self) -> Path:
        """Get the executable directory."""
        return self._exe_dir
    
    @property
    def is_portable(self) -> bool:
        """Check if running in portable mode."""
        return self._is_portable
    
    def get_status(self) -> dict:
        """Get resolver status information."""
        return {
            "exe_directory": str(self._exe_dir),
            "is_portable": self._is_portable,
            "temp_fallback": str(self._temp_fallback) if self._temp_fallback else None,
            "data_directory": str(self.get_data_directory(create=False)),
            "logs_directory": str(self.get_logs_directory(create=False)),
            "config_directory": str(self.get_config_directory(create=False))
        }

# Global instance
_path_resolver: Optional[PathResolver] = None

def get_path_resolver() -> PathResolver:
    """Get or create the global path resolver instance."""
    global _path_resolver
    if _path_resolver is None:
        _path_resolver = PathResolver()
    return _path_resolver

def resolve_data_path(path: Union[str, Path]) -> Path:
    """Convenience function to resolve a data path."""
    return get_path_resolver().resolve_path(path, "data")

def resolve_logs_path(path: Union[str, Path]) -> Path:
    """Convenience function to resolve a logs path."""
    return get_path_resolver().resolve_path(path, "logs")

def resolve_config_path(path: Union[str, Path]) -> Path:
    """Convenience function to resolve a config path."""
    return get_path_resolver().resolve_path(path, "config")