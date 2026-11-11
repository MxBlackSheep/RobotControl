"""Offline stored-data checks, using disposable SQLite and JSON files only.

Run: .venv/Scripts/python.exe -m backend.e2e.stored_data_check
Failure cases: a raised upgrade commits partial data/version, destroys its backup,
repeats a completed step, or writes a newer store; fresh and installed-copy schemas
diverge; a failed scheduling upgrade prevents construction or permits storage access.
Installed files are copied and hashed, never opened for writing. No robot launch.
Review rows remain listed/editable/deletable and protect package references; bad JSON
does not hide other rows. Activation, archive, launch and path corrections refuse them.
"""
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from unittest.mock import patch

from backend.services.sqlite_health import SQLiteHealthService
from backend.services.sqlite_safety import StorageUnavailable, configure_connection
from backend.services.stored_data import UpgradeStopped, upgrade_json, upgrade_sqlite


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def connection(path):
    @contextmanager
    def connect():
        with closing(sqlite3.connect(path)) as conn:
            configure_connection(conn)
            yield conn
    return connect


def stopped(action, step):
    try:
        action()
    except UpgradeStopped as exc:
        assert exc.step == step, str(exc)
        return exc
    raise AssertionError('Upgrade should have stopped')


def runner_checks(root):
    path = root / 'runner.db'
    connect = connection(path)
    health = SQLiteHealthService(path, 'scheduling', root / 'backups')

    def first(conn):
        conn.execute('CREATE TABLE records(value TEXT)')
        conn.execute("INSERT INTO records VALUES ('kept')")

    def failing(conn):
        conn.execute("UPDATE records SET value = 'lost'")
        conn.execute('CREATE TABLE partial(value TEXT)')
        raise ValueError('deliberate failure')

    upgrade_sqlite(connect, [first], health._backup)
    original = digest(path)
    backups = {}
    def backup():
        saved = health._backup()
        backups[saved] = digest(saved)
        return saved
    error = stopped(lambda: upgrade_sqlite(connect, [first, failing], backup), 2)
    assert 'deliberate failure' in str(error) and str(error.backup_path) in str(error)
    assert digest(path) == original
    assert digest(error.backup_path) == backups[error.backup_path]
    with connect() as current, connection(error.backup_path)() as saved:
        assert list(current.iterdump()) == list(saved.iterdump())
    with connect() as conn:
        assert conn.execute('SELECT MAX(version) FROM SchemaMigrations').fetchone()[0] == 1
        assert conn.execute('SELECT value FROM records').fetchone()[0] == 'kept'
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'partial'").fetchone()
    backup_digest = digest(error.backup_path)
    upgrade_sqlite(connect, [first, lambda conn: conn.execute("UPDATE records SET value = 'upgraded'")], health._backup)
    assert digest(error.backup_path) == backup_digest
    unchanged = digest(path)
    with patch.object(health, '_backup', side_effect=AssertionError('No backup for a current/newer store')):
        upgrade_sqlite(connect, [first, failing], health._backup)
        stopped(lambda: upgrade_sqlite(connect, [first], health._backup), 2)
    assert digest(path) == unchanged

    path = root / 'settings.json'
    path.write_text('{"value": "kept"}', encoding='utf-8')
    original = digest(path)

    def bad_json(data):
        data['value'] = 'lost'
        raise ValueError('deliberate JSON failure')

    error = stopped(lambda: upgrade_json(path, {2: bad_json}), 2)
    assert digest(path) == original == digest(error.backup_path)
    upgrade_json(path, {2: lambda data: data.update(value='upgraded')})
    assert json.loads(path.read_text()) == {'version': 2, 'value': 'upgraded'}
    assert digest(error.backup_path) == original
    unchanged = digest(path)
    stopped(lambda: upgrade_json(path, {}), 2)
    assert digest(path) == unchanged
    path.write_text('{', encoding='utf-8')
    stopped(lambda: upgrade_json(path, {2: bad_json}), None)
    assert path.read_text() == '{'
    print('PASS: SQLite/JSON upgrade, rollback, backup, repeat and newer-version checks')


