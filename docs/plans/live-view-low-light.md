# Live view in low light: measurements and decision (2026-10-02)

> **Correction, later on 2026-10-02** (`docs/plans/live-view-denoise.md`). The production camera's log
> after this change: `format=YUY2 | requested_fps=15 | reported_fps=15.0`, then `delivered_fps=30.0`.
> The driver reports the 15 fps request but delivers 30, so on this camera the capture saving below,
> the longer exposure (the ×4 rows) and the expected "RobotControl N% about 5–6 points lower" did not
> happen; `capture_fps` is 30 again. Level 0 is now 15 fps at **400 kbit/s with temporal denoise**:
> the owner views through the Cloudflare tunnel, and on a simulated 450–500 kbit/s link (600 in
> noise) 600 kbit/s fell to 7–12 fps and 0.8–1.9 s behind.
> The "Temporal denoise" finding below used default `atadenoise` settings and a detail measure that
> does not see noise; with tuned settings it is what lets the bitrate drop.

The owner (production Intel N100, 4 cores, USB camera in the Hamilton enclosure) reported that live
view is "a bit blurry, especially when the outer light is turned off": cyan-tinted, noisy, smeared
plate barcodes and labware, shown about 3× enlarged. They asked for better image quality without
much more CPU or bandwidth. At the time, Task Manager showed the camera helper at 14.6 % of the
machine (≈58 % of one core) and the main process at 5.2 %.

**Every number below is an estimate from the development PC (i5-12490F in a Hyper-V VM, no GPU, no
camera attached), not an N100 measurement.** No real lights-off footage and no N100 measurement are
available; both changes are therefore conservative and reversible from `config.py` (below).

## What the code did

- `camera_worker.py` asked the camera for 640×480 at **30 fps** and decoded every frame, but live view
  encoded at most 15 fps and recording kept at most 7.5: half of the helper's capture work was
  thrown away. The negotiated format (MJPG or YUY2) was never set or logged.
- Live view (level 0) was libopenh264 Constrained Baseline, 15 fps at **400 kbit/s**, ≈3.3 kB per
  frame. In low light the camera raises gain; sensor noise uses up the bits and detail smears.
- In the dark a camera's auto-exposure cannot expose longer than one frame: 1/30 s at 30 fps,
  1/15 s at 15 fps. A 15 fps request lets it gather twice the light before adding gain, if its
  driver extends exposure (unknown for this camera).

## Footage and the low-light model

Real robot clips (`clip_20260608_*`, 640×480 MJPEG, 7.5 fps, from the enclosure camera):
- **lit**: `123612`, frames 90–209 still, then the gripper moves.
- **real dim**: `122511` (12:25, luma ≈50 against ≈140 lit, only the deck lighting on). Inferred to
  be the outer light off, not confirmed. Here the camera did not raise gain: dark, not noisy, so it
  is not the owner's picture.

**Synthetic low light** (`live_view_quality_probe.darken`), built from the lit clip:
1. Undo the 8-bit gamma (2.2) to get linear light per channel.
2. Scale to equivalent electrons: 100 at 8-bit white, divided by the gain G (1/G of the light).
   The 100 is calibrated to the lit clip. Its temporal noise is σ 12.5 levels in mid-tones; this
   takes about 45 % of that variance as shot noise, the rest as compression and fixed noise.
   (60 would take all of it as shot noise, 150 little.)
3. Draw Poisson shot noise plus Gaussian read noise (0.5), new for every frame and channel, from one
   fixed seed, so every setting sees identical frames.
4. Smooth the noise slightly (σ 0.6 px), as demosaicing correlates neighbours.
5. Multiply by G: the camera's gain restores brightness and amplifies the noise.
6. Shift white balance toward cyan in linear light (B 1.06, G 1.04, R 0.82), re-apply gamma, round
   to 8 bits.

Temporal noise in mid-tones becomes ≈29 levels at ×4 and ≈43 at ×8, against 12.5 lit.
The real dim clip has ≈10× less light (linear) than lit. So a camera that restores brightness at
30 fps needs about **×8**; at 15 fps, if exposure doubles, about **×4**. The model is a stand-in,
not camera output; its ×8/×4 picture is cyan, grainy and smeared like the owner's description.

## Measured

