# H.264 live view: spike findings (2026-10-01)

Question: would H.264 (via ffmpeg) give a better live view through the Cloudflare tunnel than the
current JPEG frames, within the N100's CPU budget? This records a measurement, not a decision.

## Measured on the development machine

Machine: Intel i5-12490F in a Hyper-V VM, **no GPU** (the "F" part has no integrated graphics), so
Intel QuickSync could not be tested here. Encoder: ffmpeg `N-127032` LGPL build
(BtbN/FFmpeg-Builds `ffmpeg-master-latest-win64-lgpl.zip`, 176 MB zip, `ffmpeg.exe` 138 MB static).
Its H.264 encoders: `h264_qsv` (Intel QuickSync), `h264_mf` (Media Foundation), `libopenh264` (Cisco,
BSD), plus AMD/NVIDIA/D3D12/Vulkan. No x264 (GPL).

Source: ffmpeg `testsrc2` (moving pattern), 640×480, 15 fps, 30 s = 450 frames. Synthetic: real
camera scenes have sensor noise and less motion.

| Stream | kB/s | SSIM vs clean source | CPU (user) for 450 frames |
| --- | --- | --- | --- |
| JPEG q≈75, 480×360 (today's adaptive preset) | 163 | 0.859 | 0.375 s |
| OpenH264, 640×480, 300 kbit/s, 1 s GOP | **39** | **0.871** | **0.094 s** |
| OpenH264, 640×480, 600 kbit/s | 76 | 0.876 | 0.188 s |
| Media Foundation (software MFT here), 640×480, 500 kbit/s | 72 | not measured | 1.45 s |

With temporal noise added (`noise=alls=12:allf=t`, closer to a webcam), byte ratios were similar
(JPEG 480×360: 188 kB/s; OpenH264 300k: 41 kB/s). SSIM against a noisy source is not meaningful
(each encoder removes the noise differently), so quality was compared on the clean source only.

Reading: **software OpenH264 at full resolution used about a quarter of the bytes and a quarter of
the CPU of today's downscaled JPEG, at equal or better quality.** It does not need QuickSync. The
Media Foundation software encoder is much more expensive; on the N100 its hardware path may differ.

Against the spike's bar (bytes ≤ 40 % of JPEG at similar quality; CPU no higher): met on this
synthetic source. Not yet measured: the real camera on the N100, end-to-end delay through the
tunnel, and browser support.

## Repeat on the N100 (please run there)

Copy `ffmpeg.exe` to the N100, then in PowerShell (synthetic source; no camera, no RobotControl):

```powershell
$ff = ".\ffmpeg.exe"; $gen = 'testsrc2=size=640x480:rate=15'
& $ff -hide_banner -benchmark -f lavfi -i $gen -t 30 -vf scale=480:360 -c:v mjpeg -q:v 8 -f mjpeg a.mjpeg
& $ff -hide_banner -benchmark -f lavfi -i $gen -t 30 -c:v libopenh264 -b:v 300k -g 15 -f h264 b.h264
& $ff -hide_banner -benchmark -f lavfi -i $gen -t 30 -c:v h264_qsv -b:v 300k -g 15 -f h264 c.h264
```

Compare the `bench: utime=` lines and file sizes (bytes / 30 = bytes per second). The QSV line shows
whether QuickSync is available to the account running RobotControl. With the real camera stopped in
RobotControl, `-f dshow -i video="<camera name>"` replaces the `lavfi` source.

## What adoption would involve (not started)

- Encoder: `ffmpeg.exe` as a child process fed raw BGR frames from the camera supervisor only while
  someone watches (640×480×3×15 fps ≈ 14 MB/s through a pipe), `-c:v libopenh264` (or `h264_qsv` if
  available), 1 s GOP, no B-frames; a new viewer waits for the next keyframe.
- Transport: the existing binary WebSocket frames and acknowledgements (one access unit per message;
  when behind, skip to the next keyframe instead of queueing).
- Browser: WebCodecs `VideoDecoder` onto a canvas (Chrome/Edge 94+, Safari 16.4+, Firefox 130+),
  with today's JPEG path as fallback for other browsers. Snapshots and MJPEG recording unchanged.
- Packaging: the full static `ffmpeg.exe` adds 138 MB. Smaller options: a trimmed ffmpeg build with
  only rawvideo input and the H.264 encoders, or Cisco's OpenH264 DLL (~1 MB; Cisco's own binary
  carries its H.264 patent licence) behind a small binding. Licence review needed before bundling.

Decision needed from the owner after the N100 run: adopt (as a separate feature), or keep JPEG.
