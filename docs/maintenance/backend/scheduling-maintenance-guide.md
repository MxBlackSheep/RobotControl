# Scheduling Service Maintenance Guide

## Reviewed database settings (2026-09-28)

Local admins use **Database settings / Schedule preparation / Change setup** to choose an existing
EvoYeast operation connection or the existing Batch SQLite adapter. This does not
add arbitrary SQL or new preparation algorithms. The schedule editor still selects
the experiment/batch, preserving existing preparation tokens.

`lab_settings.py` and `/api/database/tools/scheduling-settings` provide status,
review, apply and cancel. Compatibility checks read required table metadata only;
they never run ResetHamiltonTables or prepare an experiment. Passing does not
prove permissions to execute preparation or the scientific/hardware method.
EvoYeast's ResetHamiltonTables procedure is optional: ordinary experiment selection
does not require it. An explicit reset step still executes transactionally and
blocks launch on failure. Do not restore an unconditional procedure-existence check.
Review tokens are owner-bound, expire after ten minutes, and capture config and
source revisions. Apply repeats safety checks under `database_change_guard` (the
scheduler launch locks), then an IMMEDIATE scheduler-storage transaction. Active
schedules, queued/running work and unresolved recovery block saving.

The current integration keeps its startup snapshot. Atomic saves replace
`data/scheduling-lab.json` for restart and keep startup bytes in
`scheduling-lab.previous.json`; Cancel change restores those exact startup bytes
(or removes the file when the native default was active). Active/pending source
profiles cannot be edited or removed through connection APIs. Use a separate
profile, review, save, restart, then review/rebind existing disabled schedules.
Old schedule bindings never silently switch to the new laboratory. Existing
startup identity/recovery checks remain authoritative, including offline JSON edits.

## SQLite recovery safety (2026-09-14)

Recovery acknowledgement and queued dispatch resumption are separate. Recovery, running executions and unfinished monitoring block schedule deletion/archive inside the database transaction. Ordinary edits must never write recovery columns. Schedule/global recovery changes use one transaction with a safety revision. Use the [SQLite safety guide](sqlite-safety-maintenance-guide.md) for the missing-schedule path, API contracts, lock order, repair workflow and rollback instructions.

This document explains how the scheduling subsystem fits together and how to modify it safely. It is written for developers who are new to the codebase and prefer explicit, step‑by‑step directions.

---

## 1. High-Level Architecture

### Reviewed method path corrections

Use `/experiments/library/{method_id}/path-preview` with `{new_path}` to validate an absolute `.med` file and list all primary and cleanup references. The response includes `expected_revision` and each reference's `updated_at`, active/archive flags and busy state. Busy means a pending, queued or running execution; a Hamilton Paused run still has the running execution lifecycle state. No preview changes data.

Submit `/experiments/library/{method_id}/change-path` with `{new_path, expected_revision, references: [{schedule_id, role, expected_updated_at}]}`. `role` is `primary` or `cleanup`; an empty list changes only the library. Both routes require a local authenticated admin/user. The server validates the file again, rejects another catalogue entry owning the canonical path, and rechecks every selected schedule. An archived or busy schedule cannot be selected. A conflict returns 409; the operator must review again. Never infer selected references from a method name.

`prepare_path_change` performs filesystem work before scheduler locks. `change_library_method_path` takes `_schedules_lock` then `_jobs_lock`, checks queue/running membership, and calls `apply_method_path_change`. That SQLite transaction uses `BEGIN IMMEDIATE`, checks the prepared catalogue snapshot plus schedule versions and pending executions, updates only selected path columns, and commits the catalogue and schedules together. A failure rolls back everything. Refreshed schedule objects replace the cache before either lock is released. Enqueue uses `_jobs_lock`; dispatch reloads the cached schedule, so an older queued object cannot launch an old selected path.

Ordinary schedule edits recheck their version under the same schedule lock immediately before saving; version timestamps compare exactly, including microseconds. Schedule archive actions also load/save under that lock. Keep this coordination when adding other schedule mutations. Path corrections preserve labels, timing, contacts, cleanup labels, execution history, monitoring associations, archive state and original import provenance. They never move files or relaunch runs. The containing folder in the library derives from the current path.

