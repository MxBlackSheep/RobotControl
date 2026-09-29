# Monitoring & Notifications Maintenance Guide

Hamilton status uses the shared mapping: 1 = Running, 2 = Paused, 64 = Aborted, 128 = Complete. `ExperimentState.is_running` is strict; `is_in_progress` includes Running and Paused. Both retain the existing 50% placeholder in the monitoring API. Pause/resume never fires recording completion callbacks. Original SQL status is retained separately for diagnostics.

Use this document whenever you need to touch real-time monitoring, experiment tracking, or email notifications. The goal is to keep polling and alerts predictable even if you have never built a monitoring system before.

---

## 1. High-Level Architecture

- `backend/services/monitoring.py`  
  `MonitoringService` runs the background loop and holds cached telemetry for the REST endpoints.

- `backend/services/experiment_monitor.py`  
  `ExperimentMonitor` polls the Hamilton database, normalises run states, and fires callbacks when runs complete (e.g., to trigger video archiving).

- `backend/services/notifications.py`  
  Email delivery helpers: `EmailNotificationService` (SMTP client) and `SchedulingNotificationService` (formats schedule alerts, manual recovery emails, TRC attachments).

- `backend/api/monitoring.py`  
  REST endpoints. Wraps the services in `ResponseFormatter`, enforces auth, and exposes `/status`, `/system-health`, `/experiments`, `/start` and `/stop`.

- `frontend/src/hooks/useMonitoring.ts`  
  React hook that polls `/experiments`, `/system-health` and the camera streaming status through `useSerialPolling` (one request per owner, 20-second deadline) and normalises the response.

- `frontend/src/pages/MonitoringPage.tsx`  
  The System Status page: renders the data from `useMonitoring`, freshness chip and Refresh.

**Rule of thumb:** Let the service singletons (`get_monitoring_service()`, `get_experiment_monitor()`) own their threads. Do not start extra loops somewhere else, or you will double-poll the database and spam clients.

---

## 2. Monitoring Lifecycle Cheat Sheet

1. **Start**: `/api/monitoring/start` (admin) or application startup calls `MonitoringService.start_monitoring()`.

2. **Background loop** (`MonitoringService._monitoring_loop`) runs every 5 seconds:  
   - `_update_experiment_data()` pulls the latest experiment from `ExperimentMonitor`.  
   - `_update_system_health()` takes the latest CPU/memory/disk sample from `health_sampler`.  
   - `_update_db_performance()` calls `get_database_service().get_performance_stats()`.

3. **Cached snapshots** live in `MonitoringService.last_experiment_data`, `last_system_health`, `last_db_performance`. These keep REST endpoints fast.

4. **Experiment monitor thread**  
   - `_monitoring_worker` polls SQL (`SELECT TOP 1 … FROM HamiltonVectorDB.dbo.HxRun`).  
   - `ExperimentState` is created, state transitions detected, and `is_newly_completed` set when a run goes to `COMPLETE`/`ABORTED`.  
   - Completion callbacks (e.g., auto-recording archiver) run outside locks.

5. **Notifications**  
   - Scheduler paths call `SchedulingNotificationService.schedule_alert` and manual recovery helpers.  
   - `EmailNotificationService.send` handles SMTP auth, retries, attachment size limits, and reports errors via logs.

6. **Frontend**  
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
  - `ROBOTCONTROL_LOG_RATE_LIMIT_MONITORING`, `ROBOTCONTROL_LOG_RATE_LIMIT_AUTOMATION` – reduce log noise for busy loops.  
  - `AUTO_RECORDING_CONFIG["experiment_check_interval_seconds"]` – tune poll interval for `ExperimentMonitor`.  
  - SMTP settings (set via scheduling admin UI or DB entries).

---

## 4. REST Responses

