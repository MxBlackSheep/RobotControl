"""
RobotControl Simplified Authentication API

Clean and simple REST API endpoints for authentication operations.
Consolidates functionality from web_app/api/v1/auth.py into a simplified interface.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
import logging
import time
from datetime import datetime

# Import our simplified authentication service
from backend.services.auth import AuthService, User, get_auth_service

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter,
    ResponseMetadata,
)
from backend.api.dependencies import ConnectionContext, get_connection_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
security = HTTPBearer()


# Request/Response Models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)

class RegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)

class PasswordResetRequestBody(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    note: Optional[str] = Field(default=None, max_length=500)

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    is_active: bool


class MessageResponse(BaseModel):
    message: str


# Dependency to get auth service
async def get_auth_service_dep() -> AuthService:
    """FastAPI dependency function to get the auth service"""
    return get_auth_service()


# Dependency to get current user from token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service_dep)
) -> User:
    """
    FastAPI dependency to get current authenticated user from JWT token
    
    Args:
        credentials: HTTP Bearer token credentials
        auth_service: Authentication service
        
    Returns:
        User object if token is valid
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = auth_service.verify_token(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


# Dependency to require admin role
async def require_admin(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service_dep)
) -> User:
    """
    FastAPI dependency to require admin role
    
    Args:
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        User object if user is admin
        
    Raises:
        HTTPException: If user is not admin
    """
    if not auth_service.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user


# Authentication Endpoints

@router.post("/login")
async def login(
    request: LoginRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service_dep),
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
    start_time = time.time()
    
    try:
        # Attempt login
        client_info = {
            "ip": connection.client_ip,
            "user_agent": http_request.headers.get("user-agent"),
        }
        result = auth_service.login(request.username, request.password, client_info=client_info)
        
        if not result:
            logger.warning(f"Failed login attempt for username: {request.username}")
            return ResponseFormatter.unauthorized(
                message="Invalid username or password",
                details={"username": request.username}
            )
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "login")
        metadata.add_metadata("username", request.username)
        
        if result:
            result["session"] = {
                "is_local": connection.is_local,
                "ip_classification": connection.ip_classification,
            }

        logger.info(
            "Successful login for user: %s (connection=%s)",
            request.username,
            connection.ip_classification,
        )
        return ResponseFormatter.success(data=result, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Login error for user '{request.username}': {e}")
        return ResponseFormatter.server_error(
            message="Login failed due to server error",
            details=str(e)
        )

@router.post("/register")
async def register(
    request: RegisterRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service_dep),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Register a new user account and issue tokens.
    """
    start_time = time.time()
    try:
        auth_service.register_user(request.username.strip(), request.email.lower(), request.password)
        client_info = {
            "ip": connection.client_ip,
            "user_agent": http_request.headers.get("user-agent"),
        }
        result = auth_service.login(request.username, request.password, client_info=client_info)
        if result:
            result["session"] = {
                "is_local": connection.is_local,
                "ip_classification": connection.ip_classification,
            }

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "register")
        metadata.add_metadata("username", request.username)

        return ResponseFormatter.success(data=result, metadata=metadata, status_code=201, message="Registration successful")

    except ValueError as exc:
        logger.warning(f"Registration failed for '{request.username}': {exc}")
        return ResponseFormatter.bad_request(
            message=str(exc),
            details={"username": request.username, "email": request.email}
        )
    except Exception as exc:
        logger.error(f"Registration error for '{request.username}': {exc}")
        return ResponseFormatter.server_error(
            message="Registration failed due to server error",
            details=str(exc)
        )

@router.post("/password-reset/request")
async def password_reset_request(
    request: PasswordResetRequestBody,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service_dep),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Allow a user to request an administrator-assisted password reset.
    """
    start_time = time.time()

    try:
        if not request.username and not request.email:
            return ResponseFormatter.validation_error(
                message="Username or email must be provided"
            )

        client_info = {
            "ip": connection.client_ip,
            "user_agent": http_request.headers.get("user-agent"),
        }

        result = auth_service.request_password_reset(
            username=request.username.strip() if request.username else None,
            email=request.email.lower() if request.email else None,
            note=request.note,
            client_info=client_info,
        )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "password_reset_request")
        if request.username:
            metadata.add_metadata("username", request.username)

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
            metadata=metadata,
            status_code=202,
            message=message,
        )

    except ValueError as exc:
        logger.warning("Password reset request rejected: %s", exc)
        return ResponseFormatter.validation_error(message=str(exc))
    except Exception as exc:
        logger.error("Password reset request error: %s", exc)
        return ResponseFormatter.server_error(
            message="Unable to submit password reset request",
            details=str(exc),
        )

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service_dep)
):
    """
    Allow an authenticated user to change their password.
    """
    start_time = time.time()

    try:
        success = auth_service.change_password(
            current_user,
            request.current_password,
            request.new_password,
        )

        if not success:
            return ResponseFormatter.unauthorized(
                message="Current password is incorrect",
                details={"username": current_user.username}
            )

        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "change_password")
        metadata.add_metadata("username", current_user.username)

        return ResponseFormatter.success(
            data={"message": "Password changed successfully"},
            metadata=metadata,
            message="Password changed successfully"
        )

    except Exception as exc:
        logger.error(f"Password change error for '{current_user.username}': {exc}")
        return ResponseFormatter.server_error(
            message="Password change failed due to server error",
            details=str(exc)
        )


