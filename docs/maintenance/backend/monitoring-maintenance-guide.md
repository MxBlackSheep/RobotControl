# Monitoring & Notifications Maintenance Guide

Use this document whenever you need to touch real-time monitoring, experiment tracking, or email notifications. The goal is to keep WebSockets, polling, and alerts predictable even if you have never built a monitoring system before.

---

## 1. High-Level Architecture

- `backend/services/monitoring.py`  
  `MonitoringService` runs the background loop, holds cached telemetry, manages WebSocket connections, and streams updates to channels.

- `backend/services/experiment_monitor.py`  
  `ExperimentMonitor` polls the Hamilton database, normalises run states, and fires callbacks when runs complete (e.g., to trigger video archiving).

- `backend/services/notifications.py`  
  Email delivery helpers: `EmailNotificationService` (SMTP client) and `SchedulingNotificationService` (formats schedule alerts, manual recovery emails, TRC attachments).

- `backend/api/monitoring.py`  
  REST and WebSocket endpoints. Wraps the services in `ResponseFormatter`, enforces auth, and exposes `/status`, `/system-health`, `/experiments`, and `/ws/*`.

- `frontend/src/hooks/useMonitoring.ts`  
  React hook that opens the WebSocket, falls back to REST polling, and normalises the response for dashboards.

- `frontend/src/components/MonitoringDashboard.tsx`, `SystemStatus.tsx`  
  Render the data from `useMonitoring`, display health chips, charts, and connection state.

**Rule of thumb:** Let the service singletons (`get_monitoring_service()`, `get_experiment_monitor()`) own their threads. Do not start extra loops somewhere else, or you will double-poll the database and spam clients.

---

## 2. Monitoring Lifecycle Cheat Sheet

1. **First client hits `/api/monitoring/ws/*`**.  
   `websocket_endpoint` accepts the socket, ensures `MonitoringService.start_monitoring()` ran, and puts the connection in a channel (e.g., `"general"`, `"experiments"`).

2. **Background loop** (`MonitoringService._monitoring_loop`) runs every 5 seconds:  
   - `_update_experiment_data()` pulls the latest experiment from `ExperimentMonitor`.  
   - `_update_system_health()` gathers CPU/memory/disk via `psutil` and counts active WebSockets.  
   - `_update_db_performance()` calls `get_database_service().get_performance_stats()`.

3. **Cached snapshots** live in `MonitoringService.last_experiment_data`, `last_system_health`, `last_db_performance`. These keep REST endpoints fast.

4. **Broadcast** happens lazily. When a socket sends `"get_current_data"` or the service decides to push, `_broadcast_updates()` sends JSON messages per channel.

5. **Experiment monitor thread**  
   - `_monitoring_worker` polls SQL (`SELECT TOP 1 … FROM HamiltonVectorDB.dbo.HxRun`).  
   - `ExperimentState` is created, state transitions detected, and `is_newly_completed` set when a run goes to `COMPLETE`/`ABORTED`.  
   - Completion callbacks (e.g., auto-recording archiver) run outside locks.

6. **Notifications**  
   - Scheduler paths call `SchedulingNotificationService.schedule_alert` and manual recovery helpers.  
   - `EmailNotificationService.send` handles SMTP auth, retries, attachment size limits, and reports errors via logs.

7. **Frontend**  
   - `useMonitoring` opens `ws://…/api/monitoring/ws/general`, listens for JSON messages (`type: "current_data"`, `"experiments_update"`, etc.), and mirrors them into React state.  
   - When the socket drops or auth fails, the hook falls back to fetching `/api/monitoring/experiments` and `/api/monitoring/system-health` via `fetch`.

---

## 3. Key Data Structures & Settings

- `ExperimentState` (`backend/services/experiment_monitor.py`)  
  Contains `run_guid`, `method_name`, `run_state` (`ExperimentStateType` enum), timestamps, `is_newly_completed`, and `state_change_time`.

- `Hamilton state mapping` (`backend/constants.py`)  
  Maps numeric VENUS codes → human readable values (`"RUNNING"`, `"COMPLETED"`, etc.). Keep this in sync if Hamilton upgrades.

- `MonitoringService.websocket_manager`  
  Tracks connections per channel, metadata (`connected_at`, `last_ping`), and counts for metrics.

