# Frontend Monitoring Maintenance Guide

`pages/MonitoringPage.tsx` is the active System status page. It owns exactly one
`useMonitoring()` call. Its status chips, resource cards and details are presentation
only. Do not call `useMonitoring()` a second time elsewhere on the page: each call
starts another polling owner.

## Data and state

`useMonitoring` reads `/api/monitoring/experiments`, `/api/monitoring/system-health`,
`/api/camera/streaming/status` and `/api/monitoring/databases` through one serial cycle; a
failed streaming or databases read leaves only that card unavailable. The normal interval is
60 seconds; failed reads retry after 30 seconds. Unmount invalidates and aborts the
owner. Manual Refresh joins an existing request. This hook currently uses REST,
not WebSockets, despite some older type names/comments. Reads go through the shared
`api` client, so an expired access token is renewed; polling restarts only when the
signed-in user changes. An experiment without a start time keeps `start_time: null`.

Database connection and streaming availability are independent of CPU/memory/disk
usage. Never infer service health from a low CPU reading. The CPU card's detail,
**RobotControl N%**, is `robotcontrol_cpu_percent` (RobotControl's processes as a share of the
machine); while it is null it reads "RobotControl —", never 0 %. Missing values display
an em dash or Unavailable. A failed cycle retains the previous reading, marks it
Stale data and displays the last reading time. The Refresh control is disabled
while a read is pending.

The **Live view** card's Enabled/Disabled chip reports the service configuration.
It does not claim that a camera is connected, a frame is fresh, or recording is
active. Its Sessions row counts all registered sessions, including a pending
connection or a paused session; do not rename this to connected viewers. The
**Databases** card lists every SQL Server connection RobotControl depends on: the built-in
Hamilton connection (`DB_CONFIG_PRIMARY`; run records, labware, backup) and each saved
workspace connection with its uses (viewer, packages, schedules' before-run steps). Each
row has its own state and message; the header is Connected only when every connection is
reported connected, a failure count when any fails, otherwise Partly unknown. An
incomplete reply (`normalizeDatabases`) is Unavailable, never an empty healthy list. After
a failed read both cards keep the last state in neutral colour beside Stale data.

Do not restore the old streaming utilization or bandwidth readouts. The backend
`resource_usage_percent` is process CPU with a system-CPU fallback, not a streaming
load percentage. `total_bandwidth_mbps` counts JPEG payload bytes and updates only
when frames are sent, so it can remain unchanged after delivery stops. Neither
belongs in this operator overview without a stronger metric contract. The regular
CPU/memory/disk cards continue to use the system-health sampler.

A request that never answers is abandoned after 20 seconds and shown as
"Request timed out" (see `polling-maintenance-guide.md`). Hidden pages keep the shared
polling policy.

## Layout and verification

Use the overview PageContent pattern, one PageHeader and theme palette tokens.
Resource cards become one column on phones; the one connection disclosure is
collapsed by default and works with keyboard Enter/Space. Keep explanations out
of metric cards.

Run `npm run build` then `npx playwright test` from `frontend`. The
`system-pages.spec.ts` checks that one Refresh issues one system-health request,
a disconnected database remains an error with low CPU usage, unavailable live view
is not shown as healthy, and failed refresh retains explicitly stale data. It also
checks the connection facts in their cards at 320px and 1280px, visible
database failures, omission of ambiguous figures and screenshots. The
appearance suite saves phone/desktop dark screenshots. See `frontend/e2e/README.md`
for reports, disposable fixtures and packaged verification.
