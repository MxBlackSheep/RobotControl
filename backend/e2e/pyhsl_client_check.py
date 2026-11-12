"""Read-only PyHSL boundary check: real HTTP socket, discovery files and SQLite.

Failure cases:
1. Missing folder/file or malformed discovery: reason, no email or crash.
2. Instance mismatch: unavailable, no token sent.
3. Non-loopback URL: refused, no token sent (including redirects).
4. Token/bootstrap never appear in logs, exceptions, replies or emails.
5. Hung Run Control: cached HTTP status responds immediately; reads unknown, not closed; stale at 60 seconds.
6. Failed run: one email across polls and restart with the same SQLite database.
7. Review required: one email, blocked; an active review list is cached, not clear.
8. Completed/stopped without review: no email.
9. Unknown status: raw, non-terminal, no success or email.
10. Runs older than 24 hours: no email.
11. HTTP 401: unknown with a reason.
12. The review list, which makes Run Control parse every journal, is read only when a run row changes.

Run with PYTHONPATH set to the checkout. No installed PyHSL or Hamilton is used.
"""
import io
import json
import logging
import tempfile
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import pyhsl
from backend.services.auth import get_current_user
from backend.services.pyhsl_client import PyHslClient, PyHslError, PyHslRefusal
from backend.services.pyhsl_monitor import PyHslMonitor
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase


