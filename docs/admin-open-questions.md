# Admin Consolidation Pending Decisions

## Open Questions
- Where should database maintenance actions (cache clear, health check) live if `/admin` is removed?
- What UI replaces the current user activation flow (`/api/admin/users/*` endpoints)?
- How will Backup and System Config pages route/breadcrumb if the `/admin` hub disappears?
- Which navigation surfaces (tabs, drawer, keyboard shortcuts) need redesign to reflect the new structure?
- Do we keep the `/api/admin/*` namespace or collapse endpoints into other services?
- How will we communicate the admin-only context once the dedicated page goes away?
- What testing or migration plan ensures existing admins are not blocked during the transition?

## Dependencies & Risks
- BackupManager and SystemConfigSettings both assume an `/admin` parent route for return navigation.
- Keyboard shortcut `Alt+6` and various breadcrumbs reference `/admin`; removing it without replacements breaks accessibility aids.
- `SystemStatus` admin fetch currently unused - decide whether to drop the call or surface extra metrics elsewhere.
- Removing the admin page without relocating user management strands the only UI that can toggle account activity.

## Next Checkpoints
- Define the target structure (merge into Monitoring, split into Database, create new Maintenance section, etc.).
- Align backend routing changes with frontend navigation updates.
- Draft migration timeline and owner assignments before beginning refactor.
## Logging Improvements for Continuous Operation
- Current backend logger writes a single session file (`pyrobot_backend_<timestamp>.log`) with no rotation; multi-day runs will create huge files that are hard to search.
- Only the performance logger uses rotation (10MB/5 files). We need a rotation/retention strategy for the primary logs (e.g., daily `TimedRotatingFileHandler` plus severity-specific files and gzip after rotation).
- Consider structured logging (JSON) or at minimum ship logs to an index (Elastic/OpenSearch) so prolonged runs remain searchable.
- Define high-severity alert path (e.g., emit to separate `error.log` + optional email/Slack hook) so multi-day review surfaces critical failures quickly.

## Authentication UX & Security Upgrades
- AuthService keeps users in-memory with hard-coded credentials (`admin`, `hamilton`, `user`); no persistence or password rotation survived across restarts.
- There is no self-service password change, lockout, MFA, or audit trail; idle tokens last 4h (access) / 7d (refresh) with no invalidation on role change.
- Recommend moving users to the SQLite scheduling DB (or dedicated auth DB), adding salted hashes with per-user secrets, password reset flows, and optionally SSO/LDAP integration.
- Frontend currently exposes default credentials on the login screen; remove that copy once onboarding docs exist.

## Automatic Recording Resource Optimizations
- Service polls experiment state every 5s and runs minute-level filesystem sweeps; consider adaptive backoff (e.g., 15-30s when idle, tighten during active experiments) and event-based triggers when Hamilton DB is accessible.
- Recording threads capture 640x480@30fps in software via OpenCV; evaluate GPU-friendly pipelines (FFmpeg/GStreamer) or allow admins to pick lower fps/resolution profiles per schedule.
- ThreadPoolExecutor(4) + frequent globbing can be dialed down by watching filesystem events and batching cleanup.
- Archive workflow always copies + compresses clips immediately after completion; queue heavy work to a background worker so recording threads stay lightweight.

## Scheduling Module Snapshot
- Scheduler engine/service exists but only starts on `/api/scheduling/start-scheduler`; default runtime is "stopped". Need policy for auto-start and watchdog restart.
- Scheduling data persists in `data/pyrobot_scheduling.db` (SQLite). Hamilton integration (ScheduledToRun flags, HxRun.exe detection) logs "not fully implemented" and currently acts as mock if the Windows process/DB are unavailable.
- Queue manager exposes status/conflict APIs, but `hamilton_available` simply negates `is_hamilton_running()`; confirm semantics and add health telemetry before trusting for automation.
- Experiment discovery/import flows write into SQLite but still require manual folder inputs; no end-to-end E2E validation yet. Identify owner/tests before relying on production automation.
- Conflict handling now auto-reschedules blocking overlaps (2-minute delay, up to 3 attempts) before disabling the schedule and surfacing a failure event.
- Manual recovery is enforced via a global scheduler flag (persisted in `SchedulerState`); any aborted run pauses all schedule dispatch until resolved. The `/api/scheduling/*/recovery/*` endpoints and queue status response now include the `manual_recovery` payload so the UI can show the blocking experiment and note.
- Implementation detail: retry bookkeeping lives in scheduler_engine._handle_conflict_retry, which updates failed_execution_count, emits a job_delayed event, and shifts start_time forward to avoid 30-second polling churn.
