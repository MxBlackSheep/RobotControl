# SQLite safety and recovery

RobotControl has two local SQLite databases: `robotcontrol_scheduling.db` and `robotcontrol_auth.db` (the authentication filename can be configured). They live under the application's `data` directory. SQL Server backup controls do not back up these files.

## Operator recovery

1. Open Scheduling → Manual Recovery on the local workstation. Every pending recovery appears here, including archived and deleted schedules.
2. Check the robot, complete the physical recovery and close HxRun. Enter a note and confirm the robot is ready. A note is mandatory when the original schedule is missing.
3. Acknowledge each recovery item. This leaves failed schedules inactive and queued jobs paused.
4. Once storage is healthy, maintenance is off and previous runs are reconciled, select **Resume queued jobs**. Due jobs can start immediately. Reactivate the failed schedule separately if it should run again.

Local users and administrators can acknowledge and resume. Remote sessions are read-only. HxRun detection failure blocks these actions. Never edit recovery flags directly in SQLite to bypass a hold.

## Administrator storage review

The local Administration page contains **SQLite storage health** for each database. Preview is read-only. It shows record IDs and repair descriptions, never password hashes or token contents. Apply requires the exact preview token and automatically creates and verifies a SQLite backup first. Backups are retained under `data/backups/sqlite-safety`.

Repairs remove dangling contact/token associations, clear nullable links while retaining history, archive terminal orphan executions, and restore missing recovery holds. They never acknowledge recovery or resume dispatch. A changed database invalidates the preview; preview again. Repairs to scheduling storage require HxRun and owned scheduler executions to be absent.

Unfinished orphan runs have a separate **Reconcile abandoned run** action. Only use it after checking the robot and closing HxRun. Enter a note; the run is archived as cancelled. Pending observations are then closed. Conflicting live/archive outcomes or missing execution history are preserved for offline review. Structural corruption cannot be automatically repaired.

For a live/archive conflict, inspect a stopped, consistent copy of the current deployment database; a pre-repair backup may still contain issues already repaired. Compare the run IDs, schedule IDs, timestamps, recorded outcomes and monitoring history. A stale running archive and a later terminal record require a reviewed correction, not an invented cancellation. Preserve both original records and the source database, retain archive snapshots, record the correction, and keep `resume_required` enabled. Verify SQLite integrity, foreign keys and the health preview before replacement. Never replace a newer deployment database with an older repaired copy. Local database copies and repair reports belong under the Git-ignored `recovery/` folder.

## Storage implementation rules

- Both connection helpers enable and verify foreign keys before any transaction. The lock wait is bounded to two seconds. Existing journal modes are unchanged.
- `SchemaMigrations` records the safety migration. All migration statements commit together; do not catch and continue after an ALTER failure. A missing existing scheduler-state row stays unavailable until reviewed repair.
- `SchedulerSafetyStore` owns recovery transitions. Schedule/global flags, `safety_revision`, `resume_required` and `SchedulerSafetyEvents` are committed together using `BEGIN IMMEDIATE`. Only this code may change recovery columns. Ordinary edits and finalization must not reactivate a flagged or archived schedule.
- Deletion/archive guards run inside the write transaction. Recovery, a running execution or unfinished monitoring prevents deletion/archive. Queued deletion cancels and archives queued executions before the schedule and live children are removed.
- Live execution writes use upsert, not `INSERT OR REPLACE`. Callbacks after deletion update archived history and never recreate live executions. Monitoring snapshots and recovery metadata intentionally survive schedule deletion.
- The scheduler holds `_schedules_lock`, then `_jobs_lock`, for lifecycle changes. Final launch also holds the SQLite connection lock through the durable running-row commit and Popen. Release these locks before waiting for the robot or sending mail. Do not acquire the manual-state lock while already holding the SQLite connection lock.
- A storage exception is not “not found” or “recovery cleared.” It blocks dispatch. When storage becomes readable, the in-process fault is persisted as a resume hold before it is cleared. An already running method is not killed merely because SQLite fails; unfinished observations remain available for reconciliation.
- Safety revision conflicts return 409. Storage failures return 503. Scheduling handlers without asynchronous work use FastAPI's request thread pool so bounded database waits do not block the API event loop.

## API changes

`manual_recovery` retains its existing fields and adds `safety_revision`, `resume_required`, `pending_recoveries`, `schedule_missing`, `storage_healthy`, `storage_error`, and `resume_block_reason`.

- `POST /api/scheduling/recovery/resolve`: `{schedule_id, expected_revision, robot_ready, note, expected_updated_at?}`. `schedule_id` may be null for a global incident with no known origin. The schedule-specific resolve route remains an adapter, but also requires revision and confirmation.
- `POST /api/scheduling/dispatch/resume`: `{expected_revision}`.
- `GET /api/admin/sqlite/{scheduling|authentication}/preview` and `POST .../repair` with `{token}`.
- `POST /api/admin/sqlite/scheduling/reconcile`: `{token, execution_id, robot_ready, note}`.

An acknowledgement response may contain `schedule: null`. A client must refresh after 409 and ask the operator to review again; it must not silently resubmit with a new revision.

## Offline restore

1. Close RobotControl and HxRun. Confirm no RobotControl process remains.
2. Preserve the damaged database and any adjacent `-wal`, `-shm` or `-journal` files together in a separate recovery folder. Do not overwrite the only copy.
3. Use a verified backup from `data/backups/sqlite-safety`. Check it with SQLite `PRAGMA quick_check`; the result must be `ok`. Restore the appropriate database while the application is stopped. Do not mix old journal sidecars with the restored database.
4. Start the application and preview storage health again. Review recovery and execution history before resuming jobs. Authentication restoration also restores the users and credentials from that backup's point in time.
5. Keep the preserved originals until recovery is verified. Ambiguous histories require deliberate comparison, not deleting whichever record is inconvenient.

## Verification

`backend/tests/test_sqlite_safety.py` exercises real temporary SQLite databases, failure injection, stale revisions, concurrent deletion/recovery, reviewed repair and backup preservation. The scheduling/run-monitor/authentication suites cover integration; frontend recovery and health panel tests cover confirmation, permissions and stale previews. Always isolate data paths before importing `backend.main` in test harnesses. Never point tests at a deployed `data` directory or launch real robot methods.

For a separate Windows release, build the frontend, embed it, then run `.venv/Scripts/python.exe build_scripts/pyinstaller_build.py --output-dir dist/sqlite-safety-release`. Use a new empty output directory; the compiled app resolves data relative to its executable. Copy the whole resulting RobotControl folder, including `_internal`, for VM validation. Keep deployment and real-robot acceptance testing separate from isolated software smoke tests.

When updating an existing deployment, stop RobotControl and replace the executable and entire `_internal` folder together from the same build. Rename or remove the old support folder before copying: merging folders can retain obsolete libraries. Preserve the deployment's existing data and configuration; do not overwrite them with development copies.
