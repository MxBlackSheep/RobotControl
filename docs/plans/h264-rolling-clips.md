# Rolling clips as H.264: measurements and brief (2026-10-01)

The owner asked: could ffmpeg be applied when rolling clips are saved, would that be too
CPU-heavy, and how much smaller would clips be?

## Measured on real footage (development PC)

Source: 7 real rolling clips from the robot camera (`clip_20260608_1233*`–`1239*`, 640×480 MJPEG
AVI as `camera_worker.py` writes them, 7.5 fps, 451 frames per minute). Machine: i5-12490F in a
Hyper-V VM, no GPU. Encoder: the bundled ffmpeg n9.0.2 (LGPL), `libopenh264`, one thread,
BelowNormal priority. Repeat with `backend/scripts/clip_transcode_probe.ps1` (header has the command).

| Format | MB per 1-minute clip | Smaller by | CPU per clip | Picture (2× crops, still and moving) |
| --- | --- | --- | --- | --- |
| MJPEG AVI (today) | **45** (35–50) | – | – | reference; heavy sensor noise |
| H.264 300 kbit/s | 2.3 | 20× | 0.9 s | plate wells and gripper fingers smear |
| H.264 600 kbit/s | 4.4 | 10.6× | 1.0 s | plates and gripper readable, slightly soft |
| H.264 1000 kbit/s | **7.2** | **6.3×** (4.9–6.6×) | **1.0 s** | close to the source |

(MB = 2²⁰ bytes, full 451-frame clips. The bitrate is constant, so the MP4 size is fixed by it and the
ratio depends on the scene: a quieter 35 MB clip shrank 4.9×.)

- Real clips are about twice the reviewer's synthetic proxy (21.5 MB), because OpenCV's MJPEG
  writer uses high quality on a noisy picture. 120 rolling clips are ≈5.4 GB today, ≈0.9 GB at
  1000 kbit/s; a 15-minute experiment archive drops from ≈680 MB to ≈110 MB.
- CPU is about 1 s of one core per 1-minute clip (decode MJPEG + encode), i.e. ≈2 % of one core.
  The bitrate barely changes it. Decode-verification adds ≈0.3 s.
- SSIM against the source is low at every bitrate (0.71–0.78) because the encoder removes sensor
  noise, which SSIM counts as loss; the crops, not SSIM, decided the bitrate.
- MJPEG is full-range YUV. Kept full-range, OpenH264 output lifted blacks (mean pixel error 9.2);
  converted to standard (limited) range it was 5.1 at the same size, and every player expects it.
  The transcode therefore converts to limited range.
- `h264_qsv` and `h264_mf` (QuickSync) cannot run in this VM. On the N100 they may be cheaper,
  but software OpenH264 already fits; QuickSync is not needed.

**Not yet measured: the N100.** Its Gracemont cores are slower per thread; expect 2–3 s per clip
(still under 5 % of one core, under 2 % of the machine). The owner runs the probe there:

```powershell
powershell -ExecutionPolicy Bypass -File clip_transcode_probe.ps1 -Ffmpeg <RobotControl folder>\ffmpeg.exe -Clips <RobotControl folder>\data\videos\rolling_clips
```

## Decision: transcode each finalized clip (option a)

- **(a) Transcode after finalization, in a separate low-priority ffmpeg child (chosen).** The
  camera helper keeps writing MJPEG exactly as today, so recording never depends on ffmpeg. A
  missing, crashing or slow ffmpeg only leaves clips as MJPEG. Cost: each clip is written twice
  (45 MB then 7 MB per minute, < 1 MB/s) and stays MJPEG for a few seconds.
- (b) Pipe frames to ffmpeg instead of `VideoWriter`. Saves that write, but recording would then
  depend on a second process staying alive, and a fallback writer would be needed inside the
  camera helper, the code that recovery work keeps deliberately small. Rejected.

## Brief

