# Main Application Maintenance Guide

This guide explains how the FastAPI entry point, logging, static assets, and build scripts fit together. Use it whenever you touch `backend/main.py`, tweak environment flags, or package the app.

---

## 1. High-Level Architecture

- `backend/main.py`  
  Creates the FastAPI app, configures logging/CORS, wires routers, manages startup/shutdown, and serves static assets in both development and embedded modes.

- `backend/utils/data_paths.py`  
  `DataPathManager` decides where logs, backups, and videos live (`project_root/data/*` in dev, executable folder in compiled mode).

- `backend/utils/logging_setup.py`  
  Builds rotating file handlers, optional JSON logs, and log rate limiting. Imported early in `main.py`.

- API routers included by `main.py`:
  - `backend/api/auth`, `backend/api/database`, `backend/api/camera`, `backend/api/monitoring`, `backend/api/scheduling`, `backend/api/admin`, `backend/api/system_config`, `backend/api/system`, `backend/api/experiments`.

- Static asset helpers
  - `backend/services/embedded_resources.py` & generated `backend/embedded_static.py` handle single-exe mode.
  - Dev mode reads `frontend/dist` directly if the folder exists.

- Build scripts
  - `build_scripts/embed_resources.py` – bake `frontend/dist` into `backend/embedded_static.py`.
  - `build_scripts/pyinstaller_build.py` – run PyInstaller with the right hidden imports, data files, and backup preservation.

---

## 2. Startup & Shutdown Flow

1. **Module import**  
   - `_patch_bcrypt_metadata()` runs immediately so modern `bcrypt` works with `passlib`.  
   - Project root is added to `sys.path` before routers import, allowing relative imports inside packaged builds.

2. **Logging**  
   - `setup_logging(...)` builds handlers under `data/logs/`.  
   - `configure_uvicorn_logging()` replaces uvicorn’s default handlers and filters out static-file access noise.

3. **Lifespan context** (`@asynccontextmanager lifespan`)  
   - Logs startup banner.  
   - Schedules scheduler auto-start after `_SCHEDULER_AUTOSTART_DELAY_SECONDS` (default 60) unless env disables it (`ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS=disable`).  
   - Starts automatic recording if enabled.

4. **App creation**  
   - FastAPI app instantiates with docs at `/docs`, `/redoc`.  
   - CORS allows localhost ports used by Vite (`5173`), CRA (`3000`), and packaged app (`8005`).

5. **Signal & exit handling**  
   - `graceful_shutdown` handles `SIGINT`/`SIGTERM` and `atexit`, stopping camera, auto-recording, monitoring, etc.
   - In packaged builds the system-tray “Terminate” now toggles `server.should_exit`; avoid calling `sys.exit()` there or pystray will log a handler error.

6. **Shutdown block in lifespan**  
   - Cancels pending auto-start task, clears DB pool, stops monitoring/live streaming/auto-recording/scheduler/camera in a predictable order.

---

## 3. Static Asset Serving

1. **Embedded mode (`EMBEDDED_MODE=True`)**  
   - `serve_embedded_static` fetches bytes via `EmbeddedResourceManager.get_resource(path)`.  
   - Supports ETag caching (304 responses) and sets headers like `Cache-Control`.  
   - SPA routing fallback: if a path is missing, it serves `/index.html`.

2. **Development mode** (`frontend/dist` present)  
   - `serve_static_dev` reads files from disk.  
   - Only routes non-API paths; asset misses return 404, while navigation routes fall back to `index.html`.

3. **When no dist exists**  
   - Backend logs “No frontend build found - API only mode.”  
   - Use this when you host the frontend separately.

4. **Embedding pipeline**  
   - Run `npm run build` (from `frontend/`).  
   - Execute `python build_scripts/embed_resources.py` – generates `backend/embedded_static.py`.  
   - Confirm logs show the number of embedded files; if zero, the script could not find `frontend/dist`.

---

## 4. Scheduler Auto-Start & Service Coordination

- Scheduler auto-start delay controlled by `ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS`.  
  - Positive integer ⇒ delay in seconds.  
  - `disable`, `off`, `never` ⇒ auto-start disabled; admin must start scheduler manually via API/UI.

- Shutdown sequence order matters:  
  1. Stop camera (saves clips).  
  2. Stop auto-recording (releases watchers).  
  3. Stop monitoring (ends WebSockets).  
  4. Stop live streaming, scheduler, and clear DB pools.

- Startup logs show readiness for each service (lazy loading). If a service fails to import, check logs right after “Backend session starting” for stack traces.

---

## 5. Logging & Data Directory Expectations

- **DataPathManager**  
  - Dev: base path = project root.  
  - Compiled: base path = folder containing `RobotControl.exe`.

- **Folders it ensures** (`data/` under base path): `backups`, `videos`, `logs`, `config`, `temp`.

- **Log retention**  
  - `ROBOTCONTROL_LOG_RETENTION_DAYS` (default 14).  
  - `ROBOTCONTROL_LOG_ERROR_RETENTION_DAYS` (default 30).  
  - Logs rotate daily, old files compress straight into `data/logs/history`, and only the live `robotcontrol_backend.log`/`robotcontrol_backend_error.log` stay in `data/logs/`.

