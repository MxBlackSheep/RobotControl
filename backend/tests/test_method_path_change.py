from datetime import datetime
from queue import Queue
from threading import Event, RLock, Thread
from types import SimpleNamespace
import sqlite3
from unittest.mock import Mock

import pytest
from backend.tests.test_method_import import service, methods, client
from backend.tests.test_method_library import add_schedule
from backend.services.scheduling.method_library import path_change_preview, prepare_path_change
from backend.services.scheduling.scheduler_engine import SchedulerEngine
from backend.models import JobExecution


@pytest.fixture
def engine():
    engine = SchedulerEngine.__new__(SchedulerEngine)
    engine._jobs_lock = RLock(); engine._schedules_lock = RLock()
    engine._running_jobs = set(); engine._queued_backlog = set(); engine._active_schedules = {}
    engine._queue_runtime = {}; engine._job_queue = Queue(); engine._emit_event = Mock()
    engine.config = SimpleNamespace(check_interval_seconds=30)
    return engine


@pytest.fixture
def change(service, methods, engine):
    service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    method = service.db.get_experiment_methods()[0]
    schedule = add_schedule(service.db, method['file_path'])
    engine._active_schedules[schedule.schedule_id] = schedule
    engine.db_manager = SimpleNamespace(store_job_execution=service.db.create_job_execution)
    target = str(methods / 'nested' / 'Same.MED')
    preview = path_change_preview(service.db, engine, method['method_id'], target)
    return method, schedule, target, preview


def select(preview, role='primary'):
    return [{'schedule_id': ref['schedule_id'], 'role': ref['role'], 'expected_updated_at': ref['updated_at']}
            for ref in preview['references'] if ref['role'] == role]


def test_partial_reference_update_preserves_labels_history_and_cache(service, engine, change):
    method, schedule, target, preview = change
    service.db.create_job_execution(JobExecution(execution_id='history', schedule_id=schedule.schedule_id, status='completed', hamilton_command='HxRun old-path'))
    with service.db._get_connection() as conn: history = [tuple(row) for row in conn.execute('SELECT * FROM JobExecutions')]
    result = engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview, 'cleanup'))
    updated = service.db.get_schedule_by_id(schedule.schedule_id)
    assert result['updated_schedule_ids'] == [schedule.schedule_id]
    assert updated.experiment_path == schedule.experiment_path
    assert updated.timeout_config.cleanup_experiment_path == target
    assert updated.experiment_name == schedule.experiment_name
    assert updated.start_time == schedule.start_time and updated.notification_contacts == schedule.notification_contacts
    assert engine._active_schedules[schedule.schedule_id].timeout_config.cleanup_experiment_path == target
    with service.db._get_connection() as conn: assert [tuple(row) for row in conn.execute('SELECT * FROM JobExecutions')] == history


@pytest.mark.parametrize('busy_set', ['_running_jobs', '_queued_backlog'])
def test_busy_schedules_cannot_be_selected(service, engine, change, busy_set):
    method, schedule, target, preview = change
    getattr(engine, busy_set).add(schedule.schedule_id)
    assert all(ref['busy'] for ref in path_change_preview(service.db, engine, method['method_id'], target)['references'])
    with pytest.raises(ValueError, match='queued, running or paused'):
        engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview))
    assert service.db.get_experiment_methods()[0]['file_path'] == method['file_path']
    # Catalogue-only correction must not touch an existing running/paused execution.
    engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], [])
    assert service.db.get_schedule_by_id(schedule.schedule_id).experiment_path == method['file_path']
    assert schedule.schedule_id in getattr(engine, busy_set)


@pytest.mark.parametrize('conflict', ['revision', 'schedule', 'archived', 'pending', 'deleted_file'])
def test_conflicts_leave_everything_unchanged(service, engine, change, conflict):
    method, schedule, target, preview = change
    if conflict == 'revision': service.db.set_method_archived(method['method_id'], True, method['revision'])
    if conflict in {'schedule', 'archived'}:
        schedule.archived = conflict == 'archived'
        schedule.experiment_name = 'Edited elsewhere'
        schedule.updated_at = datetime.now()
        service.db.update_schedule(schedule)
    if conflict == 'pending': service.db.create_job_execution(JobExecution(execution_id='pending', schedule_id=schedule.schedule_id, status='pending'))
    if conflict == 'deleted_file':
        from pathlib import Path
        Path(target).unlink()
    with pytest.raises(ValueError): engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview))
    assert service.db.get_experiment_methods(valid_only=False)[0]['file_path'] == method['file_path']
    assert service.db.get_schedule_by_id(schedule.schedule_id).experiment_path == method['file_path']


def test_collision_and_concurrent_catalogue_change(service, engine, change, methods):
    method, schedule, target, preview = change
    prepared = prepare_path_change(service.db, method['method_id'], target)
    service.import_methods_from_folder(str(methods), 'other', ['nested/Same.MED'])
    with pytest.raises(ValueError, match='another library entry'): prepare_path_change(service.db, method['method_id'], target)
    with pytest.raises(ValueError, match='library changed'): service.db.apply_method_path_change(prepared, method['revision'], select(preview))


