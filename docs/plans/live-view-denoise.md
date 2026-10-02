# Live view: temporal denoise and 400 kbit/s (2026-10-02)

Follows `live-view-low-light.md` (#48), which raised level 0 to 15 fps at 600 kbit/s and asked the
camera for 15 fps. **Every number below is from the development PC (i5-12490F in a Hyper-V VM, no
camera), not the N100.**

## Evidence after #48 (production N100, 2026-10-02 08:56)

- Log: `Camera capture | format=YUY2 | requested_fps=15 | reported_fps=15.0`, 10 s later
  `delivered_fps=30.0`. The driver reports the request but delivers 30, so #48's capture saving,
  longer exposure and "RobotControl N% about 5–6 points lower" did not happen on this camera.
- Live view ran at level 0 (15/600) throughout: no `encoder_degraded`, no delivery errors.
- The owner watches through the Cloudflare tunnel (cloudflared on the N100, hence 127.0.0.1 in the
  log) and found live view "laggy again" since #48, with no visible noise reduction (#48 added none).
- Three 1-minute rolling clips (light on, still scene): sensor noise, not flicker (overall
  brightness sd 0.10). Clips have been through the 1000 kbit/s transcode, so the camera's own frames
  are noisier.

## What makes live view lag on the tunnel

A viewer's frames wait for that viewer's window (`streaming_session.py`); a frame waiting over 0.5 s
skips that viewer to the next keyframe. When the link carries less than the stream, frames queue,
then skip: the picture is late and jerky. libopenh264 also overshoots its target when the picture is
noisy (#48: 844 kbit/s at a nominal 600 in the light-off model), so noise raises the bitrate exactly
when the picture is worst.

`performance_probe.py --rtt R --kbps L --clip <clip> --level0 fps:kbit/s[:d]` now models a link of
L kbit/s (frames cross one after another) with real frames. One viewer, 20 s each, owner clip
085717 and the light-off model (#48's `darken`, gain ×8, of clip 123612). Latency is capture to
shown in the simulated browser (no decode or display). Evidence: `tunnel_matrix.jsonl`.

| scene, round trip | link kbit/s | 15/400 (before #48) | 15/600 (#48) | **15/400 + denoise** | 15/450 + denoise |
| --- | --- | --- | --- | --- | --- |
| owner, 0.15 s | unlimited | 15.0 fps, 80 ms | 14.9, 80 ms | **14.8, 284 ms** | 14.8, 284 ms |
| | 1000 | 14.9, 109 | 14.3, 125 | **14.8, 312** | 14.8, 314 |
| | 600 | 14.3, 128 | 14.2, 333 | **14.8, 332** | 14.2, 340 |
| | 500 | 14.3, 141 | 11.6, 1361 | **14.2, 339** | 14.2, 354 |
| | 450 | 14.3, 175 | 10.3, 1530 | **14.2, 348** | 14.2, 451 |
| owner, 0.3 s | 600 | 14.3, 205 | 14.3, 397 | **14.2, 404** | 14.2, 411 |
| | 500 | 14.3, 215 | 11.3, 797 | **14.2, 414** | 14.2, 428 |
| | 450 | 14.3, 238 | 10.2, 1418 | **14.2, 430** | 14.2, 537 |
| light-off model, 0.15 s | unlimited | 14.9, 79 (511 kbit/s sent) | 14.9, 80 (783) | **14.8, 288 (411)** | 14.8, 286 (464) |
| | 600 | 13.9, 300 | 9.7, 1121 | **14.1, 329** | 14.0, 335 |
| | 500 | 13.5, 456 | 7.1, 1904 | **13.9, 343** | 13.8, 372 |

So on a link of 450–500 kbit/s (600 in noise) 600 kbit/s falls to 7–12 fps and 0.8–1.9 s behind,
while 400 + denoise keeps 13.9–14.8 fps and 0.3–0.4 s. The unknown is the owner's link. The probe models the link's
rate, not loss or Cloudflare's own buffering.

## Denoise: which filter

The bundled LGPL ffmpeg has no `hqdn3d`. Candidates on the owner clip and the gripper clip (123612,
gripper moves after frame 209), encoded at 15/600 (`round1`):

| filter | noise left | detail kept | frames held | CPU |
| --- | --- | --- | --- | --- |
| none | 2.61 | 90.5 % | 0 | |
| `atadenoise` s=9 (default algorithm) | 1.81 | 92.4 % | 5 | ≈0.3 ms/frame |
| `atadenoise` s=5 | 1.84 | 92.4 % | 3 | ≈0.3 ms/frame |
| `tmix` 2 frames | 1.62 | 93.4 % | 0 | ghosts: moving parts keep half of the previous frame |
| `fftdnoiz` prev=1 | 1.5–2.1 | ≤ 90 % | 0 | 17–39 ms/frame: too slow |

- **Noise left**: mean absolute frame-to-frame change of the grey image on still frames after
  encoding, the flicker a viewer sees (`live_view_quality_probe`). #48's detail measure ignores
  noise by design, which is why default `atadenoise` looked useless there.
- **Frames held**: `atadenoise` outputs the middle of its window, so it holds back (s+1)/2 frames;
  5 is its smallest window (`frames_held.py`). 3 frames is 200 ms at 15 fps, 400–600 ms at the
  degraded 7.5 and 5 fps, which is why only level 0 uses it.
- **Ghost**: on frames where the gripper moves, the share of the previous/next source frame left in
  the output (`live_view_quality_probe`, validated: `tmix` 2 frames reads 0.507). Encoder alone:
  0.10 previous / 0.08 next.

Thresholds (s=5, 450 kbit/s, gripper clip): 0.08 → ghost 0.107, 0.12 → 0.113, 0.16 → 0.123,
0.20 → 0.137. The serial algorithm (`a=s`, stops averaging at the first frame that differs too much)
at 0.16 keeps ghosting at 0.112/0.090 with noise left 0.94, near what 0.20 parallel removes. In
2× crops of the moving gripper there is no double edge.

**Chosen:** `atadenoise=0a=0.16:0b=0.32:1a=0.16:1b=0.32:2a=0.16:2b=0.32:s=5:a=s`, run on the
encoder's yuv420p planes (`format=yuv420p` first) with `-filter_threads 1`.

## Bitrate

`live_view_quality_probe` (`clip_*.json`, crops `clip_*_crops.jpg`):

| detail kept (still frames) / noise left / kbit/s sent | 15/600 (#48) | 15/400 | **15/400 + denoise** | 15/450 + denoise |
| --- | --- | --- | --- | --- |
| owner 085717 (light on) | 90.5 / 2.61 / 644 | 88.0 / 1.95 / 424 | **92.6 / 0.80 / 413** | 93.6 / 0.81 / 467 |
| owner 085817 | 90.1 / 2.63 / 616 | 87.9 / 1.91 / 410 | **92.6 / 0.79 / 406** | 93.8 / 0.81 / 458 |
| gripper clip, lit | 89.9 / 2.37 / 637 | 88.0 / 1.75 / 423 | **91.7 / 0.91 / 418** | 92.6 / 0.94 / 471 |
| real dim | 95.8 / 3.17 / 623 | 94.3 / 2.44 / 414 | **96.5 / 1.16 / 413** | 96.9 / 1.24 / 466 |
| light-off model ×8 | 84.8 / 3.42 / 846 | 83.2 / 2.40 / 545 | **87.7 / 1.41 / 426** | 88.9 / 1.52 / 483 |

(085817 from the tuning round, 120 frames from frame 200.) Ghost on the gripper clip:
0.091/0.072 at 15/600, 0.109/0.088 at 15/400 + denoise. Clip frames (7.5 fps) are fed at 15, so
motion is twice as fast as live: a harder case for a temporal filter.

**Chosen: 15 fps at 400 kbit/s with denoise.** Detail is higher than 600 without denoise in every
scene, noise left is about a third, and it sends 406–426 kbit/s, overshooting by at most 7 % in the
light-off model (600 without denoise: +41 %). 450 adds about 1 point of detail for 12 % more
bandwidth and more delay on a 450 kbit/s link; on the tunnel the margin matters more.

**The cost: 200 ms more delay at every link speed** (capture to shown 80 → 284 ms on a fast link).
Plain 15/400 has no extra delay but overshoots in noise (511–545 kbit/s in the model) and keeps less
detail than #48. If the delay matters more than the picture, `denoise_filter: ""` gives plain
15/400; `{"fps": 15, "bitrate_kbps": 600}` without `denoise` gives #48's level back.

## CPU (development PC)

- Filter alone (`filter_cpu.txt`, 9 paired runs of 1800 frames): median +0.36 ms per frame
  (−0.1 to 0.9), ≈0.5 % of one core at 15 fps here; roughly 1 % of an N100 core if it is ≈1.7×
  slower per thread (estimate).
- Live chain with one viewer, real frames, camera at 30 fps (`chain_cpu_ab.txt`, 3 alternations of
  30 s, main + ffmpeg, % of one core): 15/600 1.51–1.98 (median 1.77), 15/400 + denoise 1.19–1.41
  (median 1.30). Encoding fewer bits pays for the filter.
- Encoder-only A/B (`encoder_cpu_ab.txt`) ranged too widely on this VM to separate (15/400 alone
  0.59–1.99 ms per frame).

## Camera request: back to 30 fps

`capture_fps` is 30 again. The production camera delivers 30 whatever is requested, so 15 saved
nothing and only made `performance_probe` (which runs its camera at `capture_fps`) and the docs
describe a camera we do not have. The request is only a hint: recording measures what arrives
(keeps at most 7.5) and live view paces itself to its level, so nothing else changes. A camera that
honours 15 would save capture work, but none is in use, and exposure gains were never observed.

## Not done

- **Clip transcode denoise.** The same filter would cost about 0.16 CPU-s per 1-minute clip
  (0.36 ms × 450 frames, +13 % on 1.24 CPU-s) and flushes its held frames at end of input, so frame
  counts and clip verification would be unaffected. Its benefit at 1000 kbit/s is unmeasured; a
  separate change if wanted.
- Degraded levels (7.5/300, 5/200) are unchanged and without denoise; they exist for CPU, not links.
- Not measured on the N100: filter and chain CPU, the real tunnel's capacity, lights-off footage.

Evidence (local): `test-output/live-view-denoise/` (probe JSON and crops, `tunnel_matrix.jsonl` and
`.sh`, `frames_held.py/.txt`, `filter_cpu.sh/.txt`, `encoder_cpu_ab.py/.txt`, `chain_cpu_ab.sh/.txt`,
`levels_on_off.py/.txt`). Tuning rounds are summarised above.
