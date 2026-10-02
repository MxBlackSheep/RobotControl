"""Single-camera process ownership and serialized, manual lifecycle operations."""
import json
import logging
import multiprocessing as mp
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from backend.services.camera_devices import enumerate_devices, resolve_device
from backend.services.camera_worker import FRAME_BYTES, capture_worker
from backend.utils.filesystem import replace_file

logger = logging.getLogger(__name__)


def warn_if_clip_too_fast(clip):
    """The recording rate is measured once at connection; a camera that later slows down (exposure
    priority after the light is switched off) leaves fewer frames than the clip's rate claims, so it
    plays faster than real time. Reported only: recording is unchanged."""
    try:
        delivered = clip["frame_count"] / clip["actual_duration"]
        if delivered < .8 * clip["fps"]:
            logger.warning("Camera delivered %.1f fps, below the recording rate (%.1f fps); this clip plays "
                           "faster than real time | %s", delivered, clip["fps"], clip["path"])
    except (KeyError, TypeError, ZeroDivisionError):
        pass  # incomplete metadata is not this check's concern


class CameraRuntime:
    def __init__(self, folder, clip_seconds, publish, accept_clip):
        self.folder = Path(folder)
        self.clip_seconds = clip_seconds
        self.publish = publish
        self.accept_clip = accept_clip
        self.config_path = self.folder.parent.parent / "config" / "camera_selection.json"
        self.identity = None
        self.selection_error = None
        if self.config_path.exists():
            try:
                self.identity = json.loads(self.config_path.read_text(encoding="utf-8"))["device_identity"]
            except (ValueError, KeyError, OSError) as exc:
                self.selection_error = f"Cannot read saved camera selection: {exc}"
        self.devices = []
        self.process = None
        self.monitor = None
        self.recording_requested = False
        self.camera_id = None
        self.generation = None
        self.ready = False
        self.error = None
        self.error_kind = None
        self.operation = None
        self.operation_revision = 0
        self.lock = threading.RLock()
        self.operation_lock = threading.Lock()
        self.closed = False
        self.started = 0
        self.counters = [0.] * 6
        self.no_frame_seconds = 10
        self.startup_seconds = 20
        self.capture_fps = 15
        self.graceful_stop_seconds = 15
        self.on_recording_started = None

    def refresh(self):
        devices = enumerate_devices()
        with self.lock:
            self.devices = devices
        return devices

    def select(self, identity):
        if self.recording_requested and self.identity is not None:
            raise ValueError("Stop recording before changing the selected camera")
        device = resolve_device(self.refresh(), identity)
        if self.process is not None:
            self._stop()
        self._save_identity(device["device_identity"])

    def _save_identity(self, identity):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"device_identity": identity}), encoding="utf-8")
        replace_file(temp, self.config_path)
        self.identity = identity
        self.selection_error = None

    def connect(self, recording=None, camera_id=None):
        if self.selection_error:
            raise ValueError(self.selection_error)
        if self.process is not None and camera_id is not None and camera_id != self.camera_id:
            raise ValueError("Only one camera can be active. Stop recording and change the selection first.")
        if recording is not None:
            self.recording_requested = recording
        devices = self.refresh()
        if self.identity is None:
            candidate = next((d for d in devices if d["id"] == camera_id), None)
            if not candidate or not candidate.get("device_identity"):
                raise ValueError("No selected camera is available. Refresh cameras and select one.")
            identity = candidate["device_identity"]
        else:
            identity = self.identity
        device = resolve_device(devices, identity)
        if camera_id is not None and self.identity and camera_id != device["id"]:
            raise ValueError("Camera index no longer matches the saved selection; refresh cameras")
        self._stop()
        self.error = self.error_kind = None
        self.ready = False
        self.generation = uuid.uuid4().hex
        self.camera_id = device["id"]
        ctx = mp.get_context("spawn")
        self.stop_event = ctx.Event()
        self.pixels = ctx.RawArray("B", FRAME_BYTES)
        self.frame_lock = ctx.Lock()
        self.counters = ctx.RawArray("d", 6)
        parent, child = ctx.Pipe()
        self.events = parent
        options = {"identity": identity, "camera_id": self.camera_id, "generation": self.generation,
                   "folder": str(self.folder), "clip_seconds": self.clip_seconds,
                   "recording": self.recording_requested, "capture_fps": self.capture_fps}
        self.started = time.monotonic()
        self.process = ctx.Process(target=capture_worker,
            args=(options, self.stop_event, self.pixels, self.frame_lock, self.counters, child),
            name="RobotControlCamera", daemon=True)
        try:
            self.process.start()
        except BaseException:
            parent.close()
            self.process = None
            raise
        finally:
            child.close()
        self.monitor = threading.Thread(target=self._observe, args=(self.process, self.generation, parent),
                                        name="CameraSupervisor", daemon=True)
        self.monitor.start()
        deadline = time.monotonic() + self.startup_seconds
        while not self.ready and not self.error and self.process.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not self.ready:
            self.error = self.error or "Camera did not produce frames and initialize recording within 20 seconds. Reconnect manually."
            raise RuntimeError(self.error)
        if self.identity is None:
            self._save_identity(identity)
        if self.recording_requested and self.on_recording_started:
            self.on_recording_started(self.camera_id)

    def _observe(self, process, generation, events):
        last_sequence = 0
        rate_from = None  # (monotonic, frame count) once ready, until the delivered rate is logged
        try:
            while process.is_alive() or events.poll():
                if events.poll(.03):
                    try:
                        event = events.recv()
                    except EOFError:
                        break
                    if event.get("generation") != self.generation:
                        continue
                    if event["kind"] == "ready":
                        self.ready = True
                        capture = event.get("capture", {})
                        logger.info("Camera capture | generation=%s | format=%s | requested_fps=%s | reported_fps=%s",
                                    generation, capture.get("fourcc"), capture.get("requested_fps"), capture.get("reported_fps"))
                        rate_from = (time.monotonic(), self.counters[2])
                    elif event["kind"] == "error":
                        self.error, self.error_kind = event["error"], event["error_kind"]
                        logger.error("Camera generation %s: %s", generation, self.error)
                    elif event["kind"] == "clip":
                        self.accept_clip(event["clip"])
                        events.send("ack")
                        warn_if_clip_too_fast(event["clip"])
                if generation != self.generation:
                    break
                if rate_from and time.monotonic() - rate_from[0] >= 10:
                    # Drivers may ignore the requested rate, and lower it in the dark.
                    delivered = (self.counters[2] - rate_from[1]) / (time.monotonic() - rate_from[0])
                    logger.info("Camera capture | generation=%s | delivered_fps=%.1f", generation, delivered)
                    rate_from = None
                if self.counters[5] != last_sequence and self.frame_lock.acquire(False):
                    try:
                        frame = np.frombuffer(self.pixels, dtype=np.uint8).reshape(480, 640, 3).copy()
                        last_sequence = self.counters[5]
                    finally:
                        self.frame_lock.release()
                    self.publish(frame)
        except Exception as exc:
            self.error = f"Camera supervision failed: {exc}"
            logger.exception(self.error)
        finally:
            if generation == self.generation:
                self.ready = False
                if not self.stop_event.is_set():
                    self.error = self.error or "Camera worker exited. Reconnect manually."

    def _stop(self):
        process = self.process
        if process is None:
            return
        self.stop_event.set()
        process.join(self.graceful_stop_seconds)
        forced = process.is_alive()
        if forced:
            process.terminate()
            process.join(5)
        if process.is_alive():
            raise RuntimeError("Camera helper could not be stopped; another helper will not be started")
        if self.monitor:
            self.monitor.join(5)
            if self.monitor.is_alive():
                raise RuntimeError("Camera supervisor is still completing work; retry after it finishes")
        self.events.close()
        process.close()
        self.process = self.monitor = None
        self.ready = False
        self.counters = list(self.counters)
        self.pixels = self.frame_lock = None
        self.publish(None)
        if forced:
            logger.warning("Camera helper terminated; its current clip remains incomplete")

    def perform(self, action, identity=None, camera_id=None):
        if action == "refresh":
            return self.refresh()
        if action == "select":
            return self.select(identity)
        if action == "stop":
            self.recording_requested = False
            return self._stop()
        if action == "start":
            if self.ready and self.recording_requested:
                raise ValueError("Selected camera is already recording")
            return self.connect(True, camera_id)
        if action in ("connect", "reconnect"):
            return self.connect(camera_id=camera_id)
        raise ValueError("Unknown camera operation")

    def run(self, action, **kwargs):
        if not self.operation_lock.acquire(False):
            raise ValueError("A camera operation is already in progress")
        try:
            if self.closed:
                raise ValueError("Camera service is shutting down")
            return self.perform(action, **kwargs)
        finally:
            self.operation_lock.release()

    def submit(self, action, **kwargs):
        if not self.operation_lock.acquire(False):
            raise ValueError("A camera operation is already in progress")
        if self.closed:
            self.operation_lock.release()
            raise ValueError("Camera service is shutting down")
        self.operation_revision += 1
        operation = {"id": uuid.uuid4().hex, "revision": self.operation_revision,
                     "action": action, "state": "pending", "error": None}
        self.operation = operation
        def work():
            try:
                self.perform(action, **kwargs)
                operation["state"] = "succeeded"
            except Exception as exc:
                operation.update(state="failed", error=str(exc))
            finally:
                self.operation_lock.release()
        threading.Thread(target=work, name="CameraOperation", daemon=True).start()
        return dict(operation)

    def status(self):
        now = time.monotonic()
        process = self.process
        try:
            alive = process is not None and process.is_alive()
        except ValueError:  # A concurrent completed stop has closed the handle.
            alive = False
        age = now - self.counters[1] if alive and self.counters[1] else None
        state = "connected" if alive and self.ready else "disconnected"
        if alive and not self.ready and not self.error:
            state = "connecting"
        if alive and ((age is not None and age >= self.no_frame_seconds) or
                      (age is None and now - self.started >= self.startup_seconds)):
            state = "no_frames"
        if self.error:
            state = "error"
        if self.operation and self.operation["state"] == "pending" and self.operation["action"] == "reconnect":
            state = "reconnecting"
        recording = "stopped"
        if self.recording_requested:
            recording = "recording" if self.ready and state == "connected" else "starting"
            if state in ("error", "no_frames", "disconnected"):
                recording = "error"
        return {"device_identity": self.identity, "camera_id": self.camera_id, "generation": self.generation,
                "capture_state": state, "recording_state": recording, "recording_requested": self.recording_requested,
                "last_frame_age_seconds": age, "frame_sequence": int(self.counters[2]),
                "last_write_age_seconds": now - self.counters[3] if alive and self.counters[3] else None,
                "heartbeat_age_seconds": now - self.counters[0] if alive and self.counters[0] else None,
                "read_failures": int(self.counters[4]), "error": self.error or self.selection_error,
                "error_kind": self.error_kind, "operation": dict(self.operation) if self.operation else None}

    def shutdown(self):
        with self.operation_lock:
            self.closed = True
            self.recording_requested = False
            self._stop()
