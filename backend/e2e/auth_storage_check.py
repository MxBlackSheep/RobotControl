"""Sign-in over HTTP: storage outages must not sign anyone out; the public default password stays local.

Run: .venv/Scripts/python.exe -m backend.e2e.auth_storage_check
Needs no SQL Server: the real AuthService runs against a disposable SQLite file, and a second
connection holds an exclusive lock on it for longer than the 2 s connect timeout. Evidence is
written to test-output/auth-storage-verification/results.json.

Failure cases: a locked auth database makes /api/auth/me, a protected route or
/api/auth/refresh answer 401 (the browser then deletes the saved sign-in) instead of 503; the
refresh token is revoked during the outage, so /me and refresh fail after the lock is released;
a genuinely bad, expired, wrong-type or revoked token stops answering 401; a sign-in relayed by
a tunnel on this computer (loopback peer with forwarding headers) is reported as local by login
or /api/auth/me, or /api/auth/me stops reporting a plain loopback session as local; remote
password guessing is unlimited (including through the tunnel with a spoofed first
X-Forwarded-For entry), remote guessing locks the RobotControl computer out, or an auth storage
outage counts as wrong passwords.

Cookies and the request header (programs sign in like the page: the header on login, the token
from the rc_access Set-Cookie, then Bearer): a sign-in reply carries a token in its body; a
cookie lacks HttpOnly or SameSite=Strict, has the wrong Path or lifetime, carries Secure on
plain http (the lab PC could not sign in) or lacks it through the tunnel (x-forwarded-proto:
https); a cookie-only unsafe request without X-Requested-With: RobotControl is accepted, or a
Bearer program or a request with the header is refused; refresh does not renew rc_access from
rc_refresh, a rejected refresh keeps the cookies, or an outage (503) clears them; logout
leaves the refresh token valid or the cookies set; /me drops a stored must_reset.

Folder list (/api/system/browse, used only by the restore picker): a remote plain user lists
the RobotControl PC's folders; a local user or a remote admin (who may restore) is refused.

Role change and delete (PUT /api/admin/users/{name}/role, DELETE /api/admin/users/{name}): a plain
user changes a role; an admin changes their own role or deletes their own account; an unknown
user is not 404; a promoted user's existing sign-in must sign in again before admin routes work,
or a demoted admin's still passes them; a caller who is not an admin (a plain user, or an
admin demoted earlier whose page stayed open) changes a role or deletes, or is told anything
but 403 "You are no longer an admin. Reload the page" on these two routes while other admin
routes keep "Admin access required"; a change or refusal is missing from the audit log.
Not reached here: two admins acting at the same instant, both past the admin check. The UPDATE
and DELETE in AuthDatabase then refuse the second change in SQL (maker still an active admin).

Signing keys: a token signed with the old published key is accepted; the key file is missing
after first start, holds a published text, or is regenerated on restart (signing everyone out);
an unreadable key file is rewritten instead of stopping start-up; a crash while the first file is
written leaves a file that stops the next start; the key variables do not win. An empty Bearer
header falls back to the cookie (and so skips the request-header rule).

Built-in admin password (public in the repository): a remote sign-in with it (tunnel, spoofed
first X-Forwarded-For, LAN peer) gets tokens or records a last login instead of 403 "Change the
default password on the robot PC before signing in remotely."; refused attempts count toward the
remote throttle; a local sign-in with it is refused or does not ask for a password change
(must_reset); after the change, the new password is refused remotely or the old one is not
refused like any wrong password; a wrong password's answer differs depending on whether the
default is still in use (account oracle).
"""
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import traceback
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path

FOLDER = Path(tempfile.mkdtemp(prefix='rc-auth-storage-'))
os.environ['ROBOTCONTROL_AUTH_DB_FILENAME'] = str(FOLDER / 'auth.db')
# No key variables: the check proves the per-installation key file (in the disposable folder).
for name in ('ROBOTCONTROL_ACCESS_TOKEN_SECRET', 'ROBOTCONTROL_REFRESH_TOKEN_SECRET'):
    os.environ.pop(name, None)

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import jwt  # noqa: E402

