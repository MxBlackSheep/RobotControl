# Backend scheduling

The scheduler that launches Hamilton methods: schedules, the single-worker queue and its
safety gates, laboratory data preparation, run-log monitoring, the method library and email
alerts. The Scheduling page is described in
[the frontend scheduling guide](../frontend/scheduling-frontend-maintenance-guide.md).
Recovery transitions, storage rules, lock details, repair and the recovery API are owned by
[the SQLite safety guide](sqlite-safety-maintenance-guide.md); HxRun maintenance mode by
[its guide](hxrun-maintenance-maintenance-guide.md); writing a preparation step by
[the database package README](../../../database_packages/README.md).

## Files and ownership

All paths are under `backend/services/scheduling/` unless stated.

- `scheduler_engine.py`: `SchedulerEngine` (`get_scheduler_engine()`) owns the scheduler loop,
  the single worker queue, dispatch gates, `launch_guard`, `database_change_guard`, recovery
  transitions and finalization.
- `experiment_executor.py`: `ExperimentExecutor` applies the late-start timeout action, runs
  laboratory preparation, launches `HxRun.exe "<method>" -t` once and waits for it to exit.
  `pre_execution.py` writes the preparation receipt and runs the schedule's database package
  step; `legacy_preparation.py` reads the retired adapter's tokens on older schedules.
- `process_monitor.py`: detects HxRun with `psutil`, falling back to
  `tasklist /FO CSV /NH` (five-second timeout).
- `run_log_monitor.py`: `HamiltonRunReader` matches the Hamilton run in SQL; `RunLogMonitor`
  observes the trace file and delivers monitoring email. `run_log_store.py` owns the
  transactional observation and alert writes.
- `safety_store.py`: `SchedulerSafetyStore`, the only code that changes recovery columns.
- `database_manager.py`: `SchedulingDatabaseManager`, the façade the API and engine use for
  schedules, executions, contacts and notification logs. `sqlite_database.py` holds all SQL and
  the schema migration (`_initialize_database`). The launch guard and laboratory settings use
  its connection lock and transactions directly because their checks must share the write.
- `method_library.py`, `experiment_discovery.py`: method catalogue, path changes and import.
- `backend/services/notifications.py` sends email; `notification_delivery.py` records
  manual, test and recovery sends.
- `backend/api/scheduling.py`: `/api/scheduling` routes. Database settings routes are in
  `backend/api/database_tools.py`. Models are in `backend/models.py`.

## Permissions

Remote sessions are read-only; the backend enforces this.

- Create and update schedules, recovery acknowledgement and Resume, method library, import and
  browsing, and manual email sends: local session, role admin or user.
- Delete and archive a schedule: local session, admin or the schedule's creator.
- Reading notification settings or delivery logs, the SMTP test, and changing settings or
  contacts: admin; every change also needs a local session.
- Laboratory database settings (`/api/database/tools/scheduling-settings`): local admin.

## Execution lifecycle

1. **Scheduler loop** (`_scheduler_loop`, every `check_interval_seconds`, 30). A schedule is
   due when it is active, `start_time <= now`, not queued or running and not flagged for
   recovery. Overdue schedules run; nothing is marked missed. The loop also advances running
   interval schedules and checks active run logs.
2. **Queue** (`_process_due_job`). Stores a `pending` `JobExecution` first; if that fails,
   nothing is queued.
3. **Single worker** (`_job_worker_loop`) takes jobs in order. `_wait_until_dispatch_ready`
   rechecks every five seconds or less, with no timeout, and keeps the job queued with a
   `waiting_reason` (shown by `GET /status/queue`) while any gate holds:
   - scheduler safety storage is unhealthy;
   - HxRun maintenance mode is on;
   - manual recovery is active, or acknowledged but waiting for **Resume queued jobs**;
   - this schedule requires recovery;
   - a previous execution is still observed (unfinished or not reconciled);
   - HxRun is running, or process detection failed.

   A schedule removed or deactivated while waiting cancels its execution with that reason.
4. **Timeout action.** Timeout is measured from the scheduled start at actual launch, so queue
   delay counts. `continue` runs the method; `run_cleanup_and_terminate` runs the configured
   cleanup method instead and deactivates the schedule (a missing cleanup path fails the run).
