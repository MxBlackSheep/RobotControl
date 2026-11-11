"""Disposable SQLite + HTTP + worker + HxRun-boundary check; no Hamilton reads or launches.

Run: uv run --locked python backend/e2e/simulation_mode_check.py
Failure cases:
1. Real/global on waits with reason, one email, no HxRun/preparation or running execution.
2. Real/global off/instrument on waits with the instrument reason.
3. Simulation/both off waits without HxRun.
4. Simulation/either on and real/both off run; global on takes precedence.
5. Missing, unreadable, truncated, text, unsupported, missing-key and nonbinary cfg
   are unknown for both modes. Versions 2/3 and all string-length encodings work.
6. Correction releases the same queued execution without restart or repeat mail.
7. A change at the final launch guard refuses Popen, including cleanup methods;
   existing failure handling remains, and preparation may already have committed.
8. Old rows migrate real; mode survives restart and omitted API edits; invalid values fail.
9. Unrelated secret markers never escape through logs/reasons/exceptions or disk copies.
10. Raising or impossible email delivery cannot stop the wait or worker.
11. Deactivation/removal while waiting follows existing cancellation handling.
12. Status/queue reads remain responsive during blocked cfg reads (no scheduler locks).
13. Waiting alerts attach no trace even when another run's trace exists.
Also: cleanup inherits mode, missing HxRun fails normally through the engine gate,
and simulation preparation still runs with its existing inputs.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
import io
import json
import logging
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MARKER = b'PRIVATE-MAIL-PASSWORD-MARKER'


def cfg_bytes(section, key, value, *, version=3, encoding=1):
    def string(value):
        prefix = (struct.pack('<B', len(value)) if encoding == 1 else
                  b'\xff' + struct.pack('<H', len(value)) if encoding == 2 else
                  b'\xff\xff\xff' + struct.pack('<I', len(value)))
        return prefix + value
    entries = [(b'MailPassword', MARKER), (key.encode(), str(value).encode())]
    return (struct.pack('<HHI', version, 0, 1) + string(section.encode()) +
            struct.pack('<HI', 0, len(entries)) +
            b''.join(string(k) + string(v) for k, v in entries) + b'$$valid=1$$')


def sample_config(root, global_value=0, instrument_value=0):
    """Build only disposable cfg files; shared by executor checks using fake HxRun."""
    folder = Path(root) / 'Config'
    folder.mkdir(parents=True, exist_ok=True)
    for filename, section, key, value in (
        ('HxServices.cfg', 'HxServicesGeneralSettings,default', 'SimulationOn', global_value),
        ('ML_STAR.cfg', 'CommandEdit,default', 'SimulateMode', instrument_value),
    ):
        (folder / filename).write_bytes(cfg_bytes(section, key, value))
    executable = Path(root) / 'Bin' / 'not-a-robot.exe'
    executable.parent.mkdir(exist_ok=True)
    return executable


def eventually(predicate, message, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError(message)


def run():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import scheduling as api
    from backend.models import JobExecution, NotificationContact, ScheduledExperiment, TimeoutConfig
    from backend.services.auth import get_current_user
    from backend.services.alert_email import schedule_alert_email
    from backend.services.notifications import SchedulingNotificationService
    from backend.services.scheduling import experiment_executor as ex, scheduler_engine as se
    from backend.services.scheduling.database_manager import SchedulingDatabaseManager
    from backend.services.scheduling.simulation_mode import read_simulation_mode
    from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase
    from backend.services.sqlite_safety import SafetyConflict

    evidence = ROOT / 'test-output/simulation-mode-verification'
    evidence.mkdir(parents=True, exist_ok=True)
    report = dict(passed=False, checks=[], command='uv run --locked python backend/e2e/simulation_mode_check.py',
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                      'backend/models.py', 'backend/api/scheduling.py', 'backend/services/alert_email.py',
                      'backend/services/scheduling/experiment_executor.py',
                      'backend/services/scheduling/scheduler_engine.py',
                      'backend/services/scheduling/sqlite_database.py',
                      'backend/services/scheduling/simulation_mode.py', 'backend/e2e/simulation_mode_check.py')},
                  fixture='Disposable binary cfg files and SQLite; Popen replaced; no Hamilton access')
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    previous_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    try:
        with tempfile.TemporaryDirectory(prefix='rc-simulation-') as temporary, ExitStack() as stack:
            root = Path(temporary)
            executable = sample_config(root)
            config = ex.ExecutionConfig(hxrun_path=str(executable), method_base_path=str(root))
            storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))
            manager = SchedulingDatabaseManager.__new__(SchedulingDatabaseManager)
            manager.sqlite_db = storage
            manager.main_db_service = None
            method = root / 'fixture.med'
            method.write_text('fixture')
            # Construct an old schema from the current schema, with mode removed.
            old = ScheduledExperiment('', 'Old schedule', str(method), 'once', is_active=False)
            assert storage.create_schedule(old)
            with storage._get_connection() as conn:
                conn.execute('ALTER TABLE ScheduledExperiments DROP COLUMN mode')
                conn.execute('DELETE FROM SchemaMigrations WHERE version > 1')
                conn.commit()
            storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))
            manager.sqlite_db = storage
            assert storage.get_schedule_by_id(old.schedule_id).mode == 'real'

            stack.enter_context(patch.object(ex, 'ExecutionConfig', return_value=config))
            stack.enter_context(patch.object(ex, 'get_scheduling_database_manager', return_value=manager))
            stack.enter_context(patch.object(se, 'get_scheduling_database_manager', return_value=manager))
            stack.enter_context(patch.object(se, 'get_hamilton_process_monitor', return_value=SimpleNamespace(
                is_hamilton_running=lambda: False, get_hamilton_processes=lambda: [])))
            stack.enter_context(patch.object(se, 'get_hxrun_maintenance_service', return_value=SimpleNamespace(
                get_state=lambda **_: storage.get_hxrun_maintenance_state())))
            sent = []
            delivered = []
            notification = SchedulingNotificationService.__new__(SchedulingNotificationService)
            notification._hamilton_log_dir = root / 'Logs'
            notification._hamilton_log_dir.mkdir()
            unrelated_trace = notification._hamilton_log_dir / 'unrelated-run.trc'
            unrelated_trace.write_text('Trace from another run')
            from backend.services import storage_manager
            stack.enter_context(patch.object(storage_manager, 'VIDEO_PATH', root / 'videos'))
            video_store = storage_manager.StorageManager()
            stack.enter_context(patch.object(storage_manager, 'get_storage_manager', return_value=video_store))
            def deliver(*args, **kwargs):
                delivered.append(kwargs)
                return True
            notification.email = SimpleNamespace(send=deliver)
            mail_raises = False
            def send(*args, **kwargs):
                sent.append(kwargs)
                if mail_raises:
                    raise RuntimeError('Fixture mail unavailable')
                if kwargs['trigger'] == 'simulation_mode_mismatch':
                    return notification.schedule_alert(*args, **kwargs)
                return SimpleNamespace(sent=True, delivery_status='sent', error=None, recipients=['fixture@example.invalid'],
                                       attachments=[], subject='Fixture alert', body=kwargs['context'].get('note', ''), attachment_notes=[])
            stack.enter_context(patch.object(se, 'get_notification_service', return_value=SimpleNamespace(schedule_alert=send)))
            engine = se.SchedulerEngine(se.SchedulerConfig(check_interval_seconds=1))
            # Keep this check out of Hamilton SQL and trace folders while exercising real persistence.
            engine.run_log_monitor = SimpleNamespace(snapshots=lambda: [], snapshot=lambda _: None,
                prepare=lambda *args: None, launched=lambda *args: None, check=lambda _: SimpleNamespace(run_state='Complete'),
                process_finished=lambda _: None, finish=lambda _: None)
            contact = storage.create_notification_contact(NotificationContact('', 'Fixture', 'fixture@example.invalid'))
            engine._notification_contacts[contact.contact_id] = contact
            launched, prepared = [], []
            process = SimpleNamespace(pid=123, returncode=0, communicate=lambda: ('', ''))
            def popen(*args, **kwargs):
                launched.append(args[0])
                return process
            popen_mock = stack.enter_context(patch.object(ex.subprocess, 'Popen', side_effect=popen))
            stack.enter_context(patch.object(ex, 'get_experiment_discovery_service', return_value=SimpleNamespace(
                db=SimpleNamespace(update_method_usage=lambda _: None))))
            original_prepare = ex.PreExecutionPipeline.prepare
            change_after_prepare = False
            def prepare(pipeline, schedule, execution_id):
                prepared.append(execution_id)
                result = original_prepare(pipeline, schedule, execution_id)
                if change_after_prepare:
                    sample_config(root, 1, 0)
                return result
            stack.enter_context(patch.object(ex.PreExecutionPipeline, 'prepare', prepare))

            def schedule(mode='real', contacts=True, **kwargs):
                value = ScheduledExperiment('', 'Fixture', str(method), 'once', mode=mode,
                    notification_contacts=[contact.contact_id] if contacts else [], **kwargs)
                assert storage.create_schedule(value)
                engine._active_schedules[value.schedule_id] = value
                return value

            # Real HTTP contract, persisted SQL and optimistic concurrency.
            app = FastAPI()
            app.include_router(api.router)
            app.dependency_overrides[get_current_user] = lambda: dict(username='admin', role='admin')
            stack.enter_context(patch.object(api, 'get_services', return_value=(engine, manager, None)))
            stack.enter_context(patch.object(api, 'log_action'))
            with TestClient(app, client=('127.0.0.1', 1)) as client:
                body = dict(experiment_name='API fixture', experiment_path=str(method), schedule_type='once', estimated_duration=5, is_active=False)
                def create(extra):
                    return client.post('/api/scheduling/create', json={**body, **extra})
                def read(identity):
                    response = client.get('/api/scheduling/list?active_only=false')
                    assert response.status_code == 200, response.text
                    return next(row for row in response.json()['data'] if row['schedule_id'] == identity)
                real = create({})
                assert real.status_code == 200, real.text
                identity = real.json()['data']['schedule_id']
                assert read(identity)['mode'] == 'real'
                simulation = create(dict(mode='simulation'))
                assert simulation.status_code == 200, simulation.text
                identity = simulation.json()['data']['schedule_id']
                def update(extra):
                    return client.put(f'/api/scheduling/{identity}', json={**extra, 'expected_updated_at': read(identity)['updated_at']})
                assert update(dict(estimated_duration=9)).status_code == 200
                assert read(identity)['mode'] == 'simulation'
                assert SQLiteSchedulingDatabase(str(root / 'scheduler.db')).get_schedule_by_id(identity).mode == 'simulation'
                assert update(dict(mode='real')).status_code == 200 and read(identity)['mode'] == 'real'
                for bad in ('test', 'Simulation', '', None, True, 1, [], {}):
                    assert create(dict(mode=bad)).status_code == 400, bad
                    assert update(dict(mode=bad)).status_code == 400, bad
                assert read(identity)['mode'] == 'real'
            report['checks'].append('8: migration, API create/default/edit/validation and restart persistence')

            global_file, instrument_file = root / 'Config/HxServices.cfg', root / 'Config/ML_STAR.cfg'
            real, simulation = schedule(), schedule('simulation')
            for global_value, instrument_value, real_ok, simulation_ok in ((0, 0, True, False), (1, 0, False, True), (0, 1, False, True), (1, 1, False, True)):
                sample_config(root, global_value, instrument_value)
                for value, allowed in ((real, real_ok), (simulation, simulation_ok)):
                    assert (engine._resolve_dispatch_block_reason(value) is None) == allowed
                    before = len(launched)
                    item = JobExecution('', value.schedule_id, 'pending')
                    executor = ex.ExperimentExecutor(engine.run_log_monitor, engine.launch_guard, config)
                    if allowed:
                        assert executor.execute_experiment(value, item)
                        assert len(launched) == before + 1
                    else:
                        try:
                            with engine.launch_guard(value, item):
                                raise AssertionError('Mismatched mode passed launch guard')
                        except SafetyConflict:
                            pass
                        assert len(launched) == before
            launched.clear()
            prepared.clear()
            sample_config(root, 0, 1)
            assert engine._resolve_dispatch_block_reason(real) == "The instrument's Simulation setting is on; this schedule is real."
            sample_config(root, 1, 0)
            instrument_file.unlink()  # Global on decides without needing the instrument setting.
            assert read_simulation_mode(executable).state == 'on'
            for version in (2, 3):
                for encoding in (1, 2, 4):
                    global_file.write_bytes(cfg_bytes('HxServicesGeneralSettings,default', 'SimulationOn', 1, version=version, encoding=encoding))
                    assert read_simulation_mode(executable).state == 'on'
            report['checks'].append('2–4: precedence, mismatch reasons, all matching combinations and binary encodings')

            for target, section, key in ((global_file, 'HxServicesGeneralSettings,default', 'SimulationOn'), (instrument_file, 'CommandEdit,default', 'SimulateMode')):
                for bad in (None, b'\x03', b'HxCfgFile' + MARKER,
                            cfg_bytes(section, key, 0, version=4), cfg_bytes(section, 'MissingKey', 0),
                            cfg_bytes(section, key, MARKER.decode()), cfg_bytes(section, key, 2)):
                    sample_config(root)
                    if bad is None:
                        target.unlink()
                    else:
                        target.write_bytes(bad)
                    for value in (real, simulation):
                        reason = engine._resolve_dispatch_block_reason(value)
                        assert reason.startswith('VENUS Simulation Mode could not be read:'), reason
                        assert MARKER.decode() not in reason
                sample_config(root)
                original_read = Path.read_bytes
                def unreadable(path):
                    if path == target:
                        raise PermissionError(MARKER.decode())
                    return original_read(path)
                with patch.object(Path, 'read_bytes', unreadable):
                    for value in (real, simulation):
                        assert engine._resolve_dispatch_block_reason(value).startswith('VENUS Simulation Mode could not be read:')
            report['checks'].append('5: every malformed/unavailable setting blocks both modes without revealing contents')

            # Actual worker wait: execution deliberately not yet stored (NotificationLog has no execution FK).
            sample_config(root, 1, 0)
            waiting = schedule()
            execution = JobExecution('', waiting.schedule_id, 'pending')
            assert notification._locate_trc_file(waiting, execution) == unrelated_trace
            engine._queued_backlog.add(waiting.schedule_id)
            engine._job_queue.put((waiting, execution))
            engine._running = True
            worker = threading.Thread(target=engine._job_worker_loop, daemon=True)
            worker.start()
            try:
                eventually(lambda: engine._get_queue_waiting_reason(waiting.schedule_id), 'Worker did not wait')
                eventually(lambda: len(sent) == 1, 'No wait notification')
                assert execution.status == 'pending' and not prepared and not launched
                assert storage.notification_log_exists(execution.execution_id, 'simulation_mode_mismatch')
                eventually(lambda: len(delivered) == 1, 'Waiting alert was not delivered')
                assert not delivered[0]['attachments'], 'Waiting alert attached another run trace'
                with storage._get_connection() as conn:
                    assert not conn.execute('SELECT 1 FROM JobExecutions WHERE execution_id=?', (execution.execution_id,)).fetchone()
                time.sleep(1.1)
                assert len(sent) == 1 and worker.is_alive()
                sample_config(root, 0, 1)
                eventually(lambda: "instrument's" in (engine._get_queue_waiting_reason(waiting.schedule_id) or ''), 'Instrument wait not shown')
                assert len(sent) == 1
                sample_config(root)
                eventually(lambda: any(row['execution_id'] == execution.execution_id and row['status'] == 'completed'
                                       for row in storage.get_execution_history(waiting.schedule_id)),
                           'Corrected run did not finish')
                assert len(sent) == 1 and prepared == [execution.execution_id] and len(launched) == 1
                with storage._get_connection() as conn:
                    assert conn.execute('SELECT status FROM JobExecutions WHERE execution_id=?', (execution.execution_id,)).fetchone()[0] == 'completed'
                report['checks'].append('1,6: pending wait, one email before execution persistence, no preparation/launch until correction; same run completes')
                report['checks'].append('13: waiting alert delivered without an unrelated existing trace')

                for mode, contacts, raising, remove in (('real', True, True, False), ('simulation', False, False, False), ('real', True, False, True)):
                    sample_config(root, 0 if mode == 'simulation' else 1, 0)
                    mail_raises = raising
                    value = schedule(mode, contacts=contacts)
                    item = JobExecution('', value.schedule_id, 'pending')
                    engine._queued_backlog.add(value.schedule_id)
                    engine._job_queue.put((value, item))
                    eventually(lambda: engine._get_queue_waiting_reason(value.schedule_id), 'Mail failure stopped wait')
                    if contacts:
                        eventually(lambda: storage.notification_log_exists(item.execution_id, 'simulation_mode_mismatch'), 'No delivery attempt logged')
                    time.sleep(1.1)
                    assert worker.is_alive() and item.status == 'pending'
                    if remove:
                        assert storage.delete_schedule(value.schedule_id)
                        engine.invalidate_schedule(value.schedule_id)
                    else:
                        value.is_active = False
                        assert storage.update_schedule(value)
                    eventually(lambda: item.status == 'cancelled', 'Waiting job did not cancel')
                report['checks'].append('10,11: failed/no-contact email keeps worker alive; deactivation/removal cancels')
            finally:
                engine._running = False
                worker.join(8)
                assert not worker.is_alive(), 'Worker leaked'
            mail_raises = False

            # A slow filesystem must not hold either scheduler lock or block status snapshots.
            engine._running = True
            sample_config(root)
            entered, release = threading.Event(), threading.Event()
            original_read = Path.read_bytes
            def slow_read(path):
                if path == global_file:
                    entered.set()
                    assert release.wait(5), 'Slow-read fixture was not released'
                return original_read(path)
            values = []
            with patch.object(Path, 'read_bytes', slow_read):
                thread = threading.Thread(target=lambda: values.append(engine._wait_until_dispatch_ready(real.schedule_id)))
                thread.start()
                try:
                    assert entered.wait(3)
                    status = threading.Thread(target=lambda: (engine.get_status(), engine.get_runtime_queue_status()))
                    status.start()
                    status.join(1)
                    assert not status.is_alive(), 'Status blocked on cfg read'
                finally:
                    release.set()
                    thread.join(5)
            engine._running = False
            assert values == [real]
            report['checks'].append('12: status and queue remain responsive while cfg read is blocked')

            sample_config(root)
            value = schedule()
            item = JobExecution('', value.schedule_id, 'pending')
            assert engine._resolve_dispatch_block_reason(value) is None
            sample_config(root, 1, 0)
            try:
                with engine.launch_guard(value, item):
                    raise AssertionError('Guard accepted a mode change')
            except SafetyConflict as exc:
                assert str(exc) == engine._resolve_dispatch_block_reason(value)
            before = len(launched)
            sample_config(root)
            change_after_prepare = True
            engine._execute_job(value, item)
            change_after_prepare = False
            assert item.status == 'failed' and len(launched) == before
            with storage._get_connection() as conn:
                assert conn.execute('SELECT status FROM LabPreparation WHERE execution_id=?', (item.execution_id,)).fetchone()[0] == 'prepared'
            report['checks'].append('7: final guard refuses changed setting; existing caller finalizes failed after preparation')

            for mode, global_value in (('real', 0), ('simulation', 1)):
                sample_config(root, global_value, 0)
                cleanup = schedule(mode, start_time=datetime.now() - timedelta(minutes=5), timeout_config=TimeoutConfig(
                    timeout_minutes=1, action='run_cleanup_and_terminate', cleanup_experiment_path=str(method), cleanup_experiment_name='Cleanup'))
                item = JobExecution('', cleanup.schedule_id, 'pending')
                before, before_prepared = len(launched), len(prepared)
                engine._execute_job(cleanup, item)
                assert item.status == 'completed' and len(launched) == before + 1 and len(prepared) == before_prepared
                cleanup.is_active = True
                assert storage.update_schedule(cleanup)
                refused = JobExecution('', cleanup.schedule_id, 'pending')
                before = len(launched)
                engine.run_log_monitor.prepare = lambda *args: sample_config(root, 1 - global_value, 0)
                engine._execute_job(cleanup, refused)
                engine.run_log_monitor.prepare = lambda *args: None
                assert refused.status == 'failed' and len(launched) == before and len(prepared) == before_prepared
            sample_config(root)
            value = schedule()
            with patch.object(ex.subprocess, 'Popen', side_effect=FileNotFoundError):
                missing = JobExecution('', value.schedule_id, 'pending')
                engine._execute_job(value, missing)
                assert missing.status == 'failed' and 'HxRun.exe not found' in missing.error_message
            report['checks'].append('Launch paths: real/simulation cleanup inherits mode and skips preparation; missing HxRun fails normally')

            # Database steps receive the same inputs for simulation; no mode is passed.
            sample_config(root, 1, 0)
            calls = []
            tools = SimpleNamespace(preparation_state=lambda _: 'ready', prepare_for_run=lambda saved, run: calls.append((saved, run)))
            value = schedule('simulation', preparation=dict(tool_id='fixture', inputs=dict(experiment_id=42)))
            with patch('backend.services.database_tools.get_database_tools', return_value=tools):
                item = JobExecution('', value.schedule_id, 'pending')
                engine._execute_job(value, item)
            assert item.status == 'completed' and len(calls) == 1 and 'mode' not in calls[0][1]
            report['checks'].append('Simulation database step still executes with the existing run context (no mode)')

            # The new trigger must render the waiting reason, without requiring a started run.
            email = schedule_alert_email(trigger='simulation_mode_mismatch', experiment='Fixture', schedule_id=value.schedule_id,
                execution_id=item.execution_id, start_time=None, end_time=None, estimated_duration=None,
                recorded_minutes=None, attached=[], clip_attached=False, now=datetime.now(),
                context={'note': 'VENUS is in Simulation Mode; this schedule is real.'})
            assert 'VENUS is in Simulation Mode' in email.text()
            assert MARKER.decode() not in output.getvalue() + json.dumps(report) + email.text() + email.html()
            for path in root.rglob('*'):
                if path.is_file() and path not in (global_file, instrument_file):
                    assert MARKER not in path.read_bytes(), f'Secret copied to {path.name}'
            report['checks'].append('9: planted unrelated password absent from logs, reasons, email, report and every non-cfg file')
            report['passed'] = True
    finally:
        logging.getLogger().removeHandler(handler)
        logging.getLogger().setLevel(previous_level)
        (evidence / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        (evidence / 'check.log').write_text(output.getvalue(), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
