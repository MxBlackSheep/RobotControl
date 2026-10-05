"""Store finalized rolling clips as H.264 MP4 instead of MJPEG AVI, in the background.

The camera helper keeps writing MJPEG AVI, so recording never depends on ffmpeg. After a clip is
finalized, one ffmpeg child at BelowNormal priority, in a kill-on-close Job Object, encodes it to
a temporary file, denoised unless CAMERA_CONFIG clip_denoise_filter is "". Decoder, filters,
encoder and the verifying decoder get one thread each; FFmpeg still runs these stages side by
side, so a conversion peaks at about 1.5 cores (2.5 with the denoise) for a few seconds. Only when
the file decodes to exactly the sidecar's frame count does it become `<stem>.mp4` (atomic rename)
and the AVI get deleted, under the camera's clip lock, which the experiment archive also holds
while it copies. Any failure leaves the AVI and is reported in status().
Measurements and the brief: docs/plans/h264-rolling-clips.md, clip-transcode-denoise.md.

Invariant: an MP4 exists only after verification, so if both formats of a clip exist (killed
between rename and delete, or the AVI was open), the AVI is redundant and is removed later.
"""
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from backend.services.h264_encoder import EncoderUnavailable, _kill_on_close_job, find_ffmpeg
from backend.utils.filesystem import replace_file

logger = logging.getLogger(__name__)

CLIP_SUFFIXES = (".mp4", ".avi")  # preferred first
# Ends in .tmp, so no clip glob (*.avi, *.mp4) or attachment scan matches it.
TEMPORARY_SUFFIX = ".mp4.tmp"
GOP_FRAMES = 75  # a keyframe every 10 s at 7.5 fps: seeking stays quick, size barely changes
MISSING_ENCODER = "ffmpeg.exe is missing; clips are kept as MJPEG AVI"
CHILD_TIMEOUT_SECONDS = 600  # BelowNormal may wait behind a busy machine; a 1-minute clip takes ~1-3 s
# Before -i: decoder threads and filter-graph threads. By default both start one thread per core;
# the H.264 verifying decoder then bursts over several cores (CPU per clip -17 %, 2026-10-02 probe).
SINGLE_THREADED = ("-threads", "1", "-filter_threads", "1")


class TranscodeFailed(RuntimeError):
    pass


def finalized_clips(folder: Path) -> List[Path]:
    """One path per finalized clip, MP4 preferred, oldest name first; never .partial files."""
    chosen = {}
    for suffix in reversed(CLIP_SUFFIXES):
        for path in folder.glob(f"clip_*{suffix}"):
            if ".partial." not in path.name and path.is_file():
                chosen[path.stem] = path
    return [chosen[stem] for stem in sorted(chosen)]


def clip_files(path: Path) -> List[Path]:
    """Every existing format of this clip (not its sidecar)."""
    return [candidate for candidate in (path.with_suffix(suffix) for suffix in CLIP_SUFFIXES) if candidate.exists()]


def transcode_command(ffmpeg: Path, source: Path, target: Path, bitrate_kbps: int, denoise_filter: str = "") -> list:
    """The conversion of one clip; the denoise filter (CAMERA_CONFIG clip_denoise_filter) runs on the
    encoder's yuv420p planes after the range conversion."""
    # MJPEG is full-range; players expect limited range (lifted blacks otherwise).
    video_filter = "scale=out_range=tv,format=yuv420p" + (f",{denoise_filter}" if denoise_filter else "")
    return [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *SINGLE_THREADED,
            "-i", str(source), "-map", "0:v:0", "-an", "-vf", video_filter, "-color_range", "tv",
            "-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate",
            "-b:v", f"{bitrate_kbps}k", "-g", str(GOP_FRAMES), "-bf", "0", "-threads", "1",
            "-fps_mode", "passthrough", "-movflags", "+faststart", "-f", "mp4", str(target)]


def _frame_count(sidecar: Path) -> Optional[int]:
    try:
        count = json.loads(sidecar.read_text(encoding="utf-8")).get("frame_count")
    except (OSError, ValueError):
        return None
    return count if isinstance(count, int) and count > 0 else None


