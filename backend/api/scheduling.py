from typing import Dict, Any, List, Optional, Union, Tuple
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Header

from backend.services.auth import get_current_user
from backend.services.scheduling import (
    get_scheduler_engine,
    get_scheduling_database_manager,
    get_job_queue_manager,
    get_hamilton_process_monitor,
)
from backend.services.notifications import EmailNotificationService
from backend.services.scheduling.experiment_discovery import get_experiment_discovery_service
from backend.services.scheduling.experiment_executor import resolve_experiment_path
from backend.models import (
    ScheduledExperiment,
    JobExecution,
    RetryConfig,
    CalendarEvent,
    ApiResponse,
    NotificationContact,
    NotificationSettings,
)
from backend.api.dependencies import ConnectionContext, require_local_access
from backend.utils.audit import log_action
from backend.utils.secret_cipher import encrypt_secret, SecretCipherError

try:
    from backend.utils.datetime import (
        parse_iso_datetime_to_local,
    )
except ImportError:  # pragma: no cover - fallback
    from utils.datetime import (  # type: ignore
        parse_iso_datetime_to_local,
    )

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])

# Service instances (lazy-loaded)
scheduler_engine = None
db_manager = None
queue_manager = None
process_monitor = None

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEDULE_INTERVAL_ALIASES: Dict[str, float] = {
    "hourly": 1.0,
    "daily": 24.0,
    "weekly": 24.0 * 7,
}
SUPPORTED_SCHEDULE_TYPES = {"once", "interval", "cron"} | set(SCHEDULE_INTERVAL_ALIASES.keys())


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


def _normalize_contact_ids(contact_ids: Optional[Any], db_mgr) -> List[str]:
    """Validate and normalize notification contact IDs."""
    if contact_ids is None:
        return []
    if not isinstance(contact_ids, list):
        raise HTTPException(status_code=400, detail="notification_contacts must be a list of contact IDs")
    cleaned: List[str] = []
    seen = set()
    for value in contact_ids:
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail="notification_contacts must contain contact ID strings")
        contact_id = value.strip()
        if not contact_id or contact_id in seen:
            continue
        cleaned.append(contact_id)
        seen.add(contact_id)
    if not cleaned:
        return []

    available_ids = {
        contact.contact_id for contact in db_mgr.get_notification_contacts(include_inactive=True)
    }
    missing = [contact_id for contact_id in cleaned if contact_id not in available_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown notification contact(s): {', '.join(missing)}"
        )
    return cleaned


def _validate_email_address(value: Any) -> str:
    """Simple email validation."""
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="Email address must be a string")
    email = value.strip()
    if not EMAIL_REGEX.fullmatch(email):
        raise HTTPException(status_code=400, detail="Invalid email address format")
    return email


def _timestamps_match(expected: Optional[str], actual: Optional[datetime]) -> bool:
    """Return True when the expected timestamp matches the actual value."""
    if not expected or actual is None:
        return True
    if not isinstance(expected, str):
        return False
    candidate = expected.strip()
    if not candidate:
        return True
    try:
        expected_dt = parse_iso_datetime_to_local(candidate)
    except Exception:  # pragma: no cover - defensive
        return False

    if expected_dt == actual:
        return True
    delta_seconds = abs((expected_dt - actual).total_seconds())
    return delta_seconds <= 1


def _normalize_schedule_request(
    schedule_type: Any,
    interval_hours: Optional[Any],
) -> Tuple[str, Optional[float]]:
    """Validate and normalize schedule type + interval combination."""
    if not isinstance(schedule_type, str):
        raise HTTPException(status_code=400, detail="schedule_type must be a string")
    normalized_type = schedule_type.strip().lower()
    if normalized_type not in SUPPORTED_SCHEDULE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported schedule_type '{schedule_type}'",
        )

    if normalized_type == "interval":
        if interval_hours is None:
            raise HTTPException(
                status_code=400,
                detail="interval_hours is required for interval schedules",
            )
        try:
            hours_value = float(interval_hours)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="interval_hours must be a numeric value",
            )
        if hours_value <= 0:
            raise HTTPException(
                status_code=400,
                detail="interval_hours must be greater than zero",
            )
        return normalized_type, hours_value

    alias_hours = SCHEDULE_INTERVAL_ALIASES.get(normalized_type)
    if alias_hours is not None:
        return normalized_type, alias_hours

    # For types like "once" or "cron" we do not enforce interval hours.
    return normalized_type, None