@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service_dep)
):
    """
    Refresh access token using refresh token
    
    Args:
        request: Refresh token request
        auth_service: Authentication service
        
    Returns:
        New access token
    """
    start_time = time.time()
    
    try:
        new_access_token = auth_service.refresh_access_token(request.refresh_token)
        
        if not new_access_token:
            logger.warning("Failed token refresh attempt")
            return ResponseFormatter.unauthorized(
                message="Invalid or expired refresh token"
            )
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "token_refresh")
        
        logger.info("Token refreshed successfully")
        return ResponseFormatter.success(
            data={
                "access_token": new_access_token,
                "token_type": "bearer"
            },
            metadata=metadata
        )
        
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return ResponseFormatter.server_error(
            message="Token refresh failed due to server error",
            details=str(e)
        )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Logout user (token invalidation handled client-side)
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Success message
        
    Note:
        In a stateless JWT system, logout is handled client-side by discarding tokens.
        For additional security, a token blacklist could be implemented.
    """
    start_time = time.time()
    
    try:
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "logout")
        metadata.add_metadata("username", current_user.username)
        
        logger.info(f"User '{current_user.username}' logged out")
        return ResponseFormatter.success(
            data={"message": "Logged out successfully"},
            metadata=metadata
        )
        
    except Exception as e:
        logger.error(f"Logout error for user '{current_user.username}': {e}")
        return ResponseFormatter.server_error(
            message="Logout failed due to server error",
            details=str(e)
        )


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Get current user information
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User information
    """
    start_time = time.time()
    
    try:
        user_data = {
            "user_id": current_user.user_id,
            "username": current_user.username,
            "role": current_user.role,
            "is_active": current_user.is_active,
            "session": {
                "is_local": connection.is_local,
                "ip_classification": connection.ip_classification,
                "client_ip": connection.client_ip,
            },
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_user_info")
        metadata.add_metadata("user_id", current_user.user_id)
        metadata.add_metadata("connection", connection.ip_classification)
        
        return ResponseFormatter.success(data=user_data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting user info for '{current_user.username}': {e}")
        return ResponseFormatter.server_error(
            message="Failed to get user information",
            details=str(e)
        )


@router.get("/users")
async def get_users(
    current_user: User = Depends(require_admin),
    auth_service: AuthService = Depends(get_auth_service_dep)
):
    """
    Get list of all users (admin only)
    
    Args:
        current_user: Current authenticated admin user
        auth_service: Authentication service
        
    Returns:
        List of all users
    """
    start_time = time.time()
    
    try:
        user_list = auth_service.get_user_list()
        stats = auth_service.get_auth_stats()
        
        data = {
            "users": user_list,
            "total_count": len(user_list),
            "statistics": stats
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_user_list")
        metadata.add_metadata("requested_by", current_user.username)
        metadata.set_pagination(len(user_list))
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting user list: {e}")
        return ResponseFormatter.server_error(
            message="Failed to get user list",
            details=str(e)
        )


@router.get("/status")
async def get_auth_status():
    """
    Get authentication service status (public endpoint)
    
    Returns:
        Authentication service status and statistics
    """
    start_time = time.time()
    
    try:
        auth_service = get_auth_service()
        stats = auth_service.get_auth_stats()
        
        data = {
            "service": "authentication",
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_users": stats["total_users"],
                "active_users": stats["active_users"],
                "admin_users": stats["admin_users"]
            },
            "endpoints": [
                "/api/auth/login",
                "/api/auth/refresh", 
                "/api/auth/logout",
                "/api/auth/me",
                "/api/auth/users",
                "/api/auth/status"
            ]
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "status_check")
        metadata.set_cache_used(False)
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Auth status error: {e}")
        return ResponseFormatter.server_error(
            message="Authentication service status check failed",
            details=str(e)
        )


@router.get("/health")
async def health_check():
    """
    Authentication service health check endpoint
    
    Returns:
        Service health status
    """
    start_time = time.time()
    
    try:
        auth_service = get_auth_service()
        stats = auth_service.get_auth_stats()
        
        data = {
            "service": "authentication",
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "details": {
                "users_configured": stats["total_users"] > 0,
                "admin_users_available": stats["admin_users"] > 0
            }
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "health_check")
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Auth health check error: {e}")
        return ResponseFormatter.server_error(
            message="Authentication service health check failed",
            details=str(e)
        )


if __name__ == "__main__":
    # For testing purposes
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI(title="RobotControl Authentication API", version="1.0.0")
    app.include_router(router)
    
    uvicorn.run(app, host="0.0.0.0", port=8002)