def schema_checks(root):
    from backend.services.scheduling import sqlite_database as module

    installed = Path.home() / 'Documents/RobotControl/data/robotcontrol_scheduling.db'
    assert installed.is_file(), f'Installed fixture missing: {installed}'
    before = digest(installed)
    copied = root / 'installed.db'
    shutil.copyfile(installed, copied)
    with connection(copied)() as conn:
        columns = len(conn.execute('PRAGMA table_info(ScheduledExperiments)').fetchall())
        assert columns == 25, f'Installed fixture changed: expected 25 columns, got {columns}'
    with patch.object(module, 'get_data_path', return_value=root):
        old = module.SQLiteSchedulingDatabase(str(copied))
        fresh = module.SQLiteSchedulingDatabase('empty.db')
        for store in (old, fresh):
            with store._get_connection() as conn:
                assert conn.execute('SELECT MAX(version) FROM SchemaMigrations').fetchone()[0] == 4
        with old._get_connection() as a, fresh._get_connection() as b:
            tables = [r[0] for r in b.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                assert [tuple(r) for r in a.execute(f'PRAGMA table_info({table})')] == [tuple(r) for r in b.execute(f'PRAGMA table_info({table})')], table
        with fresh._get_connection() as conn:
            conn.execute('UPDATE SchedulerState SET recovery_required=1, resume_required=0')
            conn.commit()
        assert not module.SQLiteSchedulingDatabase('empty.db').get_manual_recovery_state().resume_required
        with fresh._get_connection() as conn:
            conn.execute('DELETE FROM SchemaMigrations')
            conn.commit()
        assert module.SQLiteSchedulingDatabase('empty.db').get_manual_recovery_state().resume_required

        # Older stores can have schedule recovery flags but no global state table yet.
        prior = module.SQLiteSchedulingDatabase('before-state.db')
        with prior._get_connection() as conn:
            conn.execute("INSERT INTO ScheduledExperiments(schedule_id, experiment_name, experiment_path, schedule_type, recovery_required) VALUES ('held', 'Held', 'held.med', 'once', 1)")
            conn.execute('DROP TABLE SchedulerState')
            conn.execute('DELETE FROM SchemaMigrations')
            conn.commit()
        assert module.SQLiteSchedulingDatabase('before-state.db').get_manual_recovery_state().resume_required

        def fail(conn):
            conn.execute("UPDATE SchedulerState SET recovery_note='must roll back'")
            raise ValueError('schema failure')

        with fresh._get_connection() as conn:
            conn.execute('DELETE FROM SchemaMigrations WHERE version>=2')
            conn.commit()
        before_failure = digest(fresh.db_path)
        with patch.object(module.SQLiteSchedulingDatabase, '_upgrade_schema', staticmethod(fail)):
            held = module.SQLiteSchedulingDatabase('empty.db')
        assert digest(fresh.db_path) == before_failure
        assert 'step 2' in held._upgrade_error and 'schema failure' in held._upgrade_error and 'Backup:' in held._upgrade_error
        try:
            held.get_active_schedules()
        except StorageUnavailable:
            pass
        else:
            raise AssertionError('Failed upgrade must block store access')
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api import sqlite_health as api
        from backend.services.auth import get_current_user
        from types import SimpleNamespace
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
        with patch.object(api, 'get_data_path', return_value=root), patch(
            'backend.services.scheduling.get_scheduling_database_manager',
            return_value=SimpleNamespace(sqlite_db=held)), TestClient(app, client=('127.0.0.1', 1)) as client:
            reply = client.get('/api/admin/sqlite/scheduling/preview')
            assert reply.status_code == 200, reply.text
            assert reply.json()['message'] == held._upgrade_error, reply.text
            assert not reply.json()['healthy'] and reply.json()['token'] is None
    assert digest(installed) == before
    print('PASS: installed-copy/fresh schema parity, once-only recovery update and failed-upgrade hold')


def review_checks(root):
    from datetime import datetime, timedelta
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import scheduling as api
    from backend.models import ScheduledExperiment, JobExecution, NotificationContact
    from backend.services.auth import get_current_user
    from backend.services.scheduling import sqlite_database as module
    from backend.services.database_tools import DatabaseTools
    from backend.services.database_packages import PackageCatalogue, PackageError
    from backend.tests.test_sqlite_safety import engine

    with patch.object(module, 'get_data_path', return_value=root):
        db = module.SQLiteSchedulingDatabase('review.db')
    scheduler = engine(db)
    scheduler._queued_backlog = set()
    scheduler._queue_runtime = {}
    method = root / 'review.med'
    method.write_text('disposable method')
    for key in ('good', 'cron', 'bad-json'):
        row = ScheduledExperiment(key, key, str(method), 'once', created_by='admin',
                                  start_time=datetime.now() - timedelta(minutes=1))
        assert db.create_schedule(row)
    contact = NotificationContact('review-contact', 'Review contact', 'review@example.test')
    assert db.create_notification_contact(contact)
    saved = db.get_schedule_by_id('bad-json')
    saved.notification_contacts = [contact.contact_id]
    assert db.update_schedule(saved)
    assert db.create_job_execution(JobExecution('prior-run', 'bad-json', 'completed'))
    with db._get_connection() as conn:
        conn.execute("UPDATE ScheduledExperiments SET schedule_type='cron', preparation=? WHERE schedule_id='cron'",
                     (json.dumps({'package_id': 'used', 'source_id': 'connection'}),))
        conn.execute("UPDATE ScheduledExperiments SET parameters='{' WHERE schedule_id='bad-json'")
        conn.commit()
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
    with patch.object(api, 'get_services', return_value=(scheduler, scheduler.db_manager, None)), \
         patch.object(api, 'log_action'), TestClient(app, client=('127.0.0.1', 1)) as client:
        reply = client.get('/api/scheduling/list')
        assert reply.status_code == 200, reply.text
        rows = {row['schedule_id']: row for row in reply.json()['data']}
        assert set(rows) == {'good', 'cron', 'bad-json'}, reply.text
        assert rows['cron']['review_reason'] and rows['bad-json']['review_reason']
        assert rows['good']['review_reason'] is None
        assert rows['bad-json']['parameters'] == '{'
        from backend.services.scheduling.method_library import prepare_path_change, check_method_path
        db.import_experiment_methods([{'path': str(method), 'name': method.stem}], 'admin')
        target = root / 'corrected.med'
        target.write_text('disposable corrected method')
        entry = db.get_experiment_methods()[0]
        prepared = prepare_path_change(db, entry['method_id'], str(target))
        selected = [dict(schedule_id=ref['schedule_id'], role=ref['role'], expected_updated_at=ref['updated_at'])
                    for ref in prepared['references'] if ref['schedule_id'] in ('good', 'cron')]
        before = digest(db.db_path)
        try:
            db.apply_method_path_change(prepared, entry['revision'], selected)
        except ValueError as exc:
            assert 'cron' in str(exc) and rows['cron']['review_reason'] in str(exc)
        else:
            raise AssertionError('A selected review row must refuse the entire path correction')
        assert digest(db.db_path) == before
        db.apply_method_path_change(prepared, entry['revision'], [ref for ref in selected if ref['schedule_id'] == 'good'])
        assert db.get_schedule_by_id('cron').experiment_path == str(method)
        assert [s.schedule_id for s in db.get_active_schedules()] == ['good']
        scheduler._load_schedules_from_database()
        assert [s.schedule_id for s in scheduler._find_due_jobs(datetime.now())] == ['good']
        for key in ('cron', 'bad-json'):
            before = digest(db.db_path)
            for payload in ({'is_active': True}, {'start_time': datetime.now().isoformat(), 'is_active': True}):
                reply = client.put('/api/scheduling/' + key, json=payload)
                assert reply.status_code == 400, reply.text
            reply = client.post('/api/scheduling/' + key + '/archive', json={'archived': True})
            assert reply.status_code == 400, reply.text
            assert digest(db.db_path) == before
        with patch('backend.services.scheduling.database_manager.get_scheduling_database_manager', return_value=scheduler.db_manager):
            catalogue = PackageCatalogue.__new__(PackageCatalogue)
            catalogue.in_use = DatabaseTools.schedules_using
            try:
                catalogue.refuse_if_scheduled('used')
            except PackageError as exc:
                assert exc.status == 409 and 'cron' in str(exc)
            else:
                raise AssertionError('Review row must protect its package')
        original = rows['bad-json']
        reply = client.put('/api/scheduling/bad-json', json={**original, 'parameters': {}})
        assert reply.status_code == 200, reply.text
        repaired = db.get_schedule_by_id('bad-json')
        assert repaired.created_at.isoformat() == original['created_at']
        assert repaired.notification_contacts == original['notification_contacts'] == ['review-contact']
        assert db.get_execution_history('bad-json')[0]['execution_id'] == 'prior-run'
        reply = client.put('/api/scheduling/bad-json', json={'estimated_duration': 90},
                           headers={'If-Unmodified-Since': original['updated_at']})
        assert reply.status_code == 409, reply.text
        with db._get_connection() as conn:
            conn.execute("UPDATE ScheduledExperiments SET preparation='{' WHERE schedule_id='bad-json'")
            conn.commit()
        with patch('backend.services.scheduling.database_manager.get_scheduling_database_manager', return_value=scheduler.db_manager):
            assert DatabaseTools.schedules_using('used') == ['cron']
        before = digest(db.db_path)
        reply = client.put('/api/scheduling/bad-json', json={'is_active': True})
        assert reply.status_code == 400 and digest(db.db_path) == before, reply.text
        reply = client.delete('/api/scheduling/cron')
        assert reply.status_code == 200, reply.text
        assert db.get_schedule_by_id('cron') is None
    print('PASS: review listing, dispatch exclusions, repair, stale edit, delete and package protection')


def schedule_upgrade_checks(root):
    from backend.models import ScheduledExperiment
    from backend.services.scheduling import sqlite_database as module
    from backend.services.scheduling.schedule_check import check_schedule
    with patch.object(module, 'get_data_path', return_value=root):
        db = module.SQLiteSchedulingDatabase('old-schedules.db')
        for key in ('hourly', 'cron', 'noop', 'write', 'cleanup'):
            assert db.create_schedule(ScheduledExperiment(key, key, 'fixture.med', 'once'))
        with db._get_connection() as conn:
            conn.execute('DELETE FROM SchemaMigrations WHERE version > 2')
            conn.execute("UPDATE ScheduledExperiments SET schedule_type=schedule_id WHERE schedule_id IN ('hourly', 'cron')")
            conn.execute("UPDATE ScheduledExperiments SET prerequisites=? WHERE schedule_id='noop'", (json.dumps(['EvoYeastExperiment:42|none']),))
            conn.execute("UPDATE ScheduledExperiments SET prerequisites=? WHERE schedule_id='write'", (json.dumps(['ScheduledToRun', 'EvoYeastExperiment:42|set']),))
            conn.execute("UPDATE ScheduledExperiments SET timeout_action='run_cleanup_and_terminate' WHERE schedule_id='cleanup'")
            conn.commit()
        db = module.SQLiteSchedulingDatabase('old-schedules.db')
        hourly = db.get_schedule_by_id('hourly')
        assert hourly.schedule_type == 'interval' and hourly.interval_hours == 1
        assert db.get_schedule_by_id('noop').prerequisites == []
        assert {row.schedule_id for row in db.get_active_schedules()} == {'hourly', 'noop'}
        for key in ('cron', 'write', 'cleanup'):
            assert db.get_schedule_by_id(key).review_reason
        assert db.get_schedule_by_id('write').prerequisites == ['ScheduledToRun', 'EvoYeastExperiment:42|set']
        for kind in ('cron', 'hourly'):
            try:
                check_schedule({**hourly.to_dict(), 'schedule_type': kind})
            except ValueError:
                pass
            else:
                raise AssertionError(f'{kind} must no longer be accepted')
    print('PASS: hourly upgrade, no-write token upgrade and cron/write-token/cleanup review')


def route_error_checks():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import sqlite_health, scheduling
    from backend.services.auth import get_current_user
    app = FastAPI()
    app.include_router(sqlite_health.router)
    app.include_router(scheduling.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
    with patch.object(sqlite_health, 'service', side_effect=RuntimeError('fixture failure')), \
         patch.object(scheduling, 'get_services', side_effect=RuntimeError('fixture failure')), \
         TestClient(app, client=('127.0.0.1', 1), raise_server_exceptions=False) as client:
        for path in ('/api/admin/sqlite/scheduling/preview', '/api/scheduling/list'):
            reply = client.get(path)
            assert reply.status_code == 500 and reply.text == '{"detail":"Internal server error"}', reply.text
    print('PASS: SafetyRoute unexpected errors return logged JSON 500 responses')


def existing_run_review_checks(root):
    from datetime import datetime
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import scheduling as api
    from backend.services.auth import get_current_user
    from backend.services.scheduling.run_log_monitor import RunLogMonitor
    from backend.tests.test_run_log_monitor import rig, stall
    from backend.tests.test_sqlite_safety import engine
    folder = root / 'existing-run'
    folder.mkdir()
    fixture = rig.__wrapped__(folder)
    with fixture.db._get_connection() as conn:
        conn.execute("UPDATE ScheduledExperiments SET mode='invalid' WHERE schedule_id='schedule'")
        conn.commit()
    row = fixture.db.get_schedule_by_id('schedule')
    assert row.review_reason
    stall(fixture)
    sent = []
    def alert(schedule, execution, **kwargs):
        sent.append((schedule, kwargs['contacts']))
        return SimpleNamespace(sent=True, cancelled=False, delivery_status='sent', error=None,
                               recipients=['operator@example.test'], attachments=[], subject='Alert', body='Alert', attachment_notes=[])
    fixture.monitor.deliver_pending(lambda: SimpleNamespace(schedule_alert=alert))
    assert len(sent) == 1 and sent[0][0].review_reason
    assert sent[0][1][0].contact_id == 'operator'
    assert fixture.db.get_notification_logs()[0].status == 'sent'
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
    with patch.object(api, 'get_services', return_value=(None, fixture.manager, None)), \
         patch.object(api, 'log_action'), \
         patch.object(api, 'EmailNotificationService', return_value=SimpleNamespace(delivery_log_warning=None)), \
         patch.object(api, 'send_recorded', return_value=True) as send, \
         TestClient(app, client=('127.0.0.1', 1)) as client:
        reply = client.post('/api/scheduling/notifications/send', json={'schedule_id': 'schedule', 'subject': 'Manual', 'body': 'Manual'})
        assert reply.status_code == 200 and reply.json()['data']['sent'], reply.text
        assert send.call_args.kwargs['to'] == ['operator@example.test']
    # A restart still tracks a running execution whose schedule now needs review.
    monitor = RunLogMonitor(fixture.manager, reader=fixture.reader, directory=fixture.directory)
    assert len(monitor.restore()) == 1
    scheduler = engine(fixture.db)
    scheduler._queued_backlog = set()
    scheduler._queue_runtime = {}
    scheduler.run_log_monitor = monitor
    before = row.to_dict()
    execution = monitor.store.execution('execution')
    execution.status = 'completed'
    execution.end_time = datetime.now()
    scheduler._finalize_execution(row, execution)
    assert monitor.store.execution('execution').status == 'completed'
    assert fixture.db.get_schedule_by_id('schedule').to_dict() == before
    assert not monitor.snapshots()
    updated = scheduler.require_manual_recovery('schedule', 'Review existing run', 'admin')
    assert updated.recovery_required and 'schedule' not in scheduler._active_schedules
    print('PASS: review rows retain manual email, pending run alerts, restart tracking and execution completion without schedule advancement')


def run():
    with tempfile.TemporaryDirectory(prefix='rc-stored-data-') as folder:
        root = Path(folder)
        runner_checks(root)
        schema_checks(root)
        review_checks(root)
        schedule_upgrade_checks(root)
        route_error_checks()
        existing_run_review_checks(root)


if __name__ == '__main__':
    run()
