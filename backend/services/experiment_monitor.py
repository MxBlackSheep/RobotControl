"""
Experiment Monitor Service

Background service that monitors experiment state changes in the Hamilton Vector database.
Detects experiment completion events and triggers video archiving for the automatic
recording system. Includes graceful database failure handling and lazy connection management.
"""

import threading
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

from backend.config import AUTO_RECORDING_CONFIG
from backend.services.automatic_recording_types import (
    ExperimentState, ExperimentStateType
)
from backend.constants import HAMILTON_STATE_MAPPING

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ExperimentMonitorStats:
    """Statistics for experiment monitoring operations"""
    
    # Monitoring statistics
    total_checks_performed: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    experiments_detected: int = 0
    completions_detected: int = 0
    
    # Timing information
    monitor_start_time: Optional[datetime] = None
    last_check_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_error_time: Optional[datetime] = None
    
    # Error tracking
    consecutive_failures: int = 0
    error_messages: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_checks_performed": self.total_checks_performed,
            "successful_checks": self.successful_checks,
            "failed_checks": self.failed_checks,
            "experiments_detected": self.experiments_detected,
            "completions_detected": self.completions_detected,
            "monitor_start_time": self.monitor_start_time.isoformat() if self.monitor_start_time else None,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "consecutive_failures": self.consecutive_failures,
            "recent_errors": self.error_messages[-5:]  # Last 5 errors only
        }
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_checks_performed == 0:
            return 0.0
        return (self.successful_checks / self.total_checks_performed) * 100.0
    
    @property
    def is_healthy(self) -> bool:
        """Check if monitor is in healthy state"""
        return (
            self.consecutive_failures < 5 and  # Less than 5 consecutive failures
            self.success_rate >= 70.0          # At least 70% success rate
        )