- **JSON logs**  
  - Set `ROBOTCONTROL_LOG_JSON=1` for structured output (makes log ingestion easier).

---

## 6. Packaging Pipeline (PyInstaller)

1. **Prepare frontend**  
   - `cd frontend && npm install && npm run build`.

2. **Embed resources**  
   - `python build_scripts/embed_resources.py` → `backend/embedded_static.py`.

3. **Build executable**  
   - `python build_scripts/pyinstaller_build.py --layout onedir` (or `--layout onefile`).  
   - Script copies `backend/` as data, adds hidden imports (FastAPI routers, passlib, pyodbc, cv2), and preserves existing backups before cleaning `dist`.

4. **Output**  
   - `dist/RobotControl/RobotControl.exe` (onedir) or `dist/RobotControl.exe` (onefile).  
   - Restored backups end up inside `dist/.../data/backups`.

5. **System tray**  
   - Compiled mode attempts to launch a tray icon (`backend/utils/system_tray.py`). Failures are logged but non-fatal.

---

## 7. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Add a new API router | `backend/main.py` | Import router, `app.include_router(new_router, prefix="/api/new", tags=["new"])`. Ensure package listed in PyInstaller hidden imports. |
| Update allowed CORS origins | `app.add_middleware(CORSMiddleware, allow_origins=[...])` | Add your host or port, redeploy backend, confirm browser requests include it. |
| Change default port | `backend/main.py:main()` | Run `python backend/main.py --port 9000` (dev) or package with `--port`. For service installs, wrap command in a shortcut/batch file. |
| Disable static serving (reverse proxy handles it) | Set `SERVE_FRONTEND_FROM_BACKEND = False` | Remove or comment out route, ensure proxy serves `frontend/dist`. |
| Adjust log retention | Env vars | Set `ROBOTCONTROL_LOG_RETENTION_DAYS` / `ROBOTCONTROL_LOG_ERROR_RETENTION_DAYS`, restart backend, verify new numbers in startup log. |
| Force scheduler to stay off | `ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS=disable` | Set the env var, restart backend, confirm logs say “Scheduler auto-start disabled by configuration.” |

---

## 8. Quick Reference

| Function / Block | Purpose | Notes |
|------------------|---------|-------|
| `_env_flag`, `_env_int`, `_env_scheduler_autostart_delay` | Parse env vars | Keeps parsing defensive; reuse when adding toggles. |
| `lifespan(app)` | Startup/shutdown manager | Place new service boot/shutdown here so behaviour mirrors packaged build. |
| `graceful_shutdown(signum, frame)` | Signal handler | Safe to call manually; stops camera, auto-recording, monitoring. |
| `serve_embedded_static` / `serve_static_dev` | Static asset delivery | Always check path does not start with `api/` to avoid swallowing API routes. |
| `configure_uvicorn_logging()` | Puts uvicorn under our handlers | Call again after changing handlers if you reload configuration. |
| `build_scripts/embed_resources.embed_frontend_resources()` | Embed static files | Run after every frontend build; ensures PyInstaller finds `backend/embedded_static.py`. |
| `build_scripts/pyinstaller_build.build_with_pyinstaller(...)` | Compile executable | Accepts `layout` (`onefile` / `onedir`) and `console` flag. |

---

## 9. When Something Goes Wrong

1. **App boots but routers 404**  
   - Verify `app.include_router` entries exist and prefixes match expected paths.  
   - Check PyInstaller hidden imports; missing routers during packaging cause `/api/...` to 404 in the executable.

2. **Static files return 404 in packaged build**  
   - Ensure `backend/embedded_static.py` exists and `EMBEDDED_MODE` is `True` (happens automatically when running as PyInstaller bundle).  
   - Run `python -c "from backend.services.embedded_resources import get_resource_manager; print(len(get_resource_manager().list_resources()))"` inside the dist folder; count > 0 means resources are embedded.

3. **Scheduler auto-starts when it should not**  
   - Confirm env var is exactly `disable`/`off`/`never`. A blank string resets to default (60 seconds).  
   - Check logs for “Scheduler auto-start scheduled to run…” to confirm value being used.

4. **Logs missing or stuck under wrong path**  
   - On Windows, lack of permissions can block directory creation. Check `data/logs` exists; if not, run backend as Administrator once to create it.  
   - If `data` ends up next to the executable unexpectedly, inspect `DataPathManager._initialize_paths` – maybe `sys._MEIPASS` changed.

5. **PyInstaller build fails with missing module**  
   - Add `--hidden-import` or `--collect-submodules` entry in `pyinstaller_build.py`.  
   - Run build again; watch console output to confirm PyInstaller sees the added module.

6. **Graceful shutdown hangs**  
   - Look for service logs that never return (e.g., camera stop). Add timeouts or `try/except` near offending service’s stop call.  
   - If running via Windows service, ensure signals propagate; use `Ctrl+C` during testing to validate.

Follow these patterns and the backend entry point will stay predictable across local development, packaging, and deployment.
