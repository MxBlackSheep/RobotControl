"""
RobotControl Monitoring API
Real-time monitoring endpoints for system status, experiments, and WebSocket connections
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
import logging
import asyncio
import time

from backend.services.auth import get_current_user
from backend.services.monitoring import get_monitoring_service, websocket_endpoint
from backend.services.database import get_database_service
from backend.services.experiment_monitor import get_experiment_monitor
from backend.constants import HAMILTON_STATE_MAPPING

# Import standardized response formatter
from backend.api.response_formatter import (
    ResponseFormatter, 
    ResponseMetadata, 
    format_success, 
    format_error
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/status")
async def get_monitoring_status(current_user: dict = Depends(get_current_user)):
    """Get monitoring service status and statistics"""
    start_time = time.time()
    
    try:
        monitoring_service = get_monitoring_service()
        stats = monitoring_service.get_monitoring_stats()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "monitoring_status")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        
        return ResponseFormatter.success(data=stats, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving monitoring status",
            details=str(e)
        )

@router.get("/experiments")
async def get_current_experiments(current_user: dict = Depends(get_current_user)):
    """Get current experiment monitoring data using centralized experiment monitor"""
    start_time = time.time()
    
    try:
        # Get experiment data from centralized experiment monitor
        experiment_monitor = get_experiment_monitor()
        current_experiment = experiment_monitor.get_current_experiment()
        
        experiments = []
        if current_experiment:
            # Use centralized Hamilton state mapping for consistency
            raw_state = str(current_experiment.run_state.value)
            display_state = HAMILTON_STATE_MAPPING.get(raw_state, raw_state)
            
            experiments = [{
                "ExperimentID": current_experiment.run_guid,
                "MethodName": current_experiment.method_name,
                "PlateID": "N/A",  # Not available in experiment monitor
                "StartTime": current_experiment.start_time.isoformat() if current_experiment.start_time else None,
                "EndTime": current_experiment.end_time.isoformat() if current_experiment.end_time else None,
                "Status": display_state,
                "RawState": raw_state,
                "Progress": 100 if current_experiment.is_complete else (50 if current_experiment.is_running else 0),
                "IsNewlyCompleted": current_experiment.is_newly_completed,
                "StateChangeTime": current_experiment.state_change_time.isoformat() if current_experiment.state_change_time else None
            }]
        
        data = {
            "experiments": experiments,
            "count": len(experiments)
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_current_experiments")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("experiment_count", len(experiments))
        
        return ResponseFormatter.success(data=data, metadata=metadata)
        
    except Exception as e:
        logger.error(f"Error getting current experiments: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving experiment data",
            details=str(e)
        )

@router.get("/system-health")
async def get_system_health(current_user: dict = Depends(get_current_user)):
    """Get current system health metrics"""
    start_time = time.time()
    
    try:
        import psutil
        from datetime import datetime
        
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('C:' if psutil.WINDOWS else '/')
        
        # Get database status
        db_service = get_database_service()
        db_status = db_service.get_status()
        
        # Get monitoring service stats
        monitoring_service = get_monitoring_service()
        websocket_stats = monitoring_service.websocket_manager.get_connection_stats()
        
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2)
            },
            "database": {
                "is_connected": db_status.is_connected,
                "mode": db_status.mode,
                "database_name": db_status.database_name,
                "server_name": db_status.server_name,
                "error_message": db_status.error_message
            },
            "websockets": websocket_stats
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_system_health")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("cpu_percent", cpu_percent)
        metadata.add_metadata("memory_percent", memory.percent)
        
        return ResponseFormatter.success(
            data=health_data,
            metadata=metadata,
            message="System health retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving system health",
            details=str(e)
        )

@router.post("/start")
async def start_monitoring(current_user: dict = Depends(get_current_user)):
    """Start the monitoring service (admin only)"""
    start_time = time.time()
    
    try:
        if current_user.get("role") != "admin":
            return ResponseFormatter.forbidden(
                message="Admin access required",
                details="Only admin users can start monitoring service"
            )
        
        monitoring_service = get_monitoring_service()
        
        if monitoring_service.is_running:
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "start_monitoring")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("was_already_running", True)
            
            return ResponseFormatter.success(
                data={"status": "already_running"},
                metadata=metadata,
                message="Monitoring service is already running"
            )
        
        monitoring_service.start_monitoring()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "start_monitoring")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("service_started", True)
        
        return ResponseFormatter.success(
            data={"status": "started"},
            metadata=metadata,
            message="Monitoring service started successfully"
        )
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        return ResponseFormatter.server_error(
            message="Error starting monitoring service",
            details=str(e)
        )

@router.post("/stop")
async def stop_monitoring(current_user: dict = Depends(get_current_user)):
    """Stop the monitoring service (admin only)"""
    start_time = time.time()
    
    try:
        if current_user.get("role") != "admin":
            return ResponseFormatter.forbidden(
                message="Admin access required",
                details="Only admin users can stop monitoring service"
            )
        
        monitoring_service = get_monitoring_service()
        
        if not monitoring_service.is_running:
            metadata = ResponseMetadata()
            metadata.set_execution_time(start_time)
            metadata.add_metadata("operation", "stop_monitoring")
            metadata.add_metadata("user_id", current_user.get("user_id"))
            metadata.add_metadata("was_already_stopped", True)
            
            return ResponseFormatter.success(
                data={"status": "already_stopped"},
                metadata=metadata,
                message="Monitoring service is already stopped"
            )
        
        monitoring_service.stop_monitoring()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "stop_monitoring")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("service_stopped", True)
        
        return ResponseFormatter.success(
            data={"status": "stopped"},
            metadata=metadata,
            message="Monitoring service stopped successfully"
        )
        
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        return ResponseFormatter.server_error(
            message="Error stopping monitoring service",
            details=str(e)
        )

@router.get("/websocket-stats")
async def get_websocket_stats(current_user: dict = Depends(get_current_user)):
    """Get WebSocket connection statistics"""
    start_time = time.time()
    
    try:
        monitoring_service = get_monitoring_service()
        stats = monitoring_service.websocket_manager.get_connection_stats()
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "get_websocket_stats")
        metadata.add_metadata("user_id", current_user.get("user_id"))
        metadata.add_metadata("connection_count", stats.get("connection_count", 0))
        
        return ResponseFormatter.success(
            data=stats,
            metadata=metadata,
            message="WebSocket statistics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting WebSocket stats: {e}")
        return ResponseFormatter.server_error(
            message="Error retrieving WebSocket statistics",
            details=str(e)
        )

# WebSocket endpoints
@router.websocket("/ws")
async def websocket_general(websocket: WebSocket):
    """General WebSocket endpoint for real-time monitoring"""
    await websocket_endpoint(websocket, "general")

@router.websocket("/ws/{channel}")
async def websocket_channel(websocket: WebSocket, channel: str):
    """Channel-specific WebSocket endpoint for real-time monitoring"""
    await websocket_endpoint(websocket, channel)

@router.websocket("/ws/experiments")
async def websocket_experiments(websocket: WebSocket):
    """WebSocket endpoint specifically for experiment monitoring"""
    await websocket_endpoint(websocket, "experiments")

@router.websocket("/ws/system")
async def websocket_system(websocket: WebSocket):
    """WebSocket endpoint specifically for system health monitoring"""
    await websocket_endpoint(websocket, "system")

@router.websocket("/ws/database")
async def websocket_database(websocket: WebSocket):
    """WebSocket endpoint specifically for database performance monitoring"""
    await websocket_endpoint(websocket, "database")

# Health check endpoint
@router.get("/health")
async def monitoring_health_check():
    """Monitoring service health check (public endpoint)"""
    start_time = time.time()
    
    try:
        monitoring_service = get_monitoring_service()
        
        health_data = {
            "service": "RobotControl Monitoring API",
            "status": "healthy",
            "monitoring_running": monitoring_service.is_running,
            "websocket_connections": monitoring_service.websocket_manager.connection_count
        }
        
        # Create metadata
        metadata = ResponseMetadata()
        metadata.set_execution_time(start_time)
        metadata.add_metadata("operation", "health_check")
        metadata.add_metadata("service", "monitoring")
        
        return ResponseFormatter.success(
            data=health_data,
            metadata=metadata,
            message="Health check completed successfully"
        )
        
    except Exception as e:
        logger.error(f"Monitoring health check error: {e}")
        return ResponseFormatter.server_error(
            message="Health check failed",
            details=str(e)
        )