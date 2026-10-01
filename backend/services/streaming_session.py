"""
Individual streaming session management.
Handles one viewer's WebSocket: H.264 frames from the shared encoder, acknowledgements and pause.
"""

import asyncio
import logging
import math
import struct
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple
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
# Frames in flight (sent, not yet acknowledged as decoded) are sized to the viewer's link: about
# one round trip of video, from the smallest round trip seen in the last RTT_WINDOW_SECONDS. The
# smallest reflects distance, not the queueing our own frames cause on a thin link, so a far but
# fast link (the tunnel from another site) gets every frame and a slow one cannot fill a queue.
# A fixed window of two frames allowed only two per round trip: above ~130 ms the H.264 chain broke
# every second and the picture froze until the next keyframe.
MIN_IN_FLIGHT = 2                # before the first measurement, and the floor
MAX_IN_FLIGHT_SECONDS = 1.0      # at most one second of video in flight
MAX_IN_FLIGHT_BYTES = 256_000    # and at most this much data (a keyframe plus deltas)
RTT_HEADROOM = 1.5               # room for jitter above the smallest round trip
RTT_WINDOW_SECONDS = 10
# Frames waiting for the window. A frame waiting longer than this, or more of them, means the link
# is slower than the stream: drop them and resume at the next keyframe instead of falling behind.
MAX_WAIT_SECONDS = 0.5
MAX_WAITING = 8
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

        # Flow control: sequence of the last frame sent and the last one acknowledged; send time and
        # size of each frame in flight; recent round trips (monotonic time, seconds).
        self.sent_sequence = 0
        self.acknowledged_sequence = 0
        self._window_open = asyncio.Event()
        self._window_open.set()
        self._in_flight: Dict[int, Tuple[float, int]] = {}
        self._in_flight_bytes = 0
        self._round_trips: Deque[Tuple[float, float]] = deque(maxlen=64)
        self._smallest_round_trip: Optional[float] = None
        # Last message from the browser (any control: ack, pause, resume, keepalive).
        self.last_heard = time.monotonic()
        # A delta frame needs every frame since the last keyframe, so a viewer that joins, resumes
        # or misses a frame waits for the next keyframe. Frames waiting for the window, with the
        # time each arrived; bounded by MAX_WAIT_SECONDS and MAX_WAITING.
        self.pending: Deque[Tuple[AccessUnit, float]] = deque()
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
        self.pending.clear()

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
        now = time.monotonic()
        if unit.keyframe:
            # Decodable on its own: it replaces waiting frames and restarts this viewer's chain.
            self.pending.clear()
            self.pending.append((unit, now))
            self.awaiting_keyframe = False
            return True
        if self.awaiting_keyframe:
            return False
        if self.pending and (now - self.pending[0][1] > MAX_WAIT_SECONDS or len(self.pending) >= MAX_WAITING):
            # The link is slower than the stream: skip to the next keyframe rather than fall behind.
            self.resync()
            return False
        self.pending.append((unit, now))
        return True

    def take_pending(self) -> Optional[AccessUnit]:
        return self.pending.popleft()[0] if self.pending else None

    def resync(self) -> None:
        """Drop the waiting frames and start again at the next keyframe (pause, new encoder, lag)."""
        self.pending.clear()
        self.awaiting_keyframe = True

    async def send_access_unit(self, unit: AccessUnit) -> bool:
        """Send one encoded frame; True when sent."""
        if not self.is_running or self.is_paused:
            return False
        try:
            self.sent_sequence += 1
            size = FRAME_HEADER.size + len(unit.data)
            self._in_flight[self.sent_sequence] = (time.monotonic(), size)
            self._in_flight_bytes += size
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
                self._in_flight.clear()
                self._in_flight_bytes = 0
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
            now = time.monotonic()
            sent = self._in_flight.get(sequence)
            if sent is not None:
                self._round_trips.append((now, now - sent[0]))
            for acknowledged in range(self.acknowledged_sequence + 1, sequence + 1):
                self._in_flight_bytes -= self._in_flight.pop(acknowledged, (0, 0))[1]
            self.acknowledged_sequence = sequence
            self.session.update_activity()
            self._window_open.set()

    def smallest_round_trip(self) -> Optional[float]:
        """Smallest recent round trip; the last known one while there are no recent samples."""
        cutoff = time.monotonic() - RTT_WINDOW_SECONDS
        while self._round_trips and self._round_trips[0][0] < cutoff:
            self._round_trips.popleft()
        if self._round_trips:
            self._smallest_round_trip = min(round_trip for _, round_trip in self._round_trips)
        return self._smallest_round_trip

    def window(self, fps: float) -> int:
        """Frames allowed in flight: about one round trip of video, within the limits above."""
        round_trip = self.smallest_round_trip()
        if round_trip is None:
            return MIN_IN_FLIGHT
        frames = math.ceil(fps * round_trip * RTT_HEADROOM) + 1
        return max(MIN_IN_FLIGHT, min(frames, math.ceil(fps * MAX_IN_FLIGHT_SECONDS)))

    async def wait_for_window(self, fps: float, timeout: float = ACK_TIMEOUT_SECONDS) -> None:
        """Wait until the link has room for another frame (see window()).

        Raises TimeoutError when the viewer acknowledges nothing for `timeout` seconds.
        """
        async with asyncio.timeout(timeout):
            while (self.sent_sequence - self.acknowledged_sequence >= self.window(fps)
                   or self._in_flight_bytes >= MAX_IN_FLIGHT_BYTES):
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
