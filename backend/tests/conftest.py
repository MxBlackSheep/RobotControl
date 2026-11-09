import pytest


@pytest.fixture
def simulation_config(tmp_path, monkeypatch):
    """Executor/dispatch checks use disposable, readable settings, never Hamilton's cfg."""
    from backend.e2e.simulation_mode_check import sample_config
    from backend.services.scheduling import experiment_executor
    config = experiment_executor.ExecutionConfig(hxrun_path=str(sample_config(tmp_path)))
    monkeypatch.setattr(experiment_executor, 'ExecutionConfig', lambda: config)
    return config
