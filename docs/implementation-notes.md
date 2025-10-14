# PyRobot Development Log (Chronological)

---

## 2025-10-14 Camera Page Streamlining

- Camera page now focuses on two tabs (Archive + Live Streaming); dropped the inline system-status modal and live camera grid so health info stays on the dedicated System Status screen (`frontend/src/pages/CameraPage.tsx:392-760`).
- Streaming panel shows only session ID and connection state while keeping fullscreen playback support; removed quality/bandwidth/FPS details per UX request (`frontend/src/pages/CameraPage.tsx:660-750`).
- Video archive folders/files wrap cleanly on mobile and always expose action buttons thanks to responsive tweaks and loading spinners (`frontend/src/components/camera/VideoArchiveTab.tsx:200-464`).

## 2025-10-14 Scheduling Recovery Reference & Camera Notes

- Interval miss grace is half the configured interval hours; see `backend/services/scheduling/scheduler_engine.py:575-599` where `_find_due_jobs` computes `grace_period_minutes = (experiment.interval_hours * 60) / 2`.
- Missed runs log `start_time` plus the current timestamp as `end_time`, so execution history shows a long `calculated_duration_minutes`; originates in `_find_due_jobs` (`backend/services/scheduling/scheduler_engine.py:583-599`) and the formatter `get_execution_history` (`backend/services/scheduling/sqlite_database.py:1399-1424`).
- New pre-execution steps register via `_register_builtin_steps` (`backend/services/scheduling/pre_execution.py:103-160`); implement handlers with cleanup similar to `_scheduled_to_run_step`.

## 2025-10-13 Admin User Controls

- Limited the admin API to user email updates and account deletion, adding dedicated endpoints while preventing self-deletion and duplicate email assignment (`backend/api/admin.py`, `backend/services/auth.py`, `backend/services/auth_database.py`).
- Simplified the admin UI to match: user management now supports only editing email addresses or removing accounts, with refreshed UX feedback (`frontend/src/components/UserManagement.tsx`, `frontend/src/pages/AdminPage.tsx`, `frontend/src/services/api.ts`).

## 2025-10-13 Dashboard & Layout Cleanup

- Removed descriptive footer panels from Scheduling and Backup pages to keep the UI focused on actionable controls (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/pages/BackupPage.tsx`).
- Centered About page cards and ensured they stretch evenly by flexing grid items, eliminating the right-leaning layout (`frontend/src/pages/AboutPage.tsx`).
- Streamlined the Dashboard by dropping the Quick Actions card and centering the experiment widget; the latest experiment panel now loads after a 1 s handshake instead of 3 s (`frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ExperimentStatus.tsx`).

## 2025-10-13 Multi-User Concurrency & Token Refresh

- Added optimistic concurrency to schedule update/delete/manual-recovery routes using `If-Unmodified-Since` tokens from the UI; stale submissions now raise HTTP 409 and trigger an automatic reload (`backend/api/scheduling.py`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/services/schedulingApi.ts`, `frontend/src/types/scheduling.ts`).
- Scheduler now exposes `invalidate_schedule` and returns the manual-recovery snapshot as part of `/status/scheduler`, keeping the cache encapsulated and the recovery banner in sync with the 30 s poll (`backend/services/scheduling/scheduler_engine.py`, `frontend/src/hooks/useScheduling.ts`).
- Axios interceptors retry once with the stored refresh token before logging out, and a custom event keeps `AuthContext` aligned when a new access token is issued (`frontend/src/services/api.ts`, `frontend/src/context/AuthContext.tsx`).

## 2025-10-13 Multiline Alert Rendering & Status Dialogs

