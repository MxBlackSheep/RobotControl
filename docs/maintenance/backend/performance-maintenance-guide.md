# Performance and endurance validation

Target: Intel N100, 12 GB RAM. Preserve refresh intervals, recording settings and remote viewing, including hidden browser pages.

## Measure before diagnosing a leak

Set `ROBOTCONTROL_RESOURCE_DIAGNOSTICS=1` in the environment used to launch RobotControl. The default is off. Restart the application to apply it. Measurements are written every 60 seconds beneath the application's logs folder, in `diagnostics/resources-<PID>.jsonl`. Each process keeps at most five 5 MiB files. Retain the final report, then remove unneeded diagnostic files when the test is finished. No automatic restart is performed.

Rows separate RobotControl and its children, SQL Server and local browsers. Working set means resident RAM; private bytes means privately committed memory. CPU is percent of one logical core (divide by the recorded logical CPU count for whole-machine percentage). The first CPU sample is a warm-up sample. I/O counters are cumulative. Unavailable metrics are reported, not replaced with zero. Remote browser memory must be recorded on the remote computer. Total machine memory alone cannot identify a leak.

The recorder observes existing services; it does not start cameras, query SQL or read credentials. Allocation tracing is off; enable Python tracing only in isolated investigations, and compare private memory too because OpenCV/native allocations may not appear in Python traces.

## Repeatable validation

Run `python -m backend.scripts.performance_probe --seconds 3 --trials 3` before and after changes. This uses deterministic 720p frames and zero, one and two simulated viewers. It never starts hardware or sends email. Compare all three trials, including CPU seconds, delivered frames and event-loop delay. This does not measure camera capture, browser latency, disk recording or actual network performance.

For the N100 acceptance test, keep camera resolution/FPS, database content, browser version, power mode and background workload identical. Measure idle operation, running/paused scheduler monitoring, 1,000-method browsing, SQL/log browsing, recording, one remote viewer and multiple viewers. Repeat each short workload three times. Check API latency and browser responsiveness as well as CPU/private memory.

Then run a 24-hour screening test followed by ten days of recording and remote viewing. Include viewer reconnects and normal schedule completion/abort/restart checks. Track daily private-memory minima under equivalent workloads and session/thread/handle counts after reconnects. Investigate sustained growth; do not reset it with restarts or forced garbage collection. Preserve required recordings and notifications. A short synthetic test cannot establish ten-day stability.
