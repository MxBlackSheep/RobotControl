# AGENTS Runbook

## Backend Operations
- Start the backend from the repo root with `cd backend && python main.py --port 8005`; the service must listen on port 8005.
- Warm the database pool and verify connectivity with `python -c "from backend.services.database import get_database_service; print(get_database_service().get_status())"`.
- Collect the latest `pyrobot_backend_*.log` from `data/logs/` before beginning incident analysis.

## Diagnostics & Environment
- Database pooling auto-selects the best installed SQL Server ODBC driver. Missing driver errors mean Microsoft ODBC Driver 17 or 18 still needs to be installed on the host.
- Backend startup patches `bcrypt` metadata so passlib warnings disappear after a restart.
- Database performance metrics are throttled; only the first call or queries slower than ~500ms emit `METRIC: db_query_*` log lines.

## Camera & Streaming
- Run quick camera smoke tests (for example `python tmp_test_camera.py`) to confirm endpoints return HTTP 200 once `ResponseFormatter.success` is wired in.
- The streaming service auto-starts and logs `Streaming | event=*`. Blank frames from test hardware stop the WebSocket from pushing video; connect real capture input or configure a fallback source before expecting imagery.

## Scheduling & Recovery
- The scheduler auto-reschedules blocking conflicts with a two-minute delay (up to three attempts), logs the retry via `job_delayed`, and disables the schedule after retries exhaust.
- Before dispatching, the scheduler checks HamiltonVectorDB; experiments whose latest run ended `Aborted` or `Error` are flagged for manual recovery.
- Manual recovery actions trigger SMTP email alerts when configured so operators get notified as soon as intervention is required or resolved.

## Configuration Checklist
- SMTP (optional): configure host/port/sender/password and the manual recovery distribution list via the Scheduling → Email Settings admin tab; the scheduler now reads exclusively from the persisted NotificationSettings row.
- Before packaging PyInstaller builds, run `python backend/services/embed_resources.py` to embed the latest frontend and restart the backend with `PYROBOT_SERVE_FRONTEND=1` when validating the embedded bundle.
- PyInstaller builds load `build_scripts/runtime_hooks/silence_pkg_resources_warning.py` via `PyRobot.spec` to filter the deprecated `pkg_resources` warning—leave the runtime hook in place (or update it) when modifying the spec.

## Implementation Note
- Add implementation to docs/implementation-notes.md with newest note coming on top. 
- The note should aim for clarity and preciseness, while try to be as brief as possible. The note aims to keep tracks of the development process and guide future codex sessions. 
- For any requests proposed by the user: As always, review the relevant code, come up with ideas on how to fix them, then let the user know (before implementing). 
