"""Start recording after the configured delay and archive each observed run end."""
import logging
import threading

from backend.config import AUTO_RECORDING_CONFIG
from backend.services.storage_manager import get_storage_manager
from backend.services.experiment_monitor import ExperimentMonitor
from backend.services.experiment_monitor import ExperimentState

logger = logging.getLogger(__name__)


class AutomaticRecordingService:
    def __init__(self):
        from backend.services.camera import get_camera_service
        self.camera_service = get_camera_service()
        self.storage_manager = get_storage_manager()
        self.experiment_monitor = ExperimentMonitor(on_complete=self._on_experiment_complete)
        self.startup_delay_seconds = AUTO_RECORDING_CONFIG["startup_delay_seconds"]
        self.startup_thread = None
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.state_lock = threading.Lock()

    def start_automatic_recording(self) -> bool:
        with self.state_lock:
            if not AUTO_RECORDING_CONFIG["enabled"] or not self.stop_event.is_set():
                return False
            if self.startup_thread and self.startup_thread.is_alive():
                return False
            self.stop_event.clear()
            self.camera_service.runtime.on_recording_started = self._on_camera_started
            self.startup_thread = threading.Thread(
                target=self._delayed_startup_worker, name="AutoRecordingStartup", daemon=True)
            self.startup_thread.start()
        return True

    def _delayed_startup_worker(self):
        if self.stop_event.wait(self.startup_delay_seconds):
            return
        try:
            runtime = self.camera_service.runtime
            # A saved identity selects its current index; only first use needs the default.
            camera_id = None if runtime.identity else AUTO_RECORDING_CONFIG["primary_camera_id"]
            runtime.run("start", camera_id=camera_id)
        except Exception as exc:
            logger.warning("AutoRecording | event=recording_start_failed | error=%s", exc)

    def _on_camera_started(self, camera_id):
        with self.state_lock:
            if not self.stop_event.is_set() and not self.experiment_monitor.is_running:
                self.experiment_monitor.start_monitoring()

    def stop_automatic_recording(self) -> bool:
        self.stop_event.set()
        with self.state_lock:
            self.camera_service.runtime.on_recording_started = None
        if self.startup_thread and self.startup_thread.is_alive():
            self.startup_thread.join()
        self.experiment_monitor.stop_monitoring()
        try:
            self.camera_service.runtime.run("stop")
            return True
        except Exception as exc:
            logger.warning("AutoRecording | event=recording_stop_failed | error=%s", exc)
            return False

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
            
            self.camera_service.wait_for_stored_clips(storage_manager.archive_duration_minutes)
            archive_result = storage_manager.archive_experiment_videos(
                experiment_id=experiment_identifier,
                method_name=completed_experiment.method_name,
            )
            
            if archive_result.success:
                logger.info(
                    "AutoRecording | event=archive_success | clips=%s | method=%s | size_mb=%.1f | path=%s",
                    archive_result.clips_archived,
                    completed_experiment.method_name,
                    archive_result.archive_size_bytes / (1024 * 1024),
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
            self.storage_manager.cleanup_experiment_folders()
            
        except Exception as e:
            logger.error("AutoRecording | event=archive_handler_error | error=%s", e)
    

_automatic_recording_service = None
_service_lock = threading.Lock()


def get_automatic_recording_service() -> AutomaticRecordingService:
    global _automatic_recording_service
    with _service_lock:
        if _automatic_recording_service is None:
            _automatic_recording_service = AutomaticRecordingService()
        return _automatic_recording_service
