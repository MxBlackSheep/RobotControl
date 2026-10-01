"""
Individual streaming session management.
Handles one viewer's WebSocket: H.264 frames from the shared encoder, acknowledgements and pause.
"""

import asyncio
import logging
import struct
import time
from typing import Optional
from fastapi import WebSocket

from backend.services.h264_encoder import AccessUnit
from backend.services.streaming_types import StreamingSession, StreamControl, StreamFrame
from backend.config import LIVE_STREAMING_CONFIG

logger = logging.getLogger(__name__)

# Binary frame message: this header, then one H.264 access unit (Annex-B). Little-endian: version,
# sequence, capture time (Unix seconds), width, height, flags. Errors and status stay JSON text.
FRAME_HEADER = struct.Struct('<BIdHHB')
FRAME_VERSION = 2
# A keyframe (IDR with SPS/PPS) decodes on its own; a viewer starts and resumes on one.
FLAG_KEYFRAME = 1
# Frames the browser has not yet acknowledged (decoded). Two keeps the pipe busy
# without letting a slow tunnel queue seconds of video.
MAX_UNACKNOWLEDGED = 2
# A viewer that acknowledges nothing for this long has gone; its session ends.
ACK_TIMEOUT_SECONDS = 15
# The browser sends a keepalive every 30 s (also while its tab is hidden and paused, and through
# Cloudflare, which closes WebSockets silent for about 100 s). Silence for this long ends the
# session, so a half-open connection cannot hold one of the limited session slots.
BROWSER_SILENCE_SECONDS = 75


class StreamingSessionHandler:
    """
    Handles an individual user's streaming session: the WebSocket, flow control and this
    viewer's position in the shared H.264 stream.
    """

    def __init__(self, session: StreamingSession, websocket: WebSocket):
        self.session = session
        self.websocket = websocket
        self.config = LIVE_STREAMING_CONFIG

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
        # Last message from the browser (any control: ack, pause, resume, keepalive).
        self.last_heard = time.monotonic()
        # A delta frame needs every frame since the last keyframe, so a viewer that joins, resumes
        # or misses a frame waits for the next keyframe. At most one frame waits here for the
        # acknowledgement window: never a queue.
        self.pending: Optional[AccessUnit] = None
        self.awaiting_keyframe = True

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
        self.pending = None

        try:
            if self.websocket is not None:
                await asyncio.wait_for(self.websocket.close(), timeout=5)
        except Exception as e:
            logger.debug(f"Error closing WebSocket for session {self.session.session_id}: {e}")

        logger.info(f"Streaming session {self.session.session_id} stopped")

    @property
    def watching(self) -> bool:
        """Connected and visible: wants frames from the encoder."""
        return self.is_running and self.session.is_active and not self.is_paused

    def offer(self, unit: AccessUnit) -> bool:
        """Take a frame from the shared encoder; True when it now waits to be sent."""
        if unit.keyframe:
            # Decodable on its own: it replaces a waiting frame and restarts this viewer's chain.
            self.pending, self.awaiting_keyframe = unit, False
            return True
        if self.awaiting_keyframe:
            return False
        if self.pending is None:
            self.pending = unit
            return True
        # A frame is already waiting: skipping this one breaks the chain until the next keyframe.
        self.awaiting_keyframe = True
        return False

    def take_pending(self) -> Optional[AccessUnit]:
        unit, self.pending = self.pending, None
        return unit

    def resync(self) -> None:
        """Drop the waiting frame and start again at the next keyframe (pause, new encoder)."""
        self.pending = None
        self.awaiting_keyframe = True

    async def send_access_unit(self, unit: AccessUnit) -> bool:
        """Send one encoded frame; True when sent."""
        if not self.is_running or self.is_paused:
            return False
        try:
            self.sent_sequence += 1
            header = FRAME_HEADER.pack(FRAME_VERSION, self.sent_sequence & 0xFFFFFFFF, unit.captured_at,
                                       unit.width, unit.height, FLAG_KEYFRAME if unit.keyframe else 0)
            await self.websocket.send_bytes(header + unit.data)

            # Update statistics
            self.session.frames_sent += 1
            self.frames_in_period += 1
            frame_size = FRAME_HEADER.size + len(unit.data)
            self.session.bytes_sent += frame_size
            self.bytes_in_period += frame_size
            self.session.update_activity()
            if time.time() - self.last_stats_time >= 1.0:
                await self._update_statistics()
            return True

        except Exception as e:
            logger.error(f"Error sending frame for session {self.session.session_id}: {e}")
            self.session.last_error = str(e)
            self.resync()  # The browser may not have this frame.
            return False

    async def handle_control(self, control: StreamControl) -> None:
        """
        Handle control message from client.

        Args:
            control: Control message
        """
        self.last_heard = time.monotonic()
        try:
            if control.type == "ack":
                self.acknowledge(control.parameters.get("sequence"))

            elif control.type in ("pause", "resume"):
                # A hidden browser tab pauses; frames in flight no longer count against it,
                # and it resumes at the next keyframe.
                self.is_paused = control.type == "pause"
                self.resync()
                self.acknowledged_sequence = self.sent_sequence
                self._window_open.set()
                self.session.update_activity()
                await self._send_status()

            logger.debug(f"Handled control message: {control.type} for session {self.session.session_id}")

        except Exception as e:
            logger.error(f"Error handling control for session {self.session.session_id}: {e}")
            await self.send_error(str(e))

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

    async def send_error(self, error_message: str) -> None:
        """Show an error in this viewer's live view (JSON text message)."""
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

        return True
