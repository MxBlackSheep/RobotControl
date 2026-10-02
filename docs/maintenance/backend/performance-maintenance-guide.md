# Performance and endurance validation

Target: Intel N100, 12 GB RAM. Preserve refresh intervals, recording settings and remote viewing, including hidden browser pages.

## Measure before diagnosing a leak

Set `ROBOTCONTROL_RESOURCE_DIAGNOSTICS=1` in the environment used to launch RobotControl. The default is off. Restart the application to apply it. Measurements are written every 60 seconds beneath the application's logs folder, in `diagnostics/resources-<PID>.jsonl`. Each process keeps at most five 5 MiB files. Retain the final report, then remove unneeded diagnostic files when the test is finished. No automatic restart is performed.

Rows separate RobotControl and its children, SQL Server and local browsers. Working set means resident RAM; private bytes means privately committed memory. CPU is percent of one logical core (divide by the recorded logical CPU count for whole-machine percentage). The first CPU sample is a warm-up sample. I/O counters are cumulative. Unavailable metrics are reported, not replaced with zero. Remote browser memory must be recorded on the remote computer. Total machine memory alone cannot identify a leak.

The recorder observes existing services; it does not start cameras, query SQL or read credentials. Allocation tracing is off; enable Python tracing only in isolated investigations, and compare private memory too because OpenCV/native allocations may not appear in Python traces.

## Why System status differs from Task Manager

System status → **CPU** is the whole machine, the share of time the logical processors were busy, averaged over the 5 s between `health_sampler` samples. Its detail, **RobotControl N%**, is the CPU time of RobotControl's main process and every process it started (camera helper, live-view and clip ffmpeg, package scripts) over the same 5 s, as a share of the whole machine; it shows a dash until two samples exist, never 0 %. A child that starts and ends between two samples, such as a clip's 0.3 s verifying decode, is missed. Task Manager differs for four reasons:

- Its CPU column is "% Processor Utility": busy time scaled by the current clock relative to the base clock. A CPU with a low base clock that turbo-boosts, like the N100, shows more utility than busy time for the same work.
- It refreshes every second, so it shows bursts (a clip conversion lasts 1–3 s) that the 5 s average flattens.
- Observers cost CPU too: Task Manager itself and remote-desktop tools (on 2026-10-02 the owner saw 11 % and 14 %), and a local browser showing System status. None of these belong to RobotControl's share.
- Its RobotControl group lists the main process and camera helper; ffmpeg children may appear as separate rows.

Clip conversion is a short burst, not the steady load: on the development PC (i5-12490F VM) it costs about 1.2 CPU-s per 1-minute clip, about 2 % of one core averaged over the minute. The steady camera cost is the camera helper (capture and MJPEG writing), the 14.6 % process in the owner's Task Manager reading, taken while the camera was asked for 30 fps. Its capture work is paid per delivered frame; since the request became 15 fps (`docs/plans/live-view-low-light.md`) that part should halve, an estimated 5–6 points less **RobotControl N%** on the N100 if the camera delivers 15 (the `delivered_fps` log line), not yet observed there.

The live-view guard's CPU figure (camera guide) is a different unit: percent of one core (75 % = three quarters of a core), deliberately not of the machine. For a record per process, set `ROBOTCONTROL_RESOURCE_DIAGNOSTICS=1` (above). To measure what clip conversion costs on a machine, run `backend/scripts/clip_transcode_probe.ps1 -Profiles product-1000-before,product-1000` (header has the full command): CPU-seconds and wall time per clip, peak cores and the machine's peak against its background load.

## Repeatable validation

Run `python -m backend.scripts.performance_probe --seconds 3 --trials 3` before and after changes. This feeds deterministic moving 640×480 frames (worst case for compression: noise) through the real H.264 encoder (`build/vendor/ffmpeg`) to zero, one and two simulated viewers. It never starts hardware or sends email. Compare all three trials, including CPU seconds (RobotControl and, separately, the ffmpeg child), delivered frames and event-loop delay. Two viewers should receive about twice the frames from one encoder. This does not measure camera capture, browser latency, disk recording or actual network performance.

For the N100 acceptance test, keep camera resolution/FPS, database content, browser version, power mode and background workload identical. Measure idle operation, running/paused scheduler monitoring, 1,000-method browsing, SQL/log browsing, recording, one remote viewer and multiple viewers. Repeat each short workload three times. Check API latency and browser responsiveness as well as CPU/private memory.

Then run a 24-hour screening test followed by ten days of recording and remote viewing. Include viewer reconnects and normal schedule completion/abort/restart checks. Track daily private-memory minima under equivalent workloads and session/thread/handle counts after reconnects. Investigate sustained growth; do not reset it with restarts or forced garbage collection. Preserve required recordings and notifications. A short synthetic test cannot establish ten-day stability.
