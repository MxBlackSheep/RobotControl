import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import threading

import numpy as np

from backend.services.frame_encoder import FrameEncoder
from backend.services.live_streaming import LiveStreamingService
from backend.services.shared_frame_buffer import SharedFrameBuffer
from backend.services.streaming_types import FrameData


def frame(number=1):
    data = np.zeros((24, 32, 3), dtype=np.uint8)
    return FrameData(data, datetime.now(), number, False, data.nbytes)


def test_encoder_shares_quality_and_invalidates_each_source_frame():
    async def scenario():
        encoder = FrameEncoder()
        settings = SimpleNamespace(resolution_scale=1, jpeg_quality=80)
        source = frame()
        first, second = await asyncio.gather(encoder.encode(source, settings), encoder.encode(source, settings))
        assert first == second and encoder.encodes == 1
        await encoder.encode(source, SimpleNamespace(resolution_scale=.5, jpeg_quality=80))
        assert encoder.encodes == 2
        await encoder.encode(frame(2), settings)
        assert encoder.encodes == 3 and len(encoder._cache) == 1
        await encoder.close()
        assert not encoder._cache and not encoder._jobs
    asyncio.run(scenario())


def test_cancelled_viewers_cannot_accumulate_encoding_jobs():
    async def scenario():
        encoder = FrameEncoder(workers=1)
        entered, release = threading.Event(), threading.Event()
        def blocked(*args):
            entered.set()
            assert release.wait(5)
            return 'jpeg'
        with patch('backend.services.frame_encoder.encode_jpeg', blocked):
            task = asyncio.create_task(encoder.encode(frame(), SimpleNamespace(resolution_scale=1, jpeg_quality=80)))
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            for number in range(100):
                retry = asyncio.create_task(encoder.encode(frame(number + 2), SimpleNamespace(resolution_scale=1, jpeg_quality=80)))
                await asyncio.sleep(0)
                retry.cancel()
                await asyncio.gather(retry, return_exceptions=True)
                assert len(encoder._jobs) == 1
            release.set()
            await encoder.close()
    asyncio.run(scenario())


def test_frame_wakeups_are_coalesced_and_unsubscribed():
    async def scenario():
        buffer = SharedFrameBuffer(2)
        event = asyncio.Event()
        buffer.subscribe_frames(asyncio.get_running_loop(), event)
        for _ in range(100):
            buffer.put_frame(np.zeros((4, 4, 3), dtype=np.uint8))
        assert len(buffer.buffer) == 2 and len(buffer._async_readers) == 1
        await asyncio.wait_for(event.wait(), 1)
        buffer.unsubscribe_frames(event)
        assert not buffer._async_readers
    asyncio.run(scenario())


def test_slow_viewer_does_not_hold_other_viewers_or_leave_delivery_tasks():
    async def scenario():
        LiveStreamingService._instance = None
        with patch.object(LiveStreamingService, '_ensure_camera_integration'):
            service = LiveStreamingService()
        await service.start_service()
        try:
            for name in ['slow', 'fast']:
                session = await service.create_session(name, name, 'local')
                socket = AsyncMock()
                handler = await service.connect_websocket(session.session_id, socket)
                if name == 'slow':
                    async def slow_send(*args, **kwargs):
                        await asyncio.sleep(100)
                    socket.send_json.side_effect = slow_send
                else:
                    fast = handler
            for number in range(12):
                await service._distribute_frame(frame(number))
                await asyncio.sleep(.02)
            assert fast.session.frames_sent >= 2
            assert len(service._pending_frames) <= 2
        finally:
            await service.stop_service()
        assert not service._delivery_tasks
        assert not service._pending_frames and not service._delivery_events
        assert not service.frame_buffer._async_readers
    asyncio.run(scenario())