from backend.api import auth as auth_api  # noqa: E402
from backend.api import system as system_api  # noqa: E402
from backend.api import admin as admin_api  # noqa: E402
from backend.services import auth as auth_module  # noqa: E402
from backend.utils.data_paths import get_path_manager  # noqa: E402
from backend.services.auth import (  # noqa: E402
    BUILT_IN_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    get_auth_service,
    get_current_user,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/auth-storage-verification'
get_path_manager().config_path = FOLDER / 'config'
KEY_FILE = FOLDER / 'config' / 'token-secrets.json'
# The texts that signed every installation's tokens before per-installation keys.
OLD_PUBLISHED_KEYS = ('RobotControl_Access_Secret_2025', 'RobotControl_Refresh_Secret_2025')
PAGE = {'X-Requested-With': 'RobotControl'}


def run():
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    from backend.main import global_exception_handler, require_request_header
    app = FastAPI()
    app.add_exception_handler(Exception, global_exception_handler)
    app.middleware('http')(require_request_header)
    app.include_router(auth_api.router)
    app.include_router(system_api.router)
    app.include_router(admin_api.router, prefix='/api/admin')

    @app.get('/protected')
    def protected(user=Depends(get_current_user)):
        return user

    service = get_auth_service()
    lock = None
    try:
        with TestClient(app, raise_server_exceptions=False, client=('127.0.0.1', 1234), headers=PAGE) as client, \
                TestClient(app, raise_server_exceptions=False, client=('127.0.0.1', 1234)) as bare:
            def refresh_with(token):
                client.cookies.clear()
                return client.post('/api/auth/refresh', headers={'Cookie': f'rc_refresh={token}'})

            def set_cookies(response):
                return {c.split('=', 1)[0]: c.lower() for c in response.headers.get_list('set-cookie')}

            def clears_both(response):
                cookies = set_cookies(response)
                return all('max-age=0' in cookies.get(name, '') for name in ('rc_access', 'rc_refresh'))

            tokens = service.login(DEFAULT_ADMIN_USERNAME, BUILT_IN_ADMIN_PASSWORD)
            access, refresh = tokens['access_token'], tokens['refresh_token']
            bearer = {'Authorization': f'Bearer {access}'}

            lock = sqlite3.connect(os.environ['ROBOTCONTROL_AUTH_DB_FILENAME'])
            lock.execute('BEGIN EXCLUSIVE')
            me = client.get('/api/auth/me', headers=bearer)
            probe = client.get('/protected', headers=bearer)
            renewed = refresh_with(refresh)
            lock.rollback()
            lock.close()
            lock = None

            check('locked storage: /me answers 503', me.status_code == 503, [me.status_code, me.text])
            check('locked storage: protected route answers 503', probe.status_code == 503, [probe.status_code, probe.text])
            check('locked storage: refresh answers 503 and keeps the cookies',
                  renewed.status_code == 503 and not set_cookies(renewed), [renewed.status_code, renewed.text])

            me = client.get('/api/auth/me', headers=bearer)
            check('after the lock: /me answers 200', me.status_code == 200, [me.status_code, me.text])
            renewed = refresh_with(refresh)
            check('after the lock: refresh answers 200, sets a new rc_access and returns no token',
                  renewed.status_code == 200 and list(set_cookies(renewed)) == ['rc_access']
                  and renewed.json()['data'] == {}, [renewed.status_code, renewed.text, set_cookies(renewed)])

            user = service.get_user_by_id(tokens['user']['user_id'])
            expired = service.create_access_token(user, expires_delta=timedelta(seconds=-5))
            for name, token in [('garbage', 'not-a-token'), ('expired', expired), ('refresh used as access', refresh)]:
                response = client.get('/protected', headers={'Authorization': f'Bearer {token}'})
                check(f'{name} token answers 401', response.status_code == 401, [response.status_code, response.text])
                response = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
                check(f'{name} token on /me answers 401', response.status_code == 401, [response.status_code, response.text])

            # Signing keys belong to this installation; the old published texts sign nothing.
            claims = {'user_id': tokens['user']['user_id'], 'iat': datetime.utcnow(),
                      'exp': datetime.utcnow() + timedelta(minutes=5)}
            forged = jwt.encode({**claims, 'type': 'access'}, OLD_PUBLISHED_KEYS[0], algorithm='HS256')
            for route in ('/protected', '/api/auth/me'):
                response = client.get(route, headers={'Authorization': f'Bearer {forged}'})
                check(f'a token signed with the old published key answers 401 on {route}',
                      response.status_code == 401, [response.status_code, response.text])
            stored = json.loads(KEY_FILE.read_text(encoding='utf-8')) if KEY_FILE.is_file() else {}
            check('first start writes two random keys to data/config/token-secrets.json',
                  len(stored.get('access', '')) >= 64 and len(stored.get('refresh', '')) >= 64
                  and stored['access'] != stored['refresh'] and not set(stored.values()) & set(OLD_PUBLISHED_KEYS),
                  sorted(stored))
            auth_module._token_secrets = None  # what a restart does
            response = client.get('/protected', headers=bearer)
            check('after a restart the same key file keeps sessions valid',
                  response.status_code == 200 and json.loads(KEY_FILE.read_text(encoding='utf-8')) == stored,
                  [response.status_code])
            KEY_FILE.write_text('{', encoding='utf-8')
            auth_module._token_secrets = None
            try:
                auth_module.token_secrets()
                stopped = False
            except RuntimeError:
                stopped = True
            check('an unreadable key file stops start-up and is not rewritten',
                  stopped and KEY_FILE.read_text(encoding='utf-8') == '{', KEY_FILE.read_text(encoding='utf-8'))
            KEY_FILE.write_text(json.dumps(stored), encoding='utf-8')
            os.environ['ROBOTCONTROL_ACCESS_TOKEN_SECRET'] = 'a' * 64
            os.environ['ROBOTCONTROL_REFRESH_TOKEN_SECRET'] = 'b' * 64
            auth_module._token_secrets = None
            check('both key variables win over the file', auth_module.token_secrets() == ('a' * 64, 'b' * 64))
            for name in ('ROBOTCONTROL_ACCESS_TOKEN_SECRET', 'ROBOTCONTROL_REFRESH_TOKEN_SECRET'):
                os.environ.pop(name)
            # A crash while the first key file is written leaves no file, so the next start creates one.
            crash_folder = FOLDER / 'crash-config'
            get_path_manager().config_path = crash_folder

            def crash(keys, file):
                file.write('{"acc')
                raise OSError('power lost')

            auth_module._token_secrets = None
            with patch.object(auth_module.json, 'dump', crash):
                try:
                    auth_module.token_secrets()
                except RuntimeError:  # the critical log line names the file
                    pass
            left = sorted(p.name for p in crash_folder.iterdir()) if crash_folder.exists() else []
            auth_module._token_secrets = None
            check('a crash while writing the first key file leaves nothing that stops the next start',
                  left == [] and len(auth_module.token_secrets()[0]) >= 64, left)
            get_path_manager().config_path = FOLDER / 'config'
            auth_module._token_secrets = None

            response = refresh_with(access)
            check('access token used as refresh answers 401 and clears both cookies',
                  response.status_code == 401 and clears_both(response), [response.status_code, response.text])
            service.revoke_refresh_token(refresh)
            response = refresh_with(refresh)
            check('revoked refresh token answers 401 and clears both cookies',
                  response.status_code == 401 and clears_both(response), [response.status_code, response.text])
            client.cookies.clear()
            response = client.post('/api/auth/refresh')
            check('refresh without rc_refresh answers 401', response.status_code == 401, [response.status_code, response.text])

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
                  not any('access_token' in r.text or 'refresh_token' in r.text or set_cookies(r) for r in refused)
                  and last_login() == login_before, [login_before, last_login()])
            with TestClient(app, raise_server_exceptions=False, client=('192.168.1.20', 1234), headers=PAGE) as lan:
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
                                   headers={'Authorization': f"Bearer {local.cookies['rc_access']}"})
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
                me = client.get('/api/auth/me', headers={**headers, 'Authorization': f"Bearer {response.cookies.get('rc_access', '')}"})
                me_session = me.json().get('data', {}).get('session', {}) if me.status_code == 200 else {}
                check(f'/api/auth/me agrees: {name}', me_session.get('is_local') is local, [me.status_code, me_session])

            # Browsers keep the sign-in in two HttpOnly cookies; page scripts never see a token.
            client.cookies.clear()
            signed_in = client.post('/api/auth/login', json=credentials)
            cookies = set_cookies(signed_in)
            access_cookie, refresh_cookie = cookies.get('rc_access', ''), cookies.get('rc_refresh', '')
            check('a sign-in reply has no token in its body', signed_in.status_code == 200 and not
                  {'access_token', 'refresh_token'} & set(signed_in.json()['data']), signed_in.text)
            check('plain http: both cookies HttpOnly and SameSite=Strict without Secure, narrow paths and lifetimes',
                  all('httponly' in c and 'samesite=strict' in c and '; secure' not in c for c in (access_cookie, refresh_cookie))
                  and 'path=/api;' in access_cookie + ';' and 'max-age=14400' in access_cookie
                  and 'path=/api/auth' in refresh_cookie and 'max-age=604800' in refresh_cookie, cookies)
            tunnelled = set_cookies(bare.post('/api/auth/login', json=credentials,
                                              headers={**PAGE, **tunnel, 'x-forwarded-proto': 'https'}))
            check('through the tunnel (x-forwarded-proto: https) both cookies are Secure',
                  all('; secure' in tunnelled.get(name, '') for name in ('rc_access', 'rc_refresh')), tunnelled)
            response = client.get('/api/auth/me')
            check('the rc_access cookie alone signs a read in', response.status_code == 200, [response.status_code])
            jar = {'Cookie': f"rc_access={signed_in.cookies['rc_access']}"}
            wrong_change = {'current_password': 'not-it', 'new_password': 'Another password 8'}
            response = bare.post('/api/auth/change-password', json=wrong_change, headers=jar)
            check('a cookie-only POST without the request header answers 403 "Missing request header"',
                  response.status_code == 403 and response.json() == {'detail': 'Missing request header'}, response.text)
            response = bare.post('/api/auth/login', json=credentials)
            check('a sign-in POST without the request header answers 403', response.status_code == 403, response.text)
            response = bare.post('/api/auth/change-password', json=wrong_change, headers={**jar, **PAGE})
            check('the same POST with the request header reaches the route (400)', response.status_code == 400, response.text)
            response = bare.post('/api/auth/change-password', json=wrong_change,
                                 headers={'Authorization': f"Bearer {signed_in.cookies['rc_access']}"})
            check('a Bearer program needs no request header (400)', response.status_code == 400, response.text)
            # An empty Bearer header is not a sign-in, and it cannot borrow the cookie past the header rule.
            empty = {**jar, 'Authorization': 'Bearer '}
            response = bare.get('/api/auth/me', headers=empty)
            check('an empty Bearer header with the cookie answers 401', response.status_code == 401, [response.status_code, response.text])
            response = bare.post('/api/auth/change-password', json=wrong_change, headers=empty)
            check('an empty Bearer header with the cookie does not reach a change (401 or 403)',
                  response.status_code in (401, 403), [response.status_code, response.text])
            service.reset_password(DEFAULT_ADMIN_USERNAME, changed, must_reset=True)
            client.cookies.clear()
            client.post('/api/auth/login', json=credentials)
            response = client.get('/api/auth/me')
            check('/me returns a stored must_reset, so a reload keeps the required change',
                  response.status_code == 200 and response.json()['data'].get('must_reset') is True, response.text)
            service.reset_password(DEFAULT_ADMIN_USERNAME, changed, must_reset=False)
            client.cookies.clear()
            client.post('/api/auth/login', json=credentials)
            before_logout = client.cookies.get('rc_refresh')
            response = client.post('/api/auth/logout')
            check('logout answers 200 and clears both cookies', response.status_code == 200 and clears_both(response),
                  [response.status_code, set_cookies(response)])
            response = refresh_with(before_logout)
            check('after logout the refresh token answers 401', response.status_code == 401, [response.status_code, response.text])
            client.cookies.clear()
            response = client.post('/api/auth/logout')
            check('logout without a sign-in still answers 200', response.status_code == 200, [response.status_code])

            # The folder list follows the restore rule: an admin, or a user on this computer.
            service.register_user('plain', 'plain@example.test', 'Plain user password 1')
            plain = bare.post('/api/auth/login', json={'username': 'plain', 'password': 'Plain user password 1'},
                              headers=PAGE).cookies['rc_access']
            admin = bare.post('/api/auth/login', json=credentials, headers=PAGE).cookies['rc_access']
            for name, token, headers, allowed in [
                ('a remote plain user', plain, tunnel, False),
                ('a local plain user', plain, {}, True),
                ('a remote admin', admin, tunnel, True),
            ]:
                response = bare.get('/api/system/browse', params={'path': str(FOLDER)},
                                    headers={**headers, 'Authorization': f'Bearer {token}'})
                check(f'{name} {"lists" if allowed else "is refused"} folders',
                      response.status_code == (200 if allowed else 403), [response.status_code, response.text[:200]])

            # Role changes and deletes (two real admins and a user, with their existing sign-ins).
            audit = []
            audit_handler = logging.Handler()
            audit_handler.emit = lambda record: audit.append(record.msg)
            logging.getLogger('pyrobot.audit').addHandler(audit_handler)
            logging.getLogger('pyrobot.audit').setLevel(logging.INFO)
            service.register_user('second', 'second@example.test', 'Second admin password 1')
            second = bare.post('/api/auth/login', json={'username': 'second', 'password': 'Second admin password 1'},
                               headers=PAGE).cookies['rc_access']

            def as_user(token, method, path, body=None):
                return bare.request(method, path, json=body, headers={'Authorization': f'Bearer {token}'})

            def role_of(username):
                row = service.db.get_user_by_username(username)
                return row['role'] if row else None

            def refused(response, status, message):
                body = response.json()
                return response.status_code == status and message in (body.get('detail'), (body.get('error') or {}).get('message'))

            response = as_user(plain, 'PUT', '/api/admin/users/second/role', {'role': 'admin'})
            check('a plain user cannot change a role (403 with the lost-role text)', refused(response, 403, 'You are no longer an admin. Reload the page')
                  and role_of('second') == 'user', response.text)
            response = as_user(admin, 'PUT', f'/api/admin/users/{DEFAULT_ADMIN_USERNAME}/role', {'role': 'user'})
            check('an admin cannot change their own role (400)', refused(response, 400, 'Cannot change your own role')
                  and role_of(DEFAULT_ADMIN_USERNAME) == 'admin', response.text)
            response = as_user(admin, 'PUT', '/api/admin/users/nobody/role', {'role': 'admin'})
            check('an unknown user answers 404', refused(response, 404, 'User not found'), response.text)
            response = as_user(admin, 'PUT', '/api/admin/users/second/role', {'role': 'owner'})
            check('a role other than user or admin is refused', response.status_code == 422 and role_of('second') == 'user', response.text)

            response = as_user(admin, 'PUT', '/api/admin/users/second/role', {'role': 'admin'})
            check('an admin promotes a user (200 with username and role)', response.status_code == 200
                  and response.json()['data'] == {'username': 'second', 'role': 'admin'}, response.text)
            response = as_user(second, 'GET', '/api/admin/users')
            check("the promoted user's existing sign-in passes an admin route at once", response.status_code == 200, response.text[:200])
            response = as_user(second, 'PUT', '/api/admin/users/plain/role', {'role': 'admin'})
            check('the new admin may change another account', response.status_code == 200 and role_of('plain') == 'admin', response.text)
            response = as_user(second, 'PUT', '/api/admin/users/plain/role', {'role': 'user'})
            check('an admin may demote another admin', response.status_code == 200 and role_of('plain') == 'user', response.text)
            response = as_user(plain, 'GET', '/api/admin/users')
            check("the demoted admin's existing sign-in is refused an admin route at once", response.status_code == 403, response.text)

            # An admin demoted by another admin while their page stayed open: the next change says why.
            lost = 'You are no longer an admin. Reload the page'
            for name, method, path, body in [
                ('a role change', 'PUT', f'/api/admin/users/{DEFAULT_ADMIN_USERNAME}/role', {'role': 'user'}),
                ('a delete', 'DELETE', f'/api/admin/users/{DEFAULT_ADMIN_USERNAME}', None),
            ]:
                as_user(admin, 'PUT', '/api/admin/users/second/role', {'role': 'admin'})
                demoted = as_user(admin, 'PUT', '/api/admin/users/second/role', {'role': 'user'})
                response = as_user(second, method, path, body)
                check(f'{name} by an admin demoted earlier is refused (403 "{lost}") and the other admin stays',
                      demoted.status_code == 200 and refused(response, 403, lost)
                      and role_of(DEFAULT_ADMIN_USERNAME) == 'admin' and role_of('second') == 'user',
                      [response.status_code, response.text, role_of(DEFAULT_ADMIN_USERNAME)])
            response = as_user(plain, 'DELETE', '/api/admin/users/second')
            check(f'a plain user cannot delete an account (403 "{lost}")', refused(response, 403, lost)
                  and role_of('second') == 'user', response.text)
            response = as_user(plain, 'GET', '/api/admin/users')
            check('other admin routes keep "Admin access required"', refused(response, 403, 'Admin access required'), response.text)
            response = as_user(admin, 'DELETE', f'/api/admin/users/{DEFAULT_ADMIN_USERNAME}')
            check('an admin cannot delete their own account (400)', response.status_code == 400
                  and role_of(DEFAULT_ADMIN_USERNAME) == 'admin', response.text)
            logging.getLogger('pyrobot.audit').removeHandler(audit_handler)
            entries = [e for e in audit if isinstance(e, dict) and e.get('action') == 'change_user_role']
            check('every role change and refusal is in the audit log with actor, target and role',
                  any(e['success'] and e['actor'] == 'second' and e['details'] == {'target': 'plain', 'role': 'user'} for e in entries)
                  and any(not e['success'] and e['details'].get('target') == DEFAULT_ADMIN_USERNAME for e in entries)
                  and any(not e['success'] and e['details'].get('target') == 'nobody' for e in entries),
                  entries)

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
