"""
PyRobot Backend Constants
Consolidated constants for camera service and API operations
"""

# Camera system constants
CAMERA_STREAM_FPS = 15  # FPS for live streaming (lower than recording FPS)
VIDEO_CODEC = 'mp4v'    # Video codec for recording
CAMERA_DETECTION_TIMEOUT = 5  # Seconds to wait when detecting cameras

# WebSocket constants
WS_HEARTBEAT_INTERVAL = 30  # Seconds between WebSocket heartbeats

# Error messages
ERROR_MESSAGES = {
    "CAMERA_NOT_FOUND": "Camera not found",
    "CAMERA_NOT_RECORDING": "Camera is not recording",
    "CAMERA_ALREADY_RECORDING": "Camera is already recording",
    "RECORDING_START_FAILED": "Failed to start recording",
    "RECORDING_STOP_FAILED": "Failed to stop recording",
    "STREAM_UNAVAILABLE": "Camera stream is unavailable",
    "AUTHENTICATION_FAILED": "Authentication failed",
    "INSUFFICIENT_PERMISSIONS": "Insufficient permissions",
    "INTERNAL_SERVER_ERROR": "Internal server error occurred",
    "SERVICE_UNAVAILABLE": "Service temporarily unavailable"
}

# Camera system settings
DEFAULT_CAMERA_RESOLUTION = (640, 480)
DEFAULT_CAMERA_FPS = 30
DEFAULT_RECORDING_DURATION = 60  # seconds
MAX_ROLLING_CLIPS = 120

# File extensions
SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov']
SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp']

# Hamilton VENUS experiment state mapping
# Maps Hamilton database run state codes to our internal enum values
HAMILTON_STATE_MAPPING = {
    "1": "Running",        # Experiment running
    "64": "Aborted",       # Experiment aborted/cancelled  
    "128": "Complete",     # Experiment finished/completed
    # String fallbacks for direct matches
    "Running": "Running",
    "Complete": "Complete", 
    "Aborted": "Aborted",
    "Error": "Error",
    "Unknown": "Unknown"
}