class ClipTranscoder:
    """One worker thread, started by the first wake(); one ffmpeg child at a time.

    on_replaced(avi, mp4) runs with `lock` held, right after the MP4 is published.
    """

    def __init__(self, folder: Path, lock, on_replaced: Callable[[Path, Path], None], bitrate_kbps: int,
                 denoise_filter: str = ""):
        self.folder = Path(folder)
        self.lock = lock
        self.on_replaced = on_replaced
        self.bitrate_kbps = bitrate_kbps
        self.denoise_filter = denoise_filter
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._failed = set()  # AVIs that failed in this run stay MJPEG until restart
        self._state = "idle"
        self._pending = 0
        self._transcoded = 0
        self._last_error: Optional[str] = None

    def wake(self) -> None:
        with self._thread_lock:
            if self._stopping.is_set():
                return
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="ClipTranscoder", daemon=True)
                self._thread.start()
        self._wake.set()

    def wait_for(self, clips: Iterable[Path], timeout: float) -> bool:
        """Wait until none of these AVIs still waits for conversion. False on timeout."""
        clips = [Path(clip) for clip in clips if Path(clip).suffix == ".avi"]
        self.wake()
        deadline = time.monotonic() + timeout
        while any(clip.exists() and not clip.with_suffix(".mp4").exists() and clip not in self._failed
                  for clip in clips):
            if self._state == "unavailable" or self._stopping.is_set() or time.monotonic() >= deadline:
                return False
            time.sleep(.2)
        return True

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.kill()
        if self._thread is not None:
            self._thread.join(15)

    def status(self) -> dict:
        return {"state": self._state, "pending": self._pending, "transcoded": self._transcoded,
                "failed": len(self._failed), "last_error": self._last_error,
                "format": f"H.264 MP4 {self.bitrate_kbps} kbit/s{', denoised' if self.denoise_filter else ''}"}

    def _run(self) -> None:
        for stale in self.folder.glob(f"*{TEMPORARY_SUFFIX}"):
            stale.unlink(missing_ok=True)  # left by a transcode that RobotControl's exit killed
        while not self._stopping.is_set():
            self._wake.wait()
            self._wake.clear()
            try:
                self._drain()
            except Exception as exc:  # never let one bad pass end clip storage
                logger.exception("Clip storage pass failed")
                self._last_error = str(exc)
            if self._state != "unavailable":
                self._state = "idle"

    def _drain(self) -> None:
        while not self._stopping.is_set():
            waiting = self._waiting()
            self._pending = len(waiting)
            if not waiting:
                return
            try:
                ffmpeg = find_ffmpeg()
            except EncoderUnavailable as exc:
                if self._state != "unavailable":
                    logger.warning("Rolling clips stay MJPEG: %s", exc)
                self._state, self._last_error = "unavailable", MISSING_ENCODER
                return
            if self._last_error == MISSING_ENCODER:
                self._last_error = None  # a condition, not a past failure; per-clip failures stay reported
            self._state = "transcoding"
            self._transcode(ffmpeg, waiting[0])

    def _waiting(self) -> List[Path]:
        """AVIs with a sidecar frame count, newest first. Removes AVIs that already have an MP4."""
        waiting = []
        for avi in sorted(self.folder.glob("clip_*.avi"), reverse=True):
            if ".partial." in avi.name:
                continue
            if avi.with_suffix(".mp4").exists():
                self._remove_redundant(avi)
            elif avi not in self._failed and _frame_count(avi.with_suffix(".json")):
                waiting.append(avi)
        return waiting

    def _remove_redundant(self, avi: Path) -> None:
        with self.lock:
            try:
                avi.unlink(missing_ok=True)
            except OSError as exc:  # open elsewhere (a download); the next pass retries
                logger.debug("Kept %s for now: %s", avi.name, exc)

    def _transcode(self, ffmpeg: Path, avi: Path) -> None:
        temporary = avi.with_name(avi.stem + TEMPORARY_SUFFIX)
        target = avi.with_suffix(".mp4")
        sidecar = avi.with_suffix(".json")
        started = time.monotonic()
        try:
            frames = _frame_count(sidecar)
            self._run_child(transcode_command(ffmpeg, avi, temporary, self.bitrate_kbps, self.denoise_filter))
            decoded = self._decoded_frames(ffmpeg, temporary)
            if decoded != frames:
                raise TranscodeFailed(f"H.264 copy has {decoded} frames, the clip has {frames}")
            with self.lock:
                if not avi.exists():
                    return  # rotated out while encoding; the finally removes the temporary file
                source = avi.stat()
                os.utime(temporary, (source.st_atime, source.st_mtime))  # cleanup and listings sort by it
                # Sidecar first: listings take the path from the folder, so an early sidecar is harmless,
                # whereas a published MP4 the clip list does not know would be missed by an archive.
                self._update_sidecar(sidecar, target)
                replace_file(temporary, target)
                self.on_replaced(avi, target)
            self._transcoded += 1
            logger.info("Rolling clip stored as H.264 | %s | %.1f MB -> %.1f MB | %.1f s", target.name,
                        source.st_size / 2**20, target.stat().st_size / 2**20, time.monotonic() - started)
            self._remove_redundant(avi)
        except (TranscodeFailed, OSError, ValueError) as exc:
            if self._stopping.is_set():
                return  # killed by stop(); the clip is retried after restart
            self._failed.add(avi)
            self._last_error = f"{avi.name}: {exc}"
            logger.warning("Rolling clip kept as MJPEG | %s | %s", avi.name, exc, exc_info=isinstance(exc, OSError))
        finally:
            temporary.unlink(missing_ok=True)

    def _update_sidecar(self, sidecar: Path, target: Path) -> None:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata["path"] = str(target)
        temporary = sidecar.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata), encoding="utf-8")
        replace_file(temporary, sidecar)

    def _decoded_frames(self, ffmpeg: Path, path: Path) -> int:
        """Decode every frame; any decoder error fails the check."""
        output = self._run_child([str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", *SINGLE_THREADED, "-i", str(path),
                                  "-map", "0:v:0", "-f", "null", "-", "-progress", "pipe:1"])
        counts = [line.split("=", 1)[1] for line in output.splitlines() if line.startswith("frame=")]
        return int(counts[-1]) if counts else 0

    def _run_child(self, command: list) -> str:
        flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=flags)
        job = None
        self._process = process
        try:
            if sys.platform == "win32":
                job = _kill_on_close_job(process.pid)
            if self._stopping.is_set():
                process.kill()
            try:
                stdout, stderr = process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise TranscodeFailed(f"ffmpeg took longer than {CHILD_TIMEOUT_SECONDS} s")
        finally:
            self._process = None
            if process.poll() is None:
                process.kill()
                process.wait()
            if job is not None:
                import win32api
                win32api.CloseHandle(job)
        errors = stderr.decode("utf-8", "replace").strip()
        if process.returncode != 0 or errors:
            raise TranscodeFailed(f"ffmpeg exit {process.returncode}: {errors[-300:] or 'no message'}")
        return stdout.decode("utf-8", "replace")
