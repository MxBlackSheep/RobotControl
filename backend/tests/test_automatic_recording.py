"""Automatic recording start/stop races.

Failure cases:
- Disabled automation unexpectedly starts recording.
- Starting/stopping automation fails to start/stop recording and experiment monitoring.
- Stop or a manual override during the startup delay still starts recording.
- Stop returns while the startup thread is still running.
- A failed camera start leaves a recording camera recorded as active.
- A manual stop does not stop automation or is not remembered as an override.
- An error while stopping replaces STOPPING with ERROR.
"""

import threading
from collections import deque
from datetime import datetime
from unittest.mock import Mock, patch, PropertyMock

import pytest

from backend.services.automatic_recording import AutomaticRecordingService
from backend.services.automatic_recording_types import AutomationState, ArchiveResult


@pytest.fixture(autouse=True)
def reset_singleton():
    AutomaticRecordingService._instance = None
    yield
    if AutomaticRecordingService._instance:
        try:
            AutomaticRecordingService._instance.stop_automatic_recording()
        except Exception:
            pass
        AutomaticRecordingService._instance = None


@pytest.fixture
def mock_config():
    config = {
        "enabled": True,
        "startup_delay_seconds": 2,
        "primary_camera_id": 0,
        "rolling_clips_limit": 10,
        "experiment_folders_limit": 5,
        "archive_duration_minutes": 15,
        "experiment_check_interval": 5,
        "storage_cleanup_interval": 60,
    }
    with patch('backend.services.automatic_recording.AUTO_RECORDING_CONFIG', config):
        yield config


@pytest.fixture
def mock_camera_service():
    service = Mock()
    service.automatic_camera_id.side_effect = lambda fallback: fallback
    service.detect_cameras.return_value = [{"id": 0}, {"id": 1}]
    service.start_recording.return_value = True
    service.stop_recording.return_value = True
    service.rolling_clips = deque(maxlen=10)
    service.clips_lock = threading.Lock()
    return service


def test_startup_cancellation_during_delay(mock_config):
    service = AutomaticRecordingService()
    assert service.start_automatic_recording() is True
    assert service.current_state == AutomationState.STARTING
    service.stop_automatic_recording()
    service.startup_thread.join(timeout=5)
    assert service.current_state == AutomationState.STOPPED


def test_startup_with_manual_override_during_delay(mock_config):
    service = AutomaticRecordingService()
    service.start_automatic_recording()
    assert service.current_state == AutomationState.STARTING
    service.manual_override_active = True
    service.startup_thread.join(timeout=5)
    assert service.current_state == AutomationState.STOPPED


def test_stop_with_startup_thread_running(mock_config):
    service = AutomaticRecordingService()
    service.start_automatic_recording()
    assert service.startup_thread.is_alive()
    assert service.stop_automatic_recording() is True
    assert service.current_state == AutomationState.STOPPED
    assert not service.startup_thread.is_alive()


def test_camera_recording_start_service_failure(mock_config, mock_camera_service):
    service = AutomaticRecordingService()
    mock_camera_service.start_recording.return_value = False
    with patch.object(type(service), 'camera_service', new_callable=PropertyMock, return_value=mock_camera_service):
        assert service._start_camera_recording(0) is False
        mock_camera_service.start_recording.assert_called_once_with(0)
        assert service.recording_camera_id is None


def test_manual_stop_override(mock_config, mock_camera_service):
    service = AutomaticRecordingService()
    service.current_state = AutomationState.ACTIVE
    service.recording_camera_id = 0
    with patch.object(type(service), 'camera_service', new_callable=PropertyMock, return_value=mock_camera_service):
        result = service.handle_manual_override("stop")
    assert result["success"] is True
    assert result["manual_override"] is True
    assert service.manual_override_active is True
    assert service.current_state == AutomationState.STOPPED


