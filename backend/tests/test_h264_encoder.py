"""The real ffmpeg encoder child (needs build/vendor/ffmpeg: build_scripts/fetch_ffmpeg.py).

Failure cases: keyframes are not one second apart, or a stream joined at a later keyframe does
not decode; the child survives stop(), or survives RobotControl being killed (orphan); a crash is
not reported, or stop() is reported as a crash; a missing ffmpeg.exe fails without its reason;
frames offered faster than ffmpeg reads them queue up instead of replacing the one waiting.
"""
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import psutil
import pytest

from backend.services.h264_encoder import (AccessUnit, EncoderSettings, EncoderUnavailable, H264Encoder,
                                           HEIGHT, WIDTH, find_ffmpeg)

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = EncoderSettings(fps=15, bitrate_kbps=400)


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(.05)
    return condition()


def encode(frames):
    units, exits = [], []
    encoder = H264Encoder(SETTINGS, units.append, exits.append)
    encoder.start()
    base = np.random.default_rng(1).integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    try:
        for number in range(frames):
            encoder.submit(np.roll(base, number * 4, axis=1).copy(), time.time())
            assert wait_until(lambda: len(units) > number, 2), f'frame {number} was not encoded'
    finally:
        encoder.stop()
    return encoder, units, exits


def decoded_frames(stream: bytes) -> int:
    result = subprocess.run([str(find_ffmpeg()), '-hide_banner', '-loglevel', 'error', '-f', 'h264', '-i', 'pipe:0',
                             '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1'], input=stream, capture_output=True, timeout=30)
    assert result.returncode == 0 and not result.stderr, result.stderr
    return len(result.stdout) // (WIDTH * HEIGHT)


def test_keyframes_each_second_and_a_stream_joined_at_a_keyframe_decodes():
    encoder, units, exits = encode(31)
    assert [number for number, unit in enumerate(units) if unit.keyframe] == [0, 15, 30]
    assert all(isinstance(unit, AccessUnit) and unit.data.startswith(b'\x00\x00\x00\x01') for unit in units)
    assert units[15].data[4] & 0x1F == 7  # a keyframe starts with its SPS
    assert decoded_frames(b''.join(unit.data for unit in units[15:])) == 16  # a viewer joining at 15
    assert not psutil.pid_exists(encoder.pid) and not exits  # stop() is not a crash


def test_crash_is_reported_once_and_ends_the_child():
    exits = []
    encoder = H264Encoder(SETTINGS, lambda unit: None, exits.append)
    encoder.start()
    psutil.Process(encoder.pid).kill()
    assert wait_until(lambda: exits)
    encoder.stop()
    assert len(exits) == 1 and exits[0].startswith('exit code')


def test_child_does_not_outlive_a_killed_robotcontrol():
    """The Job Object ends ffmpeg when its parent dies without any cleanup, even if ffmpeg is hung.

    A running ffmpeg also exits at stdin EOF when its parent dies; suspending it models an encoder
    stuck where it no longer reads, which only the Job Object ends.
    """
    script = textwrap.dedent('''
        import sys, time
        sys.path.insert(0, sys.argv[1])
        from backend.services.h264_encoder import EncoderSettings, H264Encoder
        encoder = H264Encoder(EncoderSettings(15, 400), lambda unit: None, lambda message: None)
        encoder.start()
        print(encoder.pid, flush=True)
        time.sleep(60)
    ''')
    parent = subprocess.Popen([sys.executable, '-c', script, str(ROOT)], stdout=subprocess.PIPE, text=True)
    try:
        child = int(parent.stdout.readline())
        psutil.Process(child).suspend()
        parent.kill()  # TerminateProcess: no finally blocks, no atexit
        parent.wait(5)
        assert wait_until(lambda: not psutil.pid_exists(child)), 'ffmpeg outlived its parent'
    finally:
        parent.kill()
        parent.stdout.close()


def test_missing_ffmpeg_gives_its_reason():
    encoder = H264Encoder(SETTINGS, lambda unit: None, lambda message: None, ffmpeg=ROOT / 'missing' / 'ffmpeg.exe')
    with pytest.raises(EncoderUnavailable, match='could not start'):
        encoder.start()
    encoder.stop()


def test_frames_of_another_size_are_refused():
    units = []
    encoder = H264Encoder(SETTINGS, units.append, lambda message: None)
    encoder.start()
    try:
        encoder.submit(np.zeros((24, 32, 3), dtype=np.uint8), time.time())
        time.sleep(.5)
        assert not units
    finally:
        encoder.stop()


def test_frames_offered_faster_than_the_pipe_takes_them_are_replaced_not_queued():
    units = []
    encoder = H264Encoder(SETTINGS, units.append, lambda message: None)
    encoder.start()
    try:
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        for _ in range(200):  # far faster than 15 fps: each replaces the one still waiting
            encoder.submit(frame, time.time())
        time.sleep(1)
        assert 1 <= len(units) < 20, len(units)
    finally:
        encoder.stop()
