"""Scheduled PyHSL boundary check: real SQLite, scheduler worker and HTTP socket.

Run with PYTHONPATH set to the worktree:
    uv run --locked python backend/e2e/pyhsl_runner_check.py

Failure cases (Run Control reply shapes recorded in Simulation, 9 November 2026):
1. Completed: once off, interval advances; request_id is execution ID, mode sent.
2. A real 20-second POST leaves edits and status reads responsive.
3. Lost reply: identical resend, one run and one database preparation.
4. Every status/review/refusal outcome; error wording cannot classify an abort.
5. Acknowledge refuses review, active or unreadable reconciliation, then succeeds.
6. Unavailable waits and alerts once at 180 seconds from queuing; VENUS proceeds,
   then PyHSL starts when Run Control returns; active/review/unknown gates.
7. Changed revision holds before preparation or POST.
8. Restart with run_id follows once, no legacy observation or duplicate email.
9. Restart without run_id adopts a match, resends within five minutes, otherwise
   holds; no second preparation, including a crash before the request was saved.
   A saved refusal survives interrupted finalization without resending the POST.
10. Changed instance_id is rediscovered; outcome_unknown holds the queue.
    An archived/unknown run fails, holds and alerts aborted instead of following forever.
    Preparation failure reports execution_failed immediately with a recovery hold.
11. Unknown status keeps following, never success; silence never means finished.
12. VENUS keeps its Simulation Mode gate; old SQLite rows migrate as venus.
13. Save refuses disallowed modes, cleanup, unimported or closed Run Control;
    updates keep omitted fields and revalidate; local admin/user Validate only.
14. Maintenance and database writes refuse while PyHSL is active.
15. Token absent from logs, execution rows, replies and emails; machine runs do
    not generate the monitor's independent alerts.
16. Remote signed-in reads expose only allowed run/journal fields; invalid IDs and
    unknown roles make no request. Reports are sandboxed and bounded. Closed,
    refused and timed-out reads return 503, 404 and 504; cached review state is used without a reconciliation request.
17. A timed-out Start resends the identical request without repeating preparation;
    reconciliation reads use 30 seconds and a monitor timeout stays unknown.
18. Fresh Start expires after five minutes, adopting a match or holding even offline.
19. Validate losing Run Control waits without preparation or Start, then recovers or holds.

Only the Run Control service, database package, process and email boundaries are
fixtures. No installed PyHSL, Hamilton, SQL Server or instrument is accessed.
"""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
from pathlib import Path
import socket
import tempfile
from threading import Event, Thread
import time
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.e2e.failed_occurrence_check import Fixture
from backend.models import JobExecution
from backend.services.pyhsl_client import PyHslClient, PyHslTimeout, PyHslUnavailable
from backend.services.pyhsl_monitor import PyHslMonitor
from backend.services.scheduling import scheduler_engine as se
from backend.services.sqlite_safety import SafetyConflict


TOKEN = 'FIXTURE-MACHINE-TOKEN'


