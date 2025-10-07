"""
PyRobot Backend Types
Consolidated type definitions for camera service and API responses
"""

from typing import Optional, Any, Dict, List, Union
from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class UserModel:
    """User model for API authentication"""
    user_id: str
    username: str
    role: str
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active
        }


@dataclass
class ApiResponse:
    """Standardized API response format"""
    success: bool
    message: str
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        response = {
            "success": self.success,
            "message": self.message
        }
        if self.data is not None:
            response["data"] = self.data
        if self.metadata is not None:
            response["metadata"] = self.metadata
        return response


@dataclass 
class CameraRecordingModel:
    """Camera recording model"""
    camera_id: int
    filename: str
    timestamp: datetime
    duration_seconds: int
    file_size_bytes: int
    recording_type: str  # 'rolling', 'experiment', 'manual'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "filename": self.filename,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "file_size_bytes": self.file_size_bytes,
            "recording_type": self.recording_type
        }


@dataclass
class RetryConfig:
    """Configuration for experiment execution retry behavior"""
    max_retries: int = 5
    retry_delay_minutes: int = 2
    backoff_strategy: str = "linear"  # 'linear' or 'exponential'
    abort_after_hours: int = 24
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "retry_delay_minutes": self.retry_delay_minutes,
            "backoff_strategy": self.backoff_strategy,
            "abort_after_hours": self.abort_after_hours
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryConfig':
        """Create RetryConfig from dictionary data"""
        return cls(
            max_retries=data.get("max_retries", 5),
            retry_delay_minutes=data.get("retry_delay_minutes", 2),
            backoff_strategy=data.get("backoff_strategy", "linear"),
            abort_after_hours=data.get("abort_after_hours", 24)
        )


