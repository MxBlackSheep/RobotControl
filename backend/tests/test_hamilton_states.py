import asyncio
import json
from unittest.mock import Mock, patch


from backend.services.experiment_monitor import ExperimentMonitor
from backend.services.experiment_monitor import ExperimentStateType


def test_pause_and_resume_do_not_fire_recording_completion():
    callback = Mock()
    callback.__name__ = "recording_completion"
    monitor = ExperimentMonitor(on_complete=callback)
    for raw in [1, 2, 1, 2]:
        with patch.object(monitor, "_query_latest_experiment", return_value={
            "run_guid": "same-run", "method_name": "Simulator", "run_state": raw
        }):
            monitor._check_experiment_state()
        assert monitor.current_experiment.is_in_progress
        assert monitor.current_experiment.is_running is (raw == 1)
        assert monitor.current_experiment.run_state == (
            ExperimentStateType.RUNNING if raw == 1 else ExperimentStateType.PAUSED)
        callback.assert_not_called()
    with patch.object(monitor, "_query_latest_experiment", return_value={
        "run_guid": "same-run", "method_name": "Simulator", "run_state": 128
    }):
        monitor._check_experiment_state()
        monitor._check_experiment_state()
    callback.assert_called_once()