Run `python -m pytest backend/tests/test_method_library.py backend/tests/test_method_path_change.py -q` for archive/restore, legacy records, selected primary/cleanup changes, stale revisions, transaction rollback, enqueue/edit/archive races and preservation of paused execution observations.

### Method import (catalogue metadata only)

The method library uses `ExperimentMethods.archived`, `revision`, `path_status`, `last_checked_at` and `validation_reason`; initialization adds missing columns without replacing records or changing old `is_valid` values. `/experiments/library` returns all entries with primary/cleanup schedule references. `/library/check` persists per-method validation outcomes, and `PATCH /library/{id}` archives/restores with an expected revision. These operations require a local admin/user. Path status and archive are independent. New choices use valid, unarchived entries; existing schedules keep their saved paths. Imports increment revisions, preserve archive/provenance and prefer a unique unarchived canonical match. Ambiguous legacy duplicates require explicit review.

`GET /experiments/browse` provides host metadata for the scheduling folder browser. Omitted path starts at the standard Hamilton Methods directory when present; empty path lists drives. Responses contain canonical current/parent paths, breadcrumbs, folders (with a disabled linked flag), `.med` files and imported-folder shortcuts. Access requires the same local admin/user checks as import. Directory enumeration uses shared helpers with the system browser; do not alter backup-browser behavior when extending it.

All three endpoints below use the scheduling API prefix, require an authenticated admin/user and enforce `require_local_access`. Blocking discovery/database work runs in a thread pool.

- `POST /experiments/import-preview`: `{folder_path, relative_paths?}`; read-only discovery and validation. Omit relative paths to scan regular subfolders; an empty selection is rejected.
- `POST /experiments/import-folder`: the same payload, importing the selected paths after fresh validation.

`ExperimentDiscoveryService.preview_methods` is the shared validator. Require an existing absolute host folder, case-insensitive `.med` extension, readable filesystem metadata, and a resolved path beneath that folder. Reject traversal, escaping links, invalid files and duplicate canonical paths. Skip linked directories during whole-folder discovery. Host metadata supplies names, sizes and modification times; browser metadata is never trusted. Preview classifies canonical catalogue paths as New or Update without changing records. Existing malformed catalogue paths are left alone.

Import calls preview again, because a file can disappear or change after review. `import_experiment_methods` returns per-file outcomes, rather than optimistic counts. Updates use canonical path identity while retaining the existing method ID/path, including older path spellings; inserts get a new ID. Multiple existing entries resolving to the same file fail explicitly for manual review. Individual write failures can coexist with successes, but a transaction rollback/commit failure makes all affected rows failed. API counts derive from those actual outcomes and include per-file reasons. No import endpoint launches methods, creates schedules, or repairs/deletes old catalogue or schedule records.

Run `python -m pytest backend/tests/test_method_import.py -q` for preview, nested/uppercase files, updates, inaccessible/escaping paths, changed files, database failures, legacy compatibility and local-access enforcement.

- `backend/services/scheduling/scheduler_engine.py`  
  Runs the background thread that decides when jobs should execute. Uses a single-worker in-memory queue to execute one schedule at a time, plus notifications and state transitions.

- `backend/services/scheduling/experiment_executor.py`  
  Bridges between schedule metadata and the Hamilton controller (builds the command line, launches HxRun, tracks process exit codes).
  Timeout action selection also lives here, but readiness gating (maintenance/manual recovery/HxRun busy) now lives in the scheduler worker.

- `backend/services/scheduling/process_monitor.py`  
  Watches Hamilton processes so the scheduler knows whether the robot is already busy.

  The scheduler uses the existing `psutil` dependency to inspect processes from any thread; it does not share a WMI/COM client. Busy checks and the status loop use the same process list. If names cannot be inspected, a hidden `tasklist /FO CSV /NH` call supplies a fallback with a five-second timeout. Both detectors failing produces `availability=error` and blocks dispatch until detection recovers. Command lines and creation times may be absent when Windows denies access to those optional details. Regression tests in `backend/tests/test_process_monitor.py` cover these cases without launching Hamilton software. Other services may still use WMI for their own purposes.

