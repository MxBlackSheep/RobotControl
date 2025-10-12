# Developer Logging Guide

## Primary Logs
- Main file lives at `data/logs/pyrobot_backend.log`; each start creates a same-day alias (`pyrobot_backend_<YYYY-MM-DD>.log`) for easy archival. Rotations gzip automatically and keep 14 days by default.
- High-severity messages (WARNING+) duplicate into `pyrobot_backend_error.log` with the same alias pattern. Both files flush on each write to avoid buffering surprises.
- Session boundaries are marked with a 72-character separator and PID, so restarts or multiple runs per day are obvious when skimming the log.

## Noise Controls
- `backend/main.py` sets per-namespace logging levels through `verbosity_overrides`. Most chatty services (automatic recording, storage manager, experiment monitor, uvicorn access) default to WARNING; tweak those entries if you need finer detail.
- The rate-limiting filter in `backend/utils/logging_setup.py` suppresses repeated INFO lines from automatic recording and monitoring. Adjust via `PYROBOT_LOG_RATE_LIMIT_AUTOMATION` / `_MONITORING` (seconds) or raise the exempt level when debugging.

## Environment Variables
- `PYROBOT_LOG_LEVEL` (default `INFO`) and `PYROBOT_CONSOLE_LOG_LEVEL` control overall verbosity; `PYROBOT_LOG_JSON=1` switches the formatter to JSON for log shipping.
- Retention can be tuned with `PYROBOT_LOG_RETENTION_DAYS` and `PYROBOT_LOG_ERROR_RETENTION_DAYS`.
- All file handlers live under the path returned by `DataPathManager.logs_path`; the directory is created at startup if missing.

## Uvicorn & Reloading
- Auto-reload is disabled (`uvicorn.run(..., reload=False)`) to keep session logs clean.
- Uvicorn access logging is off; only warnings/errors surface through the shared handlers.

## Structured Logging
- JSON logging can be enabled via `PYROBOT_LOG_JSON=1`; both the main and error files emit structured records ready for ingestion (Elastic/OpenSearch, etc.).

## Troubleshooting Notes
- On platforms that cannot create hard links for the daily alias, the handler drops a stub file noting the limitation and continues using the primary path.
- If logs stay noisy, confirm the namespace is listed in `verbosity_overrides` or set an explicit level where the logger is created (e.g., `logging.getLogger("backend.services.camera").setLevel(logging.INFO)`).
