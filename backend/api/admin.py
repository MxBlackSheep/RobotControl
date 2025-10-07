"""
PyRobot Simplified Admin API
Basic admin endpoints for user management and system monitoring
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import os
import psutil
import time

from backend.services.auth import get_current_admin_user, AuthService
from backend.services.database import get_database_service

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/system/status")
async def get_system_status(current_user: dict = Depends(get_current_admin_user)):
    """Get basic system status information"""
    start_time = time.time()
    
    try:
        # Get database status
        db_service = get_database_service()
        db_status = db_service.get_status()
        
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('C:' if os.name == 'nt' else '/')
        
        # Get uptime
        boot_time = psutil.boot_time()
        uptime_seconds = datetime.now().timestamp() - boot_time
        uptime_hours = uptime_seconds / 3600
        
        system_data = {
            "database": {
                "is_connected": db_status.is_connected,
                "mode": db_status.mode,
                "database_name": db_status.database_name,
                "server_name": db_status.server_name,
                "last_check": db_status.last_check.isoformat(),
                "error_message": db_status.error_message
            },
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "uptime_hours": round(uptime_hours, 2)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_system_status")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("cpu_percent", cpu_percent)
        metadata.add_metadata("memory_percent", memory.percent)
        
        return ResponseFormatter.success(
            data=system_data,
            metadata=metadata,
            message="System status retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving system status",
            details=str(e)
        )

@router.get("/users")
async def get_users(current_user: dict = Depends(get_current_admin_user)):
    """Get list of system users"""
    start_time = time.time()
    
    try:
        auth_service = AuthService()
        users = auth_service.get_all_users()
        
        # Remove sensitive information
        safe_users = []
        for user in users:
            safe_users.append({
                "username": user["username"],
                "role": user["role"],
                "is_active": user.get("is_active", True),
                "last_login": user.get("last_login"),
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

@router.post("/users/{username}/toggle-active")
async def toggle_user_active(
    username: str, 
    current_user: dict = Depends(get_current_admin_user)
):
    """Toggle user active status"""
    start_time = time.time()
    
    try:
        # Prevent admin from deactivating themselves
        if username == current_user["username"]:
            return ResponseFormatter.bad_request(
                message="Cannot deactivate your own account",
                details="Self-deactivation is not allowed for security reasons"
            )
        
        auth_service = AuthService()
        success = auth_service.toggle_user_active(username)
        
        if not success:
            return ResponseFormatter.not_found(
                message="User not found",
                details=f"No user found with username '{username}'"
            )
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "toggle_user_active")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("target_user", username)
        
        return ResponseFormatter.success(
            data={"username": username, "action": "status_toggled"},
            metadata=metadata,
            message=f"User {username} status updated successfully"
        )
        
    except Exception as e:
        logger.error(f"Error toggling user active status: {e}")
        return ResponseFormatter.server_error(
            message="Error updating user status",
            details=str(e)
        )

@router.get("/database/performance")
async def get_database_performance(current_user: dict = Depends(get_current_admin_user)):
    """Get database performance statistics"""
    start_time = time.time()
    
    try:
        db_service = get_database_service()
        stats = db_service.get_performance_stats()
        
        performance_data = {
            "query_count": stats["query_count"],
            "total_execution_time_ms": stats["total_execution_time_ms"],
            "average_execution_time_ms": stats["average_execution_time_ms"],
            "cache_entries": stats["cache_entries"],
            "connection_pool_size": stats["connection_pool_size"],
            "connection_attempts": stats["connection_attempts"],
            "last_error": stats["last_error"]
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_database_performance")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("query_count", stats["query_count"])
        metadata.add_metadata("avg_execution_time_ms", stats["average_execution_time_ms"])
        
        return ResponseFormatter.success(
            data=performance_data,
            metadata=metadata,
            message="Database performance statistics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting database performance: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving database performance",
            details=str(e)
        )

@router.post("/database/clear-cache")
async def clear_database_cache(current_user: dict = Depends(get_current_admin_user)):
    """Clear database cache"""
    start_time = time.time()
    
    try:
        db_service = get_database_service()
        cleared_count = db_service.clear_cache()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "clear_database_cache")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("cleared_entries", cleared_count)
        
        return ResponseFormatter.success(
            data={"cleared_entries": cleared_count},
            metadata=metadata,
            message="Database cache cleared successfully"
        )
        
    except Exception as e:
        logger.error(f"Error clearing database cache: {e}")
        return ResponseFormatter.server_error(
            message="Error clearing database cache",
            details=str(e)
        )

@router.post("/database/health-check")
async def perform_database_health_check(current_user: dict = Depends(get_current_admin_user)):
    """Perform database health check"""
    start_time = time.time()
    
    try:
        db_service = get_database_service()
        is_healthy = db_service.perform_health_check()
        status_info = db_service.get_status()
        
        health_data = {
            "is_healthy": is_healthy,
            "database_status": {
                "is_connected": status_info.is_connected,
                "mode": status_info.mode,
                "database_name": status_info.database_name,
                "server_name": status_info.server_name,
                "error_message": status_info.error_message
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "database_health_check")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("is_healthy", is_healthy)
        metadata.add_metadata("database_mode", status_info.mode)
        
        return ResponseFormatter.success(
            data=health_data,
            metadata=metadata,
            message=f"Database health check completed - {'Healthy' if is_healthy else 'Unhealthy'}"
        )
        
    except Exception as e:
        logger.error(f"Error performing database health check: {e}")
        return ResponseFormatter.server_error(
            message="Error performing database health check",
            details=str(e)
        )