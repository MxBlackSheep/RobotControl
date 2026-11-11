"""
RobotControl Backend Application

Main FastAPI application that consolidates all simplified services.
Replaces the complex web_app structure with a clean, unified backend.
"""

# Divert packaged camera children before importing services with startup side effects.
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, HTMLResponse
import logging
import asyncio
import uvicorn
from datetime import datetime
import os
import sys
import argparse
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
import threading
import hashlib
import mimetypes
import inspect

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import our simplified API routers
from backend.version import __version__
from backend.api.database import router as database_router
from backend.api.database_tools import router as database_tools_router
from backend.api.auth import router as auth_router
from backend.api.admin import router as admin_router
from backend.api.monitoring import router as monitoring_router
from backend.api.pyhsl import router as pyhsl_router
from backend.services.pyhsl_monitor import get_pyhsl_monitor
from backend.api.experiments import router as experiments_router
from backend.api.backup import router as backup_router
from backend.api.camera import router as camera_router
from backend.api.scheduling import router as scheduling_router
from backend.api.sqlite_health import router as sqlite_health_router
from backend.api.system import router as system_router
from backend.api.labware import router as labware_router
from backend.api.maintenance import router as maintenance_router
from backend.api.logfiles import router as logfiles_router

# Import services for initialization
from backend.services.hxrun_maintenance import get_hxrun_maintenance_service

from backend.services.embedded_resources import get_resource_manager
from backend.utils.data_paths import get_path_manager, is_compiled_mode
from backend.api.response_formatter import ResponseFormatter

EMBEDDED_MODE = is_compiled_mode()

from backend.utils.logging_setup import setup_logging


def _env_flag(name: str, default: str = "0") -> bool:
    value = os.getenv(name, default)
    return value.lower() in {"1", "true", "yes", "on"}


def _env_scheduler_autostart_delay(name: str, default: int) -> Optional[int]:
    """Parse scheduler auto-start delay from environment."""
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    lowered = raw.lower()
    if lowered in {"disable", "disabled", "off", "none", "never"}:
        return None
    try:
        value = int(raw)
        return max(0, value)
    except ValueError:
        return default

data_paths = get_path_manager()
logs_dir = data_paths.logs_path

