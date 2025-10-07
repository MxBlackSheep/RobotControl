"""
Individual streaming session management.
Handles WebSocket communication, frame encoding, and quality adaptation.
"""

import asyncio
import base64
import io
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
import cv2
import numpy as np
from fastapi import WebSocket

from backend.services.streaming_types import (
    StreamingSession, QualitySettings, FrameData,
    StreamControl, StreamFrame
)
from backend.config import LIVE_STREAMING_CONFIG

logger = logging.getLogger(__name__)


class StreamingSessionHandler:
    """
    Handles an individual user's streaming session.
    Manages WebSocket connection, frame encoding, and quality control.
    """
    
    def __init__(
        self,
        session: StreamingSession,
        websocket: WebSocket,
        quality_settings: Optional[QualitySettings] = None
    ):
        """
        Initialize streaming session handler.
        
        Args:
            session: StreamingSession data model
            websocket: WebSocket connection
            quality_settings: Initial quality settings (uses config default if None)
        """
        self.session = session
        self.websocket = websocket
        self.config = LIVE_STREAMING_CONFIG
        
        # Quality settings
        if quality_settings is None:
            quality_settings = QualitySettings.from_config(
                session.quality_level,
                self.config
            )
        self.quality_settings = quality_settings
        
        # Frame control
        self.frame_skip_counter = 0
        self.last_frame_time = 0.0
        self.frame_interval = 1.0 / self.quality_settings.fps
        
        # Statistics
        self.start_time = time.time()
        self.last_stats_time = time.time()
        self.frames_in_period = 0
        self.bytes_in_period = 0
        
        # Control flags
        self.is_running = False
        self.is_paused = False
        
        logger.info(f"StreamingSessionHandler initialized for session {session.session_id}")
    
    async def start(self) -> None:
        """
        Start the streaming session.
        Accepts the WebSocket connection and begins streaming.
        """
        try:
            # Accept WebSocket connection
            await self.websocket.accept()
            self.session.websocket_state = "connected"
            self.session.is_active = True  # CRITICAL: Mark session as active for frame distribution
            self.is_running = True
            
            # Send initial status
            await self._send_status()
            
            logger.info(f"Streaming session {self.session.session_id} started and marked as active")
            
        except Exception as e:
            logger.error(f"Error starting session {self.session.session_id}: {e}")
            self.session.last_error = str(e)
            self.session.is_active = False  # Ensure not marked as active on failure
            raise
    
    async def stop(self) -> None:
        """
        Stop the streaming session.
        Closes WebSocket connection and cleans up resources.
        """
        self.is_running = False
        self.session.is_active = False
        self.session.websocket_state = "disconnected"
        
        try:
            await self.websocket.close()
        except Exception as e:
            logger.debug(f"Error closing WebSocket for session {self.session.session_id}: {e}")
        
        logger.info(f"Streaming session {self.session.session_id} stopped")
    
    async def send_frame(self, frame_data: FrameData) -> bool:
        """
        Send a frame to the client.
        Applies quality settings and frame skipping.
        
        Args:
            frame_data: Frame to send
            
        Returns:
            True if frame was sent successfully
        """
        if not self.is_running or self.is_paused:
            return False
        
        # Check frame rate limiting
        current_time = time.time()
        if current_time - self.last_frame_time < self.frame_interval:
            return False  # Skip frame to maintain target FPS
        
        # Apply frame skipping for degradation
        if self.quality_settings.skip_frames > 0:
            self.frame_skip_counter += 1
            if self.frame_skip_counter % (self.quality_settings.skip_frames + 1) != 0:
                return False  # Skip this frame
        
        try:
            # Encode frame
            encoded_frame = self._encode_frame(frame_data.frame)
            if encoded_frame is None:
                return False
            
            # Create message
            message = StreamFrame(
                type="frame",
                data=encoded_frame,
                timestamp=frame_data.timestamp.timestamp(),
                frame_number=frame_data.frame_number
            )
            
            # Send via WebSocket
            await self.websocket.send_json(message.to_dict())
            
            # Update statistics
            self.session.frames_sent += 1
            self.frames_in_period += 1
            frame_size = len(encoded_frame)
            self.session.bytes_sent += frame_size
            self.bytes_in_period += frame_size
            
            # Update activity
            self.session.update_activity()
            self.last_frame_time = current_time
            
            # Update statistics periodically
            if current_time - self.last_stats_time >= 1.0:
                await self._update_statistics()
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending frame for session {self.session.session_id}: {e}")
            self.session.last_error = str(e)
            return False
    
    async def handle_control(self, control: StreamControl) -> None:
        """
        Handle control message from client.
        
        Args:
            control: Control message
        """
        try:
            if control.type == "start":
                self.is_paused = False
                self.session.is_active = True
                await self._send_status()
                
            elif control.type == "stop":
                self.is_paused = True
                self.session.is_active = False
                await self._send_status()
                
            elif control.type == "quality":
                quality_level = control.parameters.get("quality", "adaptive")
                self.update_quality(quality_level)
                await self._send_status()
                
            elif control.type == "heartbeat":
                self.session.update_activity()
                await self._send_status()
            
            logger.debug(f"Handled control message: {control.type} for session {self.session.session_id}")
            
        except Exception as e:
            logger.error(f"Error handling control for session {self.session.session_id}: {e}")
            await self._send_error(str(e))
    
    async def receive_control(self) -> Optional[StreamControl]:
        """
        Receive control message from client.
        
        Returns:
            StreamControl message or None if connection closed
        """
        try:
            data = await self.websocket.receive_json()
            return StreamControl.from_dict(data)
        except Exception as e:
            logger.debug(f"Error receiving control for session {self.session.session_id}: {e}")
            return None
    
    def update_quality(self, quality_level: str) -> None:
        """
        Update quality settings for the session.
        
        Args:
            quality_level: New quality level (high/medium/low/adaptive)
        """
        self.session.quality_level = quality_level
        self.quality_settings = QualitySettings.from_config(quality_level, self.config)
        self.frame_interval = 1.0 / self.quality_settings.fps
        
        logger.info(f"Updated quality to {quality_level} for session {self.session.session_id}")
    
    def degrade_quality(self) -> None:
        """
        Degrade quality for resource protection.
        Called by priority manager when resources are constrained.
        """
        self.quality_settings = self.quality_settings.degrade()
        self.frame_interval = 1.0 / self.quality_settings.fps
        self.session.quality_level = "degraded"
        
        logger.warning(f"Degraded quality for session {self.session.session_id}")
    
    def _encode_frame(self, frame: np.ndarray) -> Optional[str]:
        """
        Encode frame to JPEG and base64.
        
        Args:
            frame: Raw frame data (BGR format)
            
        Returns:
            Base64 encoded JPEG string or None if encoding fails
        """
        try:
            # Apply resolution scaling if needed
            if self.quality_settings.resolution_scale < 1.0:
                height, width = frame.shape[:2]
                new_width = int(width * self.quality_settings.resolution_scale)
                new_height = int(height * self.quality_settings.resolution_scale)
                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
            
            # Encode to JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality_settings.jpeg_quality]
            success, buffer = cv2.imencode('.jpg', frame, encode_params)
            
            if not success:
                logger.error(f"Failed to encode frame for session {self.session.session_id}")
                return None
            
            # Convert to base64
            jpeg_bytes = buffer.tobytes()
            base64_str = base64.b64encode(jpeg_bytes).decode('utf-8')
            
            return base64_str
            
        except Exception as e:
            logger.error(f"Error encoding frame for session {self.session.session_id}: {e}")
            return None
    
    async def _update_statistics(self) -> None:
        """Update session statistics (FPS, bandwidth, etc.)."""
        current_time = time.time()
        time_delta = current_time - self.last_stats_time
        
        if time_delta > 0:
            # Calculate actual FPS
            self.session.actual_fps = self.frames_in_period / time_delta
            
            # Calculate bandwidth (Mbps)
            self.session.bandwidth_usage_mbps = (self.bytes_in_period * 8) / (time_delta * 1_000_000)
            
            # Reset period counters
            self.frames_in_period = 0
            self.bytes_in_period = 0
            self.last_stats_time = current_time
    
    async def _send_status(self) -> None:
        """Send status update to client."""
        try:
            status = {
                "fps": self.session.actual_fps,
                "quality": self.session.quality_level,
                "bandwidth_mbps": self.session.bandwidth_usage_mbps,
                "recording_active": True,  # Would get from camera service
                "is_paused": self.is_paused
            }
            
            message = StreamFrame(
                type="status",
                status=status
            )
            
            await self.websocket.send_json(message.to_dict())
            
        except Exception as e:
            logger.error(f"Error sending status for session {self.session.session_id}: {e}")
    
    async def _send_error(self, error_message: str) -> None:
        """
        Send error message to client.
        
        Args:
            error_message: Error description
        """
        try:
            message = StreamFrame(
                type="error",
                error=error_message
            )
            
            await self.websocket.send_json(message.to_dict())
            
        except Exception as e:
            logger.error(f"Error sending error message for session {self.session.session_id}: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        uptime = time.time() - self.start_time
        
        return {
            "session_id": self.session.session_id,
            "user_id": self.session.user_id,
            "uptime_seconds": uptime,
            "frames_sent": self.session.frames_sent,
            "bytes_sent": self.session.bytes_sent,
            "actual_fps": self.session.actual_fps,
            "target_fps": self.quality_settings.fps,
            "bandwidth_mbps": self.session.bandwidth_usage_mbps,
            "quality_level": self.session.quality_level,
            "is_active": self.session.is_active,
            "is_paused": self.is_paused
        }
    
    def is_healthy(self) -> bool:
        """
        Check if session is healthy.
        
        Returns:
            True if session is operating normally
        """
        # Check if session is active
        if not self.is_running or not self.session.is_active:
            return True  # Not active is OK
        
        # Check timeout
        if self.session.is_timed_out(self.config["session_timeout_seconds"]):
            return False
        
        # Check if achieving reasonable FPS
        if self.session.actual_fps > 0 and self.session.actual_fps < self.quality_settings.fps * 0.5:
            logger.warning(f"Session {self.session.session_id} FPS low: {self.session.actual_fps:.1f}")
            # This is a warning but not unhealthy
        
        return True