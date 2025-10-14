"""
System Configuration API

Web interface for managing centralized database configuration.
Allows administrators to update SQL server settings via the web UI.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import os
import time
from datetime import datetime

from backend.services.auth import get_current_admin_user
from backend.config import settings

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error
)

logger = logging.getLogger(__name__)
router = APIRouter()

class DatabaseConfig(BaseModel):
    """Database configuration model"""
    vm_sql_server: str
    vm_sql_user: str
    vm_sql_password: str
    local_backup_path: str
    sql_backup_path: str

class SystemStatus(BaseModel):
    """System status including current database connection info"""
    current_connection_mode: str
    current_server: str
    current_database: str
    connection_status: str
    backup_paths: Dict[str, str]

@router.get("/config/database", response_model=DatabaseConfig)
async def get_database_config(current_user: dict = Depends(get_current_admin_user)):
    """Get current database configuration"""
    start_time = time.time()
    
    try:
        config_data = DatabaseConfig(
            vm_sql_server=settings.VM_SQL_SERVER,
            vm_sql_user=settings.VM_SQL_USER,
            vm_sql_password=settings.VM_SQL_PASSWORD,
            local_backup_path=settings.LOCAL_BACKUP_PATH,
            sql_backup_path=settings.SQL_BACKUP_PATH
        )
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_database_config")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("server", settings.VM_SQL_SERVER)
        
        return ResponseFormatter.success(
            data=config_data.dict(),
            metadata=metadata,
            message="Database configuration retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting database config: {e}")
        return ResponseFormatter.server_error(
            message="Failed to retrieve database configuration",
            details=str(e)
        )

@router.post("/config/database")
async def update_database_config(
    config: DatabaseConfig, 
    current_user: dict = Depends(get_current_admin_user)
):
    """Update database configuration"""
    start_time = time.time()
    
    try:
        # Update the settings object
        settings.VM_SQL_SERVER = config.vm_sql_server
        settings.VM_SQL_USER = config.vm_sql_user  
        settings.VM_SQL_PASSWORD = config.vm_sql_password
        settings.LOCAL_BACKUP_PATH = config.local_backup_path
        settings.SQL_BACKUP_PATH = config.sql_backup_path
        
        # Persist changes to .env file for persistence across restarts
        env_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        env_content = f"""# RobotControl Backend Configuration
# Updated via web interface on {datetime.now().isoformat()}

VM_SQL_SERVER={config.vm_sql_server}
VM_SQL_USER={config.vm_sql_user}
VM_SQL_PASSWORD={config.vm_sql_password}
LOCAL_BACKUP_PATH={config.local_backup_path}
SQL_BACKUP_PATH={config.sql_backup_path}

PORT=8005
DEBUG=True
SECRET_KEY=robotcontrol-simplified-secret-key-2025
"""
        
        env_persisted = False
        try:
            with open(env_file_path, 'w') as f:
                f.write(env_content)
            logger.info(f"Configuration persisted to {env_file_path}")
            env_persisted = True
        except Exception as env_error:
            logger.warning(f"Could not persist to .env file: {env_error}")
            # Continue anyway - runtime settings are still updated
        
        logger.info(f"Database configuration updated by admin: {current_user.get('username', 'unknown')}")
        
        response_data = {
            "restart_required": True,
            "env_persisted": env_persisted,
            "updated_server": config.vm_sql_server,
            "updated_by": current_user.get('username', 'unknown')
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "update_database_config")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("new_server", config.vm_sql_server)
        metadata.add_metadata("env_persisted", env_persisted)
        
        return ResponseFormatter.success(
            data=response_data,
            metadata=metadata,
            message="Database configuration updated successfully. Please restart the backend to apply changes."
        )
        
    except Exception as e:
        logger.error(f"Error updating database config: {e}")
        return ResponseFormatter.server_error(
            message="Failed to update database configuration",
            details=str(e)
        )

@router.get("/config/status", response_model=SystemStatus)
async def get_system_config_status(current_user: dict = Depends(get_current_admin_user)):
    """Get current system status including active database connection"""
    start_time = time.time()
    
    try:
        # Get current connection info
        from backend.core.database_connection import db_connection_manager
        
        try:
            conn = db_connection_manager.get_connection(timeout=5)
            if conn:
                connection_status = "Connected"
                current_server = settings.VM_SQL_SERVER
                conn.close()
            else:
                connection_status = "Disconnected"
                current_server = "None"
        except Exception:
            connection_status = "Error"
            current_server = "Unknown"
        
        status_data = SystemStatus(
            current_connection_mode="centralized",
            current_server=current_server,
            current_database="EvoYeast",
            connection_status=connection_status,
            backup_paths={
                "local_path": settings.LOCAL_BACKUP_PATH,
                "sql_path": settings.SQL_BACKUP_PATH
            }
        )
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_system_config_status")
        metadata.add_metadata("admin_user", current_user.get("username"))
        metadata.add_metadata("connection_status", connection_status)
        metadata.add_metadata("current_server", current_server)
        
        return ResponseFormatter.success(
            data=status_data.dict(),
            metadata=metadata,
            message="System status retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return ResponseFormatter.server_error(
            message="Failed to retrieve system status",
            details=str(e)
        )

@router.post("/test-connection")
async def test_database_connection(current_user: dict = Depends(get_current_admin_user)):
    """Test database connection with current settings"""
    start_time = time.time()
    
    try:
        from backend.core.database_connection import db_connection_manager
        
        conn = db_connection_manager.get_connection(timeout=10)
        if conn:
            # Test with simple query
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            connection_data = {
                "server": settings.VM_SQL_SERVER,
                "sql_server_version": version[:100] + "..." if len(version) > 100 else version,
                "connection_test_result": "success"
            }
            
            # Create metadata
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "test_database_connection")
            metadata.add_metadata("admin_user", current_user.get("username"))
            metadata.add_metadata("connection_successful", True)
            metadata.add_metadata("server", settings.VM_SQL_SERVER)
            
            return ResponseFormatter.success(
                data=connection_data,
                metadata=metadata,
                message="Database connection test successful"
            )
        else:
            connection_data = {
                "server": settings.VM_SQL_SERVER,
                "connection_test_result": "failed",
                "error_reason": "unable to establish connection"
            }
            
            # Create metadata for failed connection
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "test_database_connection")
            metadata.add_metadata("admin_user", current_user.get("username"))
            metadata.add_metadata("connection_successful", False)
            metadata.add_metadata("server", settings.VM_SQL_SERVER)
            
            return ResponseFormatter.service_unavailable(
                message="Database connection test failed",
                details="Unable to establish connection to the database server",
                data=connection_data,
                metadata=metadata
            )
            
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        
        connection_data = {
            "server": settings.VM_SQL_SERVER,
            "connection_test_result": "error",
            "error_reason": str(e)
        }
        
        return ResponseFormatter.server_error(
            message="Database connection test encountered an error",
            details=str(e),
            data=connection_data
        )