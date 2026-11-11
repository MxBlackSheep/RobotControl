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
    frames_sent: int = 0                   # Total frames sent in session
    bytes_sent: int = 0                    # Total bytes sent
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
            "frames_sent": self.frames_sent,
            "bytes_sent": self.bytes_sent,
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
