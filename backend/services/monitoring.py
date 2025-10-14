"""
RobotControl Monitoring Service

Real-time monitoring service that provides WebSocket-based updates for:
- Experiment status changes
- System health metrics  
- Database performance
- Camera status

Consolidates functionality from db_monitor.py and websocket.py into a simplified interface.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Set, List, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
import threading
import time

# Import project services
from backend.services.database import get_database_service
from backend.services.auth import get_auth_service
from backend.services.experiment_monitor import get_experiment_monitor
from backend.constants import HAMILTON_STATE_MAPPING

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Simplified WebSocket connection manager for real-time communication
    """
    
    def __init__(self):
        # Store active connections by channel
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Store connection metadata
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
        # Connection statistics
        self.connection_count: int = 0
        
    async def connect(self, websocket: WebSocket, channel: str = "general"):
        """Accept a WebSocket connection and add to channel"""
        try:
            await websocket.accept()
            
            # Initialize channel if not exists
            if channel not in self.active_connections:
                self.active_connections[channel] = set()
            
            # Add connection to channel
            self.active_connections[channel].add(websocket)
            
            # Store connection metadata
            self.connection_metadata[websocket] = {
                "channel": channel,
                "connected_at": datetime.now(),
                "last_ping": datetime.now()
            }
            
            self.connection_count += 1
            logger.info(f"WebSocket connected to channel '{channel}'. Total connections: {self.connection_count}")
            
            # Skip automatic welcome message to avoid timing issues
            # Let the client send the first message instead
            logger.info(f"WebSocket ready for messages in channel '{channel}'")
            
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection: {e}")
            
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        try:
            # Find and remove from channel
            metadata = self.connection_metadata.get(websocket)
            if metadata:
                channel = metadata["channel"]
                if channel in self.active_connections:
                    self.active_connections[channel].discard(websocket)
                    
                    # Remove empty channels
                    if not self.active_connections[channel]:
                        del self.active_connections[channel]
                
                # Remove metadata
                del self.connection_metadata[websocket]
                self.connection_count -= 1
                
                logger.info(f"WebSocket disconnected from channel '{channel}'. Total connections: {self.connection_count}")
                
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to a specific WebSocket"""
        try:
            # Check if websocket is still connected before sending
            if websocket.client_state.value == 1:  # WebSocketState.CONNECTED
                await websocket.send_text(json.dumps(message))
            else:
                logger.warning(f"Cannot send message: WebSocket is not in connected state (state: {websocket.client_state.value})")
                await self.disconnect(websocket)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
            await self.disconnect(websocket)
    
    async def broadcast_to_channel(self, message: Dict[str, Any], channel: str):
        """Broadcast message to all connections in a channel"""
        if channel not in self.active_connections:
            return
        
        # Copy the set to avoid modification during iteration
        connections = self.active_connections[channel].copy()
        disconnected = []
        
        for websocket in connections:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all active connections"""
        for channel in self.active_connections:
            await self.broadcast_to_channel(message, channel)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "total_connections": self.connection_count,
            "active_channels": list(self.active_connections.keys()),
            "channels": {
                channel: len(connections) 
                for channel, connections in self.active_connections.items()
            }
        }


