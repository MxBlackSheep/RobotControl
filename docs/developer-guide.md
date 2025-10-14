# RobotControl Developer Guide

_Last updated: 2025-10-01_

## 1. Overview & Goals
- RobotControl delivers a unified control plane for the lab Hamilton robot stack: SQL Server data access, experiment scheduling, camera monitoring/recording, and admin tooling.
- The project replaces multiple legacy services with a single FastAPI backend (`backend/main.py`) and a modern React/Vite frontend (`frontend/src`).
- Windows is the target runtime (local lab workstation). Packaging uses PyInstaller for a single-file distribution that embeds the compiled frontend.

## 2. Technology Stack
- **Backend:** Python 3.11, FastAPI, Uvicorn, PyODBC (SQL Server), Pydantic v2, OpenCV, websockets, passlib, python-jose, pytest.
- **Frontend:** React 18 + TypeScript, Vite build, Material UI (MUI 5), TanStack React Query, Axios, react-router.
- **Build/Packaging:** Vite static bundle, custom embed script (`build_scripts/embed_resources.py`), PyInstaller spec (`RobotControl.spec`).
- **Data/storage:** Microsoft SQL Server (primary + secondary failover), local SQLite (`data/robotcontrol_scheduling.db`) for scheduling metadata, Windows filesystem shares for backups/videos.

## 3. Repository Layout
| Path | Description |
| --- | --- |
| `main.py` | Orchestrator that boots backend + frontend for local dev. |
| `backend/` | FastAPI application, services, config, tests, and generated resources. |
| `backend/api/` | Route modules grouped by domain (auth, database, camera, scheduling, etc.). |
| `backend/services/` | Business logic and integrations (database, scheduling engine, camera pipelines, backups, websockets, embedded resources). |
| `backend/services/scheduling/` | Scheduling engine, job queue, executors, SQLite persistence. |
| `backend/utils/` | Logging, path helpers, browser/system tray utilities. |
| `backend/constants.py` | Shared constants (camera defaults, etc.). |
| `backend/config.py` | Environment-driven settings loader. |
| `backend/embedded_static.py` | Auto-generated bundle of frontend files (only valid after running embed script). |
| `backend/tests/` | Pytest suites for services (auth, camera, scheduling, etc.). |
| `frontend/` | React/Vite client, Dockerfile, environment file, build outputs. |
| `frontend/src/` | Application source (pages, components, hooks, context, services, styles). |
| `build_scripts/` | Automation for embedding resources and building executables (PyInstaller/Nuitka). |
| `data/` | Runtime artifacts: logs, backups, videos, SQLite DB. |
| `dist/`, `build/` | PyInstaller outputs (generated). |
| `docs/` | Existing topical documentation (monitoring, scheduling updates, logging guide).

## 4. Backend Architecture
### 4.1 Application entry point
- `backend/main.py` constructs the FastAPI app via `create_app()` and wires routers in `_include_routers()`. Startup tasks in `_register_startup_event()` warm services (`get_database_service()`, `get_monitoring_service()`), while `_register_shutdown_event()` closes resources cleanly. Static asset serving toggles between embedded (`EmbeddedResourceManager.get_resource()`) and filesystem mode.
- `main()` boots uvicorn with graceful shutdown (signal handlers defined near the top of the file). Environment toggles: `ROBOTCONTROL_SERVE_FRONTEND`, `STREAMING_CPU_*`, `ROBOTCONTROL_SKIP_CAMERA_INIT`.

### 4.2 API layer (`backend/api`)
Each router isolates a domain with clear entry points:
- `auth.py`: `@router.post("/login")` issues JWTs via `AuthService.create_tokens()`. `require_admin()` guard wraps admin-only endpoints. Refresh flow handled in `refresh_token()` which checks `AuthService.verify_refresh_token()`.
- `database.py`: `get_tables()` enumerates table metadata using `DatabaseService.list_tables()`, while `get_table_data()` pages results via `DatabaseService.fetch_table_rows()`. Stored procedures execute through `DatabaseService.execute_procedure()` with execution metadata reported in `ResponseMetadata`.
- `camera.py`: Websocket endpoint `camera_stream()` streams frames from `SharedFrameBuffer.next_frame()`; REST controls like `start_recording()` and `archive_experiment()` delegate to `AutomaticRecordingService` operations.
- `scheduling.py`: `@router.post("/jobs")` enqueues work through `SchedulerEngine.enqueue_job()`. Recovery flows (`manual_failover()`, `reset_queue()`) call into `JobQueueManager` and `SchedulingDatabaseManager`. Health snapshot `get_pipeline_status()` aggregates `SchedulerEngine.inspect_state()` and `ExperimentDiscovery.scan_pending_experiments()`.
- `admin.py`: `get_system_status()` collates CPU/disk metrics via `MonitoringService.collect_system_metrics()`. User CRUD is backed by `AuthService.list_users()` / `create_user()` for staged RBAC.
- Support routers: `backup.py` triggers `BackupService.run_full_backup()`, `system_config.py` surfaces runtime overrides stored in `config.py`, `monitoring.py` proxies `MonitoringService`, `experiments.py` shares aggregated experiment summaries, `system.py` responds with a lightweight health ping.
- All endpoints return `format_success()` / `format_error()` from `response_formatter.py` ensuring the `{success,data,metadata}` contract consumed by the frontend.

