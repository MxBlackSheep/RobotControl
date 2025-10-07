"""
Automatic Recording Service Data Types

Data models and type definitions for the automatic camera recording feature.
Provides type safety and clear data contracts for automation components.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class AutomationState(Enum):
    """Automation service states"""
    STOPPED = "stopped"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    ERROR = "error"


class ExperimentStateType(Enum):
    """Experiment execution states"""
    UNKNOWN = "Unknown"
    RUNNING = "Running"
    COMPLETE = "Complete"
    ABORTED = "Aborted" 
    ERROR = "Error"


@dataclass
class AutomationStatus:
    """Current status of the automatic recording service"""
    
    # Core automation state
    is_active: bool                           # Whether automation is currently active
    state: AutomationState                    # Current automation state
    recording_camera_id: Optional[int] = None # Camera ID being used for recording
    
    # Configuration
    startup_delay_seconds: int = 20           # Configured startup delay
    rolling_clips_limit: int = 120           # Maximum rolling clips maintained
    experiment_folders_limit: int = 20        # Maximum experiment folders kept
    archive_duration_minutes: int = 15        # Minutes archived per experiment
    
    # Runtime statistics
    last_experiment_check: Optional[datetime] = None  # Last experiment state check
    rolling_clips_count: int = 0             # Current number of rolling clips
    experiment_folders_count: int = 0        # Current number of experiment folders
    total_experiments_archived: int = 0      # Total experiments archived since startup
    
    # Error handling
    error_message: Optional[str] = None       # Last error encountered
    error_count: int = 0                     # Number of errors since startup
    last_error_time: Optional[datetime] = None  # When last error occurred
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "is_active": self.is_active,
            "state": self.state.value,
            "recording_camera_id": self.recording_camera_id,
            "startup_delay_seconds": self.startup_delay_seconds,
            "rolling_clips_limit": self.rolling_clips_limit,
            "experiment_folders_limit": self.experiment_folders_limit,
            "archive_duration_minutes": self.archive_duration_minutes,
            "last_experiment_check": self.last_experiment_check.isoformat() if self.last_experiment_check else None,
            "rolling_clips_count": self.rolling_clips_count,
            "experiment_folders_count": self.experiment_folders_count,
            "total_experiments_archived": self.total_experiments_archived,
            "error_message": self.error_message,
            "error_count": self.error_count,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None
        }


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
    is_newly_completed: bool = False         # Whether completion was newly detected
    previous_state: Optional[ExperimentStateType] = None  # Previous state for change detection
    state_change_time: Optional[datetime] = None  # When state last changed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "run_guid": self.run_guid,
            "method_name": self.method_name,
            "run_state": self.run_state.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "is_newly_completed": self.is_newly_completed,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "state_change_time": self.state_change_time.isoformat() if self.state_change_time else None
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
    def duration_minutes(self) -> Optional[float]:
        """Calculate experiment duration in minutes (if both start and end times available)"""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() / 60
        return None


@dataclass
class ArchiveResult:
    """Result of experiment video archiving operation"""
    
    # Operation outcome
    success: bool                            # Whether archiving succeeded
    archive_path: str = ""                   # Path to created archive folder
    
    # Archive statistics
    clips_archived: int = 0                  # Number of clips successfully archived
    archive_size_bytes: int = 0              # Total size of archived content
    clips_skipped: int = 0                   # Number of clips skipped (duplicates, errors)
    
    # Timing information
    archive_start_time: Optional[datetime] = None  # When archiving started
    archive_duration_seconds: float = 0.0   # How long archiving took
    
    # Error handling
    error_message: Optional[str] = None      # Error details if archiving failed
    warnings: List[str] = field(default_factory=list)  # Non-fatal warnings during archiving
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "success": self.success,
            "archive_path": self.archive_path,
            "clips_archived": self.clips_archived,
            "archive_size_bytes": self.archive_size_bytes,
            "clips_skipped": self.clips_skipped,
            "archive_start_time": self.archive_start_time.isoformat() if self.archive_start_time else None,
            "archive_duration_seconds": self.archive_duration_seconds,
            "error_message": self.error_message,
            "warnings": self.warnings
        }
    
    @property
    def archive_size_mb(self) -> float:
        """Get archive size in megabytes"""
        return self.archive_size_bytes / (1024 * 1024)
    
    @property
    def is_successful_with_content(self) -> bool:
        """Check if archiving was successful and produced content"""
        return self.success and self.clips_archived > 0


@dataclass
class StorageCleanupResult:
    """Result of storage cleanup operations"""
    
    # Rolling clips cleanup
    rolling_clips_removed: int = 0           # Number of old rolling clips removed
    rolling_clips_errors: List[str] = field(default_factory=list)  # Errors removing rolling clips
    
    # Experiment folders cleanup
    experiment_folders_removed: int = 0      # Number of old experiment folders removed
    experiment_folders_errors: List[str] = field(default_factory=list)  # Errors removing folders
    
    # Storage statistics
    storage_freed_bytes: int = 0             # Total storage freed by cleanup
    cleanup_duration_seconds: float = 0.0   # How long cleanup took
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "rolling_clips_removed": self.rolling_clips_removed,
            "rolling_clips_errors": self.rolling_clips_errors,
            "experiment_folders_removed": self.experiment_folders_removed,
            "experiment_folders_errors": self.experiment_folders_errors,
            "storage_freed_bytes": self.storage_freed_bytes,
            "storage_freed_mb": round(self.storage_freed_bytes / (1024 * 1024), 2),
            "cleanup_duration_seconds": self.cleanup_duration_seconds
        }
    
    @property
    def total_items_removed(self) -> int:
        """Total number of items removed across all cleanup operations"""
        return self.rolling_clips_removed + self.experiment_folders_removed
    
    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred during cleanup"""
        return len(self.rolling_clips_errors) > 0 or len(self.experiment_folders_errors) > 0


# Compatibility types for existing code (re-export from auth service)
try:
    from backend.services.auth import User as UserModel
except ImportError:
    # Fallback if auth service not available
    @dataclass
    class UserModel:
        user_id: str
        username: str
        role: str
        is_active: bool = True


@dataclass
class ApiResponse:
    """Standard API response format"""
    success: bool
    message: str = ""
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        response = {
            "success": self.success,
            "message": self.message
        }
        
        if self.data is not None:
            response["data"] = self.data
            
        if self.metadata is not None:
            response["metadata"] = self.metadata
            
        return response


# Additional constants for shared compatibility
try:
    from backend.services.camera import CameraRecordingModel
except ImportError:
    # Fallback camera recording model
    @dataclass
    class CameraRecordingModel:
        camera_id: int
        is_recording: bool
        recording_start_time: Optional[datetime] = None