def test_database_error_rolls_back_schedule_and_library(service, engine, change):
    method, schedule, target, preview = change
    with service.db._get_connection() as conn:
        conn.execute("CREATE TRIGGER reject_relink BEFORE UPDATE OF file_path ON ExperimentMethods BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError): engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview))
    assert service.db.get_schedule_by_id(schedule.schedule_id).experiment_path == method['file_path']
    assert engine._active_schedules[schedule.schedule_id].experiment_path == method['file_path']


def test_enqueue_waits_for_atomic_change_and_uses_refreshed_cache(service, engine, change, monkeypatch):
    method, schedule, target, preview = change
    entered, release, enqueued = Event(), Event(), Event()
    original = service.db.apply_method_path_change
    failures = []
    def blocked(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(service.db, 'apply_method_path_change', blocked)
    def change_path():
        try: engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview))
        except Exception as exc: failures.append(exc)
    def enqueue():
        engine._process_due_job(schedule, datetime.now()); enqueued.set()
    edit_thread = Thread(target=change_path); edit_thread.start()
    assert entered.wait(3)
    queue_thread = Thread(target=enqueue); queue_thread.start()
    assert not enqueued.wait(.1)
    release.set(); edit_thread.join(3); queue_thread.join(3)
    assert not failures and enqueued.is_set()
    engine._running = True; engine._resolve_dispatch_block_reason = lambda schedule: None
    assert engine._wait_until_dispatch_ready(schedule.schedule_id).experiment_path == target


def test_path_api_selection_and_local_access(client, service, engine, change, monkeypatch):
    import backend.api.scheduling as api
    monkeypatch.setattr(api, 'get_scheduler_engine', lambda: engine)
    method, schedule, target, preview = change
    base = f"/api/scheduling/experiments/library/{method['method_id']}"
    assert client.post(base + '/path-preview', json={'new_path': target}).json()['data']['old_path'] == method['file_path']
    request = {'new_path': target, 'expected_revision': method['revision'], 'references': select(preview)}
    assert client.post(base + '/change-path', json=request).json()['data']['updated_schedule_ids'] == [schedule.schedule_id]
    assert client.post(base + '/change-path', json=request).status_code == 409
    for route in ('path-preview', 'change-path'):
        assert client.post(base + '/' + route, json=request, headers={'x-forwarded-for': '8.8.8.8'}).status_code == 403


def test_ordinary_edit_cannot_overwrite_a_concurrent_path_correction(client, service, engine, change, monkeypatch):
    import backend.api.scheduling as api
    method, schedule, target, preview = change
    manager = SimpleNamespace(get_schedule_by_id=service.db.get_schedule_by_id)
    monkeypatch.setattr(api, 'get_services', lambda: (engine, manager, None))
    normalize = api._normalize_schedule_request
    def relink_during_validation(*args):
        engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview))
        return normalize(*args)
    monkeypatch.setattr(api, '_normalize_schedule_request', relink_during_validation)
    response = client.put(f'/api/scheduling/{schedule.schedule_id}', json={'experiment_name': 'Stale edit'})
    assert response.status_code == 409
    saved = service.db.get_schedule_by_id(schedule.schedule_id)
    assert saved.experiment_path == target and saved.experiment_name == schedule.experiment_name


def test_schedule_archive_waits_for_path_change_and_preserves_it(client, service, engine, change, monkeypatch):
    import backend.api.scheduling as api
    from backend.services.auth import get_current_user
    method, schedule, target, preview = change
    client.app.dependency_overrides[get_current_user] = lambda: {'username': 'tester', 'role': 'admin'}
    manager = SimpleNamespace(get_schedule_by_id=service.db.get_schedule_by_id, update_scheduled_experiment=service.db.update_schedule)
    monkeypatch.setattr(api, 'get_services', lambda: (engine, manager, None))
    entered, release, finished = Event(), Event(), Event()
    original = service.db.apply_method_path_change
    def blocked(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(service.db, 'apply_method_path_change', blocked)
    responses, failures = [], []
    def relink():
        try: engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], select(preview))
        except Exception as exc: failures.append(exc)
    def archive():
        responses.append(client.post(f'/api/scheduling/{schedule.schedule_id}/archive', json={'archived': True}))
        finished.set()
    relink_thread = Thread(target=relink); relink_thread.start()
    assert entered.wait(3)
    archive_thread = Thread(target=archive); archive_thread.start()
    assert not finished.wait(.1)
    release.set(); relink_thread.join(3); archive_thread.join(3)
    assert not failures and finished.is_set() and responses[0].status_code == 200
    saved = service.db.get_schedule_by_id(schedule.schedule_id)
    assert saved.archived and saved.experiment_path == target


def test_catalogue_only_change_preserves_paused_execution_and_monitoring(service, engine, change):
    import json
    method, schedule, target, preview = change
    service.db.create_job_execution(JobExecution(execution_id='paused', schedule_id=schedule.schedule_id, status='running'))
    observation = json.dumps({'run_state': 'Paused', 'raw_run_state': 2, 'run_guid': 'same-run', 'trace_path': method['file_path'], 'pause_id': 'already-alerted'})
    with service.db._get_connection() as conn:
        conn.execute('INSERT INTO ExecutionMonitoring (execution_id, schedule_id, data) VALUES (?, ?, ?)', ('paused', schedule.schedule_id, observation))
        conn.commit()
        execution = tuple(conn.execute("SELECT * FROM JobExecutions WHERE execution_id = 'paused'").fetchone())
    engine._running_jobs.add(schedule.schedule_id)
    engine.change_library_method_path(service.db, method['method_id'], target, method['revision'], [])
    with service.db._get_connection() as conn:
        assert tuple(conn.execute("SELECT * FROM JobExecutions WHERE execution_id = 'paused'").fetchone()) == execution
        assert conn.execute("SELECT data FROM ExecutionMonitoring WHERE execution_id = 'paused'").fetchone()[0] == observation
    assert service.db.get_schedule_by_id(schedule.schedule_id).experiment_path == method['file_path']


def test_schedule_versions_distinguish_changes_within_one_second():
    from datetime import timedelta
    from backend.api.scheduling import _timestamps_match
    original = datetime(2026, 9, 12, 12, 0, 0, 123456)
    assert _timestamps_match(original.isoformat(), original)
    assert not _timestamps_match(original.isoformat(), original + timedelta(microseconds=1))