- `backend/services/scheduling/database_manager.py`  
  Logical façade that the engine and API call. It hides SQLite details and exposes CRUD operations such as `create_schedule`, `update_schedule`, `store_job_execution`, etc.

- `backend/services/scheduling/sqlite_database.py`  
  All actual SQL lives here. The class maps Python objects (`ScheduledExperiment`, `JobExecution`, `NotificationLogEntry`) to `INSERT`, `SELECT`, etc.

- `backend/api/scheduling.py`  
  FastAPI endpoints. Marshals request payloads, performs optimistic locking, and calls into the manager and engine.

- `backend/services/hxrun_maintenance.py`  
  Global enforcer outside the scheduler package. Scheduler/Executor both consult this flag before dispatching HxRun work.

**Rule of thumb:** never reach into `sqlite_database.py` from the API or engine directly. Always go through `SchedulingDatabaseManager`.

---

## 2. Execution Lifecycle Cheat Sheet

1. **Scheduler thread wakes up** (`SchedulerEngine._scheduler_loop`).  
   Loads active schedules from the database and picks jobs that are due.

2. **Job queued** (`_process_due_job`).  
   Creates a `JobExecution` row (status `pending`), puts `(ScheduledExperiment, JobExecution)` on the job queue.

3. **Single worker consumption** (`_job_worker_loop`).  
   One worker thread drains the queue in FIFO order. No scheduler-side capacity retry loop remains.

4. **Dispatch gates inside queue worker** (`SchedulerEngine._job_worker_loop`).  
   The worker keeps jobs in `queued` state while any gate is active: HxRun maintenance, manual recovery, or HxRun busy. Jobs are not marked `running` until gates clear.

5. **Execution** (`ExperimentExecutor.execute_experiment`).  
   Launches HxRun, waits for completion, collects exit code, returns success flag.

6. **Result handling** (`_finalize_execution`, shared by the worker and restart reconciliation).
   Updates execution row (`running` → `completed` or `failed`), updates schedule next-run time, triggers notifications.

7. **Failure pathways** (`_handle_failed_execution`).  
   - Abort signals ⇒ schedule marked inactive via `mark_recovery_required`, email alerts sent.  
   - Launch/execution failures ⇒ run logged as failed, schedule rescheduled to the next interval when applicable.

8. **Watcher cleanup** (`RunLogMonitor.finish`).
   Saves the finished observation and cancels any unsent monitoring alerts.

---

## 3. Key Data Structures

### ScheduledExperiment (`backend/models.py`)
Fields:
- `schedule_id`: GUID string primary key.
- `experiment_name`, `experiment_path`: human label + MED file path.
- `schedule_type`: `once`, `interval`, or alias (`hourly`, `daily`, `weekly`).
- `interval_hours`: optional float; aliases default automatically.
- `timeout_config`: `TimeoutConfig(timeout_minutes, action, cleanup_experiment_path, cleanup_experiment_name)`.
- `is_active`, `archived`, `next_run`, `last_run`.

### JobExecution
Captures each run:
- `execution_id`: GUID string (auto-generated).
- `schedule_id`: FK back to `ScheduledExperiment`.
- `status`: `pending`, `running`, `completed`, `failed`, `aborted`, etc.
- `start_time`, `end_time`, `error_message`, `hamilton_command` (legacy `retry_count` remains stored as `0`).

### NotificationContact & NotificationSettings
Represent email contacts and SMTP configuration. Hooks appear in `frontend/src/components/scheduling/*Notification*.tsx` and backend manager methods `get_notification_contacts`, `create_notification_log`, etc.

