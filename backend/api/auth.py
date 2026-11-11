"""
RobotControl Authentication API

Clean and simple REST API endpoints for authentication operations.
Consolidates functionality from web_app/api/v1/auth.py into a simplified interface.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
import logging
import time
from datetime import datetime

# Import our simplified authentication service
from backend.services.auth import AUTH_STORAGE_ERRORS, AuthService, get_auth_service, get_current_user

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter,
)
from backend.api.dependencies import ConnectionContext, get_connection_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])



# Request/Response Models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)

class LoginThrottle:
    """Failed remote sign-ins per username and per client address, in a sliding window.

    The app is reachable through a public tunnel, so password guessing is limited there.
    Local sign-ins (the RobotControl computer) are never throttled, so remote guessing
    cannot lock the lab out of its own accounts. Kept in memory: a restart clears it.
    """

    WINDOW_SECONDS = 300
    LIMITS = {"user": 5, "ip": 20}

    def __init__(self):
        self._failures: Dict[tuple, list] = {}

    def _keys(self, username: str, client_ip: Optional[str]):
        yield ("user", username.strip().lower())
        if client_ip:
            yield ("ip", client_ip)

    def _recent(self, key, now):
        recent = [at for at in self._failures.get(key, []) if now - at < self.WINDOW_SECONDS]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, username: str, client_ip: Optional[str]) -> int:
        """Seconds until another attempt is allowed; 0 when allowed now."""
        now = time.monotonic()
        wait = 0
        for key in self._keys(username, client_ip):
            recent = self._recent(key, now)
            if len(recent) >= self.LIMITS[key[0]]:
                wait = max(wait, int(self.WINDOW_SECONDS - (now - recent[0])) + 1)
        return wait

    def failed(self, username: str, client_ip: Optional[str]):
        now = time.monotonic()
        if len(self._failures) > 10_000:  # Many one-off addresses: drop expired keys.
            for key in list(self._failures):
                self._recent(key, now)
        for key in self._keys(username, client_ip):
            self._failures.setdefault(key, []).append(now)

    def succeeded(self, username: str):
        self._failures.pop(("user", username.strip().lower()), None)


login_throttle = LoginThrottle()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)

class PasswordResetRequestBody(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    note: Optional[str] = Field(default=None, max_length=500)

class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Authentication Endpoints

@router.post("/login")
async def login(
    request: LoginRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Authenticate user and return JWT tokens
    
    Args:
        request: Login request with username and password
        auth_service: Authentication service
        
    Returns:
        Access token, refresh token, and user information
    """
    throttled = not connection.is_local

    if throttled:
        wait = login_throttle.retry_after(request.username, connection.client_ip)
        if wait:
            logger.warning("Throttled remote sign-in for %s from %s", request.username, connection.client_ip)
            response = ResponseFormatter.error(
                message=f"Too many failed sign-in attempts. Try again in {max(1, round(wait / 60))} min.",
                error_code="TOO_MANY_ATTEMPTS",
                status_code=429,
            )
            response.headers["Retry-After"] = str(wait)
            return response

    if not connection.is_local and auth_service.has_built_in_password(request.username, request.password):
        logger.warning(
            "Refused remote sign-in for %s with the built-in default password (from %s)",
            request.username,
            connection.client_ip,
        )
        return ResponseFormatter.error(
            message="Change the default password on the robot PC before signing in remotely.",
            error_code="DEFAULT_PASSWORD_REMOTE",
            status_code=403,
        )
    client_info = {
        "ip": connection.client_ip,
        "ip_classification": connection.ip_classification,
        "user_agent": http_request.headers.get("user-agent"),
    }
    result = auth_service.login(request.username, request.password, client_info=client_info)
    if not result:
        logger.warning(f"Failed login attempt for username: {request.username}")
        if throttled:
            login_throttle.failed(request.username, connection.client_ip)
        return ResponseFormatter.unauthorized(
            message="Invalid username or password",
            details={"username": request.username}
        )
    if throttled:
        login_throttle.succeeded(request.username)


    result["session"] = {
        "is_local": connection.is_local,
        "ip_classification": connection.ip_classification,
    }
    # Opens the existing required change-password dialog; nothing is stored.
    if auth_service.is_built_in_password(request.password):
        result["user"]["must_reset"] = True
    logger.info(
        "Successful login for user: %s (connection=%s)",
        request.username,
        connection.ip_classification,
    )
    return ResponseFormatter.success(data=result)