5. **Laboratory preparation** runs next for the original method (see below); a failure fails
   the run before launch. The late-start cleanup method skips this preparation.
6. **Launch.** `launch_guard` holds `_schedules_lock` and `_jobs_lock`, rechecks storage,
   recovery, Resume, maintenance and HxRun absence, then under the SQLite connection lock
   rechecks that the schedule is still active, unarchived and not flagged, writes the
   `running` row and calls `Popen`. If that write fails, launch is blocked and a safety fault
   is recorded. The locks cover only this check, the write and `Popen`, never the run.
7. **Wait and classify.** Exit code 0 is success unless the run log (or the SQL abort lookup)
   reports Aborted or Error. HxRun is never killed for runtime or log inactivity.
8. **Finalize** (`_finalize_execution`, also used by restart reconciliation). Reloads the
   schedule so edits made during the run are kept; a completed once-schedule or a terminating
   timeout deactivates it, a completed interval schedule gets its next start (now plus the
   interval, to the minute). Execution and schedule are committed together.
9. **Failures** (`_handle_failed_execution`). An abort (Hamilton Aborted/Error, return code 64,
   manual abort) sends an `aborted` alert and requires manual recovery for that schedule. Other
   failures send `execution_failed`. Finally `RunLogMonitor.finish` closes the observation and
   cancels unsent monitoring alerts.

`database_change_guard` uses the same locks and refuses while storage is unhealthy, recovery
or Resume is pending, a run is owned or observed, or HxRun is present or undetectable. Package
operations and laboratory settings take it; backup restore does not.

## Schedules and edits

- `schedule_type` is `once`, `interval`, or the aliases `hourly`, `daily`, `weekly` (default
  hours are filled in). `timeout_config` holds minutes, action and cleanup method;
  `preparation` holds the pinned database step; `prerequisites` only keeps the retired
  adapter's tokens until an administrator reviews them.
- Create rejects a `start_time` in the past; update allows any value. Times are not rounded.
- `log_inactivity_threshold_minutes` is a positive whole number, default 3. An update that
  omits it keeps the saved value; each launch captures the value, so edits apply to the next run.
- Timestamps use the helpers in `backend/utils/datetime.py` (`utc_now_as_local_naive`) and
  `_serialize_timestamp`; never store bare `datetime.utcnow()` values.
- User edits send `expected_updated_at`. The version is compared exactly (including
  microseconds) under `_schedules_lock` immediately before saving; a mismatch returns 409.
  Background writes pass `touch_updated_at=False` so they do not change that version. Archive
  loads and saves under the same lock. Keep this for any new schedule mutation.
- Ordinary edits never write recovery columns. Delete and archive run their guard inside the
  write transaction: recovery, a running execution or unfinished monitoring blocks them. Delete
  cancels pending and queued executions and moves history to `JobExecutionsArchive` with the
  schedule's name and path.
- `SQLiteSchedulingDatabase.get_execution_history` merges live and archived rows per
  `execution_id`; do not repeat that in the client.

## Laboratory preparation

The native scheduling SQLite database (`data/robotcontrol_scheduling.db`) remains the owner of
schedules, the queue, history and recovery. `HamiltonRunReader` still owns Hamilton run
matching through the native connection. Preparation has one mechanism: the schedule's
database package step. The Database viewer choice has no effect on scheduling.

**Database package step.** A schedule may carry one `preparation` (a database package tool of
kind `preparation`), stored as JSON on `ScheduledExperiments.preparation` with the package file
hash, version and the operation connection's id, server and database pinned by the server when
a local administrator saved it (`_requested_preparation` in `backend/api/scheduling.py`;
requests without the key keep it, other roles get 403 when changing it).
`PreExecutionPipeline.prepare` checks `DatabaseTools.preparation_state` before the receipt (a
changed or missing package, a rebound connection or one edited to another server or database
refuses the run with no write), then runs `DatabaseTools.prepare_for_run`: a spawned child
(`report_worker.run_preparation`) with a 120 s limit that commits only after `prepare` returns.
It holds no scheduler lock; the registered execution keeps `database_change_guard` closed for
manual operations. Error before commit: receipt `failed`, nothing committed, and the receipt
keeps the step's own error (for example a procedure's RAISERROR). Timeout, crash or a commit
without confirmation: `unknown`. Both mark the schedule for recovery with a note saying what is
known. `PackageCatalogue.refuse_if_scheduled` refuses updating, removing or rebinding a package
an active schedule uses; an unreadable stored step loads as `{"invalid": true}` and blocks
dispatch. Schedule reads add `preparation_state` (`ready`/`needs_review`/`missing`/`invalid`).
Steps pinned before server and database were recorded read as `needs_review` until saved again.

