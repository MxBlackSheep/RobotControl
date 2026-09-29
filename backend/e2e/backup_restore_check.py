"""Back up, change, restore and reject a bad file over HTTP against a disposable SQL Server database.

Run: .venv/Scripts/python.exe -m backend.e2e.backup_restore_check
Needs sqlcmd and the local SQL Server instance (LOCALHOST\\HAMILTON). Creates a database named
RC_BackupCheck_<id>; EvoYeast is never backed up, restored or changed. Evidence is written to
test-output/backup-restore-verification/results.json.

Failure cases: with default settings the backup folder is <app root>/data/backups, not relative
to the working directory. SQL Server writes the .bak to the same path RobotControl then checks
and lists with its description. Restore returns a row changed after the backup to its
backup-time value, and sqlcmd gets RESTORE_TIMEOUT (600 s), not the 300 s backup default. A file
SQL Server rejects reports failure and leaves the database MULTI_USER. The disposable database and
its backup files are removed afterwards, also when a step fails.
"""
import json
import os
import subprocess
import traceback
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import backup as backup_api
from backend.services import backup as backup_module
from backend.services.auth import get_current_admin_user, get_current_user

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/backup-restore-verification'


def sql(server, query):
    result = subprocess.run(['sqlcmd', '-S', server, '-E', '-b', '-h', '-1', '-W', '-Q', f'SET NOCOUNT ON; {query}'],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def run():
    server = backup_module.SQL_SERVER
    database = f'RC_BackupCheck_{uuid.uuid4().hex[:8]}'
    checks, timeouts, created = [], [], []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    service = backup_module.BackupService()
    service.database_name = database
    service._sql_executor = backup_module.SqlCommandExecutor(server, database)
    execute = service._sql_executor.execute
    def recording_execute(command, *, timeout=backup_module.BACKUP_TIMEOUT):
        if 'RESTORE DATABASE' in command:
            timeouts.append(timeout)
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
            value = sql(server, f'SELECT Value FROM [{database}].dbo.Sample')
            check('restore succeeds', response.status_code == 200 and response.json().get('success'), response.json())
            check('restore reverts the change made after the backup', value == 'before backup', value)
            check('restore uses RESTORE_TIMEOUT (600 s)', timeouts == [600], timeouts)

            bad = f'{database}_not_a_backup.bak'
            (Path(service.backup_dir) / bad).write_bytes(b'not a SQL Server backup' * 100)
            created.append(bad)
            response = client.post('/api/admin/backup/restore', json={'filename': bad})
            access = sql(server, f"SELECT user_access_desc FROM sys.databases WHERE name = N'{database}'")
            check('bad file restore reports failure', response.status_code != 200 or not response.json().get('success'),
                  {'status': response.status_code, 'body': response.json()})
            check('database stays MULTI_USER after a rejected restore', access == 'MULTI_USER', access)
            check('data unchanged after a rejected restore',
                  sql(server, f'SELECT Value FROM [{database}].dbo.Sample') == 'before backup')
    except Exception:
        check('check ran without errors', False, traceback.format_exc())
    finally:
        try:
            sql(server, f"IF DB_ID(N'{database}') IS NOT NULL BEGIN "
                        f'ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}] END')
        except Exception:
            check('disposable database dropped', False, traceback.format_exc())
        for name in created:
            for path in (Path(service.backup_dir) / name, Path(service.backup_dir) / name.replace('.bak', '.json')):
                path.unlink(missing_ok=True)
        check('disposable database and backup files removed',
              not sql(server, f"SELECT name FROM sys.databases WHERE name = N'{database}'")
              and not any((Path(service.backup_dir) / name).exists() for name in created))

    result = {'command': '.venv/Scripts/python.exe -m backend.e2e.backup_restore_check',
              'commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
              'server': server, 'database': database, 'backup_dir': service.backup_dir,
              'passed': all(c['passed'] for c in checks), 'checks': checks}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'results.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    run()
