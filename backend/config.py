"""
Simplified Configuration Management for PyRobot Backend
"""

import os
import sys
from typing import Dict, Any
from pathlib import Path

try:
    from backend.utils.data_paths import get_path_manager
except ImportError:
    try:
        from utils.data_paths import get_path_manager  # type: ignore
    except ImportError:
        get_path_manager = None


# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")
except ImportError:
    print("python-dotenv not available, using system environment variables only")

class Settings:
    """Simplified settings configuration"""
    
    # Server settings
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # Database configuration - easily configurable via environment variables
    # Development VM SQL Server
    VM_SQL_SERVER: str = os.getenv("VM_SQL_SERVER", "192.168.3.21,50131")
    VM_SQL_USER: str = os.getenv("VM_SQL_USER", "Hamilton") 
    VM_SQL_PASSWORD: str = os.getenv("VM_SQL_PASSWORD", "mkdpw:V43")
    
    # Backup paths
    # LOCAL_BACKUP_PATH: Used by backup service on the host for file ops.
    # Default to project-relative "data/backups" so installs work out of the box.
    # Override via .env when using a network share.
    LOCAL_BACKUP_PATH: str = os.getenv("LOCAL_BACKUP_PATH", "data/backups")
    # SQL_BACKUP_PATH: Path SQL Server (on the VM) writes .bak files to.
    # Keep default aligned with LOCAL_BACKUP_PATH so host/SQL share the same folder.
    SQL_BACKUP_PATH: str = os.getenv("SQL_BACKUP_PATH", "data/backups")
    
    DB_CONFIG_PRIMARY = {
        "driver": "{ODBC Driver 11 for SQL Server}",
        "server": "LOCALHOST\\HAMILTON",
        "database": "EvoYeast",
        "user": "Hamilton",
        "password": "mkdpw:V43",
        "trust_connection": "no",
        "timeout": 5
    }
    
    DB_CONFIG_SECONDARY = {
        "driver": "{ODBC Driver 11 for SQL Server}",
        "server": VM_SQL_SERVER,
        "database": "EvoYeast", 
        "user": VM_SQL_USER,
        "password": VM_SQL_PASSWORD,
        "trust_connection": "no",
        "encrypt": "no",
        "trust_server_certificate": "yes",
        "timeout": 5
    }
    
    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "pyrobot-simplified-secret-key-2025")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # File paths
    _path_manager = get_path_manager() if 'get_path_manager' in globals() and callable(get_path_manager) else None
    if _path_manager:
        PROJECT_ROOT: Path = _path_manager.base_path
        DATA_PATH: Path = _path_manager.data_path
        VIDEO_PATH: Path = _path_manager.videos_path
        BACKUP_PATH: Path = _path_manager.backups_path
    else:
        PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
        DATA_PATH: Path = PROJECT_ROOT / "data"
        VIDEO_PATH: Path = DATA_PATH / "videos"
        BACKUP_PATH: Path = DATA_PATH / "backups"

# Camera system configuration
CAMERA_CONFIG = {
    "max_cameras": 2,                       # Maximum number of cameras to detect
    "recording_duration_minutes": 1,        # Duration of each video segment in minutes
    "archive_duration_minutes": 15,         # Minutes of clips to archive per experiment
    "rolling_clips_count": 120,             # Maximum rolling clips to maintain
    "default_fps": 30,                      # Default camera frame rate
    "default_resolution": [640, 480]        # Default camera resolution [width, height]
}

# Automatic recording configuration
AUTO_RECORDING_CONFIG = {
    "enabled": True,                        # Enable automatic recording on startup
    "startup_delay_seconds": 20,            # Delay before starting recording
    "primary_camera_id": 0,                 # Default camera to use for automatic recording
    "rolling_clips_limit": 120,             # Maximum rolling clips to maintain (mirrors CAMERA_CONFIG)
    "experiment_folders_limit": 20,         # Maximum experiment folders to keep
    "archive_duration_minutes": 15,         # Minutes of clips to archive per experiment (mirrors CAMERA_CONFIG)
    "experiment_check_interval_seconds": 5,   # Seconds between experiment state checks (reduced to catch short experiments)
    "storage_cleanup_interval_seconds": 300,   # Seconds between storage cleanup cycles
    "cleanup_interval_minutes": 30,         # Minutes between periodic cleanup checks
    "cleanup_threshold_buffer": 10          # Buffer above rolling_clips_limit before triggering cleanup
}

# Live streaming configuration
LIVE_STREAMING_CONFIG = {
    "enabled": True,                           # Enable live streaming functionality
    "max_concurrent_sessions": 10,             # Maximum concurrent streaming sessions
    "session_timeout_seconds": 60,             # Session timeout after inactivity
    "default_quality": "adaptive",             # Default streaming quality mode
    "max_bandwidth_per_session_mbps": 2.0,     # Max bandwidth per streaming session
    "total_bandwidth_limit_mbps": 15.0,        # Total bandwidth limit for all streams
    "frame_buffer_size": 30,                   # Frame buffer size (~1 second at 30fps)
    "cpu_soft_limit_percent": int(os.getenv("STREAMING_CPU_SOFT_LIMIT", "75")),  # CPU% to start degrading streams
    "cpu_hard_limit_percent": int(os.getenv("STREAMING_CPU_HARD_LIMIT", "90")),  # CPU% to stop streaming sessions
    "quality_levels": {
        "high": {
            "fps": 30,
            "resolution_scale": 1.0,
            "jpeg_quality": 85,
            "max_bitrate_kbps": 2000
        },
        "medium": {
            "fps": 15,
            "resolution_scale": 0.75,
            "jpeg_quality": 75,
            "max_bitrate_kbps": 1000
        },
        "low": {
            "fps": 10,
            "resolution_scale": 0.5,
            "jpeg_quality": 60,
            "max_bitrate_kbps": 500
        },
        "adaptive": {
            "fps": 15,                         # Starting fps for adaptive mode
            "resolution_scale": 0.75,          # Starting resolution for adaptive
            "jpeg_quality": 75,                # Starting quality for adaptive
            "max_bitrate_kbps": 1000          # Starting bitrate for adaptive
        }
    },
    "websocket": {
        "ping_interval": 20,                   # WebSocket ping interval in seconds
        "ping_timeout": 10,                    # WebSocket ping timeout in seconds
        "max_message_size": 10485760,          # Max WebSocket message size (10MB)
        "compression": "deflate"               # WebSocket compression method
    }
}

# Global settings instance
settings = Settings()

# Export VIDEO_PATH for compatibility with existing camera service
VIDEO_PATH = str(settings.VIDEO_PATH)
