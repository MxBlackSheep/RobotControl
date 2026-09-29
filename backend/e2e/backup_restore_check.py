"""Back up, change, restore and reject bad files over HTTP against a disposable SQL Server database.

Run: .venv/Scripts/python.exe -m backend.e2e.backup_restore_check
Needs sqlcmd and the local SQL Server instance (LOCALHOST\\HAMILTON). Creates a database named
RC_BackupCheck_<id>; EvoYeast is never backed up, restored or changed. Evidence is written to
test-output/backup-restore-verification/results.json.

Failure cases: with default settings the backup folder is <app root>/data/backups, not relative
to the working directory. SQL Server writes the .bak to the same path RobotControl then checks
and lists with its description. Restore returns a row changed after the backup to its
backup-time value, and sqlcmd gets RESTORE_TIMEOUT (600 s), not the 300 s backup default. A file
SQL Server rejects reports failure and leaves the database MULTI_USER. Both restore
formats must work when the restoring connection starts inside the target database.
A command timeout must attempt MULTI_USER recovery; failed recovery must warn.
Restore from a `.bck` path (file_path) never reaches SQL Server; reports success while the old
rows remain; is blocked by an open session instead of disconnecting it; uses the backup timeout;
or returns an empty message. A missing file, a folder or a wrong extension runs SQL instead of
failing first. An unrestorable `.bck` changes rows, hides SQL Server's error or leaves the
database single-user. The disposable database and its backup files are removed afterwards,
also when a step fails.
Unavailable SQL authentication or cleanup errors must still produce the evidence report;
the held connection must close even when the restore request or an assertion query fails.
"""
import json
import os
import shutil
import subprocess
import tempfile
import traceback
import uuid
from pathlib import Path
from unittest.mock import patch

import pyodbc
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import backup as backup_api
from backend.services import backup as backup_module
from backend.services.auth import get_current_admin_user, get_current_user
from backend.utils.odbc_driver import build_connection_string, resolve_driver_clause

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/backup-restore-verification'
pyodbc.pooling = False  # A pooled session would survive the restore's disconnect unnoticed.


