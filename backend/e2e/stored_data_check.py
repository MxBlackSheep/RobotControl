"""Offline stored-data checks, using disposable SQLite and JSON files only.

Run: .venv/Scripts/python.exe -m backend.e2e.stored_data_check
Failure cases: a raised upgrade commits partial data/version, destroys its backup,
repeats a completed step, or writes a newer store; fresh and installed-copy schemas
diverge; a failed scheduling upgrade prevents construction or permits storage access.
Installed files are copied and hashed, never opened for writing. No robot launch.
Review rows remain listed/editable/deletable and protect package references; bad JSON
does not hide other rows; a VENUS form without parameters repairs unreadable JSON.
List times must use the runtime next run and newest finished
execution, with no next run for review/inactive/archived rows; queue reports engine state. Activation, archive, launch and path corrections refuse them.
Contacts: a stored contact that fails the route check hides the others or the list, gets
mail (alone or with checked contacts), drops from a schedule's contacts, or cannot be
edited back or deleted; an alert whose every recipient is under review leaves no record; a
row whose timestamp does not parse cuts off the contacts after it.
Email settings: a stored row that fails the settings check reads as unconfigured (defaults),
hides its values or reason, returns the password, still sends (test or alert), or stays
under review after a valid save; a database that never had settings reads as under review;
a row with both STARTTLS and SSL stops sending (it reads as SSL); a stored recipient that is
not text reads as defaults; the route's 400 order changes.
Users: any user of a copy of this PC's installed sign-in database, the administrator with
its dot-less email above all, fails the check (a lockout); a user under review is missing
from the Admin list or hides its reason, signs in, keeps a working access or refresh token,
cannot request a password reset, stays under review after the admin's reset or email edit,
or cannot be deleted; another user cannot sign in. A bad ROBOTCONTROL_ADMIN_EMAIL stops an
installation whose administrator exists, or writes an administrator into a fresh database.
No email or hash is printed.
Report drafts: one unreadable draft file hides the others or fails the list; a truncated file
or a draft the model refuses is missing from the list, tries, checks or installs, or cannot
be deleted; a truncated file opens or is rewritten (its bytes change before Delete); a readable
draft under review cannot be opened or its save leaves the review; another owner sees a readable
draft; a draft whose owner is null is hidden, opens or cannot be deleted; another administrator
opens or saves a draft under review; a draft with a field the model no longer has, or a
revision that is not a number, opens but can never be saved; a file that cannot be read fails
the whole list. A draft from the removed report wizard (no defining Python file) is missing from
the list or hides its reason, opens, saves, tries, checks or installs, or changes before Delete.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from unittest.mock import patch

from backend.services.sqlite_health import SQLiteHealthService
from backend.services.sqlite_safety import StorageUnavailable, configure_connection
from backend.services.stored_data import UpgradeStopped, upgrade_json, upgrade_sqlite

# Sign-in keys from the environment, so no key file is written to the real data folder.
os.environ.setdefault('ROBOTCONTROL_ACCESS_TOKEN_SECRET', 'check-access-key-' + 'a' * 48)
os.environ.setdefault('ROBOTCONTROL_REFRESH_TOKEN_SECRET', 'check-refresh-key-' + 'b' * 48)


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
        assert rows['cron']['review_reason'] == "The schedule type 'cron' is no longer supported", rows['cron']
        assert rows['bad-json']['review_reason'] == 'The protocol parameters cannot be read', rows['bad-json']
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
            # VENUS parameters are ignored and repaired by any update; unsupported
            # schedule types still refuse activation and every review row refuses archive.
            if key == 'cron':
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
        # buildScheduleRequest sends parameters/protocol_id only for PyHSL.
        body = {key: original[key] for key in (
            'experiment_name', 'experiment_path', 'runner', 'schedule_type', 'start_time',
            'estimated_duration', 'log_inactivity_threshold_minutes', 'mode', 'is_active',
            'timeout_config', 'preparation', 'notification_contacts')}
        body['expected_updated_at'] = original['updated_at']
        reply = client.put('/api/scheduling/bad-json', json=body)
        assert reply.status_code == 200, reply.text
        repaired = db.get_schedule_by_id('bad-json')
        assert not getattr(repaired, 'review_reason', None) and repaired.parameters == {}
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


def schedule_status_checks(root):
    """HTTP list/status use runtime times, finished history and scheduler state."""
    from copy import deepcopy
    from datetime import datetime, timedelta
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import scheduling as api
    from backend.models import ScheduledExperiment, JobExecution
    from backend.services.auth import get_current_user
    from backend.services.scheduling import sqlite_database as module
    from backend.tests.test_sqlite_safety import engine

    with patch.object(module, 'get_data_path', return_value=root):
        db = module.SQLiteSchedulingDatabase('list-status.db')
    scheduler = engine(db)
    scheduler._queued_backlog = set()
    scheduler._queue_runtime = {}
    scheduler.process_monitor.is_hamilton_running = lambda: False
    start = datetime(2030, 1, 1, 12)
    for key in ('active', 'empty', 'inactive', 'archived', 'review'):
        row = ScheduledExperiment(key, key, 'fixture.med', 'interval',
                                  start_time=start, interval_hours=1,
                                  is_active=key != 'inactive', archived=key == 'archived')
        assert db.create_schedule(row)
        scheduler._active_schedules[key] = deepcopy(row)
    next_run = start + timedelta(hours=2)
    scheduler._active_schedules['active'].start_time = next_run
    with db._get_connection() as conn:
        conn.execute("UPDATE ScheduledExperiments SET schedule_type='cron' WHERE schedule_id='review'")
        conn.commit()
    for key, end, status in [('latest', start, 'failed'),
                              ('older', start - timedelta(hours=1), 'completed'),
                              ('unfinished', None, 'pending')]:
        assert db.create_job_execution(JobExecution(key, 'active', status, end_time=end))
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
    with patch.object(api, 'get_services', return_value=(scheduler, scheduler.db_manager, None)), TestClient(app) as client:
        for running in (True, False):
            scheduler._running = running
            reply = client.get('/api/scheduling/status/queue')
            assert reply.status_code == 200, reply.text
            assert reply.json()['data']['is_running'] is running, reply.text
        rows = {}
        for archived in (False, True):
            reply = client.get('/api/scheduling/list', params={'archived_only': archived, 'active_only': False})
            assert reply.status_code == 200, reply.text
            rows.update({row['schedule_id']: row for row in reply.json()['data']})
        assert rows['active']['last_run'] == start.isoformat(), rows['active']
        assert rows['active']['next_run'] == next_run.isoformat(), rows['active']
        assert rows['empty']['last_run'] is None
        assert rows['empty']['next_run'] == start.isoformat()
        for key in ('inactive', 'archived', 'review'):
            assert rows[key]['next_run'] is None, rows[key]
            assert rows[key]['last_run'] is None, rows[key]
        assert client.get('/api/scheduling/status/scheduler').status_code == 404
    print('PASS: HTTP list runtime next run, latest finished run and queue scheduler state')


def contact_review_checks(root):
    import threading
    from datetime import datetime
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import scheduling as api
    from backend.models import ScheduledExperiment, JobExecution, NotificationContact
    from backend.services.auth import get_current_user
    from backend.services.scheduling import sqlite_database as module
    from backend.tests.test_sqlite_safety import engine

    with patch.object(module, 'get_data_path', return_value=root):
        db = module.SQLiteSchedulingDatabase('contacts.db')
    for key in ('nameless', 'unaddressed', 'checked'):
        assert db.create_notification_contact(NotificationContact(key, key.title(), f'{key}@example.test'))
    with db._get_connection() as conn:
        conn.execute("UPDATE NotificationContacts SET display_name='' WHERE contact_id='nameless'")
        conn.execute("UPDATE NotificationContacts SET email_address='not an address' WHERE contact_id='unaddressed'")
        conn.commit()
    for key, contacts in (('mixed', ['nameless', 'unaddressed', 'checked']), ('reviewed', ['nameless', 'unaddressed'])):
        assert db.create_schedule(ScheduledExperiment(key, key, 'fixture.med', 'once', notification_contacts=contacts))
    scheduler = engine(db)
    scheduler._contacts_lock = threading.RLock()
    scheduler.config.enable_notifications = True
    scheduler.run_log_monitor = SimpleNamespace(snapshot=lambda execution_id: None)
    sent = []
    def alert(schedule, execution, **kwargs):
        sent.append((schedule.schedule_id, [c.contact_id for c in kwargs['contacts']]))
        return SimpleNamespace(sent=True, delivery_status='sent', error=None, recipients=['checked@example.test'],
                               attachments=[], subject='Alert', body='Alert', attachment_notes=[])
    scheduler._notification_service = SimpleNamespace(schedule_alert=alert)
    scheduler.refresh_notification_contacts(include_inactive=True)
    for key in ('mixed', 'reviewed'):
        execution = JobExecution(f'{key}-run', key, 'failed', end_time=datetime.now())
        assert db.create_job_execution(execution)
        scheduler._notify_execution_event(db.get_schedule_by_id(key), execution, 'execution_failed')
    assert sent == [('mixed', ['checked'])], sent
    logged = {entry.schedule_id: entry for entry in db.get_notification_logs()}
    assert logged['reviewed'].status != 'sent' and 'Needs review' in (logged['reviewed'].error_message or ''), logged['reviewed']
    assert db.get_schedule_by_id('reviewed').notification_contacts == ['nameless', 'unaddressed']

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
    with patch.object(api, 'get_services', return_value=(scheduler, scheduler.db_manager, None)), \
         patch.object(api, 'log_action'), TestClient(app, client=('127.0.0.1', 1)) as client:
        reply = client.get('/api/scheduling/contacts', params={'include_inactive': True})
        assert reply.status_code == 200, reply.text
        rows = {row['contact_id']: row for row in reply.json()['data']}
        assert set(rows) == {'nameless', 'unaddressed', 'checked'}, reply.text
        assert rows['nameless']['review_reason'] == 'The contact has no name', reply.text
        assert rows['unaddressed']['review_reason'] == "The contact's address is not a valid email address", reply.text
        assert rows['checked']['review_reason'] is None and rows['unaddressed']['email_address'] == 'not an address'
        reply = client.put('/api/scheduling/reviewed', json={'notification_contacts': ['nameless', 'unaddressed']})
        assert reply.status_code == 200, reply.text
        before = digest(db.db_path)
        reply = client.put('/api/scheduling/contacts/unaddressed', json={'display_name': 'Unaddressed', 'email_address': 'still wrong'})
        assert reply.status_code == 400 and reply.json()['detail'] == 'Invalid email address format', reply.text
        assert digest(db.db_path) == before
        reply = client.put('/api/scheduling/contacts/unaddressed', json={'display_name': 'Unaddressed', 'email_address': 'fixed@example.test'})
        assert reply.status_code == 200, reply.text
        assert reply.json()['data']['review_reason'] is None, reply.text
        assert scheduler.get_notification_contact('unaddressed').email_address == 'fixed@example.test'
        reply = client.delete('/api/scheduling/contacts/nameless')
        assert reply.status_code == 200, reply.text
        reply = client.get('/api/scheduling/contacts', params={'include_inactive': True})
        assert {row['contact_id']: row['review_reason'] for row in reply.json()['data']} == {'unaddressed': None, 'checked': None}
    # A timestamp that does not parse is a review of that row only; the contacts after it still read.
    with patch.object(module, 'get_data_path', return_value=root):
        timed = module.SQLiteSchedulingDatabase('contact-times.db')
    for key in ('a-first', 'b-untimed', 'c-last'):
        assert timed.create_notification_contact(NotificationContact(key, key, f'{key}@example.test'))
    with timed._get_connection() as conn:
        conn.execute("UPDATE NotificationContacts SET created_at='not a time' WHERE contact_id='b-untimed'")
        conn.commit()
    listed = {c.contact_id: c.review_reason for c in timed.get_notification_contacts(include_inactive=True, include_review=True)}
    assert list(listed) == ['a-first', 'b-untimed', 'c-last'] and not listed['c-last'], listed
    assert listed['b-untimed'] == "The contact's saved date cannot be read", listed
    assert [c.contact_id for c in timed.get_notification_contacts(include_inactive=True)] == ['a-first', 'c-last']
    print('PASS: contact review listing, checked-only mail, review-only alert record, repair and delete')


def email_settings_review_checks(root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import scheduling as api
    from backend.services import notifications
    from backend.services.auth import get_current_user
    from backend.services.scheduling import sqlite_database as module
    from backend.tests.test_sqlite_safety import engine

    with patch.object(module, 'get_data_path', return_value=root):
        db = module.SQLiteSchedulingDatabase('email-settings.db')
    scheduler = engine(db)
    scheduler.refresh_notification_service = lambda: None
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'admin', 'role': 'admin'}
    valid = {'host': 'smtp.example.test', 'port': 587, 'sender': 'robot@example.test', 'use_tls': True, 'use_ssl': False,
             'manual_recovery_recipients': ['operator@example.test']}
    with patch.object(api, 'get_services', return_value=(scheduler, scheduler.db_manager, None)), \
         patch.object(api, 'log_action'), \
         patch.object(notifications, '_load_notification_settings', side_effect=db.get_notification_settings), \
         TestClient(app, client=('127.0.0.1', 1)) as client:
        reply = client.get('/api/scheduling/notifications/settings')
        assert reply.status_code == 200 and reply.json()['data']['review_reason'] is None, reply.text
        assert reply.json()['data']['host'] is None
        for column, value, shown, reason in (('smtp_port', 0, 'port', 'The mail server port 0 is not between 1 and 65535'),
                                             ('smtp_sender', 'not an address', 'sender', 'The From address is not a valid email address')):
            assert client.put('/api/scheduling/notifications/settings', json=valid).status_code == 200
            with db._get_connection() as conn:
                conn.execute(f"UPDATE NotificationSettings SET {column}=?, smtp_password_encrypted='stored secret'", (value,))
                conn.commit()
            reply = client.get('/api/scheduling/notifications/settings')
            data = reply.json()['data']
            assert data['review_reason'] == reason and data[shown] == value and data['host'] == valid['host'], reply.text
            assert 'stored secret' not in reply.text and data['has_password'], reply.text
            service = notifications.EmailNotificationService()
            assert not service.send('Alert', 'Alert', to=['operator@example.test'])
            assert 'Needs review' in service.last_error, service.last_error
            reply = client.post('/api/scheduling/notifications/settings/test', json={'recipient': 'operator@example.test'})
            assert reply.status_code == 400 and data['review_reason'] in reply.json()['detail'], reply.text
            reply = client.put('/api/scheduling/notifications/settings', json=valid)
            assert reply.status_code == 200 and reply.json()['data']['review_reason'] is None, reply.text
            assert client.get('/api/scheduling/notifications/settings').json()['data']['review_reason'] is None
        reply = client.put('/api/scheduling/notifications/settings', json={**valid, 'port': 0})
        assert reply.status_code == 400 and reply.json()['detail'] == 'port must be between 1 and 65535', reply.text
        reply = client.put('/api/scheduling/notifications/settings', json={**valid, 'host': '', 'manual_recovery_recipients': 5})
        assert reply.status_code == 400 and reply.json()['detail'] == 'host is required', reply.text
        # Both encryption flags stored: read as SSL and keep sending, as before the check existed.
        with db._get_connection() as conn:
            conn.execute("UPDATE NotificationSettings SET use_tls=1, use_ssl=1, smtp_password_encrypted=NULL")
            conn.commit()
        data = client.get('/api/scheduling/notifications/settings').json()['data']
        assert data['review_reason'] is None and data['use_ssl'] and not data['use_tls'], data
        assert notifications.EmailNotificationService().config.is_enabled
        with db._get_connection() as conn:
            conn.execute("UPDATE NotificationSettings SET manual_recovery_recipients=X'35'")  # a BLOB keeps its type in a TEXT column
            conn.commit()
        data = client.get('/api/scheduling/notifications/settings').json()['data']
        assert data['review_reason'] == 'A recovery recipient is not an email address', data
    print('PASS: email settings review keeps stored values, sends nothing, clears on save; a fresh database is not under review')


def user_review_checks(root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import admin as admin_api, auth as auth_api
    from backend.services import auth as module
    from backend.services.auth_database import AuthDatabase

    installed = Path.home() / 'Documents/RobotControl/data/robotcontrol_auth.db'
    assert installed.is_file(), f'Installed fixture missing: {installed}'
    before = digest(installed)
    copied = root / 'installed-auth.db'
    shutil.copyfile(installed, copied)
    with patch.object(module, 'get_auth_database', return_value=AuthDatabase(str(copied))):
        service = module.AuthService()
    rows = service.db.list_users()
    reasons = [service._row_to_user(row).review_reason for row in rows]
    assert len(rows) == 4 and reasons == [None] * 4, f'{len(rows)} users, reasons {reasons}'
    assert any(row['role'] == 'admin' and '.' not in row['email'].split('@', 1)[1] for row in rows), 'Dot-less administrator email missing from the fixture'
    assert digest(installed) == before

    with patch.object(module, 'get_auth_database', return_value=AuthDatabase(str(root / 'users.db'))):
        service = module.AuthService()
    # A bad bootstrap email is refused only when the administrator row would be written.
    with patch.object(module, 'DEFAULT_ADMIN_EMAIL', 'admin-without-at'):
        with patch.object(module, 'get_auth_database', return_value=AuthDatabase(str(root / 'users.db'))):
            restarted = module.AuthService()
        assert restarted.login(module.DEFAULT_ADMIN_USERNAME, module.DEFAULT_ADMIN_PASSWORD)
        fresh = AuthDatabase(str(root / 'fresh-users.db'))
        try:
            with patch.object(module, 'get_auth_database', return_value=fresh):
                module.AuthService()
        except ValueError as exc:
            assert 'ROBOTCONTROL_ADMIN_EMAIL' in str(exc), str(exc)
        else:
            raise AssertionError('A bootstrap administrator that fails the user check must not be written')
        assert fresh.list_users() == []
    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(admin_api.router, prefix='/api/admin')
    app.dependency_overrides[module.get_auth_service] = lambda: service
    with patch.object(module, 'get_auth_service', return_value=service), \
         patch.object(admin_api, 'get_auth_service', return_value=service), \
         TestClient(app, client=('127.0.0.1', 1)) as client:
        def sign_in(username, password):
            return client.post('/api/auth/login', json={'username': username, 'password': password})
        for name in ('broken', 'other'):
            service.register_user(name, f'{name}@example.test', 'first-password')
        admin = sign_in(module.DEFAULT_ADMIN_USERNAME, module.DEFAULT_ADMIN_PASSWORD)
        assert admin.status_code == 200, admin.text
        bearer = {'Authorization': f"Bearer {admin.cookies['rc_access']}"}
        tokens = sign_in('broken', 'first-password').cookies
        client.cookies.clear()
        with service.db._get_connection() as conn:
            conn.execute("UPDATE users SET password_hash='' WHERE username='broken'")
            conn.commit()

        def listed():
            reply = client.get('/api/admin/users', headers=bearer)
            assert reply.status_code == 200, reply.text
            return {row['username']: row.get('review_reason', 'missing') for row in reply.json()['data']}
        users = listed()
        assert users['broken'] == "The user's saved password cannot be checked" and users['other'] is None and users['admin'] is None, users
        assert sign_in('broken', 'first-password').status_code == 401
        assert client.get('/api/auth/me', headers={'Authorization': f"Bearer {tokens['rc_access']}"}).status_code == 401
        client.cookies.clear()
        assert client.post('/api/auth/refresh', headers={'Cookie': f"rc_refresh={tokens['rc_refresh']}"}).status_code == 401
        assert sign_in('other', 'first-password').status_code == 200
        reply = client.post('/api/auth/password-reset/request', json={'username': 'broken', 'note': 'locked out'})
        assert reply.status_code == 202 and reply.json()['data'].get('request_id'), reply.text
        reply = client.post('/api/admin/users/broken/reset-password', headers=bearer, json={'new_password': 'second-password', 'must_reset': False})
        assert reply.status_code == 200, reply.text
        assert listed()['broken'] is None and sign_in('broken', 'second-password').status_code == 200

        with service.db._get_connection() as conn:
            conn.execute("UPDATE users SET email='other-without-at' WHERE username='other'")
            conn.commit()
        assert listed()['other'] == "The user's email address has no @" and sign_in('other', 'first-password').status_code == 401
        reply = client.put('/api/admin/users/other/email', headers=bearer, json={'email': 'other@example.com'})
        assert reply.status_code == 200, reply.text
        assert listed()['other'] is None and sign_in('other', 'first-password').status_code == 200

        with service.db._get_connection() as conn:
            conn.execute("UPDATE users SET password_hash='not a hash' WHERE username='other'")
            conn.commit()
        assert listed()['other']
        assert client.delete('/api/admin/users/other', headers=bearer).status_code == 200
        assert 'other' not in listed()
    print('PASS: installed users pass the user check; a user under review is listed, refused sign-in and tokens, reset, edited and deleted')


def draft_review_checks(root):
    from contextlib import nullcontext
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import database_tools as api
    from backend.services.auth import get_current_user
    from backend.services.database_tools import DatabaseTools
    from backend.services.report_authoring import ReportDraft

    service = DatabaseTools(root / 'tools', Path(__file__).resolve().parents[2] / 'database_packages', guard=nullcontext)
    authoring = service.authoring
    def tool(name):
        source = f"TOOL = {{'name': {name!r}, 'kind': 'report', 'connections': []}}\ndef run(context, inputs):\n    pass\n"
        return authoring.import_files({'tool.py': source}, 'admin')['id']
    good, truncated, nameless, ownerless, retired, unnumbered = (tool(name)
        for name in ('Good', 'Truncated', 'Nameless', 'Ownerless', 'Retired field', 'Unnumbered'))
    path = authoring._path(truncated)
    path.write_bytes(path.read_bytes()[:40])
    kept = digest(path)
    # As the removed wizard saved it: the full draft model with no defining Python file.
    wizard = 'e' * 32
    wizard_path = authoring._path(wizard)
    wizard_path.write_text(json.dumps(dict(id=wizard, owner='admin', revision=2, draft=ReportDraft(
        name='Old wizard report', handler='def run(context, inputs):\n    pass\n', step=2).model_dump())), 'utf-8')
    wizard_kept = digest(wizard_path)
    for key, change in ((nameless, lambda r: r['draft'].update(name='')), (ownerless, lambda r: r.update(owner=None)),
                        (retired, lambda r: r['draft'].update(retired_field=1)), (unnumbered, lambda r: r.update(revision='two'))):
        record = json.loads(authoring._path(key).read_text('utf-8'))
        change(record)
        authoring._path(key).write_text(json.dumps(record), 'utf-8')
    locked = authoring.root / ('d' * 32 + '.json')
    locked.mkdir()  # reading a directory raises OSError, like a file another program holds
    app = FastAPI()
    app.include_router(api.router)
    user = {'username': 'admin', 'role': 'admin'}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[api.get_database_tools] = lambda: service
    with TestClient(app, client=('127.0.0.1', 1)) as client:
        reply = client.get('/api/database/tools/drafts')
        assert reply.status_code == 200, reply.text
        listed = {entry['id']: entry for entry in reply.json()}
        assert set(listed) == {good, truncated, nameless, ownerless, retired, unnumbered, wizard, locked.stem}, reply.text
        assert listed[wizard]['review_reason'] == 'This draft was made with the old report wizard, which has been removed', listed[wizard]
        assert not listed[wizard]['openable'] and listed[wizard]['name'] == 'Old wizard report', listed[wizard]
        assert listed[good]['review_reason'] is None and all(listed[key]['review_reason'] for key in (truncated, nameless, ownerless)), reply.text
        assert listed[locked.stem]['review_reason'] == 'The draft file cannot be opened; another program may be using it', listed[locked.stem]
        assert {key: listed[key]['review_reason'] for key in (truncated, nameless, ownerless, retired, unnumbered)} == {
            truncated: 'The draft file is damaged', nameless: 'The draft has no name', ownerless: 'The draft has no owner',
            retired: 'The draft has a setting this version no longer uses', unnumbered: 'The draft has no saved revision number'}, listed
        locked.rmdir()
        assert listed[nameless]['openable'] and not listed[truncated]['openable'] and not listed[ownerless]['openable'], reply.text
        # A key the model no longer has, or a revision that is not a number, still opens and saves.
        for key in (retired, unnumbered):
            opened = client.get(f'/api/database/tools/drafts/{key}').json()
            reply = client.put(f'/api/database/tools/drafts/{key}', json={'draft': opened['draft'], 'revision': opened['revision']})
            assert reply.status_code == 200, (key, reply.text)
            assert client.get(f'/api/database/tools/drafts/{key}').json()['review_reason'] is None
            assert client.delete(f'/api/database/tools/drafts/{key}').status_code == 200
        # Only its owner opens a draft under review; one without a readable owner offers Delete only.
        reply = client.get(f'/api/database/tools/drafts/{ownerless}')
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        assert client.get(f'/api/database/tools/drafts/{good}').status_code == 200
        # An old wizard draft offers Delete only; the code-defined draft beside it still opens.
        reply = client.get(f'/api/database/tools/drafts/{wizard}')
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        reply = client.put(f'/api/database/tools/drafts/{wizard}', json={'draft': {'name': 'Taken'}, 'revision': 2})
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        for key in (truncated, nameless, wizard):
            for method, suffix, body in (('post', '/try', {'inputs': {}}), ('post', '/check', None),
                                         ('post', '/install', {'expected_current': '', 'revision': 1})):
                reply = client.request(method.upper(), f'/api/database/tools/drafts/{key}{suffix}', json=body)
                assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], (suffix, reply.text)
        # A file that does not read as JSON offers Delete only; its bytes stay.
        reply = client.get(f'/api/database/tools/drafts/{truncated}')
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        reply = client.put(f'/api/database/tools/drafts/{truncated}', json={'draft': {'name': 'Repaired'}, 'revision': 1})
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        assert digest(path) == kept and digest(wizard_path) == wizard_kept
        # A readable draft under review opens in Edit; saving it through the check clears the review.
        reply = client.get(f'/api/database/tools/drafts/{nameless}')
        assert reply.status_code == 200 and reply.json()['review_reason'], reply.text
        opened = reply.json()
        # Its missing name is the refused field, so the save supplies the name its Python defines.
        reply = client.put(f'/api/database/tools/drafts/{nameless}', json={'draft': {**opened['draft'], 'name': 'Nameless'}, 'revision': opened['revision']})
        assert reply.status_code == 200, reply.text
        listed = {entry['id']: entry for entry in client.get('/api/database/tools/drafts').json()}
        assert listed[nameless]['review_reason'] is None and listed[nameless]['name'] == 'Nameless', listed[nameless]
        user['username'] = 'other'
        assert sorted(entry['id'] for entry in client.get('/api/database/tools/drafts').json()) == sorted([truncated, ownerless])
        reply = client.get(f'/api/database/tools/drafts/{ownerless}')
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        reply = client.put(f'/api/database/tools/drafts/{ownerless}', json={'draft': {'name': 'Taken'}, 'revision': 1})
        assert reply.status_code == 400 and 'Needs review' in reply.json()['detail'], reply.text
        assert client.delete(f'/api/database/tools/drafts/{ownerless}').status_code == 200
        user['username'] = 'admin'
        assert digest(wizard_path) == wizard_kept
        for key in (truncated, nameless, wizard):
            assert client.delete(f'/api/database/tools/drafts/{key}').status_code == 200
        assert [entry['id'] for entry in client.get('/api/database/tools/drafts').json()] == [good]
        assert not path.exists() and not wizard_path.exists()
    print('PASS: draft review entries listed beside a good draft; a readable one opens and its save clears it; try/check/install refused; unreadable and old wizard bytes kept; ownerless listed for all; deleted')


def run():
    with tempfile.TemporaryDirectory(prefix='rc-stored-data-') as folder:
        root = Path(folder)
        schedule_status_checks(root)
        runner_checks(root)
        schema_checks(root)
        review_checks(root)
        schedule_upgrade_checks(root)
        route_error_checks()
        existing_run_review_checks(root)
        contact_review_checks(root)
        email_settings_review_checks(root)
        user_review_checks(root)
        draft_review_checks(root)


if __name__ == '__main__':
    run()
