# Backend HxRun Maintenance Mode Guide

This guide explains the backend pieces that enforce **HxRun Maintenance Mode**.  
Purpose: when the mode is enabled, RobotControl blocks HxRun launches everywhere it can control.

---

## 1. Files You Must Know

- `backend/services/hxrun_maintenance.py`  
  Global enforcer service. Watches for `HxRun.exe` starts and kills them while maintenance mode is enabled.

- `backend/api/maintenance.py`  
  API endpoints:
  - `GET /api/maintenance/hxrun` (inspect from local or remote session)
  - `PUT /api/maintenance/hxrun` (toggle, local-only)

- `backend/services/scheduling/sqlite_database.py`  
  Persists the flag and metadata in `SchedulerState`.

- `backend/services/scheduling/database_manager.py`  
  Wrapper methods that the API/service call.

- `backend/services/scheduling/scheduler_engine.py`  
  Pauses scheduler dispatch while maintenance mode is enabled.

- `backend/services/scheduling/experiment_executor.py`  
  Hard-blocks execution before launching HxRun.

---

## 2. Data Model (Persistent Flag)

`SchedulerState` stores:

- `hxrun_maintenance_enabled` (`0/1`)
- `hxrun_maintenance_reason` (optional text)
- `hxrun_maintenance_updated_by` (username)
- `hxrun_maintenance_updated_at` (timestamp)

Legacy DBs are auto-migrated during startup.

---

## 3. Enforcement Strategy (Event + Fallback)

`HxRunMaintenanceService` uses two mechanisms at the same time:

1. Event watcher (preferred)  
   WMI process-start watcher for `HxRun.exe`.

2. Fallback poll (safety net)  
   Polls process status every 1 second if events fail or miss.

If HxRun is detected while mode is enabled:

1. Service terminates `HxRun.exe` (`WMI Terminate` first, then `taskkill` fallback).
2. Service shows a Windows popup explaining maintenance mode is blocking launch.

---

## 4. Local/Remote Permissions

- Read state (`GET`) is allowed for all authenticated sessions.
- Write state (`PUT`) requires `require_local_access` (loopback only).

So remote users can inspect, but only local users can enable/disable.

---

## 5. Startup and Shutdown

`backend/main.py` starts the enforcer during app startup and stops it during shutdown/signal cleanup.

Do not remove this startup hook unless you intentionally want to disable external-launch blocking.

---

## 6. Common Tasks

| Task | Where | What to do |
|------|-------|------------|
| Change fallback frequency | `HxRunMaintenanceConfig.fallback_poll_seconds` | Keep it low (default `1.0`) to reduce miss windows. |
| Change popup spam behavior | `HxRunMaintenanceConfig.popup_cooldown_seconds` | Increase if users complain about repeated popups. |
| Add more audit fields | `backend/api/maintenance.py` | Extend `log_action(...details=...)` payload. |
| Disable event watcher temporarily | `HxRunMaintenanceService._build_process_start_watcher` | Return `None` to force poll-only mode. |

---

## 7. Debug Checklist

1. Flag toggles in API but no enforcement happens:
   - Check startup logs for `HxRun maintenance enforcer started`.
   - Confirm app is running on Windows (event+kill paths are Windows-only).

2. Remote user can toggle (should not happen):
   - Verify endpoint still depends on `require_local_access`.

3. Scheduler still launches runs:
   - Check `scheduler_engine.py` loop for maintenance pause branch.
   - Check executor guard in `execute_experiment`.

4. Popup never appears:
   - Confirm `ctypes.windll.user32.MessageBoxW` is reachable in current session.
   - Check cooldown setting is not too high.

