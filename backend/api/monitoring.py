from starlette.concurrency import run_in_threadpool
from backend.services.health_sampler import health_sampler
"""
RobotControl Monitoring API
Monitoring endpoints for system status and experiments
"""

from fastapi import APIRouter, Depends
import logging
import time

from backend.services.auth import get_current_user
from backend.services.database import get_database_service

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/databases")
def get_database_connections(current_user: dict = Depends(get_current_user)):
    """The SQL Server connections RobotControl depends on and whether each opens now.

    The built-in connection (settings.DB_CONFIG_PRIMARY) still reads Hamilton run records and
    serves labware and backup; the saved workspace connections serve the viewer, packages
    and schedules' before-run steps. connections is null when they could not be listed.
    """
    native = get_database_service()
    status_ = native.get_status()
    built_in = dict(id="built-in", name="Built-in Hamilton connection", access="built-in",
                    server=native._primary_config.get("server"), database=native._primary_config.get("database"),
                    uses=["Hamilton run records", "Labware", "Backup and restore"],
                    state="connected" if status_.is_connected else "failed", message=status_.error_message)
    try:
        from backend.services.database_tools import get_database_tools
        workspace = get_database_tools().connection_health()
    except Exception:
        logger.exception("Saved database connections could not be checked")
        workspace = None
    return ResponseFormatter.success(data=dict(
        built_in=built_in,
        connections=workspace["connections"] if workspace else None,
        checked_at=workspace["checked_at"] if workspace else None,
    ))

@router.get("/system-health")
async def get_system_health(current_user: dict = Depends(get_current_user)):
    """Get current system health metrics"""
    start_time = time.time()
    
    try:
        from datetime import datetime
        
        metrics = await run_in_threadpool(health_sampler.snapshot)
        health_data = {"system": metrics, "sampled_at": metrics["timestamp"]}

        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_system_health")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("cpu_percent", metrics["cpu_percent"])
        metadata.add_metadata("memory_percent", metrics["memory_percent"])
        
        return ResponseFormatter.success(
            data=health_data,
            metadata=metadata,
            message="System health retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving system health",
            details=str(e)
        )
