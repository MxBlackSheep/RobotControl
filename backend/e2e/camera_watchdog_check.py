"""Camera picture check: the real CameraRuntime and its spawned worker, fed a scripted picture.

Run: uv run --locked python backend/e2e/camera_watchdog_check.py [--frozen-seconds 4] [--slow-seconds 6]
No camera, SQL Server, robot or ffmpeg; never opens a device. The worker opens `ScriptedCapture`
below through the runtime's `capture_source` option; device enumeration is faked in this process
only. Recording writes MJPEG clips to a temporary folder. Windows are short (the defaults above);
production uses CAMERA_CONFIG frozen_seconds 30, slow_fps 1, slow_seconds 60.
Script: moving, frozen, moving, slow (a changing frame every 2 s), moving, frozen, manual Reconnect.
Evidence: test-output/camera-watchdog-check/results.json.

Failure cases:
- a frozen picture (frames still arriving) or under 1 frame a second keeps showing as connected,
  or is reported before its window or not within it (one sample per second, plus one second);
- capture_state is not no_picture with reason frozen or slow, or recording is not shown as error;
- the state does not clear once the picture moves again or the rate recovers;
- a manual Reconnect keeps the old generation's problem;
- anything reconnects by itself: the generation changes without an operation;
- the WARNING "Camera picture | event=lost" or INFO "Camera picture | event=back" is missing,
  repeated, or lacks the problem, duration, delivered fps, frame sequence or generation.
"""
import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / "test-output/camera-watchdog-check"
SCRIPT_ENV = "CAMERA_WATCHDOG_CHECK_SCRIPT"  # file holding the phase; the spawned worker inherits it
DEVICE = {"id": 0, "name": "Scripted camera", "device_identity": "scripted:camera", "status": "available"}


class ScriptedCapture:
    """VideoCapture-like source reading its phase from the script file: moving, frozen or slow."""

    def __init__(self, options):
        self.script = Path(os.environ[SCRIPT_ENV])
        self.count = 0
        self.phase = "moving"

    def isOpened(self):
        return True

    def set(self, *_):
        return True

    def get(self, *_):
        return 0

    def read(self):
        # An empty read caught mid-write keeps the last phase rather than inventing one.
        self.phase = self.script.read_text(encoding="utf-8").strip() or self.phase
        time.sleep(2 if self.phase == "slow" else 1 / 30)
        if self.phase != "frozen":
            self.count += 1
        return True, np.full((480, 640, 3), 20 + self.count % 200, dtype=np.uint8)

    def release(self):
        pass


