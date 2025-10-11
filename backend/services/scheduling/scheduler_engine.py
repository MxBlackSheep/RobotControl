"""
Core Scheduler Engine Service

Main scheduling service that manages scheduled experiments execution.
Provides background thread-based scheduling with interval support and persistence.

Features:
- Background thread scheduler with configurable intervals
- Support for 6hr, 8hr, and 24hr scheduling patterns
- Job persistence and recovery on service restart
- Integration with process monitor and database
- WebSocket notifications for real-time updates
"""

import logging
import threading
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass, field
from queue import Queue, Empty
from backend.models import (
    ScheduledExperiment,
    JobExecution,
    RetryConfig,
    ManualRecoveryState,
    NotificationContact,
    NotificationLogEntry,
)
from backend.services.scheduling.database_manager import get_scheduling_database_manager
from backend.services.scheduling.process_monitor import get_hamilton_process_monitor
from backend.services.notifications import get_notification_service

try:
    from backend.utils.datetime import ensure_local_naive
except ImportError:  # pragma: no cover - fallback
    from utils.datetime import ensure_local_naive  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    """Configuration for the scheduler engine"""
    check_interval_seconds: float = 30.0  # How often to check for due jobs
    max_concurrent_jobs: int = 1  # Maximum concurrent experiment executions
    startup_delay_seconds: float = 10.0  # Delay before first check
    enable_persistence: bool = True
    enable_notifications: bool = True


@dataclass
class SchedulingEvent:
    """Event data for scheduler notifications"""
    event_type: str  # 'job_started', 'job_completed', 'job_failed', 'schedule_added', etc.
    schedule_id: str
    experiment_name: str
    timestamp: datetime
    message: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionWatch:
    """Track active execution metadata for watchdog alerts."""
    execution_id: str
    schedule_id: str
    experiment_name: str
    started_at: datetime
    expected_minutes: int
    contact_ids: Set[str] = field(default_factory=set)
    notified_events: Set[str] = field(default_factory=set)

    def mark_notified(self, event_type: str) -> None:
        self.notified_events.add(event_type)

    def was_notified(self, event_type: str) -> bool:
        return event_type in self.notified_events


