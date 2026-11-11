"""
Experiment Monitor Service

Background service that monitors experiment state changes in the Hamilton Vector database.
Detects experiment completion events and triggers video archiving for the automatic
recording system. Includes graceful database failure handling and lazy connection management.
"""

from dataclasses import dataclass
from enum import Enum
import threading
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from backend.config import AUTO_RECORDING_CONFIG
from backend.constants import HAMILTON_STATE_MAPPING

from backend.utils.datetime import parse_iso_datetime_to_local

# Configure logging
logger = logging.getLogger(__name__)


class ExperimentStateType(Enum):
    """Experiment execution states"""
    UNKNOWN = "Unknown"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETE = "Complete"
    ABORTED = "Aborted"
    ERROR = "Error"


@dataclass
class ExperimentState:
    """Current state of an experiment from Hamilton Vector database"""

    # Core experiment identifiers
    run_guid: str                            # Unique experiment identifier
    method_name: str                         # Experiment method name
    run_state: ExperimentStateType           # Current execution state

    # Timing information
    start_time: Optional[datetime] = None    # Experiment start time
    end_time: Optional[datetime] = None      # Experiment completion time (if finished)

    # State change tracking
    raw_run_state: Optional[str] = None  # Original Hamilton SQL value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "run_guid": self.run_guid,
            "method_name": self.method_name,
            "run_state": self.run_state.value,
            "raw_run_state": self.raw_run_state,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    @property
    def is_complete(self) -> bool:
        """Check if experiment is in a completed state"""
        return self.run_state == ExperimentStateType.COMPLETE

    @property
    def is_running(self) -> bool:
        """Check if experiment is currently running"""
        return self.run_state == ExperimentStateType.RUNNING

    @property
    def is_in_progress(self) -> bool:
        """Running and paused methods both retain ownership of the robot."""
        return self.run_state in {ExperimentStateType.RUNNING, ExperimentStateType.PAUSED}

    @property
    def duration_minutes(self) -> Optional[float]:
        """Calculate experiment duration in minutes (if both start and end times available)"""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() / 60
        return None


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
    
    def __init__(self, check_interval_seconds: Optional[int] = None, *, on_complete: Callable[[ExperimentState], None]):
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
        
        # Event callbacks
        self.on_complete = on_complete
        
        self.last_check_time: Optional[datetime] = None
        
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
            
            # Reset the check time when monitoring restarts
            self.stop_event.clear()
            self.last_check_time = None
            
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
    
    def get_last_check_time(self) -> Optional[datetime]:
        """Get the last check time under the monitor lock."""
        with self.monitor_lock:
            return self.last_check_time
    
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
            # Record attempts even when the query fails.
            with self.monitor_lock:
                self.last_check_time = check_start_time
            
            # Query latest experiment from database
            experiment_data = self._query_latest_experiment()
            
            if experiment_data is None:
                # Database unavailable or no experiments - not an error
                logger.debug("No experiment data available from database")
                return
            
            # Create ExperimentState from database data
            new_experiment = self._create_experiment_state(experiment_data)
            
            with self.monitor_lock:
                previous = self.current_experiment
                completed = (
                    previous is not None
                    and previous.run_guid == new_experiment.run_guid
                    and previous.run_state not in (ExperimentStateType.COMPLETE, ExperimentStateType.ABORTED)
                    and new_experiment.run_state in (ExperimentStateType.COMPLETE, ExperimentStateType.ABORTED)
                )
                self.current_experiment = new_experiment
            if completed:
                self.on_complete(new_experiment)

        except Exception as e:
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
            
            result = query_latest_experiment(db_service)

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
        run_state = ExperimentStateType(HAMILTON_STATE_MAPPING.get(run_state_str, "Unknown"))
        if run_state == ExperimentStateType.UNKNOWN:
            logger.warning("Unknown Hamilton run state '%s', using UNKNOWN", run_state_str)

        # Parse datetime fields
        start_time = None
        end_time = None
        
        try:
            if experiment_data.get("start_time"):
                start_time = parse_iso_datetime_to_local(experiment_data["start_time"])
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse start_time: {e}")
        
        try:
            if experiment_data.get("end_time"):
                end_time = parse_iso_datetime_to_local(experiment_data["end_time"])
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse end_time: {e}")
        
        return ExperimentState(
            run_guid=str(experiment_data.get("run_guid", "")),
            method_name=str(experiment_data.get("method_name", "Unknown")),
            run_state=run_state,
            raw_run_state=run_state_str,
            start_time=start_time,
            end_time=end_time
        )
    

def query_latest_experiment(db_service):
    """Return the database result, keeping query failure distinct from no runs."""
    return db_service.execute_query("""
        SELECT TOP 1 RunGUID, MethodName, StartTime, EndTime, RunState
        FROM HamiltonVectorDB.dbo.HxRun
        ORDER BY StartTime DESC
    """)
