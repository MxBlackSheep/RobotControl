# Remote connection review — 26 September 2026

## Assessment

The reported symptom is a browser connection-timeout page when opening RobotControl through a cross-country ZeroTier connection; the application remains usable locally on the LabPC. The available evidence favors intermittent network-path reachability over the resource-saving changes as the primary cause. This is not a proven diagnosis of a particular ZeroTier peer, router, firewall or ISP.

There is also a confirmed frontend recovery defect introduced by serialized polling. It can make System Status stay stale after a request stalls, but cannot by itself prevent a TCP connection to the website.

## Live connection evidence

An initial direct HTTP request returned 200 in 0.94 seconds. A subsequent 12-request sample alternated the root page and dependency-free `/health`, bypassing HTTP proxies:

| Observation | Result |
| --- | --- |
| TCP connection timeouts | 7 of 12 requests, after an 8-second connection deadline |
| Successful HTTP responses | 5 of 12, all HTTP 200 |
| First successful connection after failures | 7.343 seconds |
| Remaining successful connections | 0.319–0.331 seconds |
| First response byte after TCP connected | 0.302–0.304 seconds for all successful requests |

Thus most observed delay occurred before HTTP processing. The health route does not run camera, SQL or authentication work. The probes made no changes or authenticated operations.

Limitations: these probes ran from the development VM, whose route uses its Hyper-V gateway, not a local ZeroTier virtual adapter. Its path need not be identical to the affected browser's path. A ZeroTier service exists here, but peer queries could not read its local CLI authentication file; no credentials were exposed and no permissions or settings were changed. The local log copies contain no corresponding incident-level remote error. Working local access is the operator's observation, not a simultaneous measurement from this review.

## Code findings

1. **Confirmed: stalled System Status requests do not recover.** `frontend/src/hooks/useSerialPolling.ts` returns the existing in-flight promise and schedules another poll only after completion. `useMonitoring.ts` combines three raw `fetch` requests without a deadline. If one response remains pending, no new poll begins, Refresh remains disabled, and the previous connected indicator can persist. Commit `f72b074` introduced serialization; the earlier interval could issue another request. Keep serialization, but add a bounded request/body deadline, an explicit abort-and-retry path and truthful stale-state reporting. Camera control polling uses the same hook with raw fetch and merits the same protection. This was reproduced in an actual browser, without changing production code.
2. **Camera-specific risk: five-second delivery deadline closes the viewer.** Commit `c42c672` added `asyncio.timeout(5)` around encoding plus WebSocket delivery in `backend/services/live_streaming.py`. A slow send or encoder wait can therefore end the session. The frontend close handler marks it disconnected and clears the image; it does not automatically reconnect. This is a code-review finding, not a reproduced cross-country camera failure. It concerns camera viewing after page load, not the initial TCP connection.
3. **Existing behaviors, not newly introduced network settings.** CPU protection thresholds of 75/90 percent and termination after three high samples existed before the optimization. The reviewed changes do not reconfigure ZeroTier, Windows networking, power settings or the application's listening address. The shared Axios client already has a ten-second deadline; its timeout message can mention the database even when transport delay is responsible. System Status uses raw fetch instead and does not inherit that deadline.

## Reproducible browser evidence

The disposable fixture bundles the unchanged production `SystemStatus`, authentication provider and monitoring hooks and uses actual browser HTTP requests. It supplies synthetic API responses and a disposable local token; no robot services, SQL database or deployment data are used.

- Normal responses loaded successfully.
- A health response was held for **99.211 seconds**. During that interval, there were **zero replacement monitoring requests**, Refresh stayed disabled, and the stale connected icon stayed visible across 50 recorded browser samples.
- Allowing new requests at the server did not unblock the existing request. Releasing that response immediately restored the display.
- An explicit HTTP 502 instead displayed the connection error and automatically recovered after **30.030 seconds**, showing that pending and failed requests follow different paths.
- The executable available under the local deployment folder contains source maps matching the reviewed `useSerialPolling.ts`, `useMonitoring.ts` and `services/api.ts`. This does not independently establish the executable on the remote LabPC.

Harnesses and timestamped JSON evidence were retained locally under `recovery/20260926-remote-investigation/`, excluded from Git. On 29 September 2026 the harnesses moved to `frontend/e2e/status-stall-probe.py` and `backend/scripts/network_probe.py`; that evidence folder was removed. `scenarios.md` was written before reproduction code. Run `serve_probe.py` with the project Python and follow its browser controls; run `network_probe.py` for a fresh timing capture. The disposable browser/server and generated bundle were cleaned up. This was a browser/HTTP integration reproduction, not a complete real-robot E2E or endurance test.

## Recommended next step

Investigate the tunnel path first; do not roll back the optimizations wholesale. During an actual timeout, capture peer state on both the affected remote computer and LabPC from an administrator terminal:

```powershell
zerotier-cli info
zerotier-cli peers
```

If the CLI is not on PATH on Windows, the installed executable also accepts `-q`, for example `& "$env:ProgramData\ZeroTier\One\zerotier-one_x64.exe" -q peers`. Match the LabPC node ID from its `info` output to the peer row on the remote computer. Do not mistake an unrelated peer's RELAY state for the LabPC's path. Compare remote TCP timings with `http://127.0.0.1:8005/health` on the LabPC during the same interval. A remote TCP failure with a fast local health response strongly isolates the remote path; slow established HTTP responses locally and remotely instead require backend investigation.

ZeroTier documents [checking peers on both nodes](https://docs.zerotier.com/faq/connectionissues/) and explains that [relaying can add latency and packet loss](https://docs.zerotier.com/faq/relaying/). Relay use was not established here. No firewall, tunnel, power setting or production code was changed in this review.
