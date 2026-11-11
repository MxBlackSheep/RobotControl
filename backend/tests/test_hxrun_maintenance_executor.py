from datetime import datetime, timedelta
from contextlib import nullcontext
import pytest
from types import SimpleNamespace

from backend.models import JobExecution, ScheduledExperiment, TimeoutConfig
import backend.services.scheduling.experiment_executor as executor_module


class StubPreExecutionPipeline:
    run_calls = 0

    def __init__(self, _db_manager):
        return

    def prepare(self, _experiment, _execution_id):
        StubPreExecutionPipeline.run_calls += 1


class StubDBManager:
    def should_block_due_to_abort(self, _experiment):
        return None


def _make_schedule(timeout_config: TimeoutConfig) -> ScheduledExperiment:
    return ScheduledExperiment(
        schedule_id="sched-1",
        experiment_name="Primary",
        experiment_path=r"C:\\Hamilton\\Methods\\primary.med",
        schedule_type="once",
        estimated_duration=30,
        start_time=datetime.now() - timedelta(minutes=60),
        timeout_config=timeout_config,
    )


def test_schedule_check_requires_cleanup_path():
    from backend.services.scheduling.schedule_check import check_schedule
    schedule = _make_schedule(TimeoutConfig(timeout_minutes=5, action='run_cleanup_and_terminate'))
    with pytest.raises(ValueError, match='cleanup_experiment_path'):
        check_schedule(schedule.to_dict())


def test_executor_uses_timeout_cleanup_target_and_skips_pre_run(monkeypatch):
    captured = {"name": None, "path": None}
    StubPreExecutionPipeline.run_calls = 0

    monkeypatch.setattr(executor_module, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(executor_module, "PreExecutionPipeline", StubPreExecutionPipeline)

    def _fake_execute(self, experiment, execution, *args):
        captured["name"] = experiment.experiment_name
        captured["path"] = experiment.experiment_path
        return executor_module.ExecutionResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            execution_time_seconds=0.1,
            command_executed="HxRun.exe ...",
        )

    monkeypatch.setattr(executor_module.ExperimentExecutor, "_execute_real_command", _fake_execute)

    executor = executor_module.ExperimentExecutor(
        SimpleNamespace(check=lambda _: SimpleNamespace(run_state="Complete")), lambda *args: nullcontext())
    schedule = _make_schedule(
        TimeoutConfig(
            timeout_minutes=5,
            action="run_cleanup_and_terminate",
            cleanup_experiment_name="CleanupMethod",
            cleanup_experiment_path=r"C:\\Hamilton\\Methods\\cleanup.med",
        )
    )
    execution = JobExecution(execution_id="exec-2", schedule_id=schedule.schedule_id, status="pending")
    timeout_context = {"timed_out": False, "action": "continue", "terminate_schedule": False}

    success = executor.execute_experiment(schedule, execution, timeout_context=timeout_context)

    assert success is True
    assert captured["name"] == "CleanupMethod"
    assert captured["path"] == r"C:\\Hamilton\\Methods\\cleanup.med"
    assert StubPreExecutionPipeline.run_calls == 0
    assert timeout_context["timed_out"] is True
    assert timeout_context["terminate_schedule"] is True
