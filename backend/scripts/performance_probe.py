"""Isolated synthetic streaming comparison: no camera, SQL, SMTP or runtime data.

Run: python -m backend.scripts.performance_probe --seconds 3 --trials 3
     python -m backend.scripts.performance_probe --seconds 6 --trials 1 --rtt 0.3   (a far viewer)
     python -m backend.scripts.performance_probe --seconds 30 --trials 1 --viewers 1 --rtt 0.15 --kbps 500
         --clip <rolling clip> --level0 15:400:d   (a thin link, real frames, a chosen level 0)
Frames are 640x480 at CAMERA_CONFIG capture_fps (the camera's request), encoded by the real H.264 encoder
(build/vendor/ffmpeg, see build_scripts/fetch_ffmpeg.py). CPU seconds include the ffmpeg child.
Without --clip the frame is random noise scrolling sideways: it measures the chain, not the bitrate
(about 60 kB per frame at any setting). --clip loops a real clip's frames instead.
--kbps limits each viewer's link: frames cross it one after another at that rate, then half a round
trip; frames wait for the link as they would in a socket buffer. --level0 fps:kbit/s[:d] replaces
encoder level 0 (d: with LIVE_STREAMING_CONFIG denoise_filter).
latency_ms_median is capture to shown in the simulated browser (no decode or display time).
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

from backend.config import CAMERA_CONFIG, LIVE_STREAMING_CONFIG
from backend.services import live_streaming
from backend.services.h264_encoder import EncoderSettings

from backend.services.live_streaming import LiveStreamingService
from backend.services.streaming_session import FLAG_KEYFRAME, FRAME_HEADER, StreamingSessionHandler
from backend.services.streaming_types import StreamingSession


class Sink:
    """A browser `rtt` seconds away (0: at once) behind a link of `kbps` (None: unlimited): each
    frame crosses the link after the frames before it, is shown half a round trip later and
    acknowledged a full round trip after crossing (see streaming_session.py)."""
    handler = None

    def __init__(self, rtt=0.0, kbps=None):
        self.rtt = rtt
        self.kbps = kbps
        self.link_free = 0.0
        self.shown = []  # (monotonic time, keyframe)
        self.latencies = []  # capture to shown, seconds

    async def send_bytes(self, payload):
        _, sequence, captured, *_ = FRAME_HEADER.unpack_from(payload)
        keyframe = bool(payload[FRAME_HEADER.size - 1] & FLAG_KEYFRAME)
        now = time.monotonic()
        crossing = 0.0
        if self.kbps:
            self.link_free = max(self.link_free, now) + len(payload) * 8 / (self.kbps * 1000)
            crossing = self.link_free - now

        def show():
            self.shown.append((time.monotonic(), keyframe))
            self.latencies.append(time.time() - captured)
        if not self.rtt and not crossing:
            show()
            self.handler.acknowledge(sequence)
            return
        loop = asyncio.get_running_loop()
        loop.call_later(crossing + self.rtt / 2, show)
        loop.call_later(crossing + self.rtt, self.handler.acknowledge, sequence)

    async def send_json(self, message):
        pass

    async def close(self, **kwargs):
        pass


async def trial(seconds, viewers, rtt=0.0, kbps=None, clip_frames=None):
    LiveStreamingService._instance = None
    with patch.object(LiveStreamingService, "_ensure_camera_integration"):
        service = LiveStreamingService()
    service.frame_buffer.clear()
    service.cpu_soft_limit = service.cpu_hard_limit = 10000
    base = np.random.default_rng(42).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    for number in range(viewers):
        session = StreamingSession(str(number), str(number), "probe", datetime.now(), datetime.now(), True)
        sink = Sink(rtt, kbps)
        handler = StreamingSessionHandler(session, sink)
        sink.handler = handler
        handler.is_running = True
        service.sessions[str(number)] = handler
    reads_before = service.frame_buffer.frames_read_streaming
    cpu_start = time.process_time()
    started = time.monotonic()
    await service.start_service()
    ticks, delays, encoder_cpu = 0, [], 0.0
    while time.monotonic() - started < seconds:
        if clip_frames is not None:
            service.frame_buffer.put_frame(clip_frames[ticks % len(clip_frames)])
        else:
            # 120 px/s whatever the camera rate, so rates are compared on the same motion
            service.frame_buffer.put_frame(np.roll(base, round(ticks * 120 / CAMERA_CONFIG["capture_fps"]), axis=1))
        if service._encoder is not None and service._encoder.pid:
            try:
                times = psutil.Process(service._encoder.pid).cpu_times()
                encoder_cpu = times.user + times.system
            except psutil.Error:
                pass
        # Due times, not fixed sleeps: Windows' 15.6 ms timer would otherwise slow the camera.
        due = started + (ticks + 1) / CAMERA_CONFIG["capture_fps"]
        await asyncio.sleep(max(0, due - time.monotonic()))
        delays.append(max(0, time.monotonic() - due))
        ticks += 1
    await asyncio.sleep(rtt)  # the last frames reach the far browser
    shown = [handler.websocket.shown for handler in service.sessions.values()]
    latencies = sorted(value for handler in service.sessions.values() for value in handler.websocket.latencies)
    gaps = [b[0] - a[0] for frames in shown for a, b in zip(frames, frames[1:])]
    sends = sum(h.session.frames_sent for h in service.sessions.values())
    sent_bytes = sum(h.session.bytes_sent for h in service.sessions.values())
    await service.stop_service()
    elapsed = time.monotonic() - started
    memory = psutil.Process().memory_info()
    return {"viewers": viewers, "rtt_seconds": rtt, "link_kbps": kbps, "level0": str(live_streaming.ENCODER_LEVELS[0]),
            "seconds": round(elapsed, 3), "source_frames": ticks,
            "shown_fps_per_viewer": [round(len(frames) / seconds, 1) for frames in shown],
            "kbit_s_per_viewer": round(sent_bytes * 8 / 1000 / seconds / viewers) if viewers else None,
            "latency_ms_median": round(latencies[len(latencies) // 2] * 1000) if latencies else None,
            "longest_gap_ms": round(max(gaps) * 1000) if gaps else None,
            "sent_frames": sends, "bytes_per_frame": round(sent_bytes / sends) if sends else None, "cpu_seconds": round(time.process_time() - cpu_start, 3),
            "encoder_cpu_seconds": round(encoder_cpu, 3),
            "buffer_reads": service.frame_buffer.frames_read_streaming - reads_before,
            "event_loop_delay_p95_ms": round(sorted(delays)[int(len(delays) * .95)] * 1000, 2),
            "working_set_bytes": memory.rss, "private_bytes": getattr(memory, "private", None)}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--rtt", type=float, default=0.0, help="round trip to the simulated browsers, seconds")
    parser.add_argument("--kbps", type=float, help="each viewer's link capacity, kbit/s")
    parser.add_argument("--clip", help="loop this clip's frames instead of scrolling noise")
    parser.add_argument("--level0", help="fps:kbit/s[:d] for encoder level 0")
    parser.add_argument("--viewers", default="0,1,2", help="viewer counts to run")
    args = parser.parse_args()
    clip_frames = None
    if args.clip:
        from backend.scripts.live_view_quality_probe import read_frames
        from backend.services.h264_encoder import find_ffmpeg
        clip_frames = list(read_frames(find_ffmpeg(), args.clip, 0, 450))
    if args.level0:
        fps, kbps, *flags = args.level0.split(":")
        level = EncoderSettings(float(fps), int(kbps), LIVE_STREAMING_CONFIG["denoise_filter"] if flags == ["d"] else "")
        live_streaming.ENCODER_LEVELS = (level,) + live_streaming.ENCODER_LEVELS[1:]
    results = []
    for viewers in map(int, args.viewers.split(",")):
        for _ in range(args.trials):
            results.append(await trial(args.seconds, viewers, args.rtt, args.kbps, clip_frames))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
