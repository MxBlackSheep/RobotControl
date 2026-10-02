"""Live-view encoder settings on a real clip: bitrate, encoder CPU, detail kept, 2× crops.

Run: uv run --locked python -m backend.scripts.live_view_quality_probe --clip <clip .avi/.mp4>
         --still 240:330 --moving 400 [--settings 15:600,15:400:d] [--denoise <filter>] [--darken 4] [--out <folder>]
--still first:end is a stretch of the clip where nothing moves; --moving a frame where the robot moves
(clip frame numbers; frames still..moving+30 are encoded). Each setting (fps:kbit/s, with :d for the
denoise filter: LIVE_STREAMING_CONFIG denoise_filter, or --denoise) encodes the same frames with the
live-view command (h264_encoder.ffmpeg_command, bundled ffmpeg). Clip frames are fed one per frame
at the setting's rate: a 7.5 fps clip at 15 moves twice as fast, a harder case for temporal filters.

Detail kept (%): on the still frames, the decoded image's fine detail (image minus a Gaussian blur,
σ 1.5) projected onto that of the mean of the still source frames. Averaging removes sensor noise,
and noise is uncorrelated with the scene, so reproducing noise does not raise the score but smearing
lowers it. PSNR/SSIM against the noisy source reward reproduced noise; do not use them for this.
Noise left: mean absolute frame-to-frame change of the grey image on the still frames (--noise-box),
which is what flickers on screen and what the encoder spends bits on.
Ghost (previous, next): on the moving frames, the share of the neighbouring source frames left in
the decoded frame where the scene changed by over 30 levels (gripper region, the last --roi). The
decoded frame is fitted as current + wp·(previous − current) + wn·(next − current); averaging two
frames (tmix) reads 0.5, the encoder alone about 0.1.
--darken G simulates 1/G of the light made up by camera gain G, with shot and read noise and a cyan
cast (see darken()); the still reference is then the mean of the darkened still frames.
Crops are of the plate and gripper area in the enclosure camera's view (--roi to change). CPU is the
ffmpeg child's user+system time per frame (best of 3 runs of the frames ×4). This is a development
measurement, not acceptance on the robot PC.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

from backend.config import LIVE_STREAMING_CONFIG
from backend.services.h264_encoder import EncoderSettings, HEIGHT, WIDTH, ffmpeg_command, find_ffmpeg

ROIS = ((180, 270, 500, 350), (280, 350, 600, 450))  # plates; gripper over the deck


def read_frames(ffmpeg, clip, first, count):
    raw = subprocess.run([str(ffmpeg), "-v", "error", "-i", str(clip), "-vf",
                          f"select=between(n\\,{first}\\,{first + count - 1})", "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, HEIGHT, WIDTH, 3)


# Equivalent electrons at 8-bit white, calibrated to the lit robot clip: its temporal noise (σ 12.5
# levels in mid-tones) is taken as about 45 % shot noise, the rest compression and fixed noise.
FULL_WELL = 100
READ_NOISE = .5  # same equivalent electrons
CYAN_CAST = np.array([1.06, 1.04, 0.82], np.float32)  # B, G, R gains in linear light: less red


def darken(frames, gain, seed=7):
    """The same scene with 1/gain of the light, brought back to brightness by the camera's gain.

    Per frame and channel, in linear light (8-bit gamma 2.2 undone): the light becomes 1/gain of the
    lit clip's, in electrons; Poisson shot noise and Gaussian read noise are drawn (new every frame,
    one fixed seed, so every setting sees identical frames); the noise is slightly smoothed (σ 0.6 px)
    as demosaicing correlates neighbours; × gain; white balance shifts toward cyan; gamma; 8 bits.
    Gain amplifies both noises, so relative noise grows about √gain in light areas and faster in
    shadows. A model, not camera output.
    """
    rng = np.random.default_rng(seed)
    out = np.empty_like(frames)
    for index, frame in enumerate(frames):
        electrons = (frame.astype(np.float32) / 255) ** 2.2 * FULL_WELL / gain
        noise = rng.poisson(electrons).astype(np.float32) - electrons
        noise += rng.normal(0, READ_NOISE, frame.shape).astype(np.float32)
        noise = cv2.GaussianBlur(noise, (0, 0), .6)
        linear = np.clip((electrons + noise) * gain / FULL_WELL * CYAN_CAST, 0, 1)
        out[index] = np.round(linear ** (1 / 2.2) * 255).astype(np.uint8)
    return out


def encode(ffmpeg, frames, settings, path):
    """Encode with the live-view command; return ffmpeg's CPU seconds."""
    command = ffmpeg_command(ffmpeg, settings)
    command[command.index("-loglevel") + 1] = "info"
    command[command.index("-nostats"):command.index("-nostats")] = ["-y", "-benchmark"]
    command[-1] = str(path)
    run = subprocess.run(command, input=frames.tobytes(), capture_output=True, check=True)
    times = re.search(rb"utime=([\d.]+)s stime=([\d.]+)s", run.stderr)
    return float(times[1]) + float(times[2])


def decode(ffmpeg, path):
    raw = subprocess.run([str(ffmpeg), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, HEIGHT, WIDTH, 3)


def fine_detail(frame, rois):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64)
    detail = gray - cv2.GaussianBlur(gray, (0, 0), 1.5)
    return np.concatenate([detail[y0:y1, x0:x1].ravel() for x0, y0, x1, y1 in rois])


