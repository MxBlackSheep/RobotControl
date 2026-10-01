"""
Live streaming service for managing multiple concurrent streaming sessions.
Coordinates with SharedFrameBuffer so streaming can reuse recording frames, and owns the one
H.264 encoder whose output every viewer shares.
"""

import asyncio
import logging
import threading
import uuid
import time
from collections import deque
from datetime import datetime, timedelta
import psutil
from typing import Dict, Optional, Any, Deque
from fastapi import WebSocket

from backend.services.h264_encoder import AccessUnit, EncoderSettings, EncoderUnavailable, H264Encoder, find_ffmpeg
from backend.services.streaming_types import StreamingSession, StreamingStatus
from backend.services.streaming_session import ACK_TIMEOUT_SECONDS, BROWSER_SILENCE_SECONDS, StreamingSessionHandler
from backend.services.shared_frame_buffer import get_shared_frame_buffer
from backend.config import LIVE_STREAMING_CONFIG

logger = logging.getLogger(__name__)

# One quality step back up after this many consecutive one-second samples below this CPU %.
CPU_RECOVER_PERCENT = 50
CPU_RECOVER_SAMPLES = 10
# The shared stream's settings; the CPU guard moves between them (0 is normal).
ENCODER_LEVELS = tuple(EncoderSettings(level["fps"], level["bitrate_kbps"])
                       for level in LIVE_STREAMING_CONFIG["encoder_levels"])
# After an encoder crash, wait 1, 2, 4 … up to 30 s before the next start; a minute without a
# crash resets the delay.
ENCODER_RETRY_MAX_SECONDS = 30
ENCODER_CRASH_MEMORY_SECONDS = 60