def _load_current_schedule(schedule_id: str, db_mgr, expected_timestamp: Optional[str]) -> ScheduledExperiment:
    """Fetch the authoritative schedule record and enforce optimistic concurrency."""
    schedule = db_mgr.get_schedule_by_id(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not _timestamps_match(expected_timestamp, schedule.updated_at):
        logger.warning(
            "Schedule concurrency mismatch | schedule_id=%s | expected=%s | actual=%s",
            schedule_id,
            expected_timestamp,
            schedule.updated_at.isoformat() if schedule.updated_at else None,
        )
        raise HTTPException(
            status_code=409,
            detail="Schedule was modified by another user. Refresh and try again.",
        )
    return schedule


@router.get("/notifications/settings")
async def get_notification_settings_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Return the global SMTP settings (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage notification settings")

    scheduler, db_mgr, _, _ = get_services()
    settings = db_mgr.get_notification_settings()
    data = settings.to_public_dict()

    return ApiResponse(
        success=True,
        message="Notification settings retrieved",
        data=data,
    ).to_dict()


@router.put("/notifications/settings")
async def update_notification_settings_endpoint(
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Update the global SMTP configuration (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage notification settings")
    actor = current_user.get("username", "unknown")

    host_value = payload.get("host")
    if not isinstance(host_value, str) or not host_value.strip():
        raise HTTPException(status_code=400, detail="host is required")
    host = host_value.strip()

    port_value = payload.get("port", 587)
    try:
        port = int(port_value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="port must be an integer")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="port must be between 1 and 65535")

    username_value = payload.get("username")
    if username_value is not None and not isinstance(username_value, str):
        raise HTTPException(status_code=400, detail="username must be a string if provided")
    username = username_value.strip() if isinstance(username_value, str) and username_value.strip() else None

    sender_value = payload.get("sender")
    sender = _validate_email_address(sender_value)

    use_tls = bool(payload.get("use_tls", True))
    use_ssl = bool(payload.get("use_ssl", False))
    if use_ssl and use_tls:
        # If SSL is requested, disable STARTTLS to avoid conflicting settings.
        use_tls = False

    manual_recipients_input = payload.get("manual_recovery_recipients", [])
    manual_recipients: List[str] = []
    if isinstance(manual_recipients_input, str):
        for value in manual_recipients_input.split(","):
            if value.strip():
                manual_recipients.append(_validate_email_address(value))
    elif isinstance(manual_recipients_input, list):
        for value in manual_recipients_input:
            if not isinstance(value, str):
                raise HTTPException(status_code=400, detail="manual_recovery_recipients must contain strings")
            trimmed = value.strip()
            if trimmed:
                manual_recipients.append(_validate_email_address(trimmed))
    elif manual_recipients_input not in (None, []):
        raise HTTPException(status_code=400, detail="manual_recovery_recipients must be a string or list of strings")
    update_password = "password" in payload
    encrypted_password: Optional[str] = None
    if update_password:
        raw_password = payload.get("password")
        if raw_password is None or raw_password == "":
            encrypted_password = None  # Explicit clear
        else:
            if not isinstance(raw_password, str):
                raise HTTPException(status_code=400, detail="password must be a string")
            try:
                encrypted_password = encrypt_secret(raw_password)
            except SecretCipherError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
    manual_recipients = list(dict.fromkeys(manual_recipients))

    settings = NotificationSettings(
        host=host,
        port=port,
        username=username,
        sender=sender,
        use_tls=use_tls,
        use_ssl=use_ssl,
        updated_by=current_user.get("username"),
        manual_recovery_recipients=manual_recipients or None,
    )

    scheduler, db_mgr, _, _ = get_services()
    updated = db_mgr.update_notification_settings(
        settings,
        password_encrypted=encrypted_password,
        update_password=update_password,
    )
    data = updated.to_public_dict()

    if scheduler:
        try:
            scheduler.refresh_notification_service()
        except Exception as exc:
            logger.warning("Failed to refresh notification service after SMTP update: %s", exc)

    log_action(
        actor=actor,
        action="update_notification_settings",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
    )

    return ApiResponse(
        success=True,
        message="Notification settings updated",
        data=data,
    ).to_dict()


@router.post("/notifications/settings/test")
async def test_notification_settings_endpoint(
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Send a test email using the stored SMTP settings (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage notification settings")

    recipient_value = payload.get("recipient")
    recipient = _validate_email_address(recipient_value)

    email_service = EmailNotificationService()
    if not email_service.config.is_enabled:
        detail = email_service.last_error or "SMTP configuration is incomplete"
        raise HTTPException(status_code=400, detail=detail)

    subject = "RobotControl SMTP test message"
    body_lines = [
        "This is a test email sent from the RobotControl scheduling service.",
        "",
        f"Recipient: {recipient}",
        f"Requested by: {current_user.get('username', 'unknown')}",
        f"Timestamp: {datetime.utcnow().isoformat()}Z",
        "",
        "If you received this message, the configured SMTP settings are working.",
    ]
    body = "\n".join(body_lines)

    if not email_service.send(subject, body, to=[recipient]):
        detail = email_service.last_error or "Failed to deliver test email; see backend logs for details."
        log_action(
            actor=current_user.get("username", "unknown"),
            action="test_notification_settings",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"recipient": recipient, "error": detail},
        )
        raise HTTPException(status_code=502, detail=detail)

    log_action(
        actor=current_user.get("username", "unknown"),
        action="test_notification_settings",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={"recipient": recipient},
    )

    return ApiResponse(
        success=True,
        message=f"Test email sent to {recipient}",
        data={"recipient": recipient},
    ).to_dict()


@router.get("/contacts")
async def list_notification_contacts(
    include_inactive: bool = Query(False, description="Include inactive contacts"),
    current_user: dict = Depends(get_current_user)
):
    """List notification contacts for scheduling."""
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()
        contacts = db_mgr.get_notification_contacts(include_inactive=include_inactive)
        response = ApiResponse(
            success=True,
            message="Notification contacts retrieved",
            data=[contact.to_dict() for contact in contacts]
        )
        return response.to_dict()
    except Exception as exc:
        logger.error(f"Error listing notification contacts: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load contacts")


@router.post("/contacts")
async def create_notification_contact_endpoint(
    contact_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Create a new notification contact (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage contacts")

    display_name = contact_data.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise HTTPException(status_code=400, detail="display_name is required")
    email_address = _validate_email_address(contact_data.get("email_address"))
    is_active = bool(contact_data.get("is_active", True))

    actor = current_user.get("username", "unknown")

    scheduler, db_mgr, _, _ = get_services()

    contact = NotificationContact(
        contact_id="",
        display_name=display_name.strip(),
        email_address=email_address,
        is_active=is_active,
    )
    created = db_mgr.create_notification_contact(contact)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create contact")
    
    # Keep scheduler cache aligned with persistent state
    scheduler.refresh_notification_contacts(include_inactive=True)

    logger.info("Notification contact created: %s", created.contact_id)
    log_action(
        actor=actor,
        action="create_notification_contact",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={"contact_id": created.contact_id},
    )
    return ApiResponse(
        success=True,
        message="Notification contact created",
        data=created.to_dict()
    ).to_dict()


@router.put("/contacts/{contact_id}")
async def update_notification_contact_endpoint(
    contact_id: str,
    contact_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Update an existing notification contact (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage contacts")

    display_name = contact_data.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise HTTPException(status_code=400, detail="display_name is required")
    email_address = _validate_email_address(contact_data.get("email_address"))
    is_active = bool(contact_data.get("is_active", True))

    actor = current_user.get("username", "unknown")

    scheduler, db_mgr, _, _ = get_services()
    contact = NotificationContact(
        contact_id=contact_id,
        display_name=display_name.strip(),
        email_address=email_address,
        is_active=is_active,
    )
    updated = db_mgr.update_notification_contact(contact)
    if not updated:
        log_action(
            actor=actor,
            action="update_notification_contact",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"contact_id": contact_id, "error": "not_found"},
        )
        raise HTTPException(status_code=404, detail="Contact not found")
    
    scheduler.refresh_notification_contacts(include_inactive=True)

    logger.info("Notification contact updated: %s", contact_id)
    log_action(
        actor=actor,
        action="update_notification_contact",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={"contact_id": contact_id},
    )
    return ApiResponse(
        success=True,
        message="Notification contact updated",
        data=contact.to_dict()
    ).to_dict()


@router.delete("/contacts/{contact_id}")
async def delete_notification_contact_endpoint(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Delete a notification contact (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage contacts")

    actor = current_user.get("username", "unknown")

    scheduler, db_mgr, _, _ = get_services()
    deleted = db_mgr.delete_notification_contact(contact_id)
    if not deleted:
        log_action(
            actor=actor,
            action="delete_notification_contact",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"contact_id": contact_id, "error": "not_found"},
        )
        raise HTTPException(status_code=404, detail="Contact not found")
    
    scheduler.refresh_notification_contacts(include_inactive=True)

    logger.info("Notification contact deleted: %s", contact_id)
    log_action(
        actor=actor,
        action="delete_notification_contact",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={"contact_id": contact_id},
    )
    return ApiResponse(
        success=True,
        message="Notification contact deleted",
        data={"contact_id": contact_id}
    ).to_dict()


@router.get("/notifications/logs")
async def list_notification_logs(
    limit: int = Query(50, description="Maximum number of notification entries to return"),
    schedule_id: Optional[str] = Query(None, description="Filter by schedule ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    current_user: dict = Depends(get_current_user)
):
    """Return recent notification delivery attempts (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to review notification logs")

    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")

    try:
        scheduler, db_mgr, _, _ = get_services()
        logs = db_mgr.get_notification_logs(
            limit,
            schedule_id=schedule_id,
            event_type=event_type,
            status=status_filter,
        )
        return ApiResponse(
            success=True,
            message=f"Retrieved {len(logs)} notification log entries",
            data=[log.to_dict() for log in logs],
            metadata={
                "limit": limit,
                "schedule_id": schedule_id,
                "event_type": event_type,
                "status": status_filter,
            },
        ).to_dict()
    except Exception as exc:
        logger.error("Error retrieving notification logs: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load notification logs")


@router.post("/create")
async def create_schedule(
    schedule_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """
    Create a new scheduled experiment
    
    Requires: admin or user role
    """
    actor = current_user.get("username", "unknown")
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
        
        notification_contact_ids = _normalize_contact_ids(
            schedule_data.get("notification_contacts"),
            db_mgr
        )
        
        # Parse datetime fields (preserve local wall-clock time)
        start_time = None
        if schedule_data.get("start_time"):
            try:
                start_time = parse_iso_datetime_to_local(schedule_data["start_time"])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_time format")
        
        # Create retry config
        retry_config = RetryConfig()
        if "retry_config" in schedule_data:
            retry_config = RetryConfig.from_dict(schedule_data["retry_config"])
        
        normalized_type, normalized_interval_hours = _normalize_schedule_request(
            schedule_data["schedule_type"],
            schedule_data.get("interval_hours"),
        )
        
        # Create scheduled experiment
        experiment = ScheduledExperiment(
            schedule_id="",  # Will be auto-generated
            experiment_name=schedule_data["experiment_name"],
            experiment_path=str(resolve_experiment_path(schedule_data["experiment_path"])),
            schedule_type=normalized_type,
            interval_hours=normalized_interval_hours,
            start_time=start_time,
            estimated_duration=schedule_data.get("estimated_duration", 60),
            created_by=current_user.get("username", "unknown"),
            is_active=schedule_data.get("is_active", True),
            retry_config=retry_config,
            prerequisites=schedule_data.get("prerequisites", []),
            notification_contacts=notification_contact_ids,
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
        
        log_action(
            actor=actor,
            action="create_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=True,
            details={"schedule_id": experiment.schedule_id, "experiment_name": experiment.experiment_name},
        )
        return response.to_dict()
        
    except HTTPException:
        log_action(
            actor=actor,
            action="create_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"error": "http_exception", "data": schedule_data},
        )
        raise
    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        log_action(
            actor=actor,
            action="create_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"error": str(e), "data": schedule_data},
        )
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
        # Parse date range (ensure values reflect local wall-clock time)
        if start_date:
            try:
                start_dt = parse_iso_datetime_to_local(start_date) or datetime.now()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        else:
            start_dt = datetime.now()
        
        if end_date:
            try:
                end_dt = parse_iso_datetime_to_local(end_date) or (start_dt + timedelta(hours=48))
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
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    if_unmodified_since: Optional[str] = Header(None, alias="If-Unmodified-Since"),
):
    """
    Update a scheduled experiment
    
    Requires: admin or user role
    """
    actor = current_user.get("username", "unknown")
    try:
        if current_user.get("role") not in ["admin", "user"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        scheduler, db_mgr, _, _ = get_services()

        expected_token = update_data.pop("expected_updated_at", None) or if_unmodified_since
        base_schedule = _load_current_schedule(schedule_id, db_mgr, expected_token)

        # Work on a fresh copy so we don't mutate cached instances prematurely
        updated_schedule = ScheduledExperiment.from_dict(base_schedule.to_dict())

        if "experiment_name" in update_data:
            updated_schedule.experiment_name = update_data["experiment_name"]
        if "experiment_path" in update_data:
            updated_schedule.experiment_path = str(resolve_experiment_path(update_data["experiment_path"]))
        if "schedule_type" in update_data:
            updated_schedule.schedule_type = update_data["schedule_type"]
        if "interval_hours" in update_data:
            updated_schedule.interval_hours = update_data["interval_hours"]
        if "start_time" in update_data:
            try:
                updated_schedule.start_time = parse_iso_datetime_to_local(update_data["start_time"])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_time format")
        if "estimated_duration" in update_data:
            updated_schedule.estimated_duration = update_data["estimated_duration"]
        if "is_active" in update_data:
            updated_schedule.is_active = update_data["is_active"]
        if "prerequisites" in update_data:
            updated_schedule.prerequisites = update_data["prerequisites"] or []
        if "retry_config" in update_data:
            retry_payload = update_data["retry_config"]
            updated_schedule.retry_config = (
                RetryConfig.from_dict(retry_payload) if isinstance(retry_payload, dict) else None
            )
        if "notification_contacts" in update_data:
            updated_schedule.notification_contacts = _normalize_contact_ids(
                update_data["notification_contacts"],
                db_mgr
            )

        normalized_type, normalized_interval_hours = _normalize_schedule_request(
            updated_schedule.schedule_type,
            updated_schedule.interval_hours,
        )
        updated_schedule.schedule_type = normalized_type
        updated_schedule.interval_hours = normalized_interval_hours

        updated_schedule.updated_at = datetime.utcnow()

        success = scheduler.update_schedule(updated_schedule)
        if not success:
            # Scheduler offline or cache missing; persist directly then clear cache.
            if not db_mgr.update_scheduled_experiment(updated_schedule):
                raise HTTPException(status_code=400, detail="Failed to update schedule")
            scheduler.invalidate_schedule(schedule_id)

        refreshed = db_mgr.get_schedule_by_id(schedule_id) or updated_schedule

        response = ApiResponse(
            success=True,
            message="Schedule updated successfully",
            data=refreshed.to_dict()
        )
        
        log_action(
            actor=actor,
            action="update_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=True,
            details={"schedule_id": schedule_id},
        )
        return response.to_dict()
        
    except HTTPException:
        log_action(
            actor=actor,
            action="update_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"schedule_id": schedule_id, "error": "http_exception"},
        )
        raise
    except Exception as e:
        logger.error(f"Error updating schedule {schedule_id}: {e}")
        log_action(
            actor=actor,
            action="update_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"schedule_id": schedule_id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{schedule_id}/recovery/require")
async def require_schedule_recovery(
    schedule_id: str,
    payload: Dict[str, Any] = None,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    if_unmodified_since: Optional[str] = Header(None, alias="If-Unmodified-Since"),
):
    # Mark a schedule as requiring manual recovery and halt automated dispatch.
    if current_user.get('role') not in ['admin', 'user']:
        raise HTTPException(status_code=403, detail='Insufficient permissions')

    scheduler, db_mgr, _, _ = get_services()
    note = (payload or {}).get('note') if payload else None
    expected_token = (payload or {}).get('expected_updated_at') or if_unmodified_since
    actor = current_user.get('username') or current_user.get('user_id', 'system')

    _load_current_schedule(schedule_id, db_mgr, expected_token)
    updated = scheduler.require_manual_recovery(schedule_id, note, actor)
    if not updated:
        existing = db_mgr.get_schedule_by_id(schedule_id)
        if not existing:
            log_action(
                actor=actor,
                action="require_schedule_recovery",
                scope="scheduling",
                client_ip=connection.client_ip,
                success=False,
                details={"schedule_id": schedule_id, "error": "not_found"},
            )
            raise HTTPException(status_code=404, detail='Schedule not found')
        log_action(
            actor=actor,
            action="require_schedule_recovery",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"schedule_id": schedule_id, "error": "transition_failed"},
        )
        raise HTTPException(status_code=500, detail='Failed to mark schedule for recovery')

    manual_state = scheduler.get_manual_recovery_state()

    log_action(
        actor=actor,
        action="require_schedule_recovery",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={"schedule_id": schedule_id},
    )

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
    connection: ConnectionContext = Depends(require_local_access),
    if_unmodified_since: Optional[str] = Header(None, alias="If-Unmodified-Since"),
):
    # Clear manual recovery requirement and resume scheduling.
    if current_user.get('role') not in ['admin', 'user']:
        raise HTTPException(status_code=403, detail='Insufficient permissions')

    scheduler, db_mgr, _, _ = get_services()
    note = (payload or {}).get('note') if payload else None
    expected_token = (payload or {}).get('expected_updated_at') or if_unmodified_since
    actor = current_user.get('username') or current_user.get('user_id', 'system')

    _load_current_schedule(schedule_id, db_mgr, expected_token)
    updated = scheduler.resolve_manual_recovery(schedule_id, note, actor)
    if not updated:
        existing = db_mgr.get_schedule_by_id(schedule_id)
        if not existing:
            log_action(
                actor=actor,
                action="resolve_schedule_recovery",
                scope="scheduling",
                client_ip=connection.client_ip,
                success=False,
                details={"schedule_id": schedule_id, "error": "not_found"},
            )
            raise HTTPException(status_code=404, detail='Schedule not found')
        log_action(
            actor=actor,
            action="resolve_schedule_recovery",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"schedule_id": schedule_id, "error": "transition_failed"},
        )
        raise HTTPException(status_code=500, detail='Failed to resolve manual recovery state')

    manual_state = scheduler.get_manual_recovery_state()

    log_action(
        actor=actor,
        action="resolve_schedule_recovery",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={"schedule_id": schedule_id},
    )

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
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    if_unmodified_since: Optional[str] = Header(None, alias="If-Unmodified-Since"),
):
    """
    Delete a scheduled experiment
    
    Requires: admin role
    """
    actor = current_user.get("username", "unknown")
    try:
        scheduler, db_mgr, queue_mgr, proc_mon = get_services()

        existing_schedule = db_mgr.get_schedule_by_id(schedule_id)
        if not existing_schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        is_admin = current_user.get("role") == "admin"
        is_local_owner = (
            connection.is_local
            and existing_schedule.created_by
            and existing_schedule.created_by == current_user.get("username")
        )
        if not (is_admin or is_local_owner):
            raise HTTPException(status_code=403, detail="Admin role required")

        # Check concurrency against authoritative record
        expected_token = if_unmodified_since
        authoritative_schedule = _load_current_schedule(schedule_id, db_mgr, expected_token)

        scheduler_schedule = scheduler.get_schedule(schedule_id)
        schedule_from_engine = scheduler_schedule is not None
        schedule = scheduler_schedule or authoritative_schedule
        
        fallback_used = False
        success = False

        if schedule_from_engine:
            success = scheduler.remove_schedule(schedule_id)

        if not success:
            # Either the scheduler is not running or removal failed; fall back to direct DB removal
            fallback_deleted = db_mgr.delete_scheduled_experiment(schedule_id)
            if not fallback_deleted:
                raise HTTPException(status_code=400, detail="Failed to delete schedule")
            fallback_used = True
            scheduler.invalidate_schedule(schedule_id)
            success = True

        response = ApiResponse(
            success=True,
            message=f"Schedule deleted: {authoritative_schedule.experiment_name}",
            data={
                "schedule_id": schedule_id,
                "deleted_via": "database_fallback" if fallback_used else "scheduler",
            }
        )
        
        log_action(
            actor=actor,
            action="delete_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=True,
            details={
                "schedule_id": schedule_id,
                "deleted_via": "database_fallback" if fallback_used else "scheduler",
            },
        )
        return response.to_dict()
        
    except HTTPException:
        log_action(
            actor=actor,
            action="delete_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"schedule_id": schedule_id, "error": "http_exception"},
        )
        raise
    except Exception as e:
        logger.error(f"Error deleting schedule {schedule_id}: {e}")
        log_action(
            actor=actor,
            action="delete_schedule",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={"schedule_id": schedule_id, "error": str(e)},
        )
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
                    start_time = parse_iso_datetime_to_local(exp_data["start_time"])
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
        scheduler, db_mgr, _, _ = get_services()
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