@router.post("/register")
async def register(
    request: RegisterRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Register a new user account and issue tokens.
    """
    try:
        auth_service.register_user(request.username.strip(), request.email.lower(), request.password)
        client_info = {
            "ip": connection.client_ip,
            "ip_classification": connection.ip_classification,
            "user_agent": http_request.headers.get("user-agent"),
        }
        result = auth_service.login(request.username, request.password, client_info=client_info)
        if result:
            result["session"] = {
                "is_local": connection.is_local,
                "ip_classification": connection.ip_classification,
            }


        return ResponseFormatter.success(data=result, status_code=201, message="Registration successful")

    except ValueError as exc:
        logger.warning(f"Registration failed for '{request.username}': {exc}")
        return ResponseFormatter.bad_request(
            message=str(exc),
            details={"username": request.username, "email": request.email}
        )

@router.post("/password-reset/request")
async def password_reset_request(
    request: PasswordResetRequestBody,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Allow a user to request an administrator-assisted password reset.
    """

    try:
        if not request.username and not request.email:
            return ResponseFormatter.validation_error(
                message="Username or email must be provided"
            )

        client_info = {
            "ip": connection.client_ip,
            "ip_classification": connection.ip_classification,
            "user_agent": http_request.headers.get("user-agent"),
        }

        result = auth_service.request_password_reset(
            username=request.username.strip() if request.username else None,
            email=request.email.lower() if request.email else None,
            note=request.note,
            client_info=client_info,
        )


        response_payload: Dict[str, Any] = {"status": "queued"}
        if result:
            response_payload.update(
                {
                    "request_id": result.get("id"),
                    "requested_at": result.get("requested_at"),
                }
            )

        message = "If the account exists, an administrator has been notified."
        return ResponseFormatter.success(
            data=response_payload,

            status_code=202,
            message=message,
        )

    except ValueError as exc:
        logger.warning("Password reset request rejected: %s", exc)
        return ResponseFormatter.validation_error(message=str(exc))

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Allow an authenticated user to change their password.
    """

    success = auth_service.change_password(
        current_user["user_id"],
        request.current_password,
        request.new_password,
    )
    if not success:
        # 400, not 401: the session is valid, and the frontend treats 401 as a
        # lost session and signs the user out.
        return ResponseFormatter.bad_request(
            message="Current password is incorrect",
            details={"username": current_user["username"]}
        )
    return ResponseFormatter.success(
        data={"message": "Password changed successfully"},
        message="Password changed successfully"
    )


@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Refresh access token using refresh token
    
    Args:
        request: Refresh token request
        auth_service: Authentication service
        
    Returns:
        New access token
    """
    
    try:
        new_access_token = auth_service.refresh_access_token(request.refresh_token)
        
        if not new_access_token:
            logger.warning("Failed token refresh attempt")
            return ResponseFormatter.unauthorized(
                message="Invalid or expired refresh token"
            )
        

        logger.info("Token refreshed successfully")
        return ResponseFormatter.success(
            data={
                "access_token": new_access_token,
                "token_type": "bearer"
            },

        )

    except AUTH_STORAGE_ERRORS as e:
        logger.error(f"Sign-in storage unavailable during token refresh: {e}")
        return ResponseFormatter.service_unavailable(
            message="Sign-in storage is temporarily unavailable",
            details=str(e)
        )


@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    return ResponseFormatter.success(data={
        **{key: current_user[key] for key in ("user_id", "username", "role", "is_active")},
        "session": {"is_local": connection.is_local, "ip_classification": connection.ip_classification,
                    "client_ip": connection.client_ip},
    })