class LiveStreamingService:
    """
    Main service for managing live streaming sessions.
    Singleton pattern to ensure single instance.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the live streaming service."""
        # Skip initialization if already done
        if hasattr(self, '_initialized'):
            return

        self.config = LIVE_STREAMING_CONFIG
        self.enabled = self.config["enabled"]

        # Session management
        self.sessions: Dict[str, StreamingSessionHandler] = {}
        self.sessions_by_user: Dict[str, str] = {}
        self.session_lock = asyncio.Lock()
        self._service_lock = asyncio.Lock()

        # Service components
        self.frame_buffer = get_shared_frame_buffer(self.config["frame_buffer_size"])

        # Hook camera recording into shared buffer for streaming
        self._ensure_camera_integration()

        # Service state
        self.service_started_at = datetime.now()
        self.total_sessions_created = 0
        self.total_frames_distributed = 0
        self.total_bytes_distributed = 0

        # Frame distribution
        self.distribution_task: Optional[asyncio.Task] = None
        self.distribution_active = False
        self._frame_event = asyncio.Event()
        self._delivery_tasks = {}
        self._delivery_events = {}

        # The shared encoder. Only _update_encoder starts or stops it (under _encoder_lock).
        self._encoder_factory = H264Encoder
        self._encoder = None
        self._encoder_lock = asyncio.Lock()
        self._encoder_level = 0
        self._encoder_crashes: Deque[float] = deque(maxlen=8)
        self._encoder_retry_at = 0.0
        self._encoder_error: Optional[str] = None
        self._next_submit = 0.0
        self._encoder_process: Optional[psutil.Process] = None

        self.cpu_soft_limit = self.config.get("cpu_soft_limit_percent", 75)
        self.cpu_hard_limit = self.config.get("cpu_hard_limit_percent", 90)
        self._last_resource_check = datetime.now() - timedelta(seconds=1)
        self._last_cpu_percent = 0.0
        self._last_cpu_sample_monotonic = 0.0
        self._process = psutil.Process()
        # Prime cpu_percent to avoid the first-call zero artefact
        try:
            self._process.cpu_percent(interval=None)
        except Exception:
            psutil.cpu_percent(interval=None)
        self._cpu_samples: Deque[float] = deque(maxlen=5)
        self._consecutive_soft_limit_hits = 0
        self._consecutive_hard_limit_hits = 0
        self._consecutive_calm_samples = 0
        self._resource_state = "normal"
        self._recording_impact = "none"

        self._initialized = True
        logger.info("Streaming | event=service_init | enabled=%s", self.enabled)

    def _ensure_camera_integration(self) -> None:
        """Ensure camera recording publishes frames into the shared buffer."""
        try:
            from backend.services.camera import get_camera_service
            camera_service = get_camera_service()
            if getattr(camera_service, 'streaming_integration_enabled', False):
                logger.debug("Streaming | event=camera_integration_ready")
                return
            camera_service.enable_streaming_integration()
            logger.info("Streaming | event=camera_integration_enabled")
        except Exception as exc:
            logger.warning("Streaming | event=camera_integration_failed | error=%s", exc)

    async def ensure_service_started(self) -> None:
        """Ensure the streaming service is active before handling sessions."""
        if not self.enabled:
            return
        if self.distribution_active:
            return
        await self.start_service()

    async def start_service(self) -> None:
        """
        Start the live streaming service.
        Called during application startup."""
        if not self.enabled:
            logger.info("Streaming | event=start_skipped | reason=disabled")
            return

        async with self._service_lock:
            if self.distribution_active:
                logger.debug("Streaming | event=start_ignored | reason=already_active")
                return

            # Start frame distribution
            self.distribution_active = True
            self.frame_buffer.subscribe_frames(asyncio.get_running_loop(), self._frame_event)
            self.service_started_at = datetime.now()
            self.distribution_task = asyncio.create_task(self._frame_distribution_loop())

            logger.info("Streaming | event=service_started")

    async def stop_service(self) -> None:
        """
        Stop the live streaming service.
        Called during application shutdown."""
        async with self._service_lock:
            if not self.distribution_active:
                return

            # Stop frame distribution
            self.distribution_active = False
            self.frame_buffer.unsubscribe_frames(self._frame_event)
            if self.distribution_task:
                self.distribution_task.cancel()
                try:
                    await self.distribution_task
                except asyncio.CancelledError:
                    pass

            # Stop all sessions, then the encoder (nobody is watching any more)
            await self._terminate_all_sessions("Service shutdown")
            await self._update_encoder()
            self.distribution_task = None

            logger.info("Streaming | event=service_stopped")

    async def create_session(
        self,
        user_id: str,
        user_name: str,
        client_ip: str,
    ) -> Optional[StreamingSession]:
        """
        Create a new streaming session.

        Returns the StreamingSession, or None at capacity or for a duplicate user. Raises
        EncoderUnavailable (with the reason to show) when ffmpeg.exe is missing.
        """
        find_ffmpeg()
        await self.ensure_service_started()
        await self._expire_pending_sessions()

        async with self.session_lock:
            # Check if service can accept new session
            status = self.get_status()
            if not status.can_accept_new_session():
                logger.warning("Streaming | event=session_rejected | reason=capacity | user=%s", user_id)
                return None

            # Check for existing session mapping for this user
            existing_session_id = self.sessions_by_user.get(user_id)
            if existing_session_id:
                existing_handler = self.sessions.get(existing_session_id)
                if existing_handler and existing_handler.session.websocket_state == "connected":
                    logger.warning(
                        "Streaming | event=session_rejected | reason=duplicate_user | user=%s",
                        user_id,
                    )
                    return None

                # Stale session placeholder; remove it so the user can reconnect
                self.sessions.pop(existing_session_id, None)
                self.sessions_by_user.pop(user_id, None)

            # Create new session
            session_id = str(uuid.uuid4())
            session = StreamingSession(
                session_id=session_id,
                user_id=user_id,
                user_name=user_name,
                created_at=datetime.now(),
                last_activity=datetime.now(),
                is_active=False,  # Starts inactive until WebSocket connects
                client_ip=client_ip,
                websocket_state="connecting"
            )

            # Create session handler and store it
            session_handler = StreamingSessionHandler(
                session=session,
                websocket=None  # Will be set when WebSocket connects
            )
            self.sessions[session_id] = session_handler
            self.sessions_by_user[user_id] = session_id

            self.total_sessions_created += 1
            logger.info("Streaming | event=session_created | session=%s | user=%s", session_id, user_name)

            return session

    async def connect_websocket(
        self,
        session_id: str,
        websocket: WebSocket
    ) -> Optional[StreamingSessionHandler]:
        """
        Connect WebSocket to an existing session.

        Args:
            session_id: Session identifier
            websocket: WebSocket connection

        Returns:
            StreamingSessionHandler or None if session not found
        """
        await self.ensure_service_started()

        async with self.session_lock:
            previous = self.sessions.get(session_id)
            # Reserve this attachment before any network await. A second socket
            # must never replace a live handler and orphan its delivery task.
            if previous is None or previous.websocket is not None:
                return None
            handler = StreamingSessionHandler(previous.session, websocket)
            self.sessions[session_id] = handler
        try:
            await asyncio.wait_for(handler.start(), timeout=self.config.get("session_timeout_seconds", 60))
            if self.sessions.get(session_id) is not handler:
                await handler.stop()
                return None
            self._frame_event.set()  # Start the encoder now if this is the first viewer.
            return handler
        except BaseException:
            await self.terminate_session(session_id, expected=handler)
            raise

    async def handle_websocket_session(
        self,
        session_id: str,
        websocket: WebSocket
    ) -> None:
        """
        Handle a complete WebSocket streaming session.

        Args:
            session_id: Session identifier
            websocket: WebSocket connection
        """
        handler = None
        try:
            # Connect WebSocket to session
            handler = await self.connect_websocket(session_id, websocket)
            if not handler:
                await websocket.close(code=4004, reason="Session not found")
                return

            # Handle control messages
            while handler.is_running:
                control = await handler.receive_control()
                if control is None:
                    break  # Connection closed

                await handler.handle_control(control)
                if control.type in ("pause", "resume"):
                    self._frame_event.set()  # The encoder may now be needed, or not.

        except Exception as e:
            logger.error("Streaming | event=websocket_error | session=%s | error=%s", session_id, e)

        finally:
            # Clean up session
            if handler:
                await self.terminate_session(session_id, expected=handler)

    async def stop_session(self, session_id: str, user_id: str) -> bool:
        """
        Stop a streaming session for a specific user.

        Args:
            session_id: Session identifier
            user_id: User identifier (for security check)

        Returns:
            True if session was stopped successfully
        """
        async with self.session_lock:
            handler = self.sessions.get(session_id)
            if handler is None or handler.session.user_id != user_id:
                return False
        return await self.terminate_session(session_id, expected=handler)

    async def terminate_session(self, session_id: str, expected=None) -> bool:
        """Detach atomically; never hold the registry lock across socket I/O."""
        async with self.session_lock:
            handler = self.sessions.get(session_id)
            if handler is None or (expected is not None and handler is not expected):
                return False
            del self.sessions[session_id]
            user_id = handler.session.user_id
            if self.sessions_by_user.get(user_id) == session_id:
                del self.sessions_by_user[user_id]
        task = self._delivery_tasks.pop(session_id, None)
        self._delivery_events.pop(session_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await handler.stop()
        self._frame_event.set()  # Stop the encoder promptly if that was the last viewer.
        return True

    async def _expire_pending_sessions(self):
        """Release capacity held by a browser that never attached, or that has gone silent
        (no ack or keepalive), e.g. a paused tab whose connection died without a close."""
        timeout = self.config.get("session_timeout_seconds", 60)
        now = time.monotonic()
        for session_id, handler in list(self.sessions.items()):
            if handler.websocket is None and handler.session.is_timed_out(timeout):
                await self.terminate_session(session_id, expected=handler)
            elif handler.websocket is not None and now - handler.last_heard > BROWSER_SILENCE_SECONDS:
                logger.info("Streaming | event=browser_silent | session=%s", session_id)
                await self.terminate_session(session_id, expected=handler)

    async def _frame_distribution_loop(self) -> None:
        last_frame = None
        while self.distribution_active:
            try:
                try:
                    async with asyncio.timeout(1):
                        await self._frame_event.wait()
                except asyncio.TimeoutError:
                    pass
                self._frame_event.clear()
                await self._apply_resource_guard()
                await self._update_encoder()
                frame = self.frame_buffer.get_frame_for_streaming(timeout=0)
                if frame is not None and frame is not last_frame:
                    last_frame = frame
                    self._submit_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Streaming frame distribution failed")
                await asyncio.sleep(.1)

    def _submit_frame(self, frame) -> None:
        """Pace camera frames (about 30 fps) to the encoder's rate. Encoding happens only here,
        once for every viewer, and only while the encoder runs (someone watches)."""
        encoder = self._encoder
        if encoder is None:
            return
        interval = 1 / encoder.settings.fps
        now = time.monotonic()
        # A quarter interval of tolerance keeps 15 of 30 camera frames despite arrival jitter.
        if now + interval / 4 < self._next_submit:
            return
        self._next_submit = max(self._next_submit + interval, now)
        encoder.submit(frame.frame, frame.timestamp.timestamp())

    async def _update_encoder(self) -> None:
        """Make the encoder match the viewers: running at the guard's level while anyone is
        watching (connected and visible), stopped otherwise."""
        async with self._encoder_lock:
            watching = any(handler.watching for handler in self.sessions.values())
            wanted = ENCODER_LEVELS[self._encoder_level] if watching else None
            current = self._encoder
            if current is not None and current.settings != wanted:
                self._encoder = None
                await asyncio.to_thread(current.stop)
            if wanted is None or self._encoder is not None or time.monotonic() < self._encoder_retry_at:
                return
            loop = asyncio.get_running_loop()
            encoder = None

            def on_access_unit(unit):
                self._call_on_loop(loop, self._on_access_unit, encoder, unit)

            def on_exit(message):
                self._call_on_loop(loop, self._on_encoder_exit, encoder, message)

            encoder = self._encoder_factory(wanted, on_access_unit, on_exit)
            try:
                await asyncio.to_thread(encoder.start)
            except EncoderUnavailable as exc:
                await asyncio.to_thread(encoder.stop)
                self._encoder_failed(str(exc))
                await self._tell_viewers(str(exc))
                return
            self._encoder = encoder
            self._encoder_error = None
            self._next_submit = 0.0
            for handler in self.sessions.values():
                handler.resync()  # A new encoder's first frame is a keyframe; older frames no longer apply.

    @staticmethod
    def _call_on_loop(loop, callback, *args) -> None:
        try:
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            pass  # The loop has closed (shutdown); nothing to deliver to.

    def _on_access_unit(self, encoder, unit: AccessUnit) -> None:
        """Fan one encoded frame out to every watching viewer (each keeps at most one waiting)."""
        if encoder is not self._encoder:
            return  # Late output from a stopped or crashed encoder.
        for session_id, handler in list(self.sessions.items()):
            if not handler.watching or not handler.offer(unit):
                continue
            event = self._delivery_events.setdefault(session_id, asyncio.Event())
            if session_id not in self._delivery_tasks:
                self._delivery_tasks[session_id] = asyncio.create_task(self._deliver(session_id, handler, event))
            event.set()

    def _on_encoder_exit(self, encoder, message: str) -> None:
        if encoder is not self._encoder:
            return
        self._encoder = None
        # Stop its threads and close the job handle off the loop; the process has already ended.
        asyncio.get_running_loop().run_in_executor(None, encoder.stop)
        self._encoder_failed(f"Live view encoder stopped ({message})")
        asyncio.create_task(self._tell_viewers("Live view stopped unexpectedly and is restarting. Recording is not affected."))
        self._frame_event.set()

    def _encoder_failed(self, error: str) -> None:
        now = time.monotonic()
        while self._encoder_crashes and now - self._encoder_crashes[0] > ENCODER_CRASH_MEMORY_SECONDS:
            self._encoder_crashes.popleft()
        self._encoder_crashes.append(now)
        delay = min(ENCODER_RETRY_MAX_SECONDS, 2 ** (len(self._encoder_crashes) - 1))
        self._encoder_retry_at = now + delay
        self._encoder_error = error
        logger.error("Streaming | event=encoder_failed | retry_in=%ss | error=%s", delay, error)

    async def _tell_viewers(self, message: str) -> None:
        for handler in list(self.sessions.values()):
            if handler.is_running:
                await handler.send_error(message)

    async def _deliver(self, session_id, handler, event):
        try:
            while self.sessions.get(session_id) is handler and handler.is_running:
                await event.wait()
                event.clear()
                # Wait for the browser to acknowledge before sending: a slow link lowers this
                # viewer's frame rate (it skips to the next keyframe) instead of queueing video.
                # Silence for 15 s ends the session.
                await handler.wait_for_window(ACK_TIMEOUT_SECONDS)
                unit = handler.take_pending()
                if unit is None:
                    continue
                async with asyncio.timeout(ACK_TIMEOUT_SECONDS):
                    sent = await handler.send_access_unit(unit)
                if sent:
                    self.total_frames_distributed += 1
                    self.total_bytes_distributed += len(unit.data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Streaming delivery ended | session=%s | error=%s", session_id, exc)
            await self.terminate_session(session_id, expected=handler)

    async def _terminate_all_sessions(self, reason: str) -> None:
        for session_id, handler in list(self.sessions.items()):
            await self.terminate_session(session_id, expected=handler)

    def _sample_cpu(self) -> float:
        """Return a non-blocking CPU percentage sample: RobotControl plus its encoder child."""
        now = time.monotonic()
        if now - self._last_cpu_sample_monotonic < 1:
            return self._last_cpu_percent
        self._last_cpu_sample_monotonic = now
        try:
            cpu_percent = self._process.cpu_percent(interval=None)
        except Exception:
            cpu_percent = psutil.cpu_percent(interval=0.0)
        cpu_percent += self._encoder_cpu()
        self._last_cpu_percent = cpu_percent
        self._cpu_samples.append(cpu_percent)
        return cpu_percent

    def _encoder_cpu(self) -> float:
        """ffmpeg converts and encodes in its own process, which psutil.Process() does not count."""
        pid = self._encoder.pid if self._encoder is not None else None
        if pid is None:
            self._encoder_process = None
            return 0.0
        try:
            if self._encoder_process is None or self._encoder_process.pid != pid:
                self._encoder_process = psutil.Process(pid)
                self._encoder_process.cpu_percent(interval=None)  # first call primes the counter
            return self._encoder_process.cpu_percent(interval=None)
        except psutil.Error:
            self._encoder_process = None
            return 0.0

    async def _degrade_active_sessions(self) -> None:
        """One step down for the shared encoder (lower frame rate and bitrate)."""
        if self._encoder_level < len(ENCODER_LEVELS) - 1:
            self._encoder_level += 1
            logger.warning("Streaming | event=encoder_degraded | level=%s", self._encoder_level)

    async def _recover_active_sessions(self) -> None:
        """Step the encoder back up after CPU has stayed low (before, it never recovered)."""
        if self._encoder_level > 0:
            self._encoder_level -= 1
            logger.info("Streaming | event=encoder_recovered | level=%s", self._encoder_level)

    async def _apply_resource_guard(self) -> None:
        """Lightweight guard that keeps CPU usage within configured thresholds."""
        now = datetime.now()
        if (now - self._last_resource_check).total_seconds() < 1:
            return
        self._last_resource_check = now
        await self._expire_pending_sessions()

        cpu_percent = self._sample_cpu()

        if not self.sessions:
            self._resource_state = "normal"
            self._recording_impact = "none"
            self._consecutive_soft_limit_hits = 0
            self._consecutive_hard_limit_hits = 0
            self._consecutive_calm_samples = 0
            self._cpu_samples.clear()
            return

        soft_limit = self.cpu_soft_limit
        hard_limit = self.cpu_hard_limit

        if cpu_percent >= hard_limit:
            self._consecutive_hard_limit_hits += 1
        else:
            self._consecutive_hard_limit_hits = 0

        if cpu_percent >= soft_limit:
            self._consecutive_soft_limit_hits += 1
        else:
            self._consecutive_soft_limit_hits = 0

        if cpu_percent >= self.cpu_hard_limit:
            if self._consecutive_hard_limit_hits >= 3:
                if self._resource_state != "blocked":
                    logger.warning("Streaming | event=resource_guard_emergency | cpu=%.1f", cpu_percent)
                self._resource_state = "emergency"
                self._recording_impact = "degraded"
                await self._terminate_all_sessions("CPU limit reached")
                return
        elif cpu_percent >= self.cpu_soft_limit:
            if self._consecutive_soft_limit_hits >= 2:
                if self._resource_state != "protected":
                    logger.info("Streaming | event=resource_guard_protected | cpu=%.1f", cpu_percent)
                self._resource_state = "protected"
                self._recording_impact = "minimal"
                await self._degrade_active_sessions()
        else:
            self._resource_state = "normal"
            self._recording_impact = "none"
            self._consecutive_soft_limit_hits = 0
            self._consecutive_hard_limit_hits = 0

        # Thresholds are the summed CPU (psutil) of RobotControl and its encoder, as before: 75 %
        # means three quarters of one core. Recovery needs a sustained calm, well below the soft limit.
        if cpu_percent < CPU_RECOVER_PERCENT:
            self._consecutive_calm_samples += 1
            if self._consecutive_calm_samples >= CPU_RECOVER_SAMPLES:
                self._consecutive_calm_samples = 0
                await self._recover_active_sessions()
        else:
            self._consecutive_calm_samples = 0

    def get_status(self) -> StreamingStatus:
        """
        Get current streaming service status.

        Returns:
            StreamingStatus object
        """
        # Get active sessions
        active_sessions = []
        total_bandwidth = 0.0

        for handler in self.sessions.values():
            active_sessions.append(handler.session)
            total_bandwidth += handler.session.bandwidth_usage_mbps

        cpu_percent = self._sample_cpu()
        uptime = (datetime.now() - self.service_started_at).total_seconds()
        settings = ENCODER_LEVELS[self._encoder_level]

        return StreamingStatus(
            enabled=self.enabled,
            active_sessions=active_sessions,
            max_sessions=self.config["max_concurrent_sessions"],
            total_bandwidth_mbps=total_bandwidth,
            available_bandwidth_mbps=max(0, self.config["total_bandwidth_limit_mbps"] - total_bandwidth),
            resource_usage_percent=cpu_percent,
            recording_impact=self._recording_impact if active_sessions else "none",
            priority_mode=self._resource_state,
            frames_distributed=self.total_frames_distributed,
            bytes_distributed=self.total_bytes_distributed,
            service_uptime_seconds=uptime,
            last_error=self._encoder_error,
            encoder={"running": self._encoder is not None, "level": self._encoder_level,
                     "fps": settings.fps, "bitrate_kbps": settings.bitrate_kbps},
        )

    def get_resource_usage(self) -> Dict[str, Any]:
        """
        Get current resource usage by streaming.

        Returns:
            Dictionary with resource usage information
        """
        status = self.get_status()

        return {
            "active_sessions": len(status.active_sessions),
            "total_bandwidth_mbps": status.total_bandwidth_mbps,
            "resource_usage_percent": status.resource_usage_percent,
            "priority_mode": status.priority_mode,
            "recording_impact": status.recording_impact
        }


# Global instance access
_service_instance: Optional[LiveStreamingService] = None


def get_live_streaming_service() -> LiveStreamingService:
    """
    Get the global live streaming service instance.

    Returns:
        The global LiveStreamingService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = LiveStreamingService()
    return _service_instance
