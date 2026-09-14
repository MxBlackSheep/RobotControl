import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from backend.services.live_streaming import LiveStreamingService


def test_stream_sessions_release_capacity_on_failure_and_abandonment():
    async def scenario():
        LiveStreamingService._instance = None
        with patch.object(LiveStreamingService, "_ensure_camera_integration"):
            service = LiveStreamingService()
        with patch.object(service, "ensure_service_started", new=AsyncMock()):
            for _ in range(100):
                session = await service.create_session("user", "User", "local")
                service.sessions[session.session_id].session.last_activity = datetime.now() - timedelta(minutes=2)
                await service._expire_pending_sessions()
                assert service.sessions == service.sessions_by_user == {}
            session = await service.create_session("user", "User", "local")
            socket = AsyncMock()
            socket.accept.side_effect = RuntimeError("connection failed")
            try:
                await service.connect_websocket(session.session_id, socket)
            except RuntimeError:
                pass
            assert not service.sessions and not service.sessions_by_user
            socket.close.assert_awaited_once()
    asyncio.run(scenario())


def test_second_socket_cannot_replace_live_session_or_cleanup_it():
    async def scenario():
        LiveStreamingService._instance = None
        with patch.object(LiveStreamingService, "_ensure_camera_integration"):
            service = LiveStreamingService()
        with patch.object(service, "ensure_service_started", new=AsyncMock()):
            session = await service.create_session("user", "User", "local")
            first, second = AsyncMock(), AsyncMock()
            handler = await service.connect_websocket(session.session_id, first)
            await service.handle_websocket_session(session.session_id, second)
            assert service.sessions[session.session_id] is handler
            first.close.assert_not_awaited()
            assert not await service.stop_session(session.session_id, "another-user")
            assert await service.stop_session(session.session_id, "user")
            assert not await service.terminate_session(session.session_id)
            await handler.stop()
            first.close.assert_awaited_once()
    asyncio.run(scenario())
