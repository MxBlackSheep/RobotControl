"""Sign-in storage outages over HTTP: a locked auth database must not sign anyone out.

Run: .venv/Scripts/python.exe -m backend.e2e.auth_storage_check
Needs no SQL Server: the real AuthService runs against a disposable SQLite file, and a second
connection holds an exclusive lock on it for longer than the 2 s connect timeout. Evidence is
written to test-output/auth-storage-verification/results.json.

Failure cases: a locked auth database makes /api/auth/me, a protected route or
/api/auth/refresh answer 401 (the browser then deletes the saved sign-in) instead of 503; the
refresh token is revoked during the outage, so /me and refresh fail after the lock is released;
a genuinely bad, expired, wrong-type or revoked token stops answering 401; a sign-in relayed by
a tunnel on this computer (loopback peer with forwarding headers) is reported as local.
"""
import json
import os
import shutil
import sqlite3
import tempfile
import traceback
from datetime import timedelta
from pathlib import Path

FOLDER = Path(tempfile.mkdtemp(prefix='rc-auth-storage-'))
os.environ['ROBOTCONTROL_AUTH_DB_FILENAME'] = str(FOLDER / 'auth.db')

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api import auth as auth_api  # noqa: E402
from backend.services.auth import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, get_auth_service, get_current_user  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/auth-storage-verification'


def run():
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    app = FastAPI()
    app.include_router(auth_api.router)

    @app.get('/protected')
    def protected(user=Depends(get_current_user)):
        return user

    service = get_auth_service()
    lock = None
    try:
        with TestClient(app, client=('127.0.0.1', 1234)) as client:
            tokens = service.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
            access, refresh = tokens['access_token'], tokens['refresh_token']
            bearer = {'Authorization': f'Bearer {access}'}

            lock = sqlite3.connect(os.environ['ROBOTCONTROL_AUTH_DB_FILENAME'])
            lock.execute('BEGIN EXCLUSIVE')
            me = client.get('/api/auth/me', headers=bearer)
            probe = client.get('/protected', headers=bearer)
            renewed = client.post('/api/auth/refresh', json={'refresh_token': refresh})
            lock.rollback()
            lock.close()
            lock = None

            check('locked storage: /me answers 503', me.status_code == 503, [me.status_code, me.text])
            check('locked storage: protected route answers 503', probe.status_code == 503, [probe.status_code, probe.text])
            check('locked storage: refresh answers 503', renewed.status_code == 503, [renewed.status_code, renewed.text])

            me = client.get('/api/auth/me', headers=bearer)
            check('after the lock: /me answers 200', me.status_code == 200, [me.status_code, me.text])
            renewed = client.post('/api/auth/refresh', json={'refresh_token': refresh})
            check('after the lock: refresh answers 200', renewed.status_code == 200, [renewed.status_code, renewed.text])

            user = service.get_user_by_id(tokens['user']['user_id'])
            expired = service.create_access_token(user, expires_delta=timedelta(seconds=-5))
            for name, token in [('garbage', 'not-a-token'), ('expired', expired), ('refresh used as access', refresh)]:
                response = client.get('/protected', headers={'Authorization': f'Bearer {token}'})
                check(f'{name} token answers 401', response.status_code == 401, [response.status_code, response.text])
                response = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
                check(f'{name} token on /me answers 401', response.status_code == 401, [response.status_code, response.text])

            response = client.post('/api/auth/refresh', json={'refresh_token': access})
            check('access token used as refresh answers 401', response.status_code == 401, [response.status_code, response.text])
            service.revoke_refresh_token(refresh)
            response = client.post('/api/auth/refresh', json={'refresh_token': refresh})
            check('revoked refresh token answers 401', response.status_code == 401, [response.status_code, response.text])

            credentials = {'username': DEFAULT_ADMIN_USERNAME, 'password': DEFAULT_ADMIN_PASSWORD}
            for name, headers, local in [
                ('plain loopback sign-in is local', {}, True),
                ('tunnelled sign-in with spoofed first X-Forwarded-For is remote',
                 {'x-forwarded-for': '127.0.0.1, 203.0.113.9', 'cf-connecting-ip': '203.0.113.9'}, False),
            ]:
                response = client.post('/api/auth/login', json=credentials, headers=headers)
                session = response.json().get('data', {}).get('session', {}) if response.status_code == 200 else {}
                check(name, session.get('is_local') is local, [response.status_code, session])
    except Exception:
        check('check ran to completion', False, traceback.format_exc())
    finally:
        if lock is not None:
            lock.close()

    result = {'passed': all(c['passed'] for c in checks), 'checks': checks}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'results.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    for c in checks:
        print(('PASS ' if c['passed'] else 'FAIL ') + c['check'])
    return result['passed']


if __name__ == '__main__':
    try:
        passed = run()
    finally:
        shutil.rmtree(FOLDER, ignore_errors=True)
    raise SystemExit(0 if passed else 1)
