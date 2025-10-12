## 2025-10-12 Backup Path Persistence

- Pointed the backup service at the managed data directory so PyInstaller builds persist backups beside `PyRobot.exe` rather than the temp `_MEI` unpack location (backend/services/backup.py).

## 2025-10-11 Manual Recovery Dropdown

- Swapped the manual recovery recipient text area for a multi-select fed by Notification Contacts, keeping custom addresses visible and clarifying the helper copy (frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx).
- Passed the contact list through to the email settings panel so selections stay synchronized with the scheduler contact management view (frontend/src/pages/SchedulingPage.tsx).

## 2025-10-11 Manual Recovery Distribution

- Manual recovery recipient lists persist in NotificationSettings and flow through the admin API/UI; legacy `PYROBOT_*` email fallbacks were removed so delivery now depends on stored configuration (backend/api/scheduling.py, backend/services/scheduling/sqlite_database.py, backend/services/notifications.py, backend/tests/test_notifications.py).
- Hamilton TRC attachments convert to `.log` files with predictable names before mailing, and scheduler alerts prefer the configured distribution list when present (backend/services/notifications.py, backend/tests/test_notifications.py).
- Restored missing FastAPI imports so the scheduling router initializes correctly in packaged builds (backend/api/scheduling.py); rebuilt frontend assets, refreshed embedded resources, and regenerated the PyInstaller executable to capture all changes (frontend build output, backend/embedded_static.py, dist/PyRobot.exe via build_scripts/pyinstaller_build.py).

## 2025-10-10 Long-Run Alerts & SMTP Test Harness

- Scheduler watchdog now fires long-running alerts strictly at 2x the estimated duration and falls back to a stitched MP4 summary built from the latest three rolling clips (recorded at 7.5 fps) when no experiment archive exists (backend/services/notifications.py, backend/services/scheduling/scheduler_engine.py, backend/tests/test_notifications.py).
- Camera recorder targets 7.5 fps for rolling clips and the unit suite asserts the new writer configuration (backend/services/camera.py, backend/tests/test_camera.py).
- Added /api/scheduling/notifications/settings/test, UI wiring, and build safeguards: Send Test Email button, hook integration, and preserved dist/data/backups during PyInstaller rebuilds (backend/api/scheduling.py, frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx, frontend/src/services/schedulingApi.ts, frontend/src/hooks/useScheduling.ts, frontend/src/pages/SchedulingPage.tsx, build_scripts/pyinstaller_build.py).

## 2025-10-10 SMTP Config Panel



- Swapped Fernet secrets for Windows DPAPI so SMTP credentials encrypt/decrypt without a shared key (backend/utils/secret_cipher.py, backend/services/notifications.py).

- Added NotificationSettings persistence + admin API and extended the scheduling UI with an Email Settings tab (DPAPI-backed password storage) (backend/services/scheduling/sqlite_database.py, backend/api/scheduling.py, frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx).



- Added encrypted NotificationSettings storage and admin API so the scheduler reads SMTP host/sender/password from SQLite instead of environment variables (backend/services/scheduling/sqlite_database.py, backend/api/scheduling.py, backend/services/notifications.py).



- Extended the scheduling admin UI with an Email Settings tab that encrypts passwords via Fernet and guides operators through key setup (

rontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx, 

rontend/src/pages/SchedulingPage.tsx, 

rontend/src/hooks/useScheduling.ts).







## 2025-10-10 Scheduler SQLite Def Fix



- Removed the duplicated, truncated `_row_to_scheduled_experiment` helper that left a dangling try block and broke PyInstaller execution (`backend/services/scheduling/sqlite_database.py`).

- Verified the corrected module via `python -m compileall backend/services/scheduling/sqlite_database.py` to ensure the packaged build loads cleanly.



## 2025-10-09 Scheduler Watchdog & Admin Notifications



- Implemented long-running and abort alert dispatch with notification logging, attachment bundling, and contact cache refresh (`backend/services/scheduling/scheduler_engine.py`, `backend/services/notifications.py`, `backend/services/scheduling/sqlite_database.py`).

