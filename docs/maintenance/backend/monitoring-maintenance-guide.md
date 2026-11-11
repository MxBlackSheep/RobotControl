# Monitoring & Notifications Maintenance Guide

Hamilton status uses the shared mapping: 1 = Running, 2 = Paused, 64 = Aborted, 128 = Complete. `ExperimentState.is_running` is strict; `is_in_progress` includes Running and Paused. The duplicate monitoring experiment route is removed. Pause/resume never fires recording completion callbacks. Original SQL status is retained separately for diagnostics.

Use this document whenever you need to touch real-time monitoring, experiment tracking, or email notifications. The goal is to keep polling and alerts predictable even if you have never built a monitoring system before.

---

## 1. High-Level Architecture

- `backend/services/health_sampler.py`
  `health_sampler` owns the five-second PC sample used by the display endpoints.

- `backend/services/experiment_monitor.py`  
  `ExperimentMonitor` polls the Hamilton database, normalises run states, and fires callbacks when runs complete (e.g., to trigger video archiving).

- `backend/services/notifications.py`  
  Email delivery helpers: `EmailNotificationService` (SMTP client) and `SchedulingNotificationService` (formats schedule alerts, manual recovery emails, TRC attachments).

- `backend/api/monitoring.py`  
  REST endpoints. Wraps the services in `ResponseFormatter`, enforces auth, and exposes `/system-health` and `/databases`; latest-run data comes from `/api/experiments/latest`.
  `/databases` reports the built-in connection's `get_status` and `DatabaseTools.connection_health`:
  every saved connection opened as its users open it (a reader's read-only check included),
  in parallel, with its uses. A result under 90 seconds old (`HEALTH_STALE_SECONDS`) returns
  at once and, past 30 seconds (`HEALTH_CACHE_SECONDS`), starts one background re-check, so an
  unreachable server's 8-second connect timeout does not delay the page's other readings. An
  older result is never served: the check runs in the request, and if it fails (for example
  background checks keep failing) `connections` is null and the card shows Partly unknown
  instead of the last Connected rows. `checked_at` is the result's time.

- `frontend/src/hooks/useMonitoring.ts`  
  React hook that polls `/experiments`, `/system-health`, `/databases` and the camera streaming status through `useSerialPolling` (one request per owner, 20-second deadline) and normalises the response.

- `frontend/src/pages/MonitoringPage.tsx`  
  The System Status page: renders the data from `useMonitoring`, freshness chip and Refresh.

SQL status calls and blocking Database/Experiments API calls run in Starlette's bounded worker pool. These display paths never cache scheduler dispatch decisions or Hamilton terminal state.

**Rule of thumb:** Let the service singletons (`health_sampler`, the automatic-recording-owned `ExperimentMonitor`) own their threads. Do not start extra loops somewhere else, or you will double-poll the database and spam clients.

---

## 2. Monitoring Lifecycle Cheat Sheet

1. **PC samples**: application lifespan starts and stops `health_sampler`. The API reads its
   snapshot; `sampled_at` is the sample time. The first CPU sample is a warm-up value.
2. **Experiment monitor thread**  
   - Automatic recording supplies the completion callback at construction and starts the monitor after recording succeeds. The monitor keeps its current
     experiment and the time of its last check.  
   - `_monitoring_worker` polls SQL (`SELECT TOP 1 … FROM HamiltonVectorDB.dbo.HxRun`).  
   - `ExperimentState` is created, state transitions detected, and `is_newly_completed` set when a run goes to `COMPLETE`/`ABORTED`.  
   - Completion callbacks (e.g., auto-recording archiver) run outside locks.

3. **Notifications**  
   - Scheduler paths call `SchedulingNotificationService.schedule_alert` and manual recovery helpers.  
   - `EmailNotificationService.send` handles SMTP auth, retries, attachment size limits, and reports errors via logs.

4. **Frontend**  
   - `useMonitoring` polls every 60 seconds (30 seconds after a failure). A request that has not answered within 20 seconds is aborted and shown as "Request timed out"; the last reading is kept. See `docs/maintenance/frontend/polling-maintenance-guide.md`.

---

## 3. Key Data Structures & Settings

- `ExperimentState` (`backend/services/experiment_monitor.py`)  
  Contains `run_guid`, `method_name`, `run_state` (`ExperimentStateType` enum), timestamps, `is_newly_completed`, and `state_change_time`.

- `Hamilton state mapping` (`backend/constants.py`)  
  Maps numeric VENUS codes → human readable values (`"RUNNING"`, `"COMPLETED"`, etc.). Keep this in sync if Hamilton upgrades.

- `NotificationSettings` (stored via `NotificationSettings` table in scheduling DB)  
  Holds SMTP host, port, TLS/SSL flags, encrypted password. Loaded lazily inside `EmailNotificationService`.

- Environment toggles:  
  - `AUTO_RECORDING_CONFIG["experiment_check_interval_seconds"]` – tune poll interval for `ExperimentMonitor`.  
  - SMTP settings (set via scheduling admin UI or DB entries).

---

## 4. REST Responses

1. **Keep them cheap** – use the current experiment and the `health_sampler` snapshot so `/system-health` does not sample `psutil` per request.
2. **Frontend expectations** – `useMonitoring` normalises `/experiments` and `/system-health`. If you rename fields, update its normaliser to avoid `undefined` values on the System Status page.
3. **Authentication** – every endpoint requires a Bearer token (`get_current_user`).

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Adjust polling interval | `ExperimentMonitor.__init__` or `AUTO_RECORDING_CONFIG` | Change `experiment_check_interval_seconds`, restart backend, confirm logs show the new interval. |
| Add a metric to `/system-health` | `HealthSampler` and its snapshot | Compute the metric in the sampler, and return it in `/api/monitoring/system-health`. Update dashboard labels. |
| Enable email alerts | `NotificationSettings` table | Populate SMTP host/port/sender/password (UI or SQL). Ensure `EmailNotificationService` logs “Sent email notification…” to confirm. |
| Attach extra files to schedule alert | `SchedulingNotificationService.schedule_alert` | Append to `attachments`, respect size guard (`GMAIL_MESSAGE_SIZE_LIMIT`) to avoid dropped emails. |

---

## 6. Extension Points & Safe Modifications

### 6.1 Adding a new system metric (example: GPU usage)
1. Extend `HealthSampler` with your metric (e.g., call `gpustat`).
2. Include it in the sampler snapshot.
3. Return the field in `/api/monitoring/system-health`.  
4. Update the frontend dashboard to render it (chip or chart).

### 6.2 Triggering alerts on experiment completion
1. Register a completion callback:  
   ```python
   monitor = get_experiment_monitor()
   monitor.add_completion_callback(my_callback)
   ```  
2. In `my_callback`, call downstream services (storage, notifications). Remember callbacks run in the monitor thread—keep them quick or offload to an async task queue.

### 6.3 Changing email templates
1. Edit `_render_alert_subject` / `_render_alert_body` in `SchedulingNotificationService`.  
2. Keep plain text—HTML emails or embedded images require MIME tweaks.  
3. Update `attachment_notes` if you change how TRC/clip files are attached so recipients understand the payload.

---

## 7. Quick Reference

| Function / Method | Purpose | Notes |
|-------------------|---------|-------|
| `ExperimentMonitor.start_monitoring()` | Begin polling Hamilton DB | Thread-safe; sets up `stop_event` and `monitor_thread`. |
| `ExperimentMonitor.add_completion_callback(fn)` | Register completion handler | Use for archiving triggers or alerts. |
| `SchedulingNotificationService.schedule_alert(...)` | Send email with optional TRC/video attachments | Returns `ScheduleAlertResult` for logging/inspection. |
| `EmailNotificationService.send(subject, body, to, attachments)` | Raw SMTP send helper | Retries `_smtp_retries` times with `_smtp_retry_delay` seconds between tries. |

---

## 8. When Something Goes Wrong

1. **System Status shows no data or "Stale data"**  
   - "Request timed out" means a response took over 20 seconds; check network path and backend responsiveness.  
   - Inspect the retained endpoint response and application logs for database or sampler failures.

2. **CPU usage spike from monitoring**  
   - Check the shared sampler; display requests must not start another CPU sample.
   - Keep one PC sampler and one experiment monitor; their owners manage startup and shutdown.

3. **Experiment states never change**  
   - Verify database connection: `ExperimentMonitor._query_latest_experiment` logs errors. If `execute_query` returns `error`, check SQL Server availability.  
   - Make sure `AUTO_RECORDING_CONFIG["experiment_check_interval_seconds"]` is reasonable (default pulled from config).

4. **Emails fail silently**  
   - `EmailNotificationService.last_error` stores the last SMTP issue; log it or surface it.  
   - Check decrypted password: if `decrypt_secret` throws, the settings UI stored an invalid cipher. Reset via scheduling admin page.

5. **Attachment blows up email size**  
   - Logs show “Rolling clip summary skipped” or “size … exceeds limit”. Change `GMAIL_MESSAGE_SIZE_LIMIT` cautiously or trim attachments.

Treat the services as the single source of truth. Update cached snapshots carefully, keep callbacks quick, and always double-check that the frontend normalises whatever shape you emit.