**EvoYeast flag.** The starter package `database_packages/evoyeast-experiment` ("Select EvoYeast
experiment") runs the SQL the former built-in adapter ran. In the host's SERIALIZABLE
transaction it locks the target row (`UPDLOCK, HOLDLOCK`), refuses a missing or duplicated
`ExperimentID`, clears every `ScheduledToRun` flag and sets the target; it has one required
input, **Experiment**. Version 1.0.0 also offered a `dbo.ResetHamiltonTables` table reset copied
from the adapter's token support, which no form in use had offered; 1.0.1 removed it. Importing
1.0.1 is refused while an active schedule uses 1.0.0 (`refuse_if_scheduled`); after the import
such schedules read Needs review (changed hash) until an administrator saves them again. The
selection stays set after the run; there is no post-run reset. It needs a read connection
(`primary`, experiment choices) and an operation connection to the same EvoYeast database.
New installations seed it; on an existing installation an administrator imports
`starter-packages\evoyeast-experiment.zip` from the release folder (Database → Manage packages;
`build_scripts/pyinstaller_build.py` writes a ZIP of every starter package there).

**Schedules saved with the retired adapter.** Before this package, a built-in adapter
(`lab_integration.py`, chosen by `data/scheduling-lab.json`) ran tokens saved in
`prerequisites`, for example `ResetHamiltonTables:Runtime`, `ScheduledToRun`,
`EvoYeastExperiment:42|set`, or `Batch:<code>` for the removed SQLite batch example. Nothing
runs them now and `scheduling-lab.json` is no longer read. `legacy_preparation.py` derives, on
every read, a review for such a schedule: `preparation_state` is `needs_review` and
`legacy_preparation` carries the tokens, a message and, where the tokens fit the EvoYeast
package (one selection, optionally the `ScheduledToRun` marker, no existing database step), a
prefilled `suggestion` `{experiment_id}`. A `ResetHamiltonTables` token is never prefilled or
dropped: the message says the table reset is no longer part of the step and an administrator
decides. The run is refused before any write until a local administrator saves the schedule
with the `preparation` key; that save clears the tokens. The form always sends that key for an administrator (the suggestion, else the saved step, else
`null`), so schedules without a prefill can be resolved too.
`|none`, `|noop` and `|skip` selections never wrote anything and do not block. Clients cannot
create or edit tokens (HTTP 400). Nothing is rewritten at startup, so restarts and repeated
upgrades keep the tokens until that save.

**Receipts.** `LabPreparation` in the scheduling SQLite database holds the execution ID, the
saved tokens (`steps`), the pinned step (`package`), status `preparing`/`prepared`/`failed`/
`unknown` and the step's `message`; `identity` described the retired adapter and is now `{}`.
The receipt is written under `BEGIN IMMEDIATE` before any laboratory write, also for a schedule
without a step. A repeated execution ID is rejected even after restart, and the restart
reconciler never reruns preparation. Receipts are kept as evidence. The `LabInstallation` and
`LabScheduleBinding` tables of the retired adapter are no longer created or read.

## Run-log monitoring

Log inactivity replaced the old "twice the estimated duration" email; estimated duration now
only plans the calendar.

- Before `Popen` the monitor saves the actual method path, schedule, SQL clock boundary and
  previous run GUID. Afterwards it binds one SQL run row for the exact `.hsl`/`.med` path within
  five minutes of that boundary; a late row is allowed, missing or ambiguous rows stay
  unavailable. A bound GUID never changes.
- Only `<method>_<GUID>_Trace.trc` in `ROBOTCONTROL_HAMILTON_LOG_PATH` (default
  `C:\Program Files\HAMILTON\LogFiles`) counts. Size, modification time and file identity are
  polled without reading the file; a size change counts as activity. Replacement or truncation
  starts a new baseline.
- Hamilton states (`backend/constants.py`): 1 Running, 2 Paused, 64 Aborted, 128 Complete.
  Running and Paused both keep the robot occupied and are observed; Paused is not terminal and
  does not archive camera video. Unknown codes are unavailable, with the raw value in the reason.
  Only file activity resets inactivity; state changes alone do not.
- Inactivity uses a monotonic clock: 3 minutes means more than 180 observed seconds, plus up
  to about 30 seconds of polling delay. Missing SQL, unknown state, a missing or duplicate trace
  starts a separate fixed three-minute unavailable timer. Completion or abort in SQL stops alerts.
- `ExecutionMonitoring` stores one observation per execution. `NotificationLog.log_id`
  identifies execution, event and pause, and is written in the same transaction as the
  observation change. Statuses: `pending`, `sending`, `sent`, `error`, `cancelled`, plus
  `partial` and `unknown` for recorded sends. A sent pause is not repeated; new activity
  creates a new pause. Failed monitoring email retries after 60 seconds while still applicable,
  off the scheduler thread.
- The email worker rechecks SQL and the file before claiming an alert and again after
  preparing attachments. Only the exact trace is attached. Stable Message-ID values reduce
  duplicates after a crash, but SMTP cannot promise exactly-once delivery. No active contacts
  means observation continues and history records an error.
- Startup restores unfinished observations before dispatch, keeping pause IDs and file
  signatures but starting fresh timers. A restored active run keeps blocking launch. Known
  process outcomes survive restart; otherwise terminal SQL status completes the execution once,
  including executions archived after their schedule was deleted. A `sending` monitoring alert
  interrupted by restart becomes `unknown` and is not resent.
- New observations persist `launched_at` with its UTC offset. Queue status qualifies older
  server-local timestamps using the launch date's system offset; missing or invalid starts
  are returned as null. This makes elapsed time consistent across browser timezones without
  changing SQL association or safety timers. Older naive records assume the server timezone
  has not changed; a start in the repeated autumn hour cannot recover its original offset.
  Check HTTP serialization and SQLite restart with
  `uv run --locked python backend/e2e/run_timing_check.py`; its exported queue payloads are
  browser fixtures in `test-output/timezone-review-fix/queue-payloads.json`.
- Older runs without a launch association show monitoring unavailable. Resolve an orphan with
  manual recovery (verify or stop HxRun, mark recovery, acknowledge). Acknowledgement closes an
  unowned execution only when HxRun detection confirms no process; detection failure keeps it
  blocked.

## Method library

`ExperimentMethods` carries `archived`, `revision`, `path_status`, `last_checked_at` and
`validation_reason`; migration adds missing columns without changing records. Path status and
archive are independent. New choices use valid, unarchived entries; existing schedules keep
their saved paths.

- `GET /experiments/library` lists entries with primary and cleanup references;
  `/library/check` stores validation results; `PATCH /library/{id}` archives or restores with an
  expected revision. Archiving never stops schedules or deletes files.
- `GET /experiments/browse` lists host folders and `.med` files for the folder browser (no path:
  the Hamilton Methods folder when present; empty path: drives). Linked folders are marked and
  not entered. It shares directory helpers with the backup browser; do not change that behavior.
- `POST /experiments/import-preview` and `/import-folder` take `{folder_path, relative_paths?}`.
  `ExperimentDiscoveryService.preview_methods` requires an existing absolute folder, `.med`
  files (any case) resolving inside it, and rejects traversal, escaping links and duplicates;
  whole-folder discovery skips linked folders. Metadata comes from the host, never the browser.
  Import validates again and returns per-file Added/Updated/Failed with reasons; updates keep
  the existing ID and path, prefer a unique unarchived match, and several entries for one file
  fail for manual review. A failed commit fails every affected row. Import never creates
  schedules, launches methods or deletes records.
- **Path change.** `POST /experiments/library/{id}/path-preview` with `{new_path}` validates the
  file and lists every primary and cleanup reference with its version, active/archive flags and
  busy state (pending, queued or running, including a Hamilton pause); it changes nothing.
  `POST .../change-path` takes `{new_path, expected_revision, references: [{schedule_id, role,
  expected_updated_at}]}`; an empty list changes only the library. `prepare_path_change` does
  file work before any lock; `change_library_method_path` then holds `_schedules_lock` and
  `_jobs_lock`, rejects queued or running selections, and `apply_method_path_change` commits the
  catalogue and selected path columns in one `BEGIN IMMEDIATE` transaction, rechecking revisions
  and pending executions. The refreshed schedules replace the cache before the locks are released,
  so an older queued object cannot launch the old path. Conflicts return 409; never infer
  references from a method name. Labels, timing, contacts, history, monitoring and archive
  state are kept; files are never moved and runs never relaunched.

## Email

- Test and manual sends run in the request thread pool, make one attempt with a 10-second
  timeout per SMTP step, and go through `notification_delivery.send_recorded`: a `pending` record
  first (no record, no send), then `sent`, `partial` or `error`. If the final update fails the
  response warns; accepted mail is never resent to repair a log. Background alerts use a
  90-second timeout and three attempts.
- Sent means SMTP accepted the message, not inbox delivery. A partial refusal is recorded as
  `partial` and accepted recipients are not retried.
- Errors name the host, port and step (connection/greeting, SSL, STARTTLS, authentication,
  submission). A greeting timeout happens before the password is checked: check reachability,
  port and encryption first. Certificate validation stays on. Keep blocking SMTP out of async
  route bodies; manual recovery actions are offloaded because they can send email.

## Checks

- Unit and focused tests: `uv run --locked python -m pytest backend/tests/test_scheduler_single_worker.py
  backend/tests/test_scheduler_manual_recovery.py backend/tests/test_scheduling_create_guard.py
  backend/tests/test_run_log_monitor.py backend/tests/test_hamilton_states.py
  backend/tests/test_method_library.py backend/tests/test_method_path_change.py
  backend/tests/test_method_import.py backend/tests/test_process_monitor.py
  backend/tests/test_notification_responsiveness.py backend/tests/test_sqlite_safety.py`.
  They use temporary SQLite files, fake SQL, fake SMTP and a controllable clock; none launches
  Hamilton software.
- Laboratory preparation: `.venv/Scripts/python.exe -X utf8 -m backend.e2e.scheduling_lab_check`
  (EvoYeast package and retired-token schedules) and `backend.e2e.preparation_step_check`
  (any step) use UUID-named disposable SQL Server databases, with a recorder in place of
  process launch; the browser side is `frontend/e2e/scheduling-lab.spec.ts`. Evidence:
  `test-output/scheduling-lab-verification`. Failure cases are in each file's header.
- Email records: `backend.e2e.notification_delivery_check` (commands in
  [frontend/e2e/README.md](../../../frontend/e2e/README.md)).
- Operator acceptance on the simulator: schedule a simulator-only method with an email
  contact, pause trace writes for at least 3.5 minutes, confirm one `log_inactive` email (check
  the event type, not just receipt), resume, pause again and confirm a second; complete and
  confirm silence. Repeat with a restart during a pause: a sent pause is not resent, an
  unalerted pause starts a fresh window. Before using a new build on hardware, verify a real
  deployed schedule's preparation on the VM.

To inspect requests, start the backend with
`uv run --locked python backend/main.py --host 127.0.0.1 --port 8005 --no-browser` and open
`http://127.0.0.1:8005/docs`. Scripts must sign in (`POST /api/auth/login`), run locally for
writes and send `expected_updated_at` from the latest schedule.

## Troubleshooting

- **Queue grows:** expected while a gate holds; read `waiting_reason` in `/status/queue`.
- **Edit returns 409:** another save or a background change came first; reload and edit again.
- **No notification:** read `get_notification_logs`. No record means the event never fired
  (`_notify_execution_event`); `unknown` means an interrupted send, so check recipients before
  resending.
- **"Method file not found" or HxRun fails:** the executor logs the resolved path from
  `resolve_experiment_path` and the full command.
- **"…EvoYeast selection moved to a database step…" / "…old preparation … cannot be carried
  over…":** the schedule still has retired adapter tokens. A local administrator opens it,
  checks the prefilled step (or chooses one) and saves. Install the EvoYeast package and assign
  its connections first if the step shows "not installed".
- **"Preparation was already attempted for this execution":** review recovery; preparation is
  never repeated automatically.