- Added admin-facing notifications tab with contact CRUD, filterable delivery history, and surfaced latest alert status on schedule detail cards (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/scheduling/NotificationContactsPanel.tsx`, `frontend/src/hooks/useScheduling.ts`).

- Extended schedule form to select contacts and wired notification log API plus persistence helpers; added backend tests covering notification logging CRUD (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `backend/api/scheduling.py`, `backend/tests/test_notification_logging.py`).

## 2025-10-09 Notification Contact Cache Bridge



- Added scheduling database-manager wrappers for contact CRUD so API and future services reuse the same SQLite helpers and keep timestamps aligned (`backend/services/scheduling/database_manager.py`).

- Scheduler now caches notification contacts and refreshes them on demand for upcoming alert logic (`backend/services/scheduling/scheduler_engine.py`).

- Contact management API endpoints trigger a cache refresh after create/update/delete operations to keep the engine in sync (`backend/api/scheduling.py`).



## 2025-10-09 Scheduling TZ & Video Archive Adjustments



- Normalized scheduling ISO timestamps to local naive datetimes so non-UTC systems no longer see start-time drift (backend/utils/datetime.py, backend/api/scheduling.py, backend/models.py, backend/services/scheduling/*, backend/services/experiment_monitor.py).

- Routed experiment archiving through StorageManager to keep original one-minute clips and surface richer metadata to automation (backend/services/camera.py, backend/services/automatic_recording.py, backend/tests/test_camera.py).

- Resolved PyInstaller data paths so packaged builds read/write the real data/videos directory beside the executable (backend/config.py).



## 2025-10-09 Camera Resolution ASCII Fix



- Replaced the multiplication symbol in camera resolution displays and fullscreen hint with ASCII `x` so Windows clients no longer see kanji U+8133 (Japanese "brain") in place of the separator (`frontend/src/pages/CameraPage.tsx`, `frontend/src/components/CameraViewer.tsx`).

## 2025-10-08 Streaming Guard & UI Polish (Binary Refresh)



- Refined the streaming CPU guard to sample the PyRobot process with a rolling window, preventing false "CPU limit reached" shutdowns while keeping the soft/hard protections (`backend/services/live_streaming.py`).

- Widened scheduling layout padding so desktop cards and calendars no longer hug the container edges (`frontend/src/pages/SchedulingPage.tsx`).

- Execution history's experiment filter now includes a short schedule-id suffix to distinguish duplicate method names (`frontend/src/components/ExecutionHistory.tsx`).

- Restored the lightweight camera live-stream view without frame counters while retaining start/stop controls (`frontend/src/pages/CameraPage.tsx`).

- Rebuilt the frontend, re-embedded static assets, and produced a fresh PyInstaller binary with the updated bundle (`build_scripts/embed_resources.py`, `build_scripts/pyinstaller_build.py`, `dist/PyRobot.exe`).

## 2025-10-08 Streaming Guard & Scheduling Polish



- Reworked the streaming CPU guard to sample the PyRobot process, smooth spikes, and require consecutive hits before terminating sessions (backend/services/live_streaming.py).

- Widened scheduling tab padding and card content so laptop layouts breathe instead of hugging the edges (frontend/src/pages/SchedulingPage.tsx).

- Execution history's experiment filter now shows each schedule's short id alongside the name to avoid duplicate labels (frontend/src/components/ExecutionHistory.tsx).

## 2025-10-08 Scheduling Layout & Streaming Consolidation



- Reordered top-level navigation so System Status sits beside About, updating both the desktop tabs and mobile drawer (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`).

- Relaxed the scheduling page spacing with wider gutters, roomier tabs, and padded cards while keeping manual recovery and calendar content consistent (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/ScheduleList.tsx`).

- Extended monitoring data to carry streaming status and reliable timestamps, then surfaced the service metrics on the System Status dashboard (`frontend/src/hooks/useMonitoring.ts`, `frontend/src/components/SystemStatus.tsx`, `frontend/src/components/MonitoringDashboard.tsx`).

- Streamlined the Camera streaming tab to just session controls, removing the metrics card and video preview while keeping start/stop flows intact (`frontend/src/pages/CameraPage.tsx`).

## 2025-10-08 Monitoring & Scheduling Tweaks



- Refined the scheduling form so the improved modal now powers both create and edit flows, requires an explicit experiment prep option, and removes the unused Hamilton tables flag (frontend/src/components/scheduling/ImprovedScheduleForm.tsx, frontend/src/pages/SchedulingPage.tsx, frontend/src/hooks/useScheduling.ts).

- Mobile monitoring header now wraps cleanly, simplifies the status chip, and keeps last-update info readable at small widths (frontend/src/components/MonitoringDashboard.tsx).

- Latest bundle embedded and PyInstaller binary refreshed after UI fixes (backend/embedded_static.py).



# Implementation Notes



Refer to `AGENTS.md` for the day-to-day runbook; this file captures development-facing context extracted from recent session notes.



## 2025-10-08 Navigation & Mobile Polish



- Database tables lose the nested scroll on phones by relaxing the card height on `DatabasePage` and only constraining `TableContainer` on md+ breakpoints so pagination stays in view (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).

- Removed the unused Admin surface, renamed Monitoring to System Status, and introduced a dedicated About page with navigation hooks across tabs, the mobile drawer, breadcrumbs, and keyboard shortcuts (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`, `frontend/src/pages/AboutPage.tsx`).