class MonitoringService:
    """
    Simplified monitoring service that tracks system health and experiments
    
    Provides:
    - Real-time experiment status monitoring
    - System health tracking
    - Database performance monitoring
    - WebSocket-based real-time updates
    """
    
    def __init__(self):
        """Initialize the monitoring service"""
        self.websocket_manager = WebSocketManager()
        self.is_running = False
        self.monitor_thread = None
        self.monitor_interval = 5  # seconds
        
        # Cache for monitoring data
        self.last_experiment_data = []
        self.last_system_health = {}
        self.last_db_performance = {}
        
        logger.info("MonitoringService initialized")
    
    def start_monitoring(self):
        """Start the background monitoring thread"""
        if not self.is_running:
            self.is_running = True
            self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Monitoring service started")
    
    def stop_monitoring(self):
        """Stop the background monitoring thread"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Monitoring service stopped")
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.is_running:
            try:
                # Update monitoring data
                self._update_experiment_data()
                self._update_system_health()
                self._update_db_performance()
                
                # Broadcast updates via WebSocket (handled synchronously to avoid thread issues)
                # The actual broadcasting will happen when WebSocket connections request data
                
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.monitor_interval)
    
    def _update_experiment_data(self):
        """Update experiment monitoring data"""
        try:
            # Get current experiment from experiment monitor
            experiment_monitor = get_experiment_monitor()
            current_experiment = experiment_monitor.get_current_experiment()
            
            experiment_data = []
            if current_experiment:
                # Use centralized Hamilton state mapping for consistency
                raw_state = str(current_experiment.run_state.value)
                display_state = HAMILTON_STATE_MAPPING.get(raw_state, raw_state)
                
                experiment_data = [{
                    "ExperimentID": current_experiment.run_guid,
                    "MethodName": current_experiment.method_name,
                    "StartTime": current_experiment.start_time.isoformat() if current_experiment.start_time else None,
                    "EndTime": current_experiment.end_time.isoformat() if current_experiment.end_time else None,
                    "Status": display_state,
                    "RawState": raw_state,
                    "IsNewlyCompleted": current_experiment.is_newly_completed,
                    "StateChangeTime": current_experiment.state_change_time.isoformat() if current_experiment.state_change_time else None
                }]
            
            # Check for changes
            if experiment_data != self.last_experiment_data:
                self.last_experiment_data = experiment_data
                logger.debug(f"Experiment data updated: {len(experiment_data)} experiments")
                
        except Exception as e:
            logger.error(f"Error updating experiment data: {e}")
            # Use empty list as fallback
            self.last_experiment_data = []
    
    def _update_system_health(self):
        """Update system health metrics"""
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('C:' if hasattr(psutil, 'WINDOWS') and psutil.WINDOWS else '/')
            
            system_health = {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "connections": self.websocket_manager.get_connection_stats()
            }
            
            # Check for significant changes (>5% change or every minute)
            if (not self.last_system_health or 
                abs(system_health["cpu_percent"] - self.last_system_health.get("cpu_percent", 0)) > 5 or
                abs(system_health["memory_percent"] - self.last_system_health.get("memory_percent", 0)) > 5):
                
                self.last_system_health = system_health
                logger.debug(f"System health updated: CPU {system_health['cpu_percent']}%, Memory {system_health['memory_percent']}%")
                
        except Exception as e:
            logger.error(f"Error updating system health: {e}")
    
    def _update_db_performance(self):
        """Update database performance metrics"""
        try:
            db_service = get_database_service()
            db_performance = db_service.get_performance_stats()
            
            # Add database status
            db_status = db_service.get_status()
            db_performance.update({
                "timestamp": datetime.now().isoformat(),
                "is_connected": db_status.is_connected,
                "mode": db_status.mode,
                "database_name": db_status.database_name
            })
            
            self.last_db_performance = db_performance
            
        except Exception as e:
            logger.error(f"Error updating database performance: {e}")
    
    async def _broadcast_updates(self):
        """Broadcast monitoring updates via WebSocket"""
        try:
            # Broadcast experiment updates
            if self.last_experiment_data:
                await self.websocket_manager.broadcast_to_channel({
                    "type": "experiments_update",
                    "data": self.last_experiment_data,
                    "timestamp": datetime.now().isoformat()
                }, "experiments")
            
            # Broadcast system health updates
            if self.last_system_health:
                await self.websocket_manager.broadcast_to_channel({
                    "type": "system_health",
                    "data": self.last_system_health,
                    "timestamp": datetime.now().isoformat()
                }, "system")
            
            # Broadcast database performance updates
            if self.last_db_performance:
                await self.websocket_manager.broadcast_to_channel({
                    "type": "database_performance",
                    "data": self.last_db_performance,
                    "timestamp": datetime.now().isoformat()
                }, "database")
                
        except Exception as e:
            logger.error(f"Error broadcasting updates: {e}")
    
    # Public API methods
    
    async def connect_websocket(self, websocket: WebSocket, channel: str = "general"):
        """Connect a WebSocket to monitoring updates"""
        await self.websocket_manager.connect(websocket, channel)
    
    async def disconnect_websocket(self, websocket: WebSocket):
        """Disconnect a WebSocket"""
        await self.websocket_manager.disconnect(websocket)
    
    async def handle_websocket_message(self, websocket: WebSocket, data: dict):
        """Handle incoming WebSocket messages"""
        try:
            message_type = data.get("type")
            logger.info(f"WebSocket message received: {message_type}")
            
            if message_type == "ping":
                # Update last ping time
                if websocket in self.websocket_manager.connection_metadata:
                    self.websocket_manager.connection_metadata[websocket]["last_ping"] = datetime.now()
                
                # Send pong response
                await self.websocket_manager.send_personal_message({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }, websocket)
                logger.info("Sent pong response to WebSocket client")
            
            elif message_type == "subscribe":
                # Handle channel subscription
                channel = data.get("channel", "general")
                # Move websocket to new channel (implementation would be here)
                logger.info(f"WebSocket subscription request for channel: {channel}")
            
            elif message_type == "get_current_data":
                # Send current monitoring data
                logger.info("Sending current monitoring data to WebSocket client")
                await self.send_current_data(websocket)
                logger.info("Successfully sent current data to WebSocket client")
            
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
    
    async def send_current_data(self, websocket: WebSocket):
        """Send current monitoring data to a specific websocket"""
        try:
            current_data = {
                "type": "current_data",
                "data": {
                    "experiments": self.last_experiment_data,
                    "system_health": self.last_system_health,
                    "database_performance": self.last_db_performance
                },
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Preparing to send WebSocket data: {len(self.last_experiment_data) if self.last_experiment_data else 0} experiments, system_health={bool(self.last_system_health)}, db_performance={bool(self.last_db_performance)}")
            
            await self.websocket_manager.send_personal_message(current_data, websocket)
            logger.info("Current data sent successfully via WebSocket")
            
        except Exception as e:
            logger.error(f"Error sending current data: {e}", exc_info=True)
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get monitoring service statistics"""
        return {
            "is_running": self.is_running,
            "monitor_interval": self.monitor_interval,
            "websocket_stats": self.websocket_manager.get_connection_stats(),
            "last_update": {
                "experiments": len(self.last_experiment_data),
                "system_health_timestamp": self.last_system_health.get("timestamp"),
                "database_performance_timestamp": self.last_db_performance.get("timestamp")
            }
        }


