"""
Job Queue Manager with Conflict Detection

Manages experiment execution queue with intelligent conflict resolution.
Supports parallel execution and duration-based scheduling conflict detection.

Features:
- Queue management with priority and conflict resolution
- Duration-based conflict detection using experiment estimates
- Parallel execution support with resource management
- Retry logic and failure handling
- Real-time conflict analysis and resolution suggestions
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple, NamedTuple
from dataclasses import dataclass, field
from queue import Queue, PriorityQueue, Empty
from enum import Enum
from backend.models import ScheduledExperiment, JobExecution
from backend.services.scheduling.process_monitor import get_hamilton_process_monitor

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of scheduling conflicts"""
    TIME_OVERLAP = "time_overlap"
    RESOURCE_CONFLICT = "resource_conflict"
    HAMILTON_BUSY = "hamilton_busy"
    DEPENDENCY_CONFLICT = "dependency_conflict"


class JobPriority(Enum):
    """Job execution priorities"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0


@dataclass
class ConflictInfo:
    """Information about a scheduling conflict"""
    conflict_type: ConflictType
    conflicting_schedule_ids: List[str]
    message: str
    suggested_resolution: str
    alternative_times: List[datetime] = field(default_factory=list)
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class QueuedJob:
    """Job queued for execution with metadata"""
    experiment: ScheduledExperiment
    execution: JobExecution
    priority: JobPriority = JobPriority.NORMAL
    queued_time: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    last_attempt: Optional[datetime] = None
    conflicts: List[ConflictInfo] = field(default_factory=list)
    
    def __lt__(self, other):
        """Priority queue ordering"""
        return self.priority.value < other.priority.value


@dataclass
class ExecutionWindow:
    """Time window for experiment execution"""
    start_time: datetime
    end_time: datetime
    experiment_name: str
    schedule_id: str
    is_running: bool = False


class JobQueueManager:
    """Manages job execution queue with conflict detection and resolution"""
    
    def __init__(self, max_parallel_jobs: int = 1):
        """
        Initialize the job queue manager
        
        Args:
            max_parallel_jobs: Maximum number of parallel experiments
        """
        self.max_parallel_jobs = max_parallel_jobs
        self._job_queue = PriorityQueue()
        self._running_jobs: Dict[str, QueuedJob] = {}
        self._execution_windows: List[ExecutionWindow] = []
        self._conflict_threshold_minutes = 15  # Buffer time between experiments
        
        # Threading synchronization
        self._queue_lock = threading.RLock()
        self._windows_lock = threading.RLock()
        
        # Service dependencies
        self.process_monitor = get_hamilton_process_monitor()
        
        logger.info(f"Job queue manager initialized (max parallel jobs: {max_parallel_jobs})")

    def set_max_parallel_jobs(self, value: int):
        """Update the maximum number of parallel jobs."""
        with self._queue_lock:
            self.max_parallel_jobs = max(1, value)

    def reset(self):
        """Clear queued and running jobs."""
        with self._queue_lock:
            self._job_queue = PriorityQueue()
            self._running_jobs.clear()
        with self._windows_lock:
            self._execution_windows.clear()
    
    def enqueue_job(self, experiment: ScheduledExperiment, execution: JobExecution,
                   priority: JobPriority = JobPriority.NORMAL) -> bool:
        """
        Enqueue a job for execution with conflict detection
        
        Args:
            experiment: Scheduled experiment to execute
            execution: Job execution record
            priority: Job priority level
            
        Returns:
            bool: True if enqueued successfully, False if conflicts prevent queuing
        """
        try:
            # Create queued job
            job = QueuedJob(
                experiment=experiment,
                execution=execution,
                priority=priority
            )
            
            # Detect conflicts
            conflicts = self._detect_conflicts(experiment)
            job.conflicts = conflicts
            
            # Check if conflicts are blocking
            blocking_conflicts = [c for c in conflicts if c.severity in ["high", "critical"]]
            
            if blocking_conflicts and priority != JobPriority.CRITICAL:
                logger.warning(f"Blocking conflicts prevent queuing {experiment.experiment_name}")
                for conflict in blocking_conflicts:
                    logger.warning(f"  - {conflict.message}")
                return False
            
            # Add to queue
            with self._queue_lock:
                self._job_queue.put(job)
                
                # Update execution windows
                self._update_execution_windows()
            
            logger.info(f"Enqueued job: {experiment.experiment_name} (priority: {priority.name})")
            
            if conflicts:
                logger.info(f"  - {len(conflicts)} conflicts detected but job queued")
                for conflict in conflicts:
                    logger.info(f"    * {conflict.message}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error enqueuing job: {e}")
            return False
    
    def get_next_job(self) -> Optional[QueuedJob]:
        """
        Get the next job from the queue if execution is possible
        
        Returns:
            QueuedJob or None if no jobs available or conflicts prevent execution
        """
        try:
            with self._queue_lock:
                if self._job_queue.empty():
                    return None
                
                # Check if we can start more jobs
                if len(self._running_jobs) >= self.max_parallel_jobs:
                    return None
                
                # Get next job
                job = self._job_queue.get()
                
                # Re-check conflicts in case situation changed
                current_conflicts = self._detect_conflicts(job.experiment)
                job.conflicts = current_conflicts
                
                # Check Hamilton availability
                if not self._is_hamilton_available_for_job(job):
                    # Requeue job for later
                    self._job_queue.put(job)
                    return None
                
                # Check for blocking conflicts
                blocking_conflicts = [c for c in current_conflicts 
                                    if c.severity in ["high", "critical"]]
                
                if blocking_conflicts and job.priority != JobPriority.CRITICAL:
                    # Requeue job for later
                    self._job_queue.put(job)
                    return None
                
                return job
                
        except Empty:
            return None
        except Exception as e:
            logger.error(f"Error getting next job: {e}")
            return None
    
    def start_job_execution(self, job: QueuedJob) -> bool:
        """
        Mark a job as started and track its execution
        
        Args:
            job: Job that is starting execution
            
        Returns:
            bool: True if started successfully
        """
        try:
            with self._queue_lock:
                # Add to running jobs
                self._running_jobs[job.experiment.schedule_id] = job
                
                # Create execution window
                start_time = datetime.now()
                end_time = start_time + timedelta(minutes=job.experiment.estimated_duration)
                
                window = ExecutionWindow(
                    start_time=start_time,
                    end_time=end_time,
                    experiment_name=job.experiment.experiment_name,
                    schedule_id=job.experiment.schedule_id,
                    is_running=True
                )
                
                with self._windows_lock:
                    self._execution_windows.append(window)
                
                logger.info(f"Started job execution: {job.experiment.experiment_name}")
                return True
                
        except Exception as e:
            logger.error(f"Error starting job execution: {e}")
            return False
    
    def complete_job_execution(self, schedule_id: str, success: bool = True):
        """
        Mark a job as completed and clean up tracking
        
        Args:
            schedule_id: ID of the completed job
            success: Whether the job completed successfully
        """
        try:
            with self._queue_lock:
                if schedule_id in self._running_jobs:
                    job = self._running_jobs[schedule_id]
                    del self._running_jobs[schedule_id]
                    
                    status = "completed" if success else "failed"
                    logger.info(f"Job execution {status}: {job.experiment.experiment_name}")
                
                # Update execution windows
                with self._windows_lock:
                    self._execution_windows = [w for w in self._execution_windows 
                                             if w.schedule_id != schedule_id]
                
                # Update remaining windows
                self._update_execution_windows()
                
        except Exception as e:
            logger.error(f"Error completing job execution: {e}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue status information
        
        Returns:
            Dictionary with queue status details
        """
        try:
            with self._queue_lock:
                queue_size = self._job_queue.qsize()
                running_count = len(self._running_jobs)
                
                running_jobs = []
                for job in self._running_jobs.values():
                    running_jobs.append({
                        "schedule_id": job.experiment.schedule_id,
                        "experiment_name": job.experiment.experiment_name,
                        "priority": job.priority.name,
                        "queued_time": job.queued_time.isoformat(),
                        "retry_count": job.retry_count
                    })
                
                with self._windows_lock:
                    execution_windows = []
                    for window in self._execution_windows:
                        execution_windows.append({
                            "schedule_id": window.schedule_id,
                            "experiment_name": window.experiment_name,
                            "start_time": window.start_time.isoformat(),
                            "end_time": window.end_time.isoformat(),
                            "is_running": window.is_running
                        })
                
                return {
                    "queue_size": queue_size,
                    "running_jobs": running_count,
                    "max_parallel_jobs": self.max_parallel_jobs,
                    "capacity_available": running_count < self.max_parallel_jobs,
                    "running_job_details": running_jobs,
                    "execution_windows": execution_windows,
                    "hamilton_available": self.process_monitor.is_hamilton_running() == False
                }
                
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"error": str(e)}
    
    def detect_scheduling_conflicts(self, experiments: List[ScheduledExperiment]) -> Dict[str, List[ConflictInfo]]:
        """
        Detect conflicts among a list of scheduled experiments
        
        Args:
            experiments: List of scheduled experiments to check
            
        Returns:
            Dictionary mapping schedule_id to list of conflicts
        """
        conflicts_map = {}
        
        for experiment in experiments:
            conflicts = self._detect_conflicts(experiment, experiments)
            if conflicts:
                conflicts_map[experiment.schedule_id] = conflicts
        
        return conflicts_map
    
    def suggest_conflict_resolution(self, experiment: ScheduledExperiment) -> List[datetime]:
        """
        Suggest alternative execution times to resolve conflicts
        
        Args:
            experiment: Experiment with conflicts
            
        Returns:
            List of suggested alternative execution times
        """
        suggestions = []
        
        try:
            current_time = datetime.now()
            suggested_start = experiment.start_time or current_time
            
            # Look for gaps in the next 48 hours
            end_search = current_time + timedelta(hours=48)
            check_time = max(suggested_start, current_time)
            
            with self._windows_lock:
                while check_time < end_search and len(suggestions) < 5:
                    # Check if this time slot is free
                    test_end_time = check_time + timedelta(minutes=experiment.estimated_duration)
                    
                    conflicts = self._check_time_conflicts(check_time, test_end_time, experiment.schedule_id)
                    
                    if not conflicts:
                        suggestions.append(check_time)
                    
                    # Move to next possible slot (30-minute intervals)
                    check_time += timedelta(minutes=30)
            
        except Exception as e:
            logger.error(f"Error suggesting conflict resolution: {e}")
        
        return suggestions
    
    def _detect_conflicts(self, experiment: ScheduledExperiment, 
                         all_experiments: Optional[List[ScheduledExperiment]] = None) -> List[ConflictInfo]:
        """Detect conflicts for a given experiment"""
        conflicts = []
        
        if not experiment.start_time:
            return conflicts
        
        experiment_end = experiment.start_time + timedelta(minutes=experiment.estimated_duration)
        
        # Time overlap conflicts
        with self._windows_lock:
            overlapping_windows = self._check_time_conflicts(
                experiment.start_time, experiment_end, experiment.schedule_id
            )
            
            if overlapping_windows:
                conflict_ids = [w.schedule_id for w in overlapping_windows]
                conflicts.append(ConflictInfo(
                    conflict_type=ConflictType.TIME_OVERLAP,
                    conflicting_schedule_ids=conflict_ids,
                    message=f"Time overlap with {len(overlapping_windows)} other experiments",
                    suggested_resolution="Reschedule to avoid overlap",
                    alternative_times=self.suggest_conflict_resolution(experiment),
                    severity="high"
                ))
        
        # Hamilton resource conflicts
        if self.process_monitor.is_hamilton_running():
            conflicts.append(ConflictInfo(
                conflict_type=ConflictType.HAMILTON_BUSY,
                conflicting_schedule_ids=[],
                message="Hamilton robot is currently busy",
                suggested_resolution="Wait for Hamilton to become available",
                severity="medium"
            ))
        
        # Check against other scheduled experiments
        if all_experiments:
            for other_exp in all_experiments:
                if (other_exp.schedule_id != experiment.schedule_id and
                    other_exp.start_time and other_exp.is_active):
                    
                    other_end = other_exp.start_time + timedelta(minutes=other_exp.estimated_duration)
                    
                    # Check for overlap with buffer
                    buffer_start = experiment.start_time - timedelta(minutes=self._conflict_threshold_minutes)
                    buffer_end = experiment_end + timedelta(minutes=self._conflict_threshold_minutes)
                    
                    if (other_exp.start_time < buffer_end and other_end > buffer_start):
                        conflicts.append(ConflictInfo(
                            conflict_type=ConflictType.TIME_OVERLAP,
                            conflicting_schedule_ids=[other_exp.schedule_id],
                            message=f"Potential overlap with {other_exp.experiment_name}",
                            suggested_resolution="Adjust timing to maintain buffer",
                            severity="medium"
                        ))
        
        return conflicts
    
    def _check_time_conflicts(self, start_time: datetime, end_time: datetime, 
                             exclude_schedule_id: str) -> List[ExecutionWindow]:
        """Check for time conflicts with existing execution windows"""
        conflicts = []
        
        for window in self._execution_windows:
            if window.schedule_id == exclude_schedule_id:
                continue
            
            # Check for overlap
            if (start_time < window.end_time and end_time > window.start_time):
                conflicts.append(window)
        
        return conflicts
    
    def _is_hamilton_available_for_job(self, job: QueuedJob) -> bool:
        """Check if Hamilton is available for job execution"""
        try:
            # Check if Hamilton is currently running
            if self.process_monitor.is_hamilton_running():
                return False
            
            # Additional checks could be added here:
            # - Check system resources
            # - Check experiment file accessibility
            # - Check database connectivity
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking Hamilton availability: {e}")
            return False
    
    def _update_execution_windows(self):
        """Update execution windows based on current queue state"""
        try:
            current_time = datetime.now()
            
            with self._windows_lock:
                # Remove past windows
                self._execution_windows = [w for w in self._execution_windows 
                                         if w.end_time > current_time]
                
                # Add windows for queued jobs
                temp_queue = []
                
                # Process queue to create execution windows
                while not self._job_queue.empty():
                    try:
                        job = self._job_queue.get_nowait()
                        temp_queue.append(job)
                        
                        # Create projected execution window
                        if job.experiment.start_time:
                            projected_start = max(job.experiment.start_time, current_time)
                            projected_end = projected_start + timedelta(
                                minutes=job.experiment.estimated_duration
                            )
                            
                            # Check if window already exists
                            exists = any(w.schedule_id == job.experiment.schedule_id 
                                       for w in self._execution_windows)
                            
                            if not exists:
                                window = ExecutionWindow(
                                    start_time=projected_start,
                                    end_time=projected_end,
                                    experiment_name=job.experiment.experiment_name,
                                    schedule_id=job.experiment.schedule_id,
                                    is_running=False
                                )
                                self._execution_windows.append(window)
                        
                    except Empty:
                        break
                
                # Put jobs back in queue
                for job in temp_queue:
                    self._job_queue.put(job)
                
                # Sort windows by start time
                self._execution_windows.sort(key=lambda w: w.start_time)
                
        except Exception as e:
            logger.error(f"Error updating execution windows: {e}")


# Singleton instance management
_job_queue_manager_instance = None
_job_queue_manager_lock = threading.Lock()


def get_job_queue_manager(max_parallel_jobs: int = 1) -> JobQueueManager:
    """
    Get the singleton JobQueueManager instance

    Args:
        max_parallel_jobs: Desired maximum number of parallel jobs.

    Returns:
        JobQueueManager: The job queue manager instance
    """
    global _job_queue_manager_instance

    with _job_queue_manager_lock:
        if _job_queue_manager_instance is None:
            _job_queue_manager_instance = JobQueueManager(max_parallel_jobs=max_parallel_jobs)
        else:
            _job_queue_manager_instance.set_max_parallel_jobs(max_parallel_jobs)

    return _job_queue_manager_instance
