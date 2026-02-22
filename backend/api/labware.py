"""
Labware API endpoints.

Exposes TipTracking and Cytomat read/update operations.
"""

from __future__ import annotations

from datetime import datetime
import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.dependencies import ConnectionContext, get_connection_context, require_local_access
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata
from backend.services.auth import get_current_user
from backend.services.labware_tip_tracking import (
    TipStatusUpdate,
    TipTrackingDatabaseError,
    TipTrackingService,
    TipTrackingValidationError,
    get_tip_tracking_service,
)
from backend.services.labware_cytomat import (
    CytomatDatabaseError,
    CytomatPlateUpdate,
    CytomatService,
    CytomatValidationError,
    get_cytomat_service,
)
from backend.utils.audit import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/labware", tags=["labware"])


class TipTrackingUpdateItem(BaseModel):
    labware_id: str = Field(..., min_length=1, max_length=100)
    position_id: int = Field(..., ge=1, le=96)
    status: str = Field(..., min_length=1, max_length=32)


class TipTrackingUpdateRequest(BaseModel):
    family: str = Field(..., min_length=1, max_length=32)
    updates: List[TipTrackingUpdateItem] = Field(default_factory=list)


class TipTrackingResetRequest(BaseModel):
    family: str = Field(..., min_length=1, max_length=32)


class CytomatUpdateItem(BaseModel):
    cytomat_pos: str = Field(..., min_length=1, max_length=100)
    plate_id: str = Field(default="", max_length=255)


class CytomatUpdateRequest(BaseModel):
    updates: List[CytomatUpdateItem] = Field(default_factory=list)


def _require_labware_role(current_user: Dict[str, Any]) -> str:
    role = str(current_user.get("role") or "").lower()
    if role not in {"admin", "user"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or user role required",
        )
    return role


@router.get("/tip-tracking")
async def get_tip_tracking_snapshot(
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
    service: TipTrackingService = Depends(get_tip_tracking_service),
):
    """Fetch tip-tracking state for all supported families."""
    start_time = time.time()

    role = _require_labware_role(current_user)

    try:
        snapshot = service.build_snapshot()
        snapshot["permissions"] = {
            "role": role,
            "is_local_session": connection.is_local,
            "can_update": connection.is_local,
            "ip_classification": connection.ip_classification,
            "client_ip": connection.client_ip,
        }

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "labware_tip_tracking_get")
        metadata.add_metadata("requested_by", current_user.get("username"))
        metadata.add_metadata("can_update", connection.is_local)

        return ResponseFormatter.success(
            data=snapshot,
            metadata=metadata,
            message="Tip tracking state retrieved",
        )
    except TipTrackingValidationError as exc:
        return ResponseFormatter.bad_request(message=str(exc))
    except TipTrackingDatabaseError as exc:
        return ResponseFormatter.server_error(
            message="Unable to load tip tracking state",
            details=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected tip-tracking read error: %s", exc)
        return ResponseFormatter.server_error(
            message="Unexpected error while loading tip tracking state",
            details=str(exc),
        )


@router.put("/tip-tracking")
async def update_tip_tracking(
    request: TipTrackingUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    service: TipTrackingService = Depends(get_tip_tracking_service),
):
    """Apply batch tip status updates. Local access is required."""
    start_time = time.time()

    _require_labware_role(current_user)
    actor = current_user.get("username", "unknown")

    if not request.updates:
        return ResponseFormatter.validation_error(message="updates list cannot be empty")

    try:
        updates = [
            TipStatusUpdate(
                labware_id=item.labware_id,
                position_id=item.position_id,
                status=item.status,
            )
            for item in request.updates
        ]

        updated_count = service.apply_updates(request.family, updates)

        log_action(
            actor=actor,
            action="tip_tracking_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=True,
            details={
                "family": request.family,
                "requested_count": len(request.updates),
                "updated_count": updated_count,
            },
        )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "labware_tip_tracking_update")
        metadata.add_metadata("requested_by", actor)
        metadata.add_metadata("family", request.family)
        metadata.add_metadata("requested_count", len(request.updates))
        metadata.add_metadata("updated_count", updated_count)

        return ResponseFormatter.success(
            data={
                "family": request.family,
                "requested_count": len(request.updates),
                "updated_count": updated_count,
                "updated_at": datetime.now().isoformat(),
            },
            metadata=metadata,
            message="Tip tracking updates applied",
        )
    except TipTrackingValidationError as exc:
        log_action(
            actor=actor,
            action="tip_tracking_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"family": request.family, "error": str(exc)},
        )
        return ResponseFormatter.validation_error(message=str(exc))
    except TipTrackingDatabaseError as exc:
        log_action(
            actor=actor,
            action="tip_tracking_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"family": request.family, "error": str(exc)},
        )
        return ResponseFormatter.server_error(
            message="Unable to persist tip tracking updates",
            details=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected tip-tracking update error: %s", exc)
        log_action(
            actor=actor,
            action="tip_tracking_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"family": request.family, "error": str(exc)},
        )
        return ResponseFormatter.server_error(
            message="Unexpected error while updating tip tracking state",
            details=str(exc),
        )


@router.post("/tip-tracking/reset")
async def reset_tip_tracking_family(
    request: TipTrackingResetRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    service: TipTrackingService = Depends(get_tip_tracking_service),
):
    """Reset one tip family to its configured baseline state. Local access is required."""
    start_time = time.time()

    _require_labware_role(current_user)
    actor = current_user.get("username", "unknown")

    try:
        updated_count = service.reset_family(request.family)

        log_action(
            actor=actor,
            action="tip_tracking_reset",
            scope="labware",
            client_ip=connection.client_ip,
            success=True,
            details={"family": request.family, "updated_count": updated_count},
        )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "labware_tip_tracking_reset")
        metadata.add_metadata("requested_by", actor)
        metadata.add_metadata("family", request.family)
        metadata.add_metadata("updated_count", updated_count)

        return ResponseFormatter.success(
            data={
                "family": request.family,
                "updated_count": updated_count,
                "updated_at": datetime.now().isoformat(),
            },
            metadata=metadata,
            message="Tip tracking family reset complete",
        )
    except TipTrackingValidationError as exc:
        log_action(
            actor=actor,
            action="tip_tracking_reset",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"family": request.family, "error": str(exc)},
        )
        return ResponseFormatter.validation_error(message=str(exc))
    except TipTrackingDatabaseError as exc:
        log_action(
            actor=actor,
            action="tip_tracking_reset",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"family": request.family, "error": str(exc)},
        )
        return ResponseFormatter.server_error(
            message="Unable to reset tip tracking family",
            details=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected tip-tracking reset error: %s", exc)
        log_action(
            actor=actor,
            action="tip_tracking_reset",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"family": request.family, "error": str(exc)},
        )
        return ResponseFormatter.server_error(
            message="Unexpected error while resetting tip tracking family",
            details=str(exc),
        )


