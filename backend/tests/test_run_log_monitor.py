import os
from backend.services.sqlite_safety import SafetyConflict
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.models import JobExecution, NotificationContact, ScheduledExperiment
from backend.services.notifications import ScheduleAlertResult, SchedulingNotificationService
from backend.services.scheduling.database_manager import SchedulingDatabaseManager
from backend.services.scheduling.run_log_monitor import HamiltonRunReader, RunLogMonitor, method_variants
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase

GUID = "e514f7d266d24d15ad060af512ecf6f0"
METHOD = r"C:\Methods\Actual.med"


class Clock:
    value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class Reader:
    state = "Running"
    failure = None

    def boundary(self, method):
        return datetime.now().isoformat(), "old-guid"

    def find(self, observation):
        if self.failure:
            raise self.failure
        return {"guid": GUID, "state": self.state,
                "end_time": datetime.now().isoformat() if self.state in {"Complete", "Aborted"} else None}


@pytest.fixture
def rig(tmp_path):
    db = SQLiteSchedulingDatabase(str(tmp_path / "scheduling.db"))
    manager = SchedulingDatabaseManager.__new__(SchedulingDatabaseManager)
    manager.sqlite_db = db
    manager.main_db_service = None
    schedule = ScheduledExperiment("schedule", "Primary", METHOD, "once", notification_contacts=["operator"])
    contact = NotificationContact("operator", "Operator", "operator@example.test")
    assert db.create_notification_contact(contact)
    assert db.create_schedule(schedule)
    execution = JobExecution("execution", schedule.schedule_id, "running", start_time=datetime.now())
    assert db.create_job_execution(execution)
    directory = tmp_path / "logs"
    directory.mkdir()
    trace = directory / f"Actual_{GUID}_Trace.trc"
    trace.write_text("starting\n")
    clock = Clock()
    reader = Reader()
    monitor = RunLogMonitor(manager, reader=reader, directory=directory, clock=clock)
    monitor.prepare(schedule, execution, METHOD)
    monitor.launched(execution.execution_id, 123)
    return SimpleNamespace(**locals())


def observe(r):
    return r.monitor.check(r.execution.execution_id)


def alerts(r):
    return r.db.get_notification_logs(limit=100)


def stall(r):
    observe(r)
    r.clock.advance(181)
    assert observe(r).state == "log_inactive"


def test_threshold_and_new_pause_episode(rig):
    r = rig
    assert observe(r).state == "monitoring"
    r.clock.advance(180)
    assert observe(r).state == "monitoring"
    r.clock.advance(1)
    first = observe(r)
    assert len(alerts(r)) == 1
    r.db.update_notification_log(first.active_alert_id, status="sent")
    r.clock.advance(600)
    observe(r)
    assert len(alerts(r)) == 1
    r.trace.write_text("resumed and appended\n")
    assert observe(r).state == "monitoring"
    r.clock.advance(181)
    second = observe(r)
    assert second.episode_id != first.episode_id
    assert len(alerts(r)) == 2


@pytest.mark.parametrize("raw, expected", [(1, "Running"), ("1", "Running"), (2, "Paused"), ("2", "Paused"), ("Paused", "Paused")])
def test_hamilton_state_mapping(rig, raw, expected):
    reader = HamiltonRunReader(None)
    reader.query = Mock(return_value=[{"RunGUID": GUID, "MethodName": METHOD,
                                      "EndTime": None, "RunState": raw}])
    row = reader.find(rig.monitor.snapshot(rig.execution.execution_id))
    assert row["state"] == expected
    assert row["raw_state"] == str(raw)


def test_paused_run_keeps_timer_and_restart_episode(rig):
    r = rig
    first = observe(r)
    r.clock.advance(120)
    r.reader.state = "Paused"
    assert observe(r).episode_id == first.episode_id
    r.clock.advance(61)
    paused = observe(r)
    assert paused.state == "log_inactive"
    assert alerts(r)[0].metadata["context"]["run_state"] == "Paused"
    r.db.update_notification_log(paused.active_alert_id, status="sent")
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    r.monitor.restore()
    observe(r)
    r.clock.advance(181)
    assert observe(r).episode_id == paused.episode_id
    assert len(alerts(r)) == 1
    r.reader.state = "Running"
    assert observe(r).state == "log_inactive"
    r.trace.write_text("resumed writes\n")
    assert observe(r).state == "monitoring"
    r.reader.state = "Paused"
    r.clock.advance(181)
    assert observe(r).state == "log_inactive"
    assert len(alerts(r)) == 2
    r.reader.state = "Complete"
    assert observe(r).state == "terminal"


