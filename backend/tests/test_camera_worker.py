"""Native-worker fault tests; no physical camera access."""
import threading
from unittest.mock import Mock, patch

import numpy as np
import pytest

from backend.services.camera_worker import FRAME_BYTES, capture_worker


@pytest.mark.parametrize("recording", [False, True])
def test_worker_finalizes_only_successful_clips(tmp_path, recording):
    stop = threading.Event()
    counters = [0.] * 6
    pixels = bytearray(FRAME_BYTES)
    events = Mock()
    events.poll.return_value = True
    events.recv.return_value = "ack"
    device = {"id": 2, "device_identity": "test"}
    cap = Mock()
    def read():
        if counters[2] >= 65:
            stop.set()
        return True, np.zeros((480, 640, 3), dtype=np.uint8)
    cap.read.side_effect = read
    writer = Mock()
    def open_writer(path, *_args):
        from pathlib import Path
        Path(path).write_bytes(b"encoded clip")
        return writer
    options = {"identity": "test", "camera_id": 2, "generation": "test", "folder": str(tmp_path),
               "clip_seconds": 60, "recording": recording, "capture_fps": 15}
    with patch("backend.services.camera_worker.enumerate_devices", return_value=[device]), \
         patch("backend.services.camera_worker.cv2.VideoCapture", return_value=cap), \
         patch("backend.services.camera_worker.cv2.VideoWriter", side_effect=open_writer):
        capture_worker(options, stop, pixels, threading.Lock(), counters, events)
    messages = [call.args[0] for call in events.send.call_args_list]
    assert any(message["kind"] == "ready" for message in messages)
    assert not any(message["kind"] == "error" for message in messages)
    assert bool(list(tmp_path.glob("*.json"))) == recording
    assert not list(tmp_path.glob("*.partial.avi"))
    assert counters[2] >= 65
    cap.release.assert_called_once()
    if recording:
        writer.release.assert_called_once()
        assert [m for m in messages if m["kind"] == "clip"][0]["clip"]["frame_count"] > 0


def test_failed_open_sends_error_without_ready(tmp_path):
    device = {"id": 0, "device_identity": "test"}
    cap, events = Mock(), Mock()
    cap.isOpened.return_value = False
    with patch("backend.services.camera_worker.enumerate_devices", return_value=[device]), \
         patch("backend.services.camera_worker.cv2.VideoCapture", return_value=cap):
        capture_worker({"identity": "test", "camera_id": 0, "generation": "test"},
                       threading.Event(), bytearray(FRAME_BYTES), threading.Lock(), [0.] * 6, events)
    assert events.send.call_args.args[0]["kind"] == "error"
    cap.release.assert_called_once()
