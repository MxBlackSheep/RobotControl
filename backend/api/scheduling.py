from typing import Dict, Any, List, Optional, Tuple
import logging
import sqlite3
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, StrictStr, StrictBool, Field

from backend.services.auth import get_current_user
from backend.services.scheduling import (
    get_scheduler_engine,
    get_scheduling_database_manager,
    get_hamilton_process_monitor,
)
from backend.services.notifications import EmailNotificationService
from backend.services.notification_delivery import send_recorded
from backend.services.scheduling.experiment_discovery import get_experiment_discovery_service
from backend.services.scheduling.experiment_executor import resolve_experiment_path
from backend.services.scheduling.schedule_check import check_schedule
from backend.services.scheduling.schedule_review import ScheduleReview
from backend.services.scheduling.notification_check import check_contact, check_email_address, check_email_settings
from backend.models import ScheduledExperiment, CalendarEvent, ApiResponse, NotificationContact
from backend.api.dependencies import ConnectionContext, require_local_access
from backend.utils.audit import log_action
from backend.services.database_packages import PackageError
from backend.utils.secret_cipher import encrypt_secret, SecretCipherError

from backend.utils.datetime import (
    parse_iso_datetime_to_local,
    utc_now_as_local_naive,
)

logger = logging.getLogger(__name__)

class SafetyRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except SafetyConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except (StorageUnavailable, sqlite3.Error) as exc:
                logger.exception('Scheduling storage unavailable')
                raise HTTPException(status_code=503, detail='Scheduler safety state unavailable. Review SQLite storage health and retry.') from exc
            except (HTTPException, RequestValidationError):
                raise
            except Exception as exc:
                logger.exception('Scheduling request failed')
                raise HTTPException(status_code=500, detail='Internal server error') from exc
        return handler


router = APIRouter(prefix="/api/scheduling", tags=["scheduling"], route_class=SafetyRoute)



def _runner_fields(data):
    runner = data.get('runner', 'venus')
    if runner == 'venus':
        return dict(runner=runner, protocol_id=None, parameters={}, protocol_revision=None,
                    experiment_path=data['experiment_path'])
    from backend.api.pyhsl import validate_request
    validated = validate_request(data)
    return dict(runner=runner, protocol_id=data['protocol_id'], parameters=data.get('parameters', {}),
                protocol_revision=validated['protocol']['revision'], experiment_path='pyhsl:' + data['protocol_id'])


PREREQUISITES_RETIRED = ("Preparation tokens are retired. A local administrator attaches a database step "
                         "(for example Select EvoYeast experiment) under Before this run.")


def get_services():
    """Return the scheduler service dependencies."""
    scheduler = get_scheduler_engine()
    db_mgr = get_scheduling_database_manager()
    proc_monitor = get_hamilton_process_monitor()
    return scheduler, db_mgr, proc_monitor


def _schedule_payload(schedule: ScheduledExperiment) -> Dict[str, Any]:
    """to_dict plus the derived state of a database preparation step (never stored)."""
    payload = schedule.to_dict()
    payload['review_reason'] = getattr(schedule, 'review_reason', None)
    if isinstance(schedule, ScheduleReview):
        return payload
    if schedule.preparation:
        try:
            from backend.services.database_tools import get_database_tools
            payload["preparation_state"] = get_database_tools().preparation_state(schedule.preparation)
        except Exception:
            logger.exception("Could not check the preparation step of %s", schedule.schedule_id)
            payload["preparation_state"] = "unknown"
    return payload