def test_unknown_sql_code_is_reported(rig):
    rig.reader.find = lambda state: {"guid": GUID, "state": "Unknown", "raw_state": "7", "end_time": None}
    observe(rig)
    rig.clock.advance(181)
    state = observe(rig)
    assert state.state == "monitoring_unavailable"
    assert state.reason == "Unrecognized Hamilton SQL state: 7"
    assert rig.monitor.details(rig.schedule.schedule_id)["raw_run_state"] == "7"


def test_growth_resets_timer_even_if_windows_mtime_does_not_change(rig):
    r = rig
    observe(r)
    original = r.trace.stat()
    r.clock.advance(179)
    with r.trace.open("a") as stream:
        stream.write("new entry\n")
    os.utime(r.trace, ns=(original.st_atime_ns, original.st_mtime_ns))
    observe(r)
    r.clock.advance(179)
    assert observe(r).state == "monitoring"
    assert alerts(r) == []


def test_unrelated_logs_never_keep_run_alive(rig):
    r = rig
    observe(r)
    (r.directory / "Actual_11111111111111111111111111111111_Trace.trc").write_text("other run")
    (r.directory / "ComTrace_Simulator.trc").write_text("communication")
    r.clock.advance(181)
    assert observe(r).state == "log_inactive"


@pytest.mark.parametrize("state", ["Complete", "Aborted"])
def test_terminal_sql_cancels_pending_inactivity(rig, state):
    r = rig
    stall(r)
    r.reader.state = state
    assert observe(r).state == "terminal"
    assert alerts(r)[0].status == "cancelled"
    r.clock.advance(500)
    assert observe(r).state == "terminal"
    assert len(alerts(r)) == 1


@pytest.mark.parametrize("failure", [PermissionError("Locked"), LookupError("Missing SQL row"), OSError("SQL offline")])
def test_unavailable_warning_is_separate_and_recovers(rig, failure):
    r = rig
    observe(r)
    r.reader.failure = failure
    assert observe(r).state == "waiting"
    r.clock.advance(181)
    state = observe(r)
    assert state.state == "monitoring_unavailable"
    assert alerts(r)[0].event_type == "monitoring_unavailable"
    r.db.update_notification_log(state.active_alert_id, status="sent")
    r.clock.advance(300)
    observe(r)
    assert len(alerts(r)) == 1
    r.reader.failure = None
    assert observe(r).state == "monitoring"
    r.reader.failure = failure
    observe(r)
    r.clock.advance(181)
    observe(r)
    assert len(alerts(r)) == 2


def test_missing_and_ambiguous_trace_do_not_fall_back(rig):
    r = rig
    r.trace.unlink()
    (r.directory / "wrong_11111111111111111111111111111111_Trace.trc").write_text("wrong")
    assert observe(r).state == "waiting"
    r.clock.advance(181)
    assert observe(r).state == "monitoring_unavailable"
    r.trace.write_text("valid")
    assert observe(r).state == "monitoring"
    (r.directory / f"duplicate_{GUID}_Trace.trc").write_text("duplicate")
    assert "Multiple traces" in observe(r).reason


def test_truncation_rearms_and_restart_preserves_sent_episode(rig):
    r = rig
    stall(r)
    first = observe(r)
    r.db.update_notification_log(first.active_alert_id, status="sent")
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    restored = r.monitor.restore()
    assert restored[0].run_guid == GUID
    assert observe(r).state == "monitoring"
    r.clock.advance(181)
    assert observe(r).episode_id == first.episode_id
    assert len(alerts(r)) == 1
    r.trace.write_text("")
    assert observe(r).state == "monitoring"
    r.clock.advance(181)
    observe(r)
    assert len(alerts(r)) == 2


def test_restart_before_binding_and_before_confirmed_launch(rig):
    r = rig
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    r.monitor.restore()
    assert observe(r).run_guid == GUID
    r.monitor.prepare(r.schedule, r.execution, METHOD)
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    r.monitor.restore()
    assert observe(r).run_guid is None
    r.clock.advance(181)
    assert observe(r).state == "monitoring_unavailable"


def test_legacy_execution_is_never_adopted(rig):
    r = rig
    legacy = JobExecution("legacy", "schedule", "running", start_time=datetime.now())
    r.db.create_job_execution(legacy)
    r.monitor.restore()
    assert r.monitor.check("legacy").run_guid is None
    r.clock.advance(181)
    assert r.monitor.check("legacy").state == "monitoring_unavailable"


