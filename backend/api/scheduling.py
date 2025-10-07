"""
Scheduling API Router

RESTful API endpoints for experiment scheduling management.
Provides CRUD operations for scheduled experiments with role-based access control.

Features:
- Schedule creation, modification, and deletion
- Calendar data endpoints for frontend visualization
- Conflict detection and resolution
- Real-time status updates
- Role-based access control
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from backend.services.auth import get_current_user
from backend.services.scheduling import (
    get_scheduler_engine,
    get_scheduling_database_manager,
    get_job_queue_manager,
    get_hamilton_process_monitor
)
from backend.services.scheduling.experiment_discovery import get_experiment_discovery_service
from backend.models import (
    ScheduledExperiment,
    JobExecution,
    RetryConfig,
    CalendarEvent,
    ApiResponse
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])

# Service instances (lazy-loaded)
scheduler_engine = None
db_manager = None
queue_manager = None
process_monitor = None


def get_services():
    """Get lazy-loaded service instances"""
    global scheduler_engine, db_manager, queue_manager, process_monitor
    
    if scheduler_engine is None:
        scheduler_engine = get_scheduler_engine()
    if db_manager is None:
        db_manager = get_scheduling_database_manager()
    if queue_manager is None:
        queue_manager = get_job_queue_manager()
    if process_monitor is None:
        process_monitor = get_hamilton_process_monitor()
    
    return scheduler_engine, db_manager, queue_manager, process_monitor


@router.post("/create")
async def create_schedule(
    schedule_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new scheduled experiment
    
    Requires: admin or user role
    """
    try:
        logger.info(f"Create schedule request received: {schedule_data}")
        
        # Check user permissions
        if current_user.get("role") not in ["admin", "user"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Validate required fields
        required_fields = ["experiment_name", "experiment_path", "schedule_type", "estimated_duration"]
        for field in required_fields:
            if field not in schedule_data:
                logger.error(f"Missing required field: {field}. Received data: {schedule_data}")
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Parse datetime fields
        start_time = None
        if schedule_data.get("start_time"):
            try:
                start_time = datetime.fromisoformat(schedule_data["start_time"].replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_time format")
        
        # Create retry config
        retry_config = RetryConfig()
        if "retry_config" in schedule_data:
            retry_config = RetryConfig.from_dict(schedule_data["retry_config"])
        
        # Create scheduled experiment
        experiment = ScheduledExperiment(
            schedule_id="",  # Will be auto-generated
            experiment_name=schedule_data["experiment_name"],
            experiment_path=schedule_data["experiment_path"],
            schedule_type=schedule_data["schedule_type"],
            interval_hours=schedule_data.get("interval_hours"),
            start_time=start_time,
            estimated_duration=schedule_data.get("estimated_duration", 60),
            created_by=current_user.get("username", "unknown"),
            is_active=schedule_data.get("is_active", True),
            retry_config=retry_config,
            prerequisites=schedule_data.get("prerequisites", []),
            failed_execution_count=0,  # Initialize to 0 for new schedules
            created_at=None,  # Will be set in __post_init__
            updated_at=None   # Will be set in __post_init__
        )
        
        # Add to scheduler
        success = scheduler.add_schedule(experiment)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to create schedule")
        
        response = ApiResponse(
            success=True,
            message="Schedule created successfully",
            data={
                "schedule_id": experiment.schedule_id,
                "experiment_name": experiment.experiment_name,
                "next_execution": experiment.start_time.isoformat() if experiment.start_time else None
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/list")
async def list_schedules(
    active_only: bool = Query(True, description="Return only active schedules"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of scheduled experiments
    
    Requires: any authenticated user
    """
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        logger.info(f"Getting schedules: active_only={active_only}")
        
        if active_only:
            schedules = scheduler.get_active_schedules()
            if schedules:
                logger.info(f"Found {len(schedules)} schedules from scheduler cache")
            else:
                logger.info("Scheduler cache empty; loading schedules from database")
                schedules = db_mgr.get_active_schedules()
        else:
            schedules = db_mgr.get_active_schedules()
            logger.info(f"Found {len(schedules)} schedules from database (active_only=False)")
        
        schedule_list = []
        if schedules:
            for schedule in schedules:
                try:
                    schedule_dict = schedule.to_dict()
                    schedule_list.append(schedule_dict)
                    logger.debug(f"Added schedule: {schedule.experiment_name}")
                except Exception as e:
                    logger.error(f"Error converting schedule to dict: {e}")
                    logger.error(f"Schedule object: {schedule}")
        
        logger.info(f"Returning {len(schedule_list)} schedules in response")
        
        response = ApiResponse(
            success=True,
            message=f"Retrieved {len(schedule_list)} schedules",
            data=schedule_list,
            metadata={
                "count": len(schedule_list),
                "active_only": active_only
            }
        )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error listing schedules: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/upcoming")
async def get_upcoming_schedules(
    hours_ahead: int = Query(48, description="Hours to look ahead"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get scheduled experiments for the next N hours
    
    Requires: any authenticated user
    """
    try:
        if hours_ahead < 1 or hours_ahead > 168:  # Max 1 week
            raise HTTPException(status_code=400, detail="hours_ahead must be between 1 and 168")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        upcoming = scheduler.get_upcoming_jobs(hours_ahead)
        
        upcoming_list = []
        for schedule in upcoming:
            schedule_dict = schedule.to_dict()
            upcoming_list.append(schedule_dict)
        
        response = ApiResponse(
            success=True,
            message=f"Retrieved {len(upcoming_list)} upcoming schedules",
            data=upcoming_list,
            metadata={
                "hours_ahead": hours_ahead,
                "count": len(upcoming_list)
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting upcoming schedules: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/calendar")
async def get_calendar_data(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get calendar data for scheduled experiments
    
    Requires: any authenticated user
    """
    try:
        # Parse date range (keep timezone-naive for consistent comparison)
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '').replace('+00:00', ''))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        else:
            start_dt = datetime.now()
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '').replace('+00:00', ''))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")
        else:
            end_dt = start_dt + timedelta(hours=48)  # Default 48-hour view
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get schedules in date range
        all_schedules = scheduler.get_active_schedules()
        if not all_schedules:
            logger.info("Scheduler cache empty when building calendar; loading schedules from database")
            all_schedules = db_mgr.get_active_schedules()
        
        calendar_events = []
        for schedule in all_schedules:
            if (schedule.start_time and 
                schedule.start_time >= start_dt and 
                schedule.start_time <= end_dt):
                
                # Create calendar event
                event = CalendarEvent.from_scheduled_experiment(schedule)
                calendar_events.append(event.to_dict())
        
        response = ApiResponse(
            success=True,
            message=f"Retrieved calendar data for {len(calendar_events)} events",
            data=calendar_events,
            metadata={
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "event_count": len(calendar_events)
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting calendar data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific scheduled experiment
    
    Requires: any authenticated user
    """
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        schedule = scheduler.get_schedule(schedule_id)
        
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        response = ApiResponse(
            success=True,
            message="Schedule retrieved successfully",
            data=schedule.to_dict()
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    update_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Update a scheduled experiment
    
    Requires: admin or user role
    """
    try:
        # Check user permissions
        if current_user.get("role") not in ["admin", "user"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get existing schedule
        existing_schedule = scheduler.get_schedule(schedule_id)
        if not existing_schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Update fields
        if "experiment_name" in update_data:
            existing_schedule.experiment_name = update_data["experiment_name"]
        if "experiment_path" in update_data:
            existing_schedule.experiment_path = update_data["experiment_path"]
        if "schedule_type" in update_data:
            existing_schedule.schedule_type = update_data["schedule_type"]
        if "interval_hours" in update_data:
            existing_schedule.interval_hours = update_data["interval_hours"]
        if "start_time" in update_data:
            try:
                existing_schedule.start_time = datetime.fromisoformat(
                    update_data["start_time"].replace('Z', '+00:00')
                )
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_time format")
        if "estimated_duration" in update_data:
            existing_schedule.estimated_duration = update_data["estimated_duration"]
        if "is_active" in update_data:
            existing_schedule.is_active = update_data["is_active"]
        if "prerequisites" in update_data:
            existing_schedule.prerequisites = update_data["prerequisites"]
        if "retry_config" in update_data:
            existing_schedule.retry_config = RetryConfig.from_dict(update_data["retry_config"])
        
        existing_schedule.updated_at = datetime.now()
        
        # Update in scheduler
        success = scheduler.update_schedule(existing_schedule)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update schedule")
        
        response = ApiResponse(
            success=True,
            message="Schedule updated successfully",
            data=existing_schedule.to_dict()
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{schedule_id}/recovery/require")
async def require_schedule_recovery(
    schedule_id: str,
    payload: Dict[str, Any] = None,
    current_user: dict = Depends(get_current_user),
):
    # Mark a schedule as requiring manual recovery and halt automated dispatch.
    if current_user.get('role') not in ['admin', 'user']:
        raise HTTPException(status_code=403, detail='Insufficient permissions')

    scheduler, db_mgr, _, _ = get_services()
    note = (payload or {}).get('note') if payload else None
    actor = current_user.get('username') or current_user.get('user_id', 'system')

    updated = scheduler.require_manual_recovery(schedule_id, note, actor)
    if not updated:
        existing = db_mgr.get_schedule_by_id(schedule_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Schedule not found')
        raise HTTPException(status_code=500, detail='Failed to mark schedule for recovery')

    manual_state = scheduler.get_manual_recovery_state()

    response = ApiResponse(
        success=True,
        message='Schedule marked for manual recovery',
        data={
            'schedule': updated.to_dict(),
            'manual_recovery': manual_state.to_dict() if manual_state else None,
        },
    )
    return response.to_dict()


@router.post("/{schedule_id}/recovery/resolve")
async def resolve_schedule_recovery(
    schedule_id: str,
    payload: Dict[str, Any] = None,
    current_user: dict = Depends(get_current_user),
):
    # Clear manual recovery requirement and resume scheduling.
    if current_user.get('role') not in ['admin', 'user']:
        raise HTTPException(status_code=403, detail='Insufficient permissions')

    scheduler, db_mgr, _, _ = get_services()
    note = (payload or {}).get('note') if payload else None
    actor = current_user.get('username') or current_user.get('user_id', 'system')

    updated = scheduler.resolve_manual_recovery(schedule_id, note, actor)
    if not updated:
        existing = db_mgr.get_schedule_by_id(schedule_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Schedule not found')
        raise HTTPException(status_code=500, detail='Failed to resolve manual recovery state')

    manual_state = scheduler.get_manual_recovery_state()

    response = ApiResponse(
        success=True,
        message='Manual recovery cleared',
        data={
            'schedule': updated.to_dict(),
            'manual_recovery': manual_state.to_dict() if manual_state else None,
        },
    )
    return response.to_dict()


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a scheduled experiment
    
    Requires: admin role
    """
    try:
        # Check user permissions
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get schedule for logging
        schedule = scheduler.get_schedule(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Remove from scheduler
        success = scheduler.remove_schedule(schedule_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete schedule")
        
        response = ApiResponse(
            success=True,
            message=f"Schedule deleted: {schedule.experiment_name}",
            data={"schedule_id": schedule_id}
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status/scheduler")
async def get_scheduler_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current scheduler status
    
    Requires: any authenticated user
    """
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get scheduler status
        scheduler_status = scheduler.get_status()
        
        response = ApiResponse(
            success=True,
            message="Scheduler status retrieved successfully",
            data=scheduler_status
        )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status/queue")
async def get_queue_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current queue status and running jobs
    
    Requires: any authenticated user
    """
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get queue status
        queue_status = queue_mgr.get_queue_status()
        
        # Get Hamilton status
        hamilton_status = proc_mon.get_status()
        
        manual_state = scheduler.get_manual_recovery_state()

        response = ApiResponse(
            success=True,
            message="Queue status retrieved successfully",
            data={
                "queue": queue_status,
                "hamilton": {
                    "is_running": hamilton_status.is_running,
                    "process_count": hamilton_status.process_count,
                    "availability": hamilton_status.availability,
                    "last_check": hamilton_status.last_check.isoformat()
                },
                "manual_recovery": manual_state.to_dict() if manual_state else None,
            }
        )

        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/conflicts/check")
async def check_conflicts(
    experiments_data: List[Dict[str, Any]],
    current_user: dict = Depends(get_current_user)
):
    """
    Check for scheduling conflicts among experiments
    
    Requires: any authenticated user
    """
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Convert to ScheduledExperiment objects
        experiments = []
        for exp_data in experiments_data:
            # Parse start_time if provided
            start_time = None
            if exp_data.get("start_time"):
                try:
                    start_time = datetime.fromisoformat(exp_data["start_time"].replace('Z', '+00:00'))
                except ValueError:
                    continue  # Skip invalid entries
            
            experiment = ScheduledExperiment(
                schedule_id=exp_data.get("schedule_id", ""),
                experiment_name=exp_data["experiment_name"],
                experiment_path=exp_data.get("experiment_path", ""),
                schedule_type=exp_data.get("schedule_type", "once"),
                interval_hours=None,
                start_time=start_time,
                estimated_duration=exp_data.get("estimated_duration", 60),
                created_by="system",
                is_active=True,
                retry_config=None,
                prerequisites=[],
                failed_execution_count=0,
                created_at=None,
                updated_at=None
            )
            experiments.append(experiment)
        
        # Detect conflicts
        conflicts = queue_mgr.detect_scheduling_conflicts(experiments)
        
        response = ApiResponse(
            success=True,
            message=f"Conflict analysis completed for {len(experiments)} experiments",
            data=conflicts,
            metadata={
                "experiments_analyzed": len(experiments),
                "conflicts_found": len(conflicts)
            }
        )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error checking conflicts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/start-scheduler")
async def start_scheduler_service(
    current_user: dict = Depends(get_current_user)
):
    """
    Start the scheduler service
    
    Requires: admin role
    """
    try:
        # Check user permissions
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        success = scheduler.start()
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start scheduler service")
        
        response = ApiResponse(
            success=True,
            message="Scheduler service started successfully",
            data={"status": "running"}
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting scheduler service: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/stop-scheduler")
async def stop_scheduler_service(
    current_user: dict = Depends(get_current_user)
):
    """
    Stop the scheduler service
    
    Requires: admin role
    """
    try:
        # Check user permissions
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        scheduler.stop()
        
        response = ApiResponse(
            success=True,
            message="Scheduler service stopped successfully",
            data={"status": "stopped"}
        )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error stopping scheduler service: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/experiments/scan-defaults")
async def scan_default_experiment_paths(
    current_user: dict = Depends(get_current_user)
):
    """
    Scan default Hamilton paths for experiment files and import them
    
    Scans common Hamilton installation directories and imports any found
    .med files into the database automatically.
    
    Requires: admin or user role
    """
    try:
        # Check user permissions
        if current_user.get("role") not in ["admin", "user"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        discovery_service = get_experiment_discovery_service()
        
        # Perform scan of default paths
        discovered = discovery_service.scan_for_experiments()
        
        if discovered:
            # Import discovered experiments
            methods_data = [exp.to_dict() for exp in discovered]
            new_count, updated_count = discovery_service.db.import_experiment_methods(
                methods_data, 
                current_user.get("username", "system")
            )
            
            response = ApiResponse(
                success=True,
                message=f"Scanned default paths and imported {new_count} new, {updated_count} updated experiments",
                data={
                    "scanned_paths": discovery_service.DEFAULT_SEARCH_PATHS,
                    "total_found": len(discovered),
                    "new_methods": new_count,
                    "updated_methods": updated_count,
                    "experiments": methods_data
                }
            )
        else:
            response = ApiResponse(
                success=False,
                message="No experiment files found in default Hamilton paths",
                data={
                    "scanned_paths": discovery_service.DEFAULT_SEARCH_PATHS,
                    "total_found": 0
                }
            )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error scanning default paths: {e}")
        raise HTTPException(status_code=500, detail="Failed to scan for experiments")


@router.get("/experiments/available")
async def get_available_experiments(
    rescan: bool = Query(False, description="Force rescan of experiment files"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of available Hamilton experiment files
    
    Returns experiment files discovered on the system with metadata.
    Use rescan=true to force a fresh scan of the file system.
    
    Requires: any authenticated user
    """
    try:
        discovery_service = get_experiment_discovery_service()
        
        # Get experiments (use cache unless rescan requested)
        experiments = discovery_service.get_available_experiments(use_cache=not rescan)
        
        # Group by category for better organization
        categorized = {}
        for exp in experiments:
            category = exp.get("category", "Custom")
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(exp)
        
        response = ApiResponse(
            success=True,
            message=f"Found {len(experiments)} available experiments",
            data={
                "experiments": experiments,
                "categorized": categorized,
                "last_scan": discovery_service._last_scan.isoformat() if discovery_service._last_scan else None
            }
        )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error getting available experiments: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve experiments")


@router.get("/experiments/evo-yeast")
async def get_evo_yeast_experiments(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of experiments to return"),
    current_user: dict = Depends(get_current_user)
):
    """Return EvoYeast experiments with their ScheduledToRun flag states."""
    try:
        _, db_mgr, _, _ = get_services()
        experiments = db_mgr.get_evo_yeast_experiments(limit)

        response = ApiResponse(
            success=True,
            message=f"Retrieved {len(experiments)} EvoYeast experiments",
            data={
                "experiments": experiments,
                "limit": limit
            }
        )

        return response.to_dict()

    except Exception as e:
        logger.error(f"Error getting EvoYeast experiments: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve EvoYeast experiments")


@router.get("/experiments/prerequisites")
async def get_available_prerequisites(
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of available prerequisite database flags
    
    Returns the available database flags that can be set as prerequisites
    before running scheduled experiments.
    
    Requires: any authenticated user
    """
    try:
        discovery_service = get_experiment_discovery_service()
        
        prerequisites = discovery_service.get_available_prerequisites()
        
        response = ApiResponse(
            success=True,
            message="Retrieved available prerequisites",
            data={
                "prerequisites": prerequisites,
                "count": len(prerequisites)
            }
        )
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error getting prerequisites: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve prerequisites")


@router.post("/experiments/import-files")
async def import_experiment_files(
    files_data: Union[List[Dict[str, Any]], Dict[str, Any]],
    current_user: dict = Depends(get_current_user)
):
    """
    Import experiment files from browser file selection
    
    Takes file metadata from browser folder selection and imports
    the experiments into the database for easy scheduling access.
    
    Requires: admin or user role
    """
    try:
        # Check user permissions
        if current_user.get("role") not in ["admin", "user"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        if isinstance(files_data, list):
            files_metadata = files_data
        else:
            files_metadata = files_data.get("files", [])
        
        if not files_metadata:
            raise HTTPException(status_code=400, detail="No file metadata provided")
        
        discovery_service = get_experiment_discovery_service()
        
        # Convert browser file metadata to our format
        methods_to_import = []
        for file_meta in files_metadata:
            method_data = {
                "name": file_meta.get("name", ""),
                "path": file_meta.get("path", ""),
                "category": discovery_service._determine_category(file_meta.get("name", "")),
                "description": f"Imported via browser from {file_meta.get('sourceFolder', 'browser selection')}",
                "file_size": file_meta.get("size", 0),
                "last_modified": file_meta.get("lastModified"),
                "source_folder": file_meta.get("sourceFolder", "Browser Selection"),
                "metadata": {
                    "import_method": "browser_selection",
                    "relative_path": file_meta.get("path", ""),
                    "import_timestamp": datetime.now().isoformat()
                }
            }
            methods_to_import.append(method_data)
        
        # Import to database
        new_count, updated_count = discovery_service.db.import_experiment_methods(
            methods_to_import,
            current_user.get("username", "unknown")
        )
        
        response = ApiResponse(
            success=True,
            message=f"Imported {new_count} new and {updated_count} updated methods from {len(files_metadata)} files",
            data={
                "new_methods": new_count,
                "updated_methods": updated_count,
                "failed_methods": len(files_metadata) - new_count - updated_count,
                "total_files": len(files_metadata),
                "errors": []  # Could add validation errors here
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing experiment files: {e}")
        raise HTTPException(status_code=500, detail="Failed to import experiments")


@router.post("/experiments/import-folder")
async def import_experiment_folder(
    import_data: Dict[str, str],
    current_user: dict = Depends(get_current_user)
):
    """
    Import all .med experiment files from a specified folder
    
    Scans the folder recursively for .med files and imports them into the database
    for easy selection in scheduling forms.
    
    Requires: admin or user role
    """
    try:
        # Check user permissions
        if current_user.get("role") not in ["admin", "user"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        folder_path = import_data.get("folder_path", "")
        
        if not folder_path:
            raise HTTPException(status_code=400, detail="Folder path is required")
        
        discovery_service = get_experiment_discovery_service()
        
        # Import methods from the folder
        results = discovery_service.import_methods_from_folder(
            folder_path=folder_path,
            imported_by=current_user.get("username", "unknown")
        )
        
        if not results["success"] and results["errors"]:
            # If completely failed, return error
            raise HTTPException(status_code=400, detail=results["errors"][0])
        
        response = ApiResponse(
            success=results["success"],
            message=f"Imported {results['new_methods']} new and {results['updated_methods']} updated methods from {results['total_found']} files",
            data=results
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing experiment folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to import experiments")


@router.post("/experiments/validate-path")
async def validate_experiment_path(
    path_data: Dict[str, str],
    current_user: dict = Depends(get_current_user)
):
    """
    Validate an experiment file path
    
    Checks if the provided path exists and is a valid .med file.
    
    Requires: any authenticated user
    """
    try:
        path = path_data.get("path", "")
        
        if not path:
            raise HTTPException(status_code=400, detail="Path is required")
        
        discovery_service = get_experiment_discovery_service()
        
        is_valid = discovery_service.validate_experiment_path(path)
        
        response = ApiResponse(
            success=is_valid,
            message="Path is valid" if is_valid else "Path is invalid or inaccessible",
            data={
                "path": path,
                "valid": is_valid
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating path: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate path")


@router.get("/executions/history")
async def get_execution_history(
    schedule_id: Optional[str] = Query(None, description="Schedule ID to filter by"),
    limit: int = Query(50, description="Maximum number of results"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get execution history for scheduled experiments
    
    Provides Windows Task Scheduler-like execution history with:
    - Last run time and status
    - Success/failure counts  
    - Average duration
    - Error messages and retry counts
    
    Requires: any authenticated user
    """
    try:
        if limit < 1 or limit > 200:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 200")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get execution history from SQLite database
        sqlite_db = db_mgr.sqlite_db
        executions = sqlite_db.get_execution_history(schedule_id, limit)
        
        response = ApiResponse(
            success=True,
            message=f"Retrieved {len(executions)} execution records",
            data=executions,
            metadata={
                "schedule_id": schedule_id,
                "limit": limit,
                "count": len(executions)
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/executions/summary/{schedule_id}")
async def get_schedule_execution_summary(
    schedule_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get execution summary for a specific schedule (like Windows Task Scheduler)
    
    Returns:
    - Total runs, successful runs, failed runs
    - Last run time and status
    - Next scheduled run time
    - Success rate and average duration
    - Last execution details
    
    Requires: any authenticated user
    """
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get execution summary from SQLite database
        sqlite_db = db_mgr.sqlite_db
        summary = sqlite_db.get_schedule_execution_summary(schedule_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        response = ApiResponse(
            success=True,
            message="Retrieved execution summary",
            data=summary
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/executions/recent")
async def get_recent_executions(
    hours: int = Query(24, description="Hours to look back"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent executions within the specified time period
    
    Useful for monitoring dashboard and recent activity display
    
    Requires: any authenticated user
    """
    try:
        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")
        
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        
        # Get recent executions from SQLite database
        sqlite_db = db_mgr.sqlite_db
        executions = sqlite_db.get_recent_executions(hours)
        
        response = ApiResponse(
            success=True,
            message=f"Retrieved {len(executions)} recent executions",
            data=executions,
            metadata={
                "hours": hours,
                "count": len(executions)
            }
        )
        
        return response.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recent executions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
