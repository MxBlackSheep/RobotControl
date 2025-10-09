"""
Automatic Recording Service

Main orchestration service for automatic camera recording feature.
Integrates camera service, experiment monitoring, and storage management
to provide seamless automatic recording with experiment-synchronized archiving.
"""

import asyncio
import threading
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from backend.config import AUTO_RECORDING_CONFIG
from backend.services.automatic_recording_types import (
    AutomationStatus, AutomationState, ExperimentState
)
from backend.services.storage_manager import get_storage_manager
from backend.services.experiment_monitor import get_experiment_monitor

# Configure logging
logger = logging.getLogger(__name__)


class AutomaticRecordingService:
    """
    Main orchestration service for automatic camera recording.
    
    Features:
    - Automatic recording startup with configurable delay
    - Integration with camera service for recording management
    - Experiment completion detection and video archiving
    - Manual override support for user control
    - Comprehensive status tracking and error handling
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AutomaticRecordingService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize automatic recording service"""
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        
        # Configuration from backend config
        self.startup_delay_seconds = AUTO_RECORDING_CONFIG["startup_delay_seconds"]
        self.primary_camera_id = AUTO_RECORDING_CONFIG["primary_camera_id"]
        self.enabled = AUTO_RECORDING_CONFIG["enabled"]
        
        # Service state
        self.current_state = AutomationState.STOPPED
        self.recording_camera_id: Optional[int] = None
        self.automation_start_time: Optional[datetime] = None
        self.last_experiment_check: Optional[datetime] = None
        self.manual_override_active = False
        
        # Error tracking
        self.error_message: Optional[str] = None
        self.error_count = 0
        self.last_error_time: Optional[datetime] = None
        
        # Threading
        self.startup_thread: Optional[threading.Thread] = None
        self.cleanup_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        
        # Periodic cleanup configuration
        self.cleanup_interval_minutes = AUTO_RECORDING_CONFIG.get("cleanup_interval_minutes", 30)
        self.cleanup_threshold_buffer = AUTO_RECORDING_CONFIG.get("cleanup_threshold_buffer", 10)
        
        # Service references (lazy loaded)
        self._camera_service = None
        self._storage_manager = None
        self._experiment_monitor = None
        
        # Archive statistics
        self.total_experiments_archived = 0
        
        logger.info("AutoRecording | event=init | enabled=%s | startup_delay_s=%s", self.enabled, self.startup_delay_seconds)
    
    @property
    def camera_service(self):
        """Lazy-loaded camera service"""
        if self._camera_service is None:
            try:
                from backend.services.camera import get_camera_service
                self._camera_service = get_camera_service()
            except ImportError as e:
                logger.error(f"Failed to load camera service: {e}")
                self._camera_service = None
        return self._camera_service
    
    @property
    def storage_manager(self):
        """Lazy-loaded storage manager"""
        if self._storage_manager is None:
            self._storage_manager = get_storage_manager()
        return self._storage_manager
    
    @property
    def experiment_monitor(self):
        """Lazy-loaded experiment monitor"""
        if self._experiment_monitor is None:
            self._experiment_monitor = get_experiment_monitor()
        return self._experiment_monitor
    
    def start_automatic_recording(self) -> bool:
        """
        Start automatic recording with configured startup delay
        
        Returns:
            True if automatic recording startup initiated successfully
        """
        try:
            with self.state_lock:
                if not self.enabled:
                    logger.info("AutoRecording | event=start_skipped | reason=disabled")
                    return False
                
                if self.current_state != AutomationState.STOPPED:
                    logger.warning("AutoRecording | event=start_ignored | state=%s", self.current_state.value)
                    return False
                
                logger.info("AutoRecording | event=start_requested | delay_s=%s", self.startup_delay_seconds)
                
                # Update state
                self.current_state = AutomationState.STARTING
                self.automation_start_time = datetime.now()
                self.stop_event.clear()
                self.manual_override_active = False
                self.error_message = None
                
                # Start delayed startup thread
                self.startup_thread = threading.Thread(
                    target=self._delayed_startup_worker,
                    name="AutoRecordingStartup",
                    daemon=True
                )
                self.startup_thread.start()
                
                # Start periodic cleanup thread
                self.cleanup_thread = threading.Thread(
                    target=self._periodic_cleanup_worker,
                    name="AutoRecordingCleanup",
                    daemon=True
                )
                self.cleanup_thread.start()
                
                logger.info("AutoRecording | event=start_queued")
                logger.info("AutoRecording | event=start_queued_cleanup | cleanup_interval_min=%s", self.cleanup_interval_minutes)
                return True
                
        except Exception as e:
            error_msg = f"Failed to start automatic recording: {e}"
            logger.error(error_msg)
            self._handle_error(error_msg)
            return False
    
    def stop_automatic_recording(self, manual_stop: bool = False) -> bool:
        """
        Stop automatic recording and cleanup
        
        Args:
            manual_stop: Whether this is a manual stop (user-initiated)
            
        Returns:
            True if stop was successful
        """
        try:
            with self.state_lock:
                if self.current_state == AutomationState.STOPPED:
                    logger.info("AutoRecording | event=stop_ignored | reason=already_stopped")
                    return True
                
                logger.info("AutoRecording | event=stop_requested | manual=%s", manual_stop)
                
                # Update state
                self.current_state = AutomationState.STOPPING
                self.stop_event.set()
                
                if manual_stop:
                    self.manual_override_active = True
            
            # Stop experiment monitoring
            if self.experiment_monitor and self.experiment_monitor.is_monitoring_active():
                self.experiment_monitor.stop_monitoring()
                logger.info("AutoRecording | event=monitoring_stopped")
            
            # Stop camera recording if we started it
            if self.recording_camera_id is not None and self.camera_service:
                try:
                    success = self.camera_service.stop_recording(self.recording_camera_id)
                    if success:
                        logger.info("AutoRecording | event=recording_stopped | camera_id=%s", self.recording_camera_id)
                    else:
                        logger.warning("AutoRecording | event=recording_stop_failed | camera_id=%s", self.recording_camera_id)
                except Exception as e:
                    logger.error(f"Error stopping camera recording: {e}")
            
            # Wait for threads to finish
            if self.startup_thread and self.startup_thread.is_alive():
                self.startup_thread.join(timeout=5)
            if self.cleanup_thread and self.cleanup_thread.is_alive():
                self.cleanup_thread.join(timeout=5)
            
            # Update final state
            with self.state_lock:
                self.current_state = AutomationState.STOPPED
                self.recording_camera_id = None
                
            logger.info("AutoRecording | event=stop_complete")
            return True
            
        except Exception as e:
            error_msg = f"Error stopping automatic recording: {e}"
            logger.error(error_msg)
            self._handle_error(error_msg)
            return False
    
    def get_automation_status(self) -> AutomationStatus:
        """
        Get comprehensive automation status
        
        Returns:
            AutomationStatus with current state and statistics
        """
        with self.state_lock:
            # Get storage statistics
            storage_stats = {}
            try:
                storage_stats = self.storage_manager.get_storage_statistics()
            except Exception as e:
                logger.debug(f"Could not get storage statistics: {e}")
            
            # Get experiment monitor statistics
            monitor_stats = None
            try:
                if self.experiment_monitor:
                    monitor_stats = self.experiment_monitor.get_monitor_stats()
            except Exception as e:
                logger.debug(f"Could not get monitor statistics: {e}")
            
            status = AutomationStatus(
                is_active=(self.current_state == AutomationState.ACTIVE),
                state=self.current_state,
                recording_camera_id=self.recording_camera_id,
                startup_delay_seconds=self.startup_delay_seconds,
                rolling_clips_limit=AUTO_RECORDING_CONFIG["rolling_clips_limit"],
                experiment_folders_limit=AUTO_RECORDING_CONFIG["experiment_folders_limit"],
                archive_duration_minutes=AUTO_RECORDING_CONFIG["archive_duration_minutes"],
                last_experiment_check=monitor_stats.last_check_time if monitor_stats else None,
                rolling_clips_count=storage_stats.get("rolling_clips_count", 0),
                experiment_folders_count=storage_stats.get("experiment_folders_count", 0),
                total_experiments_archived=self.total_experiments_archived,
                error_message=self.error_message,
                error_count=self.error_count,
                last_error_time=self.last_error_time
            )
            
            return status
    
    def handle_manual_override(self, action: str, camera_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Handle manual recording override actions
        
        Args:
            action: "start" or "stop"
            camera_id: Camera ID for manual start (uses primary if None)
            
        Returns:
            Dictionary with operation result
        """
        try:
            if action == "stop":
                # Manual stop - disable automatic restart
                success = self.stop_automatic_recording(manual_stop=True)
                return {
                    "success": success,
                    "action": "stop",
                    "message": "Automatic recording stopped manually" if success else "Failed to stop recording",
                    "manual_override": True
                }
                
            elif action == "start":
                # Manual start - override delay and start immediately
                target_camera_id = camera_id or self.primary_camera_id
                
                with self.state_lock:
                    if self.current_state == AutomationState.ACTIVE:
                        return {
                            "success": False,
                            "action": "start",
                            "message": "Automatic recording is already active",
                            "camera_id": self.recording_camera_id
                        }
                    
                    # Reset override flag and start immediately
                    self.manual_override_active = False
                
                success = self._start_camera_recording(target_camera_id)
                
                if success:
                    # Start experiment monitoring
                    self._setup_experiment_monitoring()
                    
                    with self.state_lock:
                        self.current_state = AutomationState.ACTIVE
                    
                    return {
                        "success": True,
                        "action": "start",
                        "message": f"Manual recording started on camera {target_camera_id}",
                        "camera_id": target_camera_id,
                        "manual_override": True
                    }
                else:
                    return {
                        "success": False,
                        "action": "start", 
                        "message": f"Failed to start manual recording on camera {target_camera_id}",
                        "camera_id": target_camera_id
                    }
            
            else:
                return {
                    "success": False,
                    "message": f"Unknown manual override action: {action}"
                }
                
        except Exception as e:
            error_msg = f"Manual override error: {e}"
            logger.error(error_msg)
            self._handle_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def _delayed_startup_worker(self):
        """Worker thread that handles delayed automatic recording startup"""
        try:
            logger.info("AutoRecording | event=delay_wait | seconds=%s", self.startup_delay_seconds)
            
            # Wait for startup delay (with early exit on stop signal)
            if self.stop_event.wait(timeout=self.startup_delay_seconds):
                logger.info("AutoRecording | event=start_cancelled | reason=stop_during_delay")
                with self.state_lock:
                    self.current_state = AutomationState.STOPPED
                return
            
            # Check if we should still start (no manual override)
            with self.state_lock:
                if self.manual_override_active or self.current_state != AutomationState.STARTING:
                    logger.info("AutoRecording | event=start_cancelled | reason=state_change")
                    self.current_state = AutomationState.STOPPED
                    return
            
            logger.info("AutoRecording | event=recording_starting | camera_id=%s", self.primary_camera_id)
            
            # Start camera recording
            success = self._start_camera_recording(self.primary_camera_id)
            
            if success:
                # Setup experiment monitoring
                self._setup_experiment_monitoring()
                
                # Perform startup cleanup to handle accumulated files
                self._startup_cleanup()
                
                # Update state to active
                with self.state_lock:
                    self.current_state = AutomationState.ACTIVE
                
                logger.info("AutoRecording | event=active | camera_id=%s", self.primary_camera_id)
            else:
                error_msg = f"Failed to start camera recording on camera {self.primary_camera_id}"
                logger.error(error_msg)
                self._handle_error(error_msg)
                
                with self.state_lock:
                    self.current_state = AutomationState.ERROR
                    
        except Exception as e:
            error_msg = f"Error in automatic recording startup: {e}"
            logger.error(error_msg)
            self._handle_error(error_msg)
            
            with self.state_lock:
                self.current_state = AutomationState.ERROR
    
    def _start_camera_recording(self, camera_id: int) -> bool:
        """
        Start camera recording on specified camera
        
        Args:
            camera_id: Camera ID to start recording on
            
        Returns:
            True if recording started successfully
        """
        try:
            if not self.camera_service:
                logger.error("Camera service not available")
                return False
            
            # Detect cameras if not already done
            cameras = self.camera_service.detect_cameras()
            if not cameras:
                logger.warning("AutoRecording | event=recording_start_failed | reason=no_cameras")
                return False
            
            # Check if specified camera exists
            camera_found = any(cam["id"] == camera_id for cam in cameras)
            if not camera_found:
                logger.error("AutoRecording | event=recording_start_failed | reason=camera_missing | camera_id=%s", camera_id)
                return False
            
            # Start recording
            success = self.camera_service.start_recording(camera_id)
            
            if success:
                with self.state_lock:
                    self.recording_camera_id = camera_id
                logger.info("AutoRecording | event=recording_started | camera_id=%s", camera_id)
                return True
            else:
                logger.error("AutoRecording | event=recording_start_failed | reason=camera_start_error | camera_id=%s", camera_id)
                return False
                
        except Exception as e:
            logger.error("AutoRecording | event=recording_start_exception | camera_id=%s | error=%s", camera_id, e)
            return False
    
    def _setup_experiment_monitoring(self):
        """Setup experiment monitoring with completion callback"""
        try:
            if not self.experiment_monitor:
                logger.warning("AutoRecording | event=monitoring_unavailable")
                return
            
            # Register completion callback for video archiving
            self.experiment_monitor.add_completion_callback(self._on_experiment_complete)
            
            # Start monitoring if not already active
            if not self.experiment_monitor.is_monitoring_active():
                self.experiment_monitor.start_monitoring()
                logger.info("AutoRecording | event=monitoring_started")
            else:
                logger.debug("Experiment monitoring already active")
                
        except Exception as e:
            logger.error(f"Error setting up experiment monitoring: {e}")
    
    def _on_experiment_complete(self, completed_experiment: ExperimentState):
        """
        Callback for when an experiment completes - triggers video archiving
        
        Args:
            completed_experiment: The experiment that just completed
        """
        try:
            logger.info("AutoRecording | event=experiment_complete | method=%s", completed_experiment.method_name)
            
            if not self.camera_service:
                logger.error("Cannot archive videos - camera service not available")
                return
            
            storage_manager = self.storage_manager
            if not storage_manager:
                logger.error("Cannot archive videos - storage manager unavailable")
                return

            # Derive a stable experiment identifier usable in folder names
            try:
                exp_id = int(completed_experiment.run_guid[:8], 16) % 1000000
            except Exception:
                exp_id = hash(completed_experiment.run_guid) % 1000000
            experiment_identifier = str(exp_id)
            
            archive_result = storage_manager.archive_experiment_videos(
                experiment_id=experiment_identifier,
                method_name=completed_experiment.method_name,
                rolling_clips=self.camera_service.rolling_clips,
                clips_lock=self.camera_service.clips_lock
            )
            
            if archive_result.success:
                with self.state_lock:
                    self.total_experiments_archived += 1
                
                logger.info(
                    "AutoRecording | event=archive_success | clips=%s | method=%s | size_mb=%.1f | path=%s",
                    archive_result.clips_archived,
                    completed_experiment.method_name,
                    archive_result.archive_size_mb,
                    archive_result.archive_path,
                )
            else:
                logger.error(
                    "AutoRecording | event=archive_failed | method=%s | error=%s",
                    completed_experiment.method_name,
                    archive_result.error_message or "unknown error",
                )
                for warning in archive_result.warnings:
                    logger.debug("AutoRecording | archive_warning | detail=%s", warning)
            
            # Trigger storage cleanup to maintain limits
            self._schedule_storage_cleanup()
            
        except Exception as e:
            logger.error("AutoRecording | event=archive_handler_error | error=%s", e)
    
    def _schedule_storage_cleanup(self):
        """Schedule storage cleanup in background thread"""
        def cleanup_worker():
            try:
                cleanup_result = self.storage_manager.cleanup_all_storage()
                logger.info("AutoRecording | event=storage_cleanup | removed=%s | freed_mb=%.1f", cleanup_result.total_items_removed, cleanup_result.storage_freed_bytes / (1024*1024))
            except Exception as e:
                logger.error("AutoRecording | event=storage_cleanup_error | error=%s", e)
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _startup_cleanup(self):
        """Perform cleanup on startup to handle files that accumulated while system was offline"""
        try:
            stats = self.storage_manager.get_storage_statistics()
            rolling_clips_count = stats["rolling_clips_count"]
            rolling_clips_limit = AUTO_RECORDING_CONFIG["rolling_clips_limit"]
            
            if rolling_clips_count > rolling_clips_limit:
                logger.info("AutoRecording | event=startup_cleanup_needed | clips=%s | limit=%s", rolling_clips_count, rolling_clips_limit)
                cleanup_result = self.storage_manager.cleanup_rolling_clips()
                logger.info("AutoRecording | event=startup_cleanup_done | removed=%s | freed_mb=%.1f", cleanup_result.rolling_clips_removed, cleanup_result.storage_freed_bytes / (1024*1024))
            else:
                logger.info("AutoRecording | event=startup_cleanup_skipped | clips=%s | limit=%s", rolling_clips_count, rolling_clips_limit)
                
        except Exception as e:
            logger.error("AutoRecording | event=startup_cleanup_error | error=%s", e)
    
    def _periodic_cleanup_worker(self):
        """Background worker that performs periodic storage cleanup"""
        logger.info("AutoRecording | event=cleanup_worker_start | interval_min=%s", self.cleanup_interval_minutes)
        
        while not self.stop_event.is_set():
            try:
                # Wait for the cleanup interval or stop signal
                if self.stop_event.wait(timeout=self.cleanup_interval_minutes * 60):
                    logger.info("AutoRecording | event=cleanup_worker_stop")
                    break
                
                # Check if we should perform cleanup
                should_cleanup = False
                
                try:
                    # Get current storage statistics
                    stats = self.storage_manager.get_storage_statistics()
                    rolling_clips_count = stats["rolling_clips_count"]
                    rolling_clips_limit = AUTO_RECORDING_CONFIG["rolling_clips_limit"]
                    
                    # Check if we're exceeding the threshold
                    if rolling_clips_count > rolling_clips_limit + self.cleanup_threshold_buffer:
                        should_cleanup = True
                        logger.info("AutoRecording | event=cleanup_threshold | clips=%s | limit=%s | buffer=%s", rolling_clips_count, rolling_clips_limit, self.cleanup_threshold_buffer)
                    elif rolling_clips_count > rolling_clips_limit:
                        # Also cleanup if we're over the basic limit (but log as maintenance)
                        should_cleanup = True
                        logger.info("AutoRecording | event=cleanup_maintenance | clips=%s | limit=%s", rolling_clips_count, rolling_clips_limit)
                    
                except Exception as e:
                    # Fallback: perform cleanup anyway if we can't get stats
                    should_cleanup = True
                    logger.warning("AutoRecording | event=cleanup_stats_missing | error=%s", e)
                
                # Perform cleanup if needed
                if should_cleanup:
                    try:
                        cleanup_result = self.storage_manager.cleanup_rolling_clips()
                        logger.info("AutoRecording | event=cleanup_periodic | removed=%s | freed_mb=%.1f", cleanup_result.rolling_clips_removed, cleanup_result.storage_freed_bytes / (1024*1024))
                    except Exception as e:
                        logger.error("AutoRecording | event=cleanup_periodic_error | error=%s", e)
                else:
                    # Log periodic status even when no cleanup is needed
                    try:
                        stats = self.storage_manager.get_storage_statistics()
                        logger.debug(f"Periodic cleanup check - {stats['rolling_clips_count']} clips "
                                    f"({stats['rolling_clips_size_mb']:.1f}MB), within limits")
                    except Exception:
                        pass
                
            except Exception as e:
                logger.error("AutoRecording | event=cleanup_worker_error | error=%s", e)
                # Continue running despite errors
                
        logger.info("AutoRecording | event=cleanup_worker_done")
    
    def _handle_error(self, error_message: str):
        """Handle error state and update statistics"""
        with self.state_lock:
            self.error_message = error_message
            self.error_count += 1
            self.last_error_time = datetime.now()
            
            # Update state to error if not stopping
            if self.current_state != AutomationState.STOPPING:
                self.current_state = AutomationState.ERROR
    
    def is_active(self) -> bool:
        """Check if automatic recording is currently active"""
        with self.state_lock:
            return self.current_state == AutomationState.ACTIVE
    
    def is_enabled(self) -> bool:
        """Check if automatic recording is enabled in configuration"""
        return self.enabled
    
    def get_current_experiment(self) -> Optional[ExperimentState]:
        """Get current experiment being monitored"""
        try:
            if self.experiment_monitor:
                return self.experiment_monitor.get_current_experiment()
        except Exception as e:
            logger.debug(f"Error getting current experiment: {e}")
        return None


# Global instance management
_automatic_recording_service = None
_service_lock = threading.Lock()


def get_automatic_recording_service() -> AutomaticRecordingService:
    """Get the global automatic recording service instance (singleton pattern)"""
    global _automatic_recording_service
    if _automatic_recording_service is None:
        with _service_lock:
            if _automatic_recording_service is None:
                _automatic_recording_service = AutomaticRecordingService()
    return _automatic_recording_service
