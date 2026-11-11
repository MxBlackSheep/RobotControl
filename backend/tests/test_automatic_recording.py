"""Automatic recording timing: delay cancellation, late camera, start failure,
stop racing a camera start, watcher starts only after recording and never after stop.
Uses a disposable fake runtime; never opens hardware or SQL.
"""
import threading
from unittest.mock import Mock, patch
import pytest
from backend.services import automatic_recording as automatic

@pytest.fixture
def setup():
    camera = Mock()
    camera.runtime.identity = "selected"
    camera.runtime.on_recording_started = None
    monitor = Mock()
    monitor.is_running = False
    def start_monitor():
        monitor.is_running = True
    def stop_monitor():
        monitor.is_running = False
    monitor.start_monitoring.side_effect = start_monitor
    monitor.stop_monitoring.side_effect = stop_monitor
    def run(action, **kwargs):
        if action == "start" and camera.runtime.on_recording_started:
            camera.runtime.on_recording_started(0)
    camera.runtime.run.side_effect = run
    with patch('backend.services.camera.get_camera_service', return_value=camera), patch.object(automatic, 'get_storage_manager', return_value=Mock()), patch.object(automatic, 'ExperimentMonitor', return_value=monitor):
        service = automatic.AutomaticRecordingService()
        service.startup_delay_seconds = 0
        yield service, camera, monitor
        service.stop_automatic_recording()

def test_stop_during_delay(setup):
    service, camera, monitor = setup
    service.startup_delay_seconds = 60
    service.start_automatic_recording()
    assert service.stop_automatic_recording()
    assert not service.startup_thread.is_alive()
    assert not any(call.args[0] == 'start' for call in camera.runtime.run.call_args_list)
    monitor.start_monitoring.assert_not_called()

def test_late_camera_starts_watcher_only_when_recording(setup):
    service, camera, monitor = setup
    camera.runtime.run.side_effect = ValueError('No selected camera is available')
    service.start_automatic_recording()
    service.startup_thread.join(2)
    monitor.start_monitoring.assert_not_called()
    callback = camera.runtime.on_recording_started
    assert callback is not None
    callback(0)
    monitor.start_monitoring.assert_called_once()
    camera.runtime.run.side_effect = None
    assert service.stop_automatic_recording()
    callback(0)  # a callback already captured by a completing connection
    assert monitor.start_monitoring.call_count == 1
    assert not monitor.is_running

def test_stop_racing_start_waits_and_stops_watcher(setup):
    service, camera, monitor = setup
    entered, release = threading.Event(), threading.Event()
    def run(action, **kwargs):
        if action == 'start':
            entered.set()
            assert release.wait(2)
            callback = camera.runtime.on_recording_started
            if callback:
                callback(0)
    camera.runtime.run.side_effect = run
    service.start_automatic_recording()
    assert entered.wait(2)
    stopped = threading.Event()
    worker = threading.Thread(target=lambda: (service.stop_automatic_recording(), stopped.set()))
    worker.start()
    assert not stopped.wait(.05)
    release.set()
    worker.join(2)
    assert stopped.is_set()
    assert not monitor.is_running
    assert camera.runtime.run.call_args.args[0] == 'stop'

def test_success_starts_and_stops_once(setup):
    service, camera, monitor = setup
    service.start_automatic_recording()
    service.startup_thread.join(2)
    monitor.start_monitoring.assert_called_once()
    service.stop_automatic_recording()
    assert not monitor.is_running
