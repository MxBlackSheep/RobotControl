"""
RobotControl Database Backup/Restore API

Secure admin-only endpoints for database backup and restore operations.
Follows the simplified architecture pattern with comprehensive error handling.

Features:
- Admin-only authentication required for all operations
- RESTful API design with consistent response formats
- Comprehensive validation and error handling
- File security and path validation
- Operation logging and monitoring
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import time

from backend.services.auth import get_current_admin_user, get_current_user
from backend.services.backup import get_backup_service, BackupInfo, BackupResult, RestoreResult, BackupDetails
from backend.api.dependencies import ConnectionContext, require_local_access, get_connection_context
from backend.utils.audit import log_action

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _ensure_backup_permission(current_user: Dict[str, Any], connection: ConnectionContext) -> None:
    """Allow admins or local users to perform backup operations."""
    role = current_user.get("role")
    if role == "admin":
        return
    if connection.is_local and role in {"user", "admin"}:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin role required",
    )

# Request/Response Models
class CreateBackupRequest(BaseModel):
    """Request model for backup creation"""
    description: str = Field(
        ..., 
        min_length=1, 
        max_length=1000,
        description="Description for the backup"
    )

class BackupInfoResponse(BaseModel):
    """Response model for backup information"""
    filename: str
    description: str
    timestamp: str
    created_date: str
    file_size: int
    file_size_formatted: str
    is_valid: bool
    database_name: Optional[str] = None
    sql_server: Optional[str] = None

class BackupResultResponse(BaseModel):
    """Response model for backup operation results"""
    success: bool
    message: str
    filename: Optional[str] = None
    file_size: Optional[int] = None
    duration_ms: Optional[int] = None
    error_details: Optional[str] = None

class RestoreResultResponse(BaseModel):
    """Response model for restore operation results"""
    success: bool
    message: str
    backup_filename: str
    duration_ms: Optional[int] = None
    warnings: Optional[List[str]] = None
    error_details: Optional[str] = None

class BackupDetailsResponse(BaseModel):
    """Response model for detailed backup information"""
    filename: str
    description: str
    timestamp: str
    created_date: str
    file_size: int
    file_size_formatted: str
    database_name: str
    sql_server: str
    metadata: Dict[str, Any]
    is_valid: bool

# Helper function to ensure consistent API response format (DEPRECATED - use ResponseFormatter)
# This function is maintained for backward compatibility but should use ResponseFormatter
def create_api_response(success: bool, data: Any = None, message: str = "", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    DEPRECATED: Use ResponseFormatter.success() or ResponseFormatter.error() instead
    
    Create standardized API response format to prevent axios response.data vs response.data.data issues
    
    Args:
        success: Operation success status
        data: Response data
        message: Response message
        metadata: Optional metadata
    
    Returns:
        Standardized response dictionary
    """
    response = {
        "success": success,
        "data": data,
        "message": message
    }
    
    if metadata:
        response["metadata"] = metadata
    
    return response