class RunControl(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        s = self.server
        s.requests.append((self.path, self.headers.get('Authorization')))
        if self.path.endswith('/health'):
            code, body = 200, {'instance_id': s.instance_id}
        else:
            s.entered.set()
            s.release.wait(4)
            code = s.code
            body = ({'runs': s.runs} if self.path.endswith('/runs') else s.reviews)
            if code != 200:
                body = {'error': s.refusal if code == 409 else 'Denied'}
        data = json.dumps(body).encode()
        self.send_response(code)
        if code == 302:
            self.send_header('Location', 'http://example.invalid/')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class Email:
    last_error = None

    def __init__(self):
        self.messages = []

    def get_manual_recovery_recipients(self):
        return ['recovery@example.invalid']

    def send(self, subject, body, **options):
        self.messages.append((subject, body, options))
        return True


def run():
    logs = io.StringIO()
    handler = logging.StreamHandler(logs)
    logging.getLogger().addHandler(handler)
    try:
        with tempfile.TemporaryDirectory() as folder, ThreadingHTTPServer(('127.0.0.1', 0), RunControl) as server:
            server.instance_id, server.code = 'fixture-instance', 200
            server.refusal = 'Run refused'
            server.requests, server.runs = [], []
            server.reviews = {'cases': [], 'blocked': False, 'active': False}
            server.entered, server.release = threading.Event(), threading.Event()
            server.release.set()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = Path(folder)
            app_dir = root / 'data' / 'sessions' / 'app'
            db = SQLiteSchedulingDatabase(str(root / 'notifications.db'))
            email = Email()
            client = PyHslClient(root / 'data', timeout=0.5)
            monitor = PyHslMonitor(client, email=email)
            def discover(**changes):
                app_dir.mkdir(parents=True, exist_ok=True)
                values = {'url': f'http://127.0.0.1:{server.server_port}',
                          'instance_id': 'fixture-instance', 'bootstrap': 'BOOTSTRAP-SECRET'}
                values.update(changes)
                (app_dir / 'instance.json').write_text(json.dumps(values))
                (app_dir / 'machine-token').write_text('MACHINE-SECRET')
            def row(status, run_id='run', days=0):
                return dict(run_id=run_id, protocol='Fixture', status=status, mode='simulation',
                            completed_count=0, error=None, origin='manual',
                            created_at=(datetime.now() - timedelta(days=days)).isoformat())
            with (patch('backend.services.scheduling.get_scheduling_database_manager', return_value=db),
                  patch('backend.services.pyhsl_monitor.REVIEW_READ_SECONDS', -1)):
                monitor.poll()
                assert monitor.status()['state'] == 'not_running'
                app_dir.mkdir(parents=True)
                monitor.poll()
                (app_dir / 'instance.json').write_text('{bad')
                monitor.poll()
                assert monitor.status()['state'] == 'unknown' and not email.messages
                discover(instance_id='stale')
                monitor.poll()
                assert monitor.status()['state'] == 'not_running'
                assert all(auth is None for _, auth in server.requests)
                before = len(server.requests)
                for url in ['http://example.invalid', 'https://127.0.0.1', 'http://127.0.0.1@evil.invalid']:
                    discover(url=url)
                    monitor.poll()
                    assert monitor.status()['state'] == 'unknown'
                assert len(server.requests) == before
                discover()
                server.runs = [row('failed')]
                for _ in range(2):
                    monitor.poll()
                monitor = PyHslMonitor(client, email=email)
                monitor.poll()
                assert len(email.messages) == 1
                assert db.get_notification_logs()[0].execution_id == 'run'
                for status in ['outcome_unknown', 'reconciliation_required']:
                    server.runs = [row(status, status)]
                    monitor.poll(); monitor.poll()
                assert len(email.messages) == 3
                server.runs = [row('failed')]
                server.reviews = {'cases': [{'run_id': 'run', 'requires_review': True}], 'blocked': True, 'active': False}
                monitor.poll(); monitor.poll()
                assert len(email.messages) == 4 and monitor.status()['reviews']['blocked']
                assert 'record the Run review in Run Control' in email.messages[-1][1]
                server.reviews['active'] = True
                monitor.poll()
                assert not monitor.status()['reviews']['known'] and 'cached' in monitor.status()['reason']
                server.reviews = {'cases': [], 'blocked': False, 'active': False}
                server.runs = [row('completed', 'complete'), row('stopped', 'stop'), row('failed', 'old', 2)]
                monitor.poll()
                assert len(email.messages) == 4 and monitor.status()['run'] is None
                server.runs = [row('future_status', 'future')]
                monitor.poll()
                assert monitor.status()['run']['status'] == 'future_status'
                assert monitor.status()['state'] == 'running' and len(email.messages) == 4
                server.runs = [dict(row('running'), error='MACHINE-SECRET')]
                monitor.poll()
                assert monitor.status()['run']['error'] == '[redacted]'
                server.code = 401
                monitor.poll()
                assert monitor.status()['state'] == 'unknown' and '401' in monitor.status()['reason']
                server.code = 409
                try:
                    client.get('/runs')
                    raise AssertionError('expected refusal')
                except PyHslRefusal as exc:
                    assert str(exc) == 'Run refused'
                server.refusal = 'Refused MACHINE-SECRET'
                try:
                    client.get('/runs')
                    raise AssertionError('expected refusal')
                except PyHslRefusal as exc:
                    assert str(exc) == 'Refused [redacted]'
                server.code = 302
                try:
                    client.get('/runs')
                    raise AssertionError('expected redirect refusal')
                except PyHslError:
                    pass
                server.code = 200
                for status in ['starting', 'paused', 'waiting_for_input', 'waiting_for_next', 'closing', 'finalizing']:
                    server.runs = [row(status)]
                    monitor.poll()
                    assert monitor.status()['state'] == 'running'
                server.runs = [row('running')]
                monitor.poll()
                assert monitor.status()['state'] == 'running'
                app = FastAPI()
                app.include_router(pyhsl.router)
                app.dependency_overrides[get_current_user] = lambda: {'role': 'viewer'}
                server.entered.clear(); server.release.clear()
                polling = threading.Thread(target=monitor.poll)
                polling.start()
                assert server.entered.wait(2)
                with patch.object(pyhsl, 'get_pyhsl_monitor', return_value=monitor), TestClient(app, client=('192.0.2.1', 1234)) as http:
                    started = time.monotonic()
                    response = http.get('/api/pyhsl/status')
                    assert response.status_code == 200 and time.monotonic() - started < 0.3
                    with patch('backend.services.pyhsl_monitor.time.monotonic', return_value=time.monotonic() + 61):
                        stale = http.get('/api/pyhsl/status').json()
                    assert stale['state'] != 'running' and not stale['reviews']['known']
                polling.join(2)
                assert not polling.is_alive() and monitor.status()['state'] == 'unknown'
                server.release.set()
                server.entered.clear()
                with patch('backend.services.pyhsl_monitor.REVIEW_READ_SECONDS', 120):
                    reads = lambda: sum(path.endswith('/reviews') for path, _ in server.requests)
                    server.runs = [row('completed', run_id='settled')]
                    server.reviews = {'cases': [], 'blocked': False, 'active': False}
                    monitor.poll()
                    before = reads()
                    monitor.poll(); monitor.poll()
                    assert reads() == before
                    server.runs = [row('failed', run_id='settled')]
                    monitor.poll()
                    assert reads() == before + 1
                monitor.start()
                assert server.entered.wait(2)
                monitor.stop()
                assert not monitor._thread.is_alive()
                exposed = logs.getvalue() + repr(email.messages) + repr(monitor.status()) + response.text
                assert 'MACHINE-SECRET' not in exposed and 'BOOTSTRAP-SECRET' not in exposed
            server.shutdown()
        print('PyHSL HTTP/SQLite check: all eleven failure cases passed.')
    finally:
        logging.getLogger().removeHandler(handler)


if __name__ == '__main__':
    run()
