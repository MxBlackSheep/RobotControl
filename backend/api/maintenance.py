"""
HxRun maintenance mode API.

This module exposes a persistent maintenance flag dedicated to blocking HxRun.
It is intentionally separate from transient database-maintenance UI state.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from backend.api.dependencies import ConnectionContext, get_connection_context, require_local_access
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata
from backend.services.auth import get_current_user
from backend.services.hxrun_maintenance import get_hxrun_maintenance_service
from backend.utils.audit import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class HxRunMaintenanceUpdateRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = Field(default=None, max_length=500)


@router.get("/hxrun")
async def get_hxrun_maintenance_state(
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """Return current HxRun maintenance mode state (readable by local and remote sessions)."""
    start_time = time.time()
    service = get_hxrun_maintenance_service()
    state = service.get_state(force_refresh=True)

    metadata = ResponseMetadata()
    metadata.set_execution_time(start_time)
    metadata.add_metadata("operation", "hxrun_maintenance_get")
    metadata.add_metadata("requested_by", current_user.get("username"))

    return ResponseFormatter.success(
        data={
            **state.to_dict(),
            "permissions": {
                "is_local_session": connection.is_local,
                "can_edit": connection.is_local,
                "ip_classification": connection.ip_classification,
                "client_ip": connection.client_ip,
            },
        },
        metadata=metadata,
        message="HxRun maintenance state retrieved",
    )


@router.put("/hxrun")
async def update_hxrun_maintenance_state(
    payload: HxRunMaintenanceUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """Enable or disable HxRun maintenance mode (local sessions only)."""
    start_time = time.time()
    actor = current_user.get("username", "unknown")
    reason = payload.reason.strip() if isinstance(payload.reason, str) and payload.reason.strip() else None

    service = get_hxrun_maintenance_service()
    current_state = service.get_state(force_refresh=True)

    if payload.enabled and not current_state.enabled and service.is_hxrun_running():
        message = "HxRun is running. Please close the software before entering maintenance mode."

        log_action(
            actor=actor,
            action="hxrun_maintenance_update_blocked",
            scope="maintenance",
            client_ip=connection.client_ip,
            success=False,
            details={
                "requested_enabled": True,
                "reason": reason,
                "blocked_by": "hxrun_running",
            },
        )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "hxrun_maintenance_update")
        metadata.add_metadata("requested_by", actor)
        metadata.add_metadata("enabled", False)
        metadata.add_metadata("blocked", True)
        metadata.add_metadata("blocked_reason", "hxrun_running")

        return ResponseFormatter.error(
            message=message,
            error_code="HXRUN_RUNNING",
            details={"hxrun_running": True},
            status_code=status.HTTP_409_CONFLICT,
            metadata=metadata,
        )

    state = service.set_state(enabled=payload.enabled, reason=reason, actor=actor)

    log_action(
        actor=actor,
        action="hxrun_maintenance_update",
        scope="maintenance",
        client_ip=connection.client_ip,
        success=True,
        details={
            "enabled": state.enabled,
            "reason": state.reason,
        },
    )

    metadata = ResponseMetadata()
    metadata.set_execution_time(start_time)
    metadata.add_metadata("operation", "hxrun_maintenance_update")
    metadata.add_metadata("requested_by", actor)
    metadata.add_metadata("enabled", state.enabled)

    return ResponseFormatter.success(
        data={
            **state.to_dict(),
            "permissions": {
                "is_local_session": connection.is_local,
                "can_edit": True,
                "ip_classification": connection.ip_classification,
                "client_ip": connection.client_ip,
            },
        },
        metadata=metadata,
        message="HxRun maintenance state updated",
    )