### 4.3 Services layer (`backend/services`)
- `database.py`: `DatabaseService` maintains lazy primary/secondary PyODBC connections. Methods like `execute_query()` and `_connect()` enforce timeouts and failover (see `_connect_with_retry()` for backoff). `get_status()` yields `DatabaseStatus` used by the API health endpoint.
- `auth.py`: `AuthService` stores users in `_users` with hashed passwords (see `_seed_default_users()`). Tokens issued via `create_tokens()` (`python-jose`), validated in `verify_token()`. Password hashing relies on `passlib.hash.bcrypt_sha256`.
- `camera.py`: `CameraService` uses OpenCV capture objects inside `CameraSession`. Stream frames land in `SharedFrameBuffer` (`shared_frame_buffer.py`), while `LiveStreamingService` (websocket_manager) handles subscription lifecycle and adaptive quality decisions.
- `automatic_recording.py`: orchestrates recording loops. `AutomaticRecordingService.start()` launches a background thread that calls `_record_loop()`; archiving is offloaded to `StorageManager.archive_experiment()`.
- `monitoring.py`: `MonitoringService.collect_dashboard_metrics()` collates camera, scheduling, and system information. Hooks into `ExperimentMonitor.observe_active_experiments()` for real-time updates.
- `backup.py`: `BackupService.run_full_backup()` executes SQL stored procedures through `DatabaseService` and mirrors files to `LOCAL_BACKUP_PATH`; retention enforced via `_prune_old_backups()`.
- `embedded_resources.py`: `EmbeddedResourceManager.get_resource()` caches assets keyed by path. ETags generated by `_generate_etag()` to allow conditional GETs.

### 4.4 Scheduling subsystem (`backend/services/scheduling`)
- `scheduler_engine.py`: `SchedulerEngine.enqueue_job()` validates payloads, persists to SQLite via `SchedulingDatabaseManager`, then schedules execution through `JobQueueManager`. Worker loop `_process_queue()` drives state transitions (`_start_job()`, `_complete_job()`, `_fail_job()`).
- `job_queue.py`: Manages in-memory queue with priority sorting (`_sort_queue()`), supports persistence by syncing with `sqlite_database.py` on mutation. `recover_jobs_from_disk()` resurrects jobs after crashes.
- `database_manager.py`: wraps SQL Server + SQLite access. Functions like `fetch_pending_jobs()` and `update_job_status()` coordinate with `sqlite_database` helper functions (`persist_job()` etc.).
- `experiment_discovery.py`: `scan_pending_experiments()` queries SQL via `DatabaseService` and filters results with `is_experiment_ready()`.
- `experiment_executor.py`: `execute_job()` launches Hamilton processes via `subprocess.Popen` and uses `PreExecutionChecks.run_all()` (from `pre_execution.py`) before dispatch. Completion events feed back into `SchedulerEngine`.
- `process_monitor.py`: `HamiltonProcessMonitor.watch()` checks OS processes at intervals, raising alerts through the `notifications` service.
- `sqlite_database.py`: Provides thin CRUD around the local scheduling store; key entry points `init_db()`, `persist_job()`, `load_jobs_by_state()`.

### 4.5 Utilities & configuration
- `backend/config.py`: `Settings` loads `.env`, exposes `DB_CONFIG_PRIMARY/SECONDARY`, path constants, and camera/streaming configuration maps used across services.
- `backend/utils/logging_setup.py`: `setup_logging()` applies rotating handlers under `data/logs` and installs rate-limit filters through `apply_rate_limit_filters()`; referenced from `backend/main.py` during startup.
- `backend/utils/data_paths.py`: `DataPathManager.ensure_directories()` creates log/video/backup folders, used during bootstrapping.
- `backend/constants.py`: enumerates camera defaults (`DEFAULT_FPS`, `ROLLING_CLIP_LIMIT`) and backup options consumed by services.
- Optional UX helpers: `system_tray.py` (tray icon menu with start/stop commands) and `browser_launcher.py` (open default browser to app URL) are invoked when running as a packaged exe.