class RunControl(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        s = self.server
        if self.path == '/api/v1/health':
            return self.reply(200, {'instance_id': s.instance_id})
        assert self.headers['Authorization'] == 'Bearer ' + TOKEN
        if s.unreachable:
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        if self.path == '/api/v1/runs':
            return self.reply(200, {'sessions': [dict(run_id=k, protocol='fixture',
                created_at=v['created_at'], status=v['status'], origin='machine', mode='simulation',
                error=v['error'], completed_count=0) for k, v in s.runs.items()]})
        if self.path == '/api/v1/reconciliation':
            return self.reply(200, s.reviews)
        if '/journal?' in self.path:
            s.journal_path = self.path
            return self.reply(200, s.journal)
        if self.path.endswith('/report'):
            return self.reply(200, s.report)
        run_id = self.path.removeprefix('/api/v1/runs/')
        if run_id not in s.runs or s.run_refused:
            return self.reply(409, {'error': 'Run unavailable ' + TOKEN})
        return self.reply(200, s.runs[run_id])

    def do_POST(self):
        s = self.server
        assert self.headers['Authorization'] == 'Bearer ' + TOKEN
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/v1/validate':
            if s.validate_code != 200:
                return self.reply(s.validate_code, {'error': s.error})
            return self.reply(200, {'protocol': {'id': data['protocol_id'], 'revision': s.revision,
                'parameters': {'round': {'label': 'Round', 'type': 'choice', 'default': 'first',
                    'choices': ['first', 'second']}}}, 'mode': data['mode'], 'parameters': data['parameters']})
        assert self.path == '/api/v1/runs', 'No run controls are permitted'
        s.posts.append(data)
        s.entered.set()
        if s.delay:
            time.sleep(s.delay)
        if s.start_code != 200:
            return self.reply(s.start_code, {'error': s.error})
        run_id = 'fixture-run'
        if not s.runs:
            s.runs[run_id] = dict(run_id=run_id, status=s.outcome, host_status='closed',
                created_at=datetime.now().isoformat(), error=s.error, mode=data['mode'],
                configuration={'request_id': data['request_id']})
        if s.lose_reply:
            s.lose_reply = False
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        if s.timeout_reply:
            s.timeout_reply = False
            time.sleep(.2)
        self.reply(200, s.runs[run_id])


def until(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Boundary check did not reach the expected state')


@contextmanager
def fixture(*, allow_venus=False):
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        root = Path(folder)
        f = Fixture(root, stack)
        server = ThreadingHTTPServer(('127.0.0.1', 0), RunControl)
        server.instance_id, server.revision = 'instance-one', 'revision-one'
        server.validate_code = server.start_code = 200
        server.error, server.outcome = 'abort; stopped by user ' + TOKEN, 'completed'
        server.runs, server.posts = {}, []
        server.reviews = dict(cases=[], blocked=False, active=False)
        server.delay, server.lose_reply, server.unreachable = 0, False, False
        server.timeout_reply = server.run_refused = False
        server.report = b'<html><script>alert(1)</script>FIXTURE-MACHINE-TOKEN</html>'
        server.journal = dict(events=[dict(revision=1, at='now', event='device_intent',
            details=dict(summary='Move ' + TOKEN, path='private'), state={'deck': 'private'})], next=1)
        server.entered = Event()
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # These are disposable stand-in discovery files, never the real sessions.
        app_dir = root / 'data' / 'sessions' / 'app'
        app_dir.mkdir(parents=True)
        def discover():
            (app_dir / 'instance.json').write_text(json.dumps(dict(
                url=f'http://127.0.0.1:{server.server_port}', instance_id=server.instance_id)))
            (app_dir / 'machine-token').write_text(TOKEN)
        discover()
        client = PyHslClient(root / 'data', timeout=.5)
        monitor = PyHslMonitor(client)
        stack.enter_context(patch('backend.services.pyhsl_monitor.get_pyhsl_monitor', return_value=monitor))
        stack.enter_context(patch('backend.services.pyhsl_client.PyHslClient', return_value=client))
        # Fixture always replaces Popen; most checks should not reach VENUS at all.
        if not allow_venus:
            stack.enter_context(patch('backend.services.scheduling.experiment_executor.ExperimentExecutor.execute_experiment',
                                      side_effect=AssertionError('VENUS must not run')))
        stack.enter_context(patch.object(monitor, '_alert', side_effect=AssertionError('Machine alert duplicated')))
        f.engine.pyhsl_runner.client = client
        f.server, f.client, f.monitor, f.discover, f.app_dir = server, client, monitor, discover, app_dir
        f.engine.config.check_interval_seconds = .05
        f.engine.pyhsl_runner.poll_seconds = .02
        monitor.poll()
        f.engine._running = True
        worker = Thread(target=f.engine._job_worker_loop, daemon=True)
        worker.start()
        f.worker = worker
        try:
            yield f
        finally:
            f.engine._running = False
            f.engine._stop_event.set()
            f.engine._job_queue.put(None)
            worker.join(25)
            if f.engine._scheduler_thread:
                f.engine._scheduler_thread.join(3)
            f.worker.join(3)
            server.shutdown()
            server.server_close()
            thread.join(2)
            assert not worker.is_alive()


def schedule(f, kind='once', **kwargs):
    return f.schedule(kind, runner='pyhsl', protocol_id='fixture', protocol_revision='revision-one',
        parameters={'round': 'first'}, mode='simulation', **kwargs)


def dispatch(f, s):
    f.engine._process_due_job(s, f.now)
    until(lambda: bool(f.storage.get_execution_history(s.schedule_id)))
    return f.storage.get_execution_history(s.schedule_id)[0]['execution_id']


def finished(f, execution_id):
    until(lambda: f.engine.run_log_monitor.store.execution(execution_id).status in {'completed', 'failed'})
    until(lambda: not f.engine._owned_execution_ids)
    return f.engine.run_log_monitor.store.execution(execution_id)


def outcomes():
    rows = [('completed', False, 'completed', False, None),
            ('completed', True, 'completed', True, 'pyhsl_review_required'),
            ('failed', False, 'failed', False, 'execution_failed'),
            ('stopped', False, 'failed', False, 'execution_failed'),
            ('failed', True, 'failed', True, 'pyhsl_review_required'),
            ('stopped', True, 'failed', True, 'pyhsl_review_required'),
            ('outcome_unknown', False, 'failed', True, 'aborted'),
            ('reconciliation_required', False, 'failed', True, 'aborted')]
    for outcome, review, status, hold, trigger in rows:
        with fixture() as f:
            s = schedule(f)
            f.server.outcome = outcome
            if review:
                f.server.reviews = dict(active=False, blocked=True,
                    cases=[dict(run_id='fixture-run', requires_review=True)])
            # Gate reading is from before the scheduled run started.
            eid = dispatch(f, s)
            e = finished(f, eid)
            saved = f.storage.get_schedule_by_id(s.schedule_id)
            assert e.status == status and saved.recovery_required == hold and not saved.is_active
            assert [x[0] for x in f.sent] == ([trigger] if trigger else [])
            assert f.server.posts[0]['request_id'] == eid
            assert f.server.posts[0]['mode'] == 'simulation'
            assert f.prepared == [eid] and not f.launched
            f.monitor.poll()
            assert TOKEN not in json.dumps(e.to_dict()) + repr(f.sent)
    with fixture() as f:
        s = schedule(f, 'interval', interval_hours=6)
        finished(f, dispatch(f, s))
        saved = f.storage.get_schedule_by_id(s.schedule_id)
        assert saved.is_active and saved.start_time > f.now
    for code in (409, 422, 500):
        with fixture() as f:
            s = schedule(f)
            f.server.start_code = code
            e = finished(f, dispatch(f, s))
            assert e.status == 'failed' and f.storage.get_schedule_by_id(s.schedule_id).recovery_required
            assert f.sent[0][0] == 'execution_failed'
            if code == 409:
                assert e.error_message == f.server.error.replace(TOKEN, '[redacted]')
    for reviews in ({'active': True, 'blocked': False, 'cases': []}, {'active': False}):
        with fixture() as f:
            s = schedule(f)
            f.server.reviews = reviews
            f.engine.pyhsl_runner.reconciliation_seconds = .05
            e = finished(f, dispatch(f, s))
            assert e.status == 'failed' and f.sent[0][0] == 'aborted'
            assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required


def slow_and_lost():
    with fixture() as f:
        s = schedule(f)
        f.server.delay = 20
        eid = dispatch(f, s)
        assert f.server.entered.wait(3)
        start = time.monotonic()
        f.engine.get_status()
        assert f.save(f.storage.get_schedule_by_id(s.schedule_id)) == 200
        assert time.monotonic() - start < 2, 'POST held a scheduler or SQLite lock'
        assert f.engine.run_log_monitor.store.execution(eid).status == 'running'
        e = finished_after_slow(f, eid)
        assert e.status == 'completed'
    with fixture() as f:
        s = schedule(f)
        f.server.lose_reply = True
        finished(f, dispatch(f, s))
        assert len(f.server.posts) == 2 and f.server.posts[0] == f.server.posts[1]
        assert len(f.server.runs) == len(f.prepared) == 1


def finished_after_slow(f, eid):
    until(lambda: f.engine.run_log_monitor.store.execution(eid).status == 'completed', timeout=25)
    return finished(f, eid)


def runner_failures():
    with fixture() as f:
        s = schedule(f)
        f.server.timeout_reply = True
        post = f.client.post
        def short_start(path, data, **kwargs):
            return post(path, data, timeout=.05 if path == '/runs' else 60)
        with patch.object(f.client, 'post', side_effect=short_start), patch.object(f.client, 'get', wraps=f.client.get) as get:
            assert finished(f, dispatch(f, s)).status == 'completed'
            assert len(f.server.posts) == 2 and f.server.posts[0] == f.server.posts[1]
            assert len(f.prepared) == len(f.server.runs) == 1
            f.engine.pyhsl_runner.acknowledge(s.schedule_id)
            assert all(c.kwargs.get('timeout') == 30 for c in get.call_args_list if c.args[0] == '/reconciliation')
        with patch.object(f.client, 'get', side_effect=PyHslTimeout('Run Control did not answer in time')):
            f.monitor.poll()
            assert f.monitor.status()['state'] == 'unknown'
    with fixture() as f:
        s = schedule(f)
        f.server.run_refused = True
        e = finished(f, dispatch(f, s))
        assert e.status == 'failed' and f.sent[0][0] == 'aborted'
        assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required
    for error in (RuntimeError('Preparation failed'), SafetyConflict('Safety changed')):
        with fixture() as f:
            s = schedule(f)
            with patch('backend.services.scheduling.pyhsl_runner.PreExecutionPipeline.prepare', side_effect=error):
                e = finished(f, dispatch(f, s))
            assert e.status == 'failed' and e.error_message == str(error)
            assert f.sent[0][0] == 'execution_failed' and not f.server.posts
            assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required
            assert f.sent[0][1]['schedule_active'] is False


def bounded_waits():
    from backend.services.scheduling import pyhsl_runner as runner
    for recover in (True, False):
        with fixture() as f:
            s = schedule(f)
            elapsed = [0]
            post = f.client.post
            def validate(path, data, **kwargs):
                if path == '/validate' and (not recover or elapsed[0] == 0):
                    assert not f.prepared and not f.server.posts
                    raise PyHslUnavailable('Run Control closed after monitor poll')
                return post(path, data, **kwargs)
            def wait():
                elapsed[0] += 100
                return False
            with patch.object(runner, 'time', SimpleNamespace(monotonic=lambda: elapsed[0])), \
                    patch.object(f.engine.pyhsl_runner, '_wait', side_effect=wait), \
                    patch.object(f.client, 'post', side_effect=validate):
                e = finished(f, dispatch(f, s))
            assert e.status == ('completed' if recover else 'failed')
            assert len(f.prepared) == len(f.server.posts) == int(recover)
            assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required == (not recover)
            assert [x[0] for x in f.sent].count('monitoring_unavailable') == int(not recover)
    for available, match in ((False, False), (True, False), (True, True)):
        with fixture() as f:
            s = schedule(f)
            elapsed = [0]
            class Clock(datetime):
                @classmethod
                def now(cls):
                    return datetime.now() + timedelta(seconds=elapsed[0])
            post = f.client.post
            def start(path, data, **kwargs):
                if path == '/runs':
                    if match:
                        post(path, data, **kwargs)
                    elapsed[0] = 301
                    f.server.unreachable = not available
                    raise PyHslUnavailable('Lost start reply')
                return post(path, data, **kwargs)
            with patch.object(runner, 'datetime', Clock), patch.object(f.client, 'post', side_effect=start) as calls:
                e = finished(f, dispatch(f, s))
            assert len([c for c in calls.call_args_list if c.args[0] == '/runs']) == 1
            assert len(f.prepared) == 1
            assert e.status == ('completed' if match else 'failed')
            assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required == (not match)
            if not match:
                assert e.error_message.startswith('PyHSL start could not be confirmed;')


def relay_reads():
    from backend.api import pyhsl as api
    from backend.services.auth import get_current_user
    with fixture() as f:
        run_id = 'a' * 32
        f.server.runs[run_id] = dict(run_id=run_id, protocol='fixture', status='running', created_at=datetime.now().isoformat(), error=None,
            mode={'mode': 'simulation', 'source': 'private'}, configuration=dict(origin='machine',
                protocol={'revision': 'revision-one'}, path='private'), deck='private',
            current=dict(operation_id='op', operation='initialize', status='dispatched', positions={'deck': 'private'}),
            prompt=dict(message='Continue?', choices=['yes'], answered=False))
        app = FastAPI()
        app.include_router(api.router)
        with patch.object(api, 'PyHslClient', return_value=f.client), patch.object(api, 'get_pyhsl_monitor', return_value=f.monitor), TestClient(app, client=('198.51.100.5', 50000)) as http:
            url = f'/api/pyhsl/runs/{run_id}'
            for role in ('admin', 'user'):
                app.dependency_overrides[get_current_user] = lambda: {'role': role}
                with patch.object(f.client, 'get', wraps=f.client.get) as get:
                    response = http.get(url)
                    assert [c.args[0] for c in get.call_args_list] == [f'/runs/{run_id}']
                assert response.status_code == 200, response.text
                run = response.json()
                assert set(run) == {'run_id', 'protocol', 'status', 'host_status', 'mode', 'completed_count',
                    'error', 'origin', 'created_at', 'updated_at', 'current', 'prompt', 'protocol_revision', 'requires_review'}
                assert run['origin'] == 'machine' and run['protocol_revision'] == 'revision-one'
                assert run['mode'] == 'simulation' and run['requires_review'] is False
                assert run['prompt'] == {'waiting': True, 'text': 'Continue?'}
                assert set(run['current']) == {'operation_id', 'operation', 'status'}
                assert 'private' not in response.text
            with patch.object(f.monitor, 'status', return_value={'reviews': {'known': True, 'run_ids': [run_id]}}):
                assert http.get(url).json()['requires_review'] is True
            page = http.get(url + '/journal?after=3&limit=999').json()
            assert page == dict(events=[dict(revision=1, at='now', event='device_intent', text='Move [redacted]')], next=1)
            assert f.server.journal_path.endswith('?after=3&limit=200')
            report = http.get(url + '/report')
            assert report.status_code == 200 and report.headers['content-security-policy'] == 'sandbox'
            assert report.headers['content-type'].startswith('text/html') and TOKEN not in report.text
            with patch.object(api, 'REPORT_MAX_BYTES', 10):
                response = http.get(url + '/report')
                assert response.status_code == 502 and 'too large' in response.text
            with patch.object(f.client, '_discover', side_effect=AssertionError('Unexpected request')):
                for suffix in ('', '/journal', '/report'):
                    for bad in ('bad', 'A' * 32, 'a' * 31, 'a' * 33):
                        assert http.get('/api/pyhsl/runs/' + bad + suffix).status_code == 400
                    app.dependency_overrides[get_current_user] = lambda: {'role': 'unknown'}
                    assert http.get(url + suffix).status_code == 403
                    app.dependency_overrides[get_current_user] = lambda: {'role': 'user'}
            f.server.reviews['active'] = True
            f.monitor.poll()
            assert http.get(url).json()['requires_review'] is None
            get = f.client.get
            def review_timeout(path, **kwargs):
                if path == '/reconciliation':
                    raise PyHslTimeout('Run Control did not answer in time')
                return get(path, **kwargs)
            with patch.object(f.client, 'get', side_effect=review_timeout):
                f.monitor.poll()
                assert http.get(url).json()['requires_review'] is None
            f.server.run_refused = True
            response = http.get(url)
            assert response.status_code == 404 and TOKEN not in response.text
            with patch.object(f.client, '_discover', side_effect=PyHslTimeout('Run Control did not answer in time')):
                assert http.get(url).status_code == 504
            f.app_dir.joinpath('instance.json').unlink()
            for suffix in ('', '/journal', '/report'):
                assert http.get(url + suffix).status_code == 503


def revision_and_acknowledge():
    with fixture() as f:
        s = schedule(f)
        f.server.revision = 'reimported'
        e = finished(f, dispatch(f, s))
        assert e.error_message == 'Protocol revision changed in Run Control; save the schedule again'
        assert not f.prepared and not f.server.posts
    with fixture() as f:
        s = schedule(f)
        f.server.reviews = dict(active=False, blocked=True,
            cases=[dict(run_id='fixture-run', requires_review=True)])
        finished(f, dispatch(f, s))
        def acknowledge():
            state = f.engine.get_manual_recovery_state()
            return f.engine.resolve_manual_recovery(s.schedule_id, 'Reviewed', 'fixture', state.safety_revision)
        for active, unreachable, review in ((False, False, True), (True, False, False), (False, True, False)):
            f.server.reviews = dict(active=active, blocked=review,
                cases=[dict(run_id='fixture-run', requires_review=review)])
            f.server.unreachable = unreachable
            try:
                acknowledge()
                raise AssertionError('Unsafe acknowledgement accepted')
            except SafetyConflict:
                pass
        f.server.unreachable = False
        assert not acknowledge().recovery_required


def gates_and_following():
    with fixture(allow_venus=True) as f:
        s = schedule(f)
        for reading, expected in (
            (dict(state='not_running', run=None, reviews={}), 'PyHSL Run Control is not running'),
            (dict(state='running', run={'run_id': 'other'}, reviews={}), 'A PyHSL run is active'),
            (dict(state='running', run=None, reviews={'known': True, 'blocked': True}), 'PyHSL runs wait for a Run review'),
            (dict(state='unknown', reason='Unreadable', run=None, reviews={}), 'Unreadable')):
            with patch.object(f.monitor, 'status', return_value=reading):
                assert expected in f.engine._resolve_dispatch_block_reason(s)
        f.app_dir.joinpath('instance.json').unlink()
        f.monitor.poll()
        eid = dispatch(f, s)
        until(lambda: f.engine._get_queue_waiting_reason(s.schedule_id) == 'PyHSL Run Control is not running')
        venus = f.schedule(mode='real')
        f.returncode, f.stderr, f.sql_state = 0, '', 'Complete'
        venus_id = dispatch(f, venus)
        assert finished(f, venus_id).status == 'completed'
        assert len(f.launched) == 1 and not f.server.posts
        assert f.prepared == [venus_id]
        with f.engine._jobs_lock:
            f.engine._queue_runtime[s.schedule_id].queued_at -= timedelta(seconds=181)
        until(lambda: any(x[0] == 'pyhsl_unavailable' for x in f.sent), timeout=3)
        time.sleep(1.1)
        assert [x[0] for x in f.sent].count('pyhsl_unavailable') == 1
        f.discover()
        f.monitor.poll()
        assert finished(f, eid).status == 'completed'
    with fixture() as f:
        s = schedule(f)
        f.server.outcome = 'future_status'
        eid = dispatch(f, s)
        until(lambda: bool(f.server.runs))
        time.sleep(.1)
        assert f.engine.run_log_monitor.store.execution(eid).status == 'running'
        f.server.unreachable = True
        f.engine.pyhsl_runner.unavailable_seconds = .05
        until(lambda: any(x[0] == 'monitoring_unavailable' for x in f.sent))
        assert f.engine.run_log_monitor.store.execution(eid).status == 'running'
        f.server.instance_id = 'instance-two'
        f.discover()
        f.server.runs['fixture-run']['status'] = 'outcome_unknown'
        f.server.unreachable = False
        assert finished(f, eid).status == 'failed'
        assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required


def restarts():
    for saved_id, match, age in ((True, True, 600), (False, True, 600),
                                (False, False, 0), (False, False, 600), (False, False, None)):
        with fixture() as f:
            s = schedule(f)
            e = JobExecution('', s.schedule_id, 'running', start_time=datetime.now() - timedelta(minutes=10))
            request = dict(protocol_id=s.protocol_id, protocol_revision=s.protocol_revision,
                parameters=s.parameters, mode=s.mode, request_id=e.execution_id)
            e.pyhsl = dict(request=request, run_id='fixture-run' if saved_id else None,
                attempted_at=(datetime.now() - timedelta(seconds=age or 0)).isoformat()) if age is not None else {}
            assert f.manager.store_job_execution(e)
            from backend.services.scheduling.pre_execution import PreExecutionPipeline
            PreExecutionPipeline(f.manager).prepare(s, e.execution_id)
            if match:
                f.server.runs['fixture-run'] = dict(run_id='fixture-run', status='failed',
                    host_status='closed', error='stopped by user', created_at=datetime.now().isoformat(),
                    configuration={'request_id': e.execution_id})
            # A fresh engine on the same SQLite file is the restart boundary.
            f.engine._running = False
            f.engine._job_queue.put(None)
            f.worker.join(2)
            f.engine = f.new_engine()
            f.engine.pyhsl_runner.client = f.client
            f.engine.pyhsl_runner.poll_seconds = .02
            f.engine._notification_contacts[f.contact.contact_id] = f.contact
            f.engine._load_schedules_from_database()
            assert f.engine.run_log_monitor.restore() == []
            assert f.engine._resolve_dispatch_block_reason(s)
            f.engine._running = True
            f.engine.config.startup_delay_seconds = 0
            f.engine.config.check_interval_seconds = .05
            f.worker = Thread(target=f.engine._job_worker_loop, daemon=True)
            f.worker.start()
            f.engine._scheduler_thread = Thread(target=f.engine._scheduler_loop, daemon=True)
            f.engine._scheduler_thread.start()
            result = finished(f, e.execution_id)
            assert f.prepared == [e.execution_id]
            assert len(f.server.posts) == (1 if age == 0 and not match else 0)
            assert result.status == ('completed' if age == 0 and not match else 'failed')
            assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required == (not match and age != 0)
            sent = len(f.sent)
            time.sleep(1.1)
            assert len(f.sent) == sent and f.engine._job_queue.empty()
    with fixture() as f:
        s = schedule(f)
        f.server.start_code = 409
        with patch.object(f.engine, '_apply_manual_recovery', side_effect=RuntimeError('Interrupted finalization')):
            eid = dispatch(f, s)
            until(lambda: bool(f.server.posts) and not f.engine._owned_execution_ids)
        assert f.engine.run_log_monitor.store.execution(eid).status == 'running'
        time.sleep(1.1)
        assert finished(f, eid).status == 'failed'
        assert len(f.server.posts) == len(f.prepared) == 1
        assert f.storage.get_schedule_by_id(s.schedule_id).recovery_required


def saves_and_guards():
    from backend.api import pyhsl as api
    from backend.services.auth import get_current_user
    from backend.services.hxrun_maintenance import HxRunMaintenanceService
    with fixture() as f:
        app = FastAPI()
        app.include_router(api.router)
        app.include_router(f.api.router)
        app.dependency_overrides[get_current_user] = lambda: {'role': 'user', 'username': 'fixture'}
        with TestClient(app, client=('127.0.0.1', 50000)) as http:
            response = http.post('/api/pyhsl/validate', json=dict(protocol_id='fixture', parameters={}, mode='simulation'))
            assert response.status_code == 200 and response.json()['protocol']['parameters']
            draft = dict(experiment_name='API fixture', runner='pyhsl', protocol_id='fixture', parameters={},
                mode='simulation', schedule_type='once', estimated_duration=10)
            created = http.post('/api/scheduling/create', json=draft)
            assert created.status_code == 200, created.text
            saved = f.storage.get_schedule_by_id(created.json()['data']['schedule_id'])
            assert saved.experiment_path == 'pyhsl:fixture' and saved.protocol_revision == 'revision-one'
            assert http.post('/api/scheduling/create', json={**draft, 'mode': 'real'}).status_code == 400
            assert http.post('/api/pyhsl/validate', json=draft,
                headers={'x-forwarded-for': '198.51.100.5'}).status_code == 403
            app.dependency_overrides[get_current_user] = lambda: {'role': 'viewer'}
            assert http.post('/api/pyhsl/validate', json={}).status_code == 403
        s = schedule(f)
        def update(**changes):
            draft = f.storage.get_schedule_by_id(s.schedule_id)
            return f.api.update_schedule(s.schedule_id, dict(expected_updated_at=draft.updated_at.isoformat(), **changes),
                current_user={'username': 'fixture', 'role': 'user'},
                connection=SimpleNamespace(client_ip='127.0.0.1'), if_unmodified_since=None)
        f.server.revision = 'revision-two'
        update(experiment_name='Edited')
        saved = f.storage.get_schedule_by_id(s.schedule_id)
        assert saved.protocol_id == s.protocol_id and saved.parameters == s.parameters
        assert saved.protocol_revision == 'revision-two' and saved.runner == 'pyhsl'
        for change in ({'mode': 'real'}, {'mode': 'test'}, {'timeout_config': {'action': 'run_cleanup_and_terminate',
                        'cleanup_experiment_name': 'Fixture', 'cleanup_experiment_path': str(f.method)}}):
            try:
                update(**change)
                raise AssertionError('Invalid save accepted')
            except HTTPException as exc:
                assert exc.status_code == 400
        for absent in (False, True):
            f.server.validate_code = 409
            if absent:
                f.app_dir.joinpath('instance.json').unlink()
            try:
                update()
                raise AssertionError('Unavailable/unimported save accepted')
            except HTTPException as exc:
                assert exc.status_code == 400 and TOKEN not in exc.detail
        for reading in (dict(state='running', run={'run_id': 'external'}, reviews=dict(known=False)),
                        dict(state='unknown', run=None, reviews=dict(known=False))):
            with patch.object(f.monitor, 'status', return_value=reading):
                service = HxRunMaintenanceService.__new__(HxRunMaintenanceService)
                for action in (lambda: service.set_state(enabled=True, reason='fixture', actor='fixture'),
                               lambda: f.engine.database_change_guard().__enter__()):
                    try:
                        action()
                        raise AssertionError('Active PyHSL run not protected')
                    except SafetyConflict:
                        pass
        venus = f.schedule(mode='real')
        assert venus.runner == 'venus'
        assert f.engine._simulation_block_reason(venus) is None
        venus.mode = 'simulation'
        assert f.engine._simulation_block_reason(venus)

        # Reopen an old schema containing a real row, not only a newly created default.
        from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase
        old = SQLiteSchedulingDatabase(str(f.root / 'old.db'))
        venus.notification_contacts = []
        assert old.create_schedule(venus)
        with old._get_connection() as conn:
            for name in ('runner', 'protocol_id', 'parameters', 'protocol_revision'):
                conn.execute(f'ALTER TABLE ScheduledExperiments DROP COLUMN {name}')
            for table in ('JobExecutions', 'JobExecutionsArchive'):
                conn.execute(f'ALTER TABLE {table} DROP COLUMN pyhsl')
            conn.commit()
        migrated = SQLiteSchedulingDatabase(str(f.root / 'old.db')).get_schedule_by_id(venus.schedule_id)
        assert migrated.runner == 'venus' and migrated.parameters == {} and migrated.mode == 'simulation'


def run():
    logs = io.StringIO()
    handler = logging.StreamHandler(logs)
    logging.getLogger().addHandler(handler)
    try:
        for check in (outcomes, slow_and_lost, runner_failures, bounded_waits, relay_reads, revision_and_acknowledge, gates_and_following, restarts, saves_and_guards):
            check()
            print(f'PASS {check.__name__}', flush=True)
        assert TOKEN not in logs.getvalue()
    finally:
        logging.getLogger().removeHandler(handler)
    print('PASS scheduled PyHSL boundary check')


if __name__ == '__main__':
    run()