def _requested_preparation(schedule_data: Dict[str, Any], current_user: dict, existing: Optional[Dict[str, Any]] = None):
    """The schedule's database preparation step after this request.

    Absent from the request: unchanged. Attaching, changing or removing a step schedules
    uploaded Python to write unattended, so it needs an administrator (the routes already
    require a local session). The server pins the package hash and connection; the client
    sends only the tool and its inputs.
    """
    if "preparation" not in schedule_data:
        return existing
    requested = schedule_data.get("preparation")
    is_admin = current_user.get("role") == "admin"
    from backend.services.database_tools import get_database_tools
    tools = get_database_tools()
    if requested is None:
        if existing is not None and not is_admin:
            raise HTTPException(status_code=403, detail="Only a local administrator can remove a database preparation step")
        return None
    if not isinstance(requested, dict) or not isinstance(requested.get("tool_id"), str) or not isinstance(requested.get("inputs", {}), dict):
        raise HTTPException(status_code=400, detail="preparation must be {tool_id, inputs}")
    unchanged = bool(existing) and requested["tool_id"] == existing.get("tool_id") and requested.get("inputs", {}) == existing.get("inputs", {})
    if unchanged and (not is_admin or tools.preparation_state(existing) == "ready"):
        return existing
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only a local administrator can attach or change a database preparation step")
    try:
        return tools.pin_preparation(requested["tool_id"], requested.get("inputs", {}), current_user.get("username", "unknown"))
    except PackageError as exc:
        raise HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc)) from exc


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
        contact.contact_id for contact in db_mgr.get_notification_contacts(include_inactive=True, include_review=True)
    }
    missing = [contact_id for contact_id in cleaned if contact_id not in available_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown notification contact(s): {', '.join(missing)}"
        )
    return cleaned