def test_error_during_stopping_state(mock_config):
    service = AutomaticRecordingService()
    service.current_state = AutomationState.STOPPING
    service._handle_error("Error during stop")
    assert service.current_state == AutomationState.STOPPING
    assert service.error_count == 1


@pytest.fixture
def mock_storage_manager():
    """Mock storage manager for testing"""
    mock_manager = Mock()

    # Mock storage statistics
    mock_manager.get_storage_statistics.return_value = {
        "rolling_clips_count": 5,
        "experiment_folders_count": 3
    }

    # Mock archive operation
    mock_archive_result = ArchiveResult(
        success=True,
        archive_path="/test/archive/path",
        clips_archived=5,
        archive_size_bytes=1024 * 1024  # 1MB
    )
    mock_manager.archive_experiment_videos.return_value = mock_archive_result

    return mock_manager


@pytest.fixture
def mock_experiment_monitor():
    """Mock experiment monitor for testing"""
    mock_monitor = Mock()

    mock_monitor.is_monitoring_active.return_value = False
    mock_monitor.start_monitoring.return_value = True
    mock_monitor.stop_monitoring.return_value = True
    mock_monitor.add_completion_callback = Mock()

    # Mock monitor stats
    mock_stats = Mock()
    mock_stats.last_check_time = datetime.now()
    mock_monitor.get_monitor_stats.return_value = mock_stats

    return mock_monitor


def test_start_automatic_recording_when_disabled(mock_config):
    """Test starting automatic recording when disabled in config"""
    with patch.dict(mock_config, {"enabled": False}):
        service = AutomaticRecordingService()

        success = service.start_automatic_recording()

        assert success is False
        assert service.current_state == AutomationState.STOPPED


def test_complete_startup_workflow(mock_config, mock_camera_service, mock_storage_manager, mock_experiment_monitor):
    """Test complete startup workflow from initialization to active recording"""
    service = AutomaticRecordingService()

    # Mock all dependencies
    with patch.object(type(service), 'camera_service', new_callable=PropertyMock, return_value=mock_camera_service):
        with patch.object(type(service), 'storage_manager', new_callable=PropertyMock, return_value=mock_storage_manager):
            with patch.object(type(service), 'experiment_monitor', new_callable=PropertyMock, return_value=mock_experiment_monitor):

                try:
                    # Start automatic recording
                    success = service.start_automatic_recording()
                    assert success is True
                    assert service.current_state == AutomationState.STARTING

                    # Wait for startup to complete
                    service.startup_thread.join(timeout=10)

                    # Verify final state
                    assert service.current_state == AutomationState.ACTIVE
                    assert service.recording_camera_id == 0
                    assert service.manual_override_active is False

                    # Verify all services were called correctly
                    mock_camera_service.detect_cameras.assert_called()
                    mock_camera_service.start_recording.assert_called_with(0)
                    mock_experiment_monitor.add_completion_callback.assert_called()
                    mock_experiment_monitor.start_monitoring.assert_called()
                finally:
                    # Stop while the camera and monitor are still replaced by fixtures.
                    service.stop_automatic_recording()


def test_complete_shutdown_workflow(mock_config, mock_camera_service, mock_storage_manager, mock_experiment_monitor):
    """Test complete shutdown workflow"""
    service = AutomaticRecordingService()

    # Setup active recording state
    service.current_state = AutomationState.ACTIVE
    service.recording_camera_id = 0

    mock_experiment_monitor.is_monitoring_active.return_value = True

    with patch.object(type(service), 'camera_service', new_callable=PropertyMock, return_value=mock_camera_service):
        with patch.object(type(service), 'experiment_monitor', new_callable=PropertyMock, return_value=mock_experiment_monitor):

            success = service.stop_automatic_recording(manual_stop=True)

            assert success is True
            assert service.current_state == AutomationState.STOPPED
            assert service.recording_camera_id is None
            assert service.manual_override_active is True

            # Verify cleanup
            mock_camera_service.stop_recording.assert_called_with(0)
            mock_experiment_monitor.stop_monitoring.assert_called()
