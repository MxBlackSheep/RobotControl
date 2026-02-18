# Scheduling Service Maintenance Guide

This document explains how the scheduling subsystem fits together and how to modify it safely. It is written for developers who are new to the codebase and prefer explicit, step‑by‑step directions.

---

## 1. High-Level Architecture

- `backend/services/scheduling/scheduler_engine.py`  
  Runs the background thread that decides when jobs should execute. Uses a single-worker in-memory queue to execute one schedule at a time, plus notifications and state transitions.

- `backend/services/scheduling/job_queue.py`  
  Lightweight wrapper around `Queue` that the engine uses to hand work to worker threads.

- `backend/services/scheduling/experiment_executor.py`  
  Bridges between schedule metadata and the Hamilton controller (builds the command line, launches HxRun, tracks process exit codes).
  Timeout action selection also lives here, but readiness gating (maintenance/manual recovery/HxRun busy) now lives in the scheduler worker.

- `backend/services/scheduling/process_monitor.py`  
  Watches Hamilton processes so the scheduler knows whether the robot is already busy.

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

6. **Result handling** (`_execute_job`).  
   Updates execution row (`running` → `completed` or `failed`), updates schedule next-run time, triggers notifications.

7. **Failure pathways** (`_handle_failed_execution`).  
   - Abort signals ⇒ schedule marked inactive via `mark_recovery_required`, email alerts sent.  
   - Launch/execution failures ⇒ run logged as failed, schedule rescheduled to the next interval when applicable.

8. **Watcher cleanup** (`_clear_execution_watch`).  
   Removes timers that detect long-running jobs.

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
  Locks: `_schedules_lock`, `_jobs_lock`, `_contacts_lock`, `_execution_watch_lock`. Acquire them exactly where the engine currently does. Never hold locks while performing long operations (like network calls).

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

By following the structure above you can extend the scheduling stack without reintroducing the duplication and fragile flows that existed before this cleanup. When in doubt, trace the execution lifecycle in section 2 and ensure your changes respect the same boundaries. Happy scheduling!