@dataclass
class ScheduledExperiment:
    """Model for scheduled experiment configuration"""
    schedule_id: str
    experiment_name: str
    experiment_path: str
    schedule_type: str  # 'interval', 'once', 'cron'
    interval_hours: Optional[int] = None  # 6, 8, 24 for interval schedules
    start_time: Optional[datetime] = None  # Next execution time
    estimated_duration: int = 60  # Duration in minutes
    created_by: str = "system"
    is_active: bool = True
    retry_config: Optional[RetryConfig] = None
    prerequisites: List[str] = None  # Database flags to set before execution
    failed_execution_count: int = 0  # Track failed executions for retry limits
    recovery_required: bool = False
    recovery_note: Optional[str] = None
    recovery_marked_at: Optional[datetime] = None
    recovery_marked_by: Optional[str] = None
    recovery_resolved_at: Optional[datetime] = None
    recovery_resolved_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize default values after creation"""
        if self.prerequisites is None:
            self.prerequisites = []
        if self.retry_config is None:
            self.retry_config = RetryConfig()
        if not self.schedule_id:
            self.schedule_id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "experiment_name": self.experiment_name,
            "experiment_path": self.experiment_path,
            "schedule_type": self.schedule_type,
            "interval_hours": self.interval_hours,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "estimated_duration": self.estimated_duration,
            "created_by": self.created_by,
            "is_active": self.is_active,
            "retry_config": self.retry_config.to_dict() if self.retry_config else None,
            "prerequisites": self.prerequisites,
            "failed_execution_count": self.failed_execution_count,
            "recovery_required": self.recovery_required,
            "recovery_note": self.recovery_note,
            "recovery_marked_at": self.recovery_marked_at.isoformat() if self.recovery_marked_at else None,
            "recovery_marked_by": self.recovery_marked_by,
            "recovery_resolved_at": self.recovery_resolved_at.isoformat() if self.recovery_resolved_at else None,
            "recovery_resolved_by": self.recovery_resolved_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledExperiment':
        """Create ScheduledExperiment from dictionary data"""
        # Parse datetime fields (ensure timezone-naive for consistent comparison)
        start_time = None
        if data.get("start_time"):
            start_time_str = data["start_time"].replace('Z', '').replace('+00:00', '')
            start_time = datetime.fromisoformat(start_time_str)
        
        created_at = None
        if data.get("created_at"):
            created_at_str = data["created_at"].replace('Z', '').replace('+00:00', '')
            created_at = datetime.fromisoformat(created_at_str)
            
        updated_at = None
        if data.get("updated_at"):
            updated_at_str = data["updated_at"].replace('Z', '').replace('+00:00', '')
            updated_at = datetime.fromisoformat(updated_at_str)
        
        recovery_marked_at = None
        if data.get("recovery_marked_at"):
            marked_str = data["recovery_marked_at"].replace('Z', '').replace('+00:00', '')
            recovery_marked_at = datetime.fromisoformat(marked_str)

        recovery_resolved_at = None
        if data.get("recovery_resolved_at"):
            resolved_str = data["recovery_resolved_at"].replace('Z', '').replace('+00:00', '')
            recovery_resolved_at = datetime.fromisoformat(resolved_str)

        # Parse retry config
        retry_config = None
        if data.get("retry_config"):
            retry_config = RetryConfig.from_dict(data["retry_config"])
        
        return cls(
            schedule_id=data.get("schedule_id", str(uuid.uuid4())),
            experiment_name=data["experiment_name"],
            experiment_path=data["experiment_path"],
            schedule_type=data["schedule_type"],
            interval_hours=data.get("interval_hours"),
            start_time=start_time,
            estimated_duration=data.get("estimated_duration", 60),
            created_by=data.get("created_by", "system"),
            is_active=data.get("is_active", True),
            retry_config=retry_config,
            prerequisites=data.get("prerequisites", []),
            failed_execution_count=data.get("failed_execution_count", 0),
            recovery_required=data.get("recovery_required", False),
            recovery_note=data.get("recovery_note"),
            recovery_marked_at=recovery_marked_at,
            recovery_marked_by=data.get("recovery_marked_by"),
            recovery_resolved_at=recovery_resolved_at,
            recovery_resolved_by=data.get("recovery_resolved_by"),
            created_at=created_at,
            updated_at=updated_at
        )


@dataclass
class ManualRecoveryState:
    """Global manual recovery state for the scheduler."""
    active: bool = False
    note: Optional[str] = None
    schedule_id: Optional[str] = None
    experiment_name: Optional[str] = None
    triggered_by: Optional[str] = None
    triggered_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "note": self.note,
            "schedule_id": self.schedule_id,
            "experiment_name": self.experiment_name,
            "triggered_by": self.triggered_by,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManualRecoveryState":
        def parse_ts(value):
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            value = str(value).replace('Z', '').replace('+00:00', '')
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return cls(
            active=bool(data.get("active", False)),
            note=data.get("note"),
            schedule_id=data.get("schedule_id"),
            experiment_name=data.get("experiment_name"),
            triggered_by=data.get("triggered_by"),
            triggered_at=parse_ts(data.get("triggered_at")),
            resolved_by=data.get("resolved_by"),
            resolved_at=parse_ts(data.get("resolved_at")),
        )


@dataclass
class JobExecution:
    """Model for tracking individual job execution instances"""
    execution_id: str
    schedule_id: str
    status: str  # 'pending', 'running', 'completed', 'failed', 'retrying'
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    hamilton_command: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize default values after creation"""
        if not self.execution_id:
            self.execution_id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "schedule_id": self.schedule_id,
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_minutes": self.duration_minutes,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "hamilton_command": self.hamilton_command,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobExecution':
        """Create JobExecution from dictionary data"""
        # Parse datetime fields (ensure timezone-naive)
        start_time = None
        if data.get("start_time"):
            start_time_str = data["start_time"].replace('Z', '').replace('+00:00', '')
            start_time = datetime.fromisoformat(start_time_str)
        
        end_time = None
        if data.get("end_time"):
            end_time_str = data["end_time"].replace('Z', '').replace('+00:00', '')
            end_time = datetime.fromisoformat(end_time_str)
            
        created_at = None
        if data.get("created_at"):
            created_at_str = data["created_at"].replace('Z', '').replace('+00:00', '')
            created_at = datetime.fromisoformat(created_at_str)
        
        return cls(
            execution_id=data.get("execution_id", str(uuid.uuid4())),
            schedule_id=data["schedule_id"],
            status=data["status"],
            start_time=start_time,
            end_time=end_time,
            duration_minutes=data.get("duration_minutes"),
            retry_count=data.get("retry_count", 0),
            error_message=data.get("error_message"),
            hamilton_command=data.get("hamilton_command"),
            created_at=created_at
        )


@dataclass
class CalendarEvent:
    """Frontend calendar event model for UI display"""
    id: str
    title: str
    start: datetime
    end: datetime
    status: str  # 'scheduled', 'running', 'completed', 'conflict'
    experiment_type: str
    duration_estimate: int  # Minutes
    can_edit: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "status": self.status,
            "experiment_type": self.experiment_type,
            "duration_estimate": self.duration_estimate,
            "can_edit": self.can_edit
        }
    
    @classmethod
    def from_scheduled_experiment(cls, scheduled_exp: ScheduledExperiment, 
                                  execution: Optional[JobExecution] = None) -> 'CalendarEvent':
        """Create CalendarEvent from ScheduledExperiment"""
        start_time = scheduled_exp.start_time or datetime.now()
        end_time = start_time
        if scheduled_exp.estimated_duration:
            from datetime import timedelta
            end_time = start_time + timedelta(minutes=scheduled_exp.estimated_duration)
        
        # Determine status from execution if available
        status = "scheduled"
        if execution:
            if execution.status == "running":
                status = "running"
            elif execution.status == "completed":
                status = "completed"
            elif execution.status == "failed":
                status = "conflict"  # Show failed as conflict for user attention
        
        return cls(
            id=scheduled_exp.schedule_id,
            title=scheduled_exp.experiment_name,
            start=start_time,
            end=end_time,
            status=status,
            experiment_type=scheduled_exp.experiment_name,
            duration_estimate=scheduled_exp.estimated_duration,
            can_edit=scheduled_exp.is_active
        )