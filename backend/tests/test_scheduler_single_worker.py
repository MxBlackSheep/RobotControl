import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional

from backend.models import JobExecution, ManualRecoveryState, ScheduledExperiment, TimeoutConfig
from backend.services.scheduling import scheduler_engine
from backend.services.scheduling.scheduler_engine import SchedulerConfig, SchedulerEngine
import backend.services.scheduling.experiment_executor as executor_module


class StubMonitor:
    def start_monitoring(self) -> bool:
        return True

    def stop_monitoring(self) -> None:
        return None

    def is_hamilton_running(self) -> bool:
        return False


class ToggleBusyMonitor(StubMonitor):
    def __init__(self, busy: bool = True):
        self.busy = busy

    def is_hamilton_running(self) -> bool:
        return self.busy


class StubHxRunMaintenanceService:
    class _State:
        enabled = False
        reason = None

        def to_dict(self):
            return {
                "enabled": False,
                "reason": None,
                "updated_by": None,
                "updated_at": None,
            }

    def is_enabled(self) -> bool:
        return False

    def get_state(self, force_refresh: bool = False):
        return self._State()


class StubDBManager:
    def __init__(self):
        self.manual_state = ManualRecoveryState()

    def initialize_schema(self) -> bool:
        return True

    def get_active_schedules(self):
        return []

    def get_schedule_by_id(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        return None

    def get_manual_recovery_state(self) -> ManualRecoveryState:
        return self.manual_state

    def get_notification_contacts(self, include_inactive: bool = False):
        return []

    def store_job_execution(self, execution: JobExecution) -> bool:
        return True

    def update_scheduled_experiment(self, experiment: ScheduledExperiment, *, touch_updated_at: bool = True) -> bool:
        return True

    def should_block_due_to_abort(self, experiment: ScheduledExperiment):
        return None

    def notification_log_exists(self, execution_id: str, event_type: str) -> bool:
        return False


class FakeExecutor:
    lock = threading.Lock()
    active_count = 0
    max_active = 0
    call_order: List[str] = []

    def __init__(self, *args, **kwargs):
        return None

    def execute_experiment(
        self,
        experiment: ScheduledExperiment,
        execution: JobExecution,
        timeout_context=None,
    ) -> bool:
        with self.lock:
            FakeExecutor.active_count += 1
            FakeExecutor.max_active = max(FakeExecutor.max_active, FakeExecutor.active_count)
        try:
            time.sleep(0.05)
            FakeExecutor.call_order.append(experiment.schedule_id)
            return True
        finally:
            with self.lock:
                FakeExecutor.active_count -= 1


def test_scheduler_uses_single_worker_queue(monkeypatch):
    FakeExecutor.call_order = []
    FakeExecutor.active_count = 0
    FakeExecutor.max_active = 0
    monkeypatch.setattr(scheduler_engine, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(scheduler_engine, "get_hamilton_process_monitor", lambda: StubMonitor())
    monkeypatch.setattr(
        scheduler_engine,
        "get_hxrun_maintenance_service",
        lambda: StubHxRunMaintenanceService(),
    )
    monkeypatch.setattr(executor_module, "ExperimentExecutor", FakeExecutor)

    engine = SchedulerEngine(SchedulerConfig(enable_notifications=False, startup_delay_seconds=0))
    current_time = datetime.now()

    schedule_a = ScheduledExperiment(
        schedule_id="sched-A",
        experiment_name="A",
        experiment_path=r"C:\\Hamilton\\Methods\\a.med",
        schedule_type="once",
        start_time=current_time,
        estimated_duration=1,
    )
    schedule_b = ScheduledExperiment(
        schedule_id="sched-B",
        experiment_name="B",
        experiment_path=r"C:\\Hamilton\\Methods\\b.med",
        schedule_type="once",
        start_time=current_time,
        estimated_duration=1,
    )

    engine._active_schedules[schedule_a.schedule_id] = schedule_a
    engine._active_schedules[schedule_b.schedule_id] = schedule_b

    engine._running = True
    worker = threading.Thread(target=engine._job_worker_loop, daemon=True)
    worker.start()

    engine._process_due_job(schedule_a, current_time)
    engine._process_due_job(schedule_b, current_time)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if engine._job_queue.empty() and not engine._running_jobs and not engine._queued_backlog:
            break
        time.sleep(0.02)

    engine._running = False
    engine._job_queue.put(None)
    worker.join(timeout=2.0)

    assert FakeExecutor.call_order == ["sched-A", "sched-B"]
    assert FakeExecutor.max_active == 1
    assert not engine._running_jobs
    assert not engine._queued_backlog


def test_busy_hamilton_keeps_job_queued_until_available(monkeypatch):
    FakeExecutor.call_order = []
    FakeExecutor.active_count = 0
    FakeExecutor.max_active = 0

    busy_monitor = ToggleBusyMonitor(busy=True)
    monkeypatch.setattr(scheduler_engine, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(scheduler_engine, "get_hamilton_process_monitor", lambda: busy_monitor)
    monkeypatch.setattr(
        scheduler_engine,
        "get_hxrun_maintenance_service",
        lambda: StubHxRunMaintenanceService(),
    )
    monkeypatch.setattr(executor_module, "ExperimentExecutor", FakeExecutor)

    engine = SchedulerEngine(SchedulerConfig(enable_notifications=False, startup_delay_seconds=0))
    now = datetime.now()
    schedule = ScheduledExperiment(
        schedule_id="sched-busy",
        experiment_name="BusyWait",
        experiment_path=r"C:\\Hamilton\\Methods\\busy.med",
        schedule_type="once",
        start_time=now,
        estimated_duration=1,
    )
    engine._active_schedules[schedule.schedule_id] = schedule

    engine._running = True
    worker = threading.Thread(target=engine._job_worker_loop, daemon=True)
    worker.start()

    engine._process_due_job(schedule, now)
    time.sleep(0.2)

    assert schedule.schedule_id in engine._queued_backlog
    assert schedule.schedule_id not in engine._running_jobs
    assert FakeExecutor.call_order == []

    queue_status = engine.get_runtime_queue_status()
    queued = [item for item in queue_status["queued_job_details"] if item["schedule_id"] == schedule.schedule_id]
    assert queued
    assert "busy" in (queued[0].get("waiting_reason") or "").lower()

    busy_monitor.busy = False

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if FakeExecutor.call_order == [schedule.schedule_id]:
            break
        time.sleep(0.02)

    engine._running = False
    engine._job_queue.put(None)
    worker.join(timeout=2.0)

    assert FakeExecutor.call_order == [schedule.schedule_id]
    assert schedule.schedule_id not in engine._queued_backlog
    assert schedule.schedule_id not in engine._running_jobs


def test_timeout_cleanup_action_disables_schedule(monkeypatch):
    FakeExecutor.call_order = []
    monkeypatch.setattr(scheduler_engine, "get_scheduling_database_manager", lambda: StubDBManager())
    monkeypatch.setattr(scheduler_engine, "get_hamilton_process_monitor", lambda: StubMonitor())
    monkeypatch.setattr(
        scheduler_engine,
        "get_hxrun_maintenance_service",
        lambda: StubHxRunMaintenanceService(),
    )
    monkeypatch.setattr(executor_module, "ExperimentExecutor", FakeExecutor)

    engine = SchedulerEngine(SchedulerConfig(enable_notifications=False, startup_delay_seconds=0))
    now = datetime.now()
    schedule = ScheduledExperiment(
        schedule_id="sched-timeout",
        experiment_name="PrimaryMethod",
        experiment_path=r"C:\\Hamilton\\Methods\\primary.med",
        schedule_type="interval",
        interval_hours=6,
        start_time=now - timedelta(minutes=45),
        estimated_duration=5,
        timeout_config=TimeoutConfig(
            timeout_minutes=5,
            action="run_cleanup_and_terminate",
            cleanup_experiment_name="CleanupMethod",
            cleanup_experiment_path=r"C:\\Hamilton\\Methods\\cleanup.med",
        ),
    )
    execution = JobExecution(
        execution_id="exec-timeout",
        schedule_id=schedule.schedule_id,
        status="pending",
        start_time=now,
    )

    engine._active_schedules[schedule.schedule_id] = schedule
    engine._execute_job(schedule, execution)

    assert schedule.is_active is False
