"""Restore admission: active run and recovery retain database_change_guard's
refusal; a restore blocks launches but schedule edits answer before it finishes.
Schedules due during restore wait with a reason, retain their pending occurrence
and send no email; once and interval schedules start once after restore ends.
Uses disposable SQLite and the existing executor boundary fixture, no SQL/hardware.
"""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.services.scheduling.scheduler_engine import SchedulerEngine
from backend.models import ScheduledExperiment
from backend.services.sqlite_safety import SafetyConflict
from backend.e2e.failed_occurrence_check import Fixture
from backend.services.scheduling import scheduler_engine as se


def queued_during_restore():
    for schedule_type, options in [('once', {}), ('interval', {'interval_hours': 6})]:
        with tempfile.TemporaryDirectory(prefix='rc-restore-queue-') as temporary, ExitStack() as stack:
            fixture = Fixture(Path(temporary), stack)
            engine = fixture.engine
            schedule = fixture.schedule(schedule_type, **options)
            due_time = schedule.start_time
            fixture.returncode, fixture.stderr, fixture.sql_state = 0, '', 'Complete'
            paused, release = threading.Event(), threading.Event()
            execute = engine._execute_job

            def dispatch(schedule, execution):
                try:
                    execute(schedule, execution)
                finally:
                    engine._running = False
                    paused.set()

            def wait(_seconds):
                paused.set()
                assert release.wait(5), 'restore fixture was not released'

            engine._execute_job = dispatch
            engine.config.check_interval_seconds = 1
            stack.enter_context(patch.object(se, 'time', SimpleNamespace(
                time=se.time.time, monotonic=se.time.monotonic, sleep=wait)))
            stack.enter_context(patch('backend.services.scheduling.pyhsl_runner.require_no_active_run'))
            worker = threading.Thread(target=engine._job_worker_loop)
            try:
                with engine.database_restore_guard():
                    assert engine._find_due_jobs(fixture.now) == [schedule]
                    engine._process_due_job(schedule, fixture.now)
                    engine._running = True
                    worker.start()
                    assert paused.wait(3), 'worker did not reach the dispatch gate'
                    history = fixture.storage.get_execution_history(schedule.schedule_id)
                    reason = engine._get_queue_waiting_reason(schedule.schedule_id)
                    assert reason == 'Database restore is in progress', (
                        f'{schedule_type}: reason={reason!r}, '
                        f'stored statuses={[row["status"] for row in history]}, '
                        f'emails={[item[0] for item in fixture.sent]}')
                    assert len(history) == 1 and history[0]['status'] == 'pending'
                    execution_id = history[0]['execution_id']
                    stored = fixture.storage.get_schedule_by_id(schedule.schedule_id)
                    assert stored.is_active and stored.start_time == due_time
                    assert schedule.schedule_id in engine._queued_backlog
                    assert not fixture.sent and not fixture.prepared and not fixture.launched
                    with fixture.storage._get_connection() as conn:
                        assert conn.execute('SELECT COUNT(*) FROM NotificationLog').fetchone()[0] == 0
                assert not engine._database_restore_active
                release.set()
                worker.join(5)
                assert not worker.is_alive(), 'worker did not dispatch after restore'
                history = fixture.storage.get_execution_history(schedule.schedule_id)
                assert len(history) == 1 and history[0]['execution_id'] == execution_id
                assert history[0]['status'] == 'completed', history
                assert len(fixture.prepared) == len(fixture.launched) == 1
                assert all(item[0] != 'execution_failed' for item in fixture.sent)
                stored = fixture.storage.get_schedule_by_id(schedule.schedule_id)
                assert stored.is_active == (schedule_type == 'interval')
                if stored.is_active:
                    assert stored.start_time > due_time
                print(f'PASS {schedule_type} waits without failure/email and starts after restore')
            finally:
                engine._running = False
                release.set()
                if worker.ident is not None:
                    worker.join(5)


def run():
    engine = SchedulerEngine.__new__(SchedulerEngine)
    engine._schedules_lock = threading.RLock()
    engine._jobs_lock = threading.RLock()
    engine._database_restore_active = False
    engine._owned_execution_ids = set()
    engine._active_schedules = {}
    engine.run_log_monitor = SimpleNamespace(snapshots=lambda: [])
    engine.pyhsl_runner = SimpleNamespace(unfinished=lambda: [])
    state = SimpleNamespace(storage_healthy=True, active=False, resume_required=False)
    engine._refresh_manual_recovery_state = lambda **_: state
    engine._require_robot_absent = lambda: None
    engine._validate_experiment = lambda _: True
    engine.db_manager = Mock()
    engine.db_manager.update_scheduled_experiment.return_value = True
    with patch('backend.services.scheduling.pyhsl_runner.require_no_active_run'):
        for active, owned in [(True, set()), (False, {'run'})]:
            state.active, engine._owned_execution_ids = active, owned
            try:
                with engine.database_restore_guard():
                    raise AssertionError('restore was admitted')
            except SafetyConflict as exc:
                assert str(exc) == 'Finish the run and resolve recovery before changing the database.'
        state.active, engine._owned_execution_ids = False, set()
        entered, release = threading.Event(), threading.Event()
        def restore():
            with engine.database_restore_guard():
                entered.set()
                assert release.wait(3)
        worker = threading.Thread(target=restore)
        worker.start()
        try:
            assert entered.wait(2)
            edited = threading.Event()
            edit = threading.Thread(target=lambda: (engine.update_schedule(ScheduledExperiment(
                schedule_id='fixture', experiment_name='Edited', experiment_path='fixture.med', schedule_type='once')), edited.set()))
            edit.start()
            assert edited.wait(1), 'schedule edit waited for the restore'
            try:
                with engine.launch_guard(None, None):
                    raise AssertionError('launch was admitted')
            except SafetyConflict as exc:
                assert 'restore' in str(exc).lower()
        finally:
            release.set()
            worker.join(3)
        assert not engine._database_restore_active
    print('PASS restore admission and responsive edits')
    queued_during_restore()

if __name__ == '__main__':
    run()

