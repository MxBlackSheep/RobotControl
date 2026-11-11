"""Restore admission: active run and recovery retain database_change_guard's
refusal; a restore blocks launches but schedule edits answer before it finishes.
Uses scheduler methods and disposable in-memory boundary doubles, no SQL/hardware.
"""
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.services.scheduling.scheduler_engine import SchedulerEngine
from backend.models import ScheduledExperiment
from backend.services.sqlite_safety import SafetyConflict


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

if __name__ == '__main__':
    run()

