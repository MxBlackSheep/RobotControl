"""H.264 live-view encoder: one ffmpeg.exe child process whose output every viewer shares.

Raw BGR frames go to ffmpeg's stdin with at most one waiting (a newer frame replaces an unsent
one), so a slow encoder lowers the frame rate instead of buffering video. ffmpeg writes FLV to
stdout because each FLV tag carries its packet's size and keyframe bit: a packet can be passed on
as soon as it is written (about 2 ms after its frame), whereas raw H.264 only reveals the end of
a frame when the next one starts. Packets are converted back to Annex-B for the browser's
WebCodecs decoder.

The child is assigned to a Windows Job Object that kills it when its last handle closes, which
includes RobotControl being killed, so the encoder cannot outlive the server. Its crash affects
only live view: it never touches the camera helper, recording or Hamilton.
"""
import logging
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

# camera_runtime.py publishes fixed 640×480 BGR frames.
WIDTH, HEIGHT = 640, 480
START_CODE = b"\x00\x00\x00\x01"
NAL_SPS = 7


class EncoderUnavailable(RuntimeError):
    """ffmpeg.exe is missing or cannot start."""


@dataclass(frozen=True)
class EncoderSettings:
    fps: float
    bitrate_kbps: int
    denoise: str = ""  # ffmpeg video filter run before encoding; "" for none (LIVE_STREAMING_CONFIG)
    keyframe_seconds: float = 1  # LIVE_STREAMING_CONFIG keyframe_seconds

    @property
    def gop(self) -> int:
        """Frames from one keyframe to the next (int(7.5) = 7: never longer than keyframe_seconds)."""
        return max(1, int(self.fps * self.keyframe_seconds))


@dataclass(frozen=True)
class AccessUnit:
    """One encoded frame in Annex-B form; a delta frame needs every frame since the last keyframe."""
    data: bytes
    keyframe: bool
    captured_at: float  # Unix seconds of the camera frame
    width: int = WIDTH
    height: int = HEIGHT


def find_ffmpeg() -> Path:
    """ffmpeg.exe beside RobotControl.exe when packaged, else build/vendor (build_scripts/fetch_ffmpeg.py)."""
    if getattr(sys, "frozen", False):
        path = Path(sys.executable).parent / "ffmpeg.exe"
        remedy = "Reinstall RobotControl"
    else:
        path = Path(__file__).resolve().parents[2] / "build" / "vendor" / "ffmpeg" / "ffmpeg.exe"
        remedy = "Run: uv run --locked python build_scripts/fetch_ffmpeg.py"
    if not path.is_file():
        raise EncoderUnavailable(f"Live view is unavailable: the video encoder (ffmpeg.exe) is missing. {remedy}.")
    return path


def ffmpeg_command(ffmpeg: Path, settings: EncoderSettings) -> list:
    """Constrained Baseline (no B-frames), a keyframe at least every keyframe_seconds, so a viewer
    can join within that time.

    A denoise filter runs on the encoder's own yuv420p planes, on one thread like the encoder.
    """
    video_filter = ["-filter_threads", "1", "-vf", f"format=yuv420p,{settings.denoise}"] if settings.denoise else []
    return [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostats",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{WIDTH}x{HEIGHT}", "-framerate", str(settings.fps),
            "-thread_queue_size", "2", "-i", "pipe:0", "-an", *video_filter,
            "-c:v", "libopenh264", "-profile:v", "constrained_baseline", "-rc_mode", "bitrate",
            "-b:v", f"{settings.bitrate_kbps}k", "-g", str(settings.gop), "-bf", "0", "-slices", "1",
            "-threads", "1", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
            "-flush_packets", "1", "-flvflags", "no_duration_filesize", "-f", "flv", "pipe:1"]


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return data


def read_flv_packets(stream: BinaryIO) -> Iterator[Tuple[bool, bytes]]:
    """Yield (keyframe, Annex-B access unit) for each H.264 packet in an FLV stream until EOF.

    Keyframes carry SPS/PPS, so a viewer can start decoding at any keyframe.
    """
    try:
        _read_exact(stream, 9 + 4)  # FLV header, PreviousTagSize0
        parameter_sets, length_size = b"", 4
        while True:
            head = _read_exact(stream, 11)
            data = _read_exact(stream, int.from_bytes(head[1:4], "big"))
            _read_exact(stream, 4)  # PreviousTagSize
            if head[0] != 9 or len(data) < 5 or data[0] & 0x0F != 7:
                continue  # script data, or not AVC video
            keyframe, packet_type, payload = data[0] >> 4 == 1, data[1], data[5:]
            if packet_type == 0:  # AVCDecoderConfigurationRecord
                length_size = (payload[4] & 3) + 1
                parameter_sets, offset = b"", 5
                for _ in range(2):  # SPS list, then PPS list
                    count, offset = payload[offset] & 0x1F, offset + 1
                    for _ in range(count):
                        size = int.from_bytes(payload[offset:offset + 2], "big")
                        parameter_sets += START_CODE + payload[offset + 2:offset + 2 + size]
                        offset += 2 + size
            elif packet_type == 1:
                units, offset, has_sps = [], 0, False
                while offset + length_size <= len(payload):
                    size = int.from_bytes(payload[offset:offset + length_size], "big")
                    unit = payload[offset + length_size:offset + length_size + size]
                    has_sps = has_sps or (bool(unit) and unit[0] & 0x1F == NAL_SPS)
                    units.append(START_CODE + unit)
                    offset += length_size + size
                if keyframe and not has_sps:
                    units.insert(0, parameter_sets)
                yield keyframe, b"".join(units)
    except EOFError:
        return


