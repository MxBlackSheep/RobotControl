from backend.models import ScheduledExperiment
from backend.services.scheduling.pre_execution import PreExecutionPipeline


class StubSchedulingDatabaseManager:
    def __init__(self, *, flag_success: bool = True, table_success: bool = True, evoyeast_success: bool = True):
        self.flag_success = flag_success
        self.table_success = table_success
        self.evoyeast_success = evoyeast_success
        self.calls = []

    def reset_all_scheduled_to_run_flags(self) -> bool:
        self.calls.append("reset_all")
        return self.flag_success

    def set_scheduled_to_run_flag(self, experiment_name: str, value: bool) -> bool:
        self.calls.append(("set_flag", experiment_name, value))
        return self.flag_success

    def reset_hamilton_tables(self, experiment_name: str, tables=None) -> bool:
        self.calls.append(("reset_tables", experiment_name, tables))
        return self.table_success

    def set_exclusive_evoyeast_experiment(self, experiment_id: str) -> bool:
        self.calls.append(("set_evoyeast", experiment_id))
        return self.evoyeast_success


def make_experiment(prerequisites=None) -> ScheduledExperiment:
    return ScheduledExperiment(
        schedule_id="",
        experiment_name="Demo",
        experiment_path=r"C:\\Hamilton\\Methods\\demo.med",
        schedule_type="once",
        prerequisites=prerequisites or [],
    )


def test_pipeline_runs_configured_steps_and_cleans_up():
    manager = StubSchedulingDatabaseManager()
    pipeline = PreExecutionPipeline(manager)
    experiment = make_experiment(["ScheduledToRun", "ResetHamiltonTables:Experiments,Runtime"])

    run = pipeline.run(experiment)
    assert run.success is True
    assert run.cleanup_required is True
    assert ("reset_tables", "Demo", ["Experiments", "Runtime"]) in manager.calls

    pipeline.cleanup(run.steps)
    assert ("set_flag", "Demo", False) in manager.calls


def test_pipeline_unknown_step_returns_failure():
    manager = StubSchedulingDatabaseManager()
    pipeline = PreExecutionPipeline(manager)
    experiment = make_experiment(["UnknownStep"])

    run = pipeline.run(experiment)
    assert run.success is False
    assert run.cleanup_required is False
    assert run.failure_reason is not None
    assert manager.calls == []  # No calls should occur for unknown steps


def test_pipeline_failure_short_circuits_and_cleans_previous_steps():
    manager = StubSchedulingDatabaseManager(flag_success=False)
    pipeline = PreExecutionPipeline(manager)
    experiment = make_experiment(["ScheduledToRun", "ResetHamiltonTables"])

    run = pipeline.run(experiment)
    assert run.success is False
    assert run.cleanup_required is False
    assert any(call == "reset_all" for call in manager.calls)
    # set_flag should not be called with False because step never succeeded
    assert ("set_flag", "Demo", False) not in manager.calls


def test_evo_yeast_prerequisite_sets_flag():
    manager = StubSchedulingDatabaseManager()
    pipeline = PreExecutionPipeline(manager)
    experiment = make_experiment(["EvoYeastExperiment:42|set"])

    run = pipeline.run(experiment)
    assert run.success is True
    assert ("set_evoyeast", "42") in manager.calls


def test_evo_yeast_prerequisite_noop_skips_update():
    manager = StubSchedulingDatabaseManager()
    pipeline = PreExecutionPipeline(manager)
    experiment = make_experiment(["EvoYeastExperiment:42|none"])

    run = pipeline.run(experiment)
    assert run.success is True
    assert all(call[0] != "set_evoyeast" for call in manager.calls)


def test_evo_yeast_prerequisite_failure_propagates():
    manager = StubSchedulingDatabaseManager(evoyeast_success=False)
    pipeline = PreExecutionPipeline(manager)
    experiment = make_experiment(["EvoYeastExperiment:42|set"])

    run = pipeline.run(experiment)
    assert run.success is False
    assert any(call == ("set_evoyeast", "42") for call in manager.calls)

