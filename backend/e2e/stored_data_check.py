"""Offline stored-data checks, using disposable SQLite and JSON files only.

Run: .venv/Scripts/python.exe -m backend.e2e.stored_data_check
Failure cases: a raised upgrade commits partial data/version, destroys its backup,
repeats a completed step, or writes a newer store; fresh and installed-copy schemas
diverge; a failed scheduling upgrade prevents construction or permits storage access.
Installed files are copied and hashed, never opened for writing. No robot launch.
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
                assert conn.execute('SELECT MAX(version) FROM SchemaMigrations').fetchone()[0] == 2
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
            conn.execute('DELETE FROM SchemaMigrations WHERE version=2')
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


def run():
    with tempfile.TemporaryDirectory(prefix='rc-stored-data-') as folder:
        root = Path(folder)
        runner_checks(root)
        schema_checks(root)


if __name__ == '__main__':
    run()
