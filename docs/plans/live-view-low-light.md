# Live view in low light: measurements and decision (2026-10-02)

The owner (production Intel N100, 4 cores, USB camera in the Hamilton enclosure) reported that live
view is "a bit blurry, especially when the outer light is turned off": cyan-tinted, noisy, smeared
plate barcodes and labware, shown about 3× enlarged. They asked for better image quality without
much more CPU or bandwidth. At the time, Task Manager showed the camera helper at 14.6 % of the
machine (≈58 % of one core) and the main process at 5.2 %.

## What the code did

- `camera_worker.py` asked the camera for 640×480 at **30 fps** and decoded every frame, but live view
  encoded at most 15 fps and recording kept at most 7.5: half of the helper's capture work was
  thrown away. The negotiated format (MJPG or YUY2) was never set or logged.
- Live view (level 0) was libopenh264 Constrained Baseline, 15 fps at **400 kbit/s**, ≈3.3 kB per
  frame. In low light the camera raises gain; sensor noise uses up the bits and detail smears.
- In the dark a camera's auto-exposure cannot expose longer than one frame: 1/30 s at 30 fps,
  1/15 s at 15 fps. A 15 fps request lets it gather twice the light before adding gain (if its
  driver extends exposure; not every one does).

## Measured on real footage (development PC, no camera attached)

Footage: real robot clips (`clip_20260608_*`, 640×480 MJPEG, 7.5 fps). Cases:
- **lit**: `123612`, frames 90–209 still, then the gripper moves.
- **real dim**: `122511` (12:25, luma ≈50 against ≈140 lit; only the deck lighting is on). Inferred
  to be the outer light off; not confirmed. Here the camera did not raise gain (dark, not noisy).
- **synthetic dark** (the owner's case: gain raised, noisy): the lit segment ÷ 4, sensor noise
  σ 2.5, 8-bit rounding, × 4 ("gain ×4", as at 30 fps); and the same with ÷/× 2 ("gain ×2", what a
  15 fps exposure would need if the driver doubles the exposure). Synthetic, not camera output.

Every setting encodes the same frames with the production command. "Detail kept" is the decoded
image's fine detail projected onto that of the noise-free still scene (mean of the still frames).
Reproduced noise does not raise it; smearing lowers it. PSNR/SSIM against the noisy source fell as
bitrate rose (more bits reproduce more noise), so they were not used to choose
(`backend/scripts/live_view_quality_probe.py`, header).

| Detail kept, % (still frames) | 15 fps 400k (before) | 15 fps 600k (after) | 10 fps 600k | 10 fps 500k | 15 fps 600k + atadenoise |
| --- | --- | --- | --- | --- | --- |
| real dim | 94.2 | 95.7 | 96.7 | 96.2 | 95.8 |
| lit | 88.0 | 89.9 | 91.5 | 90.8 | 90.3 |
| synthetic dark, gain ×4 | 86.0 | 88.0 | 89.1 | 88.7 | 88.1 |
| synthetic dark, gain ×2 | 87.3 | 89.5 | 90.6 | 90.0 | 89.6 |

- **Bits per frame** help most on moving parts. In 2× crops, the gripper's three fingers stay
  separate while it moves at 600k (a single smear at 400k), and the second plate's well rows survive
  in the synthetic dark still frame. Halving gain gains about as much again (×4 → ×2 rows).
- **10 fps** scores best per frame, but 10 does not divide a 15 fps capture (frames 67/133 ms
  apart, a judder), and keeping 30 fps capture to allow it would forgo the capture saving.
- **Temporal denoise**: the bundled LGPL ffmpeg has no `hqdn3d` (GPL). `atadenoise` (s=5) added
  0.1 point for extra filter CPU; `tmedian` holds back frames. libopenh264 already discards most
  noise at these rates. Not used.
- **Resolution** was not changed (fixed 640×480 slot, recording, transcoder, ≈3× CPU). The
  softness of 640×480 enlarged 3× in the browser remains; this change does not remove it.

## Decision

- Capture at **15 fps** (`camera_worker.CAPTURE_FPS`). The helper decodes and copies half as many
  frames; the parent copies half as many. Recording still measures its rate at connection and
  keeps at most 7.5 (every second frame). The format the driver negotiated and the rate actually
  delivered are logged (`Camera capture | …`) because a driver may ignore the request.
- Live view levels **15 fps/600k, 7.5/300, 5/200** (`config.py`). Each divides 15, so frames stay
  evenly spaced; the GOP is `int(fps)` frames (at most one second; 7 at 7.5 fps), so joining and
  keyframe recovery stay within a second. Level 0 bandwidth: **+50 %** (measured 594–661 kbit/s
  per viewer against 400–439 before, depending on the scene). Degraded levels measured 430 and
  338 kbit/s (at low rates a keyframe each second sets a floor; the old 10/300 and 5/200 measured
  355 and 338).
- Pacing (`_submit_frame`, ¼-interval tolerance) is unchanged. The camera supervisor notices new
  frames on a ≈31 ms poll; a simulation of that arrival pattern kept 15.00 of 15 fps (gaps 61–97 ms),
  and 7.5 and 5 from 15 at their rates (`test-output/live-view-quality/pacing_sim.py`).

## CPU

Sustained 60 s emulation (live chain with one viewer and the real encoder; a stand-in helper that
decodes real MJPEG frames at the capture rate, copies them to the slot and writes the 7.5 fps clip),
5 interleaved pairs, median % of one core on the development PC:

| | helper stand-in | main | ffmpeg | total |
| --- | --- | --- | --- | --- |
| before: 30 fps capture, 15 fps 400k | 6.8 | 2.4 | 2.5 | 11.7 |
| after: 15 fps capture, 15 fps 600k | 6.0 | 2.4 | 3.4 | 11.9 |

Unchanged within noise here: the encoder costs ≈0.9 point more for 600k and the stand-in saves
≈0.8. The stand-in decodes with libjpeg-turbo (1.8 ms per frame); it cannot include the DirectShow
and driver work that makes up most of the N100 helper's 58 % of a core and is paid per delivered
frame. That saving must be measured on the N100 (below).

## Not measured here: the N100 and a real lights-off picture

1. After installing, connect the camera and open `data\logs\robotcontrol_backend.log`: find
   `Camera capture | … | format=… | requested_fps=15 | reported_fps=…` and, 10 s later,
   `delivered_fps=…`. Expect about 15. About 30 means the driver ignored the request (no CPU
   saving); below 15 with the light off means the camera is lowering its rate to expose longer.
2. With recording running and one browser on the Camera page's live view, light on, watch Task
   Manager → Details for 1 minute: CPU of the camera helper (the `RobotControl.exe` child that
   writes clips), the main `RobotControl.exe` and `ffmpeg.exe`. Repeat with the outer light off.
   Compare with 14.6 % (helper) and 5.2 % (main) before.
3. With the outer light off, copy the newest finished `clip_*.mp4` (or `.avi`) and its `.json` from
   `data\videos\rolling_clips` and share it. Then run on a development PC:
   `uv run --locked python -m backend.scripts.live_view_quality_probe --clip <clip> --still <a:b> --moving <n>`
   with a stretch where nothing moves and a frame where the gripper moves; it reports detail kept for
   400k and 600k and writes crops to `test-output/live-view-quality`.

Evidence (local): `test-output/live-view-quality/` (crop sheets, `option-matrix*.json`,
`cpu_runs_all.txt`, `levels_after.txt`, probe JSON).

Not part of this change: the cyan tint is the camera's white balance (lit footage has it too); a
manual white balance or sharpness setting in the camera driver may help, but needs the camera.
