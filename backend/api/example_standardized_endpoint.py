"""
Example API Endpoint Using Standardized Response Format

This file demonstrates how to implement API endpoints using the standardized
ResponseFormatter to ensure consistent response structure across RobotControl.

This example shows:
1. Success responses with metadata
2. Error responses with proper codes
3. Paginated responses
4. Validation error handling
5. Exception handling
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, Field
import time
import logging

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error,
    handle_api_exceptions
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/example", tags=["example"])


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    role: str = Field(default="user", regex=r'^(user|admin|moderator)$')


class User(BaseModel):
    id: int
    username: str
    email: str
    role: str
    created_at: str


# Mock data for demonstration
MOCK_USERS = [
    User(id=1, username="admin", email="admin@robotcontrol.com", role="admin", created_at="2023-01-01T00:00:00Z"),
    User(id=2, username="user1", email="user1@robotcontrol.com", role="user", created_at="2023-01-02T00:00:00Z"),
    User(id=3, username="mod1", email="mod1@robotcontrol.com", role="moderator", created_at="2023-01-03T00:00:00Z"),
]


@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search users by username")
):
    """
    Get paginated list of users with standardized response format.
    
    This demonstrates:
    - Paginated response with metadata
    - Query parameter validation
    - Search functionality
    - Performance timing
    """
    start_time = time.time()
    
    try:
        # Filter users based on search
        filtered_users = MOCK_USERS
        if search:
            filtered_users = [
                user for user in MOCK_USERS 
                if search.lower() in user.username.lower()
            ]
        
        # Calculate pagination
        total_count = len(filtered_users)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_users = filtered_users[start_idx:end_idx]
        
        # Return standardized paginated response
        return ResponseFormatter.paginated_response(
            data=[user.dict() for user in page_users],
            total_count=total_count,
            page=page,
            limit=limit,
            execution_start_time=start_time,
            cache_used=False  # No cache in this example
        )
        
    except Exception as e:
        logger.error(f"Error retrieving users: {e}")
        return ResponseFormatter.server_error(
            message="Failed to retrieve users",
            details=str(e)
        )


@router.get("/users/{user_id}")
async def get_user(user_id: int):
    """
    Get single user by ID with standardized response format.
    
    This demonstrates:
    - Success response with metadata
    - Not found error handling
    - Execution timing
    """
    start_time = time.time()
    
    try:
        # Find user
        user = next((u for u in MOCK_USERS if u.id == user_id), None)
        
        if not user:
            return ResponseFormatter.not_found(
                message=f"User with ID {user_id} not found",
                details={"user_id": user_id}
            )
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("source", "mock_data")
        metadata.add_metadata("user_id", user_id)
        
        return ResponseFormatter.success(
            data=user.dict(),
            metadata=metadata
        )
        
    except Exception as e:
        logger.error(f"Error retrieving user {user_id}: {e}")
        return ResponseFormatter.server_error(
            message="Failed to retrieve user",
            details=str(e)
        )


@router.post("/users")
async def create_user(user_data: UserCreateRequest):
    """
    Create new user with standardized response format.
    
    This demonstrates:
    - Request validation
    - Validation error responses
    - Success response with 201 status
    - Resource creation metadata
    """
    start_time = time.time()
    
    try:
        # Check if username already exists
        if any(u.username == user_data.username for u in MOCK_USERS):
            return ResponseFormatter.validation_error(
                message="Username already exists",
                details={
                    "field": "username",
                    "value": user_data.username,
                    "constraint": "unique"
                }
            )
        
        # Create new user (mock implementation)
        new_user = User(
            id=len(MOCK_USERS) + 1,
            username=user_data.username,
            email=user_data.email,
            role=user_data.role,
            created_at=f"{time.time():.0f}"
        )
        
        # Add to mock data
        MOCK_USERS.append(new_user)
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "create")
        metadata.add_metadata("resource_id", new_user.id)
        
        return ResponseFormatter.success(
            data=new_user.dict(),
            metadata=metadata,
            status_code=201  # Created
        )
        
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return ResponseFormatter.server_error(
            message="Failed to create user",
            details=str(e)
        )


@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """
    Delete user with standardized response format.
    
    This demonstrates:
    - Delete operation response
    - Not found handling
    - Success response with no data
    """
    start_time = time.time()
    
    try:
        # Find user index
        user_index = next((i for i, u in enumerate(MOCK_USERS) if u.id == user_id), None)
        
        if user_index is None:
            return ResponseFormatter.not_found(
                message=f"User with ID {user_id} not found",
                details={"user_id": user_id}
            )
        
        # Remove user (mock implementation)
        deleted_user = MOCK_USERS.pop(user_index)
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "delete")
        metadata.add_metadata("deleted_user_id", user_id)
        metadata.add_metadata("deleted_username", deleted_user.username)
        
        return ResponseFormatter.success(
            data={"message": f"User '{deleted_user.username}' deleted successfully"},
            metadata=metadata
        )
        
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        return ResponseFormatter.server_error(
            message="Failed to delete user",
            details=str(e)
        )


@handle_api_exceptions
@router.get("/users/stats")
async def get_user_stats():
    """
    Get user statistics with automatic exception handling.
    
    This demonstrates:
    - Using the exception handling decorator
    - Statistics/summary endpoints
    - Cache simulation
    """
    start_time = time.time()
    
    # Simulate potential exception (remove this in real implementation)
    # raise ValueError("Simulated error for demonstration")
    
    # Calculate stats
    total_users = len(MOCK_USERS)
    role_counts = {}
    for user in MOCK_USERS:
        role_counts[user.role] = role_counts.get(user.role, 0) + 1
    
    stats = {
        "total_users": total_users,
        "role_distribution": role_counts,
        "average_username_length": sum(len(u.username) for u in MOCK_USERS) / total_users if total_users > 0 else 0
    }
    
    # Create metadata with cache simulation
    metadata = ResponseMetadata()
    metadata.set_execution_time(start_time)
    metadata.set_cache_used(True)  # Simulate cache hit
    metadata.add_metadata("stats_calculated_at", metadata.timestamp)
    
    return ResponseFormatter.success(
        data=stats,
        metadata=metadata
    )


# Health check endpoint (minimal response)
@router.get("/health")
async def health_check():
    """Simple health check with minimal standardized response"""
    return format_success({"status": "healthy", "service": "example_api"})


# Error simulation endpoint for testing
@router.get("/simulate-error")
async def simulate_error(error_type: str = Query("server", regex=r'^(server|validation|not_found|unauthorized)$')):
    """
    Simulate different types of errors for testing frontend error handling.
    
    This demonstrates different error response types.
    """
    
    if error_type == "server":
        return ResponseFormatter.server_error(
            message="Simulated server error",
            details={"simulation": True, "error_type": "server"}
        )
    elif error_type == "validation":
        return ResponseFormatter.validation_error(
            message="Simulated validation error",
            details={"field": "test_field", "constraint": "required"}
        )
    elif error_type == "not_found":
        return ResponseFormatter.not_found(
            message="Simulated resource not found",
            details={"resource_id": "test_123"}
        )
    elif error_type == "unauthorized":
        return ResponseFormatter.unauthorized(
            message="Simulated unauthorized access",
            details={"required_permission": "admin"}
        )
    
    # Default to server error
    return ResponseFormatter.server_error("Unknown error type requested")