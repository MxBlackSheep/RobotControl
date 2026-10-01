"""
Individual streaming session management.
Handles WebSocket communication, frame encoding, and quality adaptation.
"""

import asyncio
import logging
import struct
import time
from typing import Optional
import numpy as np
from fastapi import WebSocket

from backend.services.streaming_types import (
    StreamingSession, QualitySettings, FrameData,
    StreamControl, StreamFrame
)
from backend.config import LIVE_STREAMING_CONFIG
from backend.services.frame_encoder import encode_jpeg

logger = logging.getLogger(__name__)

# Binary frame message: this header, then the JPEG. Little-endian: version, sequence,
# capture time (Unix seconds), width, height. Errors and status stay JSON text.
FRAME_HEADER = struct.Struct('<BIdHH')
FRAME_VERSION = 1
# Frames the browser has not yet acknowledged (decoded). Two keeps the pipe busy
# without letting a slow tunnel queue seconds of video.
MAX_UNACKNOWLEDGED = 2
# A viewer that acknowledges nothing for this long has gone; its session ends.
ACK_TIMEOUT_SECONDS = 15
# QualitySettings.degrade() reaches its floor (5 fps, 30 % JPEG, skip 5) within five steps.
MAX_DEGRADE_LEVEL = 5


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
        # Degradation is a level over the requested quality, so it can step back up.
        self.requested_quality = quality_settings
        self.requested_level = session.quality_level
        self.degrade_level = 0
        
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
        self._stopped = False
        self.is_paused = False

        # Flow control: sequence of the last frame sent and the last one acknowledged.
        self.sent_sequence = 0
        self.acknowledged_sequence = 0
        self._window_open = asyncio.Event()
        self._window_open.set()
        
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
        if self._stopped:
            return
        self._stopped = True
        self.is_running = False
        self.session.is_active = False
        self.session.websocket_state = "disconnected"
        
        try:
            if self.websocket is not None:
                await asyncio.wait_for(self.websocket.close(), timeout=5)
        except Exception as e:
            logger.debug(f"Error closing WebSocket for session {self.session.session_id}: {e}")
        
        logger.info(f"Streaming session {self.session.session_id} stopped")
    
    async def send_frame(self, frame_data: FrameData, encoder=None) -> bool:
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
        current_time = time.monotonic()
        if current_time - self.last_frame_time < self.frame_interval:
            return False  # Skip frame to maintain target FPS
        
        # Apply frame skipping for degradation
        if self.quality_settings.skip_frames > 0:
            self.frame_skip_counter += 1
            if self.frame_skip_counter % (self.quality_settings.skip_frames + 1) != 0:
                return False  # Skip this frame
        
        try:
            # Encode frame
            encoded = (await encoder(frame_data, self.quality_settings) if encoder
                       else await asyncio.to_thread(self._encode_frame, frame_data.frame))
            if encoded is None:
                return False
            jpeg, width, height = encoded

            self.sent_sequence += 1
            header = FRAME_HEADER.pack(FRAME_VERSION, self.sent_sequence & 0xFFFFFFFF,
                                       frame_data.timestamp.timestamp(), width, height)
            await self.websocket.send_bytes(header + jpeg)

            # Update statistics
            self.session.frames_sent += 1
            self.frames_in_period += 1
            frame_size = FRAME_HEADER.size + len(jpeg)
            self.session.bytes_sent += frame_size
            self.bytes_in_period += frame_size
            
            # Update activity
            self.session.update_activity()
            self.last_frame_time = current_time
            
            # Update statistics periodically
            if time.time() - self.last_stats_time >= 1.0:
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
            if control.type == "ack":
                self.acknowledge(control.parameters.get("sequence"))

            elif control.type in ("pause", "resume"):
                # A hidden browser tab pauses; frames in flight no longer count against it.
                self.is_paused = control.type == "pause"
                self.acknowledged_sequence = self.sent_sequence
                self._window_open.set()
                self.session.update_activity()
                await self._send_status()

            logger.debug(f"Handled control message: {control.type} for session {self.session.session_id}")
            
        except Exception as e:
            logger.error(f"Error handling control for session {self.session.session_id}: {e}")
            await self._send_error(str(e))
    
    def acknowledge(self, sequence) -> None:
        """The browser decoded frame `sequence` (and every earlier one)."""
        if isinstance(sequence, int) and self.acknowledged_sequence < sequence <= self.sent_sequence:
            self.acknowledged_sequence = sequence
            self.session.update_activity()
            self._window_open.set()

    async def wait_for_window(self, timeout: float = ACK_TIMEOUT_SECONDS) -> None:
        """Wait until fewer than MAX_UNACKNOWLEDGED frames are in flight.

        Raises TimeoutError when the viewer acknowledges nothing for `timeout` seconds.
        """
        async with asyncio.timeout(timeout):
            while self.sent_sequence - self.acknowledged_sequence >= MAX_UNACKNOWLEDGED:
                self._window_open.clear()
                await self._window_open.wait()

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
    
    def degrade_quality(self) -> None:
        """One step down under CPU pressure (the resource guard in live_streaming.py)."""
        if self.degrade_level < MAX_DEGRADE_LEVEL:
            self.degrade_level += 1
            self._apply_degrade_level()
            logger.warning("Degraded quality for session %s to level %s", self.session.session_id, self.degrade_level)

    def recover_quality(self) -> None:
        """One step back up once CPU has stayed low; level 0 is the requested quality."""
        if self.degrade_level > 0:
            self.degrade_level -= 1
            self._apply_degrade_level()
            logger.info("Recovered quality for session %s to level %s", self.session.session_id, self.degrade_level)

    def _apply_degrade_level(self) -> None:
        settings = self.requested_quality
        for _ in range(self.degrade_level):
            settings = settings.degrade()
        self.quality_settings = settings
        self.frame_interval = 1.0 / settings.fps
        self.session.quality_level = self.requested_level if self.degrade_level == 0 else "degraded"
    
    def _encode_frame(self, frame: np.ndarray):
        """Encode a BGR frame to (jpeg bytes, width, height), or None on failure."""
        try:
            return encode_jpeg(frame, self.quality_settings.resolution_scale, self.quality_settings.jpeg_quality)
        except Exception as exc:
            logger.error("Frame encoding failed: %s", exc)
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