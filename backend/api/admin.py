"""
RobotControl Admin API
Basic admin endpoints for user management and system monitoring
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional
import logging
import time

from backend.api.dependencies import ConnectionContext, get_connection_context
from backend.services.auth import get_current_admin_user, get_auth_service
from backend.utils.audit import log_action

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateUserEmailRequest(BaseModel):
    email: EmailStr


class SetUserRoleRequest(BaseModel):
    role: Literal["user", "admin"]


# Another admin removed the caller's admin role after this request passed the admin check.
NO_LONGER_ADMIN = "You are no longer an admin. Reload the page"


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)
    must_reset: bool = Field(default=True)


class ResolveResetRequestBody(BaseModel):
    resolution_note: Optional[str] = Field(default=None, max_length=500)

@router.get("/users")
async def get_users(current_user: dict = Depends(get_current_admin_user)):
    """Get list of system users"""
    
    auth_service = get_auth_service()
    users = auth_service.get_user_list()

    # Create metadata

    return ResponseFormatter.success(
        data=users,
        message=f"Retrieved {len(users)} users successfully"
    )


@router.get("/password-reset/requests")
async def get_password_reset_requests(current_user: dict = Depends(get_current_admin_user)):
    """Retrieve pending and resolved password reset requests."""

    auth_service = get_auth_service()
    requests = auth_service.get_password_reset_requests()
    safe_requests = []
    for entry in requests:
        safe_requests.append(
            {
                "id": entry.get("id"),
                "user_id": entry.get("user_id"),
                "username": entry.get("username"),
                "email": entry.get("email"),
                "status": entry.get("status"),
                "note": entry.get("note"),
                "client_ip": entry.get("client_ip"),
                "user_agent": entry.get("user_agent"),
                "requested_at": entry.get("requested_at"),
                "resolved_at": entry.get("resolved_at"),
                "resolved_by": entry.get("resolved_by"),
                "resolution_note": entry.get("resolution_note"),
            }
        )
    return ResponseFormatter.success(
        data=safe_requests,
        message="Password reset requests retrieved successfully",
    )


@router.post("/password-reset/requests/{request_id}/resolve")
async def resolve_password_reset_request(
    request_id: int,
    request: ResolveResetRequestBody,
    current_user: dict = Depends(get_current_admin_user),
):
    """Mark a password reset request as resolved."""

    auth_service = get_auth_service()
    resolved = auth_service.resolve_password_reset_request(
        request_id=request_id,
        resolved_by=current_user.get("username"),
        resolution_note=request.resolution_note,
    )
    if not resolved:
        return ResponseFormatter.not_found(
            message="Password reset request not found",
            details={"request_id": request_id},
        )
    return ResponseFormatter.success(
        data={
            "id": resolved.get("id"),
            "status": resolved.get("status"),
            "resolved_at": resolved.get("resolved_at"),
            "resolved_by": resolved.get("resolved_by"),
            "resolution_note": resolved.get("resolution_note"),
        },
        message="Password reset request resolved",
    )


@router.post("/users/{username}/reset-password")
async def reset_user_password(
    username: str,
    request: ResetPasswordRequest,
    current_user: dict = Depends(get_current_admin_user)
):
    """Reset a user's password and optionally force a change on next login."""

    auth_service = get_auth_service()
    success = auth_service.reset_password(
        username=username,
        new_password=request.new_password,
        must_reset=request.must_reset,
    )
    if not success:
        return ResponseFormatter.not_found(
            message="User not found",
            details={"username": username}
        )
    return ResponseFormatter.success(
        data={"username": username, "must_reset": request.must_reset},
        message="Password reset successfully"
    )

@router.put("/users/{username}/email")
async def update_user_email(
    username: str,
    request: UpdateUserEmailRequest,
    current_user: dict = Depends(get_current_admin_user),
):
    """Update a user's email address."""

    auth_service = get_auth_service()
    existing = auth_service.get_user_by_username(username)
    if not existing:
        return ResponseFormatter.not_found(
            message="User not found",
            details={"username": username},
        )
    try:
        success = auth_service.update_user_email(username, request.email)
    except ValueError as exc:
        return ResponseFormatter.validation_error(
            message=str(exc),
            details={"email": request.email},
        )
    if not success:
        return ResponseFormatter.error(
            message="Email address already in use",
            error_code="EMAIL_IN_USE",
            details={"email": request.email},
            status_code=status.HTTP_409_CONFLICT,
        )
    return ResponseFormatter.success(
        data={"username": username, "email": request.email},
        message="User email updated successfully",
    )

@router.put("/users/{username}/role")
async def set_user_role(
    username: str,
    request: SetUserRoleRequest,
    current_user: dict = Depends(get_current_admin_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """Switch another account between user and admin; it applies on that account's next request."""

    auth_service = get_auth_service()
    if username == current_user.get("username"):
        response = ResponseFormatter.bad_request(message="Cannot change your own role", details={"username": username})
    elif not auth_service.get_user_by_username(username):
        response = ResponseFormatter.not_found(message="User not found", details={"username": username})
    elif not auth_service.set_user_role(username, request.role, int(current_user["user_id"])):
        response = ResponseFormatter.forbidden(message=NO_LONGER_ADMIN, details={"username": username})
    else:
        response = ResponseFormatter.success(data={"username": username, "role": request.role},
                                             message="User role updated successfully")
    log_action(actor=current_user["username"], action="change_user_role", scope="users", client_ip=connection.client_ip,
               success=response.status_code == 200, details={"target": username, "role": request.role})
    return response


@router.delete("/users/{username}")
async def delete_user(
    username: str,
    current_user: dict = Depends(get_current_admin_user),
):
    """Delete a user account."""

    if username == current_user.get("username"):
        return ResponseFormatter.bad_request(
            message="Cannot delete the currently authenticated administrator",
            details={"username": username},
        )
    auth_service = get_auth_service()
    existing = auth_service.get_user_by_username(username)
    if not existing:
        return ResponseFormatter.not_found(
            message="User not found",
            details={"username": username},
        )
    if not auth_service.delete_user(username, int(current_user["user_id"])):
        return ResponseFormatter.forbidden(message=NO_LONGER_ADMIN, details={"username": username})
    return ResponseFormatter.success(
        data={"username": username},
        message="User deleted successfully",
    )