def sql(server, query):
    result = subprocess.run(['sqlcmd', '-S', server, '-E', '-b', '-h', '-1', '-W', '-Q', f'SET NOCOUNT ON; {query}'],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def session_alive(connection):
    try:
        connection.execute('SELECT 1').fetchall()
        return True
    except pyodbc.Error:
        return False


def run():
    server = backup_module.SQL_SERVER
    database = f'RC_BackupCheck_{uuid.uuid4().hex[:8]}'
    checks, commands, created = [], [], []
    held = None

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    def restore_timeouts():
        return [timeout for command, timeout in commands if 'RESTORE DATABASE' in command]

    def value():
        return sql(server, f'SELECT Value FROM [{database}].dbo.Sample')

    def access():
        return sql(server, f"SELECT user_access_desc FROM sys.databases WHERE name = N'{database}'")

    service = backup_module.BackupService()
    service.database_name = database
    service._sql_executor = backup_module.SqlCommandExecutor(server, database)
    execute = service._sql_executor.execute
    def recording_execute(command, *, timeout=backup_module.BACKUP_TIMEOUT):
        commands.append((command, timeout))
        # Reproduce a login whose default database is the restore target, without
        # changing any real login's settings.
        if 'RESTORE DATABASE' in command:
            command = f"USE [{database}];\n" + command
        return execute(command, timeout=timeout)
    service._sql_executor.execute = recording_execute

    app = FastAPI()
    app.include_router(backup_api.router, prefix='/api/admin/backup')
    admin = {'username': 'backup-check', 'role': 'admin'}
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_admin_user] = lambda: admin

    try:
        if 'LOCAL_BACKUP_PATH' not in os.environ:
            check('default folder is <app root>/data/backups',
                  Path(service.backup_dir) == (ROOT / 'data/backups').resolve(), service.backup_dir)

        sql(server, f'CREATE DATABASE [{database}]')
        sql(server, f'CREATE TABLE [{database}].dbo.Sample (Value nvarchar(20)); '
                    f"INSERT [{database}].dbo.Sample VALUES (N'before backup')")

        with patch.object(backup_api, 'get_backup_service', return_value=service), \
                TestClient(app, client=('127.0.0.1', 1234)) as client:
            response = client.post('/api/admin/backup/create', json={'description': 'backup check'})
            body = response.json()
            filename = (body.get('data') or {}).get('filename')
            check('backup succeeds', response.status_code == 200 and body.get('success') and filename, body)
            if filename:
                created.append(filename)
            bak = Path(service.backup_dir) / (filename or '')
            check('SQL Server wrote the .bak into the backup folder', filename and bak.is_file() and bak.stat().st_size > 0, str(bak))

            listed = client.get('/api/admin/backup/list').json()
            entry = next((b for b in (listed.get('data') or []) if b.get('filename') == filename), None)
            check('backup is listed with its description', entry and entry.get('description') == 'backup check', entry)

            sql(server, f"UPDATE [{database}].dbo.Sample SET Value = N'after backup'")
            response = client.post('/api/admin/backup/restore', json={'filename': filename})
            check('restore succeeds', response.status_code == 200 and response.json().get('success'), response.json())
            check('restore reverts the change made after the backup', value() == 'before backup', value())
            check('restore uses RESTORE_TIMEOUT (600 s)', restore_timeouts() == [600], restore_timeouts())

            bad = f'{database}_not_a_backup.bak'
            (Path(service.backup_dir) / bad).write_bytes(b'not a SQL Server backup' * 100)
            created.append(bad)
            response = client.post('/api/admin/backup/restore', json={'filename': bad})
            check('bad file restore reports failure', response.status_code != 200 or not response.json().get('success'),
                  {'status': response.status_code, 'body': response.json()})
            check('database stays MULTI_USER after a rejected restore', access() == 'MULTI_USER', access())
            check('data unchanged after a rejected restore', value() == 'before backup')

            # Restore from a path: a .bck outside the managed listing, in a folder SQL Server can read.
            bck = f'{database}_manual.bck'
            shutil.copyfile(bak, Path(service.backup_dir) / bck)
            created.append(bck)
            sql(server, f"UPDATE [{database}].dbo.Sample SET Value = N'after backup'")
            held = pyodbc.connect(build_connection_string({
                'driver': resolve_driver_clause(), 'server': server, 'database': database,
                'trusted_connection': 'yes', 'trust_server_certificate': 'yes'}), timeout=5, autocommit=True)
            commands.clear()
            response = client.post('/api/admin/backup/restore', json={'file_path': str(Path(service.backup_dir) / bck)})
            body = response.json()
            check('.bck path restore succeeds with a message',
                  response.status_code == 200 and body.get('success') and body.get('message') == 'Database restored successfully', body)
            check('.bck path restore reverts the change made after the backup', value() == 'before backup', value())
            check('.bck path restore uses RESTORE_TIMEOUT (600 s)', restore_timeouts() == [600], restore_timeouts())
            check('.bck path restore disconnects an open session', not session_alive(held))
            held.close()
            held = None
            check('database is MULTI_USER after the .bck path restore', access() == 'MULTI_USER', access())

            sql(server, f"UPDATE [{database}].dbo.Sample SET Value = N'kept'")
            with tempfile.TemporaryDirectory(prefix='rc-restore-') as scratch:
                folder = Path(scratch) / 'folder.bck'
                folder.mkdir()
                wrong = Path(scratch) / 'backup.txt'
                wrong.write_bytes(b'x' * 2048)
                commands.clear()
                bodies = [client.post('/api/admin/backup/restore', json={'file_path': str(path)}).json()
                          for path in (Path(scratch) / 'missing.bck', folder, wrong)]
            check('missing file, folder and .txt fail with a message before any SQL runs',
                  not commands and all(not b.get('success') and b.get('message') == 'Database restore failed'
                                       and (b.get('data') or {}).get('error_details') for b in bodies),
                  {'bodies': bodies, 'sql': list(commands)})
            check('data unchanged after rejected paths', value() == 'kept', value())

            # Right extension and size, so the rejection has to come from SQL Server.
            garbage = f'{database}_garbage.bck'
            (Path(service.backup_dir) / garbage).write_bytes(os.urandom(4096))
            created.append(garbage)
            commands.clear()
            body = client.post('/api/admin/backup/restore', json={'file_path': str(Path(service.backup_dir) / garbage)}).json()
            check('unrestorable .bck reports the SQL Server error',
                  not body.get('success') and body.get('message') == 'Database restore failed'
                  and 'SQL Server error' in ((body.get('data') or {}).get('error_details') or ''), body)
            check('unrestorable .bck leaves data unchanged and the database MULTI_USER',
                  value() == 'kept' and access() == 'MULTI_USER', {'value': value(), 'access': access()})
            # Inject runner timeouts at the HTTP boundary, then confirm recovery is
            # attempted and a failed recovery is retained in the API warning list.
            for payload in ({'filename': filename}, {'file_path': str(Path(service.backup_dir) / bck)}):
                commands.clear()
                with patch.object(backup_module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('sqlcmd', 600)):
                    body = client.post('/api/admin/backup/restore', json=payload).json()
                check('runner timeout fails restore and warns about failed MULTI_USER recovery',
                      not body.get('success') and len(commands) == 2
                      and 'timed out' in body['data']['error_details']
                      and any('single-user' in w for w in body['data']['warnings']), body)
    except Exception:
        check('check ran without errors', False, traceback.format_exc())
    finally:
        if held is not None:
            try:
                held.close()
            except Exception:
                check('held connection closed', False, traceback.format_exc())
        try:
            sql(server, f"IF DB_ID(N'{database}') IS NOT NULL BEGIN "
                        f'ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}] END')
        except Exception:
            check('disposable database dropped', False, traceback.format_exc())
        for name in created:
            for path in (Path(service.backup_dir) / name, Path(service.backup_dir) / name.replace('.bak', '.json')):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    check('disposable backup file removed', False, traceback.format_exc())
        try:
            check('disposable database and backup files removed',
                  not sql(server, f"SELECT name FROM sys.databases WHERE name = N'{database}'")
                  and not any((Path(service.backup_dir) / name).exists() for name in created))
        except Exception:
            check('disposable cleanup verified', False, traceback.format_exc())

    result = {'command': '.venv/Scripts/python.exe -m backend.e2e.backup_restore_check',
              'commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
              'working_tree': subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
              'server': server, 'database': database, 'backup_dir': service.backup_dir,
              'passed': all(c['passed'] for c in checks), 'checks': checks}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'results.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    run()
