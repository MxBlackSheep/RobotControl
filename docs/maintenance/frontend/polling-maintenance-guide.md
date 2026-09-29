# Polling without duplicate work

`useSerialPolling` owns a single timer, abort controller and in-flight request. Requests with the same owner cannot overlap; changing identity or unmounting aborts and invalidates the old response. Interval timing resumes after a request settles. Failed reads preserve the last successful data. It does not inspect document visibility: hidden views continue their existing refresh policy.

System Status refreshes normally every 60 seconds and retries failed reads every 30 seconds when automatic recovery is enabled. Its component must not add a second retry timer. Execution History uses the same owner, fetching once by default and every 30 seconds if automatic refresh is selected. An interval of zero means manual refresh after the initial read.

History must not instantiate `useScheduling`: doing so loads schedules/calendar/archive and starts another scheduler poller. The Scheduling page remains the owner of those requests. Queue/scheduler API reads share concurrent requests for the same login only; results are never cached after completion. Do not coalesce writes or requests requiring fresh dispatch authorization.

Known limitation, reviewed 26 September 2026: raw-fetch callers do not have a request deadline. A pending response can block the owner indefinitely; manual Refresh joins the same request rather than replacing it. System Status can retain its previous connected indicator while stuck. HTTP failures that actually reject still retry normally. This requires bounded cancellation/recovery, not a return to overlapping polling. See `docs/remote-connection-review-2026-09-26.md` for the browser reproduction and distinction from pre-HTTP network timeouts.
