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
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import time

from backend.services.auth import get_current_admin_user, get_current_user
from backend.services.backup import get_backup_service
from backend.api.dependencies import ConnectionContext, require_local_access, get_connection_context
from backend.utils.audit import log_action

# Import standardized response formatter
from backend.api.response_formatter import ResponseFormatter

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
    
    actor = current_user.get("username", "unknown")
    try:
        logger.info(f"Creating backup requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        # sqlcmd can run for BACKUP_TIMEOUT (300 s); a worker thread keeps the server answering.
        result = await run_in_threadpool(backup_service.create_backup, request.description)
        
        # Create metadata
        
        if result.success:
            logger.info(f"Backup created successfully: {result.filename}")
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
                message="Backup created successfully"
            )
        else:
            logger.warning(f"Backup creation failed: {result.message}")
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
    
    try:
        _ensure_backup_permission(current_user, connection)
        logger.info(f"Listing backups requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        backups = backup_service.list_backups()
        
        # Convert BackupInfo objects to dictionaries
        backup_data = [backup.to_dict() for backup in backups]
        
        logger.info(f"Found {len(backups)} backup files")
        
        # Create metadata
        
        return ResponseFormatter.success(
            data=backup_data,
            message=f"Found {len(backups)} backup files"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing backups: {e}")
        return ResponseFormatter.server_error(
            message="An unexpected error occurred while listing backups",
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
        _ensure_backup_permission(current_user, connection)
        logger.warning(f"Database restore from {restore_source} requested by user: {current_user['username']}")
        
        backup_service = get_backup_service()
        
        def restore():
            from backend.services.scheduling.scheduler_engine import get_scheduler_engine
            from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable
            try:
                with get_scheduler_engine().database_restore_guard():
                    return (backup_service.restore_backup(request.filename) if request.filename
                            else backup_service.restore_backup_from_path(request.file_path))
            except SafetyConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except StorageUnavailable:
                raise HTTPException(503, "Scheduler safety storage is unavailable.") from None

        result = await run_in_threadpool(restore)

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
            return ResponseFormatter.success(
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
            return ResponseFormatter.error(
                status_code=200,
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
        # Deletion waits for a running backup or restore; wait in a worker thread, not on the event loop.
        result = await run_in_threadpool(backup_service.delete_backup, filename)
        
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
            return ResponseFormatter.success(
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
            return ResponseFormatter.error(
                status_code=200,
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