- Compact experiment summaries now wrap their header/status controls and stack timestamps on narrow widths, avoiding truncated chips and timestamps (`frontend/src/components/ExperimentStatus.tsx`).

- Dashboard quick actions point at the new System Status route and expose a shortcut to the About page while retiring the redundant system info card (`frontend/src/pages/Dashboard.tsx`).

- Added a PyInstaller runtime hook that filters the deprecated `pkg_resources` warning so packaged binaries start cleanly, and wired it into the spec (`build_scripts/runtime_hooks/silence_pkg_resources_warning.py`, `PyRobot.spec`).

- Scheduling history now loads globally with per-experiment filters, improved status chips, and reliable durations, while the status summary reflects live engine state and derived upcoming events (`frontend/src/components/ExecutionHistory.tsx`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`).

- Monitoring dashboard header is now mobile-friendly with cleaner status copy, and the scheduling form drives both create/edit flows with required experiment prep options while retiring unused Hamilton flags (`frontend/src/components/MonitoringDashboard.tsx`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`).



## 2025-10-07 Responsive Database & History Retention



- Database page tabs now mirror the scheduling UX: scrollable with mobile labels, and legacy connection chips/metadata were removed so the header no longer shows “Disconnected / Unknown?placeholders (`frontend/src/pages/DatabasePage.tsx`).

- Tight viewports get a more usable table pager—`TablePagination` wraps controls with larger touch targets when vertical space is constrained (`frontend/src/components/DatabaseTable.tsx`).

- Job execution records survive schedule deletion by archiving into a new `JobExecutionsArchive` table; history/summary queries now union current and archived rows with schedule snapshots (`backend/services/scheduling/sqlite_database.py`).

- Packaging workflow remains: `npm run build`, `python build_scripts/embed_resources.py`, `python build_scripts/pyinstaller_build.py` to refresh the single-file binary (`dist/PyRobot.exe`).



## 2025-10-07 Backup UX & Packaging



- Database restore screen now lets admins capture a managed `.bak/.json` pair before restoring. Added a `Create JSON Backup` action and dialog that calls `/api/admin/backup/create`, refreshes the managed list, and auto-selects the new file (`frontend/src/components/DatabaseRestore.tsx`).

- The dashboard experiment status chip swaps patterned backgrounds for accessible solid colors, improving readability in compact mode (`frontend/src/components/ExperimentStatus.tsx`).

- Removed the redundant queue-status tab from scheduling while keeping overview metrics in place (`frontend/src/pages/SchedulingPage.tsx`).

- Post-change workflow: `npm run build`, `python build_scripts/embed_resources.py`, and `python build_scripts/pyinstaller_build.py` produce `dist/PyRobot.exe` with the refreshed embedded frontend (`backend/embedded_static.py` regenerated).



## 2025-09-26 Session



### Completed Work

- Added conflict-aware retry handling to the scheduler engine (`backend/services/scheduling/scheduler_engine.py`):

  - Blocking overlaps auto-reschedule with a two-minute delay for up to three attempts.

  - Retry state emits `job_delayed` events and disables schedules after retries exhaust.

- Documented the conflict retry behaviour in `docs/admin-open-questions.md`.

- Rebuilt the frontend (`npm run build`) and re-embedded assets into `backend/embedded_static.py` via `embed_resources.py`.

- Produced a new PyInstaller binary (`dist/PyRobot.exe`) using `build_scripts/pyinstaller_build.py`.



