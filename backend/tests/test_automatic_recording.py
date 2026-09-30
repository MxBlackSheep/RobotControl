"""Automatic recording start/stop races.

Failure cases:
- Stop or a manual override during the startup delay still starts recording.
- Stop returns while the startup thread is still running.
- A failed camera start leaves a recording camera recorded as active.
- A manual stop does not stop automation or is not remembered as an override.
- An error while stopping replaces STOPPING with ERROR.
"""

import threading
from collections import deque
from unittest.mock import Mock, patch, PropertyMock

import pytest

from backend.services.automatic_recording import AutomaticRecordingService
from backend.services.automatic_recording_types import AutomationState


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
