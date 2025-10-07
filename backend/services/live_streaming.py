"""
Live streaming service for managing multiple concurrent streaming sessions.
Coordinates with SharedFrameBuffer so streaming can reuse recording frames.
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta
import psutil
from typing import Dict, List, Optional, Any
from fastapi import WebSocket

from backend.services.streaming_types import (
    StreamingSession, StreamingStatus, QualitySettings,
    FrameData
)
from backend.services.streaming_session import StreamingSessionHandler
from backend.services.shared_frame_buffer import get_shared_frame_buffer
from backend.config import LIVE_STREAMING_CONFIG

logger = logging.getLogger(__name__)


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

        self.cpu_soft_limit = self.config.get("cpu_soft_limit_percent", 75)
        self.cpu_hard_limit = self.config.get("cpu_hard_limit_percent", 90)
        self._last_resource_check = datetime.now() - timedelta(seconds=1)
        self._last_cpu_percent = 0.0
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
            if self.distribution_task:
                self.distribution_task.cancel()
                try:
                    await self.distribution_task
                except asyncio.CancelledError:
                    pass

            # Stop all sessions
            await self._terminate_all_sessions("Service shutdown")


            logger.info("Streaming | event=service_stopped")

    async def create_session(
        self,
        user_id: str,
        user_name: str,
        client_ip: str,
        quality: str = "adaptive"
    ) -> Optional[StreamingSession]:
        """
        Create a new streaming session.

        Args:
            user_id: User identifier
            user_name: User display name
            client_ip: Client IP address
            quality: Initial quality setting

        Returns:
            StreamingSession object or None if cannot create
        """
        await self.ensure_service_started()

        async with self.session_lock:
            # Check if service can accept new session
            status = self.get_status()
            if not status.can_accept_new_session():
                logger.warning("Streaming | event=session_rejected | reason=capacity | user=%s", user_id)
                return None

            # Check if user already has a session
            for session_handler in self.sessions.values():
                if session_handler.session.user_id == user_id:
                    logger.warning("Streaming | event=session_rejected | reason=duplicate_user | user=%s", user_id)
                    return None

            # Create new session
            session_id = str(uuid.uuid4())
            session = StreamingSession(
                session_id=session_id,
                user_id=user_id,
                user_name=user_name,
                created_at=datetime.now(),
                last_activity=datetime.now(),
                is_active=False,  # Starts inactive until WebSocket connects
                quality_level=quality,
                client_ip=client_ip,
                websocket_state="connecting"
            )

            # Create session handler and store it
            session_handler = StreamingSessionHandler(
                session=session,
                websocket=None  # Will be set when WebSocket connects
            )
            self.sessions[session_id] = session_handler

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
            # Find the session (created earlier)
            session = None
            for handler in self.sessions.values():
                if handler.session.session_id == session_id:
                    session = handler.session
                    break

            if not session:
                # Create session from ID (for reconnection)
                logger.warning("Streaming | event=websocket_missing | session=%s", session_id)
                return None

            # Create session handler
            quality_settings = QualitySettings.from_config(
                session.quality_level,
                self.config
            )

            handler = StreamingSessionHandler(
                session=session,
                websocket=websocket,
                quality_settings=quality_settings
            )

            # Start the handler
            await handler.start()

            # Replace the existing handler
            self.sessions[session_id] = handler
            session.websocket_state = "connected"
            session.is_active = True

            logger.info("Streaming | event=websocket_connected | session=%s", session_id)

            return handler

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
        
        except Exception as e:
            logger.error("Streaming | event=websocket_error | session=%s | error=%s", session_id, e)
        
        finally:
            # Clean up session
            if handler:
                await handler.stop()
            await self.terminate_session(session_id)
    
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
            if session_id in self.sessions:
                handler = self.sessions[session_id]
                # Security check - ensure user owns the session
                if handler.session.user_id != user_id:
                    logger.warning("Streaming | event=session_stop_denied | session=%s | requester=%s | owner=%s", session_id, user_id, handler.session.user_id)
                    return False
                
                await handler.stop()
                del self.sessions[session_id]
                logger.info("Streaming | event=session_stopped | session=%s | user=%s", session_id, user_id)
                return True
            logger.warning("Streaming | event=session_missing | session=%s | user=%s", session_id, user_id)
            return False
    
    async def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a streaming session (admin/system operation).
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was terminated
        """
        async with self.session_lock:
            if session_id in self.sessions:
                handler = self.sessions[session_id]
                await handler.stop()
                del self.sessions[session_id]
                logger.info("Streaming | event=session_terminated | session=%s", session_id)
                return True
            return False
    
    async def get_active_sessions(self) -> List[StreamingSession]:
        """
        Get list of active streaming sessions.
        
        Returns:
            List of active StreamingSession objects
        """
        async with self.session_lock:
            return [handler.session for handler in self.sessions.values()]
    
    async def toggle_streaming(self, session_id: str, enabled: bool) -> bool:
        """
        Enable or disable streaming for a specific session.
        
        Args:
            session_id: Session identifier
            enabled: True to enable, False to disable
            
        Returns:
            True if toggle was successful
        """
        async with self.session_lock:
            if session_id in self.sessions:
                handler = self.sessions[session_id]
                if enabled:
                    handler.is_paused = False
                    handler.session.is_active = True
                else:
                    handler.is_paused = True
                    handler.session.is_active = False
                logger.info("Streaming | event=session_toggle | session=%s | enabled=%s", session_id, enabled)
                return True
            return False
    
    async def _frame_distribution_loop(self) -> None:
        """
        Main loop for distributing frames to active sessions.
        Runs in a separate task.
        """
        logger.info("Streaming | event=frame_loop_start")
        
        while self.distribution_active:
            try:
                await self._apply_resource_guard()

                # Get frame from buffer
                frame_data = self.frame_buffer.get_frame_for_streaming(timeout=0.033)
                
                if frame_data:
                    # Debug: Log frame retrieval every 600th frame (every 20 seconds at 30fps) when distributing
                    if frame_data.frame_number % 600 == 0:
                        logger.debug(f"Retrieved frame #{frame_data.frame_number} from SharedFrameBuffer for distribution")
                    
                    # Distribute to active sessions
                    await self._distribute_frame(frame_data)
                
                # Small delay to prevent tight loop
                await asyncio.sleep(0.001)
                
            except Exception as e:
                logger.error("Streaming | event=frame_loop_error | error=%s", e)
                await asyncio.sleep(0.1)
        
        logger.info("Streaming | event=frame_loop_stop")
    
    async def _distribute_frame(self, frame_data: FrameData) -> None:
        """
        Distribute a frame to all active sessions.
        
        Args:
            frame_data: Frame to distribute
        """
        # Get active sessions
        async with self.session_lock:
            total_sessions = len(self.sessions)
            active_handlers = [
                handler for handler in self.sessions.values()
                if handler.session.is_active and not handler.is_paused
            ]
            
            # Debug logging every 300 frames (every 10 seconds at 30fps) to track session status
            if frame_data.frame_number % 300 == 0:
                if total_sessions > 0 or len(active_handlers) > 0:
                    # Only log at INFO level when there are active sessions
                    logger.info("Streaming | event=frame_loop_status | sessions=%s | active=%s", total_sessions, len(active_handlers))
                    for session_id, handler in self.sessions.items():
                        logger.debug("Streaming | session=%s | active=%s | paused=%s", session_id[:8], handler.session.is_active, handler.is_paused)
                else:
                    # Log at DEBUG level when no sessions (reduce noise)
                    logger.debug("Streaming | event=frame_loop_status | sessions=%s | active=%s", total_sessions, len(active_handlers))
        
        if not active_handlers:
            return
        
        # Send frame to each session
        tasks = []
        for handler in active_handlers:
            tasks.append(handler.send_frame(frame_data))
        
        # Wait for all sends to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update statistics
        successful_sends = sum(1 for r in results if r is True)
        if successful_sends > 0:
            self.total_frames_distributed += successful_sends
            self.total_bytes_distributed += frame_data.size_bytes * successful_sends
            # Log only every 300 frames (every 10 seconds at 30fps) when actively distributing to sessions
            if frame_data.frame_number % 300 == 0:
                logger.info("Streaming | event=frame_sent | frame=%s | sessions=%s", frame_data.frame_number, successful_sends)
    
    async def _terminate_all_sessions(self, reason: str) -> None:
        """
        Terminate all active sessions.
        
        Args:
            reason: Reason for termination
        """
        async with self.session_lock:
            for session_id, handler in list(self.sessions.items()):
                logger.info("Streaming | event=session_terminated | session=%s | reason=%s", session_id, reason)
                await handler.stop()
            self.sessions.clear()
    
    def _sample_cpu(self) -> float:
        """Return a non-blocking CPU percentage sample."""
        cpu_percent = psutil.cpu_percent(interval=0.0)
        self._last_cpu_percent = cpu_percent
        return cpu_percent

    async def _degrade_active_sessions(self) -> None:
        """Reduce quality on all active sessions to ease resource usage."""
        async with self.session_lock:
            for handler in self.sessions.values():
                handler.degrade_quality()

    async def _apply_resource_guard(self) -> None:
        """Lightweight guard that keeps CPU usage within configured thresholds."""
        now = datetime.now()
        if (now - self._last_resource_check).total_seconds() < 1:
            return
        self._last_resource_check = now

        cpu_percent = self._sample_cpu()

        if not self.sessions:
            self._resource_state = "normal"
            self._recording_impact = "none"
            return

        if cpu_percent >= self.cpu_hard_limit:
            if self._resource_state != "blocked":
                logger.warning("Streaming | event=resource_guard_emergency | cpu=%.1f", cpu_percent)
            self._resource_state = "emergency"
            self._recording_impact = "degraded"
            await self._terminate_all_sessions("CPU limit reached")
            return

        if cpu_percent >= self.cpu_soft_limit:
            if self._resource_state != "protected":
                logger.info("Streaming | event=resource_guard_protected | cpu=%.1f", cpu_percent)
            self._resource_state = "protected"
            self._recording_impact = "minimal"
            await self._degrade_active_sessions()
        else:
            self._resource_state = "normal"
            self._recording_impact = "none"


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
            service_uptime_seconds=uptime
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