**User flow.** Nothing changes while recording. A clip finishes as `clip_….avi` as today; within
seconds it is replaced by `clip_….mp4` with the same name stem. Staff see clips through experiment
archives on the Camera page (it lists archive folders, not rolling clips). When a run completes,
the archive waits up to 60 s for the conversion of its 15-minute window (newest first, so these
go first), then copies: archives hold MP4s, about 6× smaller, and download as before. The MP4 is
H.264 Constrained Baseline with its index at the front; Chromium plays it at its real length
(checked: 60.13 s for 451 frames). Existing MJPEG clips with sidecars are converted in the
background, newest first, once the first new clip is finished.

**Data kept.** The MJPEG file stays until its H.264 copy decodes to exactly the sidecar's frame
count; only then does the MP4 appear (atomic rename) and the AVI get deleted. The sidecar keeps its
fields (frame count, duration, identity, generation) and its path is updated; the MP4 keeps the
AVI's modification time, which cleanup and listings sort by. Clips without a sidecar (legacy) or
whose check fails stay MJPEG. `.partial.avi` files are never touched.

**Safety.** One ffmpeg at a time, BelowNormal priority, inside a kill-on-close Job Object (reusing
`h264_encoder.find_ffmpeg` and `_kill_on_close_job`), so it yields to Hamilton and the camera
helper and cannot outlive RobotControl. Failures are logged and shown as `clip_storage` in the
camera status, never raised into recording. The swap runs under the camera's clip lock, the same
lock the experiment archive holds while it copies, so an archive never sees a clip half swapped.

**Who reads clips, and what changes**

| Consumer | Today | With this change |
| --- | --- | --- |
| `CameraService._read_finalized_clips` (startup list, memory sync) | `clip_*.avi` | one entry per clip stem, MP4 preferred |
| `CameraService._cleanup_orphaned_files` (120-clip limit) | deletes AVI + sidecar | deletes every format of the clip + sidecar |
| `StorageManager.cleanup_rolling_clips`, statistics | `*.mp4`, `*.avi` | one clip per stem; deletes all its files |
| `StorageManager.archive_experiment_videos` | copies `clip["path"]` under the clip lock | unchanged; the path is updated under that lock |
| Recordings API list / download | uses memory list; MIME by suffix | unchanged (`.mp4` → `video/mp4`) |
| Notification attachments | stitches newest `.avi/.mp4` with OpenCV | unchanged; OpenCV decodes the MP4 (checked) |
| Sidecar `clip_….json` | one per stem | same file, `path` updated |

**Acceptance.**
1. A finalized clip with a sidecar becomes an MP4 with the same frame count and frame rate (real
   playback speed, including a calibrated rate below 7.5 fps), decodable by ffmpeg and OpenCV,
   within its bitrate (≈7.5 MB per minute) and smaller than the MJPEG; AVI and temporary file are
   gone. On real footage it is 4.9–6.6× smaller.
2. ffmpeg missing, crashing, killed, or producing a wrong frame count: the AVI stays playable and
   listed, the temporary file is removed, `clip_storage` reports it, recording continues.
3. RobotControl killed during a transcode: ffmpeg ends with it; the next start removes the
   temporary file and leaves AVI (or a verified MP4 and no duplicate listing).
4. Never two ffmpeg transcodes at once; each runs at BelowNormal.
5. Cleanup and archive handle a folder holding both formats; a clip rotated out during its
   transcode leaves no orphan MP4. An archive taken after a clip's conversion holds the MP4.
6. Recorded in the PR: before/after size and CPU per clip on real footage; the N100 run by the owner.

## Product review (2026-10-01)

The product-specialist review agreed with option (a) at 1000 kbit/s: clips exist to judge gripper
and plate positions after a failure, and 600 kbit/s would save only ≈0.35 GB more across 120 clips.
No new UI: a failed conversion leaves the MJPEG (no evidence lost), so `clip_storage` in the camera
status plus logs is enough. Adopted from the review: archives wait for their window's conversion
(the Camera page shows only archives), the AVI-in-use case is retried rather than failed, and
playback speed is an acceptance condition.

Open for the owner (not part of this change):
- With clips ≈6× smaller, should more than 2 hours of rolling clips be kept in the same space?
- Is an experiment archive created when a run crashes or fails? If not, staff cannot see the clips
  from that run on the Camera page.
