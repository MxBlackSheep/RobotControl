"""
RobotControl Monitoring Service

Background monitoring service that caches readings for:
- Experiment status changes
- System health metrics  
- Database performance
- Camera status

"""

import logging
from datetime import datetime
from typing import Dict, Any
import threading
import time

# Import project services
from backend.services.database import get_database_service
from backend.services.experiment_monitor import get_experiment_monitor
from backend.constants import HAMILTON_STATE_MAPPING

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    Simplified monitoring service that tracks system health and experiments
    
    Provides:
    - Real-time experiment status monitoring
    - System health tracking
    - Database performance monitoring
    """
    
    def __init__(self):
        """Initialize the monitoring service"""
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
                    "RawState": current_experiment.raw_run_state or raw_state,
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
            from backend.services.health_sampler import health_sampler
            system_health = health_sampler.snapshot()

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
    
    # Public API methods
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get monitoring service statistics"""
        return {
            "is_running": self.is_running,
            "monitor_interval": self.monitor_interval,
            "last_update": {
                "experiments": len(self.last_experiment_data),
                "system_health_timestamp": self.last_system_health.get("timestamp"),
                "database_performance_timestamp": self.last_db_performance.get("timestamp")
            }
        }



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