Every setting encodes the same frames with the production command (`h264_encoder.ffmpeg_command`).
"Detail kept" is the decoded image's fine detail projected onto that of the noise-free still scene
(the mean of the still frames; for the model, of the darkened still frames). Reproduced noise does
not raise it; smearing lowers it. PSNR/SSIM against the noisy source fell as bitrate rose (they
reward reproduced noise), so they were not used to choose.

| Detail kept, % (still frames) | 15/400 (before) | 15/500 | **15/600 (after)** | 10/600 | 15/600 + atadenoise |
| --- | --- | --- | --- | --- | --- |
| model, gain ×8 (30 fps capture, light off) | 83.2 | 84.0 | **84.8** | 85.9 | 84.9 |
| model, gain ×4 (if 15 fps doubles exposure) | 85.6 | 86.5 | **87.5** | 88.4 | 87.2 |
| real dim | 94.2 | – | **95.7** | 96.7 | 95.8 |
| lit | 88.0 | – | **89.9** | 91.5 | 90.3 |

- Light off, before (×8, 400k) → after: 83.2 → 84.8 at equal gain, → 87.5 if 15 fps halves the gain.
  In 2× crops the second and third plates' well rows break into blocks at 400k and stay rows at 600k,
  and the gripper's fingers stay separate while it moves.
- **10 fps** scores best per frame, but 10 does not divide a 15 fps capture (frames 67/133 ms apart,
  a judder), and keeping 30 fps capture to allow it would forgo the capture saving.
- **Temporal denoise**: the bundled LGPL ffmpeg has no `hqdn3d` (GPL). `atadenoise` (s=5) changed
  detail by −0.3 to +0.1 points and roughly doubled encoder CPU per frame; `tmedian` holds back
  frames. libopenh264 already discards most noise at these rates. Not used.
- **Resolution** was not changed (fixed 640×480 slot, recording, transcoder, ≈3× CPU). The softness
  of 640×480 enlarged 3× in the browser remains; this change does not remove it.

**Bandwidth per viewer.** After/before is +50 % in every scene, but libopenh264 overshoots its
target when noise is heavy:

| scene | before (400k) | after (600k) |
| --- | --- | --- |
| lit, real dim | 407–439 kbit/s | 610–661 kbit/s |
| model ×4 | 454 | 688 |
| model ×8 | 554 | 844 |

So with the light off a remote viewer may need ≈0.85 Mbit/s instead of ≈0.55. Degraded levels
(4 s of real footage): 7.5/300 → 430 kbit/s, 5/200 → 338 (old 10/300 355, 5/200 338). At low rates
a keyframe each second sets a floor.

**CPU** (% of one core):
- Sustained 60 s emulation (`test-output/live-view-quality/cpu_pipeline.py`), medians of 5 pairs:

  | | helper stand-in | main | ffmpeg | total |
  | --- | --- | --- | --- | --- |
  | before: 30 fps capture, 15/400 | 6.8 | 2.4 | 2.5 | 11.7 |
  | after: 15 fps capture, 15/600 | 6.0 | 2.4 | 3.4 | 11.9 |

  It runs the live chain with one viewer and the real encoder on real footage. A stand-in helper
  process decodes real MJPEG frames at the capture rate, copies them to the slot and writes the
  7.5 fps clip. The total is unchanged within noise: encoder +0.9, helper −0.8.
- `performance_probe` trials of 20 s with one viewer, 3 alternations: before 2.4–2.7 %, after
  0.9–2.0 %. The main process roughly halves, ffmpeg is similar; the helper is not included. The
  probe's scene is pure noise (≈60 kB per frame at both settings), so this measures the chain, not
  the bitrate.
- Not reproducible here: the DirectShow/driver work, which makes up most of the N100 helper's 58 %
  of a core and is paid per delivered frame. Halving the delivered rate should reduce it, but this
  is unmeasured.

Pacing (`_submit_frame`, ¼-interval tolerance) is unchanged. The camera supervisor notices new frames
on a ≈31 ms poll. A simulation of that arrival pattern kept 15.00 of 15 fps (gaps 61–97 ms), and 7.5
and 5 fps from 15 at their rates (`test-output/live-view-quality/pacing_sim.py`).

## Decision

- *(Did not hold on the production camera, which delivers 30 fps regardless; reverted to 30, see the correction above.)*
  `CAMERA_CONFIG["capture_fps"] = 15`. The helper decodes and copies half as many frames; the parent
  copies half as many. Recording still measures its rate at connection and keeps at most 7.5 (every
  second frame).