class Lines(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.records = []

    def emit(self, record):
        message = record.getMessage()
        if message.startswith("Camera picture"):
            self.records.append((record.levelname, message))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-seconds", type=float, default=4)
    parser.add_argument("--slow-seconds", type=float, default=6)
    args = parser.parse_args()
    from backend.services.camera_runtime import CameraRuntime

    temp = Path(tempfile.mkdtemp(prefix="camera-watchdog-"))
    script = temp / "phase.txt"
    os.environ[SCRIPT_ENV] = str(script)
    clips = temp / "videos" / "rolling"
    clips.mkdir(parents=True)
    lines = Lines()
    logging.getLogger("backend.services.camera_runtime").addHandler(lines)
    logging.getLogger("backend.services.camera_runtime").setLevel(logging.INFO)
    runtime = CameraRuntime(clips, 3600, lambda frame: None, lambda clip: None)
    runtime.capture_source = "backend.e2e.camera_watchdog_check:ScriptedCapture"
    runtime.frozen_seconds, runtime.slow_fps, runtime.slow_seconds = args.frozen_seconds, 1, args.slow_seconds
    results, failures = {"frozen_seconds": args.frozen_seconds, "slow_seconds": args.slow_seconds}, []

    def check(name, ok, detail=""):
        results[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            failures.append(f"{name}: {detail}")

    def phase(name):
        script.write_text(name, encoding="utf-8")

    def watch(seconds, until=None):
        """Polls status every 0.2 s; returns (seconds until `until` held, statuses seen)."""
        start, seen = time.monotonic(), []
        while time.monotonic() - start < seconds:
            status = runtime.status()
            seen.append(status)
            if until and until(status):
                return time.monotonic() - start, seen
            time.sleep(.2)
        return None, seen

    no_picture = lambda reason: lambda s: s["capture_state"] == "no_picture" and s["no_picture_reason"] == reason
    connected = lambda s: s["capture_state"] == "connected"
    try:
        phase("moving")
        with patch("backend.services.camera_runtime.enumerate_devices", return_value=[DEVICE]):
            runtime.run("start", camera_id=0)
            generation = runtime.generation
            _, seen = watch(args.frozen_seconds + 2)
            check("moving picture is connected and recording", all(connected(s) and s["recording_state"] == "recording" for s in seen),
                  sorted({(s["capture_state"], s["recording_state"]) for s in seen}))

            phase("frozen")
            took, _ = watch(args.frozen_seconds + 4, no_picture("frozen"))
            check("frozen detected within its window, not before", took is not None and args.frozen_seconds - 1 <= took <= args.frozen_seconds + 2.5,
                  f"after {took} s")
            status = runtime.status()
            check("frozen shows recording failing", status["recording_state"] == "error", status["recording_state"])
            phase("moving")
            took, _ = watch(4, connected)
            check("frozen clears when the picture moves", took is not None and runtime.status()["no_picture_reason"] is None, f"after {took} s")

            phase("slow")
            # The first slow frame arrives about 2 s after the switch and samples then come every 2 s,
            # so the window holds only slow frames from about slow_seconds + 2 on.
            took, _ = watch(args.slow_seconds + 8, no_picture("slow"))
            check("slow detected within its window, not before", took is not None and args.slow_seconds - 1 <= took <= args.slow_seconds + 5,
                  f"after {took} s")
            phase("moving")
            took, _ = watch(6, connected)
            check("slow clears when the rate recovers", took is not None, f"after {took} s")
            check("nothing reconnected by itself", runtime.generation == generation, f"{generation} -> {runtime.generation}")

            phase("frozen")
            took, _ = watch(args.frozen_seconds + 4, no_picture("frozen"))
            check("frozen detected again", took is not None, f"after {took} s")
            runtime.run("reconnect")
            status = runtime.status()
            check("manual Reconnect clears it under a new generation",
                  status["capture_state"] == "connected" and status["generation"] != generation and status["recording_requested"],
                  f"{status['capture_state']} {status['generation']}")
            phase("moving")
            runtime.run("stop")

        events = [(level, message.split(" | ")[1]) for level, message in lines.records]
        check("log lines: one per start and return", events == [
            ("WARNING", "event=lost"), ("INFO", "event=back"), ("WARNING", "event=lost"), ("INFO", "event=back"),
            ("WARNING", "event=lost")], events)
        lost = [message for level, message in lines.records if level == "WARNING"]
        check("WARNING lines carry problem, duration, fps, sequence, generation",
              len(lost) == 3 and all(all(f in m for f in ("problem=", "for_seconds=", "delivered_fps=", "frame_sequence=", "generation="))
                                     for m in lost) and "problem=frozen" in lost[0] and "problem=slow" in lost[1], lost)
        back = [message for level, message in lines.records if level == "INFO"]
        check("INFO lines say how long the picture was gone", all("gone_seconds=" in m for m in back), back)
        results["log"] = [message for _, message in lines.records]
    except Exception:
        failures.append(traceback.format_exc())
    finally:
        try:
            runtime.shutdown()
        except Exception:
            failures.append(traceback.format_exc())
        shutil.rmtree(temp, ignore_errors=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "results.json").write_text(json.dumps({**results, "failures": failures}, indent=2, default=str), encoding="utf-8")
    print("\n".join(failures) if failures else "camera_watchdog_check: all passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
