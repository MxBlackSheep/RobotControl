# Scheduling Module Changes (2025-09-29)

## Frontend
- Updated `frontend/src/services/schedulingApi.ts` and `frontend/src/components/scheduling/FolderImportDialog.tsx` so folder imports send `{ files: [...] }`, matching the backend payload contract.
- Adjusted `ScheduleList` to keep the table visible during refreshes, only showing the full-screen spinner for initial loads, and added an inline `LinearProgress` banner while background updates run.

## Backend
- Relaxed `/api/scheduling/experiments/import-files` to accept either an array or `{ files: [...] }` payload; ensures older clients still work.
- Added a post-run abort check in `ExperimentExecutor.execute_experiment` so manual Hamilton aborts flip successful exits into failures and trigger manual recovery.
- Exposed `SchedulerEngine.get_manual_recovery_state()` to support queue-status queries for both dev and packaged builds.

## Packaging / Build
- Re-embedded the freshly built frontend (`build_scripts/embed_resources.py`).
- Regenerated `dist/PyRobot.exe` via `build_scripts/pyinstaller_build.py`; latest binary contains the scheduling fixes above.

## Operational Notes
- Manual recovery remains a global flag persisted in SQLite; the new helper simply surfaces it without adding new state.
- Abort detection now runs both before queuing and immediately after HxRun completion. A manual abort should surface in the UI as a failed run requiring recovery.
- Note: Current packaged build still fails to detect aborted runs on the live system; revisit abort-state polling once session tokens reset.
- Adjusted abort-state lookup to search by full path, stems, and .hsl/.med variants so Hamilton DB entries such as C:\\...\\MethodName.hsl match scheduled experiments.
- Expanded Hamilton abort detection to search for method names using full paths, stems, and .hsl/.med variants so manual aborts logged with absolute paths are caught.
- Removed the scheduling page panel's overflow: hidden so the page regains browser scrollbars after dialog interactions.
- TODO: mid-run aborts don¡¯t surface until HxRun writes the final row; we should hook into HxRun.exe state or live log events to catch aborts immediately.
- Hardened ExecutionHistory date rendering: invalid/empty timestamps now display N/A instead of Invalid Date.
- 2025-09-30: Frontend scheduling page now polls scheduler status every 30 seconds, hides manual start/stop controls, and adds a dedicated Manual Recovery tab.
- Known issue: "once" schedules flagged for manual recovery will currently requeue themselves after the flag is cleared. Operators should deactivate or delete the schedule manually until we design a smarter resume policy.
