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

- Database page tabs now mirror the scheduling UX: scrollable with mobile labels, and legacy connection chips/metadata were removed so the header no longer shows “Disconnected / Unknown�?placeholders (`frontend/src/pages/DatabasePage.tsx`).
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
- Verify end-to-end that the PyInstaller build serves the embedded frontend with `PYROBOT_SERVE_FRONTEND=1` and that scheduling executes correctly.

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
- Frontend TypeScript build fixed by excluding tests, aligning `import.meta.env.DEV`, and updating validation typings.
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