Test and custom email API calls run SMTP in the request thread pool, so a slow mail server does not freeze other pages or health requests. Manual recovery API actions are also offloaded because their scheduler calls can send email. Keep blocking SMTP out of async endpoint bodies. Interactive email sends once, with a 10-second timeout for each blocking SMTP operation; this is not a total request deadline. The frontend test request allows 60 seconds for its result. Background alerts retain the normal delivery retries.

Failure details identify the SMTP host/port and step: connection/server greeting, SSL connection, STARTTLS, authentication, or message submission. A greeting timeout happens before the password is checked: investigate network reachability and the selected port/encryption mode before changing credentials. An authentication rejection requires checking the username and SMTP/app password; repeating the same credentials is not retried. Certificate validation stays enabled. Sockets are closed after each attempt; cleanup failure after a server accepts the message does not trigger duplicate sending. `test_notification_responsiveness.py` verifies concurrent health requests while email and recovery requests are stalled.

---

## 4. How to Add or Modify Functionality

### 4.1 Adding a New Schedule Field
1. **Model update** (`backend/models.py`).  
   Add the attribute to `ScheduledExperiment` data class. Provide defaults.

2. **SQLite schema** (`backend/services/scheduling/sqlite_database.py`).  
   - Add column to `CREATE TABLE` section.
   - Write migration logic in `_ensure_schema` (check for column, `ALTER TABLE`).
   - Update `create_schedule`, `update_schedule`, and row-to-model conversions.

3. **API serialization** (`backend/api/scheduling.py`).  
   - Accept field in request validator or `_normalize_schedule_request`.
   - Include field when constructing response dictionaries.

4. **Frontend types** (`frontend/src/types/scheduling.ts`).  
   - Extend relevant interfaces and normalizers (`normalizeSchedule`).

5. **Hook & UI** (`frontend/src/hooks/useScheduling.ts`, `SchedulingPage.tsx`).  
   - Load the field when fetching schedules.
   - Update forms if the field is editable.

6. **Tests/Notes**  
   - Adjust existing backend tests if they assert entire schedule dicts.
   - Document in `docs/implementation-notes.md`.

### 4.2 Adding a New Execution Event Notification
1. **Define trigger** inside `SchedulerEngine._notify_execution_event`.  
   Use a new `event_type` string (e.g., `"execution_warning"`).

2. **Logging + dedupe**  
   The notification log ensures uniqueness with `notification_log_exists`. Extend the check if the trigger should be suppressed under certain conditions.

3. **Email template**  
   Modify `backend/services/notifications.py` to format the new event. Ensure `NotificationLogEntry.event_type` is stored.

4. **Front-end display**  
   Update `frontend/src/components/ScheduleHistory.tsx` or relevant UI to show the new status label.

### 4.3 Timeout Behaviour
1. Timeout behavior lives in `ScheduledExperiment.timeout_config` and is evaluated in `SchedulerEngine._resolve_timeout_context`.
2. Executor launch is now single-attempt: `ExperimentExecutor.execute_experiment` runs once (no retry loop).
3. Worker readiness waiting is queue-based and indefinite (no robot-availability timeout cutoff). The schedule stays queued until gates clear.
4. Timeout context is evaluated at actual launch time, so queued/wait delay contributes to timeout action selection.
5. Timeout actions:
   - `continue`: run the originally scheduled method.
   - `run_cleanup_and_terminate`: run the configured cleanup method instead and deactivate the schedule.

### 4.4 Manual Recovery Flows
1. Use `SchedulingDatabaseManager.mark_recovery_required(schedule_id, note, actor)` to force a schedule inactive.  
2. Clearing the flag uses `resolve_recovery_required`.  
3. Frontend surfaces rely on `ManualRecoveryState` via `useScheduling`. Update both the hook and API `GET /status/queue` responses if new metadata is needed.

### 4.5 Start-Time Policy
1. API accepts user-provided `start_time` without minute rounding.
2. Create rejects past timestamps (`start_time < now`) to prevent invalid new schedules from being saved.
3. Update still allows explicit operator control over `start_time` values for existing schedules.
4. Scheduling engine treats any active schedule with `start_time <= now` as due and enqueues it; it does not auto-mark overdue jobs as `missed`.

