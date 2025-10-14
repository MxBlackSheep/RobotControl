"""
RobotControl Simplified Backend Application

Main FastAPI application that consolidates all simplified services.
Replaces the complex web_app structure with a clean, unified backend.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, HTMLResponse
import logging
import asyncio
import uvicorn
from datetime import datetime
import os
import sys
import signal
import atexit
import argparse
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

# Patch bcrypt metadata to remain compatible with passlib when using bcrypt>=4

def _patch_bcrypt_metadata() -> None:
    patch_logger = logging.getLogger(__name__)
    try:
        import bcrypt  # type: ignore
    except Exception as exc:
        patch_logger.debug("bcrypt not available; skipping metadata patch: %s", exc)
        return

    about = getattr(bcrypt, "__about__", None)
    if about and getattr(about, "__version__", None):
        return

    version = getattr(bcrypt, "__version__", None)
    if not version:
        patch_logger.debug("bcrypt version metadata unavailable; skipping patch")
        return

    class _About:
        __version__ = version

    try:
        bcrypt.__about__ = _About()  # type: ignore[attr-defined]
        patch_logger.info("Patched bcrypt metadata for passlib compatibility (version %s)", version)
    except Exception as exc:
        patch_logger.warning("Unable to patch bcrypt metadata: %s", exc)


_patch_bcrypt_metadata()

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import our simplified API routers
from backend.api.database import router as database_router
from backend.api.auth import router as auth_router
from backend.api.admin import router as admin_router
from backend.api.monitoring import router as monitoring_router
from backend.api.experiments import router as experiments_router
from backend.api.backup import router as backup_router
from backend.api.system_config import router as system_config_router
from backend.api.camera import router as camera_router
from backend.api.scheduling import router as scheduling_router
from backend.api.system import router as system_router

# Import services for initialization
from backend.services.database import get_database_service
from backend.services.auth import get_auth_service
from backend.services.monitoring import get_monitoring_service

# Import embedded resource manager
# Only use embedded mode when running as compiled executable
import sys
is_compiled = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
SERVE_FRONTEND_FROM_BACKEND = True  # Always serve static frontend assets from backend

try:
    from backend.services.embedded_resources import get_resource_manager
    EMBEDDED_MODE = is_compiled  # Only use embedded resources in compiled mode
except ImportError:
    EMBEDDED_MODE = False

if not EMBEDDED_MODE:
    logger = logging.getLogger(__name__)
    logger.info("Running in development mode - serving from filesystem")

# Configure comprehensive logging with rotation and rate limiting
try:
    from backend.utils.data_paths import DataPathManager
except ImportError:  # pragma: no cover - fallback for legacy packaging
    from utils.data_paths import DataPathManager

try:
    from backend.utils.logging_setup import apply_rate_limit_filters, setup_logging
except ImportError:  # pragma: no cover - fallback for legacy packaging
    from utils.logging_setup import apply_rate_limit_filters, setup_logging


def _env_flag(name: str, default: str = "0") -> bool:
    value = os.getenv(name, default)
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        parsed = int(raw)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


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

data_paths = DataPathManager()
logs_dir = data_paths.logs_path

log_level_name = os.getenv("ROBOTCONTROL_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)

console_level_name = os.getenv("ROBOTCONTROL_CONSOLE_LOG_LEVEL", log_level_name).upper()
console_level = getattr(logging, console_level_name, log_level)

retention_days = _env_int("ROBOTCONTROL_LOG_RETENTION_DAYS", 14)
error_retention_days = _env_int("ROBOTCONTROL_LOG_ERROR_RETENTION_DAYS", 30)
use_json_logs = _env_flag("ROBOTCONTROL_LOG_JSON")

logging_handlers = setup_logging(
    logs_dir,
    log_level=log_level,
    retention_days=retention_days,
    error_retention_days=error_retention_days,
    use_json=use_json_logs,
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
    "backend.services.monitoring",
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
    "backend.services.automatic_recording": logging.WARNING,
    "backend.services.monitoring": logging.WARNING,
    "backend.services.camera": logging.WARNING,
    "backend.services.storage_manager": logging.WARNING,
    "backend.services.experiment_monitor": logging.WARNING,
    "backend.services.shared_frame_buffer": logging.WARNING,
    "backend.services": logging.INFO,
    "backend.utils.data_paths": logging.WARNING,
    "uvicorn": logging.WARNING,
    "uvicorn.error": logging.WARNING,
    "uvicorn.access": logging.WARNING,
}

for logger_name in backend_loggers:
    target_logger = logging.getLogger(logger_name)
    if log_level <= logging.DEBUG:
        target_level = log_level
    else:
        target_level = verbosity_overrides.get(logger_name, log_level)
    target_logger.setLevel(target_level)
    target_logger.propagate = True

rate_limit_config = {
    "backend.services.automatic_recording": os.getenv("ROBOTCONTROL_LOG_RATE_LIMIT_AUTOMATION", "60"),
    "backend.services.monitoring": os.getenv("ROBOTCONTROL_LOG_RATE_LIMIT_MONITORING", "30"),
}
rate_limit_config = {k: v for k, v in rate_limit_config.items() if v not in {None, ""}}
apply_rate_limit_filters(rate_limit_config, exempt_level=logging.WARNING)

_SCHEDULER_AUTOSTART_DELAY_SECONDS: Optional[int] = _env_scheduler_autostart_delay(
    "ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS",
    60,
)
_scheduler_autostart_task: Optional[asyncio.Task] = None
STATIC_ACCESS_PATH_PREFIXES = ("/assets/", "/favicon.ico")


class SuppressStaticAccessFilter(logging.Filter):
    """Filter uvicorn access log entries that represent static asset hits."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_line = ""
        if isinstance(record.args, dict):
            request_line = record.args.get("request_line") or ""
        elif isinstance(record.args, tuple) and record.args:
            request_line = record.args[1] if len(record.args) > 1 else ""

        if any(prefix in request_line for prefix in STATIC_ACCESS_PATH_PREFIXES):
            return False

        message = record.getMessage()
        return not any(prefix in message for prefix in STATIC_ACCESS_PATH_PREFIXES)


