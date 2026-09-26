# Frontend Monitoring Maintenance Guide

`pages/MonitoringPage.tsx` is the active System Status page. It owns exactly one
`useMonitoring()` call. Its status chips, resource cards and details are presentation
only. Do not mount the older `MonitoringDashboard` and `SystemStatus` components
under this page: each starts another polling owner. They remain as legacy code;
neither is imported by an active route.

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

A held raw-fetch request still has no deadline; this existing limitation is
recorded in `polling-maintenance-guide.md`. This UI change does not alter the
shared hidden-document polling policy.

## Layout and verification

Use the overview PageContent pattern, one PageHeader and theme palette tokens.
Resource cards become one column on phones; service details are independently
expandable. Keep explanations out of metric cards.

Run `npm run build` then `npx playwright test` from `frontend`. The
`system-pages.spec.ts` checks that one Refresh issues one system-health request,
a disconnected database remains an error with low CPU usage, unavailable streaming
is not shown as healthy, and failed refresh retains explicitly stale data. The
appearance suite saves phone/desktop dark screenshots. See `frontend/e2e/README.md`
for reports, disposable fixtures and packaged verification.
