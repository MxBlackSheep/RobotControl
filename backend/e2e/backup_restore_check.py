"""Real SQL Server + HTTP restore from a `.bck` path, using an owned disposable database.

Run: .venv/Scripts/python.exe -m backend.e2e.backup_restore_check
Requires a local SQL Server administrator on LOCALHOST\\HAMILTON via Windows
authentication. Creates, restores and drops only its own rc_restore_check_* database.

Failure cases:
- The path restore never reaches SQL Server and every request reports
  "Database restore failed".
- A successful response while the database still holds the old rows.
- An open session on the target database blocks the restore instead of being disconnected.
- A missing file, a folder or a wrong extension touches the database instead of failing first.
- A file SQL Server cannot restore reports success, returns an empty message, changes
  the rows, or leaves the database in single-user mode.
- The path restore uses the backup timeout instead of RESTORE_TIMEOUT.
- The check touches EvoYeast or any database it did not create, or leaves its
  disposable database or backup files behind.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import traceback
import uuid

import pyodbc
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.backup as backup_api
from backend.services.auth import get_current_user
from backend.services.backup import BackupService, SqlCommandExecutor, RESTORE_TIMEOUT

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/backup-restore-verification'
SERVER = r'LOCALHOST\HAMILTON'
PREFIX = 'rc_restore_check_'
URL = '/api/admin/backup/restore'
pyodbc.pooling = False  # Pooled sessions would keep the disposable database open.


def connect(database='master'):
    return pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={database};'
                          'Trusted_Connection=yes;TrustServerCertificate=yes', timeout=5, autocommit=True)


@contextmanager
def sql_fixture(folder):
    """Disposable database plus a .bck of it in `folder`, readable by this user and SQL Server."""
    name = PREFIX + uuid.uuid4().hex[:12]
    assert name.replace('_', '').isalnum() and 'evoyeast' not in name.lower()
    good = Path(folder) / (name + '.bck')
    admin = connect()
    created = False
    try:
        admin.execute(f'CREATE DATABASE [{name}]'); created = True
        admin.execute(f"CREATE TABLE [{name}].dbo.Marker (v nvarchar(20)); INSERT [{name}].dbo.Marker VALUES (N'backed-up')")
        backup = admin.execute(f"BACKUP DATABASE [{name}] TO DISK = N'{good}' WITH INIT")
        while backup.nextset(): pass
        assert good.is_file(), f'SQL Server could not write {good}'
        yield dict(name=name, admin=admin, good=good)
    finally:
        admin.execute('USE master')
        if created:
            admin.execute(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            admin.execute(f'DROP DATABASE [{name}]')
            admin.execute('EXEC msdb.dbo.sp_delete_database_backuphistory ?', name)
        admin.close()


def state(admin, name):
    rows = [r[0] for r in admin.execute(f'SELECT v FROM [{name}].dbo.Marker').fetchall()]
    access = admin.execute('SELECT user_access_desc FROM sys.databases WHERE name=?', name).fetchval()
    return rows, access


def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'checks': [], 'command': '.venv/Scripts/python.exe -m backend.e2e.backup_restore_check'}
    name = None
    try:
        with tempfile.TemporaryDirectory(prefix='rc-restore-') as temporary, sql_fixture(temporary) as fx:
            name, admin = fx['name'], fx['admin']
            result['fixture'] = {'server': SERVER, 'database': name, 'backup_file': str(fx['good'])}

            service = BackupService()
            service.backup_dir, service.sql_server, service.database_name = temporary, SERVER, name
            service._sql_executor = SqlCommandExecutor(SERVER, name)
            calls, all_sql = [], []
            real_execute = service._sql_executor.execute
            def spy(sql, **kwargs):
                calls.append({'sql': sql, 'timeout': kwargs.get('timeout')}); all_sql.append(sql)
                return real_execute(sql, **kwargs)
            service._sql_executor.execute = spy
            # Pool recovery targets the configured application database; keep it out of this check.
            recovered = []
            service._recover_database_connections = lambda: recovered.append(True)
            backup_api.get_backup_service = lambda: service

            app = FastAPI(); app.include_router(backup_api.router, prefix='/api/admin/backup')
            app.dependency_overrides[get_current_user] = lambda: {'username': 'restore-check', 'role': 'admin'}
            with TestClient(app, client=('127.0.0.1', 1234)) as client:
                def restore(path):
                    response = client.post(URL, json={'file_path': str(path)})
                    assert response.status_code == 200, response.text
                    return response.json()

                admin.execute(f"UPDATE [{name}].dbo.Marker SET v=N'changed'")
                held = connect(name)
                body = restore(fx['good'])
                assert body['success'] and body['message'] == 'Database restored successfully', body
                assert state(admin, name) == (['backed-up'], 'MULTI_USER'), state(admin, name)
                try:
                    held.execute('SELECT 1').fetchall(); held_survived = True
                except pyodbc.Error:
                    held_survived = False
                held.close()
                assert not held_survived, 'Open session was not disconnected by the restore'
                assert recovered == [True]
                assert [c['timeout'] for c in calls] == [RESTORE_TIMEOUT], calls
                result['checks'].append('Valid .bck restores over changed rows with an open session; MULTI_USER afterwards; RESTORE_TIMEOUT used')

                admin.execute(f"UPDATE [{name}].dbo.Marker SET v=N'kept'")
                calls.clear()
                folder = Path(temporary) / 'folder.bck'; folder.mkdir()
                wrong = Path(temporary) / 'backup.txt'; wrong.write_bytes(b'x' * 2048)
                for bad in (Path(temporary) / 'missing.bck', folder, wrong):
                    body = restore(bad)
                    assert not body['success'] and body['message'] == 'Database restore failed' and body['data']['error_details'], body
                assert calls == [], calls
                assert state(admin, name) == (['kept'], 'MULTI_USER')
                result['checks'].append('Missing file, folder and .txt fail with a message before any SQL runs; rows unchanged')

                # Right extension and size, so the rejection has to come from SQL Server.
                garbage = fx['good'].with_name(name + '_garbage.bck')
                garbage.write_bytes(os.urandom(4096))
                body = restore(garbage)
                assert not body['success'] and body['message'] == 'Database restore failed', body
                assert 'SQL Server error' in body['data']['error_details'], body
                assert state(admin, name) == (['kept'], 'MULTI_USER'), state(admin, name)
                assert calls[0]['timeout'] == RESTORE_TIMEOUT and 'MULTI_USER' in calls[-1]['sql'], calls
                result['checks'].append('Unrestorable .bck fails with SQL Server error, rows unchanged, database back to MULTI_USER')
                result['garbage_error'] = body['data']['error_details'][:400]

            assert all_sql and 'evoyeast' not in ' '.join(all_sql).lower(), all_sql
        with connect() as check:
            names = [r[0] for r in check.execute('SELECT name FROM sys.databases WHERE name=?', name).fetchall()]
        assert names == [] and not Path(temporary).exists(), (names, temporary)
        result['checks'].append('Disposable database and backup files removed; no SQL referenced EvoYeast')
        result['passed'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (EVIDENCE / 'result.json').write_text(json.dumps(result, indent=2), 'utf-8')
    print(json.dumps(result, indent=2))
    return result['passed']


if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