@router.get("/cytomat")
async def get_cytomat_snapshot(
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
    service: CytomatService = Depends(get_cytomat_service),
):
    """Fetch Cytomat position to PlateID map and allowed PlateID dropdown values."""
    start_time = time.time()

    role = _require_labware_role(current_user)

    try:
        snapshot = service.build_snapshot()
        snapshot["permissions"] = {
            "role": role,
            "is_local_session": connection.is_local,
            "can_update": connection.is_local,
            "ip_classification": connection.ip_classification,
            "client_ip": connection.client_ip,
        }

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "labware_cytomat_get")
        metadata.add_metadata("requested_by", current_user.get("username"))
        metadata.add_metadata("can_update", connection.is_local)

        return ResponseFormatter.success(
            data=snapshot,
            metadata=metadata,
            message="Cytomat state retrieved",
        )
    except CytomatValidationError as exc:
        return ResponseFormatter.bad_request(message=str(exc))
    except CytomatDatabaseError as exc:
        return ResponseFormatter.server_error(
            message="Unable to load Cytomat state",
            details=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected Cytomat read error: %s", exc)
        return ResponseFormatter.server_error(
            message="Unexpected error while loading Cytomat state",
            details=str(exc),
        )


@router.put("/cytomat")
async def update_cytomat(
    request: CytomatUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
    service: CytomatService = Depends(get_cytomat_service),
):
    """Apply batch Cytomat PlateID updates. Local access is required."""
    start_time = time.time()

    _require_labware_role(current_user)
    actor = current_user.get("username", "unknown")

    if not request.updates:
        return ResponseFormatter.validation_error(message="updates list cannot be empty")

    try:
        updates = [
            CytomatPlateUpdate(
                cytomat_pos=item.cytomat_pos,
                plate_id=item.plate_id,
            )
            for item in request.updates
        ]
        updated_count = service.apply_updates(updates)

        log_action(
            actor=actor,
            action="cytomat_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=True,
            details={
                "requested_count": len(request.updates),
                "updated_count": updated_count,
            },
        )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "labware_cytomat_update")
        metadata.add_metadata("requested_by", actor)
        metadata.add_metadata("requested_count", len(request.updates))
        metadata.add_metadata("updated_count", updated_count)

        return ResponseFormatter.success(
            data={
                "requested_count": len(request.updates),
                "updated_count": updated_count,
                "updated_at": datetime.now().isoformat(),
            },
            metadata=metadata,
            message="Cytomat updates applied",
        )
    except CytomatValidationError as exc:
        log_action(
            actor=actor,
            action="cytomat_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"error": str(exc)},
        )
        return ResponseFormatter.validation_error(message=str(exc))
    except CytomatDatabaseError as exc:
        log_action(
            actor=actor,
            action="cytomat_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"error": str(exc)},
        )
        return ResponseFormatter.server_error(
            message="Unable to persist Cytomat updates",
            details=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected Cytomat update error: %s", exc)
        log_action(
            actor=actor,
            action="cytomat_update",
            scope="labware",
            client_ip=connection.client_ip,
            success=False,
            details={"error": str(exc)},
        )
        return ResponseFormatter.server_error(
            message="Unexpected error while updating Cytomat state",
            details=str(exc),
        )
