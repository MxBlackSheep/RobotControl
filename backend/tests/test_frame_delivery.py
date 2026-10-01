"""Live-view delivery: one shared H.264 encoder, per-viewer keyframe sync and acknowledgements.

Failure cases: an encoder runs with nobody watching or one per viewer; a joining, resuming or
lagging viewer gets a delta frame without the frames it depends on, or frames queue instead of
skipping to the next keyframe; a stalled viewer lowers another's frame rate; an encoder crash is
silent or restarts in a tight loop; the CPU guard stops degrading, recovering or hard-stopping.
The encoder here is a fake (its real process: test_h264_encoder.py).
"""
import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from backend.services.h264_encoder import AccessUnit, EncoderUnavailable
from backend.services.live_streaming import ENCODER_LEVELS, LiveStreamingService
from backend.services.shared_frame_buffer import SharedFrameBuffer
from backend.services.streaming_session import FLAG_KEYFRAME, FRAME_HEADER, FRAME_VERSION, MAX_UNACKNOWLEDGED
from backend.services.streaming_types import StreamControl


class FakeEncoder:
    """Records lifecycle and frames; emit() plays the encoder's reader thread."""
    instances = []

    def __init__(self, settings, on_access_unit, on_exit):
        self.settings, self.on_access_unit, self.on_exit = settings, on_access_unit, on_exit
        self.started = self.stopped = False
        self.frames = []
        self.index = 0
        self.pid = None
        FakeEncoder.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def submit(self, frame, captured_at):
        self.frames.append(frame)

    def emit(self, keyframe):
        """One access unit whose payload is its index, so a test can check continuity."""
        self.index += 1
        self.on_access_unit(AccessUnit(self.index.to_bytes(4, 'big'), keyframe, time.time()))


@pytest.fixture
def service():
    FakeEncoder.instances = []
    LiveStreamingService._instance = None
    with patch.object(LiveStreamingService, '_ensure_camera_integration'), \
         patch('backend.services.live_streaming.find_ffmpeg'):
        service = LiveStreamingService()
        service._encoder_factory = FakeEncoder
        yield service
    LiveStreamingService._instance = None


def received(socket):
    """(index, keyframe) of every binary frame sent to this socket, checking the header."""
    frames = []
    for call in socket.send_bytes.await_args_list:
        version, sequence, _, width, height, flags = FRAME_HEADER.unpack_from(call.args[0])
        assert (version, width, height) == (FRAME_VERSION, 640, 480)
        assert sequence == len(frames) + 1
        frames.append((int.from_bytes(call.args[0][FRAME_HEADER.size:], 'big'), bool(flags & FLAG_KEYFRAME)))
    return frames


def assert_decodable(frames):
    """A viewer starts at a keyframe and every delta directly follows the frame before it."""
    for position, (index, keyframe) in enumerate(frames):
        assert keyframe or (position > 0 and index == frames[position - 1][0] + 1), frames


async def viewer(service, name, acknowledge=True):
    session = await service.create_session(name, name, 'local')
    socket = AsyncMock()
    handler = await service.connect_websocket(session.session_id, socket)
    if acknowledge:  # A fast browser acknowledges each frame as it arrives.
        async def ack(payload):
            handler.acknowledge(FRAME_HEADER.unpack_from(payload)[1])
        socket.send_bytes.side_effect = ack
    return handler, socket


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)
    await asyncio.sleep(.01)


def test_one_encoder_runs_only_while_someone_watches(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()):
            await service._update_encoder()
            pending = await service.create_session('a', 'a', 'local')
            await service._update_encoder()
            assert not FakeEncoder.instances  # a session without a browser is not watching
            a = await service.connect_websocket(pending.session_id, AsyncMock())
            b, _ = await viewer(service, 'b')
            await service._update_encoder()
            assert len(FakeEncoder.instances) == 1 and FakeEncoder.instances[0].started
            await a.handle_control(StreamControl('pause'))
            await service._update_encoder()
            assert not FakeEncoder.instances[0].stopped  # b still watches
            await service.stop_session(b.session.session_id, 'b')
            await service._update_encoder()
            assert FakeEncoder.instances[0].stopped and service._encoder is None  # a is hidden
            await a.handle_control(StreamControl('resume'))
            await service._update_encoder()
            assert len(FakeEncoder.instances) == 2 and service._encoder is FakeEncoder.instances[1]
            await service.terminate_session(a.session.session_id)
            await service._update_encoder()
            assert FakeEncoder.instances[1].stopped and service._encoder is None
    asyncio.run(scenario())


