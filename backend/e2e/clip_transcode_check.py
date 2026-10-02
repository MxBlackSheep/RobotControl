"""Rolling clips stored as H.264: the real ffmpeg, CameraService, archive, cleanup and download.

Run: uv run --locked python backend/e2e/clip_transcode_check.py [--clips <folder of real clip_*.avi>]
Needs the bundled ffmpeg (uv run --locked python build_scripts/fetch_ffmpeg.py); no camera, SQL
Server or robot. Clips are disposable MJPEG AVIs written like camera_worker.py writes them (noise,
moving plate, text) in a temporary folder; --clips also copies up to three real clips there and
records their before/after size. Evidence: test-output/clip-transcode-verification/results.json.

Failure cases:
- a verified clip is not replaced: the MP4 is missing, its frame count or frame rate (playback
  speed) differs from the sidecar,
  OpenCV cannot decode it (notification attachments), the AVI or temporary file remains, the
  sidecar path or modification time is wrong, or the clip list still names the AVI;
- ffmpeg is missing, crashes mid-transcode, or yields a different frame count: the AVI is lost,
  a temporary file remains, the failure is not reported in clip_storage, or it raises;
- ffmpeg returns after being missing, but clip_storage still reports it missing;
- RobotControl is killed mid-transcode: ffmpeg outlives it, or the next start keeps the temporary
  file or does not finish the clip;
- two transcodes run at once, or one runs above BelowNormal priority;
- a clip rotated out while its MP4 waits for the lock leaves an orphan MP4;
- a folder holding both formats of one clip (killed between publish and delete, or the AVI held
  open by a download) is listed twice, archived twice or loses the sidecar in cleanup; the AVI is
  not removed once released;
- legacy clips without sidecar and .partial.avi files are touched;
- the download route serves the MP4 with the wrong type.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / "test-output/clip-transcode-verification"

from backend.config import CAMERA_CONFIG  # noqa: E402
from backend.services.h264_encoder import EncoderUnavailable, find_ffmpeg  # noqa: E402

DEVICES = [{"id": 0, "name": "USB camera", "device_identity": "usb:check", "status": "available"}]


def write_clip(folder: Path, stamp: datetime, frames: int, sidecar=True, partial=False, fps=7.5) -> Path:
    """An MJPEG AVI as camera_worker.py writes it, plus its sidecar."""
    name = f"clip_{stamp:%Y%m%d_%H%M%S_%f}_1.{'partial.' if partial else ''}avi"
    path = folder / name
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (640, 480))
    rng = np.random.default_rng(stamp.second)
    for index in range(frames):
        frame = rng.integers(40, 90, (480, 640, 3), dtype=np.uint8)
        x = 40 + (index * 7) % 480
        cv2.rectangle(frame, (x, 200), (x + 120, 280), (230, 230, 230), -1)
        cv2.putText(frame, f"PLATE {index:03d}", (x + 4, 245), cv2.FONT_HERSHEY_SIMPLEX, .6, (20, 20, 20), 2)
        writer.write(frame)
    writer.release()
    if sidecar and not partial:
        path.with_suffix(".json").write_text(json.dumps({
            "path": str(path), "timestamp": stamp.isoformat(), "camera_id": 0, "device_identity": "usb:check",
            "generation": 1, "frame_count": frames, "actual_duration": frames / fps, "fps": fps}), encoding="utf-8")
    return path


def accept(service, path: Path) -> None:
    """What CameraRuntime does when the camera helper reports a finalized clip."""
    service._accept_clip(json.loads(path.with_suffix(".json").read_text(encoding="utf-8")))


def ffmpeg_children():
    return [child for child in psutil.Process().children(recursive=True)
            if child.name().lower() == "ffmpeg.exe"]


def wait_for(condition, seconds=60.0, step=.02):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(step)
    return condition()


def settled(transcoder, done):
    """Wait until transcoded + failed reaches `done` and the worker is idle."""
    return wait_for(lambda: (lambda s: s["state"] in ("idle", "unavailable") and s["transcoded"] + s["failed"] >= done)(
        transcoder.status()), 120)


def frame_rate(path: Path) -> float:
    capture = cv2.VideoCapture(str(path))
    rate = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    return rate


def decoded_frames(path: Path) -> int:
    capture = cv2.VideoCapture(str(path))
    count = 0
    while capture.read()[0]:
        count += 1
    capture.release()
    return count


KILLED_CHILD = """
import sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from backend.services.clip_transcoder import ClipTranscoder
transcoder = ClipTranscoder(Path(sys.argv[1]), threading.Lock(), lambda old, new: None, 1000)
transcoder.wake()
time.sleep(600)
"""


def run(real_clips: Path = None):
    checks, measurements = [], []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail and not ok else ""))

    find_ffmpeg()  # fails early with the fetch command when the bundled encoder is absent
    work = Path(tempfile.mkdtemp(prefix="rc-clip-transcode-"))
    videos = work / "videos"
    rolling = videos / "rolling_clips"
    rolling.mkdir(parents=True)
    service = None
    try:
        from backend.services import clip_transcoder as transcoder_module
        from backend.services.camera import CameraService
        from backend.services.clip_transcoder import TEMPORARY_SUFFIX, finalized_clips
        from backend.services.storage_manager import StorageManager

        with patch("backend.services.camera.VIDEO_PATH", str(videos)), \
                patch("backend.services.camera_runtime.enumerate_devices", return_value=DEVICES):
            CameraService._instance = None
            service = CameraService()
        with patch("backend.services.storage_manager.VIDEO_PATH", str(videos)):
            service._storage_manager = StorageManager()
        transcoder = service.clip_transcoder
        now = datetime.now() - timedelta(minutes=5)

        # Untouchable files, a stale temporary file from a killed run, and a backlog of three clips.
        legacy = rolling / "clip_20260101_120000.avi"
        write_clip(rolling, now, 10, sidecar=False).rename(legacy)
        partial = write_clip(rolling, now + timedelta(seconds=1), 10, partial=True)
        stale = rolling / f"clip_20260101_110000_000000_1{TEMPORARY_SUFFIX}"
        stale.write_bytes(b"left by a killed transcode")
        backlog = [write_clip(rolling, now + timedelta(seconds=10 + i), 60) for i in range(3)]
        mtimes = {path.stem: path.stat().st_mtime for path in backlog}
        service._sync_memory_with_filesystem()

        # One at a time, at BelowNormal, while the backlog runs.
        samples, stop_sampling = [], threading.Event()

        def sample():
            while not stop_sampling.is_set():
                try:
                    samples.append([child.nice() for child in ffmpeg_children()])
                except psutil.Error:
                    pass
                time.sleep(.01)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        newest = write_clip(rolling, now + timedelta(seconds=20), 60, fps=6.4)  # a calibrated, slower camera
        accept(service, newest)
        settled(transcoder, 4)
        stop_sampling.set()
        sampler.join()
        status = transcoder.status()
        seen = [s for s in samples if s]
        check("backlog and new clip transcoded", status["transcoded"] == 4 and status["failed"] == 0, status)
        check("never two ffmpeg transcodes at once", seen and max(len(s) for s in seen) == 1, f"{len(seen)} samples")
        check("ffmpeg runs at BelowNormal", seen and all(n == psutil.BELOW_NORMAL_PRIORITY_CLASS for s in seen for n in s))
        check("stale temporary file removed", not stale.exists())
        check("legacy clip without sidecar and .partial.avi untouched", legacy.exists() and partial.exists())
        for path in backlog + [newest]:
            mp4 = path.with_suffix(".mp4")
            sidecar = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            ok = (mp4.exists() and not path.exists() and decoded_frames(mp4) == sidecar["frame_count"]
                  and sidecar["path"] == str(mp4) and not list(rolling.glob(f"*{TEMPORARY_SUFFIX}")))
            check(f"{path.stem}: MP4 replaces AVI with sidecar frame count, OpenCV decodes it", ok)
        check("MP4 plays at the clip's own frame rate (7.5 and a calibrated 6.4 fps)",
              all(abs(frame_rate(p.with_suffix(".mp4")) - json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))["fps"]) < .05
                  for p in backlog + [newest]), [round(frame_rate(p.with_suffix(".mp4")), 2) for p in backlog + [newest]])
        check("MP4 keeps the AVI's modification time",
              all(abs(path.with_suffix(".mp4").stat().st_mtime - mtimes[path.stem]) < 1 for path in backlog))
        listed = [Path(clip["path"]).name for clip in service.rolling_clips]
        check("clip list names the MP4s once each", sorted(listed) == sorted(p.name for p in finalized_clips(rolling))
              and not any(name.endswith(".avi") and "partial" not in name and name != legacy.name for name in listed), listed)

        # Download route serves the MP4 as video/mp4.
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api import camera as camera_api
        from backend.services.auth import get_current_user
        app = FastAPI()
        app.include_router(camera_api.router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: {"username": "check", "role": "admin", "user_id": "check"}
        with patch.object(camera_api, "ROLLING_CLIPS_PATH", rolling), \
                patch.object(camera_api, "EXPERIMENTS_PATH", videos / "experiments"), TestClient(app) as client:
            response = client.get(f"/api/camera/recording/{newest.with_suffix('.mp4').name}")
        check("download serves video/mp4", response.status_code == 200 and response.headers["content-type"] == "video/mp4",
              response.status_code)

        # ffmpeg missing: AVI kept and reported; nothing raises; a later wake retries.
        missing = write_clip(rolling, now + timedelta(seconds=30), 30)
        with patch.object(transcoder_module, "find_ffmpeg", side_effect=EncoderUnavailable("ffmpeg.exe is missing")):
            accept(service, missing)
            wait_for(lambda: transcoder.status()["state"] == "unavailable", 10)
            status = transcoder.status()
        check("missing ffmpeg keeps the AVI and is reported", missing.exists() and status["state"] == "unavailable"
              and "missing" in (status["last_error"] or ""), status)
        transcoder.wake()
        settled(transcoder, 5)
        status = transcoder.status()
        check("after ffmpeg returns, the waiting clip is transcoded and the missing-ffmpeg error clears",
              missing.with_suffix(".mp4").exists() and not missing.exists() and status["state"] == "idle"
              and status["last_error"] is None, status)

        # Wrong frame count (sidecar says one more than the file holds).
        short = write_clip(rolling, now + timedelta(seconds=40), 30)
        sidecar = json.loads(short.with_suffix(".json").read_text(encoding="utf-8"))
        short.with_suffix(".json").write_text(json.dumps({**sidecar, "frame_count": 31}), encoding="utf-8")
        accept(service, short)
        settled(transcoder, 6)
        status = transcoder.status()
        check("frame count mismatch keeps the AVI and reports it", short.exists() and not short.with_suffix(".mp4").exists()
              and status["failed"] == 1 and "30" in (status["last_error"] or ""), status)
        check("no temporary file after a failed check", not list(rolling.glob(f"*{TEMPORARY_SUFFIX}")))

        # ffmpeg crashes mid-transcode.
        crash = write_clip(rolling, now + timedelta(seconds=50), 451)
        accept(service, crash)
        # Kill once it is encoding (its output exists), not while Windows is still creating it.
        child = wait_for(lambda: list(rolling.glob(f"*{TEMPORARY_SUFFIX}")) and ffmpeg_children(), 30, .005)
        if child:
            child[0].kill()
        settled(transcoder, 7)
        status = transcoder.status()
        check("crashed ffmpeg keeps the AVI and reports it", bool(child) and crash.exists()
              and not crash.with_suffix(".mp4").exists() and status["failed"] == 2, status)
        check("no temporary file after a crash", not list(rolling.glob(f"*{TEMPORARY_SUFFIX}")))
        crash.unlink()
        crash.with_suffix(".json").unlink()
        service._sync_memory_with_filesystem()

        # A clip rotated out while its verified MP4 waits for the clip lock.
        rotated = write_clip(rolling, now + timedelta(seconds=60), 30)
        with service.clips_lock:
            accept_thread = threading.Thread(target=transcoder.wake)
            service.rolling_clips.append({"path": str(rotated), "timestamp": now, "camera_id": 0, "frame_count": 30})
            accept_thread.start()
            waiting = wait_for(lambda: list(rolling.glob(f"*{TEMPORARY_SUFFIX}")) and not ffmpeg_children(), 60)
            rotated.unlink()
            rotated.with_suffix(".json").unlink()
        settled(transcoder, 8)
        check("rotated-out clip leaves no MP4 or temporary file", bool(waiting) and not rotated.with_suffix(".mp4").exists()
              and not list(rolling.glob(f"*{TEMPORARY_SUFFIX}")))
        service._sync_memory_with_filesystem()

        # AVI held open (a download) when the MP4 is published: both kept, one listed; removed later.
        held = write_clip(rolling, now + timedelta(seconds=70), 30)
        handle = open(held, "rb")
        accept(service, held)
        settled(transcoder, 9)
        both = held.exists() and held.with_suffix(".mp4").exists()
        names = [Path(clip["path"]).name for clip in service.rolling_clips]
        service._sync_memory_with_filesystem()
        names_after_sync = [Path(clip["path"]).name for clip in service.rolling_clips]
        check("held AVI: both files kept, the clip listed once as MP4", both and held.name not in names
              and names_after_sync.count(held.with_suffix(".mp4").name) == 1 and held.name not in names_after_sync,
              names_after_sync)
        archive = service._storage_manager.archive_experiment_videos("check", "Check", service.rolling_clips, service.clips_lock)
        archived = sorted(p.name for p in Path(archive.archive_path).iterdir())
        check("archive copies each clip once, MP4s included", archive.success and len(archived) == len(set(
            n.split("_", 2)[2].rsplit(".", 1)[0] for n in archived)) and any(n.endswith(".mp4") for n in archived), archived)
        handle.close()
        transcoder.wake()
        wait_for(lambda: not held.exists(), 30)
        check("released AVI removed on the next pass", not held.exists() and held.with_suffix(".mp4").exists()
              and held.with_suffix(".json").exists())

        # Cleanup with both formats present keeps the sidecar of a kept clip and removes all files of old ones.
        both_old = write_clip(rolling, now - timedelta(minutes=30), 10)
        shutil.copy2(newest.with_suffix(".mp4"), both_old.with_suffix(".mp4"))
        day_ago = time.time() - 86400  # StorageManager removes by modification time
        for old_file in (both_old, both_old.with_suffix(".mp4")):
            os.utime(old_file, (day_ago, day_ago))
        before = len(finalized_clips(rolling))
        result = service._storage_manager.cleanup_rolling_clips(max_clips=before - 1)
        check("storage cleanup removes every file of the oldest clip", not both_old.exists()
              and not both_old.with_suffix(".mp4").exists() and not both_old.with_suffix(".json").exists()
              and len(finalized_clips(rolling)) == before - 1 and result.rolling_clips_removed == 1, result.rolling_clips_removed)
        kept = finalized_clips(rolling)
        check("every kept clip still has its sidecar or is legacy",
              all(p.with_suffix(".json").exists() or p == legacy for p in kept), [p.name for p in kept])
        service.rolling_clips_count = len(kept) - 1
        service._cleanup_orphaned_files()
        check("camera cleanup removes every file of the oldest clip", not legacy.exists() and len(finalized_clips(rolling)) == len(kept) - 1)

        # RobotControl killed mid-transcode: ffmpeg ends with it; the next start finishes the clip.
        killed = write_clip(rolling, now + timedelta(seconds=80), 451)
        child = subprocess.Popen([sys.executable, "-c", KILLED_CHILD, str(rolling), str(ROOT)])
        parent = psutil.Process(child.pid)
        encoder = wait_for(lambda: [c for c in parent.children(recursive=True) if c.name().lower() == "ffmpeg.exe"], 60, .005)
        parent.kill()
        child.wait(10)
        gone = encoder and wait_for(lambda: not psutil.pid_exists(encoder[0].pid), 10)
        check("killed RobotControl takes ffmpeg with it", bool(gone), encoder and encoder[0].pid)
        done = transcoder.status()["transcoded"]
        transcoder.wake()
        settled(transcoder, done + transcoder.status()["failed"] + 1)
        check("next start removes the temporary file and finishes the clip", killed.with_suffix(".mp4").exists()
              and not killed.exists() and not list(rolling.glob(f"*{TEMPORARY_SUFFIX}")))

        # Size and duration for the record.
        for path in [newest, killed]:
            sidecar = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            measurements.append({"clip": "synthetic " + path.stem, "frames": sidecar["frame_count"],
                                 "mp4_bytes": path.with_suffix(".mp4").stat().st_size})
        if real_clips:
            for source in sorted(real_clips.glob("clip_*.avi"))[:3]:
                frames = decoded_frames(source)
                if not frames:
                    continue
                stamp = datetime.now() + timedelta(seconds=len(measurements))
                target = rolling / f"clip_{stamp:%Y%m%d_%H%M%S_%f}_9.avi"
                shutil.copy2(source, target)
                target.with_suffix(".json").write_text(json.dumps({"timestamp": stamp.isoformat(), "camera_id": 0,
                    "frame_count": frames, "actual_duration": frames / 7.5}), encoding="utf-8")
                started, done = time.monotonic(), transcoder.status()["transcoded"]
                transcoder.wake()
                settled(transcoder, done + transcoder.status()["failed"] + 1)
                mp4 = target.with_suffix(".mp4")
                measurements.append({"clip": source.name, "frames": frames, "avi_bytes": source.stat().st_size,
                                     "mp4_bytes": mp4.stat().st_size if mp4.exists() else None,
                                     "ratio": round(source.stat().st_size / mp4.stat().st_size, 1) if mp4.exists() else None,
                                     "seconds_to_store": round(time.monotonic() - started, 2)})
                # Constant bitrate: the MP4 size follows the bitrate, the ratio follows the scene (4.9-6.6x seen).
                limit = CAMERA_CONFIG["clip_h264_kbps"] * 1000 / 8 * frames / 7.5 * 1.15
                check(f"real clip {source.name} stored as H.264 within its bitrate and smaller than the MJPEG",
                      mp4.exists() and mp4.stat().st_size <= min(limit, source.stat().st_size) and decoded_frames(mp4) == frames,
                      mp4.exists() and mp4.stat().st_size)
    except Exception:
        checks.append({"check": "check completed", "passed": False, "detail": traceback.format_exc()})
        print(traceback.format_exc())
    finally:
        if service is not None:
            service.shutdown()
            from backend.services.camera import CameraService
            CameraService._instance = None
        shutil.rmtree(work, ignore_errors=True)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    passed = all(item["passed"] for item in checks)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (EVIDENCE / "results.json").write_text(json.dumps({
        "passed": passed, "commit": commit, "ffmpeg": str(find_ffmpeg()), "when": datetime.now().isoformat(),
        "real_clips": str(real_clips) if real_clips else None, "checks": checks, "measurements": measurements},
        indent=2), encoding="utf-8")
    print(f"{sum(c['passed'] for c in checks)}/{len(checks)} passed; evidence in {EVIDENCE / 'results.json'}")
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", type=Path, help="folder of real clip_*.avi files to copy and measure")
    sys.exit(0 if run(parser.parse_args().clips) else 1)