def gray(frame, box):
    x0, y0, x1, y1 = box
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[y0:y1, x0:x1].astype(np.float64)


def noise_left(frames, box):
    return float(np.mean([np.abs(gray(b, box) - gray(a, box)).mean() for a, b in zip(frames, frames[1:])]))


def ghost(source, decoded, moving, roi):
    rows, residuals = [], []
    for index in range(max(moving, 1), len(source) - 1):
        current, previous, following = (gray(source[i], roi) for i in (index, index - 1, index + 1))
        changed = (np.abs(previous - current) > 30) | (np.abs(following - current) > 30)
        rows.append(np.stack([(previous - current)[changed], (following - current)[changed]], 1))
        residuals.append((gray(decoded[index], roi) - current)[changed])
    if sum(len(r) for r in residuals) < 50:
        return None
    return [round(float(w), 3) for w in np.linalg.lstsq(np.concatenate(rows), np.concatenate(residuals), rcond=None)[0]]


def crop(frame, roi, label):
    x0, y0, x1, y1 = roi
    tile = cv2.resize(frame[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    cv2.rectangle(tile, (0, 0), (tile.shape[1], 22), (0, 0, 0), -1)
    cv2.putText(tile, label, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1, cv2.LINE_AA)
    return tile


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clip", type=Path, required=True)
    parser.add_argument("--still", required=True, help="first:end clip frames where nothing moves")
    parser.add_argument("--moving", type=int, required=True, help="a clip frame where the robot moves")
    parser.add_argument("--settings", default="15:600,15:400:d", help="fps:kbit/s[:d] list; d adds the denoise filter")
    parser.add_argument("--denoise", default=LIVE_STREAMING_CONFIG["denoise_filter"], help="filter for :d settings")
    parser.add_argument("--noise-box", default="100,150,540,450", help="x0,y0,x1,y1 still region for noise left")
    parser.add_argument("--darken", type=float, help="simulate less light with this camera gain")
    parser.add_argument("--roi", action="append", help="x0,y0,x1,y1 crop and score region (repeatable)")
    parser.add_argument("--out", type=Path, default=Path("test-output/live-view-quality"))
    args = parser.parse_args()
    ffmpeg = find_ffmpeg()
    first, end = map(int, args.still.split(":"))
    rois = [tuple(map(int, roi.split(","))) for roi in args.roi] if args.roi else ROIS
    noise_box = tuple(map(int, args.noise_box.split(",")))
    frames = read_frames(ffmpeg, args.clip, first, args.moving - first + 31)
    still = end - first
    if args.darken:
        frames = darken(frames, args.darken)
    reference = fine_detail(np.round(frames[:still].mean(axis=0)).astype(np.uint8), rois)
    args.out.mkdir(parents=True, exist_ok=True)
    name = args.clip.stem + (f"_darken{args.darken:g}" if args.darken else "")
    scored = range(min(30, still // 2), still)  # after the first frames settle
    rows, columns = [], [("source", frames)]
    for item in args.settings.split(","):
        fps, kbps, *flags = item.split(":")
        denoise = args.denoise if flags == ["d"] else ""
        settings = EncoderSettings(float(fps) if "." in fps else int(fps), int(kbps), denoise)
        path = args.out / f"{name}_{fps}fps_{kbps}k{'_denoise' if denoise else ''}.flv"
        encode(ffmpeg, frames, settings, path)
        cpu = min(encode(ffmpeg, np.concatenate([frames] * 4), settings, args.out / "cpu.flv") for _ in range(3))
        decoded = decode(ffmpeg, path)
        if len(decoded) != len(frames):
            raise RuntimeError(f"{item}: {len(decoded)} frames decoded of {len(frames)}")
        rows.append({"settings": item, "kbit_s": round(path.stat().st_size * 8 / 1000 / (len(frames) / settings.fps)),
                     "encoder_cpu_ms_per_frame": round(cpu / (4 * len(frames)) * 1000, 2)})
        columns.append((f"{fps} fps {kbps}k{' denoise' if denoise else ''}", decoded))
    for row, (_, decoded) in zip([{"settings": "source"}] + rows, columns):
        kept = [fine_detail(decoded[i], rois) @ reference / (reference @ reference) for i in scored]
        row["detail_kept_pct"] = round(100 * float(np.mean(kept)), 1)
        row["noise_left"] = round(noise_left(decoded[min(10, still // 2):still], noise_box), 2)
        row["ghost_prev_next"] = ghost(frames, decoded, still, rois[-1])
    (args.out / "cpu.flv").unlink(missing_ok=True)
    sheet = [np.hstack([crop(decoded[index], roi, f"{label} | {when}") for label, decoded in columns])
             for roi in rois for when, index in (("still", still - 5), ("moving", args.moving - first))]
    cv2.imwrite(str(args.out / f"{name}_crops.jpg"), np.vstack(sheet), [cv2.IMWRITE_JPEG_QUALITY, 92])
    (args.out / f"{name}.json").write_text(json.dumps(rows, indent=1))
    print(json.dumps(rows, indent=1))
    print(f"Crops: {args.out / f'{name}_crops.jpg'}")


if __name__ == "__main__":
    main()
