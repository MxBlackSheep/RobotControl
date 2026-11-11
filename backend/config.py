"""
Simplified Configuration Management for RobotControl Backend
"""

import os
from pathlib import Path

from backend.utils.data_paths import get_path_manager


from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name(".env"))

class Settings:
    """Simplified settings configuration"""
    
    # Database configuration - easily configurable via environment variables
    # Development VM SQL Server
    VM_SQL_SERVER: str = os.getenv("VM_SQL_SERVER", "192.168.3.21,50131")
    VM_SQL_USER: str = os.getenv("VM_SQL_USER", "Hamilton") 
    VM_SQL_PASSWORD: str = os.getenv("VM_SQL_PASSWORD", "mkdpw:V43")
    
    # Backup folder, relative to the app root unless absolute. SQL Server writes
    # the .bak to this same path, so it must be reachable under this name by both.
    LOCAL_BACKUP_PATH: str = os.getenv("LOCAL_BACKUP_PATH", "data/backups")
    
    DB_CONFIG_PRIMARY = {
        "driver": "{ODBC Driver 11 for SQL Server}",
        "server": "LOCALHOST\\HAMILTON",
        "database": "EvoYeast",
        "user": "Hamilton",
        "password": "mkdpw:V43",
        "trust_connection": "no",
        "timeout": 5
    }
    
    # File paths
    _path_manager = get_path_manager()
    VIDEO_PATH: Path = _path_manager.videos_path

# Camera system configuration
CAMERA_CONFIG = {
    "no_frame_seconds": 10,
    "startup_seconds": 20,
    "recording_duration_minutes": 1,        # Duration of each video segment in minutes
    # Frame rate requested from the camera; a hint only (live view paces itself to at most 15, recording
    # measures its rate and keeps at most 7.5). The production camera delivers YUY2 at 30 whatever is
    # requested, so 30 matches what arrives (docs/plans/live-view-denoise.md). LIVE_STREAMING_CONFIG
    # encoder_levels rates should divide it.
    "capture_fps": 30,
    "clip_h264_kbps": 1000,                 # H.264 bitrate finalized clips are stored at (docs/plans/h264-rolling-clips.md)
    # Temporal denoise in the clip conversion (ffmpeg filter, one thread): each pixel is averaged over
    # up to 7 frames, stopping at the first that differs more than the thresholds, so moving parts keep
    # their edges. Stored clips then no longer carry the camera's raw sensor noise; "" stores it as
    # recorded. Live view's denoise_filter is separate: it holds frames back (delay), clips do not
    # care, so this window is wider (docs/plans/clip-transcode-denoise.md).
    "clip_denoise_filter": "atadenoise=0a=0.16:0b=0.32:1a=0.16:1b=0.32:2a=0.16:2b=0.32:s=7:a=s",
}

# Automatic recording configuration
AUTO_RECORDING_CONFIG = {
    "enabled": os.getenv("ROBOTCONTROL_AUTO_RECORDING_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
    "startup_delay_seconds": 20,            # Delay before starting recording
    "primary_camera_id": 0,                 # Default camera to use for automatic recording
    "rolling_clips_limit": 120,             # Maximum rolling clips to maintain
    "experiment_folders_limit": 20,         # Maximum experiment folders to keep
    "archive_duration_minutes": 15,         # Minutes of clips to archive per experiment
    "experiment_check_interval_seconds": 5,   # Seconds between experiment state checks (reduced to catch short experiments)
}

# Live streaming configuration
LIVE_STREAMING_CONFIG = {
                           # Enable live streaming functionality
    "max_concurrent_sessions": 10,             # Maximum concurrent streaming sessions
    "session_timeout_seconds": 60,             # Session timeout after inactivity
    "cpu_soft_limit_percent": int(os.getenv("STREAMING_CPU_SOFT_LIMIT", "75")),  # CPU% to start degrading streams
    "cpu_hard_limit_percent": int(os.getenv("STREAMING_CPU_HARD_LIMIT", "90")),  # CPU% to stop streaming sessions
    # Temporal denoise before encoding (ffmpeg filter on the encoder's thread budget): each pixel is
    # averaged over up to 5 frames, stopping at the first frame where it changes more than the
    # thresholds, so moving parts keep their edges. Sensor noise no longer uses up the bits, so
    # 400 kbit/s keeps more detail than 600 did and stays near 400 in noisy scenes. It holds back
    # 3 frames (200 ms at 15 fps). "" turns it off (docs/plans/live-view-denoise.md).
    "denoise_filter": "atadenoise=0a=0.16:0b=0.32:1a=0.16:1b=0.32:2a=0.16:2b=0.32:s=5:a=s",
    # Seconds between keyframes (GOP = int(fps × this) frames). A viewer who joins, resumes or is
    # skipped for lag waits for the next keyframe, so this bounds that wait; each keyframe is about
    # five delta frames of data, which a thin link takes longer to carry (docs/plans/live-view-keyframes.md).
    "keyframe_seconds": 1,
    # One H.264 stream (640×480, keyframe every keyframe_seconds) shared by every viewer. Level 0 is normal; the CPU
    # guard steps down one level at a time under load and back up when calm. Each rate divides the
    # camera's 30 fps (CAMERA_CONFIG capture_fps; also 15) so frames stay evenly spaced. "denoise"
    # applies denoise_filter; the degraded levels go without, as 3 held frames there are 400–600 ms.
    "encoder_levels": [
        {"fps": 15, "bitrate_kbps": 400, "denoise": True},
        {"fps": 7.5, "bitrate_kbps": 300},
        {"fps": 5, "bitrate_kbps": 200},
    ],
}

# Global settings instance
settings = Settings()

# Export VIDEO_PATH for compatibility with existing camera service
VIDEO_PATH = str(settings.VIDEO_PATH)