class ExperimentMonitor:
    """
    Background service that monitors Hamilton Vector database for experiment state changes.
    
    Features:
    - Non-blocking background thread polling
    - Experiment state change detection with completion event handling
    - Graceful database failure handling with automatic retry
    - Configurable polling intervals and error recovery
    - Event callback system for experiment completion notifications
    """
    
    def __init__(self, check_interval_seconds: Optional[int] = None):
        """
        Initialize experiment monitor
        
        Args:
            check_interval_seconds: Seconds between database checks (uses config default if None)
        """
        # Configuration
        self.check_interval = check_interval_seconds or AUTO_RECORDING_CONFIG["experiment_check_interval_seconds"]
        
        # Monitoring state
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Experiment state tracking
        self.current_experiment: Optional[ExperimentState] = None
        self.experiment_history: Dict[str, ExperimentState] = {}  # run_guid -> ExperimentState
        
        # Event callbacks
        self.completion_callbacks: List[Callable[[ExperimentState], None]] = []
        
        # Statistics and health monitoring
        self.stats = ExperimentMonitorStats()
        
        # Thread safety
        self.monitor_lock = threading.Lock()
        
        logger.info(f"ExperimentMonitor initialized with {self.check_interval}s check interval")
    
    def start_monitoring(self):
        """Start the background experiment monitoring thread"""
        with self.monitor_lock:
            if self.is_running:
                logger.warning("Experiment monitor is already running")
                return
            
            logger.info("Starting experiment monitoring thread")
            
            # Reset stop event and stats
            self.stop_event.clear()
            self.stats = ExperimentMonitorStats(monitor_start_time=datetime.now())
            
            # Start monitoring thread
            self.monitor_thread = threading.Thread(
                target=self._monitoring_worker,
                name="ExperimentMonitor",
                daemon=True
            )
            self.is_running = True
            self.monitor_thread.start()
            
            logger.info("Experiment monitoring started successfully")
    
    def stop_monitoring(self):
        """Stop the background experiment monitoring thread"""
        with self.monitor_lock:
            if not self.is_running:
                logger.info("Experiment monitor is not running")
                return
            
            logger.info("Stopping experiment monitoring thread")
            
            # Signal stop and wait for thread to finish
            self.stop_event.set()
            self.is_running = False
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=10)  # Wait up to 10 seconds
                
                if self.monitor_thread.is_alive():
                    logger.warning("Monitor thread did not stop gracefully")
                else:
                    logger.info("Monitor thread stopped successfully")
            
            self.monitor_thread = None
            logger.info("Experiment monitoring stopped")
    
    def add_completion_callback(self, callback: Callable[[ExperimentState], None]):
        """
        Add a callback function to be called when an experiment completes
        
        Args:
            callback: Function that takes ExperimentState as parameter
        """
        self.completion_callbacks.append(callback)
        logger.debug(f"Added experiment completion callback: {callback.__name__}")
    
    def remove_completion_callback(self, callback: Callable[[ExperimentState], None]):
        """Remove a completion callback"""
        try:
            self.completion_callbacks.remove(callback)
            logger.debug(f"Removed experiment completion callback: {callback.__name__}")
        except ValueError:
            logger.warning(f"Callback {callback.__name__} not found in completion callbacks")
    
    def get_current_experiment(self) -> Optional[ExperimentState]:
        """Get the current experiment state (thread-safe)"""
        with self.monitor_lock:
            return self.current_experiment
    
    def get_monitor_stats(self) -> ExperimentMonitorStats:
        """Get monitoring statistics (thread-safe)"""
        with self.monitor_lock:
            return self.stats
    
    def _monitoring_worker(self):
        """Main monitoring loop running in background thread"""
        logger.info("Experiment monitor worker thread started")
        
        while not self.stop_event.is_set():
            try:
                # Perform experiment check
                self._check_experiment_state()
                
                # Wait for next check (with early exit on stop signal)
                if self.stop_event.wait(timeout=self.check_interval):
                    break  # Stop event was set during wait
                    
            except Exception as e:
                logger.error(f"Unexpected error in monitoring worker: {e}")
                # Continue monitoring despite errors
                time.sleep(min(self.check_interval, 10))  # Don't overwhelm on errors
        
        logger.info("Experiment monitor worker thread finished")
    
    def _check_experiment_state(self):
        """Check current experiment state and detect changes"""
        check_start_time = datetime.now()
        
        try:
            # Update check statistics
            with self.monitor_lock:
                self.stats.total_checks_performed += 1
                self.stats.last_check_time = check_start_time
            
            # Query latest experiment from database
            experiment_data = self._query_latest_experiment()
            
            if experiment_data is None:
                # Database unavailable or no experiments - not an error
                logger.debug("No experiment data available from database")
                return
            
            # Create ExperimentState from database data
            new_experiment = self._create_experiment_state(experiment_data)
            
            # Check for state changes
            state_changed = False
            completion_detected = False
            
            with self.monitor_lock:
                if self.current_experiment is None:
                    # First experiment detected
                    logger.info(f"First experiment detected: {new_experiment.method_name} ({new_experiment.run_state.value})")
                    state_changed = True
                    self.stats.experiments_detected += 1
                    
                elif self.current_experiment.run_guid != new_experiment.run_guid:
                    # New experiment started
                    logger.info(f"New experiment detected: {new_experiment.method_name} "
                               f"(was: {self.current_experiment.method_name})")
                    state_changed = True
                    self.stats.experiments_detected += 1
                    
                elif self.current_experiment.run_state != new_experiment.run_state:
                    # Same experiment, state changed
                    logger.info(f"Experiment state changed: {new_experiment.method_name} "
                               f"{self.current_experiment.run_state.value} -> {new_experiment.run_state.value}")
                    new_experiment.previous_state = self.current_experiment.run_state
                    new_experiment.state_change_time = check_start_time
                    state_changed = True
                    
                    # Check for completion (both COMPLETE and ABORTED states indicate experiment ended)
                    if (new_experiment.run_state in [ExperimentStateType.COMPLETE, ExperimentStateType.ABORTED] and 
                        self.current_experiment.run_state not in [ExperimentStateType.COMPLETE, ExperimentStateType.ABORTED]):
                        completion_detected = True
                        new_experiment.is_newly_completed = True
                        self.stats.completions_detected += 1
                        logger.info(f"Experiment completion detected: {new_experiment.method_name} (state: {new_experiment.run_state.value})")
                
                # Update current experiment if changed
                if state_changed:
                    self.current_experiment = new_experiment
                    self.experiment_history[new_experiment.run_guid] = new_experiment
                
                # Update success statistics
                self.stats.successful_checks += 1
                self.stats.last_success_time = check_start_time
                self.stats.consecutive_failures = 0
            
            # Fire completion callbacks (outside of lock to prevent deadlock)
            if completion_detected:
                self._fire_completion_callbacks(new_experiment)
            
            logger.debug(f"Experiment check completed successfully - State: {new_experiment.run_state.value}")
            
        except Exception as e:
            # Handle check failure
            with self.monitor_lock:
                self.stats.failed_checks += 1
                self.stats.last_error_time = check_start_time
                self.stats.consecutive_failures += 1
                
                error_msg = f"Experiment check failed: {e}"
                self.stats.error_messages.append(error_msg)
                
                # Keep only last 10 error messages
                if len(self.stats.error_messages) > 10:
                    self.stats.error_messages = self.stats.error_messages[-10:]
            
            logger.warning(f"Failed to check experiment state: {e}")
    
    def _query_latest_experiment(self) -> Optional[Dict[str, Any]]:
        """
        Query the latest experiment from Hamilton Vector database
        
        Returns:
            Dictionary with experiment data or None if unavailable
        """
        try:
            # Lazy-load database service (graceful degradation if unavailable)
            from backend.services.database import get_database_service
            
            db_service = get_database_service()
            
            # Query latest experiment (same as experiments API)
            query = """
                SELECT TOP 1 RunGUID, MethodName, StartTime, EndTime, RunState
                FROM HamiltonVectorDB.dbo.HxRun
                ORDER BY StartTime DESC
            """
            
            result = db_service.execute_query(query)
            
            if result.get("error"):
                logger.debug(f"Database query failed: {result['error']}")
                return None
            
            if result.get("rows") and len(result["rows"]) > 0:
                row = result["rows"][0]
                return {
                    "run_guid": row.get("RunGUID"),
                    "method_name": row.get("MethodName"),
                    "start_time": row.get("StartTime"),
                    "end_time": row.get("EndTime"),
                    "run_state": row.get("RunState")
                }
            
            return None  # No experiments found
            
        except ImportError:
            logger.debug("Database service not available")
            return None
        except Exception as e:
            logger.debug(f"Error querying latest experiment: {e}")
            return None
    
    def _create_experiment_state(self, experiment_data: Dict[str, Any]) -> ExperimentState:
        """
        Create ExperimentState object from database query result
        
        Args:
            experiment_data: Raw experiment data from database query
            
        Returns:
            ExperimentState object
        """
        # Parse run state - Hamilton VENUS uses numeric codes
        run_state_raw = experiment_data.get("run_state", "Unknown")
        
        # Map Hamilton VENUS numeric run states to our enum values using centralized mapping
        run_state_str = str(run_state_raw)
        if run_state_str in HAMILTON_STATE_MAPPING:
            state_value = HAMILTON_STATE_MAPPING[run_state_str]
            # Convert string to enum
            run_state = getattr(ExperimentStateType, state_value.upper(), ExperimentStateType.UNKNOWN)
            logger.debug(f"Mapped Hamilton run state '{run_state_str}' to {run_state.value}")
        else:
            logger.warning(f"Unknown Hamilton run state '{run_state_str}', using UNKNOWN")
            run_state = ExperimentStateType.UNKNOWN
        
        # Parse datetime fields
        start_time = None
        end_time = None
        
        try:
            if experiment_data.get("start_time"):
                if isinstance(experiment_data["start_time"], str):
                    start_time = datetime.fromisoformat(experiment_data["start_time"].replace('Z', '+00:00'))
                else:
                    start_time = experiment_data["start_time"]  # Already datetime object
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse start_time: {e}")
        
        try:
            if experiment_data.get("end_time"):
                if isinstance(experiment_data["end_time"], str):
                    end_time = datetime.fromisoformat(experiment_data["end_time"].replace('Z', '+00:00'))
                else:
                    end_time = experiment_data["end_time"]  # Already datetime object
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse end_time: {e}")
        
        return ExperimentState(
            run_guid=str(experiment_data.get("run_guid", "")),
            method_name=str(experiment_data.get("method_name", "Unknown")),
            run_state=run_state,
            start_time=start_time,
            end_time=end_time
        )
    
    def _fire_completion_callbacks(self, completed_experiment: ExperimentState):
        """
        Fire all registered completion callbacks for a completed experiment
        
        Args:
            completed_experiment: The experiment that just completed
        """
        logger.info(f"Firing completion callbacks for experiment: {completed_experiment.method_name}")
        
        for callback in self.completion_callbacks:
            try:
                callback(completed_experiment)
                logger.debug(f"Completion callback {callback.__name__} executed successfully")
            except Exception as e:
                logger.error(f"Error in completion callback {callback.__name__}: {e}")
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is currently active"""
        return self.is_running
    
    def get_experiment_history(self, limit: int = 10) -> List[ExperimentState]:
        """
        Get recent experiment history
        
        Args:
            limit: Maximum number of experiments to return
            
        Returns:
            List of recent experiments, sorted by start time (newest first)
        """
        with self.monitor_lock:
            experiments = list(self.experiment_history.values())
            
        # Sort by start time (newest first)
        experiments.sort(
            key=lambda exp: exp.start_time or datetime.min,
            reverse=True
        )
        
        return experiments[:limit]


# Global instance management
_experiment_monitor = None
_monitor_lock = threading.Lock()


def get_experiment_monitor() -> ExperimentMonitor:
    """Get the global experiment monitor instance (singleton pattern)"""
    global _experiment_monitor
    if _experiment_monitor is None:
        with _monitor_lock:
            if _experiment_monitor is None:
                _experiment_monitor = ExperimentMonitor()
    return _experiment_monitor