---

## 5. Common Maintenance Tasks

| Task | Where | Tips |
|------|-------|------|
| Recalculate next run time | `_calculate_next_execution_time` in `scheduler_engine.py` | Always call with `touch_updated_at=False` to avoid clobbering optimistic locking tokens. |
| Archive schedule | `SchedulingDatabaseManager.archive_schedule` & SQLite procedures | Archiving flips the `archived` flag; API returns archived-only lists via query params. |
| Delete schedule | `delete_scheduled_experiment` | Moves execution history into `JobExecutionsArchive` with name/path snapshots. |
| Execution history dedupe | `SQLiteSchedulingDatabase.get_execution_history` | Merges live and archived rows per `execution_id`; do not reimplement client-side. |
| Email contacts management | `NotificationContactsPanel` + API routes | Validate emails with regex, reuse `StatusDialog` for feedback. |

---

## 6. Extension Points & Gotchas

- **Thread safety**  
  Locks: `_schedules_lock`, `_jobs_lock`, `_contacts_lock`; the log monitor owns its own short state lock and a separate SQL polling gate. Acquire them exactly where the engine currently does. Never hold locks while performing long operations (like network calls).

- **Timezones**  
  Always normalize timestamps with the helpers in `backend.utils.datetime`. `ScheduledExperiment.__post_init__` now calls `utc_now_as_local_naive()`, and the SQLite layer serializes dates through `_serialize_timestamp`, so any new timestamps must follow the same pattern. Never write bare `datetime.utcnow()` values into the database.

- **Optimistic concurrency**  
  API enforces `updated_at` token checks (`_load_current_schedule`). When adding writes, pass `touch_updated_at=False` for background adjustments and `True` for user actions.

- **External processes**  
  `ExperimentExecutor` relies on path resolution (`resolve_experiment_path`). When changing command building, keep the logging consistent so operators can diagnose HxRun failures.

- **Frontend data flow**  
  `useScheduling` is the single source of truth. After adding new API endpoints or data, expose actions there and thread them into `SchedulingPage.tsx`.

---

## 7. Quick Reference: Key Functions

| Function | Purpose | Notes |
|----------|---------|-------|
| `SchedulerEngine.start()` | Launch background thread | Called once at backend startup. |
| `_job_worker_loop()` | Execute queued jobs serially | Single worker guarantees one active execution path and applies readiness gates while jobs remain queued. |
| `_handle_failed_execution(experiment, execution)` | Post-failure logic | Determines abort vs generic failure and triggers notifications. |
| `SchedulingDatabaseManager.create_schedule(experiment)` | Persist new schedule | Wraps `SQLiteSchedulingDatabase.create_schedule`. |
| `SchedulingDatabaseManager.store_job_execution(execution)` | Insert new run | Must be called before queueing the job. |
| `SQLiteSchedulingDatabase.get_execution_history(limit, schedule_id)` | Retrieve merged history | Already dedupes live+archive entries. |
| `ExperimentExecutor.execute_experiment(experiment, execution, timeout_context)` | Run Hamilton command | Single-attempt launch; expects scheduler worker to have already passed readiness gates. |

---

## 8. When Something Goes Wrong

1. **Queue grows while robot is busy**  
   In single-worker mode this is expected while HxRun is occupied, maintenance mode is on, or manual recovery is active. Check `/status/queue` `waiting_reason` for each queued job.

2. **Execution history shows “Archived Schedule”**  
   Ensure the delete path passed `name_snapshot` and `path_snapshot` to `delete_schedule`. If you added new entry points, forward those snapshots.

3. **Optimistic locking 409 errors**  
   Confirm your write path called `SchedulingDatabaseManager.update_scheduled_experiment(..., touch_updated_at=False)` for background adjustments. UI submissions should include `expected_updated_at`.

4. **Missing notifications**  
   Inspect `NotificationLogEntry` records via `SchedulingDatabaseManager.get_notification_logs`. If the log is empty, the event never fired—check `_notify_execution_event`.

