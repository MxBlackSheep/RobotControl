"""Isolated synthetic streaming comparison: no camera, SQL, SMTP or runtime data.

Run: python -m backend.scripts.performance_probe --seconds 3 --trials 3
This is a microbenchmark, not real camera/endurance acceptance.
"""
import argparse
import asyncio
from datetime import datetime
import json
import time
from unittest.mock import patch

import numpy as np
import psutil

from backend.services.live_streaming import LiveStreamingService
from backend.services.streaming_session import FRAME_HEADER, StreamingSessionHandler
from backend.services.streaming_types import StreamingSession


class Sink:
    """A fast browser: acknowledges each binary frame at once (see streaming_session.py)."""
    handler = None

    async def send_bytes(self, payload):
        self.handler.acknowledge(FRAME_HEADER.unpack_from(payload)[1])

    async def send_json(self, message):
        pass

    async def close(self, **kwargs):
        pass


async def trial(seconds, viewers):
    LiveStreamingService._instance = None
    with patch.object(LiveStreamingService, "_ensure_camera_integration"):
        service = LiveStreamingService()
    service.frame_buffer.clear()
    service.cpu_soft_limit = service.cpu_hard_limit = 10000
    frame = np.random.default_rng(42).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    for number in range(viewers):
        session = StreamingSession(str(number), str(number), "probe", datetime.now(), datetime.now(), True)
        sink = Sink()
        handler = StreamingSessionHandler(session, sink)
        sink.handler = handler
        handler.is_running = True
        service.sessions[str(number)] = handler
    reads_before = service.frame_buffer.frames_read_streaming
    cpu_start = time.process_time()
    started = time.monotonic()
    await service.start_service()
    ticks, delays = 0, []
    while time.monotonic() - started < seconds:
        before = time.monotonic()
        service.frame_buffer.put_frame(frame)
        await asyncio.sleep(1 / 30)
        delays.append(max(0, time.monotonic() - before - 1 / 30))
        ticks += 1
    sends = sum(h.session.frames_sent for h in service.sessions.values())
    sent_bytes = sum(h.session.bytes_sent for h in service.sessions.values())
    await service.stop_service()
    elapsed = time.monotonic() - started
    memory = psutil.Process().memory_info()
    return {"viewers": viewers, "seconds": round(elapsed, 3), "source_frames": ticks,
            "sent_frames": sends, "bytes_per_frame": round(sent_bytes / sends) if sends else None, "cpu_seconds": round(time.process_time() - cpu_start, 3),
            "buffer_reads": service.frame_buffer.frames_read_streaming - reads_before,
            "event_loop_delay_p95_ms": round(sorted(delays)[int(len(delays) * .95)] * 1000, 2),
            "working_set_bytes": memory.rss, "private_bytes": getattr(memory, "private", None)}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    results = []
    for viewers in (0, 1, 2):
        for _ in range(args.trials):
            results.append(await trial(args.seconds, viewers))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
