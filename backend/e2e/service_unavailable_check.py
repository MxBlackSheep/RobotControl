"""Service-unavailable answers over HTTP for the latest experiment and backup health.

Run: .venv/Scripts/python.exe -m backend.e2e.service_unavailable_check
Needs no SQL Server: the HamiltonVectorDB query is replaced, the backup service is real and
pointed at a temporary folder. Evidence is written to
test-output/service-unavailable-verification/results.json.

Failure cases: a failing HamiltonVectorDB query answers 500 "Experiment data unavailable"
instead of 503 "Database unavailable" with the reason; an unwritable backup folder answers
500 with a Python AttributeError instead of 503 carrying the health report (path, flags,
count); the 503 body loses the standard shape (success false, message, error.code,
metadata); a found experiment or a healthy backup folder stops answering 200; other error
helpers stop sending data: null.
"""
import json
import shutil
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import backup as backup_api
from backend.api import experiments as experiments_api
from backend.api.response_formatter import ResponseFormatter
from backend.services import backup as backup_module
from backend.services.auth import get_current_admin_user, get_current_user

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/service-unavailable-verification'


class FakeVectorDb:
    def __init__(self, answer):
        self.answer = answer

    def execute_query(self, query):
        return self.answer


def run():
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    admin = {'username': 'unavailable-check', 'role': 'admin', 'user_id': 'unavailable-check'}
    app = FastAPI()
    app.include_router(backup_api.router, prefix='/api/admin/backup')
    app.include_router(experiments_api.router)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_admin_user] = lambda: admin

    folder = Path(tempfile.mkdtemp(prefix='rc-unavailable-'))
    service = backup_module.BackupService()
    try:
        with TestClient(app, client=('127.0.0.1', 1234)) as client:
            down = FakeVectorDb({'error': 'Login timeout expired'})
            with patch.object(experiments_api, 'get_database_service', return_value=down):
                response = client.get('/api/experiments/latest')
            body = response.json()
            check('failing experiment query answers 503', response.status_code == 503, body)
            check('experiment 503 names the database and the reason',
                  body.get('message') == 'Database unavailable'
                  and body.get('error', {}).get('details') == 'Login timeout expired', body)
            check('experiment 503 keeps the standard error shape',
                  body.get('success') is False and body.get('data') is None
                  and body.get('error', {}).get('code') == 'SERVICE_UNAVAILABLE', body)

            row = {'RunGUID': 'g-1', 'MethodName': 'Fixture', 'StartTime': '2026-09-30T08:00:00',
                   'EndTime': None, 'RunState': 'Running'}
            with patch.object(experiments_api, 'get_database_service', return_value=FakeVectorDb({'rows': [row]})):
                response = client.get('/api/experiments/latest')
            check('found experiment still answers 200',
                  response.status_code == 200 and response.json()['data']['method_name'] == 'Fixture',
                  response.json())

            service.backup_dir = str(folder)
            with patch.object(backup_api, 'get_backup_service', return_value=service):
                response = client.get('/api/admin/backup/health')
                check('writable backup folder answers 200',
                      response.status_code == 200 and response.json()['data']['backup_directory']['writable'],
                      response.json())

                missing = folder / 'missing'
                service.backup_dir = str(missing)
                response = client.get('/api/admin/backup/health')
            body = response.json()
            check('missing backup folder answers 503', response.status_code == 503, body)
            report = body.get('data') or {}
            check('backup 503 carries the health report',
                  report.get('backup_directory') == {'path': str(missing), 'exists': False, 'writable': False}
                  and report.get('backup_count') == 0, body)
            check('backup 503 keeps the standard error shape with metadata',
                  body.get('success') is False and body.get('error', {}).get('code') == 'SERVICE_UNAVAILABLE'
                  and body.get('metadata', {}).get('is_healthy') is False
                  and 'AttributeError' not in json.dumps(body), body)

        other = json.loads(ResponseFormatter.bad_request('Fixture').body)
        check('other error helpers still send data: null', other.get('data') is None and 'data' in other, other)
    except Exception:
        check('check ran to completion', False, traceback.format_exc())
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    result = {'passed': all(c['passed'] for c in checks), 'checks': checks}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'results.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    for c in checks:
        print(('PASS ' if c['passed'] else 'FAIL ') + c['check'])
    return result['passed']


if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