def test_configuration_is_snapshotted_at_launch(rig):
    r = rig
    r.schedule.log_inactivity_threshold_minutes = 10
    r.db.update_schedule(r.schedule)
    stall(r)
    assert observe(r).threshold_minutes == 3


def test_delivery_retries_with_same_message_id_and_revalidates(rig):
    r = rig
    stall(r)
    service = Mock()
    service.schedule_alert.side_effect = [ScheduleAlertResult(False, "subject", "body", ["operator@example.test"], error="offline"),
                                          ScheduleAlertResult(True, "subject", "body", ["operator@example.test"])]
    r.monitor.deliver_pending(lambda: service)
    assert alerts(r)[0].status == "error"
    r.clock.advance(59)
    r.monitor.deliver_pending(lambda: service)
    assert service.schedule_alert.call_count == 1
    r.clock.advance(1)
    r.monitor.deliver_pending(lambda: service)
    assert alerts(r)[0].status == "sent"
    calls = service.schedule_alert.call_args_list
    assert calls[0].kwargs["message_id"] == calls[1].kwargs["message_id"]
    assert calls[1].kwargs["trace_path"] == r.trace
    assert calls[1].kwargs["exact_trace"] is True


def test_completed_before_delivery_never_sends(rig):
    r = rig
    stall(r)
    r.reader.state = "Complete"
    service = Mock()
    r.monitor.deliver_pending(lambda: service)
    service.schedule_alert.assert_not_called()
    assert alerts(r)[0].status == "cancelled"


def test_inactive_contact_is_visible_as_delivery_error(rig):
    r = rig
    stall(r)
    r.contact.is_active = False
    r.db.update_notification_contact(r.contact)
    r.monitor.deliver_pending(lambda: Mock())
    assert alerts(r)[0].status == "error"
    assert "No active notification contacts" in alerts(r)[0].error_message


def test_sql_reader_matches_full_method_and_launch_window_then_guid(rig):
    r = rig
    reader = HamiltonRunReader(None)
    state = r.monitor.snapshot("execution")
    row = {"RunGUID": GUID, "MethodName": r"c:\METHODS\Actual.hsl", "StartTime": datetime.now(), "EndTime": None, "RunState": 1}
    reader.query = Mock(return_value=[row])
    assert reader.find(state)["guid"] == GUID
    sql, params = reader.query.call_args.args
    assert "LIKE" not in sql and "StartTime >= ?" in sql
    assert params[:2] == method_variants(METHOD)
    state.run_guid = GUID
    reader.find(state)
    assert reader.query.call_args.args[1] == (GUID,)
    reader.query.return_value = [row, row]
    with pytest.raises(LookupError, match="ambiguous"):
        reader.find(state)
    reader.query.return_value = [{**row, "MethodName": r"C:\Other\Actual.hsl"}]
    with pytest.raises(LookupError, match="does not match"):
        reader.find(state)


def test_sql_query_timeout_and_cursor_cleanup():
    connection = Mock()
    connection.cursor.return_value.description = [("RunGUID",)]
    connection.cursor.return_value.fetchall.return_value = [(GUID,)]
    from contextlib import nullcontext
    database = SimpleNamespace(get_connection=lambda: nullcontext(connection))
    assert HamiltonRunReader(database).query("SELECT RunGUID") == [{"RunGUID": GUID}]
    assert connection.timeout == 5
    connection.cursor.return_value.close.assert_called_once()


def test_schedule_migration_and_atomic_finalization(rig):
    r = rig
    with r.db._get_connection() as conn:
        conn.execute("ALTER TABLE ScheduledExperiments DROP COLUMN log_inactivity_threshold_minutes")
        conn.commit()
    reopened = SQLiteSchedulingDatabase(str(r.db.db_path))
    assert reopened.get_schedule_by_id("schedule").log_inactivity_threshold_minutes == 3
    r.execution.status = "completed"
    r.execution.end_time = datetime.now()
    r.schedule.is_active = False
    assert r.monitor.store.finalize(r.execution, r.schedule)
    r.schedule.is_active = True
    assert not r.monitor.store.finalize(r.execution, r.schedule)
    assert reopened.get_schedule_by_id("schedule").is_active is False


