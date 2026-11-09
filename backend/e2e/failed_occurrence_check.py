"""Disposable SQLite + scheduler + executor check; no Hamilton reads or launches.

Run: uv run --locked python backend/e2e/failed_occurrence_check.py
Failure cases:
1. Fast once failure dispatches once over several loops: one email/database step; off.
2. Slow once failure has the same outcome.
3. Fast interval/hourly/daily/weekly failures advance once; an already advanced time stays.
4. Keyword-only abort consumes the occurrence and still sends aborted.
5. Abort with a note still requires manual recovery; cancelled remains recovery-owned.
6. HxRun appearing or Simulation Mode changing at either launch guard consumes failure;
   the first guard prevents preparation, the final guard can follow a committed step.
7. Successful once/interval runs retain their outcome.
8. Restart reconciliation consumes a saved observed failure and persists schedule state.
9. Duplicate finalization returns False and changes nothing; a real SQLite write
   failure retains the observation and storage safety hold.
10. Edit schedule can reactivate a consumed once occurrence; in-flight edits survive.
11. Interval without interval_hours turns off with no repeat.
12. Ended occurrences reject stale edits; fresh/list tokens and in-flight edits work.
13. Finalization serializes a concurrent edit; restart cannot repeat the occurrence.
14. Keyword abort emails describe the next run; noted aborts describe recovery only.

Exit-zero outcome cases:
1. No SQL row, once: failed, one dispatch/email, schedule off, manual recovery.
2. No SQL row, interval: failed, manual recovery, no rerun until acknowledged.
3. Complete: success without waiting.
4. Aborted (raw 64): failed with manual recovery.
5. Late Complete during re-checks: success without failure email.
6. SQL unreachable or Running: unknown failure with manual recovery.

Uses real SQLite, preparation receipts, notifications and run observations. Only the
database package boundary, SQL run reader, process monitor and Popen are fixtures.
Slow runs advance a controlled scheduler clock rather than sleeping or running VENUS.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.e2e.simulation_mode_check import sample_config
from backend.models import JobExecution, NotificationContact, ScheduledExperiment
from backend.services.alert_email import moment, schedule_alert_email
from backend.services.scheduling import experiment_executor as ex, scheduler_engine as se
from backend.services.scheduling.database_manager import SchedulingDatabaseManager
from backend.services.scheduling.run_log_monitor import RunLogMonitor
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase


class Fixture:
    def __init__(self, root, stack):
        self.root = root
        self.now = datetime.now().replace(second=0, microsecond=0)
        fixture = self

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixture.now

        self.storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))
        self.manager = SchedulingDatabaseManager.__new__(SchedulingDatabaseManager)
        self.manager.sqlite_db = self.storage
        self.manager.main_db_service = None
        self.sql_state = None
        self.sql_reason = "Waiting for the exact SQL run"
        self.waits = []
        self.after_wait = lambda: None
        def sleep(seconds):
            self.waits.append(seconds)
            self.after_wait()
        stack.enter_context(patch.object(ex, 'time', SimpleNamespace(time=ex.time.time, sleep=sleep)))
        self.note = None
        self.manager.should_block_due_to_abort = lambda _: self.note
        executable = sample_config(root)
        executable.write_text('Never executed')
        config = ex.ExecutionConfig(hxrun_path=str(executable), method_base_path=str(root))
        self.method = root / 'fixture.med'
        self.method.write_text('Fixture method, never executed')
        self.busy = False
        self.prepared, self.launched, self.sent, self.recovery = [], [], [], []
        self.returncode, self.stderr = 1, 'Fixture failure'
        self.during_run = lambda: None
        self.after_prepare = lambda: None
        self.before_execute = lambda: None
        process_monitor = SimpleNamespace(is_hamilton_running=lambda: self.busy,
            get_hamilton_processes=lambda: ['fixture HxRun'] if self.busy else [])
        for module, name, value in (
            (ex, 'ExecutionConfig', lambda: config),
            (ex, 'get_scheduling_database_manager', lambda: self.manager),
            (se, 'get_scheduling_database_manager', lambda: self.manager),
            (se, 'get_hamilton_process_monitor', lambda: process_monitor),
            (se, 'get_hxrun_maintenance_service', lambda: SimpleNamespace(
                get_state=lambda **_: self.storage.get_hxrun_maintenance_state())),
            (se, 'get_notification_service', lambda: SimpleNamespace(schedule_alert=self.send,
                manual_recovery_required=lambda *a, **k: self.recovery.append(k))),
            (ex, 'get_experiment_discovery_service', lambda: SimpleNamespace(
                db=SimpleNamespace(update_method_usage=lambda _: None))),
            (se, 'datetime', Clock),
        ):
            stack.enter_context(patch.object(module, name, value))
        # A package invocation records its committed effect in this same disposable DB.
        from backend.services import database_tools
        with self.storage._get_connection() as conn:
            conn.execute('CREATE TABLE FixturePreparation (execution_id TEXT)')
            conn.commit()

        def prepare(step, run):
            with self.storage._get_connection() as conn:
                conn.execute('INSERT INTO FixturePreparation VALUES (?)', (run['execution_id'],))
                conn.commit()
            self.prepared.append(run['execution_id'])
            self.after_prepare()
        stack.enter_context(patch.object(database_tools, 'get_database_tools', return_value=SimpleNamespace(
            preparation_state=lambda _: 'ready', prepare_for_run=prepare)))

        def popen(*args, **kwargs):
            self.launched.append(args[0])

            def communicate():
                self.during_run()
                return '', self.stderr
            return SimpleNamespace(pid=123, returncode=self.returncode, communicate=communicate)
        stack.enter_context(patch.object(ex.subprocess, 'Popen', side_effect=popen))
        self.engine = self.new_engine()
        from backend.api import scheduling as api
        self.api = api
        stack.enter_context(patch.object(api, 'get_services', return_value=(self.engine, self.manager, None)))
        stack.enter_context(patch.object(api, 'log_action'))
        self.contact = self.storage.create_notification_contact(NotificationContact(
            '', 'Fixture', 'fixture@example.invalid'))
        self.engine._notification_contacts[self.contact.contact_id] = self.contact

    def save(self, draft):
        from fastapi import HTTPException
        try:
            self.api.update_schedule(draft.schedule_id, dict(
                experiment_name='Edited', is_active=draft.is_active,
                start_time=draft.start_time.isoformat(), expected_updated_at=draft.updated_at.isoformat()),
                current_user={'username': 'fixture', 'role': 'user'},
                connection=SimpleNamespace(client_ip='127.0.0.1'), if_unmodified_since=None)
            return 200
        except HTTPException as exc:
            return exc.status_code

    def new_engine(self):
        engine = se.SchedulerEngine()
        # The SQL association boundary is faked; observations and receipts are real SQLite.
        engine.run_log_monitor = RunLogMonitor(self.manager, directory=self.root,
            reader=SimpleNamespace(boundary=lambda _: (self.now.isoformat(), ''),
                find=self.find))
        return engine

    def find(self, state):
        if self.sql_state is None:
            raise LookupError(self.sql_reason)
        return dict(guid='a' * 32, state=self.sql_state,
                    raw_state={'Complete': '128', 'Aborted': '64'}.get(self.sql_state, '1'),
                    end_time=self.now.isoformat() if self.sql_state in {'Complete', 'Aborted'} else None)

    def send(self, schedule, execution, *, trigger, context, **kwargs):
        alert = schedule_alert_email(trigger=trigger, experiment=schedule.experiment_name,
            schedule_id=schedule.schedule_id, execution_id=execution.execution_id,
            start_time=execution.start_time, end_time=execution.end_time,
            estimated_duration=schedule.estimated_duration, recorded_minutes=execution.duration_minutes,
            context=context, attached=[], clip_attached=False, now=self.now)
        self.sent.append((trigger, context, alert))
        return SimpleNamespace(sent=True, delivery_status='sent', error=None,
            recipients=['fixture@example.invalid'], attachments=[], attachment_notes=[],
            subject=alert.subject, body=alert.text())

    def schedule(self, schedule_type='once', **kwargs):
        schedule = ScheduledExperiment('', 'Fixture', str(self.method), schedule_type,
            start_time=self.now - timedelta(minutes=1), preparation={'fixture': True},
            notification_contacts=[self.contact.contact_id], **kwargs)
        assert self.storage.create_schedule(schedule)
        self.engine._active_schedules[schedule.schedule_id] = schedule
        return schedule

    def loops(self, count=4):
        for _ in range(count):
            for schedule in self.engine._find_due_jobs(self.now):
                self.engine._process_due_job(schedule, self.now)
            for _ in range(self.engine._job_queue.qsize()):
                schedule, execution = self.engine._job_queue.get_nowait()
                if self.engine._resolve_dispatch_block_reason(schedule):
                    self.engine._job_queue.put((schedule, execution))
                    self.engine._job_queue.task_done()
                    continue
                self.engine._queued_backlog.discard(schedule.schedule_id)
                self.engine._running_jobs.add(schedule.schedule_id)
                self.before_execute()
                self.engine._execute_job(schedule, execution)
                self.engine._job_queue.task_done()
            self.engine._update_interval_schedules(self.now)
            self.engine._evaluate_active_executions(self.now)
            self.now += timedelta(seconds=30)

    def assert_consumed(self, schedule, *, status='failed', trigger='execution_failed', preparations=1,
                        launches=1, executions=1, emails=1):
        stored = SQLiteSchedulingDatabase(str(self.storage.db_path)).get_schedule_by_id(schedule.schedule_id)
        history = self.storage.get_execution_history(schedule.schedule_id)
        assert len(history) == executions, f'executions={len(history)}, emails={len(self.sent)}, database_steps={len(self.prepared)}, active={stored.is_active}'
        assert all(item['status'] == status for item in history)
        assert len(self.prepared) == preparations and len(self.launched) == launches
        with self.storage._get_connection() as conn:
            assert conn.execute('SELECT COUNT(*) FROM FixturePreparation').fetchone()[0] == preparations
            assert conn.execute("SELECT COUNT(*) FROM LabPreparation WHERE status='prepared'").fetchone()[0] == preparations
            assert conn.execute('SELECT COUNT(*) FROM NotificationLog').fetchone()[0] == emails
        assert len(self.sent) == emails
        assert all(item[0] == trigger for item in self.sent)
        interval = self.engine._resolve_interval_hours(stored)
        assert stored.is_active == bool(interval) and not stored.recovery_required
        if interval:
            assert stored.start_time > self.now
        if trigger in ('execution_failed', 'aborted'):
            for _, context, alert in self.sent:
                if interval:
                    assert context['next_run_time'] == stored.start_time.isoformat()
                    assert ('Next run', moment(stored.start_time, self.now, ago=False)) in alert.rows
                    assert moment(stored.start_time, self.now, ago=False) in alert.html()
                else:
                    text = 'It will not run again until someone turns the schedule back on.'
                    assert text in alert.text() and text in alert.html()
        return stored


def run():
    report = dict(passed=False, checks=[], command='uv run --locked python backend/e2e/failed_occurrence_check.py',
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        fixture='Disposable SQLite/config, fake package/SQL reader/process/Popen; no Hamilton access',
        source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'backend/services/scheduling/scheduler_engine.py', 'backend/services/alert_email.py',
            'backend/e2e/failed_occurrence_check.py')})
    cases = []

    def case(name):
        def register(function):
            cases.append((name, function))
            return function
        return register

    @case('1 fast once')
    def fast(f):
        value = f.schedule()
        f.loops()
        f.assert_consumed(value)

    @case('2 slow once')
    def slow(f):
        value = f.schedule()
        def advance():
            f.now += timedelta(hours=3)
            f.engine._update_interval_schedules(f.now)
        f.during_run = advance
        f.loops()
        f.assert_consumed(value)

    for schedule_type in ('interval', 'hourly', 'daily', 'weekly'):
        @case(f'3 fast {schedule_type}')
        def interval(f, kind=schedule_type):
            value = f.schedule(kind, **({'interval_hours': 6} if kind == 'interval' else {}))
            f.loops()
            stored = f.assert_consumed(value)
            hours = {'interval': 6, 'hourly': 1, 'daily': 24, 'weekly': 168}[kind]
            assert stored.start_time == (f.now - timedelta(minutes=2) + timedelta(hours=hours))

    @case('3 slow interval keeps next time')
    def slow_interval(f):
        value = f.schedule('interval', interval_hours=6)
        advanced = []
        def advance():
            f.now += timedelta(hours=2)
            f.engine._update_interval_schedules(f.now)
            advanced.append(f.storage.get_schedule_by_id(value.schedule_id).start_time)
        f.during_run = advance
        f.loops()
        assert f.assert_consumed(value).start_time == advanced[0]

    @case('4 keyword abort')
    def keyword(f):
        value = f.schedule()
        f.stderr = 'stopped by user'
        f.loops()
        f.assert_consumed(value, trigger='aborted')

    @case('5 noted abort and cancelled recovery')
    def noted(f):
        value = f.schedule()
        f.note = 'Hamilton reported last run as aborted'
        f.returncode = 64
        f.loops()
        stored = f.storage.get_schedule_by_id(value.schedule_id)
        assert stored.recovery_required and not stored.is_active
        assert len(f.sent) == len(f.prepared) == len(f.launched) == len(f.recovery) == 1
        assert f.sent[0][0] == 'aborted'
        state = f.manager.get_manual_recovery_state()
        assert state.active and state.resume_required
        # Recovery cancellation closes an unfinished observation without consuming its time.
        pending = JobExecution('', value.schedule_id, 'pending', start_time=f.now)
        assert f.manager.store_job_execution(pending)
        f.engine.run_log_monitor.prepare(stored, pending, f.method)
        resolved = f.engine._clear_manual_recovery(value.schedule_id, 'Robot checked', 'fixture',
            state.safety_revision, expected_updated_at=stored.updated_at.isoformat())
        assert not resolved.recovery_required
        assert f.engine.run_log_monitor.store.execution(pending.execution_id).status == 'cancelled'
        after = f.storage.get_schedule_by_id(value.schedule_id)
        assert not after.recovery_required and not after.is_active and after.start_time == stored.start_time
        alert = f.sent[0][2]
        assert 'scheduling is paused' in alert.text()
        assert not any(label == 'Next run' for label, _ in alert.rows)
        assert 'schedule_active' not in f.sent[0][1]

    for guard in ('first', 'final'):
        for reason in ('HxRun', 'Simulation Mode'):
            @case(f'6 {guard} guard {reason}')
            def refusal(f, gate=guard, change=reason):
                value = f.schedule()
                def refuse():
                    if change == 'HxRun':
                        f.busy = True
                    else:
                        sample_config(f.root, 1, 0)
                if gate == 'first':
                    f.before_execute = refuse
                else:
                    f.after_prepare = refuse
                f.loops()
                f.assert_consumed(value, preparations=int(gate == 'final'), launches=0)
                assert ('HxRun' if change == 'HxRun' else 'Simulation') in f.storage.get_execution_history(value.schedule_id)[0]['error_message']

    for kind in ('once', 'interval'):
        @case(f'7 success {kind}')
        def success(f, schedule_type=kind):
            f.returncode = 0
            f.sql_state = 'Complete'
            value = f.schedule(schedule_type, interval_hours=6 if schedule_type == 'interval' else None)
            f.loops()
            f.assert_consumed(value, status='completed', emails=0)

    @case('8 restart reconciliation')
    def restart(f):
        value = f.schedule()
        execution = JobExecution('', value.schedule_id, 'running', start_time=f.now)
        assert f.manager.store_job_execution(execution)
        f.engine.run_log_monitor.prepare(value, execution, f.method)
        execution.status, execution.error_message, execution.end_time = 'failed', 'Fixture failure', f.now
        f.engine.run_log_monitor.process_finished(execution)
        # Fresh manager, storage, engine and monitor restore the durable process outcome.
        f.manager.sqlite_db = SQLiteSchedulingDatabase(str(f.storage.db_path))
        f.engine = f.new_engine()
        f.engine.refresh_notification_contacts()
        f.engine._load_schedules_from_database()
        f.engine.run_log_monitor.restore()
        f.engine._evaluate_active_executions(f.now)
        f.loops()
        f.assert_consumed(value, preparations=0, launches=0)
        assert not f.engine.run_log_monitor.snapshots()
        f.engine = f.new_engine()
        f.engine._load_schedules_from_database()
        f.engine.run_log_monitor.restore()
        assert not f.engine.run_log_monitor.snapshots() and not f.engine._find_due_jobs(f.now)

    @case('9 False on duplicate finalization')
    def duplicate(f):
        value = f.schedule()
        f.loops(1)
        execution = f.engine.run_log_monitor.store.execution(f.storage.get_execution_history(value.schedule_id)[0]['execution_id'])
        stored = f.storage.get_schedule_by_id(value.schedule_id)
        assert f.manager.finalize_job_execution(execution, stored) is False
        f.engine._finalize_execution(value, execution)
        f.loops()
        f.assert_consumed(value)

    @case('9 SQLite write failure retains safety hold')
    def storage_failure(f):
        value = f.schedule()
        def break_finalize():
            with f.storage._get_connection() as conn:
                conn.execute("CREATE TRIGGER RefuseFinalization BEFORE UPDATE ON JobExecutions WHEN NEW.status='failed' BEGIN SELECT RAISE(ABORT, 'Fixture storage failure'); END")
                conn.commit()
        f.during_run = break_finalize
        f.loops(1)
        assert f.storage._safety_fault
        assert len(f.engine.run_log_monitor.snapshots()) == 1
        assert len(f.launched) == len(f.prepared) == 1
        assert f.storage.get_execution_history(value.schedule_id)[0]['status'] == 'running'
        assert f.engine._resolve_dispatch_block_reason(value) == 'Recovery acknowledged; waiting for explicit Resume queued jobs'
        assert f.manager.get_manual_recovery_state().resume_required
        with f.storage._get_connection() as conn:
            conn.execute('DROP TRIGGER RefuseFinalization')
            conn.commit()
        f.engine._evaluate_active_executions(f.now)
        f.loops()
        f.assert_consumed(value)
        assert f.manager.get_manual_recovery_state().resume_required

    @case('10 retry and in-flight edits')
    def retry(f):
        value = f.schedule()
        future = f.now + timedelta(hours=5)
        def edit():
            current = f.storage.get_schedule_by_id(value.schedule_id)
            current.experiment_name = 'Edited during run'
            current.estimated_duration = 42
            current.start_time = future
            assert f.engine.update_schedule(current, expected_updated_at=current.updated_at)
        f.during_run = edit
        f.loops()
        stored = f.assert_consumed(value)
        assert stored.experiment_name == 'Edited during run' and stored.estimated_duration == 42
        assert stored.start_time == future
        f.during_run = lambda: None
        stored.is_active, stored.start_time = True, f.now - timedelta(minutes=1)
        assert f.engine.update_schedule(stored, expected_updated_at=stored.updated_at)
        f.loops()
        f.assert_consumed(value, preparations=2, launches=2, executions=2, emails=2)

    @case('11 missing interval')
    def missing(f):
        value = f.schedule('interval')
        f.loops()
        f.assert_consumed(value)

    for kind, result in (('once', 1), ('interval', 1), ('once', 0)):
        @case(f'12 stale and fresh Save {kind} exit {result}')
        def stale(f, schedule_type=kind, returncode=result):
            value = f.schedule(schedule_type, interval_hours=6 if schedule_type == 'interval' else None)
            draft = f.storage.get_schedule_by_id(value.schedule_id)
            f.returncode = returncode
            f.sql_state = 'Complete' if returncode == 0 else None
            f.loops()
            assert f.save(draft) == 409, 'Stale form was accepted'
            stored = f.assert_consumed(value, status='completed' if returncode == 0 else 'failed',
                                       emails=int(returncode != 0))
            assert stored.updated_at != draft.updated_at
            assert f.engine._active_schedules[value.schedule_id].updated_at == stored.updated_at
            listed = f.api.list_schedules(active_only=schedule_type == 'interval', archived_only=False,
                                         current_user={'role': 'user'})['data']
            assert listed[0]['updated_at'] == stored.updated_at.isoformat()
            assert f.save(stored) == 200

    @case('12 API Save before run ends preserves edit')
    def during(f):
        value = f.schedule()
        draft = f.storage.get_schedule_by_id(value.schedule_id)
        def edit():
            assert f.save(draft) == 200
        f.during_run = edit
        f.loops()
        assert f.assert_consumed(value).experiment_name == 'Edited'

    @case('13 concurrent edit waits for finalization')
    def concurrent(f):
        value = f.schedule()
        draft = f.storage.get_schedule_by_id(value.schedule_id)
        attempted, finished = Event(), Event()
        results = []
        def edit():
            attempted.set()
            results.append(f.save(draft))
            finished.set()
        worker = Thread(target=edit)
        original = f.manager.finalize_job_execution
        def finalize(*args, **kwargs):
            worker.start()
            assert attempted.wait(5)
            assert not finished.wait(0.2), 'Edit committed during finalization'
            return original(*args, **kwargs)
        try:
            with patch.object(f.manager, 'finalize_job_execution', side_effect=finalize):
                f.loops(1)
        finally:
            worker.join(5)
        assert results == [409], results
        stored = f.assert_consumed(value)
        assert f.engine._active_schedules[value.schedule_id].to_dict() == stored.to_dict()
        restarted = f.new_engine()
        restarted._load_schedules_from_database()
        assert not restarted._find_due_jobs(f.now)

    @case('14 keyword abort interval Next run')
    def keyword_interval(f):
        value = f.schedule('interval', interval_hours=6)
        f.stderr = 'abort requested'
        f.loops()
        f.assert_consumed(value, trigger='aborted')

    for kind in ('once', 'interval'):
        @case(f'outcome {1 if kind == "once" else 2} no row {kind}')
        def no_row(f, kind=kind):
            f.returncode = 0
            value = f.schedule(kind, interval_hours=6 if kind == 'interval' else None)
            f.loops()
            stored = f.storage.get_schedule_by_id(value.schedule_id)
            history = f.storage.get_execution_history(value.schedule_id)
            assert len(history) == 1 and history[0]['status'] == 'failed'
            assert stored.recovery_required and not stored.is_active
            assert len(f.recovery) == len(f.sent) == len(f.launched) == 1
            assert f.manager.get_manual_recovery_state().active
            assert history[0]['error_message'] == 'HxRun ended but Hamilton did not report the run as complete.'
            assert f.waits == [2] * 15
            assert f.sent[0][0] == 'execution_failed'
            assert 'aborted' not in f.sent[0][2].text().lower()
            assert history[0]['error_message'] in f.sent[0][2].text()
            f.now += timedelta(hours=7)
            f.loops()
            assert len(f.launched) == 1

    for state in ('Complete', 'Aborted', 'late Complete', 'SQL unreachable', 'Running'):
        @case(f'outcome {dict(Complete=3, Aborted=4).get(state, 5 if state == "late Complete" else 6)} {state}')
        def outcome(f, state=state):
            f.returncode = 0
            f.sql_state = state if state in {'Complete', 'Aborted', 'Running'} else None
            f.sql_reason = 'SQL unreachable' if state == 'SQL unreachable' else f.sql_reason
            if state == 'late Complete':
                f.after_wait = lambda: setattr(f, 'sql_state', 'Complete')
            value = f.schedule()
            f.loops()
            if state in {'Complete', 'late Complete'}:
                f.assert_consumed(value, status='completed', emails=0)
                assert f.waits == ([] if state == 'Complete' else [2])
            else:
                stored = f.storage.get_schedule_by_id(value.schedule_id)
                history = f.storage.get_execution_history(value.schedule_id)
                assert len(history) == 1 and history[0]['status'] == 'failed'
                assert stored.recovery_required and not stored.is_active
                assert len(f.recovery) == len(f.sent) == len(f.launched) == 1
                assert f.manager.get_manual_recovery_state().active
                assert f.sent[0][0] == ('aborted' if state == 'Aborted' else 'execution_failed')
                if state != 'Aborted':
                    assert history[0]['error_message'] == 'HxRun ended but Hamilton did not report the run as complete.'
                    assert f.waits == [2] * 15
                else:
                    assert not f.waits

    logging.basicConfig(level=logging.CRITICAL)
    for name, function in cases:
        try:
            with tempfile.TemporaryDirectory(prefix='rc-failed-occurrence-') as temporary, ExitStack() as stack:
                function(Fixture(Path(temporary), stack))
            report['checks'].append(dict(case=name, passed=True))
            print(f'PASS {name}')
        except Exception as exc:
            import traceback
            traceback.print_exc()
            report['checks'].append(dict(case=name, passed=False, error=f'{type(exc).__name__}: {exc}'))
            print(f'FAIL {name}: {type(exc).__name__}: {exc}')
    report['passed'] = all(item['passed'] for item in report['checks'])
    evidence = ROOT / 'test-output/failed-occurrence-verification'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"{sum(item['passed'] for item in report['checks'])}/{len(cases)} checks passed")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(run())
