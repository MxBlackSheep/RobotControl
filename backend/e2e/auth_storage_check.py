"""Sign-in over HTTP: storage outages must not sign anyone out; the public default password stays local.

Run: .venv/Scripts/python.exe -m backend.e2e.auth_storage_check
Needs no SQL Server: the real AuthService runs against a disposable SQLite file, and a second
connection holds an exclusive lock on it for longer than the 2 s connect timeout. Evidence is
written to test-output/auth-storage-verification/results.json.

Failure cases: a locked auth database makes /api/auth/me, a protected route or
/api/auth/refresh answer 401 (the browser then deletes the saved sign-in) instead of 503; the
refresh token is revoked during the outage, so /me and refresh fail after the lock is released;
a genuinely bad, expired, wrong-type or revoked token stops answering 401; a sign-in relayed by
a tunnel on this computer (loopback peer with forwarding headers) is reported as local; remote
password guessing is unlimited (including through the tunnel with a spoofed first
X-Forwarded-For entry), remote guessing locks the RobotControl computer out, or an auth storage
outage counts as wrong passwords.

Built-in admin password (public in the repository): a remote sign-in with it (tunnel, spoofed
first X-Forwarded-For, LAN peer) gets tokens or records a last login instead of 403 "Change the
default password on the robot PC before signing in remotely."; refused attempts count toward the
remote throttle; a local sign-in with it is refused or does not ask for a password change
(must_reset); after the change, the new password is refused remotely or the old one is not
refused like any wrong password; a wrong password's answer differs depending on whether the
default is still in use (account oracle).
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
from backend.services.auth import (  # noqa: E402
    BUILT_IN_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    get_auth_service,
    get_current_user,
)

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
            tokens = service.login(DEFAULT_ADMIN_USERNAME, BUILT_IN_ADMIN_PASSWORD)
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

            # The built-in password is public: refused from outside this computer until changed.
            built_in = {'username': DEFAULT_ADMIN_USERNAME, 'password': BUILT_IN_ADMIN_PASSWORD}
            wrong = {'username': DEFAULT_ADMIN_USERNAME, 'password': 'not-the-password'}
            tunnel = {'x-forwarded-for': '127.0.0.1, 203.0.113.5', 'cf-connecting-ip': '203.0.113.5'}
            refusal = 'Change the default password on the robot PC before signing in remotely.'

            def last_login():
                return service.db.get_user_by_username(DEFAULT_ADMIN_USERNAME)['last_login_at']

            def answer(response):
                body = response.json()
                return [response.status_code, body.get('message'), body.get('error')]

            auth_api.login_throttle._failures.clear()
            login_before = last_login()
            refused = [client.post('/api/auth/login', json=built_in, headers=tunnel) for _ in range(6)]
            check('six tunnelled sign-ins with the built-in password answer 403 with the change message, never 429',
                  all(r.status_code == 403 and r.json()['error']['message'] == refusal for r in refused),
                  [answer(r) for r in refused])
            check('a refused sign-in issues no tokens and records no last login',
                  not any('access_token' in r.text or 'refresh_token' in r.text for r in refused)
                  and last_login() == login_before, [login_before, last_login()])
            with TestClient(app, client=('192.168.1.20', 1234)) as lan:
                response = lan.post('/api/auth/login', json=built_in)
                check('a LAN sign-in with the built-in password answers 403', response.status_code == 403, answer(response))
            wrong_while_default = client.post('/api/auth/login', json=wrong, headers=tunnel)
            check('a wrong tunnelled password still answers the generic 401', answer(wrong_while_default) ==
                  [401, 'Invalid username or password', {'message': 'Invalid username or password', 'code': 'UNAUTHORIZED',
                                                         'details': {'username': DEFAULT_ADMIN_USERNAME}}],
                  answer(wrong_while_default))

            local = client.post('/api/auth/login', json=built_in)
            local_user = local.json().get('data', {}).get('user', {}) if local.status_code == 200 else {}
            check('a local sign-in with the built-in password works and asks for a change (must_reset)',
                  local.status_code == 200 and local_user.get('must_reset') is True, [local.status_code, local_user])
            changed = 'Lab-owned password 7'
            response = client.post('/api/auth/change-password',
                                   json={'current_password': BUILT_IN_ADMIN_PASSWORD, 'new_password': changed},
                                   headers={'Authorization': f"Bearer {local.json()['data']['access_token']}"})
            check('the local session changes the password', response.status_code == 200, [response.status_code, response.text])

            credentials = {'username': DEFAULT_ADMIN_USERNAME, 'password': changed}
            response = client.post('/api/auth/login', json=credentials, headers=tunnel)
            remote_user = response.json().get('data', {}).get('user', {}) if response.status_code == 200 else {}
            check('after the change, a tunnelled sign-in with the new password works without must_reset',
                  response.status_code == 200 and remote_user.get('must_reset') is False, [response.status_code, remote_user])
            old = client.post('/api/auth/login', json=built_in, headers=tunnel)
            wrong_after_change = client.post('/api/auth/login', json=wrong, headers=tunnel)
            check('after the change, the built-in password is a plain wrong password (401), remote and local',
                  answer(old) == answer(wrong_while_default)
                  and client.post('/api/auth/login', json=built_in).status_code == 401, answer(old))
            check('a wrong password answers the same whether or not the default was in use (no oracle)',
                  answer(wrong_after_change) == answer(wrong_while_default), [answer(wrong_while_default), answer(wrong_after_change)])

            for name, headers, local in [
                ('plain loopback sign-in is local', {}, True),
                ('tunnelled sign-in with spoofed first X-Forwarded-For is remote',
                 {'x-forwarded-for': '127.0.0.1, 203.0.113.9', 'cf-connecting-ip': '203.0.113.9'}, False),
            ]:
                response = client.post('/api/auth/login', json=credentials, headers=headers)
                session = response.json().get('data', {}).get('session', {}) if response.status_code == 200 else {}
                check(name, session.get('is_local') is local, [response.status_code, session])

            # Remote password guessing is limited; the RobotControl computer is never locked out.
            # The guesses come the way an attacker would: through the tunnel (loopback peer), with
            # a spoofed first X-Forwarded-For entry that the classifier must not trust.
            auth_api.login_throttle._failures.clear()
            remote = {'x-forwarded-for': '127.0.0.1, 203.0.113.7', 'cf-connecting-ip': '203.0.113.7'}
            answers = [client.post('/api/auth/login', json=wrong, headers=remote).status_code for _ in range(5)]
            check('five wrong tunnelled passwords (spoofed 127.0.0.1 first) answer 401', answers == [401] * 5, answers)
            blocked = client.post('/api/auth/login', json=credentials, headers=remote)
            check('sixth tunnelled attempt answers 429 with Retry-After, even with the right password',
                  blocked.status_code == 429 and int(blocked.headers.get('retry-after', 0)) > 0
                  and 'Too many failed sign-in attempts' in blocked.text, [blocked.status_code, dict(blocked.headers), blocked.text])
            local = client.post('/api/auth/login', json=credentials)
            check('local sign-in still works while the remote account is throttled', local.status_code == 200, [local.status_code, local.text])
            other = client.post('/api/auth/login', json=wrong, headers={'cf-connecting-ip': '198.51.100.4'})
            check('the account stays throttled from another remote address', other.status_code == 429, [other.status_code])
            auth_api.login_throttle._failures.clear()
            outage_lock = sqlite3.connect(os.environ['ROBOTCONTROL_AUTH_DB_FILENAME'])
            outage_lock.execute('BEGIN EXCLUSIVE')
            outage = [client.post('/api/auth/login', json=wrong, headers=remote).status_code for _ in range(6)]
            outage_lock.rollback()
            outage_lock.close()
            check('auth storage outages are not counted as wrong passwords', 429 not in outage, outage)
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