class SchedulerEngine:
    """Core scheduling engine for experiment execution"""
    
    def __init__(self, config: Optional[SchedulerConfig] = None):
        """
        Initialize the scheduler engine
        
        Args:
            config: Optional scheduler configuration
        """
        self.config = config or SchedulerConfig()
        self._running = False
        self._scheduler_thread = None
        self._job_queue = Queue()
        self._active_schedules: Dict[str, ScheduledExperiment] = {}
        self._running_jobs: Set[str] = set()
        self._event_callbacks: List[Callable[[SchedulingEvent], None]] = []
        self._manual_state_lock = threading.RLock()
        self._manual_recovery_cache: ManualRecoveryState = ManualRecoveryState()
        self._manual_state_last_check: float = 0.0
        self._manual_state_logged_active = False
        self._notification_service = get_notification_service() if self.config.enable_notifications else None
        
        # Service dependencies
        self.db_manager = get_scheduling_database_manager()
        self.process_monitor = get_hamilton_process_monitor()
        
        # Threading synchronization
        self._schedules_lock = threading.RLock()
        self._jobs_lock = threading.RLock()
        self._contacts_lock = threading.RLock()
        self._notification_contacts: Dict[str, NotificationContact] = {}
        self._execution_watch_lock = threading.RLock()
        self._execution_watches: Dict[str, ExecutionWatch] = {}
        
        logger.info("Scheduler engine initialized")
    
    def _ensure_naive_datetime(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime reflects local wall-clock time without timezone info."""
        return ensure_local_naive(dt)
    
    def start(self) -> bool:
        """
        Start the scheduler engine
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        try:
            if self._running:
                logger.warning("Scheduler engine already running")
                return True
            
            # Initialize database schema
            if not self.db_manager.initialize_schema():
                logger.error("Failed to initialize database schema")
                return False
            
            # Load existing schedules from database
            self._load_schedules_from_database()
            self._refresh_manual_recovery_state(force=True)
            self.refresh_notification_contacts(include_inactive=True)
            
            # Start process monitoring
            if not self.process_monitor.start_monitoring():
                logger.warning("Process monitoring failed to start")
            
            # Start scheduler thread
            self._running = True
            self._start_time = time.time()  # Track when scheduler started
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="SchedulerEngine"
            )
            self._scheduler_thread.start()
            
            logger.info(f"Scheduler engine started with {len(self._active_schedules)} active schedules")
            self._emit_event("scheduler_started", "", "Scheduler", 
                           f"Started with {len(self._active_schedules)} schedules")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler engine: {e}")
            self._running = False
            return False
    
    def stop(self):
        """Stop the scheduler engine"""
        logger.info("Stopping scheduler engine...")
        self._running = False
        
        # Wait for scheduler thread to finish
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5.0)
        
        # Stop process monitoring
        self.process_monitor.stop_monitoring()
        
        # Clear active schedules
        with self._schedules_lock:
            self._active_schedules.clear()
        
        logger.info("Scheduler engine stopped")
        self._emit_event("scheduler_stopped", "", "Scheduler", "Scheduler engine stopped")
    
    def add_schedule(self, experiment: ScheduledExperiment) -> bool:
        """
        Add a new scheduled experiment
        
        Args:
            experiment: ScheduledExperiment to add
            
        Returns:
            bool: True if added successfully, False otherwise
        """
        try:
            with self._schedules_lock:
                # Ensure all datetime fields are timezone-naive
                if experiment.start_time:
                    experiment.start_time = self._ensure_naive_datetime(experiment.start_time)
                if experiment.created_at:
                    experiment.created_at = self._ensure_naive_datetime(experiment.created_at)
                if experiment.updated_at:
                    experiment.updated_at = self._ensure_naive_datetime(experiment.updated_at)
                
                # Validate experiment
                if not self._validate_experiment(experiment):
                    logger.error(f"Experiment validation failed: {experiment.experiment_name}")
                    return False
                
                # Calculate next execution time if not set
                if not experiment.start_time:
                    experiment.start_time = self._calculate_next_execution_time(experiment)
                
                # Store in database
                if not self.db_manager.store_scheduled_experiment(experiment):
                    logger.error(f"Failed to store experiment in database: {experiment.schedule_id}")
                    return False
                
                # Add to active schedules
                self._active_schedules[experiment.schedule_id] = experiment
                
                logger.info(f"Added schedule: {experiment.experiment_name} ({experiment.schedule_id})")
                self._emit_event("schedule_added", experiment.schedule_id, 
                               experiment.experiment_name, 
                               f"Schedule added, next run: {experiment.start_time}")
                return True
                
        except Exception as e:
            logger.error(f"Error adding schedule: {e}")
            return False
    
    def remove_schedule(self, schedule_id: str) -> bool:
        """
        Remove a scheduled experiment
        
        Args:
            schedule_id: ID of the schedule to remove
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        try:
            with self._schedules_lock:
                # Check if schedule exists
                if schedule_id not in self._active_schedules:
                    logger.warning(f"Schedule not found: {schedule_id}")
                    return False
                
                experiment = self._active_schedules[schedule_id]
                
                # Remove from database
                if not self.db_manager.delete_scheduled_experiment(schedule_id):
                    logger.error(f"Failed to delete schedule from database: {schedule_id}")
                    return False
                
                # Remove from active schedules
                del self._active_schedules[schedule_id]
                
                logger.info(f"Removed schedule: {experiment.experiment_name} ({schedule_id})")
                self._emit_event("schedule_removed", schedule_id, 
                               experiment.experiment_name, "Schedule removed")
                return True
                
        except Exception as e:
            logger.error(f"Error removing schedule: {e}")
            return False
    
    def update_schedule(self, experiment: ScheduledExperiment) -> bool:
        """
        Update an existing scheduled experiment
        
        Args:
            experiment: Updated ScheduledExperiment
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            with self._schedules_lock:
                # Ensure all datetime fields are timezone-naive
                if experiment.start_time:
                    experiment.start_time = self._ensure_naive_datetime(experiment.start_time)
                if experiment.created_at:
                    experiment.created_at = self._ensure_naive_datetime(experiment.created_at)
                if experiment.updated_at:
                    experiment.updated_at = self._ensure_naive_datetime(experiment.updated_at)
                
                # Validate experiment
                if not self._validate_experiment(experiment):
                    return False
                
                # Update in database
                if not self.db_manager.update_scheduled_experiment(experiment):
                    logger.error(f"Failed to update schedule in database: {experiment.schedule_id}")
                    return False
                
                # Update in memory
                self._active_schedules[experiment.schedule_id] = experiment
                
                logger.info(f"Updated schedule: {experiment.experiment_name} ({experiment.schedule_id})")
                self._emit_event("schedule_updated", experiment.schedule_id,
                               experiment.experiment_name, "Schedule updated")
                return True
                
        except Exception as e:
            logger.error(f"Error updating schedule: {e}")
            return False
    
    def get_active_schedules(self) -> List[ScheduledExperiment]:
        """
        Get all active scheduled experiments
        
        Returns:
            List of active ScheduledExperiment objects
        """
        with self._schedules_lock:
            return list(self._active_schedules.values())
    
    def get_schedule(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        """
        Get a specific scheduled experiment by ID
        
        Args:
            schedule_id: ID of the schedule to retrieve
            
        Returns:
            ScheduledExperiment or None if not found
        """
        with self._schedules_lock:
            return self._active_schedules.get(schedule_id)
    
    def get_upcoming_jobs(self, hours_ahead: int = 48) -> List[ScheduledExperiment]:
        """
        Get scheduled experiments for the next N hours
        
        Args:
            hours_ahead: Number of hours to look ahead
            
        Returns:
            List of ScheduledExperiment objects
        """
        cutoff_time = datetime.now() + timedelta(hours=hours_ahead)
        
        with self._schedules_lock:
            upcoming = []
            for experiment in self._active_schedules.values():
                if (experiment.is_active and 
                    experiment.start_time and 
                    self._ensure_naive_datetime(experiment.start_time) <= cutoff_time and
                    self._ensure_naive_datetime(experiment.start_time) >= datetime.now()):
                    upcoming.append(experiment)
            
            # Sort by start time
            upcoming.sort(key=lambda x: x.start_time or datetime.max)
            return upcoming
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current scheduler status and statistics
        
        Returns:
            Dict with scheduler status information
        """
        with self._schedules_lock, self._jobs_lock:
            return {
                "is_running": self._running,
                "active_schedules_count": len(self._active_schedules),
                "running_jobs_count": len(self._running_jobs),
                "max_concurrent_jobs": self.config.max_concurrent_jobs,
                "check_interval_seconds": self.config.check_interval_seconds,
                "thread_alive": self._scheduler_thread.is_alive() if self._scheduler_thread else False,
                "uptime_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0
            }
    
    def add_event_callback(self, callback: Callable[[SchedulingEvent], None]):
        """
        Add event callback for scheduler notifications
        
        Args:
            callback: Function to call when events occur
        """
        self._event_callbacks.append(callback)
    
    def remove_event_callback(self, callback: Callable[[SchedulingEvent], None]):
        """
        Remove event callback
        
        Args:
            callback: Function to remove from callbacks
        """
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)
    
    def _refresh_manual_recovery_state(self, force: bool = False) -> ManualRecoveryState:
        """Refresh and return the cached manual recovery state."""
        with self._manual_state_lock:
            window = max(self.config.check_interval_seconds / 2, 5)
            if not force and (time.time() - self._manual_state_last_check) < window:
                return self._manual_recovery_cache
            try:
                state = self.db_manager.get_manual_recovery_state()
            except Exception as exc:
                logger.warning("Failed to refresh manual recovery state: %s", exc)
                state = self._manual_recovery_cache
            self._manual_recovery_cache = state
            self._manual_state_last_check = time.time()
            if state.active and not self._manual_state_logged_active:
                logger.warning(
                    "Manual recovery active for %s; scheduler dispatch paused",
                    state.experiment_name or state.schedule_id or "unknown schedule",
                )
                self._manual_state_logged_active = True
            elif not state.active and self._manual_state_logged_active:
                logger.info("Manual recovery cleared; scheduler dispatch resuming")
                self._manual_state_logged_active = False
            return state

    def _apply_manual_recovery(self, schedule: ScheduledExperiment, note: Optional[str], actor: str) -> Optional[ScheduledExperiment]:
        """Mark a schedule as requiring manual recovery and emit related side effects."""
        try:
            updated = self.db_manager.mark_recovery_required(schedule.schedule_id, note, actor)
        except Exception as exc:
            logger.error("Failed to mark manual recovery for %s: %s", schedule.schedule_id, exc)
            return None
        if not updated:
            logger.error("Manual recovery update returned no schedule for %s", schedule.schedule_id)
            return None
        with self._schedules_lock:
            self._active_schedules[updated.schedule_id] = updated
        self._refresh_manual_recovery_state(force=True)
        if self.config.enable_notifications and self._notification_service:
            try:
                self._notification_service.manual_recovery_required(updated, note=note, actor=actor)
            except Exception as exc:
                logger.warning("Manual recovery notification failed: %s", exc)
        self._emit_event(
            "manual_recovery_required",
            updated.schedule_id,
            updated.experiment_name,
            note or "Manual recovery required",
            data={"note": note, "actor": actor},
        )
        return updated

    def _clear_manual_recovery(self, schedule_id: str, note: Optional[str], actor: str) -> Optional[ScheduledExperiment]:
        """Clear manual recovery state for a schedule."""
        try:
            updated = self.db_manager.resolve_recovery_required(schedule_id, note, actor)
        except Exception as exc:
            logger.error("Failed to clear manual recovery for %s: %s", schedule_id, exc)
            updated = None
        if updated:
            with self._schedules_lock:
                self._active_schedules[updated.schedule_id] = updated
            if self.config.enable_notifications and self._notification_service:
                try:
                    self._notification_service.manual_recovery_cleared(updated, note=note, actor=actor)
                except Exception as exc:
                    logger.warning("Manual recovery clear notification failed: %s", exc)
            self._emit_event(
                "manual_recovery_cleared",
                updated.schedule_id,
                updated.experiment_name,
                note or "Manual recovery cleared",
                data={"note": note, "actor": actor},
            )
        self._refresh_manual_recovery_state(force=True)
        return updated

    def require_manual_recovery(self, schedule_id: str, note: Optional[str], actor: str) -> Optional[ScheduledExperiment]:
        """Public entrypoint for marking a schedule as requiring manual recovery."""
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            schedule = self.db_manager.get_scheduled_experiment(schedule_id)
            if not schedule:
                logger.error("Schedule %s not found when marking manual recovery", schedule_id)
                return None
        return self._apply_manual_recovery(schedule, note, actor)

    def resolve_manual_recovery(self, schedule_id: str, note: Optional[str], actor: str) -> Optional[ScheduledExperiment]:
        """Clear manual recovery; returns the updated schedule if successful."""
        updated = self._clear_manual_recovery(schedule_id, note, actor)
        if updated:
            return updated
        schedule = self.get_schedule(schedule_id)
        if schedule:
            return schedule
        return self.db_manager.get_scheduled_experiment(schedule_id)

    def get_manual_recovery_state(self) -> ManualRecoveryState:
        """Return the current manual recovery state."""
        return self._refresh_manual_recovery_state(force=True)

    def _scheduler_loop(self):
        """Main scheduler loop running in background thread"""
        logger.info("Scheduler loop started")
        
        # Initial startup delay
        time.sleep(self.config.startup_delay_seconds)
        
        while self._running:
            try:
                current_time = datetime.now()

                manual_state = self._refresh_manual_recovery_state()
                if manual_state.active:
                    time.sleep(self.config.check_interval_seconds)
                    continue

                # Check for due jobs
                due_jobs = self._find_due_jobs(current_time)
                
                # Process due jobs
                for experiment in due_jobs:
                    if self._manual_recovery_cache.active:
                        break
                    self._process_due_job(experiment, current_time)
                
                # Update next execution times for interval schedules
                self._update_interval_schedules(current_time)

                # Watchdog: evaluate running executions for alerts
                self._evaluate_active_executions(current_time)
                
                # Clean up completed jobs
                self._cleanup_completed_jobs()
                
                # Sleep until next check
                time.sleep(self.config.check_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(self.config.check_interval_seconds)
        
        logger.info("Scheduler loop stopped")
    
    def _find_due_jobs(self, current_time: datetime) -> List[ScheduledExperiment]:
        """Find jobs that are due for execution"""
        due_jobs = []
        
        with self._schedules_lock:
            for experiment in self._active_schedules.values():
                if (not experiment.is_active or
                    not experiment.start_time or
                    experiment.schedule_id in self._running_jobs or
                    experiment.recovery_required):
                    continue
                
                start_time = self._ensure_naive_datetime(experiment.start_time)
                max_failures = experiment.retry_config.max_retries if experiment.retry_config else 3
                
                if experiment.failed_execution_count > max_failures:
                    # Disable schedule that has exceeded retry limit
                    logger.warning(f"Schedule {experiment.experiment_name} has exceeded retry limit ({experiment.failed_execution_count}/{max_failures}), disabling")
                    experiment.is_active = False
                    self.db_manager.update_scheduled_experiment(experiment)
                    continue
                
                # Check if experiment is due
                if start_time <= current_time:
                    # Calculate how much time has passed since scheduled time
                    time_since_scheduled = (current_time - start_time).total_seconds() / 60  # minutes
                    
                    # For interval schedules: if missed by more than half the interval, mark as missed and schedule next
                    if experiment.schedule_type == "interval" and experiment.interval_hours:
                        grace_period_minutes = (experiment.interval_hours * 60) / 2  # Half the interval
                        
                        if time_since_scheduled > grace_period_minutes:
                            # Mark as missed and calculate next execution time
                            logger.info(f"Experiment {experiment.experiment_name} missed (overdue by {time_since_scheduled:.1f} minutes), scheduling next occurrence")
                            
                            # Create a missed execution record
                            missed_execution = JobExecution(
                                execution_id=f"missed_{experiment.schedule_id}_{int(current_time.timestamp())}",
                                schedule_id=experiment.schedule_id,
                                status="missed",
                                start_time=start_time,
                                end_time=current_time,
                                error_message=f"Experiment missed - overdue by {time_since_scheduled:.1f} minutes",
                                retry_count=0
                            )
                            self.db_manager.store_job_execution(missed_execution)
                            
                            # Update to next execution time for interval schedules
                            next_time = self._calculate_next_execution_time(experiment)
                            experiment.start_time = next_time
                            experiment.updated_at = current_time
                            self.db_manager.update_scheduled_experiment(experiment)
                            
                            logger.info(f"Next execution scheduled for {experiment.experiment_name}: {next_time}")
                            continue
                        else:
                            # Still within grace period, execute normally
                            due_jobs.append(experiment)
                    else:
                        # For "once" schedules: if missed by more than 30 minutes, mark as missed
                        if experiment.schedule_type == "once" and time_since_scheduled > 30:
                            logger.info(f"One-time experiment {experiment.experiment_name} missed (overdue by {time_since_scheduled:.1f} minutes)")
                            
                            # Create missed execution record
                            missed_execution = JobExecution(
                                execution_id=f"missed_{experiment.schedule_id}_{int(current_time.timestamp())}",
                                schedule_id=experiment.schedule_id,
                                status="missed",
                                start_time=start_time,
                                end_time=current_time,
                                error_message=f"One-time experiment missed - overdue by {time_since_scheduled:.1f} minutes",
                                retry_count=0
                            )
                            self.db_manager.store_job_execution(missed_execution)
                            
                            # Deactivate missed one-time schedules
                            experiment.is_active = False
                            self.db_manager.update_scheduled_experiment(experiment)
                            continue
                        else:
                            # Execute normally
                            due_jobs.append(experiment)
        
        return due_jobs
    
    def _process_due_job(self, experiment: ScheduledExperiment, current_time: datetime):
        """Process a job that is due for execution"""
        try:
            # Check if we have capacity for more jobs
            with self._jobs_lock:
                if len(self._running_jobs) >= self.config.max_concurrent_jobs:
                    logger.info(f"Max concurrent jobs reached, queuing: {experiment.experiment_name}")
                    return
                
                # Mark job as running
                self._running_jobs.add(experiment.schedule_id)
            
            # Create job execution record
            execution = JobExecution(
                execution_id="",  # Will be auto-generated
                schedule_id=experiment.schedule_id,
                status="pending",
                start_time=current_time
            )
            
            # Store execution record
            if not self.db_manager.store_job_execution(execution):
                logger.error(f"Failed to store job execution: {experiment.schedule_id}")
                with self._jobs_lock:
                    self._running_jobs.discard(experiment.schedule_id)
                return
            
            logger.info(f"Starting job execution: {experiment.experiment_name}")
            self._emit_event("job_started", experiment.schedule_id, 
                           experiment.experiment_name, "Job execution started")
            
            # Queue job for execution
            self._job_queue.put((experiment, execution))
            
            # Start execution in separate thread
            execution_thread = threading.Thread(
                target=self._execute_job,
                args=(experiment, execution),
                daemon=True,
                name=f"JobExecution-{experiment.experiment_name}"
            )
            execution_thread.start()
            
        except Exception as e:
            logger.error(f"Error processing due job: {e}")
            with self._jobs_lock:
                self._running_jobs.discard(experiment.schedule_id)
    
    def _execute_job(self, experiment: ScheduledExperiment, execution: JobExecution):
        """Execute a scheduled job"""
        try:
            # Import experiment executor here to avoid circular imports
            from backend.services.scheduling.experiment_executor import ExperimentExecutor
            
            executor = ExperimentExecutor()
            current_time = datetime.now()
            
            # Update execution status
            execution.status = "running"
            execution.start_time = current_time
            self.db_manager.store_job_execution(execution)
            self._register_execution_watch(experiment, execution)
            
            # Execute the experiment
            success = executor.execute_experiment(experiment, execution)
            
            # Update execution record
            execution.end_time = datetime.now()
            if execution.start_time:
                duration = execution.end_time - execution.start_time
                execution.duration_minutes = int(duration.total_seconds() / 60)
            
            if success:
                execution.status = "completed"
                # Reset failed count on success
                experiment.failed_execution_count = 0
                
                # Handle schedule completion based on type
                if experiment.schedule_type == "once":
                    # Deactivate "once" schedules after successful completion
                    experiment.is_active = False
                    logger.info(f"Job completed successfully: {experiment.experiment_name} - Deactivating 'once' schedule")
                elif experiment.schedule_type == "interval":
                    # Update next execution time for interval schedules
                    next_time = self._calculate_next_execution_time(experiment)
                    experiment.start_time = next_time
                    experiment.updated_at = current_time
                    logger.info(f"Job completed successfully: {experiment.experiment_name} - Next execution: {next_time}")
                else:
                    logger.info(f"Job completed successfully: {experiment.experiment_name}")
                
                self._emit_event("job_completed", experiment.schedule_id,
                               experiment.experiment_name, "Job completed successfully")
            else:
                execution.status = "failed"
                # Increment failed execution count
                experiment.failed_execution_count += 1
                logger.error(f"Job failed: {experiment.experiment_name} (failure {experiment.failed_execution_count})")
                self._emit_event("job_failed", experiment.schedule_id,
                               experiment.experiment_name, f"Job execution failed (attempt {experiment.failed_execution_count})")
            
            # Update database with execution and schedule
            self.db_manager.store_job_execution(execution)
            self.db_manager.update_scheduled_experiment(experiment)

            if execution.status == "failed":
                self._handle_failed_execution(experiment, execution)

            
        except Exception as e:
            logger.error(f"Error executing job {experiment.experiment_name}: {e}")
            execution.status = "failed"
            execution.error_message = str(e)
            execution.end_time = datetime.now()
            # Increment failed execution count on exception
            experiment.failed_execution_count += 1
            self.db_manager.store_job_execution(execution)
            self.db_manager.update_scheduled_experiment(experiment)


            self._handle_failed_execution(experiment, execution)

            self._emit_event("job_failed", experiment.schedule_id,
                           experiment.experiment_name, f"Job failed: {str(e)} (attempt {experiment.failed_execution_count})")
        
        finally:
            self._clear_execution_watch(execution.execution_id)
            # Remove from running jobs
            with self._jobs_lock:
                self._running_jobs.discard(experiment.schedule_id)
    
    def _handle_failed_execution(self, experiment: ScheduledExperiment, execution: JobExecution) -> None:
        """Handle logic after a failed execution, including manual recovery enforcement."""
        note: Optional[str] = None
        try:
            note = self.db_manager.should_block_due_to_abort(experiment)
        except Exception as exc:
            logger.debug("Abort state lookup failed for %s: %s", experiment.experiment_name, exc)
        message = (execution.error_message or "").lower()
        if not note:
            if ("return code 64" in message or
                "hamilton reported last run" in message or
                "manual abort" in message):
                note = execution.error_message or "Hamilton reported last run as aborted"

        aborted = bool(note) or self._message_indicates_abort(execution.error_message)
        if aborted:
            context: Dict[str, Any] = {
                "error_message": execution.error_message or "Unknown error",
                "failure_count": experiment.failed_execution_count,
            }
            if note:
                context["note"] = note
            if execution.start_time and execution.end_time:
                context["runtime_minutes"] = round(
                    (execution.end_time - execution.start_time).total_seconds() / 60, 1
                )
            self._notify_execution_event(experiment, execution, "aborted", context)

        if note:
            self._apply_manual_recovery(experiment, note, actor="scheduler")

    def _update_interval_schedules(self, current_time: datetime):
        """Update next execution times for interval-based schedules"""
        with self._schedules_lock:
            for experiment in self._active_schedules.values():
                if (experiment.schedule_type == "interval" and 
                    experiment.interval_hours and
                    experiment.start_time and
                    self._ensure_naive_datetime(experiment.start_time) <= current_time):
                    
                    # Calculate next execution time
                    next_time = self._calculate_next_execution_time(experiment)
                    if next_time != experiment.start_time:
                        experiment.start_time = next_time
                        experiment.updated_at = current_time
                        
                        # Update in database
                        self.db_manager.update_scheduled_experiment(experiment)
                        
                        logger.debug(f"Updated next execution time for {experiment.experiment_name}: {next_time}")
    
    def _calculate_next_execution_time(self, experiment: ScheduledExperiment) -> datetime:
        """Calculate the next execution time for an experiment"""
        current_time = datetime.now()
        
        if experiment.schedule_type == "interval" and experiment.interval_hours:
            if experiment.start_time and self._ensure_naive_datetime(experiment.start_time) > current_time:
                return experiment.start_time
            
            # Calculate next interval time
            next_time = current_time + timedelta(hours=experiment.interval_hours)
            
            # Round to the nearest minute for cleaner scheduling
            next_time = next_time.replace(second=0, microsecond=0)
            
            return next_time
        
        elif experiment.schedule_type == "once":
            # For "once" schedules, if they're completed they should be deactivated
            # If still active, return the original start time
            return experiment.start_time or current_time
        
        else:
            # Default to immediate execution
            return current_time
    
    def _validate_experiment(self, experiment: ScheduledExperiment) -> bool:
        """Validate experiment configuration"""
        if not experiment.experiment_name:
            logger.error("Experiment name is required")
            return False
        
        if not experiment.experiment_path:
            logger.error("Experiment path is required")
            return False
        
        if experiment.schedule_type not in ["interval", "once", "cron"]:
            logger.error(f"Invalid schedule type: {experiment.schedule_type}")
            return False
        
        if experiment.schedule_type == "interval" and not experiment.interval_hours:
            logger.error("Interval hours required for interval schedules")
            return False
        
        if experiment.estimated_duration <= 0:
            logger.error("Estimated duration must be positive")
            return False
        
        return True
    
    def _load_schedules_from_database(self):
        """Load active schedules from database on startup"""
        try:
            schedules = self.db_manager.get_active_schedules()
            
            with self._schedules_lock:
                for schedule in schedules:
                    # Ensure all datetime fields are timezone-naive
                    if schedule.start_time:
                        schedule.start_time = self._ensure_naive_datetime(schedule.start_time)
                    if schedule.created_at:
                        schedule.created_at = self._ensure_naive_datetime(schedule.created_at)
                    if schedule.updated_at:
                        schedule.updated_at = self._ensure_naive_datetime(schedule.updated_at)
                    self._active_schedules[schedule.schedule_id] = schedule
            
            logger.info(f"Loaded {len(schedules)} active schedules from database")
            
        except Exception as e:
            logger.error(f"Error loading schedules from database: {e}")

    def refresh_notification_contacts(self, include_inactive: bool = False) -> List[NotificationContact]:
        """Refresh cached notification contact list from the database."""
        try:
            contacts = self.db_manager.get_notification_contacts(include_inactive=include_inactive)
            with self._contacts_lock:
                self._notification_contacts = {contact.contact_id: contact for contact in contacts}
            logger.debug("Loaded %s notification contacts", len(contacts))
            return contacts
        except Exception as exc:
            logger.error("Failed to refresh notification contacts: %s", exc)
            return []

    def refresh_notification_service(self) -> None:
        """Reload the global notification service to pick up new SMTP settings."""
        if not self.config.enable_notifications:
            return
        try:
            from backend.services.notifications import (
                get_notification_service,
                reset_notification_service,
            )
            reset_notification_service()
            self._notification_service = get_notification_service()
            logger.info("Notification service reloaded with latest SMTP settings")
        except Exception as exc:
            logger.error("Failed to refresh notification service: %s", exc)

    def get_notification_contact(self, contact_id: str) -> Optional[NotificationContact]:
        """Return cached notification contact if available."""
        if not contact_id:
            return None
        with self._contacts_lock:
            return self._notification_contacts.get(contact_id)

    def iter_notification_contacts(self) -> List[NotificationContact]:
        """Return a snapshot list of cached notification contacts."""
        with self._contacts_lock:
            return list(self._notification_contacts.values())

    # ------------------------------------------------------------------
    # Execution watchdog helpers
    # ------------------------------------------------------------------

    def _register_execution_watch(self, experiment: ScheduledExperiment, execution: JobExecution) -> None:
        """Start tracking a running execution for watchdog monitoring."""
        start_time = execution.start_time or datetime.now()
        contact_ids = set(experiment.notification_contacts or [])
        watch = ExecutionWatch(
            execution_id=execution.execution_id,
            schedule_id=experiment.schedule_id,
            experiment_name=experiment.experiment_name,
            started_at=start_time,
            expected_minutes=max(1, experiment.estimated_duration or 1),
            contact_ids=contact_ids,
        )
        with self._execution_watch_lock:
            self._execution_watches[execution.execution_id] = watch
        logger.debug(
            "Registered execution watch for %s (%s) with %s contact(s)",
            execution.execution_id,
            experiment.experiment_name,
            len(contact_ids),
        )

    def _clear_execution_watch(self, execution_id: str) -> None:
        """Remove execution watch tracking when execution completes."""
        with self._execution_watch_lock:
            self._execution_watches.pop(execution_id, None)

    def _get_execution_watch(self, execution_id: str) -> Optional[ExecutionWatch]:
        with self._execution_watch_lock:
            return self._execution_watches.get(execution_id)

    def _mark_execution_event(self, execution_id: str, event_type: str) -> None:
        with self._execution_watch_lock:
            watch = self._execution_watches.get(execution_id)
            if watch:
                watch.mark_notified(event_type)

    def _was_execution_event_notified(self, execution_id: str, event_type: str) -> bool:
        with self._execution_watch_lock:
            watch = self._execution_watches.get(execution_id)
            return watch.was_notified(event_type) if watch else False

    def _snapshot_execution_watches(self) -> List[ExecutionWatch]:
        with self._execution_watch_lock:
            return list(self._execution_watches.values())

    def _evaluate_active_executions(self, current_time: datetime) -> None:
        """Check running jobs for watchdog conditions."""
        watches = self._snapshot_execution_watches()
        if not watches:
            return

        for watch in watches:
            # Skip if already notified or no contacts configured
            if watch.was_notified("long_running"):
                continue

            elapsed_minutes = (current_time - watch.started_at).total_seconds() / 60
            threshold = watch.expected_minutes * 2
            if elapsed_minutes < threshold:
                continue

            schedule = self._get_schedule_snapshot(watch.schedule_id)
            if not schedule or not (schedule.notification_contacts or watch.contact_ids):
                logger.debug(
                    "Skipping long-running alert for %s - no contacts configured",
                    watch.execution_id,
                )
                self._mark_execution_event(watch.execution_id, "long_running")
                continue

            execution = JobExecution(
                execution_id=watch.execution_id,
                schedule_id=watch.schedule_id,
                status="running",
                start_time=watch.started_at,
            )
            context = {
                "elapsed_minutes": round(elapsed_minutes, 1),
                "threshold_minutes": round(threshold, 1),
                "expected_minutes": watch.expected_minutes,
            }
            self._dispatch_execution_notification(
                schedule,
                execution,
                event_type="long_running",
                context=context,
                contact_ids=watch.contact_ids,
            )
            self._mark_execution_event(watch.execution_id, "long_running")

    def _get_schedule_snapshot(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        with self._schedules_lock:
            schedule = self._active_schedules.get(schedule_id)
        if schedule:
            return schedule
        try:
            return self.db_manager.get_scheduled_experiment(schedule_id)
        except Exception as exc:  # pragma: no cover - best effort
            logger.error("Failed to load schedule snapshot for %s: %s", schedule_id, exc)
            return None

    def _notify_execution_event(
        self,
        experiment: ScheduledExperiment,
        execution: JobExecution,
        event_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        contact_ids = set(experiment.notification_contacts or [])
        watch = self._get_execution_watch(execution.execution_id)
        if watch:
            contact_ids = watch.contact_ids or contact_ids
            self._mark_execution_event(execution.execution_id, event_type)
        self._dispatch_execution_notification(
            experiment,
            execution,
            event_type=event_type,
            context=context or {},
            contact_ids=contact_ids,
        )

    def _dispatch_execution_notification(
        self,
        experiment: ScheduledExperiment,
        execution: JobExecution,
        *,
        event_type: str,
        context: Dict[str, Any],
        contact_ids: Set[str],
    ) -> None:
        if not self.config.enable_notifications or not self._notification_service:
            logger.debug("Notifications disabled; skipping %s alert", event_type)
            return
        if not contact_ids and not experiment.notification_contacts:
            logger.debug("No notification contacts for schedule %s", experiment.schedule_id)
            return

        if self.db_manager.notification_log_exists(execution.execution_id, event_type):
            logger.debug(
                "Notification already logged for execution %s (%s)",
                execution.execution_id,
                event_type,
            )
            return

        contacts: List[NotificationContact] = []
        missing: List[str] = []
        for contact_id in contact_ids or experiment.notification_contacts or []:
            contact = self.get_notification_contact(contact_id)
            if contact and contact.is_active:
                contacts.append(contact)
            else:
                missing.append(contact_id)

        if not contacts:
            logger.info(
                "Skipping notification %s for %s - no active contacts (missing=%s)",
                event_type,
                experiment.schedule_id,
                missing,
            )
            return

        log_entry = NotificationLogEntry(
            log_id="",
            schedule_id=experiment.schedule_id,
            execution_id=execution.execution_id,
            event_type=event_type,
            status="pending",
            recipients=[contact.email_address for contact in contacts if contact.email_address],
            metadata={"context": context, "missing_contacts": missing},
        )

        stored_entry = self.db_manager.create_notification_log(log_entry) or log_entry

        try:
            result = self._notification_service.schedule_alert(
                experiment,
                execution,
                contacts=contacts,
                trigger=event_type,
                context=context,
            )
            status = "sent" if result.sent else "error"
            self.db_manager.update_notification_log(
                stored_entry.log_id,
                status=status,
                error_message=result.error,
                processed_at=datetime.now(),
                recipients=result.recipients,
                attachments=result.attachments,
                subject=result.subject,
                message=result.body,
                metadata={
                    "context": context,
                    "missing_contacts": missing,
                    "attachment_notes": result.attachment_notes,
                },
            )
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error(
                "Failed to dispatch notification for %s (%s): %s",
                execution.execution_id,
                event_type,
                exc,
            )
            self.db_manager.update_notification_log(
                stored_entry.log_id,
                status="error",
                error_message=str(exc),
                processed_at=datetime.now(),
                metadata={"context": context, "missing_contacts": missing},
            )

    def _message_indicates_abort(self, message: Optional[str]) -> bool:
        if not message:
            return False
        lowered = message.lower()
        abort_keywords = (
            "abort",
            "aborted",
            "manual abort",
            "stopped by user",
            "user stopped",
        )
        return any(keyword in lowered for keyword in abort_keywords)
    
    def _cleanup_completed_jobs(self):
        """Clean up old completed job records"""
        # This could be expanded to clean up old job execution records
        # For now, we just ensure running jobs set is accurate
        with self._jobs_lock:
            # Remove any jobs that shouldn't be in the running set
            active_job_ids = set(self._active_schedules.keys())
            self._running_jobs &= active_job_ids
    
    def _emit_event(self, event_type: str, schedule_id: str, 
                   experiment_name: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit a scheduling event to registered callbacks"""
        event = SchedulingEvent(
            event_type=event_type,
            schedule_id=schedule_id,
            experiment_name=experiment_name,
            timestamp=datetime.now(),
            message=message,
            data=data
        )
        
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")


# Singleton instance management
_scheduler_engine_instance = None
_scheduler_engine_lock = threading.Lock()


def get_scheduler_engine() -> SchedulerEngine:
    """
    Get the singleton SchedulerEngine instance
    
    Returns:
        SchedulerEngine: The scheduler engine instance
    """
    global _scheduler_engine_instance
    
    with _scheduler_engine_lock:
        if _scheduler_engine_instance is None:
            _scheduler_engine_instance = SchedulerEngine()
            
    return _scheduler_engine_instance