def configure_uvicorn_logging(handlers=logging_handlers) -> None:
    """Configure uvicorn loggers to use our handlers and filters."""
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")

    if not any(isinstance(f, SuppressStaticAccessFilter) for f in uvicorn_access_logger.filters):
        uvicorn_access_logger.addFilter(SuppressStaticAccessFilter())

    for uv_logger in (uvicorn_logger, uvicorn_access_logger, uvicorn_error_logger):
        uv_logger.handlers = []
        uv_logger.setLevel(max(logging.WARNING, log_level))
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
    global _scheduler_autostart_task
    try:
        await asyncio.sleep(max(0, delay_seconds))
        from backend.services.scheduling import get_scheduler_engine

        scheduler = get_scheduler_engine()
        status = scheduler.get_status()
        if status.get("is_running"):
            logger.info("Scheduler auto-start skipped because it is already running")
            return

        if scheduler.start():
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
    finally:
        _scheduler_autostart_task = None

# Get logger for this module
logger = logging.getLogger(__name__)

logger.info(
    "Backend logging initialized | file=%s | alias=%s | retention_days=%s | error_file=%s | error_alias=%s | json=%s",
    logging_handlers.application.baseFilename,
    getattr(logging_handlers.application, "alias_path", None) or "alias-disabled",
    retention_days,
    getattr(logging_handlers.error, "baseFilename", None),
    getattr(logging_handlers.error, "alias_path", None) or "alias-disabled",
    use_json_logs,
)

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown sequences."""
    session_marker = "=" * 72
    logger.info("")
    logger.info(session_marker)
    logger.info("Backend session starting | pid=%s", os.getpid())

    logger.info("Starting RobotControl Simplified Backend...")

    logger.info("All services configured for lazy loading")
    logger.info("Authentication: ready (will initialize on first login)")
    logger.info("Database: ready (will connect on first query)")
    logger.info("Camera: ready (will initialize on first access)")
    logger.info("Monitoring: ready (will start on first request)")
    logger.info("Streaming: ready (will activate on first connection)")
    logger.info("Scheduling: ready (will load on first scheduler access)")
    
    global _scheduler_autostart_task
    if _SCHEDULER_AUTOSTART_DELAY_SECONDS is not None:
        try:
            loop = asyncio.get_running_loop()
            if _scheduler_autostart_task and not _scheduler_autostart_task.done():
                _scheduler_autostart_task.cancel()
            _scheduler_autostart_task = loop.create_task(
                _auto_start_scheduler_after_delay(_SCHEDULER_AUTOSTART_DELAY_SECONDS)
            )
            logger.info(
                "Scheduler auto-start scheduled to run in %s seconds",
                _SCHEDULER_AUTOSTART_DELAY_SECONDS,
            )
        except RuntimeError as exc:
            logger.warning("Unable to schedule scheduler auto-start task: %s", exc)
    else:
        logger.info("Scheduler auto-start disabled by configuration")
    

    try:
        from backend.services.automatic_recording import get_automatic_recording_service
        auto_recording_service = get_automatic_recording_service()
        if auto_recording_service.is_enabled():
            started = auto_recording_service.start_automatic_recording()
            if not started:
                status = auto_recording_service.get_automation_status()
                logger.debug("AutoRecording | event=startup_request_ignored | state=%s", status.state.value)
        else:
            logger.info("AutoRecording | event=start_skipped | reason=disabled")
    except Exception as exc:
        logger.warning("AutoRecording | event=start_failed | error=%s", exc)

    logger.info("RobotControl Simplified Backend startup complete - all services ready for lazy loading!")
    try:
        yield
    finally:
        logger.info("Shutting down RobotControl Simplified Backend...")
        
        if _scheduler_autostart_task:
            if not _scheduler_autostart_task.done():
                _scheduler_autostart_task.cancel()
                try:
                    await _scheduler_autostart_task
                except asyncio.CancelledError:
                    logger.info("Scheduler auto-start task cancelled during shutdown")
                except Exception as exc:
                    logger.warning("Scheduler auto-start task raised during shutdown: %s", exc)
            _scheduler_autostart_task = None
        
        try:
            db_service = get_database_service()
            db_service.clear_connection_pool()

            monitoring_service = get_monitoring_service()
            monitoring_service.stop_monitoring()

            try:
                from backend.services.live_streaming import get_live_streaming_service
                streaming_service = get_live_streaming_service()
                await streaming_service.stop_service()
                logger.info("Live streaming service stopped")
            except Exception as exc:
                logger.warning("Error stopping live streaming service: %s", exc)

            try:
                from backend.services.automatic_recording import get_automatic_recording_service
                auto_recording_service = get_automatic_recording_service()
                auto_recording_service.stop_automatic_recording()
                logger.info("Automatic recording service stopped")
            except Exception as exc:
                logger.warning("Error stopping automatic recording service: %s", exc)

            try:
                from backend.services.scheduling import get_scheduler_engine
                scheduler_engine = get_scheduler_engine()
                scheduler_engine.stop()
                logger.info("Scheduling service stopped")
            except Exception as exc:
                logger.warning("Error stopping scheduling service: %s", exc)

            try:
                from backend.services.camera import get_camera_service
                camera_service = get_camera_service()
                camera_service.disable_streaming_integration()
                camera_service.shutdown()
                logger.info("Camera service shutdown complete")
            except Exception as exc:
                logger.warning("Error stopping camera service: %s", exc)

            logger.info("Services cleaned up successfully")
        except Exception as exc:
            logger.error("Error during shutdown: %s", exc)

        logger.info("Backend session stopped | pid=%s", os.getpid())
        logger.info(session_marker)

# Create FastAPI application
app = FastAPI(
    title="RobotControl Simplified Backend",
    description="Unified backend for Hamilton VENUS liquid handling robot management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

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

# Graceful shutdown handling
def graceful_shutdown(signum=None, frame=None):
    """Handle graceful shutdown on signal"""
    logger.info(f"Received shutdown signal {signum}, initiating graceful shutdown...")
    
    try:
        # Stop camera service to save any unsaved clips
        try:
            from backend.services.camera import get_camera_service
            camera_service = get_camera_service()
            camera_service.shutdown()
            logger.info("Camera service shutdown complete")
        except Exception as e:
            logger.warning(f"Error stopping camera service: {e}")
        
        # Stop automatic recording service
        try:
            from backend.services.automatic_recording import get_automatic_recording_service
            auto_recording_service = get_automatic_recording_service()
            auto_recording_service.stop_automatic_recording()
            logger.info("Automatic recording service stopped")
        except Exception as e:
            logger.warning(f"Error stopping automatic recording service: {e}")
            
        # Stop monitoring service
        try:
            from backend.services.monitoring import get_monitoring_service
            monitoring_service = get_monitoring_service()
            monitoring_service.stop_monitoring()
            logger.info("Monitoring service stopped")
        except Exception as e:
            logger.warning(f"Error stopping monitoring service: {e}")
            
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
    finally:
        logger.info("Graceful shutdown complete")
        if signum:
            sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, graceful_shutdown)   # Ctrl+C
signal.signal(signal.SIGTERM, graceful_shutdown)  # Terminate signal

# Register atexit handler as final fallback
atexit.register(graceful_shutdown)

# Include API routers
app.include_router(auth_router)
app.include_router(database_router)
app.include_router(experiments_router)
app.include_router(camera_router, prefix="/api", tags=["camera"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(backup_router, prefix="/api/admin/backup", tags=["backup", "admin"])
app.include_router(monitoring_router, prefix="/api/monitoring", tags=["monitoring"])
app.include_router(system_config_router, prefix="/api/admin/system", tags=["admin", "system"])
app.include_router(system_router, tags=["system"])
app.include_router(scheduling_router, tags=["scheduling"])

# Health check endpoint (must be before catch-all route)
@app.get("/health")
async def health_check():
    """Fast health check - no dependencies"""
    return {
        "service": "RobotControl Simplified Backend",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message": "Server is running"
    }

# Add embedded static file serving (must be after API routes)
if EMBEDDED_MODE:
    resource_manager = get_resource_manager()
    
    @app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def serve_embedded_static(request: Request, path: str):
        """Serve embedded static files for single-exe mode"""
        # Don't serve API routes as static files
        if (path.startswith('api/') or path.startswith('docs') or path.startswith('redoc') or 
            path == 'health' or path.startswith('auth/')):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Handle root path
        if not path or path == '/':
            path = 'index.html'
        
        # Get resource from embedded files
        resource = resource_manager.get_resource(path)
        if not resource:
            # Try index.html for SPA routing
            resource = resource_manager.get_resource('index.html')
            if not resource:
                raise HTTPException(status_code=404, detail="Resource not found")
        
        content, mime_type, etag = resource
        
        # Check if client has cached version
        client_etag = request.headers.get("if-none-match")
        if client_etag and client_etag == etag:
            return Response(status_code=304)
        
        # Get cache headers
        cache_headers = resource_manager.get_cache_headers(mime_type)
        
        # Return content with appropriate headers
        headers = {
            "etag": etag,
            "content-type": mime_type,
            **cache_headers
        }
        
        return Response(content=content, headers=headers, media_type=mime_type)

else:
    # Development mode - optionally serve from filesystem if explicitly enabled
    frontend_dist = Path(project_root) / "frontend" / "dist"
    if SERVE_FRONTEND_FROM_BACKEND and frontend_dist.exists():
        # Use manual route for development mode to avoid catching API routes
        @app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
        async def serve_static_dev(request: Request, path: str):
            """Serve static files for development mode"""
            # Don't serve API routes as static files
            if (path.startswith('api/') or path.startswith('docs') or path.startswith('redoc') or 
                path == 'health' or path.startswith('auth/') or path == 'api'):
                raise HTTPException(status_code=404, detail="Not found")
            
            # Handle root path
            if not path or path == '/':
                path = 'index.html'
            
            # Build full file path
            file_path = frontend_dist / path
            
            # Check if file exists
            if not file_path.exists() or not file_path.is_file():
                # Only fall back to index.html for navigation routes (not assets)
                if path.startswith('assets/') or '.' in path.split('/')[-1]:
                    # This is likely an asset file, return 404
                    raise HTTPException(status_code=404, detail="File not found")
                else:
                    # This is a navigation route, serve index.html for SPA routing
                    index_path = frontend_dist / 'index.html'
                    if index_path.exists():
                        file_path = index_path
                        path = 'index.html'
                    else:
                        raise HTTPException(status_code=404, detail="File not found")
            
            # Determine MIME type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Read and return file
            with open(file_path, 'rb') as f:
                content = f.read()
            
            return Response(content=content, media_type=mime_type)
            
        logger.info(f"Development mode: serving static files from {frontend_dist}")
    elif not SERVE_FRONTEND_FROM_BACKEND:
        logger.info("Static asset serving disabled; expecting external web server (set ROBOTCONTROL_SERVE_FRONTEND=1 to re-enable backend asset serving)")
    else:
        logger.info("No frontend build found - API only mode")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if app.debug else "An unexpected error occurred"
        }
    )


# Root endpoint
# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with basic information - respects lazy loading"""
    return {
        "service": "RobotControl Simplified Backend",
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message": "Services are lazy-loaded on first access",
        "endpoints": {
            "authentication": "/api/auth/",
            "database": "/api/database/",
            "backup": "/api/admin/backup/",
            "admin": "/api/admin/",
            "documentation": "/docs",
            "health": "/health"
        }
    }