import threading

# Global service instance
_monitoring_service = None
_monitoring_service_lock = threading.Lock()


def get_monitoring_service() -> MonitoringService:
    """Get singleton monitoring service instance"""
    global _monitoring_service
    if _monitoring_service is None:
        with _monitoring_service_lock:
            if _monitoring_service is None:
                _monitoring_service = MonitoringService()
                logger.info("MonitoringService singleton instance created")
    return _monitoring_service


# Convenience function for WebSocket management
async def websocket_endpoint(websocket: WebSocket, channel: str = "general"):
    """
    WebSocket endpoint handler for real-time monitoring
    
    Usage in FastAPI:
    @router.websocket("/ws/{channel}")
    async def websocket_monitoring(websocket: WebSocket, channel: str):
        await websocket_endpoint(websocket, channel)
    """
    monitoring_service = get_monitoring_service()
    
    # Ensure monitoring is started
    if not monitoring_service.is_running:
        monitoring_service.start_monitoring()
    
    await monitoring_service.connect_websocket(websocket, channel)
    
    try:
        logger.info(f"Starting WebSocket message loop for channel: {channel}")
        while True:
            # Receive messages from client
            logger.info("WebSocket waiting for client message...")
            data = await websocket.receive_text()
            logger.info(f"WebSocket received raw data: {data}")
            
            message = json.loads(data)
            logger.info(f"WebSocket parsed message: {message}")
            
            # Handle the message
            await monitoring_service.handle_websocket_message(websocket, message)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from channel: {channel}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        await monitoring_service.disconnect_websocket(websocket)


if __name__ == "__main__":
    # Example usage
    monitoring = get_monitoring_service()
    
    print("=== RobotControl Monitoring Service ===")
    
    # Start monitoring
    monitoring.start_monitoring()
    
    # Get stats
    stats = monitoring.get_monitoring_stats()
    print(f"Monitoring Stats: {stats}")
    
    # Stop monitoring
    monitoring.stop_monitoring()
    
    print("=== Monitoring Service Example Complete ===")