5. **HXRUN command failures**  
   Logs are in `backend/services/scheduling/experiment_executor.py`. Ensure paths are resolved using `resolve_experiment_path`.

---

## 9. Adding New Modules or Replacing Components

1. **Create new module** under `backend/services/scheduling/`.  
   Keep naming consistent (`snake_case.py`).  
   Provide a `get_*` singleton helper if it will be shared.

2. **Export through `backend/services/scheduling/__init__.py`** so other packages can import it cleanly.

3. **Document behaviour** in this guide or `docs/implementation-notes.md`.

4. **Wire into the engine or API** by injecting at the top of `scheduler_engine.py` or `backend/api/scheduling.py`. Avoid adding new globals—use helper functions similar to `get_scheduler_engine()`.

---

## 10. Final Checklist Before Merging Changes

- [ ] Scheduler engine still imports `SchedulingDatabaseManager` only from `database_manager.py`.
- [ ] New fields tested end-to-end (database, API, frontend).
- [ ] `docs/implementation-notes.md` updated with the change summary.
- [ ] No direct SQLite calls from API or engine.
- [ ] `/status/queue` reflects scheduler runtime queue details (`running_job_details`, `queued_job_details`).
- [ ] Frontend still builds (`npm run build` on Windows).
- [ ] PyInstaller spec includes any new modules if packaging is required (`RobotControl.spec`).

---

## 11. External API Automation (No Frontend)

You can fully manage schedules from another program using backend APIs only.

Important constraints:
- You must authenticate first (`POST /api/auth/login`) and send bearer token.
- Create/update/delete endpoints require local network access (`require_local_access`).
- For safe writes, send `expected_updated_at` from the latest schedule snapshot.

Start the backend with `uv run --locked python backend/main.py --host 127.0.0.1 --port 8005 --no-browser`.
Use the interactive API documentation at `http://127.0.0.1:8005/docs` to inspect the
current scheduling requests and responses. The previously documented
`backend/scripts/scheduling_api_cli.py` helper is not tracked in this repository
and is not available in a fresh clone.

Run scheduling regression tests with `uv run --locked python -m pytest
backend/tests/test_scheduler_single_worker.py backend/tests/test_scheduler_manual_recovery.py
backend/tests/test_scheduling_create_guard.py backend/tests/test_scheduling_pipeline.py`.
The busy-robot test configures a one-second polling interval so its wait deadline
matches the scheduler's actual dispatch polling.

By following the structure above you can extend the scheduling stack without reintroducing the duplication and fragile flows that existed before this cleanup. When in doubt, trace the execution lifecycle in section 2 and ensure your changes respect the same boundaries. Happy scheduling!


## Run log inactivity monitoring (September 2026)

The old twice-estimated-duration email is replaced by log inactivity. Estimated duration still controls calendar planning. The executor no longer kills a process after 120 minutes; the optional late-start cleanup action still works.