def test_missing_exact_attachment_still_sends_without_wrong_log(rig, monkeypatch):
    r = rig
    service = SchedulingNotificationService.__new__(SchedulingNotificationService)
    service.email = Mock()
    service.email.send.return_value = True
    monkeypatch.setattr(service, "_collect_recent_rolling_clips", lambda limit: [])
    monkeypatch.setattr(service, "_locate_trc_file", Mock(side_effect=AssertionError("Approximate lookup must not be used")))
    result = service.schedule_alert(r.schedule, r.execution, contacts=[r.contact], trigger="log_inactive", context={},
                                   trace_path=r.directory / "missing.trc", exact_trace=True)
    assert result.sent
    assert service.email.send.call_args.kwargs["attachments"] is None
    assert "no substitute" in result.body


def test_completion_during_attachment_preparation_cancels_email(rig, monkeypatch):
    r = rig
    service = SchedulingNotificationService.__new__(SchedulingNotificationService)
    service.email = Mock()
    monkeypatch.setattr(service, "_collect_recent_rolling_clips", lambda limit: [])
    result = service.schedule_alert(r.schedule, r.execution, contacts=[r.contact], trigger="log_inactive", context={},
                                   exact_trace=True, should_send=lambda: False)
    assert result.cancelled
    service.email.send.assert_not_called()


def make_engine(r, monkeypatch):
    from backend.services.scheduling import scheduler_engine
    monkeypatch.setattr(scheduler_engine, "get_scheduling_database_manager", lambda: r.manager)
    monkeypatch.setattr(scheduler_engine, "get_hamilton_process_monitor", lambda: SimpleNamespace(is_hamilton_running=lambda: False, get_hamilton_processes=lambda: []))
    monkeypatch.setattr(scheduler_engine, "get_hxrun_maintenance_service", lambda: SimpleNamespace(
        get_state=lambda **kwargs: SimpleNamespace(enabled=False)))
    engine = scheduler_engine.SchedulerEngine(scheduler_engine.SchedulerConfig(enable_notifications=False))
    engine.run_log_monitor = r.monitor
    engine._load_schedules_from_database()
    for state in r.monitor.restore():
        engine._running_jobs.add(state.schedule_id)
    return engine


@pytest.mark.parametrize("sql_state", ["Complete", "Aborted"])
def test_restart_finalizes_once_and_preserves_abort_recovery(rig, monkeypatch, sql_state):
    r = rig
    observe(r)
    r.reader.state = sql_state
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    engine = make_engine(r, monkeypatch)
    engine._evaluate_active_executions(datetime.now())
    result = r.monitor.store.execution("execution")
    assert result.status == ("completed" if sql_state == "Complete" else "failed")
    saved = r.manager.get_schedule_by_id("schedule")
    assert saved.is_active is False
    assert saved.recovery_required == (sql_state == "Aborted")
    assert engine._running_jobs == set()
    assert r.monitor.restore() == []
    engine._evaluate_active_executions(datetime.now())
    assert r.monitor.store.execution("execution").end_time == result.end_time


def test_restart_after_process_result_keeps_real_outcome_without_sql(rig, monkeypatch):
    r = rig
    r.execution.status = "completed"
    r.execution.end_time = datetime.now()
    r.monitor.process_finished(r.execution)
    r.reader.failure = OSError("SQL unavailable after the process exited")
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    engine = make_engine(r, monkeypatch)
    engine._evaluate_active_executions(datetime.now())
    assert r.monitor.store.execution("execution").status == "completed"
    assert r.manager.get_schedule_by_id("schedule").is_active is False


def test_restart_while_running_blocks_dispatch_and_exposes_observation(rig, monkeypatch):
    r = rig
    engine = make_engine(r, monkeypatch)
    observe(r)
    assert "previous scheduled execution" in engine._resolve_dispatch_block_reason(r.schedule)
    details = engine.get_runtime_queue_status()["running_job_details"][0]["monitoring"]
    assert details["state"] == "monitoring"
    assert details["run_guid"] == GUID


def test_recurring_schedule_is_advanced_only_once_after_restart(rig, monkeypatch):
    r = rig
    r.schedule.schedule_type = "interval"
    r.schedule.interval_hours = 6
    r.schedule.start_time = datetime.now() - timedelta(hours=1)
    r.db.update_schedule(r.schedule)
    r.monitor.prepare(r.schedule, r.execution, METHOD)
    r.monitor.launched("execution", 123)
    r.reader.state = "Complete"
    engine = make_engine(r, monkeypatch)
    engine._evaluate_active_executions(datetime.now())
    expected = r.manager.get_schedule_by_id("schedule").start_time
    assert expected > datetime.now()
    engine._evaluate_active_executions(datetime.now())
    assert r.manager.get_schedule_by_id("schedule").start_time == expected