log_level_name = os.getenv("ROBOTCONTROL_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)

console_level_name = os.getenv("ROBOTCONTROL_CONSOLE_LOG_LEVEL", log_level_name).upper()
console_level = getattr(logging, console_level_name, log_level)

logging_handlers = setup_logging(
    logs_dir,
    log_level=log_level,
    console_level=console_level,
)

# Ensure all backend service loggers propagate to root
backend_loggers = [
    "backend",
    "backend.services",
    "backend.services.automatic_recording",
    "backend.services.storage_manager",
    "backend.services.camera",
    "backend.services.shared_frame_buffer",
    "backend.services.experiment_monitor",
    "backend.services.scheduling",
    "backend.services.scheduling.scheduler_engine",
    "backend.services.scheduling.experiment_executor",
    "backend.services.scheduling.database_manager",
    "backend.utils.data_paths",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
]

verbosity_overrides = {
    "backend.services.automatic_recording": logging.INFO,
    "backend.services.camera": logging.WARNING,
    "backend.services.storage_manager": logging.INFO,
    "backend.services.experiment_monitor": logging.WARNING,
    "backend.services.shared_frame_buffer": logging.WARNING,
    "backend.services": logging.INFO,
    "backend.utils.data_paths": logging.WARNING,
}

for logger_name in backend_loggers:
    target_logger = logging.getLogger(logger_name)
    if log_level <= logging.DEBUG:
        target_level = log_level
    else:
        target_level = verbosity_overrides.get(logger_name, log_level)
    target_logger.setLevel(target_level)
    target_logger.propagate = True

_SCHEDULER_AUTOSTART_DELAY_SECONDS: Optional[int] = _env_scheduler_autostart_delay(
    "ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS",
    60,
)


def configure_uvicorn_logging(handlers=logging_handlers) -> None:
    """Configure uvicorn loggers to use our handlers."""
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")

    for uv_logger in (uvicorn_logger, uvicorn_access_logger, uvicorn_error_logger):
        uv_logger.handlers = []
        uv_logger.propagate = False
        uv_logger.addHandler(handlers.console)
        uv_logger.addHandler(handlers.application)
        uv_logger.addHandler(handlers.error)


for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass


configure_uvicorn_logging()

async def _auto_start_scheduler_after_delay(delay_seconds: int) -> None:
    """Auto-start the scheduler service after an optional delay."""
    try:
        await asyncio.sleep(max(0, delay_seconds))
        from backend.services.scheduling import get_scheduler_engine

        scheduler = await asyncio.to_thread(get_scheduler_engine)
        status = await asyncio.to_thread(scheduler.get_status)
        if status.get("is_running"):
            logger.info("Scheduler auto-start skipped because it is already running")
            return

        if await asyncio.to_thread(scheduler.start):
            logger.info(
                "Scheduler auto-started successfully after %s seconds",
                delay_seconds,
            )
        else:
            logger.error("Scheduler auto-start failed to start the service")
    except asyncio.CancelledError:
        logger.info("Scheduler auto-start task cancelled before execution")
        raise
    except Exception as exc:
        logger.error("Scheduler auto-start task encountered an error: %s", exc)

# Get logger for this module
logger = logging.getLogger(__name__)

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start services once and finish every stop step, including after a failed start."""
    from backend.services.log_readers import LogReaderManager
    from backend.services.database_tools import get_database_tools, close_database_tools
    from backend.services.health_sampler import health_sampler
    from backend.services.automatic_recording import get_automatic_recording_service
    from backend.services.live_streaming import get_live_streaming_service
    from backend.services.scheduling import get_scheduler_engine
    from backend.services.camera import get_camera_service

    scheduler_task = None
    diagnostics = None
    app.state.shutdown_complete.clear()
    try:
        logger.info("Starting RobotControl %s; data folder=%s", __version__, data_paths.base_path)
        try:
            app.state.log_readers = await asyncio.to_thread(LogReaderManager, app.state.log_reader_cache)
        except OSError as exc:
            logger.warning("Log reading cache unavailable: %s", exc)
        try:
            await asyncio.to_thread(get_database_tools)
        except Exception as exc:
            logger.error("Database packages unavailable: %s", exc)
        health_sampler.start()
        if _env_flag("ROBOTCONTROL_RESOURCE_DIAGNOSTICS"):
            from backend.services.resource_diagnostics import ResourceDiagnostics
            diagnostics = ResourceDiagnostics(Path(logs_dir) / "diagnostics", loop=asyncio.get_running_loop())
            try:
                diagnostics.start()
            except Exception as exc:
                logger.warning("Resource diagnostics unavailable: %s", exc)
        if _SCHEDULER_AUTOSTART_DELAY_SECONDS is not None:
            scheduler_task = asyncio.create_task(_auto_start_scheduler_after_delay(_SCHEDULER_AUTOSTART_DELAY_SECONDS))
            logger.info("Scheduler auto-start scheduled to run in %s seconds", _SCHEDULER_AUTOSTART_DELAY_SECONDS)
        else:
            logger.info("Scheduler auto-start disabled by configuration")
        try:
            get_automatic_recording_service().start_automatic_recording()
        except Exception as exc:
            logger.warning("AutoRecording | event=start_failed | error=%s", exc)
        try:
            get_hxrun_maintenance_service().start()
            logger.info("HxRun maintenance enforcer initialized")
        except Exception as exc:
            logger.warning("Failed to start HxRun maintenance enforcer: %s", exc)
        get_pyhsl_monitor().start()
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        steps = [
            ("PyHSL monitor", lambda: get_pyhsl_monitor().stop()),
            ("Log readers", lambda: app.state.log_readers.close() if getattr(app.state, "log_readers", None) else None),
            ("Health sampler", health_sampler.stop),
            ("Database tools", close_database_tools),
            ("Resource diagnostics", lambda: diagnostics.stop() if diagnostics else None),
            ("Live streaming service", lambda: get_live_streaming_service().stop_service()),
            ("Automatic recording service", lambda: get_automatic_recording_service().stop_automatic_recording()),
            ("Scheduling service", lambda: get_scheduler_engine().stop()),
            ("HxRun maintenance enforcer", lambda: get_hxrun_maintenance_service().stop()),
            ("Camera service", lambda: get_camera_service().shutdown()),
        ]
        for name, stop in steps:
            try:
                result = await asyncio.to_thread(stop)
                if inspect.isawaitable(result):
                    await result
                logger.info("%s stopped", name)
            except Exception:
                logger.exception("Error stopping %s", name)
        logger.info("Backend session stopped | pid=%s", os.getpid())
        app.state.shutdown_complete.set()

# Create FastAPI application
app = FastAPI(
    title="RobotControl Backend",
    description="Unified backend for Hamilton VENUS liquid handling robot management",
    version=__version__,
    # The packaged app is reachable through a public tunnel; its API description is not published.
    docs_url=None if EMBEDDED_MODE else "/docs",
    redoc_url=None if EMBEDDED_MODE else "/redoc",
    openapi_url=None if EMBEDDED_MODE else "/openapi.json",
    lifespan=lifespan,
)

# Share the logger's actual root with all log browsing/reading endpoints.
app.state.log_root = Path(logging_handlers.application.baseFilename).parent
app.state.log_reader_cache = data_paths.temp_path / "log-readers"
app.state.shutdown_complete = threading.Event()

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8005",  # Unified development and production
        "http://127.0.0.1:8005",  # Unified development and production (127.0.0.1)
        # Legacy frontend ports for compatibility during transition
        "http://localhost:3005",  # Force Port Strategy - Frontend  
        "http://localhost:3000",  # React dev server (legacy)
        "http://localhost:3001",  # React dev server alt
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3005",  # Force Port Strategy - Frontend (127.0.0.1)
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001", 
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router)
app.include_router(pyhsl_router)
app.include_router(database_router)
app.include_router(database_tools_router)
app.include_router(experiments_router)
app.include_router(camera_router, prefix="/api", tags=["camera"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(backup_router, prefix="/api/admin/backup", tags=["backup", "admin"])
app.include_router(monitoring_router, prefix="/api/monitoring", tags=["monitoring"])
app.include_router(system_router, tags=["system"])
app.include_router(logfiles_router, tags=["logfiles"])
app.include_router(scheduling_router, tags=["scheduling"])
app.include_router(sqlite_health_router)
app.include_router(labware_router, tags=["labware"])
app.include_router(maintenance_router, tags=["maintenance"])

# Health check endpoint (must be before catch-all route)
@app.get("/health")
async def health_check():
    """Fast health check - no dependencies"""
    return {
        "service": "RobotControl Backend",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message": "Server is running"
    }

def _is_asset_path(path: str) -> bool:
    """Files (not page routes) must 404 when missing. Serving index.html for an old
    hashed chunk after an upgrade makes the browser's module import fail."""
    return path.startswith('assets/') or '.' in path.split('/')[-1]


frontend_dist = Path(project_root) / "frontend" / "dist"


def _static_resource(path: str):
    if EMBEDDED_MODE:
        return get_resource_manager().get_resource(path)
    root = frontend_dist.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=404, detail="File not found")
    if not target.is_file():
        return None
    content = target.read_bytes()
    mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return content, mime, '"' + hashlib.sha256(content).hexdigest() + '"'