- `run_log_monitor.py`: `HamiltonRunReader` reads SQL, `RunLogMonitor` observes files and runs one email-delivery thread. The existing scheduler calls the observer every 30 seconds. `run_log_store.py` owns transactional observation/outbox writes and idempotent completion. Keep scheduling decisions in the engine.
- A schedule's `log_inactivity_threshold_minutes` is a positive integer, default 3. Creation, editing, serialization and SQLite migration preserve it. Launch snapshots the threshold; later edits apply to the next execution. Method-folder imports import method metadata, not schedules; schedules subsequently created from those methods receive the normal default.
- Before Popen, save the actual method path, original schedule, SQL clock boundary and previous GUID. After successful Popen, confirm the launch. Resolve a unique SQL row for the exact `.hsl`/`.med` path within five minutes of that boundary; delayed visibility of that row is allowed. Missing/ambiguous rows remain unavailable. SQL baseline failure uses the local launch boundary (SQL is local to this host). A bound GUID never changes.
- Only `<method>_<GUID>_Trace.trc` is considered. `ROBOTCONTROL_HAMILTON_LOG_PATH` overrides the default `C:\Program Files\HAMILTON\LogFiles`. Communication logs and unrelated methods cannot reset the timer. Poll fresh size, modification time and file identity; never read the entire trace during observation. Windows may delay last-write-time changes, so size changes count as activity too.
- Elapsed inactivity uses a monotonic clock. Three minutes means strictly more than 180 observed seconds; the normal polling delay adds up to roughly 30 seconds. Missing SQL, unknown state, missing/inaccessible trace, or duplicate matching traces instead starts a separate fixed three-minute unavailable timer. File replacement/truncation establishes a new baseline. SQL completion/abort suppresses inactivity immediately.
- `ExecutionMonitoring` stores one JSON observation per execution. `NotificationLog.log_id` deterministically identifies execution + event + pause. Observation changes, alert enqueueing and cancellation are committed together. `sent` records suppress duplicates, while new file activity creates a new pause. `pending`, `sending`, `error`, `sent`, and `cancelled` are valid notification statuses. Failed monitoring email attempts retry after 60 seconds while still applicable. SMTP's existing internal retries remain; they run off the scheduler thread.
- The email worker checks SQL/files before claiming an alert and again after preparing attachments. An exact trace is supplied to the notification service; a missing/unreadable trace never causes a substitute attachment. Existing rolling video summaries remain. Stable Message-ID values reduce duplicate delivery after a crash, but SMTP cannot promise exactly-once delivery.
- Startup restores unfinished observations before dispatch. It preserves pause IDs and file signatures but starts fresh monotonic timers: writes during downtime cannot be reconstructed. Known process outcomes survive retries/restart; otherwise terminal SQL status reconciles completion. Atomic completion updates execution and schedule once, including executions archived after their schedule was deleted. An active restored run continues blocking another launch.
- Older runs without a launch association show monitoring unavailable instead of adopting a possibly unrelated run. If an orphan cannot be resolved automatically, use the existing manual recovery controls: verify/stop HxRun, mark recovery required, then acknowledge recovery. Acknowledgement can close an unowned execution only when HxRun detection confirms no process remains. Detection failure keeps it blocked.
- Status includes observation state, GUID, trace name, last activity/observation time, threshold and unavailable reason. No active contacts means observation continues and delivery reports an error in notification history. Clearing a condition cancels unsent monitoring emails.

### Verification

Hamilton SQL states are 1 (Running), 2 (Paused), 64 (Aborted), and 128 (Complete). Running and Paused both retain robot ownership and allow exact-trace observation. Only file activity resets inactivity/rearms alerts; SQL state changes alone do not. Paused is not terminal and does not trigger camera archival. Unknown codes remain unavailable and include the raw value in the reason. Monitoring status and email context include `run_state` and `raw_run_state`; old saved observations default the added field to null. The initial simulator warnings for state 2 were a mapping defect, now corrected; repeat operator acceptance and check the notification event type, not just receipt of an email.

Run the backend test suite, then build the frontend, embed resources, and build the Windows executable. `test_run_log_monitor.py` uses temporary SQLite databases, trace files, a controllable monotonic clock, fake SQL and fake SMTP. It covers run matching, repeated pauses, outages, replacements, restart, terminal races, delivery retries, archive completion and the removed runtime cap. API tests cover positive-integer validation, default 3 and omitted-update preservation.

For acceptance on the simulator: schedule a verified simulator-only method with an email contact, pause trace writes for at least 3.5 minutes, check one email, resume writes, pause again, and check a second email. Complete and verify silence. Repeat with an application restart during a pause: the same previously sent pause must not send twice; an unalerted pause needs a fresh observation window. Actual Hamilton behavior and SMTP delivery must be checked by the operator; automated tests never launch a laboratory method.

## Delivery records (2026-09-27)

Automatic alerts retain their record owner. Manual/test/recovery sends use
`notification_delivery.send_recorded`: create pending before SMTP, then update that
row. If creating the record fails, do not send. If its final update fails, log the
failure and return a warning; never resend accepted mail solely to repair a log.
SMTP test warnings also appear in the settings panel.