### Afternoon Implementation Summary

- Scheduler now reads HamiltonVectorDB for the latest run state prior to dispatch; aborted/error experiments are auto-flagged for manual recovery (`backend/services/scheduling/database_manager.py`, `scheduler_engine.py`).

- Recovery actions trigger SMTP alerts driven by `PYROBOT_SMTP_*` and `PYROBOT_ALERT_RECIPIENTS`; configuration lives in `backend/services/notifications.py`.

- The frontend scheduling sidebar now uses `ScheduleActions`, keeping recovery status and CRUD flows in sync (`frontend/src/pages/SchedulingPage.tsx`, `components/ScheduleActions.tsx`).

- TypeScript services/hooks gained normalized scheduling payloads and execution-history helpers; `npm run build` is clean after removing CRLF artefacts.

- Added backend tests covering notification plumbing and the pre-execution pipeline (`backend/tests/test_notifications.py`, `backend/tests/test_scheduling_pipeline.py`).



### Follow-Ups

- Surface the new `job_delayed` retry state in the scheduling UI (status chip, calendar notes, related affordances).

- Define and implement manual-recovery flows for aborted experiments, including UI messaging and notifications.

- Evaluate email/alert hooks once manual recovery semantics are locked down.

- Verify end-to-end that the PyInstaller build serves the embedded frontend with `PYROBOT_SERVE_frontend=1` and that scheduling executes correctly.



### Configuration Notes

- SMTP (optional): expected env vars `PYROBOT_SMTP_HOST`, optional `PYROBOT_SMTP_PORT` (default 587), `PYROBOT_SMTP_USERNAME`, `PYROBOT_SMTP_PASSWORD`, sender via `PYROBOT_SMTP_FROM`, and comma-separated recipients via `PYROBOT_ALERT_RECIPIENTS`. TLS defaults to enabled; override with `PYROBOT_SMTP_USE_TLS` / `PYROBOT_SMTP_USE_SSL`.

- Re-embed the frontend after builds by running `python backend/services/embed_resources.py` prior to packaging.

- If SMTP vars are unset the scheduler logs that email is disabled and continues silently.



### Tomorrow's Kickoff Checklist

1. Re-run `python backend/services/embed_resources.py`, restart the backend, and confirm the new scheduling UI is packaged.

2. Simulate an aborted Hamilton run (or mock via DB) to verify the recovery gate, UI badge, and email emission.

3. Choose alert destinations (email vs Slack) and extend `SchedulingNotificationService` if needed.

4. Audit queue/calendar views so the recovery flag surfaces beyond the sidebar/table chip.

5. Plan UI polish for execution history now that typed accessors are available (success/failure chips, auto-refresh toggles, etc.).



## 2025-09-23 Snapshot

- frontend TypeScript build fixed by excluding tests, aligning `import.meta.env.DEV`, and updating validation typings.

- Backend launched in a dedicated PowerShell window (`Start-Process powershell -NoExit`) with `python main.py --port 8005`; `backend/logs/` generated as part of the run.



## Developer Tips

- Run `npm.cmd run build` inside `frontend/` after TypeScript edits to catch regressions.

- Keep backend logs under `backend/logs/` for easier diffing from packaged runs.

- Use `Start-Process powershell -NoExit` to spawn a persistent backend window when testing APIs.



## Git Workflow

- Initialize the repo with `git init` if needed.

- Stage logical changes via `git add` and commit with descriptive messages.

- Create feature branches per change stream.

- Push to a remote for review once tests pass.

## 2025-10-03 Mobile Access Update

- Added `frontend/src/utils/apiBase.ts` to normalize `VITE_API_BASE_URL`, replacing `localhost` with the client host and trimming slashes so devices on the LAN can reuse the packaged backend origin.

- Updated `frontend/src/services/api.ts` to source Axios `baseURL` from the new helper, falling back to relative paths when no override is supplied.

- Enabled the `@/*` TypeScript alias in `frontend/tsconfig.json` so the helper can be imported consistently.

- Build workflow: run `npm.cmd run build`, `python build_scripts/embed_resources.py`, then `python -m PyInstaller PyRobot.spec` to refresh the embedded bundle.

- Deployment note: leave `VITE_API_BASE_URL` empty (or set to the backend origin) before building so mobile Safari/Chrome point at the correct server automatically.