- *(Level 0 superseded by 15/400 with denoise, see the correction above.)* `encoder_levels` **15/600, 7.5/300, 5/200**. Each divides 15 (and 30), so frames stay evenly
  spaced. The GOP is `int(fps)` frames (at most a second; 7 at 7.5 fps), so joining and keyframe
  recovery stay within a second. The CPU guard and its ladder are unchanged.
- Each connection logs `Camera capture | … | format=… | requested_fps=15 | reported_fps=…`, then 10 s
  later `delivered_fps=…` counted from frames that actually arrived. A camera that ignores the
  request shows ≈30 there; one that lowers its rate in the dark shows less than 15.

**Reverting** (`backend/config.py`, then restart):
- Earlier camera request: `capture_fps: 30`. The new levels still divide 30.
- Earlier picture and bandwidth: level 0 `{"fps": 15, "bitrate_kbps": 400}`.
- Earlier degraded levels: `{10, 300}` and `{5, 200}`. 10 divides 30 but not 15, so use them only
  with `capture_fps: 30`.

## Not confirmed on the N100

- The camera's delivered rate and format, and whether its auto-exposure uses the longer frame time
  (the ×4 row) or not (the ×8 row).
- Helper, main and ffmpeg CPU on the Gracemont cores, light on and off.
- The picture with the real outer light off.

**Expected System status figure** *(did not apply: the camera delivers 30 fps, see the correction above)*. **RobotControl N%** (main process plus camera helper and ffmpeg
children, as a share of the machine) should fall by about **5–6 points** on the N100 if the camera
delivers 15 fps, for example from about 20 % to about 14–15 % with recording on and one viewer.
The estimate is built from the owner's Task Manager reading:

| part | basis | change |
| --- | --- | --- |
| camera helper, 7.5 fps clip write (fixed) | 5.5 ms per frame here, ≈1.7× slower per thread on the N100 → ≈7 % of a core ≈ 1.8 % of the machine | none |
| camera helper, per delivered frame (driver, decode, slot copy) | 14.6 − 1.8 ≈ 12.8 % | halves: −6.4 |
| main process, frame copy | 0.4 ms × 15 frames a second fewer | −0.3 |
| live encoder 400 → 600 kbit/s, only while someone watches | +0.9 % of a core here | +0.4 |

If only half of the helper's remainder is per frame, the fall is about 3 points. If the log shows
`delivered_fps` ≈ 30 (the driver ignored the request), there is no fall. Task Manager's percentages
are processor utility, which runs higher than busy time on the N100
(`docs/maintenance/backend/performance-maintenance-guide.md`).

**Passive checks** (no action needed from the owner):
- System status → CPU → **RobotControl N%**, read whenever convenient.
- `data\logs\robotcontrol_backend.log`: `Camera capture | … | delivered_fps=…` once per connection.
- A warning per clip if the camera slows below the recording rate after connection, for example once
  the light is switched off: `Camera delivered N fps, below the recording rate (7.5 fps); this clip
  plays faster than real time`. Recording is unchanged; if it appears, a fix is decided on that evidence.

**Optional, if someone is at the N100:**
1. Find the two `Camera capture` lines in the log: format and requested/reported fps at connection,
   `delivered_fps` 10 s later.
2. With recording on and one live viewer, note Task Manager → Details CPU for the camera helper,
   `RobotControl.exe` and `ffmpeg.exe` for a minute, light on and off (before: helper 14.6 %, main 5.2 %).

If a lights-off clip ever turns up, `live_view_quality_probe` is ready to score it:
`uv run --locked python -m backend.scripts.live_view_quality_probe --clip <clip> --still <a:b> --moving <n>`.
An `.mp4` rolling clip has already been through the 1000 kbit/s transcode (some noise removed), so it
is close to, not identical to, the camera's output.

Evidence (local): `test-output/live-view-quality/`: crop sheets, `option-matrix*.json` (real footage),
`model-option-matrix.json`, `cpu_runs_all.txt`, `performance_probe_ab_20s.txt`, `levels_after.txt`,
`slow_clip_warning_check.txt`.

Not part of this change: the cyan tint is the camera's white balance (lit footage has it too); a
manual white balance or sharpness setting in the camera driver may help, but needs the camera.