def _kill_on_close_job(pid: int):
    """Put the child in a Job Object that the OS ends when RobotControl's handle closes."""
    import win32api
    import win32con
    import win32job
    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
    process = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid)
    try:
        win32job.AssignProcessToJobObject(job, process)
    finally:
        win32api.CloseHandle(process)
    return job


class H264Encoder:
    """One ffmpeg child. Callbacks run on its reader thread; the owner moves them to its loop.

    on_access_unit(AccessUnit) for each encoded frame; on_exit(message) once if the child ends
    without stop(). start() and stop() block briefly: call them off the event loop.
    """

    def __init__(self, settings: EncoderSettings, on_access_unit: Callable[[AccessUnit], None],
                 on_exit: Callable[[str], None], ffmpeg: Optional[Path] = None):
        self.settings = settings
        self._ffmpeg = ffmpeg
        self._on_access_unit = on_access_unit
        self._on_exit = on_exit
        self._process: Optional[subprocess.Popen] = None
        self._job = None
        self._threads = []
        self._waiting = None  # (frame, captured_at): at most one frame waits for the pipe
        self._condition = threading.Condition()
        self._stopping = False
        # Capture times of frames written but not yet encoded (one packet per frame, in order).
        self._captured = deque(maxlen=32)
        self._stderr = deque(maxlen=10)

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None

    def start(self) -> None:
        ffmpeg = self._ffmpeg or find_ffmpeg()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(ffmpeg_command(ffmpeg, self.settings), stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, creationflags=flags)
        except OSError as exc:
            raise EncoderUnavailable(f"Live view is unavailable: the video encoder could not start ({exc}).") from exc
        try:
            if sys.platform == "win32":
                self._job = _kill_on_close_job(self._process.pid)
        except Exception:
            self._process.kill()
            self._process.wait()
            raise
        for target, name in ((self._write, "H264Writer"), (self._read, "H264Reader"), (self._drain_errors, "H264Errors")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        logger.info("Live view encoder started | pid=%s | fps=%s | kbps=%s | denoise=%s", self.pid, self.settings.fps,
                    self.settings.bitrate_kbps, "on" if self.settings.denoise else "off")

    def submit(self, frame, captured_at: float) -> None:
        """Offer a BGR frame; it replaces a frame still waiting for the pipe."""
        if getattr(frame, "shape", None) != (HEIGHT, WIDTH, 3):
            return  # A raw stream of another size would misalign every later frame.
        with self._condition:
            self._waiting = (frame, captured_at)
            self._condition.notify()

    def stop(self) -> None:
        """End the child and wait for it and its threads. Idempotent.

        Terminates instead of closing stdin: closing a pipe while the writer is blocked in it can
        hang on Windows, and unsent live-view frames have no value.
        """
        with self._condition:
            self._stopping = True
            self._waiting = None
            self._condition.notify()
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        process.wait(5)
        if self._job is not None:
            import win32api
            win32api.CloseHandle(self._job)
            self._job = None
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()
        logger.info("Live view encoder stopped | pid=%s", process.pid)

    def _write(self) -> None:
        stdin = self._process.stdin
        while True:
            with self._condition:
                while self._waiting is None and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                frame, captured_at = self._waiting
                self._waiting = None
            self._captured.append(captured_at)
            try:
                stdin.write(frame.tobytes())
            except (OSError, ValueError):
                return  # The reader reports the exit.

    def _read(self) -> None:
        for keyframe, data in read_flv_packets(self._process.stdout):
            captured_at = self._captured.popleft() if self._captured else time.time()
            self._on_access_unit(AccessUnit(data, keyframe, captured_at))
        try:
            code = self._process.wait(5)
        except subprocess.TimeoutExpired:
            code = None
        with self._condition:
            stopping = self._stopping
        if not stopping:
            detail = " | ".join(self._stderr) or "no error output"
            logger.error("Live view encoder exited | pid=%s | exit=%s | %s", self._process.pid, code, detail)
            self._on_exit(f"exit code {code}: {detail}")

    def _drain_errors(self) -> None:
        # Always drained, so a chatty child can never block on a full stderr pipe.
        for line in iter(self._process.stderr.readline, b""):
            self._stderr.append(line.decode("utf-8", "replace").strip())