1. **Keep them cheap** – use cached data from `MonitoringService` and `health_sampler` so `/system-health` does not sample `psutil` per request.
2. **Frontend expectations** – `useMonitoring` normalises `/experiments` and `/system-health`. If you rename fields, update its normaliser to avoid `undefined` values on the System Status page.
3. **Authentication** – every endpoint requires a Bearer token (`get_current_user`); start/stop require an admin.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Adjust polling interval | `ExperimentMonitor.__init__` or `AUTO_RECORDING_CONFIG` | Change `experiment_check_interval_seconds`, restart backend, confirm logs show the new interval. |
| Add a metric to `/system-health` | `_update_system_health` & `MonitoringService.last_system_health` | Compute metric, store in `last_system_health`, and return it in `/api/monitoring/system-health`. Update dashboard labels. |
| Enable email alerts | `NotificationSettings` table | Populate SMTP host/port/sender/password (UI or SQL). Ensure `EmailNotificationService` logs “Sent email notification…” to confirm. |
| Attach extra files to schedule alert | `SchedulingNotificationService.schedule_alert` | Append to `attachments`, respect size guard (`GMAIL_MESSAGE_SIZE_LIMIT`) to avoid dropped emails. |

---

## 6. Extension Points & Safe Modifications

### 6.1 Adding a new system metric (example: GPU usage)
1. Extend `_update_system_health()` with your metric (e.g., call `gpustat`).  
2. Include it in `last_system_health`.  
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

### 6.4 Pausing the monitoring loop manually
Call `get_monitoring_service().stop_monitoring()` (REST `/api/monitoring/stop` does the same). This is useful during heavy debugging so you control when polling happens.

---

## 7. Quick Reference

| Function / Method | Purpose | Notes |
|-------------------|---------|-------|
| `MonitoringService.start_monitoring()` | Launch background thread | Safe to call multiple times; no-op if already running. |
| `ExperimentMonitor.start_monitoring()` | Begin polling Hamilton DB | Thread-safe; sets up `stop_event` and `monitor_thread`. |
| `ExperimentMonitor.add_completion_callback(fn)` | Register completion handler | Use for archiving triggers or alerts. |
| `SchedulingNotificationService.schedule_alert(...)` | Send email with optional TRC/video attachments | Returns `ScheduleAlertResult` for logging/inspection. |
| `EmailNotificationService.send(subject, body, to, attachments)` | Raw SMTP send helper | Retries `_smtp_retries` times with `_smtp_retry_delay` seconds between tries. |

---

## 8. When Something Goes Wrong

1. **System Status shows no data or "Stale data"**  
   - "Request timed out" means a response took over 20 seconds; check network path and backend responsiveness.  
   - Call `/api/monitoring/status` to ensure `is_running` is `True`. If `False`, start it with `/api/monitoring/start` (admin token required).

2. **CPU usage spike from monitoring**  
   - Reduce `MonitoringService.monitor_interval` or skip `psutil.cpu_percent(interval=1)` (replace with `interval=0` for instantaneous reading).  
   - Ensure you do not create extra monitor threads—`logger` should only show “Monitoring service started” once per process.

3. **Experiment states never change**  
   - Verify database connection: `ExperimentMonitor._query_latest_experiment` logs errors. If `execute_query` returns `error`, check SQL Server availability.  
   - Make sure `AUTO_RECORDING_CONFIG["experiment_check_interval_seconds"]` is reasonable (default pulled from config).

4. **Emails fail silently**  
   - `EmailNotificationService.last_error` stores the last SMTP issue; log it or surface it.  
   - Check decrypted password: if `decrypt_secret` throws, the settings UI stored an invalid cipher. Reset via scheduling admin page.

5. **Attachment blows up email size**  
   - Logs show “Rolling clip summary skipped” or “size … exceeds limit”. Change `GMAIL_MESSAGE_SIZE_LIMIT` cautiously or trim attachments.

Treat the services as the single source of truth. Update cached snapshots carefully, keep callbacks quick, and always double-check that the frontend normalises whatever shape you emit.

# System metrics and API responsiveness (September 2026)

`health_sampler` owns one five-second background sampler, started/stopped by application lifespan. `/system-health` includes `sampled_at`; CPU/memory/disk fields preserve their existing names. The first CPU sample is a warm-up value. The frontend uses sample time, not request time, for these metrics. SQL status calls run in Starlette's bounded worker pool, as do blocking Database/Experiments API calls. These display optimizations do not cache scheduler dispatch decisions or Hamilton terminal state.
