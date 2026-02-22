from datetime import datetime, timedelta
from dataclasses import dataclass

from backend.models import JobExecution, ScheduledExperiment, TimeoutConfig
import backend.services.scheduling.experiment_executor as executor_module


@dataclass
class _PreRunResult:
    success: bool = True
    cleanup_required: bool = False
    steps: list = None
    failure_reason: str = ""


class StubPreExecutionPipeline:
    run_calls = 0

    def __init__(self, _db_manager):
        return

    def run(self, _experiment):
        StubPreExecutionPipeline.run_calls += 1
        return _PreRunResult(success=True, cleanup_required=False, steps=[])

    def cleanup(self, _steps):
        return


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


def test_executor_timeout_cleanup_requires_cleanup_path(monkeypatch):
    monkeypatch.setattr(executor_module, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(executor_module, "PreExecutionPipeline", StubPreExecutionPipeline)

    executor = executor_module.ExperimentExecutor()
    schedule = _make_schedule(
        TimeoutConfig(
            timeout_minutes=5,
            action="run_cleanup_and_terminate",
            cleanup_experiment_name="Cleanup",
            cleanup_experiment_path=None,
        )
    )
    execution = JobExecution(execution_id="exec-1", schedule_id=schedule.schedule_id, status="pending")

    success = executor.execute_experiment(schedule, execution, timeout_context={})

    assert success is False
    assert "cleanup_experiment_path" in (execution.error_message or "")


def test_executor_uses_timeout_cleanup_target_and_skips_pre_run(monkeypatch):
    captured = {"name": None, "path": None}
    StubPreExecutionPipeline.run_calls = 0

    monkeypatch.setattr(executor_module, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(executor_module, "PreExecutionPipeline", StubPreExecutionPipeline)

    def _fake_execute(self, experiment, execution):
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

    monkeypatch.setattr(executor_module.ExperimentExecutor, "_execute_hamilton_command", _fake_execute)

    executor = executor_module.ExperimentExecutor()
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
