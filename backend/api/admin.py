"""
RobotControl Admin API
Basic admin endpoints for user management and system monitoring
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import logging
import time

from backend.services.auth import get_current_admin_user, AuthService

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateUserEmailRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)
    must_reset: bool = Field(default=True)


class ResolveResetRequestBody(BaseModel):
    resolution_note: Optional[str] = Field(default=None, max_length=500)

@router.get("/users")
async def get_users(current_user: dict = Depends(get_current_admin_user)):
    """Get list of system users"""
    start_time = time.time()
    
    try:
        auth_service = AuthService()
        users = auth_service.get_all_users()
        
        safe_users = []
        for user in users:
            safe_users.append({
                "username": user.get("username"),
                "email": user.get("email"),
                "role": user.get("role"),
                "is_active": user.get("is_active", True),
                "must_reset": user.get("must_reset", False),
                "last_login": user.get("last_login_at"),
                "last_login_ip": user.get("last_login_ip"),
                "last_login_ip_type": user.get("last_login_ip_type"),
                "created_at": user.get("created_at")
            })
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_users")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("user_count", len(safe_users))
        
        return ResponseFormatter.success(
            data=safe_users,
            metadata=metadata,
            message=f"Retrieved {len(safe_users)} users successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving users",
            details=str(e)
        )


@router.get("/password-reset/requests")
async def get_password_reset_requests(current_user: dict = Depends(get_current_admin_user)):
    """Retrieve pending and resolved password reset requests."""
    start_time = time.time()

    try:
        auth_service = AuthService()
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

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_password_reset_requests")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("request_count", len(safe_requests))

        return ResponseFormatter.success(
            data=safe_requests,
            metadata=metadata,
            message="Password reset requests retrieved successfully",
        )

    except Exception as exc:
        logger.error("Error retrieving password reset requests: %s", exc)
        return ResponseFormatter.server_error(
            message="Error retrieving password reset requests",
            details=str(exc),
        )


@router.post("/password-reset/requests/{request_id}/resolve")
async def resolve_password_reset_request(
    request_id: int,
    request: ResolveResetRequestBody,
    current_user: dict = Depends(get_current_admin_user),
):
    """Mark a password reset request as resolved."""
    start_time = time.time()

    try:
        auth_service = AuthService()
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

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "resolve_password_reset_request")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("request_id", request_id)

        return ResponseFormatter.success(
            data={
                "id": resolved.get("id"),
                "status": resolved.get("status"),
                "resolved_at": resolved.get("resolved_at"),
                "resolved_by": resolved.get("resolved_by"),
                "resolution_note": resolved.get("resolution_note"),
            },
            metadata=metadata,
            message="Password reset request resolved",
        )

    except Exception as exc:
        logger.error("Error resolving password reset request %s: %s", request_id, exc)
        return ResponseFormatter.server_error(
            message="Error resolving password reset request",
            details=str(exc),
        )


@router.post("/users/{username}/reset-password")
async def reset_user_password(
    username: str,
    request: ResetPasswordRequest,
    current_user: dict = Depends(get_current_admin_user)
):
    """Reset a user's password and optionally force a change on next login."""
    start_time = time.time()

    try:
        auth_service = AuthService()
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

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "reset_password")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("target_user", username)
        metadata.add_metadata("must_reset", request.must_reset)

        return ResponseFormatter.success(
            data={"username": username, "must_reset": request.must_reset},
            metadata=metadata,
            message="Password reset successfully"
        )

    except Exception as exc:
        logger.error("Error resetting password for '%s': %s", username, exc)
        return ResponseFormatter.server_error(
            message="Error resetting password",
            details=str(exc)
        )

@router.put("/users/{username}/email")
async def update_user_email(
    username: str,
    request: UpdateUserEmailRequest,
    current_user: dict = Depends(get_current_admin_user),
):
    """Update a user's email address."""
    start_time = time.time()

    try:
        auth_service = AuthService()
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

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "update_user_email")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("target_user", username)

        return ResponseFormatter.success(
            data={"username": username, "email": request.email},
            metadata=metadata,
            message="User email updated successfully",
        )

    except Exception as exc:
        logger.error("Error updating email for '%s': %s", username, exc)
        return ResponseFormatter.server_error(
            message="Error updating user email",
            details=str(exc),
        )

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    current_user: dict = Depends(get_current_admin_user),
):
    """Delete a user account."""
    start_time = time.time()

    try:
        if username == current_user.get("username"):
            return ResponseFormatter.bad_request(
                message="Cannot delete the currently authenticated administrator",
                details={"username": username},
            )

        auth_service = AuthService()
        existing = auth_service.get_user_by_username(username)
        if not existing:
            return ResponseFormatter.not_found(
                message="User not found",
                details={"username": username},
            )

        success = auth_service.delete_user(username)
        if not success:
            return ResponseFormatter.server_error(
                message="Failed to delete user",
                details={"username": username},
            )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "delete_user")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("target_user", username)

        return ResponseFormatter.success(
            data={"username": username},
            metadata=metadata,
            message="User deleted successfully",
        )

    except Exception as exc:
        logger.error("Error deleting user '%s': %s", username, exc)
        return ResponseFormatter.server_error(
            message="Error deleting user",
            details=str(exc),
        )

