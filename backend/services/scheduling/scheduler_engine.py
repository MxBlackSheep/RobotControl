"""
Core Scheduler Engine Service

Main scheduling service that manages scheduled experiments execution.
Provides background thread-based scheduling with interval support and persistence.

Features:
- Background thread scheduler with configurable intervals
- Single-worker in-memory execution queue (one dispatch at a time)
- Support for 6hr, 8hr, and 24hr scheduling patterns
- Job persistence and recovery on service restart
- Integration with process monitor and database
- WebSocket notifications for real-time updates
"""

import logging
import sqlite3
from contextlib import contextmanager
from backend.utils.logging_setup import run_log_context
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from queue import Queue, Empty
from pathlib import Path
from backend.models import (
    ScheduledExperiment,
    JobExecution,
    ManualRecoveryState,
    NotificationContact,
    NotificationLogEntry,
)
from backend.services.scheduling.database_manager import get_scheduling_database_manager
from backend.services.scheduling.process_monitor import get_hamilton_process_monitor
from backend.services.notifications import get_notification_service
from backend.services.scheduling.run_log_monitor import NOT_REPORTED_COMPLETE, RunLogMonitor
from backend.services.hxrun_maintenance import get_hxrun_maintenance_service
from backend.services.scheduling.simulation_mode import (
    is_simulation_reason, simulation_block_reason,
)
from backend.services.scheduling.schedule_review import ScheduleReview
from backend.services.scheduling.schedule_check import check_schedule, INTERVAL_TYPE_DEFAULT_HOURS

from backend.utils.datetime import ensure_local_naive

logger = logging.getLogger(__name__)

@dataclass
class SchedulerConfig:
    """Configuration for the scheduler engine"""
    check_interval_seconds: float = 30.0  # How often to check for due jobs
    max_concurrent_jobs: int = 1  # Legacy field kept for status/config compatibility
    startup_delay_seconds: float = 10.0  # Delay before first check
    enable_notifications: bool = True