def test_executor_waits_without_runtime_cap_and_tracks_actual_cleanup(rig, monkeypatch):
    r = rig
    from backend.services.scheduling import experiment_executor
    monkeypatch.setattr(experiment_executor, "get_scheduling_database_manager", lambda: r.manager)
    path = r.tmp_path / "Cleanup.med"
    path.write_text("test fixture; never launched")
    process = Mock(pid=123, returncode=0)
    process.communicate.return_value = ("", "")
    monkeypatch.setattr(experiment_executor.subprocess, "Popen", Mock(return_value=process))
    monitor = Mock()
    executor = experiment_executor.ExperimentExecutor()
    executor.run_log_monitor = monitor
    executor._monitor_schedule = r.schedule
    executor._monitor_terminate_schedule = True
    cleanup = ScheduledExperiment("schedule", "Cleanup", str(path), "once")
    result = executor._execute_real_command(cleanup, r.execution, 0)
    assert result.success
    assert result.execution_time_seconds > 120 * 60
    process.communicate.assert_called_once_with()
    process.kill.assert_not_called()
    assert monitor.prepare.call_args.args[2] == path
    assert monitor.prepare.call_args.args[3] is True


def test_wall_clock_change_does_not_change_inactivity(rig, monkeypatch):
    r = rig
    observe(r)
    from backend.services.scheduling import run_log_monitor
    class ChangedDateTime(datetime):
        @classmethod
        def now(cls):
            return datetime(2040, 1, 1)
    monkeypatch.setattr(run_log_monitor, "datetime", ChangedDateTime)
    r.clock.advance(179)
    assert observe(r).state == "monitoring"
    r.clock.advance(2)
    assert observe(r).state == "log_inactive"


def test_process_completion_racing_sql_poll_cannot_reopen_alert(rig):
    r = rig
    observe(r)
    r.clock.advance(181)
    original_find = r.reader.find
    def complete_during_query(state):
        r.execution.status = "completed"
        r.execution.end_time = datetime.now()
        r.monitor.process_finished(r.execution)
        return original_find(state)
    r.reader.find = complete_during_query
    assert observe(r).state == "terminal"
    assert alerts(r) == []


def test_operator_recovery_can_close_orphan_but_not_running_process(rig, monkeypatch):
    r = rig
    engine = make_engine(r, monkeypatch)
    engine.process_monitor.get_hamilton_processes = lambda: [object()]
    with pytest.raises(SafetyConflict):
        engine._close_recovered_observations(r.schedule.schedule_id, "operator")
    assert r.monitor.store.execution("execution").status == "running"
    engine.process_monitor.get_hamilton_processes = lambda: []
    engine._close_recovered_observations(r.schedule.schedule_id, "operator")
    assert r.monitor.store.execution("execution").status == "cancelled"
    assert r.monitor.snapshots() == []


def test_deleted_schedule_execution_is_finalized_in_archive(rig):
    r = rig
    # Reproduce an old database, where deletion was allowed during a run.
    import sqlite3
    with sqlite3.connect(r.db.db_path) as conn:
        r.db._archive_job_executions(conn.cursor(), 'schedule')
        conn.execute("DELETE FROM JobExecutions WHERE schedule_id = 'schedule'")
        conn.execute("DELETE FROM ScheduledExperiments WHERE schedule_id = 'schedule'")
    r.execution.status = "completed"
    r.execution.end_time = datetime.now()
    assert r.monitor.store.finalize(r.execution, r.schedule)
    assert r.monitor.store.execution("execution").status == "completed"


def test_partial_sql_completion_waits_for_final_state(rig):
    r = rig
    observe(r)
    r.reader.find = lambda state: {"guid": GUID, "state": "Running", "end_time": datetime.now().isoformat()}
    r.clock.advance(181)
    state = observe(r)
    assert state.state == "waiting"
    assert "waiting for the final run state" in state.reason
    assert alerts(r) == []


def test_restart_marks_delivery_interrupted_after_run_finished_unknown(rig):
    r = rig
    stall(r)
    log_id = alerts(r)[0].log_id
    assert r.monitor.store.claim_alert(log_id)
    r.execution.status = "completed"
    r.execution.end_time = datetime.now()
    r.monitor.store.finalize(r.execution, r.schedule)
    r.monitor.finish("execution")
    r.monitor = RunLogMonitor(r.manager, reader=r.reader, directory=r.directory, clock=r.clock)
    assert r.monitor.restore() == []
    # SMTP may have accepted it before the crash; never report it as not sent.
    assert alerts(r)[0].status == "unknown"
