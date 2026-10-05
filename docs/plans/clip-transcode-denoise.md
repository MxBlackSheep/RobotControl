# Stored clips: temporal denoise in the H.264 conversion (2026-10-05)

Follows `live-view-denoise.md` (#51), which denoised live view only and left the clip conversion as
"Not done". **Every number below is from the development PC (i5-12490F in a Hyper-V VM, busy with
other sessions during the runs), not the N100.**

## Evidence

- Owner: "the recording itself is quite noisy, despite the live preview being much better." Their
  stored clip `20261005_051321_clip_…ae34b4726d7d43368f322a3ca37e4b42.mp4` (640×480, 7.5 fps, 60 s,
  1000 kbit/s, from `clip_transcoder.py`) is the camera's frames re-encoded with no denoise.
- Central review's measure (mean absolute frame-to-frame difference of a still grey crop:
  `format=gray,crop=440:300:100:150,tblend=all_mode=difference,signalstats`, mean YAVG): 6.63 as
  stored, 1.92 after the live filter alone.

## Measurements

`live_view_quality_probe` gained `clip:<kbit/s>[:d]` settings: they run
`clip_transcoder.transcode_command` (the product's command) on the whole clip and score the same
frames of the output. Noise left, detail kept and ghost are defined in the probe's header. Ghost is
measured on a region where something really moves in each clip:

- owner clip: still 200–380, the gantry moves at the top around 390–430 (region 80,0–400,200). The
  deck region is no use there: even still frames have 2–5 % of pixels jumping over 30 levels (noise),
  so the fit read the averaging of noise as "ghost" (0.40) rather than motion;
- `clip_20260608_123612` (gripper clip of #48/#51): still 90–209, gripper over the deck after 220;
- `clip_20260608_120610`: still 101–130, the arm crosses the upper left at 135–158 (40,0–360,300).

| clip: noise left / detail kept % / ghost prev, next | today (no filter) | live filter (s=5) | **s=7** | s=5, thresholds 0.20/0.40 |
| --- | --- | --- | --- | --- |
| owner | 5.16 / 97.2 / 0.027, 0.018 | 1.44 / 100.1 / 0.094, 0.071 | **1.07 / 100.2 / 0.092, 0.073** | 1.23 / 100.2 / 0.114, 0.090 |
| gripper 123612 | 5.52 / 95.5 / 0.082, 0.059 | 1.84 / 99.4 / 0.108, 0.089 | **1.51 / 99.5 / 0.105, 0.087** | 1.24 / 100.0 / 0.127, 0.111 |
| arm 120610 | 5.08 / 95.4 / 0.050, 0.041 | 1.58 / 99.4 / 0.065, 0.072 | **1.30 / 99.5 / 0.060, 0.072** | 1.05 / 99.9 / 0.077, 0.087 |

All variants keep 451 of 451 frames and send 1000–1007 kbit/s. Averaging two frames reads 0.5 ghost.

- A wider window removes about 20 % more noise at the same ghost: the serial algorithm (`a=s`) stops
  at the first frame that differs, so moving pixels are not averaged further. Higher thresholds do
  ghost more. The window's cost in live view is delay ((s+1)/2 held frames); a stored clip has none.
- In 2× crops (`clip_*_crops.jpg`, source | today | denoised) the gripper and arm keep single edges.
  The pale patch on the gripper clip's moving frame (300, during a 50 % light change) is in today's
  output too: the encoder short of bits, not the filter.
- Central review's measure on the owner clip: 6.63 stored, 5.19 re-converted without the filter,
  **1.11** with s=7.

**Chosen:** `atadenoise=0a=0.16:0b=0.32:1a=0.16:1b=0.32:2a=0.16:2b=0.32:s=7:a=s` as
`CAMERA_CONFIG.clip_denoise_filter`, separate from `LIVE_STREAMING_CONFIG.denoise_filter`.

## Size, CPU, frame counts

- Size at 1000 kbit/s does not grow: three real clips 7.57 → 7.56, 7.95 → 7.51, 7.53 → 7.52 MB
  (`clip_transcode_check --clips`); probe clips +0.0–0.7 %. Constant bitrate: the bits go to scene
  detail instead of noise (detail kept 95–97 → 99.5–100 %). Synthetic check clips (independent
  noise every frame) shrink a lot (7.5 → 2.9 MB) because the encoder has nothing left to spend on.
- CPU, conversion only, ffmpeg's own user+system time (`encode_cpu_ab.py`, 8 real clips, median of
  3 alternating rounds): 1.59 CPU-s per clip without, 1.88 with s=7, 1.92 with s=5; per clip
  +0.31 s median (−0.30 to +0.91), **about +20 %**, ≈0.5 % of one core over the minute. s=7 and s=5
  do not differ measurably. Roughly +0.5 s per clip on an N100 if it is ≈1.7× slower per thread
  (estimate).
- `clip_transcode_probe.ps1 -Profiles product-1000,product-1000-denoise` (new profile, 8 clips,
  three runs, machine 48–65 % busy): **peak per clip median 1.6 → 2.4 cores** (1.4–1.9 → 1.8–2.5,
  one 250 ms window at 3.1) for an encode of 0.7–1.2 s instead of 0.8–1.8 s (`cpu-peak/results.csv`).
  The filter now does real work in the filter-graph thread beside the decoder and encoder threads,
  so the ceiling is about 3 cores. Scale, format and denoise already share that one thread
  (`-filter_threads 1`), so there is no free restructuring; pinning to one core cost +50 % CPU-s in
  #47. On the 4-core N100 with Hamilton: up to about 2.5 of 4 cores for 1–2 s (estimate) once a
  minute, at BelowNormal. Its CPU-seconds there were within this busy machine's noise.
- Frames: `atadenoise` flushes its held frames at end of input, so every clip decodes to the
  sidecar's frame count (`clip_transcode_check` 28/28 and 31/31 with the filter, 31/31 without).
  A broken filter setting (an unknown filter) fails ffmpeg; the AVI is kept and `clip_storage`
  reports ffmpeg's message (checked by hand).

## What changes for evidence

Stored clips no longer carry the camera's raw sensor noise: still areas are averaged over up to 7
frames (≈0.9 s at 7.5 fps), and a pixel that changes is left alone: averaging stops at the first
neighbouring frame that differs by more than about 40 of 255 levels (threshold A, 0.16), or once the
differences summed outward exceed about 81 (threshold B, 0.32). A faint, brief change below those
(a dim reflection, a small low-contrast object present for one frame) can be softened. If a clip must show what the sensor delivered, set `clip_denoise_filter` to `""`; clips
recorded before then keep the denoise. The MJPEG recording itself is unchanged until conversion.

Evidence (local): `test-output/clip-denoise/` (probe JSON and crops per variant, `final/`,
`encode_cpu_ab.py/.txt`, `cpu-s5`, `cpu-s7`, `check_*.json`).
