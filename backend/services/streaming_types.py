"""
Data models for live streaming functionality.
Following modularity principle with clear separation of concerns.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import numpy as np

@dataclass
class FrameData:
    """
    Container for a single video frame with metadata.
    Used for zero-copy frame sharing between recording and streaming.
    """
    frame: np.ndarray                      # Raw frame data (BGR format from OpenCV)
    timestamp: datetime                    # Frame capture timestamp
    frame_number: int                      # Sequential frame number
    is_keyframe: bool                      # Whether this is a keyframe
    size_bytes: int                        # Frame size in bytes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses (without frame data)."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "frame_number": self.frame_number,
            "is_keyframe": self.is_keyframe,
            "size_bytes": self.size_bytes
        }


@dataclass
class StreamingSession:
    """
    Individual user streaming session information.
    Each user gets their own session with independent controls.
    """
    session_id: str                        # Unique session identifier (UUID)
    user_id: str                           # User identifier from auth
    user_name: str                         # User display name
    created_at: datetime                   # Session creation time
    last_activity: datetime                # Last frame sent or control received
    is_active: bool                        # Whether streaming is currently active
    frames_sent: int = 0                   # Total frames sent in session
    bytes_sent: int = 0                    # Total bytes sent
    bandwidth_usage_mbps: float = 0.0      # Current bandwidth usage
    quality_level: str = "adaptive"        # Current quality (high/medium/low/adaptive)
    target_fps: int = 15                   # Target frames per second
    actual_fps: float = 0.0                # Actual achieved fps
    client_ip: str = ""                    # Client IP address
    websocket_state: str = "connecting"    # WebSocket state (connecting/connected/disconnected)
    last_error: Optional[str] = None       # Last error message if any
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_active": self.is_active,
            "frames_sent": self.frames_sent,
            "bytes_sent": self.bytes_sent,
            "bandwidth_usage_mbps": round(self.bandwidth_usage_mbps, 2),
            "quality_level": self.quality_level,
            "target_fps": self.target_fps,
            "actual_fps": round(self.actual_fps, 1),
            "client_ip": self.client_ip,
            "websocket_state": self.websocket_state,
            "last_error": self.last_error
        }
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
    
    def is_timed_out(self, timeout_seconds: int) -> bool:
        """Check if session has timed out."""
        elapsed = (datetime.now() - self.last_activity).total_seconds()
        return elapsed > timeout_seconds


@dataclass
class StreamingStatus:
    """
    Overall streaming service status.
    Provides system-wide view of streaming activity.
    """
    enabled: bool                           # Whether streaming service is enabled
    active_sessions: List[StreamingSession] # Current active sessions
    max_sessions: int                       # Maximum allowed concurrent sessions
    total_bandwidth_mbps: float            # Total bandwidth being used
    available_bandwidth_mbps: float        # Available bandwidth remaining
    resource_usage_percent: float          # System resource usage by streaming
    recording_impact: str                  # Impact on recording (none/minimal/degraded)
    priority_mode: str                     # Current resource state (normal/protected/emergency)
    frames_distributed: int = 0            # Total frames distributed to all sessions
    bytes_distributed: int = 0             # Total bytes distributed
    service_uptime_seconds: float = 0.0    # Service uptime in seconds
    last_error: Optional[str] = None       # Last service-level error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "enabled": self.enabled,
            "active_session_count": len(self.active_sessions),
            "active_sessions": [s.to_dict() for s in self.active_sessions],
            "max_sessions": self.max_sessions,
            "total_bandwidth_mbps": round(self.total_bandwidth_mbps, 2),
            "available_bandwidth_mbps": round(self.available_bandwidth_mbps, 2),
            "resource_usage_percent": round(self.resource_usage_percent, 1),
            "recording_impact": self.recording_impact,
            "priority_mode": self.priority_mode,
            "frames_distributed": self.frames_distributed,
            "bytes_distributed": self.bytes_distributed,
            "service_uptime_seconds": round(self.service_uptime_seconds, 1),
            "last_error": self.last_error
        }
    
    def can_accept_new_session(self) -> bool:
        """Check if service can accept a new streaming session."""
        return (
            self.enabled and 
            len(self.active_sessions) < self.max_sessions and
            self.priority_mode != "emergency" and
            self.available_bandwidth_mbps > 0.5  # Minimum 0.5 Mbps for new session
        )


@dataclass
class StreamControl:
    """Client control message for a streaming session."""
    type: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "StreamControl":
        if not isinstance(data, dict):
            return cls(type='unknown')
        control_type = str(data.get('type', 'unknown')).lower() or 'unknown'
        parameters = data.get('parameters')
        if not isinstance(parameters, dict):
            parameters = {}
        return cls(type=control_type, parameters=parameters)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'parameters': self.parameters
        }


@dataclass
class StreamFrame:
    """Serialized frame/control payload sent over WebSocket."""
    type: str
    data: Optional[str] = None
    frame: Optional[str] = None
    status: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: Optional[float] = None
    frame_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'type': self.type}
        if self.data is not None:
            payload['data'] = self.data
        if self.frame is not None:
            payload['frame'] = self.frame
        if self.status is not None:
            payload['status'] = self.status
        if self.error is not None:
            payload['error'] = self.error
        if self.timestamp is not None:
            payload['timestamp'] = self.timestamp
        if self.frame_number is not None:
            payload['frame_number'] = self.frame_number
        return payload


@dataclass
class QualitySettings:
    """
    Quality settings for streaming.
    Used to control encoding parameters per session.
    """
    fps: int                               # Target frames per second
    resolution_scale: float                # Resolution scaling factor (0.0-1.0)
    jpeg_quality: int                      # JPEG compression quality (0-100)
    max_bitrate_kbps: int                  # Maximum bitrate in kilobits per second
    skip_frames: int = 0                   # Number of frames to skip (for degradation)
    
    @classmethod
    def from_config(cls, quality_level: str, config: Dict[str, Any]) -> "QualitySettings":
        """Create from configuration dictionary."""
        quality_config = config["quality_levels"].get(quality_level, config["quality_levels"]["medium"])
        return cls(
            fps=quality_config["fps"],
            resolution_scale=quality_config["resolution_scale"],
            jpeg_quality=quality_config["jpeg_quality"],
            max_bitrate_kbps=quality_config["max_bitrate_kbps"]
        )
    
    def degrade(self) -> "QualitySettings":
        """Return degraded quality settings for resource protection."""
        return QualitySettings(
            fps=max(5, self.fps // 2),
            resolution_scale=max(0.25, self.resolution_scale * 0.75),
            jpeg_quality=max(30, self.jpeg_quality - 20),
            max_bitrate_kbps=max(250, self.max_bitrate_kbps // 2),
            skip_frames=min(5, self.skip_frames + 1)
        )