@router.post("/create", response_model=Dict[str, Any])
async def create_backup(
    request: CreateBackupRequest,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """
    Create a new database backup
    
    Args:
        request: Backup creation request with description
        current_user: Current authenticated admin user
        
    Returns:
        Standardized API response with backup creation result
    """
    start_time = time.time()
    
    actor = current_user.get("username", "unknown")
    try:
        logger.info(f"Creating backup requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        result = backup_service.create_backup(request.description)
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "create_backup")
        metadata.add_metadata("requested_by", current_user['username'])
        metadata.add_metadata("description", request.description)
        
        if result.success:
            logger.info(f"Backup created successfully: {result.filename}")
            metadata.add_metadata("filename", result.filename)
            metadata.add_metadata("backup_successful", True)
            log_action(
                actor=actor,
                action="create_backup",
                scope="database",
                client_ip=connection.client_ip,
                success=True,
                details={"filename": result.filename},
            )
            
            return ResponseFormatter.success(
                data=result.to_dict(),
                metadata=metadata,
                message="Backup created successfully"
            )
        else:
            logger.warning(f"Backup creation failed: {result.message}")
            metadata.add_metadata("backup_successful", False)
            log_action(
                actor=actor,
                action="create_backup",
                scope="database",
                client_ip=connection.client_ip,
                success=False,
                details={"description": request.description, "error": result.message},
            )
            
            return ResponseFormatter.bad_request(
                message=result.message,
                details="Backup creation failed",
                data=result.to_dict(),
                metadata=metadata
            )
            
    except Exception as e:
        logger.error(f"Unexpected error creating backup: {e}")
        log_action(
            actor=actor,
            action="create_backup",
            scope="database",
            client_ip=connection.client_ip,
            success=False,
            details={"description": request.description, "error": str(e)},
        )
        return ResponseFormatter.server_error(
            message="An unexpected error occurred while creating backup",
            details=str(e)
        )


@router.get("/list", response_model=Dict[str, Any])
async def list_backups(
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    """
    Get list of all available backups
    
    Args:
        current_user: Current authenticated admin user
        
    Returns:
        Standardized API response with list of backup information
    """
    start_time = time.time()
    
    try:
        _ensure_backup_permission(current_user, connection)
        logger.info(f"Listing backups requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        backups = backup_service.list_backups()
        
        # Convert BackupInfo objects to dictionaries
        backup_data = [backup.to_dict() for backup in backups]
        
        logger.info(f"Found {len(backups)} backup files")
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "list_backups")
        metadata.add_metadata("requested_by", current_user['username'])
        metadata.add_metadata("backup_count", len(backups))
        
        return ResponseFormatter.success(
            data=backup_data,
            metadata=metadata,
            message=f"Found {len(backups)} backup files"
        )
        
    except Exception as e:
        logger.error(f"Unexpected error listing backups: {e}")
        return ResponseFormatter.server_error(
            message="An unexpected error occurred while listing backups",
            details=str(e)
        )


@router.get("/{filename}/details", response_model=Dict[str, Any])
async def get_backup_details(
    filename: str,
    current_user: dict = Depends(get_current_admin_user)
):
    """
    Get detailed information about a specific backup
    
    Args:
        filename: Name of backup file
        current_user: Current authenticated admin user
        
    Returns:
        Standardized API response with detailed backup information
    """
    start_time = time.time()
    
    try:
        logger.info(f"Getting backup details for {filename} requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        details = backup_service.get_backup_details(filename)
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_backup_details")
        metadata.add_metadata("admin_user", current_user['username'])
        metadata.add_metadata("filename", filename)
        
        if details is None:
            logger.warning(f"Backup not found: {filename}")
            metadata.add_metadata("backup_found", False)
            
            return ResponseFormatter.not_found(
                message=f"Backup file not found: {filename}",
                details=f"No backup file named '{filename}' exists in the backup directory",
                metadata=metadata
            )
        
        logger.info(f"Retrieved details for backup: {filename}")
        metadata.add_metadata("backup_found", True)
        metadata.add_metadata("backup_size", details.file_size)
        
        return ResponseFormatter.success(
            data=details.to_dict(),
            metadata=metadata,
            message="Backup details retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Unexpected error getting backup details: {e}")
        return ResponseFormatter.server_error(
            message="An unexpected error occurred while getting backup details",
            details=str(e)
        )


class RestoreBackupRequest(BaseModel):
    """Request model for backup restoration"""
    filename: Optional[str] = Field(None, description="Filename from backup directory")
    file_path: Optional[str] = Field(None, description="Full path to backup file")

@router.post("/restore", response_model=Dict[str, Any])
async def restore_backup(
    request: RestoreBackupRequest,
    current_user: dict = Depends(get_current_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """
    Restore database from backup file
    
    IMPORTANT: This operation will temporarily make the database unavailable
    
    Args:
        request: RestoreBackupRequest with either filename or file_path
        current_user: Current authenticated admin user
        
    Returns:
        Standardized API response with restore operation result
    """
    restore_source: Optional[str] = None
    try:
        # Validate request - must have either filename or file_path, but not both
        if not request.filename and not request.file_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either filename or file_path must be provided"
            )
        
        if request.filename and request.file_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either filename or file_path, not both"
            )
        restore_source = request.filename or request.file_path
        is_admin = current_user.get("role") == "admin"
        is_local_user = connection.is_local and current_user.get("role") in {"user", "admin"}
        if not (is_admin or is_local_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required"
            )
        logger.warning(f"Database restore from {restore_source} requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        
        if request.filename:
            # Use existing restore_backup method for managed .bak files
            result = backup_service.restore_backup(request.filename)
        else:
            # Use new restore_from_path method for .bck files
            result = backup_service.restore_backup_from_path(request.file_path)
        
        if result.success:
            logger.info(f"Database restored successfully from: {restore_source}")
            log_action(
                actor=current_user["username"],
                action="database_restore",
                scope="database",
                client_ip=connection.client_ip,
                success=True,
                details={"source": restore_source},
            )
            return create_api_response(
                success=True,
                data=result.to_dict(),
                message="Database restored successfully"
            )
        else:
            logger.error(f"Database restore failed: {result.message}")
            log_action(
                actor=current_user["username"],
                action="database_restore",
                scope="database",
                client_ip=connection.client_ip,
                success=False,
                details={"source": restore_source, "message": result.message},
            )
            return create_api_response(
                success=False,
                data=result.to_dict(),
                message=result.message
            )
            
    except HTTPException as exc:
        log_action(
            actor=current_user["username"],
            action="database_restore",
            scope="database",
            client_ip=connection.client_ip,
            success=False,
            details={"source": restore_source, "error": exc.detail},
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error during restore: {e}")
        log_action(
            actor=current_user["username"],
            action="database_restore",
            scope="database",
            client_ip=connection.client_ip,
            success=False,
            details={"source": restore_source, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during database restore"
        )


@router.delete("/{filename}", response_model=Dict[str, Any])
async def delete_backup(
    filename: str,
    current_user: dict = Depends(get_current_admin_user),
    connection: ConnectionContext = Depends(require_local_access),
):
    """
    Delete backup file and associated metadata
    
    Args:
        filename: Name of backup file to delete
        current_user: Current authenticated admin user
        
    Returns:
        Standardized API response with delete operation result
    """
    actor = current_user.get("username", "unknown")
    try:
        logger.info(f"Deleting backup {filename} requested by user: {actor}")
        
        backup_service = get_backup_service()
        result = backup_service.delete_backup(filename)
        
        if result["success"]:
            logger.info(f"Backup deleted successfully: {filename}")
            log_action(
                actor=actor,
                action="delete_backup",
                scope="database",
                client_ip=connection.client_ip,
                success=True,
                details={"filename": filename},
            )
            return create_api_response(
                success=True,
                data=result,
                message=result["message"]
            )
        else:
            logger.warning(f"Backup deletion failed: {result['message']}")
            log_action(
                actor=actor,
                action="delete_backup",
                scope="database",
                client_ip=connection.client_ip,
                success=False,
                details={"filename": filename, "error": result['message']},
            )
            return create_api_response(
                success=False,
                data=result,
                message=result["message"]
            )
            
    except Exception as e:
        logger.error(f"Unexpected error deleting backup: {e}")
        log_action(
            actor=actor,
            action="delete_backup",
            scope="database",
            client_ip=connection.client_ip,
            success=False,
            details={"filename": filename, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting backup"
        )


@router.get("/health", response_model=Dict[str, Any])
async def get_backup_health(current_user: dict = Depends(get_current_admin_user)):
    """
    Get backup service health status
    
    Args:
        current_user: Current authenticated admin user
        
    Returns:
        Standardized API response with backup service health information
    """
    start_time = time.time()
    
    try:
        backup_service = get_backup_service()
        
        # Basic health check - list backups to verify service is working
        backups = backup_service.list_backups()
        backup_count = len(backups)
        
        # Check backup directory accessibility
        import os
        backup_dir_exists = os.path.exists(backup_service.backup_dir)
        backup_dir_writable = os.access(backup_service.backup_dir, os.W_OK)
        
        health_data = {
            "service_status": "operational",
            "backup_directory": {
                "path": backup_service.backup_dir,
                "exists": backup_dir_exists,
                "writable": backup_dir_writable
            },
            "database_config": {
                "server": backup_service.sql_server,
                "database": backup_service.database_name
            },
            "backup_count": backup_count,
            "last_check": datetime.now().isoformat()
        }
        
        is_healthy = backup_dir_exists and backup_dir_writable
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "backup_health_check")
        metadata.add_metadata("admin_user", current_user['username'])
        metadata.add_metadata("is_healthy", is_healthy)
        metadata.add_metadata("backup_count", backup_count)
        metadata.add_metadata("directory_accessible", backup_dir_exists and backup_dir_writable)
        
        if is_healthy:
            return ResponseFormatter.success(
                data=health_data,
                metadata=metadata,
                message="Backup service health check completed - Service is healthy"
            )
        else:
            return ResponseFormatter.service_unavailable(
                message="Backup service health check completed - Service is unhealthy",
                details="Backup directory is not accessible or writable",
                data=health_data,
                metadata=metadata
            )
        
    except Exception as e:
        logger.error(f"Error checking backup service health: {e}")
        return ResponseFormatter.server_error(
            message="Error checking backup service health",
            details=str(e)
        )
