import asyncio
import json
from unittest.mock import Mock, patch

import pytest

from backend.services.experiment_monitor import ExperimentMonitor
from backend.services.automatic_recording_types import ExperimentStateType


def test_pause_and_resume_do_not_fire_recording_completion():
    monitor = ExperimentMonitor()
    callback = Mock()
    callback.__name__ = "recording_completion"
    monitor.add_completion_callback(callback)
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


def test_paused_monitoring_api_keeps_progress_placeholder():
    from backend.api.monitoring import get_current_experiments
    monitor = ExperimentMonitor()
    experiment = monitor._create_experiment_state({"run_guid": "run", "run_state": 2})
    with patch("backend.api.monitoring.get_experiment_monitor") as get_monitor:
        get_monitor.return_value.get_current_experiment.return_value = experiment
        result = json.loads(asyncio.run(get_current_experiments(current_user={})).body)
    assert result["data"]["experiments"][0]["Status"] == "Paused"
    assert result["data"]["experiments"][0]["RawState"] == "2"
    assert result["data"]["experiments"][0]["Progress"] == 50
