"""Isolated native capture/writer. Never imports application services or starts SQL.

Preview uses one fixed-size shared slot, not a frame queue. Clip completion uses
a pipe acknowledgement; the parent consumes it even while an operation waits.
Every connection owns fresh IPC resources, so killing a stuck native call cannot
leave a lock used by the next connection permanently acquired.
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from backend.services.camera_devices import enumerate_devices, resolve_device

FRAME_BYTES = 640 * 480 * 3


def capture_worker(options, stop, pixels, frame_lock, counters, events):
    cap = writer = None
    active_path = None
    frame_count = 0
    phase = "capture"
    heartbeat_stop = threading.Event()

    def heartbeat():
        while not heartbeat_stop.wait(1):
            counters[0] = time.monotonic()

    def send(kind, **data):
        events.send({"kind": kind, "generation": options["generation"], **data})

    def finalize():
        nonlocal writer, active_path, frame_count
        if writer is None:
            return
        writer.release()
        writer = None
        if frame_count and active_path.exists():
            final = active_path.with_name(active_path.name.replace(".partial.avi", ".avi"))
            metadata = {"path": str(final), "timestamp": clip_wall.isoformat(),
                        "camera_id": options["camera_id"], "device_identity": options["identity"],
                        "generation": options["generation"], "frame_count": frame_count,
                        "actual_duration": time.monotonic() - clip_start, "fps": target_fps}
            # Publish only after release and metadata are durable. Interrupted
            # clips retain .partial.avi and are never included in archive scans.
            sidecar = final.with_suffix(".json")
            temp = sidecar.with_suffix(".json.tmp")
            temp.write_text(json.dumps(metadata), encoding="utf-8")
            os.replace(temp, sidecar)
            os.replace(active_path, final)
            send("clip", clip=metadata)
            while not events.poll(.1):
                if stop.is_set():
                    return  # durable sidecar lets the parent reconcile this clip
            if events.recv() != "ack":
                raise RuntimeError("Clip acknowledgement failed")
        elif active_path.exists():
            active_path.unlink()
        active_path = None

    threading.Thread(target=heartbeat, name="CameraHeartbeat", daemon=True).start()
    try:
        device = resolve_device(enumerate_devices(), options["identity"])
        if device["id"] != options["camera_id"]:
            raise RuntimeError("Camera mapping changed before connection; refresh and reconnect")
        cap = cv2.VideoCapture(device["id"], cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError("Cannot open selected camera; it may be disconnected or in use")
        if resolve_device(enumerate_devices(), options["identity"])["id"] != device["id"]:
            raise RuntimeError("Camera mapping changed while opening; refresh and reconnect")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        # Keep the existing measured rolling FPS (maximum 7.5), and capture quality.
        calibration_start = time.monotonic()
        calibrated = 0
        target_fps = None
        clip_start = next_write = 0.0
        ready = False
        while not stop.is_set():
            phase = "capture"
            ok, frame = cap.read()
            now = time.monotonic()
            if not ok or frame is None:
                counters[4] += 1
                stop.wait(.1)
                continue
            if frame.shape != (480, 640, 3):
                raise RuntimeError(f"Camera returned unsupported frame shape {frame.shape}; expected 640×480 colour")
            counters[1] = now  # capture freshness independent of preview consumption
            counters[2] += 1
            if frame_lock.acquire(False):
                try:
                    np.frombuffer(pixels, dtype=np.uint8)[:] = frame.reshape(-1)
                    counters[5] = counters[2]
                finally:
                    frame_lock.release()
            if options["recording"]:
                phase = "recording"
                if target_fps is None:
                    calibrated += 1
                    duration = now - calibration_start
                    if calibrated < 60 and duration < 5:
                        continue
                    target_fps = min(7.5, max(1., min(30., calibrated / max(duration, .001))))
                if writer is not None and now - clip_start >= options["clip_seconds"]:
                    finalize()
                if writer is None:
                    clip_start = next_write = time.monotonic()
                    clip_wall = datetime.now()
                    name = f"clip_{clip_wall:%Y%m%d_%H%M%S_%f}_{options['generation']}.partial.avi"
                    active_path = Path(options["folder"]) / name
                    writer = cv2.VideoWriter(str(active_path), cv2.VideoWriter_fourcc(*"MJPG"), target_fps, (640, 480))
                    if not writer.isOpened():
                        raise OSError("Cannot create recording clip; check storage space and permissions")
                    frame_count = 0
                if now >= next_write or frame_count == 0:
                    writer.write(frame)
                    frame_count += 1
                    counters[3] = time.monotonic()
                    while next_write <= now:
                        next_write += 1 / target_fps
            if not ready:
                ready = True
                send("ready")
        finalize()
    except BaseException as exc:
        try:
            send("error", error=str(exc), error_kind=phase)
        except (OSError, EOFError):
            pass
    finally:
        # An exceptional writer path remains explicitly incomplete.
        if writer is not None:
            writer.release()
        if cap is not None:
            cap.release()
        heartbeat_stop.set()
        events.close()