Sent means SMTP acceptance, not inbox delivery. Partial refusal records partial and
does not retry accepted recipients. An interrupted run-monitor sending record becomes
unknown after restart, instead of automatically sending again. Inspect before resending.

`SchedulerEngine.database_change_guard` serializes destructive database actions with
`launch_guard`, rejecting active/unknown robot state, recovery and unhealthy storage.
## Laboratory integration boundary (2026-09-28)

The native scheduling SQLite database remains the owner of schedules, queue
history and safety/recovery. `run_log_monitor.HamiltonRunReader` still owns exact
Hamilton GUID/status matching. `lab_integration.py` owns laboratory preparation
and its separate data connection. Database viewer target selection has no effect
on scheduling. See the [installation/example guide](../../../backend/services/scheduling/examples/README.md).

Reference workflow, established from the existing form/code: save
`ScheduledToRun` and `EvoYeastExperiment:<ID>|set`, wait for the normal scheduler
gates, select exactly that experiment in SQL, then launch the chosen Hamilton
method. EvoYeast selection remains set after completion. The checked local
schedule database contained no schedules, so this is not a recording of a live
deployed run. Preserve a real deployed schedule and verify its preparation on the
VM before using this candidate on hardware.

`PreExecutionPipeline` now delegates the full prerequisite list to the selected
adapter. EvoYeast validates all tokens before writes, locks/verifies the target,
clears flags and selects it in one transaction. ResetHamiltonTables remains an
optional stored procedure step in the same connection. A failing procedure rolls
back transaction-owned writes; internal commits/external effects are not guaranteed
reversible. Explicit `none`/`noop`/`skip` selection actions are non-writing.
The old standalone ScheduledToRun placeholder now fails with an actionable error
instead of claiming a write succeeded. Missing targets and unavailable connections
also block launch. The former marker cleanup never wrote SQL and is not replaced
by a new post-run reset.

Three small native SQLite tables retain the boundary:

- `LabInstallation`: captured adapter/version, connection identity and configuration
  signature. Secrets are never stored here. A configuration change requires no
  active schedules, unfinished jobs/monitoring or pending recovery.
- `LabScheduleBinding`: original data target for each schedule, including migrated
  schedules. Credential rotation can retain a target; switching databases cannot
  silently reuse old IDs. Re-create a schedule after reviewing a changed target.
- `LabPreparation`: execution ID, captured identity, prerequisite list and
  preparing/prepared/failed status. A repeated execution ID is rejected even after
  restart. These receipts are retained as execution evidence; there is no automatic
  deletion in this change.

The existing restart reconciler remains responsible for unfinished executions;
it does not rerun preparation. Failure after preparation starts requests the
existing manual recovery flow. A storage failure retains the existing scheduler
hold. Changing installation files requires restart; an invalid configuration
blocks preparation rather than falling back to another database. Restore the
previous configuration to reconcile unfinished work.

The batch example uses its own SQLite file, `Batches` and `InstrumentWorkOrder`.
It demonstrates different identifiers and schema without rewriting the scheduler.
Its method-side workflow has not been validated in another laboratory.

Verification:

```powershell
.venv/Scripts/python.exe -X utf8 -m backend.e2e.scheduling_lab_check
npm --prefix frontend run build
Set-Location frontend
npx playwright test scheduling-lab.spec.ts --trace retain-on-failure
```

The HTTP/executor check uses UUID-named disposable SQL Server databases and two
separate SQLite files. The process launch boundary is a recorder; no robot runs.
Evidence is in `test-output/scheduling-lab-verification`: results, logs, screenshots
and the retained maintenance-modal failure trace. The obsolete stub-only
`test_scheduling_pipeline.py` was replaced by this integration coverage; its
assumptions included the removed success-without-a-write placeholders.

Existing focused safety/executor checks passed. A broader existing selection
reported 12 failures also reproduced against the previous committed implementation:
11 create/update checks rely on forwarded localhost headers/non-admin access;
one interrupted-email check expects cancelled instead of the current unknown state.
These unrelated expectations were not used to weaken production safety behavior.