def test_viewers_join_at_a_keyframe_and_then_receive_every_frame(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()):
            first, first_socket = await viewer(service, 'first')
            await service._update_encoder()
            encoder = service._encoder
            for keyframe in (False, False, True, False, False):
                encoder.emit(keyframe)
                await settle()
            second, second_socket = await viewer(service, 'second')
            for keyframe in (False, True, False):
                encoder.emit(keyframe)
                await settle()
            assert [i for i, _ in received(first_socket)] == [3, 4, 5, 6, 7, 8]
            assert [i for i, _ in received(second_socket)] == [7, 8]
            assert_decodable(received(first_socket))
            assert_decodable(received(second_socket))
            await service.terminate_session(first.session.session_id)
            await service.terminate_session(second.session.session_id)
    asyncio.run(scenario())


def test_lagging_viewer_skips_to_the_next_keyframe_and_never_holds_a_fast_one(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()):
            fast, fast_socket = await viewer(service, 'fast')
            slow, slow_socket = await viewer(service, 'slow', acknowledge=False)
            await service._update_encoder()
            encoder = service._encoder
            for number in range(30):  # two one-second GOPs at 15 fps
                encoder.emit(number % 15 == 0)
                await settle()
                if number == 20:  # the slow link catches up once, mid-GOP
                    slow.acknowledge(slow.sent_sequence)
            assert [i for i, _ in received(fast_socket)] == list(range(1, 31))
            slow_frames = received(slow_socket)
            assert_decodable(slow_frames)
            # Two in flight, then one waiting frame (the newer keyframe 16 replaced frame 3); frame 17
            # found that slot taken, so the viewer skips to the next keyframe instead of queueing.
            assert [i for i, _ in slow_frames] == [1, 2, 16]
            for handler in (fast, slow):
                await service.terminate_session(handler.session.session_id)
    asyncio.run(scenario())


def test_unacknowledged_viewer_gets_two_frames_then_its_session_ends(service):
    """A slow tunnel must not queue video; a viewer that stops acknowledging is released."""
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()), \
             patch('backend.services.live_streaming.ACK_TIMEOUT_SECONDS', .3):
            handler, socket = await viewer(service, 'silent', acknowledge=False)
            await service._update_encoder()
            for number in range(10):
                service._encoder.emit(number == 0)
                await settle()
            assert len(received(socket)) == MAX_UNACKNOWLEDGED
            await asyncio.sleep(.5)
            assert handler.session.session_id not in service.sessions
            socket.close.assert_awaited()
    asyncio.run(scenario())


def test_pause_stops_frames_and_resume_restarts_at_a_keyframe(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()):
            handler, socket = await viewer(service, 'tab')
            other, _ = await viewer(service, 'other')  # keeps the encoder running
            await service._update_encoder()
            encoder = service._encoder
            encoder.emit(True)
            await settle()
            await handler.handle_control(StreamControl('pause'))
            for keyframe in (False, False):
                encoder.emit(keyframe)
                await settle()
            assert len(received(socket)) == 1
            await handler.handle_control(StreamControl('resume'))
            for keyframe in (False, True, False):
                encoder.emit(keyframe)
                await settle()
            assert [i for i, _ in received(socket)] == [1, 5, 6]
            assert_decodable(received(socket))
            for each in (handler, other):
                await service.terminate_session(each.session.session_id)
    asyncio.run(scenario())


def test_encoder_crash_is_shown_to_viewers_and_restarts_after_a_delay(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()):
            handler, socket = await viewer(service, 'viewer')
            await service._update_encoder()
            crashed = service._encoder
            crashed.emit(True)
            await settle()
            crashed.on_exit('exit code 3: boom')
            await settle()
            errors = [call.args[0] for call in socket.send_json.await_args_list if call.args[0].get('type') == 'error']
            assert errors and 'restarting' in errors[-1]['error'] and 'Recording is not affected' in errors[-1]['error']
            assert service._encoder is None
            await service._update_encoder()
            assert len(FakeEncoder.instances) == 1  # waits before restarting: no tight loop
            crashed.emit(False)  # late output from the dead child is ignored
            await settle()
            service._encoder_retry_at = 0
            await service._update_encoder()
            restarted = service._encoder
            assert restarted is FakeEncoder.instances[1] and restarted.started
            for keyframe in (False, True, False):
                restarted.emit(keyframe)
                await settle()
            frames = received(socket)
            assert [k for _, k in frames] == [True, True, False]  # rejoined at the new keyframe
            await service.terminate_session(handler.session.session_id)
    asyncio.run(scenario())