@app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
async def serve_static(request: Request, path: str):
    if path == "api" or path.startswith(("api/", "docs", "redoc", "auth/")) or path == "health":
        raise HTTPException(status_code=404, detail="Not found")
    resource = _static_resource(path or "index.html")
    if resource is None and not _is_asset_path(path):
        resource = _static_resource("index.html")
    if resource is None:
        raise HTTPException(status_code=404, detail="File not found")
    content, mime, etag = resource
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    headers = {"etag": etag}
    if EMBEDDED_MODE:
        headers.update(get_resource_manager().get_cache_headers(mime))
    return Response(content=content, media_type=mime, headers=headers)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", exc_info=(type(exc), exc, exc.__traceback__))
    return ResponseFormatter.server_error()


def main():
    """Main function to run the server"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="RobotControl Backend Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  RobotControl.exe                    # Start server on default port 8005
  RobotControl.exe --port 8080        # Start server on port 8080
  RobotControl.exe --host 127.0.0.1   # Start server on localhost only
        """
    )
    parser.add_argument('--port', type=int, default=8005, 
                       help='Port to run the server on (default: 8005)')
    parser.add_argument('--host', type=str, default="0.0.0.0",
                       help='Host to bind the server to (default: 0.0.0.0)')
    parser.add_argument('--version', action='version', version=f"RobotControl {__version__}")
    
    args = parser.parse_args()

    server = uvicorn.Server(uvicorn.Config(
        app=app, host=args.host, port=args.port, reload=False,
        log_level="info", access_log=False, proxy_headers=False,
        use_colors=False, log_config=None, timeout_graceful_shutdown=5,
    ))
    tray = None
    if EMBEDDED_MODE:
        from backend.utils.system_tray import RobotControlSystemTray
        tray = RobotControlSystemTray(args.port, shutdown_complete=app.state.shutdown_complete)
        def stop_server():
            server.should_exit = True
        tray.start(stop_server)
    try:
        server.run()
    finally:
        if tray:
            tray.stop()


if __name__ == "__main__":
    main()