### 4.6 Testing
- Tests live in `backend/tests/` and cover key workflows:
  - `test_auth.py`: exercises login, token verification, admin guard.
  - `test_camera.py`: mocks OpenCV to validate frame buffering and websocket broadcast cadence.
  - `test_scheduler_manual_recovery.py`, `test_scheduling_pipeline.py`: simulate queue crashes and recovery.
  - `test_notifications.py`: validates notification dispatch throttling.
- Run with `pytest backend/tests -q`; asynchronous tests use `pytest.mark.asyncio`. Keep tests hermetic via fixtures (`tmp_path`) and avoid writing to `data/`.

## 5. Frontend Architecture
### 5.1 Application shell (`frontend/src/App.tsx`)
- Provides routing with React Router v6. `AppContent` guards routes with `useAuth()`; tabs call `useNavigate()` to sync URLs. Mobile nav uses `MobileDrawer` while keyboard accessibility is maintained through `useKeyboardNavigation()` and `KeyboardShortcutsHelp`.
- Lazy-loaded pages are wrapped through `loadComponent()` (`frontend/src/utils/BundleOptimizer.ts`) which uses dynamic `import()` hints for optimal chunking.

### 5.2 State management & data fetching
- `context/AuthContext.tsx`: `AuthProvider` stores JWTs with `useState`; `login()` calls `authAPI.login()` and persists tokens in `localStorage`. `checkAuth()` runs on mount to fetch `/api/auth/me`.
- `services/api.ts`: Axios instance with request interceptor injecting `Authorization` header, response interceptor handling 401 and timeouts. Domain helpers:
  - `services/schedulingApi.ts`: functions like `fetchJobQueue()` and `runManualRecovery()` map directly to scheduling endpoints.
  - `services/backupApi.ts`: `startBackup()` triggers backup routes and polls status.
- React Query integration (where present) caches scheduling data, e.g., hooks in `hooks/useScheduling.ts` call `queryClient.invalidateQueries('jobs')` after mutations.

### 5.3 UI composition
- `pages/*`: route-level components coordinate view state.
  - `SchedulingPage.tsx`: orchestrates job list, actions, and modals; ties together `ScheduleList`, `ScheduleActions`, and `ExecutionHistory`.
  - `CameraPage.tsx`: manages live feeds via `useMonitoring()` and websockets, handles CPU safeguards through `cameraSafetyBanner` logic.
  - `DatabasePage.tsx`: uses `DatabaseTable` + `DatabaseOperations` to browse tables and execute procedures.
- `components/`: reusable widgets like `ScheduleList` (renders queue with virtualization), `IntelligentStatusMonitor` (aggregated metrics), `NavigationBreadcrumbs` (contextual navigation).
- Styling uses MUI theme overrides (`theme.ts`) plus `styles/` modules for layout-specific rules.

### 5.4 Tooling & testing
- Vite dev server runs on port 3005 (`npm run dev -- --port 3005`).
- ESLint (`npm run lint`) and TypeScript (`npm run type-check`) enforce quality. `test-setup.ts` configures React Testing Library should component tests be added.

## 6. Runtime Modes
- **Split dev servers:** Run backend via Uvicorn and frontend via Vite; configure `frontend/.env` (`VITE_API_BASE_URL=http://localhost:8005`).
- **Unified dev:** `python main.py` spawns backend (FastAPI) and frontend (Vite) subprocesses, manages lifecycle, and ensures data directories exist.
- **Packaged executable:** After embedding frontend assets, PyInstaller builds a single binary that serves both API and static files from memory.

## 7. Environment Setup
1. Install prerequisites: Python 3.11+, Node.js 18+, npm 9+, SQL Server ODBC Driver 11 (or newer) and local SQL Server connectivity. Install OpenCV dependencies (Visual C++ redistributables) if missing.
2. Create virtual environment: `python -m venv .venv`. Activate via `.\.venv\Scripts\Activate.ps1` when using PowerShell.
3. Install backend deps: `pip install -r backend/requirements.txt`.
4. Copy env template: `copy backend\.env.example backend\.env` and replace placeholder credentials/paths with local secrets.
5. Install frontend deps: `cd frontend && npm install`. Maintain `node_modules/` locally; do not commit.
6. Optional: configure Windows Firewall to allow FastAPI (port 8005) and Vite (port 3005) for LAN testing.