- `NotificationSettings` (stored via `NotificationSettings` table in scheduling DB)  
  Holds SMTP host, port, TLS/SSL flags, encrypted password. Loaded lazily inside `EmailNotificationService`.

- Environment toggles:  
  - `ROBOTCONTROL_LOG_RATE_LIMIT_MONITORING`, `ROBOTCONTROL_LOG_RATE_LIMIT_AUTOMATION` – reduce log noise for busy loops.  
  - `AUTO_RECORDING_CONFIG["experiment_check_interval_seconds"]` – tune poll interval for `ExperimentMonitor`.  
  - SMTP settings (set via scheduling admin UI or DB entries).

---

## 4. Working With WebSockets and REST Fallbacks

1. **Channels** – when you add a new monitoring stream (e.g., `"scheduling"`), call `await websocket_endpoint(websocket, "scheduling")`. Inside `MonitoringService`, broadcast via `broadcast_to_channel(message, "scheduling")`.

2. **REST responses** – keep them cheap. Use cached data from `MonitoringService` so `/system-health` doesn’t call `psutil` five times per second.

3. **Frontend hook expectations** – `useMonitoring` expects message shapes:
   ```json
   { "type": "current_data", "data": { "experiments": [...], "system_health": {...}, "database_performance": {...} } }
   ```
   If you rename fields, update the hook’s normaliser to avoid `undefined` errors in the dashboard.

4. **Authentication** – all REST endpoints require a Bearer token (FastAPI dependency `get_current_user`). WebSockets currently auto-start the monitoring loop without verifying tokens; if you need locks, demand a token in query params and validate it in `websocket_endpoint`.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Adjust polling interval | `ExperimentMonitor.__init__` or `AUTO_RECORDING_CONFIG` | Change `experiment_check_interval_seconds`, restart backend, confirm logs show the new interval. |
| Add a metric to `/system-health` | `_update_system_health` & `MonitoringService.last_system_health` | Compute metric, store in `last_system_health`, and return it in `/api/monitoring/system-health`. Update dashboard labels. |
| Add a new WebSocket channel | `monitoring.py` & frontend | Broadcast via `broadcast_to_channel`, add `<WebSocket>` route, update `useMonitoring` if the frontend should listen. |
| Enable email alerts | `NotificationSettings` table | Populate SMTP host/port/sender/password (UI or SQL). Ensure `EmailNotificationService` logs “Sent email notification…” to confirm. |
| Attach extra files to schedule alert | `SchedulingNotificationService.schedule_alert` | Append to `attachments`, respect size guard (`GMAIL_MESSAGE_SIZE_LIMIT`) to avoid dropped emails. |
| Inspect experiment history | `ExperimentMonitor.get_experiment_history()` | Returns sorted list; handy for debugging repeated state flaps. |

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
| `MonitoringService.send_current_data(websocket)` | Push cached state to client | Called when clients request `"get_current_data"`. |
| `MonitoringService.websocket_manager.broadcast_to_channel(message, channel)` | Fan out updates | Provide JSON-serialisable dicts; service handles disconnect cleanup. |
| `ExperimentMonitor.start_monitoring()` | Begin polling Hamilton DB | Thread-safe; sets up `stop_event` and `monitor_thread`. |
| `ExperimentMonitor.add_completion_callback(fn)` | Register completion handler | Use for archiving triggers or alerts. |
| `SchedulingNotificationService.schedule_alert(...)` | Send email with optional TRC/video attachments | Returns `ScheduleAlertResult` for logging/inspection. |
| `EmailNotificationService.send(subject, body, to, attachments)` | Raw SMTP send helper | Retries `_smtp_retries` times with `_smtp_retry_delay` seconds between tries. |

---

## 8. When Something Goes Wrong

1. **WebSocket connects but no data appears**  
   - Check backend logs for “WebSocket waiting for client message…” loops without responses; the client might never send `"get_current_data"`.  
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

6. **WebSocket floods browser console with reconnects**  
   - Frontend retries up to `MAX_RETRIES`. If auth tokens expire, the hook eventually gives up—make sure `/api/auth/refresh` works so the interceptor renews tokens before the socket opens.

Treat the services as the single source of truth. Update cached snapshots carefully, keep callbacks quick, and always double-check that the frontend normalises whatever shape you emit.