@dataclass
class QueueRuntimeState:
    """Runtime metadata for a queued/running schedule entry."""
    queued_at: datetime
    waiting_reason: Optional[str] = None


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
        self._stop_event = threading.Event()
        self._scheduler_thread = None
        self._job_worker_thread = None
        self._job_queue = Queue()
        self._active_schedules: Dict[str, ScheduledExperiment] = {}
        self._running_jobs: Set[str] = set()
        self._queued_backlog: Set[str] = set()
        self._manual_state_lock = threading.RLock()
        self._manual_recovery_cache: ManualRecoveryState = ManualRecoveryState()
        self._manual_state_last_check: float = 0.0
        self._manual_state_logged_active = False
        self._queue_runtime: Dict[str, QueueRuntimeState] = {}
        self._notification_service = get_notification_service() if self.config.enable_notifications else None
        
        # Service dependencies
        self.db_manager = get_scheduling_database_manager()
        self.process_monitor = get_hamilton_process_monitor()
        self.hxrun_maintenance_service = get_hxrun_maintenance_service()
        
        # Threading synchronization
        self._schedules_lock = threading.RLock()
        self._jobs_lock = threading.RLock()
        self._contacts_lock = threading.RLock()
        self._notification_contacts: Dict[str, NotificationContact] = {}
        self.run_log_monitor = RunLogMonitor(self.db_manager)
        from backend.services.scheduling.pyhsl_runner import PyHslRunner
        self.pyhsl_runner = PyHslRunner(self)
        self._owned_execution_ids: Set[str] = set()
        self._database_restore_active = False
        self._pyhsl_unavailable_since: Dict[str, float] = {}
        
        logger.info("Scheduler engine initialized")
    
    def _ensure_naive_datetime(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime reflects local wall-clock time without timezone info."""
        if dt is None:
            return None
        return ensure_local_naive(dt)

    def _resolve_interval_hours(self, experiment: ScheduledExperiment) -> Optional[float]:
        """Return the effective interval hours for a schedule, applying sensible defaults."""
        if isinstance(experiment, ScheduleReview):
            return None
        if experiment.schedule_type == "interval":
            if experiment.interval_hours and experiment.interval_hours > 0:
                return float(experiment.interval_hours)
            return None

        default_hours = INTERVAL_TYPE_DEFAULT_HOURS.get(experiment.schedule_type)
        if default_hours is None:
            return None

        if experiment.interval_hours and experiment.interval_hours > 0:
            return float(experiment.interval_hours)

        # Persist defaults for alias-backed schedules if interval_hours was missing.
        experiment.interval_hours = default_hours
        return default_hours
    
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
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                logger.warning("Previous scheduler loop is still stopping; retry start shortly")
                return False
            
            # Initialize database schema
            if not self.db_manager.initialize_schema():
                logger.error("Failed to initialize database schema")
                return False
            
            # Load existing schedules from database
            self._load_schedules_from_database()
            self._refresh_manual_recovery_state(force=True)
            self.refresh_notification_contacts(include_inactive=True)
            for observation in self.run_log_monitor.restore():
                restored_schedule = self.db_manager.get_schedule_by_id(observation.schedule_id)
                if restored_schedule and not isinstance(restored_schedule, ScheduleReview):
                    self._active_schedules[observation.schedule_id] = restored_schedule
                self._running_jobs.add(observation.schedule_id)
                self._ensure_queue_runtime_entry(observation.schedule_id)
            self._evaluate_active_executions(datetime.now())
            if self.config.enable_notifications:
                self.run_log_monitor.start_delivery(lambda: self._notification_service)
            
            # Start process monitoring
            if not self.process_monitor.start_monitoring():
                logger.warning("Process monitoring failed to start")
            
            # Start scheduler thread
            self._running = True
            self._stop_event.clear()
            self._start_time = time.time()  # Track when scheduler started
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="SchedulerEngine"
            )
            self._scheduler_thread.start()
            if not self._job_worker_thread or not self._job_worker_thread.is_alive():
                self._job_worker_thread = threading.Thread(
                    target=self._job_worker_loop,
                    daemon=True,
                    name="SchedulerJobWorker",
                )
                self._job_worker_thread.start()
            
            logger.info(f"Scheduler engine started with {len(self._active_schedules)} active schedules")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler engine: {e}")
            self._running = False
            return False
    
    def stop(self):
        """Stop the scheduler engine"""
        logger.info("Stopping scheduler engine...")
        self._running = False
        self._stop_event.set()

        # Wake worker in case it is blocked waiting on queue.
        self._job_queue.put(None)

        # Wait for scheduler thread to finish
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5.0)
        if self._job_worker_thread and self._job_worker_thread.is_alive():
            self._job_worker_thread.join(timeout=5.0)
        
        # Stop process monitoring
        self.process_monitor.stop_monitoring()
        self.run_log_monitor.stop_delivery()
        
        # Clear active schedules
        with self._schedules_lock:
            self._active_schedules.clear()
        with self._jobs_lock:
            self._running_jobs.clear()
            self._queued_backlog.clear()
            self._queue_runtime.clear()
        
        logger.info("Scheduler engine stopped")
    
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
                return True
                
        except Exception as e:
            logger.error(f"Error adding schedule: {e}")
            return False
    
    def remove_schedule(self, schedule_id: str, expected_updated_at=None) -> bool:
        """
        Remove a scheduled experiment
        
        Args:
            schedule_id: ID of the schedule to remove
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        try:
            with self._schedules_lock, self._jobs_lock:
                experiment = self._active_schedules.get(schedule_id)

                # Remove from database
                if not self.db_manager.delete_scheduled_experiment(
                    schedule_id,
                    schedule=experiment,
                    expected_updated_at=expected_updated_at,
                ):
                    logger.error(f"Failed to delete schedule from database: {schedule_id}")
                    return False
                
                # Remove from active schedules
                self._active_schedules.pop(schedule_id, None)
                
                logger.info("Removed schedule: %s", schedule_id)
                return True
                
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as e:
            logger.error(f"Error removing schedule: {e}")
            return False
    
    def update_schedule(self, experiment: ScheduledExperiment, expected_updated_at=None) -> bool:
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
                if not self.db_manager.update_scheduled_experiment(experiment, expected_updated_at=expected_updated_at):
                    logger.error(f"Failed to update schedule in database: {experiment.schedule_id}")
                    return False
                
                # Update in memory
                self._active_schedules[experiment.schedule_id] = experiment
                
                logger.info(f"Updated schedule: {experiment.experiment_name} ({experiment.schedule_id})")
                return True
                
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
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
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current scheduler status and statistics
        
        Returns:
            Dict with scheduler status information
        """
        with self._schedules_lock, self._jobs_lock:
            status: Dict[str, Any] = {
                "is_running": self._running,
                "active_schedules_count": len(self._active_schedules),
                "running_jobs_count": len(self._running_jobs),
                "queued_jobs_count": len(self._queued_backlog),
                "queue_depth": self._job_queue.qsize(),
                "max_concurrent_jobs": self.config.max_concurrent_jobs,
                "worker_mode": "single",
                "check_interval_seconds": self.config.check_interval_seconds,
                "thread_alive": self._scheduler_thread.is_alive() if self._scheduler_thread else False,
                "worker_thread_alive": self._job_worker_thread.is_alive() if self._job_worker_thread else False,
                "uptime_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0,
            }
        manual_state = self.get_manual_recovery_state()
        status["manual_recovery"] = manual_state.to_dict() if manual_state else None
        try:
            status['hxrun_maintenance'] = self.hxrun_maintenance_service.get_state(force_refresh=True).to_dict()
        except Exception:
            status['hxrun_maintenance'] = None
            status['manual_recovery']['storage_healthy'] = False
            status['manual_recovery']['storage_error'] = status['manual_recovery']['storage_error'] or 'Scheduler safety state unavailable'
        return status

    def get_runtime_queue_status(self) -> Dict[str, Any]:
        """Return queue/running snapshots from the scheduler's single worker runtime."""
        with self._schedules_lock, self._jobs_lock:
            now_dt = datetime.now()

            def _queue_key(schedule_id: str) -> datetime:
                entry = self._queue_runtime.get(schedule_id)
                return entry.queued_at if entry else now_dt

            def _build_detail(schedule_id: str) -> Dict[str, Any]:
                schedule = self._active_schedules.get(schedule_id) or self.db_manager.get_schedule_by_id(schedule_id)
                entry = self._queue_runtime.get(schedule_id)
                queued_at = entry.queued_at if entry else now_dt
                return {
                    "schedule_id": schedule_id,
                    "experiment_name": schedule.experiment_name if schedule else schedule_id,
                    "experiment_path": schedule.experiment_path if schedule else None,
                    "runner": schedule.runner if schedule else None,
                    "protocol_id": schedule.protocol_id if schedule else None,
                    # The user's estimate in minutes; the UI treats it as a hint, never an end time.
                    "estimated_duration": schedule.estimated_duration if schedule else None,
                    "priority": "NORMAL",
                    "queued_time": queued_at.isoformat(),
                    "retry_count": 0,
                    "waiting_reason": entry.waiting_reason if entry else None,
                    "monitoring": self.run_log_monitor.details(schedule_id),
                }

            running_ids = sorted(self._running_jobs, key=_queue_key)
            queued_ids = sorted(self._queued_backlog, key=_queue_key)
            running = [
                _build_detail(schedule_id)
                for schedule_id in running_ids
            ]
            queued = [
                _build_detail(schedule_id)
                for schedule_id in queued_ids
            ]
        running_count = len(running)
        queued_count = len(queued)
        return {
            "queue_size": queued_count,
            "queued_jobs": queued_count,
            "running_jobs": running_count,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "max_parallel_jobs": 1,
            "capacity_available": running_count == 0,
            "running_job_details": running,
            "queued_job_details": queued,
            "execution_windows": [],
            "hamilton_available": not self.process_monitor.is_hamilton_running(),
        }
    
    def invalidate_schedule(self, schedule_id: str) -> None:
        """Remove a schedule from the in-memory cache without touching persistence."""
        with self._schedules_lock:
            self._active_schedules.pop(schedule_id, None)

    def change_library_method_path(self, library_db, method_id: str, new_path: str, expected_revision: int, references: list):
        """Review filesystem state first, then serialize the atomic update with enqueue/dispatch."""
        from backend.services.scheduling.method_library import prepare_path_change
        prepared = prepare_path_change(library_db, method_id, new_path)
        selected_ids = {reference['schedule_id'] for reference in references}
        # Same lock order as status snapshots. Enqueue and worker transitions use _jobs_lock.
        with self._schedules_lock, self._jobs_lock:
            if selected_ids & (self._running_jobs | self._queued_backlog):
                raise ValueError('A selected schedule is queued, running or paused. Wait for it to finish.')
            updated = library_db.apply_method_path_change(prepared, expected_revision, references)
            for schedule in updated:
                if schedule.is_active or schedule.schedule_id in self._active_schedules:
                    self._active_schedules[schedule.schedule_id] = schedule
        return {'method_id': method_id, 'updated_schedule_ids': [schedule.schedule_id for schedule in updated]}
    
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
                if hasattr(self.db_manager, 'sqlite_db'):
                    self.db_manager.sqlite_db._safety_fault = True
                from dataclasses import replace
                state = replace(self._manual_recovery_cache, storage_healthy=False,
                                storage_error=str(exc) if isinstance(exc, StorageUnavailable) else 'Scheduler safety state unavailable', resume_required=True)
            self._manual_recovery_cache = state
            self._manual_state_last_check = time.time()
            if state.active and not self._manual_state_logged_active:
                logger.warning(
                    "Manual recovery active for %s; queued jobs will wait until recovery is cleared",
                    state.experiment_name or state.schedule_id or "unknown schedule",
                )
                self._manual_state_logged_active = True
            elif not state.active and self._manual_state_logged_active:
                logger.info("Manual recovery acknowledged; explicit Resume is required")
                self._manual_state_logged_active = False
            return state

    def _apply_manual_recovery(self, schedule, note, actor, expected_updated_at=None):
        with self._schedules_lock, self._jobs_lock:
            updated = self.db_manager.mark_recovery_required(schedule.schedule_id, note, actor,
                        expected_updated_at=expected_updated_at, snapshot=schedule)
            if updated and not isinstance(updated, ScheduleReview):
                updated.is_active = False
                self._active_schedules[updated.schedule_id] = updated
        self._refresh_manual_recovery_state(force=True)
        if self.config.enable_notifications and self._notification_service:
            try:
                self._notification_service.manual_recovery_required(updated or schedule, note=note, actor=actor)
            except Exception:
                logger.exception('Manual recovery notification failed')
        return updated

    def _clear_manual_recovery(self, schedule_id, note, actor, expected_revision, expected_updated_at=None):
        with self._schedules_lock, self._jobs_lock:
            self._require_robot_absent()
            self.db_manager.sqlite_db.validate_recovery_resolution(schedule_id, note, expected_revision)
            if self._owned_execution_ids:
                raise SafetyConflict("The scheduler still owns this run. Wait for it to finish before acknowledging recovery.")
            self._close_recovered_observations(schedule_id, actor)
            updated = self.db_manager.resolve_recovery_required(schedule_id, note, actor, expected_revision,
                                                               expected_updated_at=expected_updated_at)
            if updated and not isinstance(updated, ScheduleReview):
                self._active_schedules[schedule_id] = updated
        self._refresh_manual_recovery_state(force=True)
        if updated and self.config.enable_notifications and self._notification_service:
            try:
                self._notification_service.manual_recovery_cleared(updated, note=note, actor=actor)
            except Exception:
                logger.exception('Manual recovery acknowledgement notification failed')
        return updated

    def _close_recovered_observations(self, schedule_id, actor):
        self._require_robot_absent()
        for observation in self.run_log_monitor.snapshots():
            if observation.schedule_id != schedule_id:
                continue
            if observation.execution_id in self._owned_execution_ids:
                raise SafetyConflict('An execution is still owned by the scheduler. Wait for it to finish.')
            execution = self.run_log_monitor.store.execution(observation.execution_id)
            if execution is None:
                raise SafetyConflict('Execution history is missing. Review SQLite storage health before acknowledging recovery.')
            if execution.status in ('running', 'pending', 'queued'):
                execution.status = 'cancelled'
                execution.end_time = datetime.now()
                execution.error_message = f'Closed after manual recovery acknowledged by {actor}; process no longer running'
                self.run_log_monitor.process_finished(execution)
                snapshot = self.db_manager.get_schedule_by_id(observation.schedule_id) or ScheduledExperiment.from_dict(observation.schedule)
                self._finalize_execution(snapshot, execution)
            else:
                self.run_log_monitor.finish(execution.execution_id)

    def _require_robot_absent(self):
        try:
            if self.process_monitor.get_hamilton_processes():
                raise SafetyConflict('HxRun is running. Close it and confirm the robot is ready before continuing.')
        except SafetyConflict:
            raise
        except Exception as exc:
            raise SafetyConflict('HxRun state could not be established. Retry after process monitoring is available.') from exc

    def resume_queued_jobs(self, expected_revision, actor):
        with self._schedules_lock, self._jobs_lock:
            self._require_robot_absent()
            if self._owned_execution_ids or self.run_log_monitor.snapshots():
                raise SafetyConflict('Reconcile unfinished executions before resuming.')
            state = self.db_manager.sqlite_db.resume_dispatch(expected_revision, actor)
        self._refresh_manual_recovery_state(force=True)
        return state

    @contextmanager
    def database_change_guard(self):
        """Serialize a short database transaction with the final scheduler launch check."""
        from backend.services.scheduling.pyhsl_runner import require_no_active_run
        require_no_active_run()
        with self._schedules_lock, self._jobs_lock:
            if self._database_restore_active:
                raise SafetyConflict('Database restore is in progress.')
            state = self._refresh_manual_recovery_state(force=True)
            if not state.storage_healthy:
                raise StorageUnavailable('Scheduler safety state unavailable')
            if state.active or state.resume_required or self._owned_execution_ids or self.run_log_monitor.snapshots() or self.pyhsl_runner.unfinished():
                raise SafetyConflict('Finish the run and resolve recovery before changing the database.')
            self._require_robot_absent()
            yield

    @contextmanager
    def database_restore_guard(self):
        """Reserve database access without holding scheduler locks during SQL restore."""
        with self.database_change_guard():
            self._database_restore_active = True
        try:
            yield
        finally:
            with self._schedules_lock, self._jobs_lock:
                self._database_restore_active = False

    @contextmanager
    def launch_guard(self, experiment, execution):
        # Hold these only for the final state check, durable write and Popen, never the run.
        with self._schedules_lock, self._jobs_lock:
            if self._database_restore_active:
                raise SafetyConflict('Database restore is in progress.')
            state = self._refresh_manual_recovery_state(force=True)
            if not state.storage_healthy:
                raise StorageUnavailable('Scheduler safety state unavailable')
            if state.active or state.resume_required:
                raise SafetyConflict('Manual recovery or explicit Resume is required before dispatch.')
            maintenance = self.db_manager.get_hxrun_maintenance_state()
            if maintenance.enabled:
                raise SafetyConflict('HxRun maintenance is enabled')
            self._require_robot_absent()
            # Serialize other in-process safety writers through Popen. The running-row
            # transaction below independently rechecks flags, including maintenance.
            with self.db_manager.sqlite_db._connection_lock:
                current = self.db_manager.get_schedule_by_id(execution.schedule_id)
                if not current or isinstance(current, ScheduleReview) or not current.is_active or current.archived or current.recovery_required:
                    raise SafetyConflict('The schedule is no longer eligible to run')
                reason = self._simulation_block_reason(current)
                if reason:
                    raise SafetyConflict(reason)
                execution.status = 'running'
                execution.start_time = execution.start_time or datetime.now()
                if not self.db_manager.store_job_execution(execution):
                    self.db_manager.sqlite_db._safety_fault = True
                    raise StorageUnavailable('Could not persist execution; launch was blocked')
                yield

    def require_manual_recovery(self, schedule_id: str, note: Optional[str], actor: str, expected_updated_at=None) -> Optional[ScheduledExperiment]:
        """Public entrypoint for marking a schedule as requiring manual recovery."""
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            schedule = self.db_manager.get_schedule_by_id(schedule_id)
            if not schedule:
                logger.error("Schedule %s not found when marking manual recovery", schedule_id)
                return None
        return self._apply_manual_recovery(schedule, note, actor, expected_updated_at)

    def resolve_manual_recovery(self, schedule_id, note, actor, expected_revision, expected_updated_at=None):
        schedule = self.db_manager.get_schedule_by_id(schedule_id)
        history = self.db_manager.sqlite_db.get_execution_history(schedule_id, limit=1)
        if (schedule and schedule.runner == 'pyhsl') or (history and history[0].get('pyhsl') is not None):
            self.pyhsl_runner.acknowledge(schedule_id)
        return self._clear_manual_recovery(schedule_id, note, actor, expected_revision, expected_updated_at)

    def get_manual_recovery_state(self) -> ManualRecoveryState:
        """Return the current manual recovery state."""
        state = self._refresh_manual_recovery_state(force=True)
        if state.resume_required and not state.resume_block_reason:
            try:
                self._require_robot_absent()
            except SafetyConflict as exc:
                state.resume_block_reason = str(exc)
        return state

    def _ensure_queue_runtime_entry(
        self,
        schedule_id: str,
        *,
        queued_at: Optional[datetime] = None,
    ) -> QueueRuntimeState:
        """Ensure runtime metadata exists for a queue entry."""
        state = self._queue_runtime.get(schedule_id)
        if state is None:
            state = QueueRuntimeState(queued_at=queued_at or datetime.now())
            self._queue_runtime[schedule_id] = state
            return state
        if queued_at and queued_at < state.queued_at:
            state.queued_at = queued_at
        return state

    def _set_queue_waiting_reason(self, schedule_id: str, reason: Optional[str]) -> None:
        """Update queue wait reason for UI/runtime status."""
        with self._jobs_lock:
            state = self._ensure_queue_runtime_entry(schedule_id)
            state.waiting_reason = reason

    def _get_queue_waiting_reason(self, schedule_id: str) -> Optional[str]:
        """Return queue wait reason snapshot."""
        with self._jobs_lock:
            state = self._queue_runtime.get(schedule_id)
            return state.waiting_reason if state else None

    def _resolve_dispatch_block_reason(self, schedule: ScheduledExperiment) -> Optional[str]:
        """Return a human-readable reason when worker dispatch should pause."""
        manual_state = self._refresh_manual_recovery_state(force=True)
        if not manual_state.storage_healthy:
            return 'Scheduler safety state unavailable'
        try:
            hxrun_state = self.hxrun_maintenance_service.get_state(force_refresh=True)
        except Exception:
            return 'Scheduler safety state unavailable'
        if hxrun_state.enabled:
            detail = hxrun_state.reason or "maintenance mode is enabled"
            return f"HxRun maintenance enabled: {detail}"

        manual_state = self._refresh_manual_recovery_state()
        if manual_state.active:
            detail = manual_state.experiment_name or manual_state.schedule_id or "another schedule"
            return f"Manual recovery active: {detail}"

        if manual_state.resume_required:
            return 'Recovery acknowledged; waiting for explicit Resume queued jobs'

        if schedule.recovery_required:
            return "Schedule requires manual recovery before next run"

        if self.run_log_monitor.snapshots() or self.pyhsl_runner.unfinished():
            return "Waiting for the previous scheduled execution to finish or be reconciled"

        if self.process_monitor.is_hamilton_running():
            return "Hamilton HxRun.exe is currently busy"

        if schedule.runner == 'pyhsl':
            from backend.services.scheduling.pyhsl_runner import dispatch_reason
            return dispatch_reason()
        return self._simulation_block_reason(schedule)

    def _simulation_block_reason(self, schedule: ScheduledExperiment) -> Optional[str]:
        if schedule.runner == 'pyhsl':
            return None
        from backend.services.scheduling.experiment_executor import ExecutionConfig
        return simulation_block_reason(schedule.mode, ExecutionConfig().hxrun_path)

    def _wait_until_dispatch_ready(self, schedule_id: str, execution: Optional[JobExecution] = None) -> Optional[ScheduledExperiment]:
        """Block worker dispatch until all runtime gates are clear."""
        last_reason: Optional[str] = None
        wait_seconds = max(1.0, min(self.config.check_interval_seconds, 5.0))

        while self._running:
            with self._schedules_lock:
                schedule = self._active_schedules.get(schedule_id)

            if schedule is None:
                self._set_queue_waiting_reason(schedule_id, "Schedule removed before dispatch")
                return None

            if not schedule.is_active:
                self._set_queue_waiting_reason(schedule_id, "Schedule deactivated before dispatch")
                return None

            try:
                reason = self._resolve_dispatch_block_reason(schedule)
            except Exception:
                logger.exception('Could not check dispatch readiness')
                reason = 'Scheduler safety state unavailable'
            if schedule.runner == 'pyhsl':
                from backend.services.scheduling.pyhsl_runner import UNAVAILABLE_REASON
                if reason == UNAVAILABLE_REASON:
                    since = self._pyhsl_unavailable_since.setdefault(schedule_id, time.monotonic())
                    if execution and time.monotonic() - since >= 180:
                        try:
                            self._notify_execution_event(schedule, execution, 'pyhsl_unavailable', {'note': reason})
                        except Exception:
                            logger.exception('PyHSL wait notification failed')
                else:
                    self._pyhsl_unavailable_since.pop(schedule_id, None)
            if reason is None:
                if last_reason:
                    logger.info(
                        "Dispatch gate cleared for %s; worker starting execution",
                        schedule.experiment_name,
                    )
                self._set_queue_waiting_reason(schedule_id, None)
                return schedule

            if reason != last_reason:
                logger.info("Queue wait for %s: %s", schedule.experiment_name, reason)
                last_reason = reason
                if execution and is_simulation_reason(reason):
                    try:
                        self._notify_execution_event(schedule, execution, 'simulation_mode_mismatch', {'note': reason})
                    except Exception:
                        # Notification storage/contact lookup failures must not release the gate or kill the worker.
                        logger.exception('Simulation Mode wait notification failed')
            self._set_queue_waiting_reason(schedule_id, reason)
            time.sleep(wait_seconds)

        self._set_queue_waiting_reason(schedule_id, "Scheduler stopping")
        return None

    def _job_worker_loop(self) -> None:
        """Single-worker queue consumer for scheduled jobs."""
        logger.info("Scheduler job worker loop started")
        while self._running or not self._job_queue.empty():
            if self._running:
                try:
                    unfinished = self.pyhsl_runner.unfinished()
                    for execution in unfinished:
                        with run_log_context(execution.execution_id):
                            schedule = self.db_manager.get_schedule_by_id(execution.schedule_id)
                            if schedule is not None:
                                with self._jobs_lock:
                                    self._running_jobs.add(schedule.schedule_id)
                                self._execute_job(schedule, execution)
                except Exception:
                    # A locked database must not end the only worker; the next pass retries.
                    logger.exception('Could not resume unfinished PyHSL executions')
                    unfinished = True
                if unfinished:
                    self._stop_event.wait(1)
                    continue
            try:
                item = self._job_queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                if item is None:
                    continue
                experiment, execution = item
                with run_log_context(execution.execution_id):
                    schedule_id = experiment.schedule_id
                    with self._jobs_lock:
                        self._ensure_queue_runtime_entry(schedule_id)
                        if schedule_id in self._running_jobs:
                            logger.debug(
                                "Schedule %s already running in worker loop; skipping duplicate item",
                                experiment.experiment_name,
                            )
                            self._queued_backlog.discard(schedule_id)
                            continue

                    ready_schedule = self._wait_until_dispatch_ready(schedule_id, execution)
                    if ready_schedule is None:
                        wait_reason = self._get_queue_waiting_reason(schedule_id)
                        if wait_reason and wait_reason != "Scheduler stopping":
                            execution.status = "cancelled"
                            execution.error_message = wait_reason
                            execution.end_time = datetime.now()
                            self.db_manager.store_job_execution(execution)
                        with self._jobs_lock:
                            self._running_jobs.discard(schedule_id)
                            self._queued_backlog.discard(schedule_id)
                            self._queue_runtime.pop(schedule_id, None)
                        continue

                    with self._jobs_lock:
                        self._running_jobs.add(schedule_id)
                        self._queued_backlog.discard(schedule_id)
                        state = self._queue_runtime.get(schedule_id)
                        if state:
                            state.waiting_reason = None
                    self._execute_job(ready_schedule, execution)
            finally:
                self._job_queue.task_done()
        logger.info("Scheduler job worker loop stopped")

    def _scheduler_loop(self):
        """Main scheduler loop running in background thread"""
        logger.info("Scheduler loop started")
        
        # Initial startup delay
        self._stop_event.wait(self.config.startup_delay_seconds)
        
        while self._running:
            try:
                current_time = datetime.now()

                # Check for due jobs
                due_jobs = self._find_due_jobs(current_time)
                
                # Process due jobs
                for experiment in due_jobs:
                    self._process_due_job(experiment, current_time)
                
                # Update next execution times for interval schedules
                self._update_interval_schedules(current_time)

                # Watchdog: evaluate running executions for alerts
                self._evaluate_active_executions(current_time)
                
                # Clean up completed jobs
                self._cleanup_completed_jobs()
                
                # Sleep until next check
                self._stop_event.wait(self.config.check_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(self.config.check_interval_seconds)
        
        logger.info("Scheduler loop stopped")
    
    def _find_due_jobs(self, current_time: datetime) -> List[ScheduledExperiment]:
        """Find jobs that are due for execution"""
        due_jobs = []

        with self._jobs_lock:
            running_snapshot = set(self._running_jobs)
            queued_snapshot = set(self._queued_backlog)

        with self._schedules_lock:
            for experiment in self._active_schedules.values():
                if (not experiment.is_active or
                    not experiment.start_time or
                    experiment.schedule_id in running_snapshot or
                    experiment.schedule_id in queued_snapshot or
                    experiment.recovery_required):
                    continue
                
                start_time = self._ensure_naive_datetime(experiment.start_time)
                if start_time <= current_time:
                    due_jobs.append(experiment)
        
        return due_jobs
    
    def _process_due_job(self, experiment: ScheduledExperiment, current_time: datetime):
        """Process a job that is due for execution"""
        try:
            with self._jobs_lock:
                if (
                    experiment.schedule_id in self._queued_backlog
                    or experiment.schedule_id in self._running_jobs
                ):
                    logger.debug(
                        "Schedule %s already pending or running; skipping duplicate dispatch",
                        experiment.experiment_name,
                    )
                    return
                self._queued_backlog.add(experiment.schedule_id)
                self._ensure_queue_runtime_entry(experiment.schedule_id, queued_at=current_time)
            # Create job execution record
            execution = JobExecution(
                execution_id="",  # Will be auto-generated
                schedule_id=experiment.schedule_id,
                status="pending",
                start_time=None,
            )
            
            with run_log_context(execution.execution_id):
                # Store execution record
                if not self.db_manager.store_job_execution(execution):
                    logger.error(f"Failed to store job execution: {experiment.schedule_id}")
                    with self._jobs_lock:
                        self._running_jobs.discard(experiment.schedule_id)
                        self._queued_backlog.discard(experiment.schedule_id)
                        self._queue_runtime.pop(experiment.schedule_id, None)
                    return
            
                logger.info("Queued due job: %s", experiment.experiment_name)
            
                # Queue job for single-worker execution
                self._job_queue.put((experiment, execution))

        except Exception as e:
            logger.error(f"Error processing due job: {e}")
            with self._jobs_lock:
                self._queued_backlog.discard(experiment.schedule_id)
                self._queue_runtime.pop(experiment.schedule_id, None)

    def _execute_job(self, experiment: ScheduledExperiment, execution: JobExecution):
        """Run one method and share completion handling with restart reconciliation."""
        pyhsl = execution.pyhsl is not None or experiment.runner == 'pyhsl'
        timeout_context = {}
        with self._jobs_lock:
            self._owned_execution_ids.add(execution.execution_id)
        try:
            if pyhsl:
                self.pyhsl_runner.execute(experiment, execution)
            else:
                from backend.services.scheduling.experiment_executor import ExperimentExecutor, resolve_timeout_context
                executor = ExperimentExecutor(self.run_log_monitor, self.launch_guard)
                timeout_context = resolve_timeout_context(experiment, datetime.now())
                execution.status = 'running'
                execution.start_time = datetime.now()
                with self.launch_guard(experiment, execution):
                    pass
                success = executor.execute_experiment(experiment, execution, timeout_context=timeout_context)
                execution.status = 'completed' if success else 'failed'
        except Exception as exc:
            logger.exception('Error executing %s', experiment.experiment_name)
            if not pyhsl:
                execution.status = 'failed'
                execution.error_message = str(exc)
            # PyHSL keeps its running row and receipt for the next resume pass.
        finally:
            if not pyhsl:
                execution.end_time = datetime.now()
                try:
                    self.run_log_monitor.process_finished(execution)
                    self._finalize_execution(experiment, execution, bool(timeout_context.get('terminate_schedule')))
                except Exception:
                    logger.exception('Could not finalize execution %s', execution.execution_id)
            with self._jobs_lock:
                self._owned_execution_ids.discard(execution.execution_id)
                self._running_jobs.discard(experiment.schedule_id)

    def _finalize_execution(self, experiment, execution, terminate_schedule=False):
        if execution.start_time and execution.end_time:
            execution.duration_minutes = int((execution.end_time - execution.start_time).total_seconds() / 60)
        # Serialize the reload and commit with edits, preserving changes made during the run.
        with self._schedules_lock:
            schedule = self.db_manager.get_schedule_by_id(experiment.schedule_id) or experiment
            if not isinstance(schedule, ScheduleReview):
                if terminate_schedule:
                    schedule.is_active = False
                elif execution.status in {'completed', 'failed'}:
                    if self._resolve_interval_hours(schedule):
                        schedule.start_time = self._calculate_next_execution_time(schedule)
                    else:
                        schedule.is_active = False
            committed = self.db_manager.finalize_job_execution(
                execution, schedule,
                touch_updated_at=terminate_schedule or execution.status in {'completed', 'failed'})
            if committed and not isinstance(schedule, ScheduleReview) and schedule.schedule_id in self._active_schedules:
                self._active_schedules[schedule.schedule_id] = schedule
        if execution.status == "failed" and execution.pyhsl is None:
            self._handle_failed_execution(schedule, execution)
        self.run_log_monitor.finish(execution.execution_id)
        with self._jobs_lock:
            self._running_jobs.discard(schedule.schedule_id)
            self._queued_backlog.discard(schedule.schedule_id)
            self._queue_runtime.pop(schedule.schedule_id, None)

    def _handle_failed_execution(self, experiment: ScheduledExperiment, execution: JobExecution) -> None:
        """Handle logic after a failed execution, including manual recovery enforcement."""
        note: Optional[str] = None
        try:
            observation = self.run_log_monitor.snapshot(execution.execution_id)
            if observation:
                if observation.run_state in {"Aborted", "Error"}:
                    note = f"Hamilton reported run {observation.run_guid} as {observation.run_state}"
        except Exception as exc:
            logger.debug("Abort state lookup failed for %s: %s", experiment.experiment_name, exc)
        message = (execution.error_message or "").lower()
        unknown = execution.error_message == NOT_REPORTED_COMPLETE
        if unknown:
            note = execution.error_message
        if not note:
            if ("return code 64" in message or
                "hamilton reported last run" in message or
                "manual abort" in message):
                note = execution.error_message or "Hamilton reported last run as aborted"

        aborted = bool(note) or self._message_indicates_abort(execution.error_message)
        if aborted:
            context: Dict[str, Any] = {
                "error_message": execution.error_message or "Unknown error",
            }
            if note:
                context["note"] = note
            else:
                context["schedule_active"] = experiment.is_active
                if experiment.is_active and self._resolve_interval_hours(experiment):
                    context["next_run_time"] = experiment.start_time.isoformat()
            if execution.start_time and execution.end_time:
                context["runtime_minutes"] = round(
                    (execution.end_time - execution.start_time).total_seconds() / 60, 1
                )
            self._notify_execution_event(experiment, execution, "execution_failed" if unknown else "aborted", context)

            if note:
                self._apply_manual_recovery(experiment, note, actor="scheduler")
            return

        # Non-abort failure (e.g., launch or execution error): notify contacts.
        context = {"error_message": execution.error_message or "Unknown error"}
        context["schedule_active"] = experiment.is_active
        if experiment.is_active and self._resolve_interval_hours(experiment):
            context["next_run_time"] = experiment.start_time.isoformat()
        self._notify_execution_event(experiment, execution, "execution_failed", context)

    def _update_interval_schedules(self, current_time: datetime):
        """Update next execution times for interval-based schedules"""
        with self._schedules_lock:
            for experiment in self._active_schedules.values():
                interval_hours = self._resolve_interval_hours(experiment)
                if (
                    experiment.is_active
                    and
                    interval_hours
                    and experiment.start_time
                    and experiment.schedule_id in self._running_jobs
                    and self._ensure_naive_datetime(experiment.start_time) <= current_time
                ):
                    # Calculate next execution time for jobs that are actively running.
                    next_time = self._calculate_next_execution_time(experiment)
                    if next_time != experiment.start_time:
                        experiment.start_time = next_time
                        # Update in database without touching concurrency timestamp
                        self.db_manager.update_scheduled_experiment(
                            experiment,
                            touch_updated_at=False,
                        )
                        logger.debug(
                            "Updated next execution time for %s: %s",
                            experiment.experiment_name,
                            next_time,
                        )

    def _calculate_next_execution_time(self, experiment: ScheduledExperiment) -> datetime:
        """Calculate the next execution time for an experiment"""
        current_time = datetime.now()
        
        interval_hours = self._resolve_interval_hours(experiment)
        if interval_hours:
            if experiment.start_time and self._ensure_naive_datetime(experiment.start_time) > current_time:
                return experiment.start_time

            # Calculate next interval time
            next_time = current_time + timedelta(hours=interval_hours)

            # Round to the nearest minute for cleaner scheduling
            next_time = next_time.replace(second=0, microsecond=0)

            return next_time

        if experiment.schedule_type == "once":
            # For "once" schedules, if they're completed they should be deactivated
            # If still active, return the original start time
            return experiment.start_time or current_time
        
        else:
            # Default to immediate execution
            return current_time
    
    def _validate_experiment(self, experiment: ScheduledExperiment) -> bool:
        """Use the same stored-field rules as API writes."""
        try:
            checked = check_schedule(experiment.to_dict())
            experiment.schedule_type = checked.schedule_type
            experiment.interval_hours = checked.interval_hours
            return True
        except ValueError as exc:
            logger.error('Experiment validation failed: %s', exc)
            return False

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

    # ------------------------------------------------------------------
    # Execution watchdog helpers
    # ------------------------------------------------------------------

    def _evaluate_active_executions(self, current_time: datetime) -> None:
        """Observe logs and reconcile scheduler runs surviving an app restart."""
        for observation in self.run_log_monitor.snapshots():
            with run_log_context(observation.execution_id):
                try:
                    state = self.run_log_monitor.check(observation.execution_id)
                    with self._jobs_lock:
                        owned = observation.execution_id in self._owned_execution_ids
                    if owned or not state:
                        continue
                    execution = self.run_log_monitor.store.execution(state.execution_id)
                    if execution and execution.status in {"completed", "failed", "cancelled"}:
                        self._finalize_execution(self.db_manager.get_schedule_by_id(state.schedule_id) or ScheduledExperiment.from_dict(state.schedule), execution, state.terminate_schedule)
                    elif state.state == "terminal":
                        if state.process_finished:
                            execution = JobExecution.from_dict(state.execution)
                        else:
                            execution = execution or JobExecution.from_dict(state.execution)
                            execution.status = "completed" if state.run_state == "Complete" else "failed"
                            execution.end_time = self._ensure_naive_datetime(datetime.fromisoformat(state.end_time)) if state.end_time else current_time
                            if execution.status == "failed":
                                execution.error_message = f"Hamilton reported run {state.run_guid} as {state.run_state}"
                        self._finalize_execution(self.db_manager.get_schedule_by_id(state.schedule_id) or ScheduledExperiment.from_dict(state.schedule), execution, state.terminate_schedule)
                except Exception:
                    logger.exception("Failed to observe execution %s", observation.execution_id)

    def _notify_execution_event(
        self,
        experiment: ScheduledExperiment,
        execution: JobExecution,
        event_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        contact_ids = set(experiment.notification_contacts or [])
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

        stored_entry = self.db_manager.create_notification_log(log_entry)
        if not stored_entry:
            logger.error("Delivery log unavailable; notification %s was not sent", event_type)
            return

        try:
            observation = self.run_log_monitor.snapshot(execution.execution_id)
            result = self._notification_service.schedule_alert(
                experiment,
                execution,
                contacts=contacts,
                trigger=event_type,
                context=context,
                **({"trace_path": Path(observation.trace_path) if observation.trace_path else None,
                    "exact_trace": True} if observation else
                   {"exact_trace": True} if event_type == "simulation_mode_mismatch" or execution.pyhsl is not None or experiment.runner == 'pyhsl' else {}),
            )
            status = "sent" if result.sent else "partial" if result.delivery_status == "partial" else "error"
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
        # For now, we just ensure runtime queue metadata remains consistent.
        with self._jobs_lock:
            active_job_ids = set(self._active_schedules.keys())
            self._running_jobs &= active_job_ids
            self._queued_backlog &= active_job_ids
            live_runtime_ids = self._running_jobs | self._queued_backlog
            for schedule_id in list(self._queue_runtime.keys()):
                if schedule_id not in live_runtime_ids:
                    self._queue_runtime.pop(schedule_id, None)


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
