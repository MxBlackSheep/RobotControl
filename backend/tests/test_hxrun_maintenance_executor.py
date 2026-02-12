from dataclasses import dataclass

from backend.models import HxRunMaintenanceState, JobExecution, ScheduledExperiment
import backend.services.scheduling.experiment_executor as executor_module


@dataclass
class _PreRunResult:
    success: bool = True
    cleanup_required: bool = False
    steps: list = None
    failure_reason: str = ""


class StubPreExecutionPipeline:
    def __init__(self, _db_manager):
        return

    def run(self, _experiment):
        return _PreRunResult(success=True, cleanup_required=False, steps=[])

    def cleanup(self, _steps):
        return


class StubDBManager:
    def should_block_due_to_abort(self, _experiment):
        return None


class StubProcessMonitor:
    def is_hamilton_running(self) -> bool:
        return False


class StubMaintenanceService:
    def get_state(self, force_refresh: bool = True) -> HxRunMaintenanceState:
        return HxRunMaintenanceState(enabled=True, reason="Blocked for maintenance")

    def is_enabled(self) -> bool:
        return True


def test_executor_blocks_before_launch_when_hxrun_maintenance_enabled(monkeypatch):
    monkeypatch.setattr(executor_module, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(executor_module, "get_hamilton_process_monitor", lambda: StubProcessMonitor())
    monkeypatch.setattr(executor_module, "PreExecutionPipeline", StubPreExecutionPipeline)
    monkeypatch.setattr(executor_module, "get_hxrun_maintenance_service", lambda: StubMaintenanceService())

    def _unexpected_retry(*args, **kwargs):
        raise AssertionError("_execute_with_retry should not run when maintenance mode is enabled")

    monkeypatch.setattr(executor_module.ExperimentExecutor, "_execute_with_retry", _unexpected_retry)

    executor = executor_module.ExperimentExecutor()
    experiment = ScheduledExperiment(
        schedule_id="sched-1",
        experiment_name="Demo",
        experiment_path=r"C:\\Hamilton\\Methods\\demo.med",
        schedule_type="once",
        estimated_duration=30,
    )
    execution = JobExecution(
        execution_id="exec-1",
        schedule_id="sched-1",
        status="pending",
    )

    success = executor.execute_experiment(experiment, execution)
    assert success is False
    assert "maintenance mode" in (execution.error_message or "").lower()