# API info endpoint
@app.get("/api")
async def api_info():
    """API information and available endpoints"""
    return {
        "api": "RobotControl Simplified API",
        "version": "1.0.0",
        "endpoints": {
            "authentication": {
                "base_url": "/api/auth",
                "endpoints": [
                    "POST /api/auth/login",
                    "POST /api/auth/refresh",
                    "POST /api/auth/logout",
                    "GET /api/auth/me",
                    "GET /api/auth/users",
                    "GET /api/auth/status"
                ]
            },
            "database": {
                "base_url": "/api/database",
                "endpoints": [
                    "GET /api/database/status",
                    "GET /api/database/tables",
                    "GET /api/database/tables/{table_name}",
                    "POST /api/database/query",
                    "GET /api/database/monitoring",
                    "GET /api/database/performance"
                ]
            },
            "backup": {
                "base_url": "/api/admin/backup",
                "endpoints": [
                    "POST /api/admin/backup/create",
                    "GET /api/admin/backup/list",
                    "GET /api/admin/backup/{filename}/details",
                    "POST /api/admin/backup/restore/{filename}",
                    "DELETE /api/admin/backup/{filename}",
                    "GET /api/admin/backup/health"
                ],
                "note": "Admin authentication required for all backup operations"
            }
        },
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json"
        }
    }


