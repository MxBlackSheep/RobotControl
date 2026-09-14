# N100 optimization validation — 2026-09-14

## What was measured

The target is an Intel N100 with 12 GB RAM. This development environment reports six logical CPUs and 12 GB RAM; it is **not an N100 acceptance run**. No connected-camera endurance result is claimed.

The synthetic probe uses deterministic 1280×720 frames, existing adaptive quality settings, and zero/one/two simulated viewers. Three ten-second trials per scenario compare original streaming code from `d228f51` with the candidate. Raw results: `performance-baseline.json` and `performance-after.json`. These are short Python-process measurements, not whole-system or browser benchmarks.

| Median metric per ten-second trial | Before | After |
|---|---:|---:|
| Buffer reads, no viewers | 658 | 216 |
| Buffer reads, one viewer | 652 | 255 |
| Buffer reads, two viewers | 649 | 254 |
| Frames delivered, one viewer | 130 | 129 |
| Frames delivered, two viewers combined | 258 | 258 |
| Process CPU seconds, one viewer | 0.438 | 0.578 |
| Process CPU seconds, two viewers | 0.750 | 0.672 |
| Event-loop delay p95, one viewer (ms) | 13.38 | 10.59 |
| Event-loop delay p95, two viewers (ms) | 13.47 | 12.70 |

Repeated buffer reads decrease about 61–67%, with comparable delivered frames. Shared encoding benefits multiple viewers. One-viewer CPU increases by 0.140 CPU seconds per ten seconds (about 1.4% of one logical core), reflecting the cost of moving work into bounded asynchronous workers; it is not an across-the-board CPU improvement. Trial variation and Windows timer granularity limit these short measurements. Private memory is approximately 211–214 MiB in these synthetic processes and does not explain the reported 8–9 GB total computer memory after ten days.

## Demonstrated corrections

- Abandoned pending sessions expire; duplicate sockets cannot replace live handlers or terminate someone else's session.
- Cancelled/reconnecting viewers cannot accumulate encoding jobs. Native work retains its worker slot until completion. Each viewer has one latest-frame slot.
- Slow viewers do not hold up fast viewers. Frame wake-ups are coalesced, and shared encoded data is limited to current frame variants.
- Failed video attachment preparation releases native captures/writers and partial temporary output. Camera disk cleanup allows only one pending job.
- System-health CPU sampling no longer blocks the API event loop for one second. SQL read work uses the bounded worker pool.
- Polling failures do not create an immediate retry loop; History no longer launches an extra scheduler polling setup. Hidden refresh behavior is retained.
- A 100-frame frontend test updates both image views without rerendering their containing page or losing focus.

## Remaining acceptance

Automated checks: 278 backend tests and 69 frontend tests passed. Production frontend build, resource embedding and isolated Windows PyInstaller packaging succeeded. The packaged executable served 22 byte-matching JavaScript assets, authenticated system health with sample timestamps, and two resource-diagnostic samples. Browser fixture checks covered draft/dropdown retention across scheduler polls, a 25-row page from 1,000 methods, fullscreen/inline synthetic video, narrow layout and a simultaneous status view. A malformed method path in the disposable fixture was corrected before completing those checks.

The N100 must still be tested with its real camera, disk, SQL workload and remote browser. Record each process separately with opt-in resource diagnostics; do not infer a leak from total system RAM. Run three matched real workloads, a 24-hour screening test and a ten-day recording/remote-viewing endurance test. Include scheduler pause/resume/restart/completion alerts and viewer reconnects. Do not claim stable long-term memory or production recording FPS until those tests complete.

## Candidate and rollout

Candidate: `dist/RobotControl-optimized/RobotControl.exe`, accompanied by its entire `_internal` directory. The previous packages and live `data` directory were not replaced. Disposable package-test databases and diagnostic logs are removed before delivery. For deployment, back up the current installation, stop RobotControl normally, and replace the executable and `_internal` together while retaining the installation's existing `data` directory. Keep the previous executable/support directory pair for rollback. Do not run the new and old installations against the same runtime data simultaneously.
