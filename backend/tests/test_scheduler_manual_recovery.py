import datetime
from typing import List, Optional

import pytest

from backend.models import JobExecution, ManualRecoveryState, ScheduledExperiment
from backend.services.scheduling import scheduler_engine
from backend.services.scheduling.scheduler_engine import SchedulerEngine, SchedulerConfig


class StubMonitor:
    def start_monitoring(self) -> bool:
        return True

    def stop_monitoring(self) -> None:  # noqa: D401
        return None


class StubNotifications:
    def __init__(self, collector: List[tuple]):
        self._collector = collector

    def manual_recovery_required(self, schedule: ScheduledExperiment, *, note: Optional[str], actor: str) -> None:
        self._collector.append(("required", schedule.schedule_id, note, actor))

    def manual_recovery_cleared(self, schedule: ScheduledExperiment, *, note: Optional[str], actor: str) -> None:
        self._collector.append(("cleared", schedule.schedule_id, note, actor))


class StubDBManager:
    def __init__(self, schedule: ScheduledExperiment, abort_note: Optional[str] = None):
        self.schedule = schedule
        self.abort_note = abort_note or "Hamilton reported last run as Aborted"
        self.manual_state = ManualRecoveryState()

    # Lifecycle helpers -------------------------------------------------
    def initialize_schema(self) -> bool:
        return True

    def get_active_schedules(self):
        return []

    def get_scheduled_experiment(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        if schedule_id == self.schedule.schedule_id:
            return self.schedule
        return None

    # Recovery helpers --------------------------------------------------
    def mark_recovery_required(self, schedule_id: str, note: Optional[str], user: str) -> Optional[ScheduledExperiment]:
        if schedule_id != self.schedule.schedule_id:
            return None
        now = datetime.datetime.now()
        self.schedule.recovery_required = True
        self.schedule.recovery_note = note
        self.schedule.recovery_marked_by = user
        self.schedule.recovery_marked_at = now
        self.schedule.recovery_resolved_at = None
        self.schedule.recovery_resolved_by = None
        self.manual_state = ManualRecoveryState(
            active=True,
            note=note,
            schedule_id=self.schedule.schedule_id,
            experiment_name=self.schedule.experiment_name,
            triggered_by=user,
            triggered_at=now,
        )
        return self.schedule

    def resolve_recovery_required(self, schedule_id: str, note: Optional[str], user: str) -> Optional[ScheduledExperiment]:
        if schedule_id != self.schedule.schedule_id:
            return None
        now = datetime.datetime.now()
        self.schedule.recovery_required = False
        self.schedule.recovery_note = note
        self.schedule.recovery_resolved_by = user
        self.schedule.recovery_resolved_at = now
        self.manual_state = ManualRecoveryState(
            active=False,
            note=note,
            resolved_by=user,
            resolved_at=now,
        )
        return self.schedule

    def get_manual_recovery_state(self) -> ManualRecoveryState:
        return self.manual_state

    def should_block_due_to_abort(self, experiment: ScheduledExperiment) -> Optional[str]:
        return self.abort_note

    # Scheduling persistence stubs --------------------------------------
    def store_job_execution(self, execution: JobExecution) -> bool:
        return True

    def update_scheduled_experiment(self, experiment: ScheduledExperiment) -> bool:
        self.schedule = experiment
        return True

    def set_global_recovery_required(self, *args, **kwargs):  # pragma: no cover - unused in tests
        return self.manual_state


@pytest.fixture
def sample_schedule() -> ScheduledExperiment:
    return ScheduledExperiment(
        schedule_id="sched-1",
        experiment_name="Demo",
        experiment_path=r"C:\\Methods\\Demo.med",
        schedule_type="once",
        estimated_duration=30,
    )


def build_engine(monkeypatch, schedule: ScheduledExperiment, abort_note: Optional[str], notifications: List[tuple]) -> SchedulerEngine:
    db = StubDBManager(schedule, abort_note=abort_note)
    monkeypatch.setattr(scheduler_engine, "get_scheduling_database_manager", lambda: db)
    monkeypatch.setattr(scheduler_engine, "get_hamilton_process_monitor", lambda: StubMonitor())
    monkeypatch.setattr(scheduler_engine, "get_notification_service", lambda: StubNotifications(notifications))
    engine = SchedulerEngine(SchedulerConfig(enable_notifications=True))
    engine._active_schedules[schedule.schedule_id] = schedule
    return engine


def test_require_and_resolve_manual_recovery(monkeypatch, sample_schedule):
    notifications: List[tuple] = []
    engine = build_engine(monkeypatch, sample_schedule, abort_note="Hamilton reported last run as Aborted", notifications=notifications)

    updated = engine.require_manual_recovery(sample_schedule.schedule_id, "Abort detected", "tester")
    assert updated is not None
    assert updated.recovery_required is True
    assert engine._manual_recovery_cache.active is True
    assert notifications and notifications[0][0] == "required"

    cleared = engine.resolve_manual_recovery(sample_schedule.schedule_id, "Resolved", "tester")
    assert cleared is not None
    assert cleared.recovery_required is False
    assert engine._manual_recovery_cache.active is False
    assert any(tag == "cleared" for tag, *_ in notifications)


def test_handle_failed_execution_triggers_manual_recovery(monkeypatch, sample_schedule):
    notifications: List[tuple] = []
    engine = build_engine(monkeypatch, sample_schedule, abort_note="Hamilton reported last run as Aborted", notifications=notifications)

    execution = JobExecution(
        execution_id="exec-1",
        schedule_id=sample_schedule.schedule_id,
        status="failed",
        error_message="HxRun.exe failed with return code 64",
    )
    engine._handle_failed_execution(sample_schedule, execution)

    assert engine._manual_recovery_cache.active is True
    assert sample_schedule.recovery_required is True
    assert any(tag == "required" for tag, *_ in notifications)