def test_missing_encoder_refuses_new_sessions_with_its_reason(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()), \
             patch('backend.services.live_streaming.find_ffmpeg', side_effect=EncoderUnavailable('ffmpeg.exe is missing')):
            with pytest.raises(EncoderUnavailable):
                await service.create_session('viewer', 'viewer', 'local')
            assert not service.sessions
    asyncio.run(scenario())


def test_cpu_guard_steps_the_shared_encoder_down_and_back_and_keeps_the_hard_stop(service):
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()):
            handler, _ = await viewer(service, 'viewer')
            top = len(ENCODER_LEVELS) - 1

            async def samples(values):
                for value in values:
                    service._last_resource_check = datetime(2000, 1, 1)
                    with patch.object(service, '_sample_cpu', return_value=value):
                        await service._apply_resource_guard()
                    await service._update_encoder()
            await samples([20])
            assert service._encoder.settings == ENCODER_LEVELS[0]
            await samples([80] * 12)
            assert service._encoder_level == top and service._encoder.settings == ENCODER_LEVELS[top]
            await samples([60] * 20)  # between the limits: hold, never recover
            assert service._encoder_level == top
            await samples([20] * (10 * top))
            assert service._encoder_level == 0 and service._encoder.settings == ENCODER_LEVELS[0]
            await samples([95, 95])
            assert handler.session.session_id in service.sessions
            await samples([95])  # third consecutive sample at the hard limit
            assert handler.session.session_id not in service.sessions and service._encoder is None
    asyncio.run(scenario())


def test_cpu_sample_includes_the_encoder_process(service):
    service._encoder = MagicMock(pid=4321)
    child = MagicMock()
    child.cpu_percent.return_value = 30.0
    with patch.object(service._process, 'cpu_percent', return_value=10.0), \
         patch('backend.services.live_streaming.psutil.Process', return_value=child) as process:
        service._last_cpu_sample_monotonic = 0
        assert service._sample_cpu() == 40.0
        process.assert_called_once_with(4321)


def test_running_service_paces_frames_to_the_encoder_and_stops_it_on_shutdown(service):
    async def scenario():
        await service.start_service()
        try:
            handler, _ = await viewer(service, 'viewer')
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            started = time.monotonic()
            while time.monotonic() - started < 1:  # a 30 fps camera for one second
                service.frame_buffer.put_frame(frame.copy())
                await asyncio.sleep(1 / 30)
            encoder = service._encoder
            assert encoder is not None and 12 <= len(encoder.frames) <= 17  # paced to 15 fps
        finally:
            await service.stop_service()
        assert encoder.stopped and service._encoder is None
        assert not service._delivery_tasks and not service._delivery_events
        assert not service.frame_buffer._async_readers
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


def test_silent_paused_viewer_is_released_and_a_keepalive_keeps_it(service):
    """A hidden tab sends no acks; only keepalives show it is still there."""
    async def scenario():
        with patch.object(service, 'ensure_service_started', new=AsyncMock()), \
             patch('backend.services.live_streaming.BROWSER_SILENCE_SECONDS', .3):
            handlers = {}
            for name in ('silent', 'alive'):
                session = await service.create_session(name, name, 'local')
                handlers[name] = await service.connect_websocket(session.session_id, AsyncMock())
                await handlers[name].handle_control(StreamControl('pause'))
            for _ in range(4):
                await asyncio.sleep(.12)
                await handlers['alive'].handle_control(StreamControl('keepalive'))
                await service._expire_pending_sessions()
            assert handlers['silent'].session.session_id not in service.sessions
            assert handlers['alive'].session.session_id in service.sessions
            await service.terminate_session(handlers['alive'].session.session_id)
    asyncio.run(scenario())
