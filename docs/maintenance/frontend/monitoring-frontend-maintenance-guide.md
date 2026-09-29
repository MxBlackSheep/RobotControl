# Frontend Monitoring Maintenance Guide

`pages/MonitoringPage.tsx` is the active System Status page. It owns exactly one
`useMonitoring()` call. Its status chips, resource cards and details are presentation
only. Do not call `useMonitoring()` a second time elsewhere on the page: each call
starts another polling owner.

## Data and state

`useMonitoring` reads `/api/monitoring/experiments`, `/api/monitoring/system-health`
and `/api/camera/streaming/status` through one serial cycle. The normal interval is
60 seconds; failed reads retry after 30 seconds. Unmount invalidates and aborts the
owner. Manual Refresh joins an existing request. This hook currently uses REST,
not WebSockets, despite some older type names/comments.

Database connection and streaming availability are independent of CPU/memory/disk
usage. Never infer service health from a low CPU reading. Missing values display
an em dash or Unavailable. A failed cycle retains the previous reading, marks it
Stale data and displays the last reading time. The Refresh control is disabled
while a read is pending. Details expand without starting requests.

The neutral **Live view enabled/disabled** chip reports the service configuration.
It does not claim that a camera is connected, a frame is fresh, or recording is
active. The single **Connection details** disclosure contains database/server/mode
and live-view slots in use. Slots count all registered sessions, including a
pending connection or a paused session; do not rename this to connected viewers.
Database error text stays above the resource cards so collapsing details cannot
hide a failure.

Do not restore the old streaming utilization or bandwidth readouts. The backend
`resource_usage_percent` is process CPU with a system-CPU fallback, not a streaming
load percentage. `total_bandwidth_mbps` counts JPEG payload bytes and updates only
when frames are sent, so it can remain unchanged after delivery stops. Neither
belongs in this operator overview without a stronger metric contract. The regular
CPU/memory/disk cards continue to use the system-health sampler.

A held raw-fetch request still has no deadline; this existing limitation is
recorded in `polling-maintenance-guide.md`. This UI change does not alter the
shared hidden-document polling policy.

## Layout and verification

Use the overview PageContent pattern, one PageHeader and theme palette tokens.
Resource cards become one column on phones; the one connection disclosure is
collapsed by default and works with keyboard Enter/Space. Keep explanations out
of metric cards.

Run `npm run build` then `npx playwright test` from `frontend`. The
`system-pages.spec.ts` checks that one Refresh issues one system-health request,
a disconnected database remains an error with low CPU usage, unavailable live view
is not shown as healthy, and failed refresh retains explicitly stale data. It also
checks compact connection details at 320px and 1280px, keyboard expansion, visible
database failures, omission of ambiguous figures and screenshots. The
appearance suite saves phone/desktop dark screenshots. See `frontend/e2e/README.md`
for reports, disposable fixtures and packaged verification.
