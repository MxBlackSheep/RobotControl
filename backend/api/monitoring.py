from starlette.concurrency import run_in_threadpool
from backend.services.health_sampler import health_sampler
"""
RobotControl Monitoring API
Monitoring endpoints for system status and experiments
"""

from fastapi import APIRouter, Depends, status
import logging
import time

from backend.services.auth import get_current_user
from backend.services.monitoring import get_monitoring_service
from backend.services.database import get_database_service
from backend.services.experiment_monitor import get_experiment_monitor
from backend.constants import HAMILTON_STATE_MAPPING

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/status")
async def get_monitoring_status(current_user: dict = Depends(get_current_user)):
    """Get monitoring service status and statistics"""
    start_time = time.time()
    
    try:
        monitoring_service = get_monitoring_service()
        stats = monitoring_service.get_monitoring_stats()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "monitoring_status")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        
        return ResponseFormatter.success(data=stats, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving monitoring status",
            details=str(e)
        )

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

@router.get("/experiments")
async def get_current_experiments(current_user: dict = Depends(get_current_user)):
    """Get current experiment monitoring data using centralized experiment monitor"""
    start_time = time.time()
    
    try:
        # Get experiment data from centralized experiment monitor
        current_experiment = await run_in_threadpool(lambda: get_experiment_monitor().get_current_experiment())
        
        experiments = []
        if current_experiment:
            # Use centralized Hamilton state mapping for consistency
            raw_state = str(current_experiment.run_state.value)
            display_state = HAMILTON_STATE_MAPPING.get(raw_state, raw_state)
            
            experiments = [{
                "ExperimentID": current_experiment.run_guid,
                "MethodName": current_experiment.method_name,
                "PlateID": "N/A",  # Not available in experiment monitor
                "StartTime": current_experiment.start_time.isoformat() if current_experiment.start_time else None,
                "EndTime": current_experiment.end_time.isoformat() if current_experiment.end_time else None,
                "Status": display_state,
                "RawState": current_experiment.raw_run_state or raw_state,
                "Progress": 100 if current_experiment.is_complete else (50 if current_experiment.is_in_progress else 0),
                "IsNewlyCompleted": current_experiment.is_newly_completed,
                "StateChangeTime": current_experiment.state_change_time.isoformat() if current_experiment.state_change_time else None
            }]
        
        data = {
            "experiments": experiments,
            "count": len(experiments)
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_current_experiments")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("experiment_count", len(experiments))
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting current experiments: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving experiment data",
            details=str(e)
        )

@router.get("/system-health")
async def get_system_health(current_user: dict = Depends(get_current_user)):
    """Get current system health metrics"""
    start_time = time.time()
    
    try:
        from datetime import datetime
        
        metrics = await run_in_threadpool(health_sampler.snapshot)
        cpu_percent = metrics["cpu_percent"]

        # Get database status
        db_service = get_database_service()
        db_status = await run_in_threadpool(db_service.get_status)
        
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "system": metrics,
            "sampled_at": metrics["timestamp"],
            "database": {
                "is_connected": db_status.is_connected,
                "mode": db_status.mode,
                "database_name": db_status.database_name,
                "server_name": db_status.server_name,
                "error_message": db_status.error_message
            }
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_system_health")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("cpu_percent", cpu_percent)
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

@router.post("/start")
async def start_monitoring(current_user: dict = Depends(get_current_user)):
    """Start the monitoring service (admin only)"""
    start_time = time.time()
    
    try:
        if current_user.get("role") != "admin":
            return ResponseFormatter.forbidden(
                message="Admin access required",
                details="Only admin users can start monitoring service"
            )
        
        monitoring_service = get_monitoring_service()
        
        if monitoring_service.is_running:
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "start_monitoring")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("was_already_running", True)
            
            return ResponseFormatter.success(
                data={"status": "already_running"},
                metadata=metadata,
                message="Monitoring service is already running"
            )
        
        monitoring_service.start_monitoring()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "start_monitoring")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("service_started", True)
        
        return ResponseFormatter.success(
            data={"status": "started"},
            metadata=metadata,
            message="Monitoring service started successfully"
        )
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        return ResponseFormatter.server_error(
            message="Error starting monitoring service",
            details=str(e)
        )

@router.post("/stop")
async def stop_monitoring(current_user: dict = Depends(get_current_user)):
    """Stop the monitoring service (admin only)"""
    start_time = time.time()
    
    try:
        if current_user.get("role") != "admin":
            return ResponseFormatter.forbidden(
                message="Admin access required",
                details="Only admin users can stop monitoring service"
            )
        
        monitoring_service = get_monitoring_service()
        
        if not monitoring_service.is_running:
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "stop_monitoring")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("was_already_stopped", True)
            
            return ResponseFormatter.success(
                data={"status": "already_stopped"},
                metadata=metadata,
                message="Monitoring service is already stopped"
            )
        
        monitoring_service.stop_monitoring()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "stop_monitoring")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("service_stopped", True)
        
        return ResponseFormatter.success(
            data={"status": "stopped"},
            metadata=metadata,
            message="Monitoring service stopped successfully"
        )
        
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        return ResponseFormatter.server_error(
            message="Error stopping monitoring service",
            details=str(e)
        )