## 8. Local Development Workflow
- **Backend only:** `uvicorn backend.main:app --reload --port 8005`. Hot reload is active; logs stream to console and `data/logs/backend.log`.
- **Frontend only:** `npm run dev` inside `frontend/`; access http://localhost:3005. The dev server proxies API calls using `VITE_API_BASE_URL`.
- **Integrated run:** From repo root, execute `python main.py`. The orchestrator launches both processes, watches for exit signals, and cleans up automatically.
- **Database connectivity:** Ensure VPN/bridge to the lab SQL Server or update `.env` to point at a local test instance. For offline development, mock responses in API services or use local SQLite fixtures.
- **Static assets:** During dev mode the backend reads directly from `frontend/dist` (if `ROBOTCONTROL_SERVE_FRONTEND=1`) or delegates to Vite; no rebuild required unless packaging.

## 9. Testing & Quality Gates
- Backend unit/integration tests: `pytest backend/tests` (add `-k` to target subsystems). Use `pytest --maxfail=1` in CI to surface failures quickly.
- Frontend linting: `npm run lint`. Type safety: `npm run type-check`.
- Manual QA checklist: camera streaming, scheduling queue operations, backup trigger, admin dashboards. Coordinate with hardware lab time before touching production endpoints.

## 10. Build & Packaging Pipeline
1. **Frontend build:** `cd frontend && npm run build`. Outputs hashed assets under `frontend/dist/`.
2. **Embed assets:** From repo root, run `python build_scripts/embed_resources.py`. This regenerates `backend/embedded_static.py` with base64+gzip payloads. Commit the generated file when preparing a release.
3. **PyInstaller build:** `pyinstaller RobotControl.spec`. The spec draws in backend modules, embedded assets, and required hidden imports (FastAPI, uvicorn, OpenCV). Outputs go to `dist/RobotControl/`.
4. **Alternate builds:** `build_scripts/pyinstaller_build.py` wraps the above with argument parsing (logging, clean flags). `build_scripts/nuitka_build.py` is experimental for performance-focused builds.
5. **Post-build validation:** Launch the generated executable on a clean Windows VM, confirm it serves the embedded frontend, verifies SQL connectivity, and records videos to `data/videos`.
6. **Clean up:** Remove stale `build/` and `dist/` directories before new builds to avoid shipping outdated assets.

## 11. Data, Logging & Storage
- Logs default to `data/logs/*.log`; rotation is handled by `backend/utils/logging_setup.py`.
- Video segments accumulate in `data/videos/`; periodic cleanup is driven by `AUTO_RECORDING_CONFIG` thresholds.
- Backups go to `data/backups/` or network share specified via `.env` (`LOCAL_BACKUP_PATH`). Ensure service account has access.
- Scheduling metadata persists in `data/robotcontrol_scheduling.db`; delete carefully if you need a clean slate (queues will reset).

## 12. Maintenance Notes & Potential Redundancies
- `backend/services/scheduling/database_manager_backup.py` appears unused (no imports found); confirm before removal.
- `frontend/src/pages/CameraPageRefactored.tsx` is not referenced in routing; likely a prototype kept for reference. Evaluate whether to delete or wire into feature flags.
- `backend/api/example_standardized_endpoint.py` functions as documentation/sample code for response formatting; safe to keep but exclude from production routers.
- Secrets in `.env` / `.env.example` are placeholders copied from legacy systems--do **not** push real credentials to version control or public repos.
- `backend/services/embedded_resources.py` expects `backend/embedded_static.py`; running the backend without regenerating it after a frontend build may serve stale assets.

## 13. Onboarding Checklist
1. Read this guide plus `docs/developer-logging-guide.md` and `docs/admin-monitoring-overview.md` for operational context.
2. Set up Python + Node environments, configure `.env`, and verify `pytest` + `npm run lint` both pass locally.
3. Exercise core flows against a staging SQL Server: login, database browse, scheduling submit, camera stream.
4. Review `backend/tests/test_scheduling_pipeline.py` to understand the happy-path queue management before modifying scheduling code.
5. Coordinate with lab ops before changing backup paths or camera defaults; hardware dependencies can be fragile.

## 14. Useful Commands
- `uvicorn backend.main:app --reload --port 8005`
- `python main.py --frontend-port 3005 --backend-port 8005`
- `pytest backend/tests -k scheduling`
- `npm run dev -- --host 0.0.0.0 --port 3005`
- `npm run build && python build_scripts/embed_resources.py`
- `pyinstaller RobotControl.spec --clean`
### 2025-10-06 Backend bring-up notes
- Ensured embedded frontend assets are always served by setting `SERVE_FRONTEND_FROM_BACKEND = True` in `backend/main.py` so the backend serves the SPA without env configuration.
- Updated project venv metadata in `.venv/pyvenv.cfg` to point at local Python 3.13 (`C:\Python313`) eliminating runtime warnings about missing platform libraries.