- Normalized newline handling so backend strings containing `\n` render as real line breaks in shared alerts and restore status dialogs via the new `normalizeMultilineText` helper (`frontend/src/components/ErrorAlert.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/utils/text.ts`).
- Added a reusable `StatusDialog` wrapper to keep success/error feedback consistent on mobile and migrated the scheduling admin panels (`NotificationEmailSettingsPanel`, `NotificationContactsPanel`, `ImprovedScheduleForm`, and `DatabaseRestore`) to use it (`frontend/src/components/StatusDialog.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/components/scheduling/NotificationContactsPanel.tsx`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`).
- Scheduler delete now falls back to the SQLite manager when the in-memory engine isn't loaded, so admins can remove schedules even if the scheduler service is offline (`backend/api/scheduling.py`).
- Database restore kicks off a health-check watcher that clears maintenance mode as soon as the backend responds again instead of waiting the full sixty-second timeout (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-13 Camera Archive Virtualization

- Replaced the archive card-grid with a collapsible tree that virtualizes video rows via `react-window`; per-folder state now lives inside `VideoArchiveTab` and supports optional lazy loading (`frontend/src/components/camera/VideoArchiveTab.tsx`, `frontend/src/types/components.ts`).
- Updated both camera pages to consume the shared archive component so the optimized UI appears regardless of route (`frontend/src/pages/CameraPage.tsx`, `frontend/src/pages/CameraPageRefactored.tsx`).
- Added a full-screen dialog for the live streaming preview triggered from the inline player, closing automatically if the session drops (`frontend/src/pages/CameraPage.tsx`).
- Standardised SQL backup writes to `data/backups` and removed the compressed backup attempt so Express Edition uses the same reliable sqlcmd path as the legacy UI (`backend/config.py`, `backend/services/backup.py`).

## 2025-10-13 Persistent Auth Rework

- Replaced the in-memory AuthService with a SQLite-backed store (`backend/services/auth.py`, `backend/services/auth_database.py`) seeded with `admin / ShouGroupAdmin`, introduced hashed refresh-token tracking, registration, change-password, and admin reset flows (`backend/api/auth.py`, `backend/api/admin.py`, `backend/scripts/auth_cli.py`).
- Added regression tests for the new flows (`backend/tests/test_auth.py`) and CLI helpers for operators; note pytest is required to run the suite.
- Updated the React client with self-serve registration, change-password dialog, and refreshed auth context (`frontend/src/context/AuthContext.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/components/ChangePasswordDialog.tsx`, `frontend/src/App.tsx`, `frontend/src/services/api.ts`).
- Introduced password reset request queue + admin tooling and forgot-password UI (`backend/api/auth.py`, `backend/api/admin.py`, `frontend/src/components/UserManagement.tsx`, `frontend/src/pages/LoginPage.tsx`).
- Hardened live streaming session tracking so stale sessions no longer block new users (`backend/services/live_streaming.py`).
- Tweaked Monitoring page to avoid duplicate headings and hide experiment card in the detail view (`frontend/src/pages/MonitoringPage.tsx`, `frontend/src/components/SystemStatus.tsx`).
- Restored a lightweight `/admin` console that surfaces the new user management tooling and hides non-admin routes (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/pages/AdminPage.tsx`).

## 2025-10-12 Maintenance UX & Modal Alerts

- Added centralized maintenance tracking so destructive workflows (e.g. database restore) trigger a short-lived maintenance window that pauses API polling, surfaces a countdown dialog, and resumes once the backend is reachable (`frontend/src/utils/MaintenanceManager.ts`, `frontend/src/hooks/useMaintenanceMode.ts`, `frontend/src/services/api.ts`).
- Refresh Flow: Database restore confirmations now show a dedicated modal summarizing the operation impact and, on success/failure, follow-up pop-up dialogs ensure mobile users see status immediately (`frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/MaintenanceDialog.tsx`).
- Next session: migrate other admin/scheduling pages to reuse the shared pop-up dialog pattern so error/success feedback is consistent across desktop and mobile.

## 2025-10-12 Connection Locality Detection