def _checked(check, value):
    """Run a stored-field check for a request; its reason is the 400 text."""
    try:
        return check(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _requested_contact(contact_id: str, contact_data: Dict[str, Any]) -> NotificationContact:
    return _checked(check_contact, {"contact_id": contact_id, "display_name": contact_data.get("display_name"),
                                    "email_address": contact_data.get("email_address"),
                                    "is_active": contact_data.get("is_active", True)})


def _collect_schedule_contact_recipients(
    schedule: ScheduledExperiment,
    db_mgr,
) -> Tuple[List[str], List[str], List[str]]:
    """Resolve active recipient emails for a schedule's notification contacts."""
    contacts = db_mgr.get_notification_contacts(include_inactive=True)
    contacts_by_id = {contact.contact_id: contact for contact in contacts}

    recipients: List[str] = []
    seen = set()
    missing_contact_ids: List[str] = []
    inactive_contact_ids: List[str] = []

    for contact_id in schedule.notification_contacts or []:
        contact = contacts_by_id.get(contact_id)
        if not contact:
            missing_contact_ids.append(contact_id)
            continue
        if not contact.is_active:
            inactive_contact_ids.append(contact_id)
            continue
        email = (contact.email_address or "").strip()
        if not email or email in seen:
            continue
        recipients.append(email)
        seen.add(email)

    return recipients, missing_contact_ids, inactive_contact_ids


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

    # Versions are returned verbatim by the API. A tolerance can accept a stale
    # draft after a path correction committed within the same second.
    return expected_dt == actual


def _check_schedule_request(fields, failure_message):
    try:
        return check_schedule(fields)
    except ValueError as exc:
        reason = str(exc)
        if reason in {'Experiment name is required', 'Experiment path is required', 'Estimated duration must be positive'}:
            reason = failure_message
        raise HTTPException(status_code=400, detail=reason) from exc


def _resolve_schedule_paths(schedule):
    if schedule.runner == 'venus':
        schedule.experiment_path = str(resolve_experiment_path(schedule.experiment_path))
    if schedule.timeout_config.cleanup_experiment_path:
        schedule.timeout_config.cleanup_experiment_path = str(resolve_experiment_path(schedule.timeout_config.cleanup_experiment_path))


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
def get_notification_settings_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Return the global SMTP settings (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage notification settings")

    scheduler, db_mgr, _ = get_services()
    settings = db_mgr.get_notification_settings()
    data = settings.to_public_dict()

    return ApiResponse(
        success=True,
        message="Notification settings retrieved",
        data=data,
    ).to_dict()


@router.put("/notifications/settings")
def update_notification_settings_endpoint(
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Update the global SMTP configuration (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage notification settings")
    actor = current_user.get("username", "unknown")

    manual_recipients = payload.get("manual_recovery_recipients", [])
    if isinstance(manual_recipients, str):
        manual_recipients = manual_recipients.split(",")
    elif isinstance(manual_recipients, list):
        if not all(isinstance(value, str) for value in manual_recipients):
            raise HTTPException(status_code=400, detail="manual_recovery_recipients must contain strings")
    elif manual_recipients is not None:
        raise HTTPException(status_code=400, detail="manual_recovery_recipients must be a string or list of strings")
    use_ssl = bool(payload.get("use_ssl", False))
    settings = _checked(check_email_settings, {
        "host": payload.get("host"),
        "port": payload.get("port", 587),
        "username": payload.get("username"),
        "sender": payload.get("sender"),
        # SSL replaces STARTTLS rather than conflicting with it.
        "use_tls": bool(payload.get("use_tls", True)) and not use_ssl,
        "use_ssl": use_ssl,
        "manual_recovery_recipients": manual_recipients,
        "updated_by": current_user.get("username"),
    })

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

    scheduler, db_mgr, _ = get_services()
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
def test_notification_settings_endpoint(
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Send a test email using the stored SMTP settings (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage notification settings")

    recipient_value = payload.get("recipient")
    recipient = _checked(check_email_address, recipient_value)

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

    if not send_recorded(email_service, subject, body, to=[recipient], timeout_seconds=10, attempts=1,
                         event_type="smtp_test", actor=current_user.get("username")):
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
        data={"recipient": recipient, "warning": email_service.delivery_log_warning},
    ).to_dict()


@router.post("/notifications/send")
def send_schedule_notification_email_endpoint(
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Send a custom email to the active notification contacts attached to a schedule."""
    actor = current_user.get("username", "unknown")
    if current_user.get("role") not in ["admin", "user"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    schedule_id_value = payload.get("schedule_id")
    subject_value = payload.get("subject")
    body_value = payload.get("body")

    if not isinstance(schedule_id_value, str) or not schedule_id_value.strip():
        raise HTTPException(status_code=400, detail="schedule_id is required")
    if not isinstance(subject_value, str) or not subject_value.strip():
        raise HTTPException(status_code=400, detail="subject is required")
    if not isinstance(body_value, str) or not body_value.strip():
        raise HTTPException(status_code=400, detail="body is required")

    schedule_id = schedule_id_value.strip()
    subject = subject_value.strip()
    body = body_value

    _, db_mgr, _ = get_services()
    schedule = db_mgr.get_schedule_by_id(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    recipients, missing_contact_ids, inactive_contact_ids = _collect_schedule_contact_recipients(schedule, db_mgr)
    if not recipients:
        details = {
            "schedule_id": schedule_id,
            "reason": "no_active_notification_recipients",
            "missing_contact_ids": missing_contact_ids,
            "inactive_contact_ids": inactive_contact_ids,
        }
        log_action(
            actor=actor,
            action="send_schedule_notification_email",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=True,
            details=details,
        )
        return ApiResponse(
            success=True,
            message="No active notification recipients configured for this schedule; email skipped",
            data={
                "schedule_id": schedule_id,
                "sent": False,
                "skipped": True,
                "recipients": [],
                "missing_contact_ids": missing_contact_ids,
                "inactive_contact_ids": inactive_contact_ids,
            },
        ).to_dict()

    email_service = EmailNotificationService()
    if not send_recorded(email_service, subject, body, to=recipients, timeout_seconds=10, attempts=1,
                         event_type="manual_email", schedule_id=schedule_id, actor=actor):
        detail = email_service.last_error or "Failed to deliver email; see backend logs for details"
        log_action(
            actor=actor,
            action="send_schedule_notification_email",
            scope="scheduling",
            client_ip=connection.client_ip,
            success=False,
            details={
                "schedule_id": schedule_id,
                "recipient_count": len(recipients),
                "error": detail,
            },
        )
        raise HTTPException(status_code=502, detail=detail)

    log_action(
        actor=actor,
        action="send_schedule_notification_email",
        scope="scheduling",
        client_ip=connection.client_ip,
        success=True,
        details={
            "schedule_id": schedule_id,
            "recipient_count": len(recipients),
        },
    )
    return ApiResponse(
        success=True,
        message=f"Notification email sent to {len(recipients)} recipient(s)",
        data={
            "schedule_id": schedule_id,
            "sent": True,
            "warning": email_service.delivery_log_warning,
            "skipped": False,
            "recipients": recipients,
            "missing_contact_ids": missing_contact_ids,
            "inactive_contact_ids": inactive_contact_ids,
        },
    ).to_dict()


@router.get("/contacts")
def list_notification_contacts(
    include_inactive: bool = Query(False, description="Include inactive contacts"),
    current_user: dict = Depends(get_current_user)
):
    """List notification contacts for scheduling."""
    try:
        _, db_mgr, _ = get_services()
        contacts = db_mgr.get_notification_contacts(include_inactive=include_inactive, include_review=True)
        response = ApiResponse(
            success=True,
            message="Notification contacts retrieved",
            data=[contact.to_dict() for contact in contacts]
        )
        return response.to_dict()
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
        raise
    except Exception as exc:
        logger.error(f"Error listing notification contacts: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load contacts")


@router.post("/contacts")
def create_notification_contact_endpoint(
    contact_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Create a new notification contact (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage contacts")

    contact = _requested_contact("", contact_data)
    actor = current_user.get("username", "unknown")

    scheduler, db_mgr, _ = get_services()
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
def update_notification_contact_endpoint(
    contact_id: str,
    contact_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Update an existing notification contact (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage contacts")

    contact = _requested_contact(contact_id, contact_data)
    actor = current_user.get("username", "unknown")

    scheduler, db_mgr, _ = get_services()
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
def delete_notification_contact_endpoint(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Delete a notification contact (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to manage contacts")

    actor = current_user.get("username", "unknown")

    scheduler, db_mgr, _ = get_services()
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
def list_notification_logs(
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
        scheduler, db_mgr, _ = get_services()
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
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
        raise
    except Exception as exc:
        logger.error("Error retrieving notification logs: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load notification logs")


@router.post("/create")
def create_schedule(
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
        
        scheduler, db_mgr, proc_mon = get_services()
        
        # Validate required fields
        required_fields = ["experiment_name", "experiment_path", "schedule_type", "estimated_duration"]
        if schedule_data.get('runner') == 'pyhsl':
            required_fields.remove('experiment_path')
        for field in required_fields:
            if field not in schedule_data:
                logger.error(f"Missing required field: {field}. Received data: {schedule_data}")
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        if schedule_data.get("prerequisites"):
            raise HTTPException(status_code=400, detail=PREREQUISITES_RETIRED)
        
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
            if start_time and start_time < datetime.now():
                raise HTTPException(
                    status_code=400,
                    detail="start_time cannot be in the past",
                )

        fields = {name: schedule_data[name] for name in (
            'experiment_name', 'experiment_path', 'schedule_type', 'interval_hours',
            'estimated_duration', 'log_inactivity_threshold_minutes', 'mode', 'is_active',
            'timeout_config', 'runner', 'protocol_id', 'parameters') if name in schedule_data}
        fields.update(schedule_id='', created_by=actor,
                      start_time=start_time.isoformat() if start_time else None,
                      notification_contacts=notification_contact_ids)
        if fields.get('runner') == 'pyhsl':
            fields['experiment_path'] = 'pyhsl:' + str(fields.get('protocol_id', ''))
        experiment = _check_schedule_request(fields, 'Failed to create schedule')
        for name, value in _runner_fields(experiment.to_dict()).items():
            setattr(experiment, name, value)
        _resolve_schedule_paths(experiment)
        experiment.preparation = _requested_preparation(schedule_data, current_user)

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
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
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
def list_schedules(
    active_only: bool = Query(True, description="Return only active schedules"),
    archived_only: bool = Query(False, description="Return only archived schedules"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of scheduled experiments
    
    Requires: any authenticated user
    """
    scheduler, db_mgr, proc_mon = get_services()


    schedules = db_mgr.get_schedules(active_only=active_only, archived_only=archived_only)

    next_run_times = scheduler.get_next_run_times()
    last_run_times = db_mgr.get_last_run_times()
    schedule_list = []
    for schedule in schedules:
        payload = _schedule_payload(schedule)
        payload['last_run'] = last_run_times.get(schedule.schedule_id)
        payload['next_run'] = (
            next_run_times.get(schedule.schedule_id)
            if not isinstance(schedule, ScheduleReview) and schedule.is_active and not schedule.archived
            else None
        )
        schedule_list.append(payload)

    response = ApiResponse(
        success=True,
        message=f"Retrieved {len(schedule_list)} schedules",
        data=schedule_list,
        metadata={
            "count": len(schedule_list),
            "active_only": active_only,
            "archived_only": archived_only,
        }
    )

    return response.to_dict()


@router.get("/calendar")
def get_calendar_data(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get calendar data for scheduled experiments
    
    Requires: any authenticated user
    """
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

    scheduler, db_mgr, proc_mon = get_services()

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


@router.put("/{schedule_id}")
def update_schedule(
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
        
        scheduler, db_mgr, _ = get_services()

        expected_token = update_data.pop("expected_updated_at", None) or if_unmodified_since
        base_schedule = _load_current_schedule(schedule_id, db_mgr, expected_token)

        if base_schedule.runner == 'pyhsl' and update_data.get('runner') == 'venus' and not update_data.get('experiment_path'):
            raise HTTPException(status_code=400, detail='Choose a VENUS method')
        if update_data.get('prerequisites', base_schedule.prerequisites) != base_schedule.prerequisites:
            raise HTTPException(status_code=400, detail=PREREQUISITES_RETIRED)
        fields = base_schedule.to_dict()
        for name in ('experiment_name', 'experiment_path', 'schedule_type', 'interval_hours', 'start_time',
                     'estimated_duration', 'log_inactivity_threshold_minutes', 'mode', 'is_active',
                     'timeout_config', 'runner', 'protocol_id', 'parameters'):
            if name in update_data:
                fields[name] = update_data[name]
        if 'start_time' in update_data:
            try:
                start_time = parse_iso_datetime_to_local(update_data['start_time'])
                fields['start_time'] = start_time.isoformat() if start_time else None
            except ValueError:
                raise HTTPException(status_code=400, detail='Invalid start_time format')
        if fields.get('runner') == 'pyhsl':
            fields['experiment_path'] = 'pyhsl:' + str(fields.get('protocol_id', ''))
        elif fields.get('runner') == 'venus':
            fields['parameters'] = {}
        fields['preparation'] = _requested_preparation(update_data, current_user, base_schedule.preparation)
        if 'preparation' in update_data and current_user.get('role') == 'admin':
            fields['prerequisites'] = []
        updated_schedule = _check_schedule_request(fields, 'Failed to update schedule')
        if 'notification_contacts' in update_data:
            updated_schedule.notification_contacts = _normalize_contact_ids(update_data['notification_contacts'], db_mgr)
        unchanged = all(getattr(updated_schedule, key) == getattr(base_schedule, key)
                        for key in ('runner', 'protocol_id', 'parameters', 'mode'))
        # Stopping or editing an unchanged stopped protocol does not need Run Control.
        if updated_schedule.is_active or not unchanged or updated_schedule.runner == 'venus':
            for name, value in _runner_fields(updated_schedule.to_dict()).items():
                setattr(updated_schedule, name, value)
        if 'experiment_path' in update_data and updated_schedule.runner == 'venus':
            updated_schedule.experiment_path = str(resolve_experiment_path(updated_schedule.experiment_path))
        if 'timeout_config' in update_data and updated_schedule.timeout_config.cleanup_experiment_path:
            updated_schedule.timeout_config.cleanup_experiment_path = str(resolve_experiment_path(updated_schedule.timeout_config.cleanup_experiment_path))

        updated_schedule.updated_at = utc_now_as_local_naive()

        # A reviewed method-path correction may have committed while this draft
        # was being validated. Recheck under the same lock before writing it back.
        with scheduler._schedules_lock:
            _load_current_schedule(schedule_id, db_mgr, base_schedule.updated_at.isoformat())
            success = scheduler.update_schedule(updated_schedule, expected_updated_at=base_schedule.updated_at.isoformat())
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update schedule")

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
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
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
def require_schedule_recovery(
    schedule_id: str,
    payload: Dict[str, Any] = None,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    if_unmodified_since: Optional[str] = Header(None, alias="If-Unmodified-Since"),
):
    # Mark a schedule as requiring manual recovery and halt automated dispatch.
    if current_user.get('role') not in ['admin', 'user']:
        raise HTTPException(status_code=403, detail='Insufficient permissions')

    scheduler, db_mgr, _ = get_services()
    note = (payload or {}).get('note') if payload else None
    expected_token = (payload or {}).get('expected_updated_at') or if_unmodified_since
    actor = current_user.get('username') or current_user.get('user_id', 'system')

    _load_current_schedule(schedule_id, db_mgr, expected_token)
    updated = scheduler.require_manual_recovery(schedule_id, note, actor, expected_token)
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


class RecoveryResolution(BaseModel):
    schedule_id: Optional[str] = None
    expected_revision: int = Field(strict=True, ge=0)
    robot_ready: StrictBool
    note: Optional[str] = None
    expected_updated_at: Optional[str] = None


class DispatchResume(BaseModel):
    expected_revision: int = Field(strict=True, ge=0)


def _resolve_recovery_request(payload, current_user, connection):
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    if not payload.robot_ready:
        raise HTTPException(status_code=400, detail='Confirm the robot is ready before acknowledging recovery.')
    scheduler, _, _ = get_services()
    actor = current_user.get('username') or 'unknown'
    updated = scheduler.resolve_manual_recovery(payload.schedule_id, payload.note, actor,
                    payload.expected_revision, payload.expected_updated_at)
    state = scheduler.get_manual_recovery_state()
    log_action(actor=actor, action='resolve_manual_recovery', scope='scheduling', client_ip=connection.client_ip,
               success=True, details={'schedule_id': payload.schedule_id, 'note': payload.note, 'revision': state.safety_revision})
    return ApiResponse(success=True, message='Recovery acknowledged. Use Resume queued jobs when ready.',
                       data={'schedule': updated.to_dict() if updated else None, 'manual_recovery': state.to_dict()}).to_dict()


@router.post('/recovery/resolve')
def resolve_global_recovery(payload: RecoveryResolution, current_user: dict = Depends(get_current_user),
                            connection: ConnectionContext = Depends(require_local_access)):
    return _resolve_recovery_request(payload, current_user, connection)


@router.post('/dispatch/resume')
def resume_queued_jobs(payload: DispatchResume, current_user: dict = Depends(get_current_user),
                       connection: ConnectionContext = Depends(require_local_access)):
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    scheduler, _, _ = get_services()
    actor = current_user.get('username') or 'unknown'
    state = scheduler.resume_queued_jobs(payload.expected_revision, actor)
    log_action(actor=actor, action='resume_queued_jobs', scope='scheduling', client_ip=connection.client_ip,
               success=True, details={'revision': state.safety_revision})
    return ApiResponse(success=True, message='Queued dispatch resumed', data={'manual_recovery': state.to_dict()}).to_dict()


@router.delete("/{schedule_id}")
def delete_schedule(
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
        scheduler, db_mgr, proc_mon = get_services()

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

        if not scheduler.remove_schedule(schedule_id, expected_updated_at=expected_token):
            raise HTTPException(status_code=400, detail="Failed to delete schedule")

        response = ApiResponse(
            success=True,
            message=f"Schedule deleted: {authoritative_schedule.experiment_name}",
            data={
                "schedule_id": schedule_id,
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
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
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


@router.post("/{schedule_id}/archive")
def set_schedule_archived(
    schedule_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    archived_flag = payload.get("archived")
    if archived_flag is None:
        raise HTTPException(status_code=400, detail="archived flag is required")
    archived = bool(archived_flag)

    scheduler, db_mgr, _ = get_services()
    # Serialize the complete read/write with reviewed method-path changes.
    with scheduler._schedules_lock:
        schedule = db_mgr.get_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        is_admin = current_user.get("role") == "admin"
        is_local_owner = (
            connection.is_local
            and schedule.created_by
            and schedule.created_by == current_user.get("username")
        )
        if not (is_admin or is_local_owner):
            raise HTTPException(status_code=403, detail="Admin role required")

        if isinstance(schedule, ScheduleReview):
            raise HTTPException(status_code=400, detail=f'Needs review: {schedule.review_reason}')

        if schedule.archived == archived:
            return ApiResponse(
                success=True,
                message="Schedule archive state unchanged",
                data=schedule.to_dict(),
            ).to_dict()

        expected_updated_at = payload.get("expected_updated_at") or schedule.updated_at.isoformat()
        schedule.archived = archived
        if archived:
            schedule.is_active = False
        schedule.updated_at = utc_now_as_local_naive()

        if not db_mgr.update_scheduled_experiment(schedule, expected_updated_at=expected_updated_at):
            raise HTTPException(status_code=400, detail="Failed to update schedule")

        scheduler.invalidate_schedule(schedule_id)

    message = "Schedule archived" if archived else "Schedule unarchived"
    return ApiResponse(
        success=True,
        message=message,
        data=schedule.to_dict(),
    ).to_dict()


@router.get("/status/queue")
def get_queue_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current queue status and running jobs
    
    Requires: any authenticated user
    """
    scheduler, db_mgr, proc_mon = get_services()

    # Get queue status from scheduler runtime (single-worker queue)
    queue_status = scheduler.get_runtime_queue_status()


    manual_state = scheduler.get_manual_recovery_state()

    response = ApiResponse(
        success=True,
        message="Queue status retrieved successfully",
        data={
            "is_running": scheduler.is_running,
            "queue": queue_status,
            "hamilton": {"is_running": not queue_status["hamilton_available"]},
            "manual_recovery": manual_state.to_dict() if manual_state else None,
        }
    )

    return response.to_dict()


@router.get("/experiments/available")
def get_available_experiments(
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of available Hamilton experiment files
    
    Returns imported experiment files from the catalogue with metadata.
    
    Requires: any authenticated user
    """
    try:
        discovery_service = get_experiment_discovery_service()
        
        experiments = discovery_service.get_available_experiments()
        
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
                "categorized": categorized
            }
        )
        
        return response.to_dict()
        
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
        raise
    except Exception as e:
        logger.error(f"Error getting available experiments: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve experiments")


class MethodImportRequest(BaseModel):
    folder_path: StrictStr
    relative_paths: Optional[List[StrictStr]] = None


def _require_method_import_role(user):
    if user.get("role") not in {"admin", "user"}:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.get("/experiments/browse")
def browse_method_folders(
    path: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    from backend.services.scheduling.method_library import browse_methods
    _require_method_import_role(current_user)
    try:
        data = browse_methods(get_experiment_discovery_service().db, path)
        return ApiResponse(success=True, message="Host folder loaded", data=data).to_dict()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MethodCheckRequest(BaseModel):
    method_ids: List[StrictStr] = Field(min_length=1, max_length=1000)


class MethodArchiveRequest(BaseModel):
    archived: StrictBool
    expected_revision: int = Field(ge=1, strict=True)


class MethodPathRequest(BaseModel):
    new_path: StrictStr = Field(min_length=1)


class MethodSelectedReference(BaseModel):
    schedule_id: StrictStr
    role: str = Field(pattern='^(primary|cleanup)$')
    expected_updated_at: StrictStr


class MethodChangePathRequest(MethodPathRequest):
    expected_revision: int = Field(ge=1, strict=True)
    references: List[MethodSelectedReference] = Field(default_factory=list, max_length=1000)


@router.post('/experiments/library/{method_id}/path-preview')
def preview_library_path(method_id: str, request: MethodPathRequest, current_user: dict = Depends(get_current_user), connection: ConnectionContext = Depends(require_local_access)):
    from backend.services.scheduling.method_library import path_change_preview
    _require_method_import_role(current_user)
    try:
        preview = path_change_preview(get_experiment_discovery_service().db, get_scheduler_engine(), method_id, request.new_path)
        return ApiResponse(success=True, message='Review affected schedules', data=preview).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/experiments/library/{method_id}/change-path')
def change_library_path(method_id: str, request: MethodChangePathRequest, current_user: dict = Depends(get_current_user), connection: ConnectionContext = Depends(require_local_access)):
    _require_method_import_role(current_user)
    try:
        result = get_scheduler_engine().change_library_method_path(get_experiment_discovery_service().db, method_id, request.new_path, request.expected_revision, [row.model_dump() for row in request.references])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    log_action(actor=current_user.get('username', 'unknown'), action='change_method_path', scope='scheduling', client_ip=connection.client_ip,
               success=True, details={**result, 'new_path': request.new_path})
    return ApiResponse(success=True, message='Method path and selected schedule references updated', data=result).to_dict()


@router.get('/experiments/library')
def get_method_library(current_user: dict = Depends(get_current_user), connection: ConnectionContext = Depends(require_local_access)):
    from backend.services.scheduling.method_library import library_records
    _require_method_import_role(current_user)
    rows = library_records(get_experiment_discovery_service().db)
    return ApiResponse(success=True, message='Method library loaded', data={'methods': rows}).to_dict()


@router.post('/experiments/library/check')
def check_method_library(request: MethodCheckRequest, current_user: dict = Depends(get_current_user), connection: ConnectionContext = Depends(require_local_access)):
    from backend.services.scheduling.method_library import check_library_paths
    _require_method_import_role(current_user)
    outcomes = check_library_paths(get_experiment_discovery_service().db, request.method_ids)
    return ApiResponse(success=all(row['success'] for row in outcomes), message='Path checks finished', data={'outcomes': outcomes}).to_dict()


@router.patch('/experiments/library/{method_id}')
def archive_library_method(method_id: str, request: MethodArchiveRequest, current_user: dict = Depends(get_current_user), connection: ConnectionContext = Depends(require_local_access)):
    _require_method_import_role(current_user)
    try:
        get_experiment_discovery_service().db.set_method_archived(method_id, request.archived, request.expected_revision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    log_action(actor=current_user.get('username', 'unknown'), action='archive_method' if request.archived else 'restore_method', scope='scheduling', client_ip=connection.client_ip, success=True, details={'method_id': method_id})
    return ApiResponse(success=True, message='Method archived' if request.archived else 'Method restored', data={'method_id': method_id}).to_dict()


@router.post("/experiments/import-preview")
def preview_experiment_import(
    request: MethodImportRequest,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Read host method metadata without updating the catalogue or starting methods."""
    _require_method_import_role(current_user)
    try:
        preview = get_experiment_discovery_service().preview_methods(request.folder_path, request.relative_paths)
        return ApiResponse(success=True, message="Review the methods before importing", data=preview).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
        raise
    except Exception as exc:
        logger.exception("Method preview failed")
        raise HTTPException(status_code=500, detail="Could not preview methods; try again.") from exc


@router.post("/experiments/import-folder")
def import_experiment_folder(
    request: MethodImportRequest,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    _require_method_import_role(current_user)
    try:
        result = get_experiment_discovery_service().import_methods_from_folder(request.folder_path, current_user.get('username', 'unknown'), request.relative_paths)
        return ApiResponse(success=result["success"], message="Method import finished", data=result).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (SafetyConflict, StorageUnavailable, sqlite3.Error):
        raise
    except Exception as exc:
        logger.exception("Method folder import failed")
        raise HTTPException(status_code=500, detail="Could not import methods; try again.") from exc


@router.get("/executions/history")
def get_execution_history(
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
    - Error messages and timeout/queue context
    
    Requires: any authenticated user
    """
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 200")

    scheduler, db_mgr, proc_mon = get_services()

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