def create_app() -> FastAPI:
    """Factory function to create the FastAPI app"""
    return app


def main():
    """Main function to run the server"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="RobotControl Simplified Backend Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  RobotControl.exe                    # Start server on default port 8005
  RobotControl.exe --port 8080        # Start server on port 8080
  RobotControl.exe --host 127.0.0.1   # Start server on localhost only
  RobotControl.exe --no-browser       # Start without opening browser
        """
    )
    parser.add_argument('--port', type=int, default=8005, 
                       help='Port to run the server on (default: 8005)')
    parser.add_argument('--host', type=str, default="0.0.0.0",
                       help='Host to bind the server to (default: 0.0.0.0)')
    parser.add_argument('--no-browser', action='store_true',
                       help='Do not automatically open browser')
    parser.add_argument('--version', action='version', version='RobotControl 1.0.0')
    
    args = parser.parse_args()
    
    logger.info("Starting RobotControl Simplified Backend Server...")
    
    # Detect if running as compiled executable
    is_compiled = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
    
    # Configuration
    host = args.host
    port = args.port
    reload = False  # Auto-reload disabled to keep sessions clean
    
    logger.info(f"Running mode: {'Compiled executable' if is_compiled else 'Development'}")
    logger.info("Auto-reload: Disabled")
    logger.info(f"Server will start on http://{host}:{port}")
    
    # Initialize system tray (only in compiled mode for now)
    tray = None
    if is_compiled:
        try:
            from backend.utils.system_tray import start_system_tray, update_tray_status, is_tray_available
            
            if is_tray_available():
                # Create stop callback for tray
                def stop_server():
                    logger.info("Server stop requested from system tray")
                    sys.exit(0)
                
                tray = start_system_tray(port, stop_server)
                update_tray_status("starting")
                logger.info("System tray icon initialized")
            else:
                logger.info("System tray not available - missing dependencies")
                
        except Exception as e:
            logger.warning(f"System tray initialization failed: {e}")
    
    try:
        # Update tray status to running
        if tray:
            update_tray_status("running")
            
        if is_compiled:
            # Configure uvicorn logging for compiled mode
            configure_uvicorn_logging()
            
            # For compiled executable, pass app object directly
            # Configure uvicorn to use existing logger configuration
            uvicorn_config = uvicorn.Config(
                app=app,
                host=host,
                port=port,
                reload=False,
                log_level="info",
                access_log=True,
                use_colors=False,  # Disable colors in compiled mode
                log_config=None,  # Use existing logger configuration
            )
            server = uvicorn.Server(uvicorn_config)
            server.run()
        else:
            # For development, use string reference for auto-reload
            uvicorn.run(
                "backend.main:app",
                host=host,
                port=port,
                reload=False,
                log_level="info",
                access_log=False,
                log_config=None
            )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        if tray:
            update_tray_status("stopped")
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        if tray:
            update_tray_status("error", str(e))
        sys.exit(1)
    finally:
        # Clean up tray
        if tray:
            try:
                from backend.utils.system_tray import stop_system_tray
                stop_system_tray()
            except:
                pass


if __name__ == "__main__":
    main()