- Added `backend/utils/network_utils.py` and `backend/api/dependencies.py` so endpoints can classify requests as local vs remote using IP heuristics. Auth endpoints now attach session locality metadata to login and `/api/auth/me` responses for the frontend to consume.
- Locked down `/api/backup/restore` to local callers via the new dependency and emit structured audit events for restore attempts (`backend/api/backup.py`, `backend/utils/audit.py`). Locality now means loopback-only (127.0.0.1/::1).
- Restricted `/api/database/execute-procedure` to loopback connections, logging every invocation (or error) with the initiating user for audit purposes (`backend/api/database.py`). Deferred: extend checks to additional write endpoints, bubble locality flags into the frontend to hide destructive UI, and surface audit history.
- Scheduling mutations are now loopback-only: create, update, delete, manual recovery, and notification management endpoints depend on the locality guard and emit audit entries (`backend/api/scheduling.py`). Remaining UI work: hide restricted controls when the session is remote.
- Backup creation/deletion and database cache clearing require a loopback connection and log every attempt (`backend/api/backup.py`, `backend/api/database.py`).
- Added modal status dialogs for backup create/restore flows and introduced a maintenance window gate that pauses background API calls and surfaces a countdown dialog after restores (`frontend/src/components/DatabaseRestore.tsx`, `frontend/src/utils/MaintenanceManager.ts`, `frontend/src/components/MaintenanceDialog.tsx`, `frontend/src/services/api.ts`).
- Corrected the restore warning copy so bullet points render properly in the confirmation banner (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-12 Performance Logging Cleanup

- Removed the unused performance logging subsystem (router, middleware, utilities) so the backend stops emitting empty `performance_*.log` files (`backend/api/performance.py`, `backend/middleware/performance.py`, `backend/utils/logger.py`, `backend/main.py`).

## 2025-10-12 Backup Path Persistence

- Pointed the backup service at the managed data directory so PyInstaller builds persist backups beside `PyRobot.exe` rather than the temp `_MEI` unpack location (`backend/services/backup.py`).

## 2025-10-11 Manual Recovery Dropdown

- Swapped the manual recovery recipient text area for a multi-select fed by Notification Contacts, keeping custom addresses visible and clarifying the helper copy (`frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`).
- Passed the contact list through to the email settings panel so selections stay synchronized with the scheduler contact management view (`frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-11 Manual Recovery Distribution

- Manual recovery recipient lists persist in NotificationSettings and flow through the admin API/UI; legacy `PYROBOT_*` email fallbacks were removed so delivery now depends on stored configuration (`backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`, `backend/services/notifications.py`, `backend/tests/test_notifications.py`).
- Hamilton TRC attachments convert to `.log` files with predictable names before mailing, and scheduler alerts prefer the configured distribution list when present (`backend/services/notifications.py`, `backend/tests/test_notifications.py`).
- Restored missing FastAPI imports so the scheduling router initializes correctly in packaged builds (`backend/api/scheduling.py`); rebuilt frontend assets, refreshed embedded resources, and regenerated the PyInstaller executable to capture all changes (`frontend build output`, `backend/embedded_static.py`, `dist/PyRobot.exe` via `build_scripts/pyinstaller_build.py`).

## 2025-10-10 Long-Run Alerts & SMTP Test Harness

- Scheduler watchdog now fires long-running alerts strictly at 2x the estimated duration and falls back to a stitched MP4 summary built from the latest three rolling clips (recorded at 7.5 fps) when no experiment archive exists (`backend/services/notifications.py`, `backend/services/scheduling/scheduler_engine.py`, `backend/tests/test_notifications.py`).
- Camera recorder targets 7.5 fps for rolling clips and the unit suite asserts the new writer configuration (`backend/services/camera.py`, `backend/tests/test_camera.py`).
- Added `/api/scheduling/notifications/settings/test`, UI wiring, and build safeguards: Send Test Email button, hook integration, and preserved `dist/data/backups` during PyInstaller rebuilds (`backend/api/scheduling.py`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/services/schedulingApi.ts`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`, `build_scripts/pyinstaller_build.py`).

## 2025-10-10 SMTP Config Panel

- Swapped Fernet secrets for Windows DPAPI so SMTP credentials encrypt/decrypt without a shared key (`backend/utils/secret_cipher.py`, `backend/services/notifications.py`).
- Added NotificationSettings persistence + admin API and extended the scheduling UI with an Email Settings tab (DPAPI-backed password storage) (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`).
- Added encrypted NotificationSettings storage and admin API so the scheduler reads SMTP host/sender/password from SQLite instead of environment variables (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `backend/services/notifications.py`).
- Extended the scheduling admin UI with an Email Settings tab that encrypts passwords via Fernet and guides operators through key setup (`frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).

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

- Normalized scheduling ISO timestamps to local naive datetimes so non-UTC systems no longer see start-time drift (`backend/utils/datetime.py`, `backend/api/scheduling.py`, `backend/models.py`, `backend/services/scheduling/*`, `backend/services/experiment_monitor.py`).
- Routed experiment archiving through StorageManager to keep original one-minute clips and surface richer metadata to automation (`backend/services/camera.py`, `backend/services/automatic_recording.py`, `backend/tests/test_camera.py`).
- Resolved PyInstaller data paths so packaged builds read/write the real data/videos directory beside the executable (`backend/config.py`).

## 2025-10-09 Camera Resolution ASCII Fix

- Replaced the multiplication symbol in camera resolution displays and fullscreen hint with ASCII `x` so Windows clients no longer see kanji U+8133 (Japanese "brain") in place of the separator (`frontend/src/pages/CameraPage.tsx`, `frontend/src/components/CameraViewer.tsx`).

## 2025-10-08 Streaming Guard & UI Polish (Binary Refresh)

- Refined the streaming CPU guard to sample the PyRobot process with a rolling window, preventing false "CPU limit reached" shutdowns while keeping the soft/hard protections (`backend/services/live_streaming.py`).
- Widened scheduling layout padding so desktop cards and calendars no longer hug the container edges (`frontend/src/pages/SchedulingPage.tsx`).
- Execution history's experiment filter now includes a short schedule-id suffix to distinguish duplicate method names (`frontend/src/components/ExecutionHistory.tsx`).
- Restored the lightweight camera live-stream view without frame counters while retaining start/stop controls (`frontend/src/pages/CameraPage.tsx`).
- Rebuilt the frontend, re-embedded static assets, and produced a fresh PyInstaller binary with the updated bundle (`build_scripts/embed_resources.py`, `build_scripts/pyinstaller_build.py`, `dist/PyRobot.exe`).

## 2025-10-08 Streaming Guard & Scheduling Polish

- Reworked the streaming CPU guard to sample the PyRobot process, smooth spikes, and require consecutive hits before terminating sessions (`backend/services/live_streaming.py`).
- Widened scheduling tab padding and card content so laptop layouts breathe instead of hugging the edges (`frontend/src/pages/SchedulingPage.tsx`).
- Execution history's experiment filter now shows each schedule's short id alongside the name to avoid duplicate labels (`frontend/src/components/ExecutionHistory.tsx`).

## 2025-10-08 Scheduling Layout & Streaming Consolidation

- Reordered top-level navigation so System Status sits beside About, updating both the desktop tabs and mobile drawer (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`).
- Relaxed the scheduling page spacing with wider gutters, roomier tabs, and padded cards while keeping manual recovery and calendar content consistent (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/ScheduleList.tsx`).
- Extended monitoring data to carry streaming status and reliable timestamps, then surfaced the service metrics on the System Status dashboard (`frontend/src/hooks/useMonitoring.ts`, `frontend/src/components/SystemStatus.tsx`, `frontend/src/components/MonitoringDashboard.tsx`).
- Streamlined the Camera streaming tab to just session controls, removing the metrics card and video preview while keeping start/stop flows intact (`frontend/src/pages/CameraPage.tsx`).

## 2025-10-08 Monitoring & Scheduling Tweaks

- Refined the scheduling form so the improved modal now powers both create and edit flows, requires an explicit experiment prep option, and removes the unused Hamilton tables flag (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Mobile monitoring header now wraps cleanly, simplifies the status chip, and keeps last-update info readable at small widths (`frontend/src/components/MonitoringDashboard.tsx`).
- Latest bundle embedded and PyInstaller binary refreshed after UI fixes (`backend/embedded_static.py`).

## 2025-10-08 Navigation & Mobile Polish

- Database tables lose the nested scroll on phones by relaxing the card height on `DatabasePage` and only constraining `TableContainer` on md+ breakpoints so pagination stays in view (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).
- Removed the unused Admin surface, renamed Monitoring to System Status, and introduced a dedicated About page with navigation hooks across tabs, the mobile drawer, breadcrumbs, and keyboard shortcuts (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`, `frontend/src/pages/AboutPage.tsx`).
- Compact experiment summaries now wrap their header/status controls and stack timestamps on narrow widths, avoiding truncated chips and timestamps (`frontend/src/components/ExperimentStatus.tsx`).
- Dashboard quick actions point at the new System Status route and expose a shortcut to the About page while retiring the redundant system info card (`frontend/src/pages/Dashboard.tsx`).
- Added a PyInstaller runtime hook that filters the deprecated `pkg_resources` warning so packaged binaries start cleanly, and wired it into the spec (`build_scripts/runtime_hooks/silence_pkg_resources_warning.py`, `Py
