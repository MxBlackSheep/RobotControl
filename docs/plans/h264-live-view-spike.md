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

## Decision (2026-10-01)

The owner chose to adopt H.264 as a separate feature, as the **only** live-view encoding: no JPEG
fallback for live view. A browser without WebCodecs H.264 decoding shows a clear "browser not
supported" message instead of a degraded stream. Snapshots and MJPEG recording stay as they are.
Still open before release: the N100 measurement above (real camera, QuickSync availability, CPU
headroom beside the robot) and the licence review for whichever encoder is bundled.

## Feature brief (2026-10-01)

**User flow.** A viewer opens Camera › Live view and presses **Start my live view**. The page first
checks that this browser can decode H.264 through WebCodecs. If it can, the session starts and the
picture appears within about a second (at the next keyframe). If it cannot, no session is created
and the viewer sees "This browser can't show live view; use Chrome/Edge 94+, Safari 16.4+ or
Firefox 130+". WebCodecs exists only on secure pages (HTTPS, or `localhost` on the robot computer),
so plain-HTTP access (the README's ZeroTier address `http://192.168.x.x:8005`) gets its own message
naming the secure address instead of blaming the browser. Fit / Fit width / zoom / pan, Expand, Stop,
Reconnect, hidden-tab pause, automatic reconnect and the 10-second stale label behave as today.
Snapshots and MJPEG recording are unchanged.

**Data and state.**
- One encoder per stream configuration (one configuration: 640×480, 15 fps, 1 s GOP, no B-frames),
  started when the first viewer is watching and stopped when none is (Stop, disconnect, hidden tab,
  shutdown, CPU hard limit). Encoded access units fan out to every viewer.
- Binary frame message: `FRAME_VERSION` 2 adds one flags byte (bit 0 = keyframe) to the existing
  header; the payload is one H.264 Annex-B access unit. Acknowledgements, `ACK_TIMEOUT_SECONDS`,
  keepalive and `BROWSER_SILENCE_SECONDS` keep their meaning; the frames allowed in flight follow
  each viewer's measured round trip (review finding: a fixed two froze far viewers).
- Per viewer: "in step" or "waiting for keyframe". A viewer whose window is full when an access unit
  arrives, or that joins, resumes or reconnects, waits for the next keyframe. Nothing queues.
- Browser: one `VideoDecoder`; the frame store holds the newest decoded `VideoFrame` (the previous
  one is closed), drawn by one canvas.
- The JPEG live-view path (`frame_encoder.py`'s live-view use, per-session JPEG quality levels and
  the `<img>` viewer) is removed.

**Safety constraints.** The encoder runs as a child process in a Windows Job Object that kills it
when RobotControl exits, so it cannot outlive the server. Pipes carry at most one raw frame in
flight. An encoder crash ends or restarts live view with a visible message; it never touches the
camera helper, recording or Hamilton. The CPU guard keeps its thresholds and steps the shared
encoder down (frame rate, then bitrate) and back up; the hard limit still ends all sessions.

**Acceptance (observable).**
1. With no viewer, no encoder process exists; Start creates one; Stop of the last viewer, a closed
   tab, server shutdown and a killed RobotControl all leave no encoder process.
2. A second viewer starts on a keyframe without restarting the encoder; a viewer on a stalled link
   does not lower the first viewer's frame rate.
3. Killing the encoder shows a message, recording continues, and live view recovers or ends cleanly.
4. Unsupported browser and insecure page each show their message and create no session.
5. Packaged candidate in a relocated folder finds and runs the encoder.
6. N100 (owner, on the robot computer): CPU and bytes per second next to a running method; see the
   commands in the PR.

**Owner decisions (2026-10-01).**
- Encoder: the BtbN **LGPL** static `ffmpeg.exe` (release branch 9.0, pinned by URL and SHA-256 in
  the build script, not committed to Git), encoding with `libopenh264` in software. QuickSync is
  not used: software encoding at this size costs about 1 % of a core. The build is configured with
  `--enable-version3`, so ffmpeg is LGPL 3.0. LGPL duties: ship the licence
  texts in `THIRD_PARTY_NOTICES`, name the build on the About page, and keep the matching source
  with the release evidence. H.264 *patents* are separate from ffmpeg's copyright licence; Cisco's
  patent cover applies only to Cisco's own DLL downloaded to the device, not to this build. The
  owner accepted that position (check with a licensing contact before distributing outside the
  organisation).
- Quality: one profile. The API's `quality` field and the four JPEG levels are removed; the CPU
  guard steps the shared encoder 15 → 10 → 5 fps and 400 → 300 → 200 kbit/s, then back up.
- Plain-HTTP (ZeroTier) access is no longer used. Remote access is through the Cloudflare tunnel
  (HTTPS); an HTTP page still shows the secure-connection message. The README is updated.
