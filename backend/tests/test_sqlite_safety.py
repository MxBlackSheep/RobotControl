"""Real SQLite regression tests; every database is temporary."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models import JobExecution, NotificationLogEntry, ScheduledExperiment
from backend.services.scheduling import sqlite_database
from backend.services.scheduling.database_manager import SchedulingDatabaseManager
from backend.services.scheduling.run_log_store import RunLogStore
from backend.services.scheduling.scheduler_engine import SchedulerEngine
from backend.services.sqlite_health import SQLiteHealthService
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_database, 'get_data_path', lambda: tmp_path)
    return sqlite_database.SQLiteSchedulingDatabase()


def schedule(db, key='a'):
    item = ScheduledExperiment(schedule_id=key, experiment_name=f'Method {key}', experiment_path=f'C:\\Methods\\{key}.med', schedule_type='once')
    assert db.create_schedule(item)
    return db.get_schedule_by_id(key)


def legacy_delete(db, key):
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('DELETE FROM ScheduledExperiments WHERE schedule_id = ?', (key,))


def engine(db):
    value = SchedulerEngine.__new__(SchedulerEngine)
    value._schedules_lock = threading.RLock()
    value._jobs_lock = threading.RLock()
    value._manual_state_lock = threading.RLock()
    value._manual_state_last_check = 0
    value._manual_state_logged_active = False
    value._manual_recovery_cache = db.get_manual_recovery_state()
    value._owned_execution_ids = set()
    value._running_jobs = set()
    value._active_schedules = {}
    value.config = SimpleNamespace(check_interval_seconds=5, enable_notifications=False)
    value.process_monitor = SimpleNamespace(get_hamilton_processes=Mock(return_value=[]))
    value.run_log_monitor = SimpleNamespace(snapshots=lambda: [])
    value.db_manager = SchedulingDatabaseManager.__new__(SchedulingDatabaseManager)
    value.db_manager.sqlite_db = db
    value._emit_event = Mock()
    return value


def test_recovery_blocks_delete_and_archive_inside_storage(db):
    item = schedule(db)
    db.mark_recovery_atomic('a', 'Abort', 'tester')
    with pytest.raises(SafetyConflict, match='Resolve manual recovery'):
        db.delete_schedule('a')
    item.archived = True
    with pytest.raises(SafetyConflict, match='Resolve manual recovery'):
        db.update_schedule(item)
    assert db.get_schedule_by_id('a')


def test_missing_schedule_can_be_acknowledged_but_requires_resume(db):
    schedule(db)
    db.mark_recovery_atomic('a', 'Abort', 'tester')
    legacy_delete(db, 'a')
    state = db.get_manual_recovery_state()
    assert state.active and state.schedule_missing
    with pytest.raises(SafetyConflict, match='note'):
        db.resolve_recovery_atomic('a', '', 'operator', state.safety_revision)
    assert db.resolve_recovery_atomic('a', 'Robot checked', 'operator', state.safety_revision) is None
    state = db.get_manual_recovery_state()
    assert not state.active and state.resume_required
    assert state.schedule_id == 'a' and state.experiment_name == 'Method a'
    assert db.resume_dispatch(state.safety_revision, 'operator').resume_required is False


def test_multiple_recoveries_and_stale_acknowledgement(db):
    schedule(db, 'a'); schedule(db, 'b')
    db.mark_recovery_atomic('a', 'A abort', 'tester')
    stale = db.get_manual_recovery_state().safety_revision
    db.mark_recovery_atomic('b', 'B abort', 'tester')
    with pytest.raises(SafetyConflict):
        db.resolve_recovery_atomic('a', None, 'operator', stale)
    state = db.get_manual_recovery_state()
    assert len(state.pending_recoveries) == 2
    db.resolve_recovery_atomic('a', None, 'operator', state.safety_revision)
    state = db.get_manual_recovery_state()
    assert state.active and state.schedule_id == 'b'
    with pytest.raises(SafetyConflict):
        db.resume_dispatch(state.safety_revision, 'operator')
    db.resolve_recovery_atomic('b', None, 'operator', state.safety_revision)
    assert not db.get_schedule_by_id('b').is_active


def test_orphan_global_incident_survives_another_recovery(db):
    schedule(db, 'a'); schedule(db, 'b')
    db.mark_recovery_atomic('a', 'A abort', 'tester'); legacy_delete(db, 'a')
    db.mark_recovery_atomic('b', 'B abort', 'tester')
    state = db.get_manual_recovery_state()
    assert state.schedule_id == 'a'
    db.resolve_recovery_atomic('b', None, 'operator', state.safety_revision)
    assert db.get_manual_recovery_state().active


def test_schedule_edits_cannot_clear_recovery(db):
    stale = schedule(db)
    db.mark_recovery_atomic('a', 'Abort', 'tester')
    with pytest.raises(SafetyConflict):
        db.update_schedule(stale)
    stale.is_active = False
    stale.experiment_name = 'Edited name'
    db.update_schedule(stale)
    assert db.get_schedule_by_id('a').recovery_required


def test_delete_checks_global_flag_even_if_schedule_flag_missing(db):
    schedule(db); db.mark_recovery_atomic('a', 'Abort', 'tester')
    with db._get_connection() as conn:
        conn.execute('UPDATE ScheduledExperiments SET recovery_required = 0'); conn.commit()
    with pytest.raises(SafetyConflict): db.delete_schedule('a')


def test_queued_delete_archives_cancellation_and_no_resurrection(db):
    schedule(db)
    execution = JobExecution(execution_id='run', schedule_id='a', status='pending')
    db.create_job_execution(execution)
    db.delete_schedule('a')
    execution.status = 'cancelled'
    assert db.create_job_execution(execution)
    with db._get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM JobExecutions').fetchone()[0] == 0
        assert conn.execute('SELECT status FROM JobExecutionsArchive').fetchone()[0] == 'cancelled'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('monitoring', [False, True])
def test_running_or_unfinished_monitoring_prevents_deletion(db, monitoring):
    schedule(db)
    if monitoring:
        with db._get_connection() as conn:
            conn.execute("INSERT INTO ExecutionMonitoring VALUES ('run', 'a', 0, '{}')"); conn.commit()
    else:
        db.create_job_execution(JobExecution(execution_id='run', schedule_id='a', status='running'))
    with pytest.raises(SafetyConflict): db.delete_schedule('a')


def test_recovery_write_failure_rolls_back_both_flags(db):
    schedule(db)
    with db._get_connection() as conn:
        conn.execute("CREATE TRIGGER fail_recovery BEFORE UPDATE ON SchedulerState BEGIN SELECT RAISE(ABORT, 'injected failure'); END"); conn.commit()
    with pytest.raises(sqlite3.Error): db.mark_recovery_atomic('a', 'Abort', 'tester')
    assert not db.get_schedule_by_id('a').recovery_required
    with db._get_connection() as conn:
        assert conn.execute('SELECT recovery_required FROM SchedulerState').fetchone()[0] == 0
        conn.execute('DROP TRIGGER fail_recovery'); conn.commit()
    assert db.get_manual_recovery_state().resume_required


def test_missing_state_is_not_an_inactive_default(db):
    with db._get_connection() as conn:
        conn.execute('DELETE FROM SchedulerState'); conn.commit()
    with pytest.raises(StorageUnavailable): db.get_manual_recovery_state()


def test_read_failure_keeps_dispatch_closed_until_resume(db, monkeypatch):
    value = engine(db)
    original = value.db_manager.get_manual_recovery_state
    monkeypatch.setattr(value.db_manager, 'get_manual_recovery_state', Mock(side_effect=sqlite3.OperationalError('locked')))
    state = value.get_manual_recovery_state()
    assert not state.storage_healthy and state.resume_required
    monkeypatch.setattr(value.db_manager, 'get_manual_recovery_state', original)
    assert value.get_manual_recovery_state().resume_required


def test_acknowledgement_rejects_running_and_unknown_process(db):
    schedule(db); db.mark_recovery_atomic('a', 'Abort', 'tester')
    value = engine(db)
    value.process_monitor.get_hamilton_processes.return_value = [object()]
    with pytest.raises(SafetyConflict): value.resolve_manual_recovery('a', None, 'tester', 1)
    value.process_monitor.get_hamilton_processes.side_effect = RuntimeError('denied')
    with pytest.raises(SafetyConflict, match='could not be established'): value.resolve_manual_recovery('a', None, 'tester', 1)
    assert db.get_manual_recovery_state().active


def test_launch_cannot_pass_recovery_or_failed_execution_write(db, monkeypatch):
    item = schedule(db); value = engine(db)
    execution = JobExecution(execution_id='run', schedule_id='a', status='pending')
    db.mark_recovery_atomic('a', 'Abort', 'tester')
    with pytest.raises(SafetyConflict):
        with value.launch_guard(item, execution): pytest.fail('Unsafe launch')
    state = db.get_manual_recovery_state()
    db.resolve_recovery_atomic('a', None, 'tester', state.safety_revision)
    db.resume_dispatch(db.get_manual_recovery_state().safety_revision, 'tester')
    item = db.get_schedule_by_id('a'); item.is_active = True; db.update_schedule(item)
    monkeypatch.setattr(value.db_manager, 'store_job_execution', lambda _: False)
    with pytest.raises(StorageUnavailable):
        with value.launch_guard(item, execution): pytest.fail('Launch without durable execution')


def test_resume_revision_and_hold_survive_reopen(db):
    schedule(db); db.mark_recovery_atomic('a', 'Abort', 'tester')
    db.resolve_recovery_atomic('a', None, 'tester', db.get_manual_recovery_state().safety_revision)
    reopened = sqlite_database.SQLiteSchedulingDatabase()
    state = reopened.get_manual_recovery_state()
    assert state.resume_required and not state.active
    with pytest.raises(SafetyConflict): reopened.resume_dispatch(state.safety_revision - 1, 'tester')
    reopened.resume_dispatch(state.safety_revision, 'tester')
    assert sqlite_database.SQLiteSchedulingDatabase().get_manual_recovery_state().resume_required is False


def test_transaction_rejects_stale_schedule_edit_and_delete(db):
    item = schedule(db)
    changed = deepcopy(item); changed.updated_at = datetime(2030, 1, 1)
    db.update_schedule(changed)
    with pytest.raises(SafetyConflict): db.update_schedule(item, expected_updated_at=item.updated_at.isoformat())
    with pytest.raises(SafetyConflict): db.delete_schedule('a', expected_updated_at=item.updated_at.isoformat())


def test_reviewed_repair_preserves_orphan_history_and_backup(db, tmp_path):
    schedule(db)
    db.create_job_execution(JobExecution(execution_id='run', schedule_id='a', status='completed'))
    legacy_delete(db, 'a')
    health = SQLiteHealthService(db.db_path, 'scheduling', tmp_path / 'backups')
    preview = health.preview()
    assert not preview['healthy'] and preview['issues'][0]['kind'] == 'orphan_execution'
    result = health.repair(preview['token'], 'admin')
    assert result['preview']['healthy']
    with sqlite3.connect(result['backup']) as backup:
        assert backup.execute('SELECT COUNT(*) FROM JobExecutions').fetchone()[0] == 1
    with db._get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM JobExecutionsArchive').fetchone()[0] == 1
    assert db.get_manual_recovery_state().resume_required
    with pytest.raises(SafetyConflict): health.repair(preview['token'], 'admin')


def test_repair_requires_fresh_preview_and_successful_backup(db, tmp_path, monkeypatch):
    schedule(db); db.create_job_execution(JobExecution(execution_id='run', schedule_id='a', status='completed')); legacy_delete(db, 'a')
    health = SQLiteHealthService(db.db_path, 'scheduling', tmp_path / 'backups')
    preview = health.preview()
    monkeypatch.setattr(health, '_backup', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError): health.repair(preview['token'], 'admin')
    assert health.preview()['token'] == preview['token']


def test_auth_foreign_keys_cleanup_and_no_secret_preview(tmp_path, monkeypatch):
    from backend.services import auth_database
    monkeypatch.setattr(auth_database, 'get_data_path', lambda: tmp_path)
    monkeypatch.delenv('ROBOTCONTROL_AUTH_DB_FILENAME', raising=False)
    db = auth_database.AuthDatabase()
    db.create_user('operator', 'operator@example.org', 'secret-hash', 'user')
    with db._get_connection() as conn:
        user_id = conn.execute('SELECT id FROM users').fetchone()[0]
        conn.execute("INSERT INTO refresh_tokens(user_id, token_hash, issued_at, expires_at) VALUES (?, 'secret-token', 'now', 'later')", (user_id,))
        conn.commit()
    assert db.delete_user('operator')
    with db._get_connection() as conn:
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM refresh_tokens').fetchone()[0] == 0
    preview = SQLiteHealthService(db.db_path, 'authentication', tmp_path / 'backups').preview()
    assert preview['healthy'] and 'secret' not in json.dumps(preview)


def test_recovery_routes_require_revision_and_local_confirmation(db, monkeypatch):
    from backend.api import scheduling
    from backend.api.dependencies import ConnectionContext
    value = engine(db)
    monkeypatch.setattr(scheduling, 'get_services', lambda: (value, value.db_manager, None))
    monkeypatch.setattr(scheduling, 'log_action', Mock())
    app = FastAPI(); app.include_router(scheduling.router)
    app.dependency_overrides[scheduling.get_current_user] = lambda: {'username': 'tester', 'role': 'user'}
    app.dependency_overrides[scheduling.require_local_access] = lambda: ConnectionContext(client_ip='127.0.0.1', is_local=True, ip_classification='loopback')
    schedule(db); db.mark_recovery_atomic('a', 'Abort', 'tester'); legacy_delete(db, 'a')
    client = TestClient(app)
    payload = {'schedule_id': 'a', 'expected_revision': db.get_manual_recovery_state().safety_revision, 'robot_ready': True, 'note': 'Checked'}
    assert client.post('/api/scheduling/recovery/resolve', json={**payload, 'robot_ready': False}).status_code == 400
    assert client.post('/api/scheduling/recovery/resolve', json={**payload, 'expected_revision': 0}).status_code == 409
    response = client.post('/api/scheduling/recovery/resolve', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['data']['schedule'] is None
    assert response.json()['data']['manual_recovery']['resume_required']


def test_require_and_delete_race_never_strands_a_recovery(db):
    schedule(db)
    barrier = threading.Barrier(2)
    outcomes = []
    def require():
        barrier.wait()
        try: db.mark_recovery_atomic('a', 'Abort', 'tester'); outcomes.append('required')
        except SafetyConflict: outcomes.append('require_rejected')
    def delete():
        barrier.wait()
        try: db.delete_schedule('a'); outcomes.append('deleted')
        except SafetyConflict: outcomes.append('delete_rejected')
    workers = [threading.Thread(target=require), threading.Thread(target=delete)]
    for worker in workers: worker.start()
    for worker in workers: worker.join(timeout=5); assert not worker.is_alive()
    assert sorted(outcomes) in [sorted(['required', 'delete_rejected']), sorted(['deleted', 'require_rejected'])]
    state = db.get_manual_recovery_state()
    assert not state.active or db.get_schedule_by_id('a') is not None


def test_commit_failure_rolls_back_recovery(db, monkeypatch):
    schedule(db)
    original = db._get_connection
    class FailingCommit:
        def __init__(self, conn): self.conn = conn
        def __getattr__(self, name): return getattr(self.conn, name)
        def commit(self): raise sqlite3.OperationalError('injected commit failure')
    @contextmanager
    def connection():
        with original() as conn: yield FailingCommit(conn)
    monkeypatch.setattr(db, '_get_connection', connection)
    with pytest.raises(sqlite3.Error): db.mark_recovery_atomic('a', 'Abort', 'tester')
    monkeypatch.setattr(db, '_get_connection', original)
    assert not db.get_schedule_by_id('a').recovery_required
    assert not db.get_manual_recovery_state().active


def test_read_only_write_failure_latches_hold(db, monkeypatch):
    schedule(db)
    original = db._get_connection
    @contextmanager
    def read_only():
        with original() as conn:
            conn.execute('PRAGMA query_only = ON')
            yield conn
    monkeypatch.setattr(db, '_get_connection', read_only)
    with pytest.raises(sqlite3.Error): db.mark_recovery_atomic('a', 'Abort', 'tester')
    monkeypatch.setattr(db, '_get_connection', original)
    assert db.get_manual_recovery_state().resume_required


def test_orphan_notification_preserves_identity(db):
    schedule(db); legacy_delete(db, 'a')
    entry = NotificationLogEntry(log_id='notice', schedule_id='a', execution_id='run', event_type='test', status='pending', recipients=[])
    assert db.create_notification_log(entry)
    with db._get_connection() as conn:
        row = conn.execute('SELECT schedule_id, metadata FROM NotificationLog').fetchone()
        assert row['schedule_id'] is None
        assert json.loads(row['metadata'])['original_schedule_id'] == 'a'


def test_new_recovery_invalidates_resume_preview(db):
    schedule(db); schedule(db, 'b')
    db.mark_recovery_atomic('a', 'Abort', 'tester')
    db.resolve_recovery_atomic('a', None, 'tester', db.get_manual_recovery_state().safety_revision)
    stale = db.get_manual_recovery_state().safety_revision
    db.mark_recovery_atomic('b', 'Another abort', 'tester')
    with pytest.raises(SafetyConflict): db.resume_dispatch(stale, 'tester')


def test_unfinished_orphan_requires_explicit_reconciliation(db, tmp_path):
    schedule(db); db.create_job_execution(JobExecution(execution_id='run', schedule_id='a', status='running')); legacy_delete(db, 'a')
    health = SQLiteHealthService(db.db_path, 'scheduling', tmp_path / 'backups')
    preview = health.preview()
    assert preview['issues'][0]['kind'] == 'unfinished_execution'
    with pytest.raises(SafetyConflict): health.repair(preview['token'], 'admin')
    result = health.reconcile_orphan(preview['token'], 'run', 'admin', 'Robot checked, no process remains')
    assert result['preview']['healthy']
    assert RunLogStore(db).execution('run').status == 'cancelled'
    assert db.get_manual_recovery_state().resume_required


def test_corrupt_storage_has_no_automatic_repair(tmp_path):
    path = tmp_path / 'corrupt.db'; path.write_bytes(b'not a SQLite database')
    preview = SQLiteHealthService(path, 'scheduling', tmp_path / 'backups').preview()
    assert preview['structural_error'] and preview['token'] is None


def test_missing_scheduler_state_repair_requires_acknowledgement(db, tmp_path):
    with db._get_connection() as conn:
        conn.execute('DELETE FROM SchedulerState'); conn.commit()
    health = SQLiteHealthService(db.db_path, 'scheduling', tmp_path / 'backups')
    result = health.repair(health.preview()['token'], 'admin')
    assert result['preview']['healthy']
    state = db.get_manual_recovery_state()
    assert state.active and state.schedule_missing and state.resume_required
    db.resolve_recovery_atomic(None, 'Checked robot', 'operator', state.safety_revision)
    assert db.get_manual_recovery_state().resume_required


def test_exclusive_database_lock_has_bounded_wait_and_requires_resume(db):
    import time
    blocker = sqlite3.connect(db.db_path)
    try:
        blocker.execute('BEGIN EXCLUSIVE')
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError): db.get_manual_recovery_state()
        assert time.monotonic() - started < 4
    finally:
        blocker.rollback(); blocker.close()
    assert db.get_manual_recovery_state().resume_required


def test_stale_contact_selection_rolls_back_the_schedule_edit(db):
    item = schedule(db)
    item.experiment_name = 'Should not be saved'
    item.notification_contacts = ['deleted-contact']
    with pytest.raises(SafetyConflict, match='contact was deleted'): db.update_schedule(item)
    assert db.get_schedule_by_id('a').experiment_name == 'Method a'


def test_health_preview_requires_local_administrator(db, tmp_path, monkeypatch):
    from backend.api import sqlite_health
    from backend.api.dependencies import ConnectionContext, get_connection_context
    user = {'role': 'user', 'username': 'tester'}
    local = [True]
    app = FastAPI(); app.include_router(sqlite_health.router)
    app.dependency_overrides[sqlite_health.get_current_user] = lambda: user
    app.dependency_overrides[get_connection_context] = lambda: ConnectionContext('127.0.0.1', local[0], 'loopback')
    monkeypatch.setattr(sqlite_health, 'service', lambda _: SQLiteHealthService(db.db_path, 'scheduling', tmp_path / 'backups'))
    client = TestClient(app)
    assert client.get('/api/admin/sqlite/scheduling/preview').status_code == 403
    user['role'] = 'admin'; local[0] = False
    assert client.get('/api/admin/sqlite/scheduling/preview').status_code == 403
    local[0] = True
    assert client.get('/api/admin/sqlite/scheduling/preview').json()['healthy']


def test_archived_unfinished_run_is_reviewable_and_blocks_resume(db, tmp_path):
    with db._get_connection() as conn:
        conn.execute("INSERT INTO JobExecutionsArchive(execution_id, schedule_id, status, created_at) VALUES ('old', 'missing', 'running', CURRENT_TIMESTAMP)")
        conn.commit()
    health = SQLiteHealthService(db.db_path, 'scheduling', tmp_path / 'backups')
    state = db.get_manual_recovery_state()
    assert not state.storage_healthy
    with pytest.raises(SafetyConflict): db.resume_dispatch(state.safety_revision, 'tester')
    health.reconcile_orphan(health.preview()['token'], 'old', 'admin', 'Robot checked')
    assert RunLogStore(db).execution('old').status == 'cancelled'
    assert db.get_manual_recovery_state().resume_required


def test_locked_recovery_request_does_not_block_health(db, monkeypatch):
    import asyncio
    import httpx
    from backend.api import scheduling
    from backend.api.dependencies import ConnectionContext
    schedule(db); value = engine(db)
    entered = threading.Event()
    original = value.db_manager.get_schedule_by_id
    def read(key):
        entered.set()
        return original(key)
    monkeypatch.setattr(value.db_manager, 'get_schedule_by_id', read)
    monkeypatch.setattr(scheduling, 'get_services', lambda: (value, value.db_manager, None))
    monkeypatch.setattr(scheduling, 'log_action', Mock())
    app = FastAPI(); app.include_router(scheduling.router)
    app.dependency_overrides[scheduling.get_current_user] = lambda: {'username': 'tester', 'role': 'user'}
    app.dependency_overrides[scheduling.require_local_access] = lambda: ConnectionContext('127.0.0.1', True, 'loopback')
    @app.get('/health')
    async def health(): return {'ok': True}
    blocker = sqlite3.connect(db.db_path)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
            pending = asyncio.create_task(client.post('/api/scheduling/a/recovery/require', json={'note': 'Test'}))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                result = await asyncio.wait_for(client.get('/health'), 0.5)
                assert result.status_code == 200
            finally:
                blocker.rollback()
            assert (await pending).status_code == 200
    try:
        blocker.execute('BEGIN EXCLUSIVE')
        asyncio.run(scenario())
    finally: blocker.close()
