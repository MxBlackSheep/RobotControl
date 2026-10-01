"""Disposable SQL Server + SQLite + HTTP/executor check of a schedule's database preparation step.

Run: .venv/Scripts/python.exe -m backend.e2e.preparation_step_check
Uses the report-wizard SQL fixture (disposable login and databases on .\\HAMILTON) and a fixture
package whose `mode` input makes prepare() succeed, raise, hang or crash. No robot launch: the
executor's Hamilton command is replaced, and no application data is used.

Failure cases:
- A user without the admin role attaches, changes or removes a step (uploaded Python writing
  unattended); editing timing loses the step.
- A step that raises leaves its writes (no rollback), or commits part of them itself and then
  fails while the recovery note says nothing was committed; the run launches anyway, or the
  schedule is not marked for recovery. An unreadable stored step is reported as uninstalled.
- A hung or crashed step blocks the launch path, or is reported as failed instead of unknown;
  a retry or restart repeats a step that may have written.
- A package update, or rebinding its connection, silently changes what an armed schedule
  runs; a changed package runs before an administrator saves the schedule again.
- Preparation takes the manual-operation guard (scheduler locks) while it runs.
"""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import traceback
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import zipfile

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/preparation-step-verification'
PACKAGE = 'prep-fixture'
SOURCE = '''import os
import time


def prepare(context, inputs):
    cursor = context.connection.cursor()
    cursor.execute("INSERT INTO dbo.PrepLog(ExecutionID, Mode) VALUES (?, ?)", context.run.execution_id, inputs["mode"])
    if inputs["mode"] == "raise":
        raise RuntimeError("Fixture preparation failure")
    if inputs["mode"] == "sleep":
        time.sleep(600)
    if inputs["mode"] == "crash":
        os._exit(3)
    if inputs["mode"] == "commit":
        cursor.commit()  # Refused: the host commits; the step then fails with nothing committed.
    return {"message": "Logged " + inputs["mode"] + " for " + context.run.experiment_name}
'''


def package(version):
    manifest = dict(contract_version=2, id=PACKAGE, name='Preparation fixture', version=version, libraries=[],
                    tools=[dict(id=PACKAGE, name='Log the run', kind='preparation', entrypoint='prepare:prepare', sources=[],
                                inputs=[dict(name='mode', label='Mode', type='choice', choices=['ok', 'raise', 'sleep', 'crash', 'commit'])])])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('prepare.py', SOURCE + f'\n# version {version}\n')
    return buffer.getvalue()


def run():
    from backend.e2e.report_wizard_check import sql_fixture
    from backend.api import scheduling as api
    from backend.models import JobExecution, ScheduledExperiment
    from backend.services.auth import get_current_user
    from backend.services.database import DatabaseService
    from backend.services.database_tools import DatabaseTools
    from backend.services.report_sources import ReportSource
    from backend.services.scheduling.experiment_executor import ExecutionConfig, ExecutionResult, ExperimentExecutor
    from backend.services.scheduling.lab_integration import load_lab_integration
    from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase
    from backend.services.sqlite_safety import SafetyConflict

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, checks=[], command='.venv/Scripts/python.exe -m backend.e2e.preparation_step_check',
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
    try:
        with sql_fixture() as fixture, tempfile.TemporaryDirectory(prefix='rc-preparation-check-') as temporary:
            root = Path(temporary)
            database = fixture['names'][0]
            admin = fixture['admin']
            admin.execute(f'USE [{database}]')
            admin.execute('CREATE TABLE dbo.PrepLog(ExecutionID nvarchar(64) PRIMARY KEY, Mode nvarchar(20))')
            admin.execute(f"GRANT INSERT, SELECT ON dbo.PrepLog TO [{fixture['login']}]")
            admin.execute('CREATE TABLE Experiments(ExperimentID int PRIMARY KEY, UserDefinedID nvarchar(100), Note nvarchar(100), ScheduledToRun bit)')
            admin.execute('USE master')
            logged = lambda: {row[0]: row[1] for row in admin.execute(f'SELECT ExecutionID, Mode FROM [{database}].dbo.PrepLog')}
            result['fixture'] = dict(database=database, login=fixture['login'], sqlite='temporary scheduler.db')

            (root / 'no-defaults').mkdir()
            tools = DatabaseTools(root / 'tools', root / 'no-defaults', database=object())
            def guard():
                raise AssertionError('Preparation must not take the manual-operation guard (scheduler locks)')
            tools.guard = guard
            storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))
            tools.catalogue.in_use = lambda package_id: [s.experiment_name for s in storage.get_schedules(active_only=True, archived_only=False)
                                                         if (s.preparation or {}).get('package_id') == package_id]
            tools.sources.save(ReportSource(id='writer', name='Disposable writer', server=fixture['server'], database=database,
                                            username=fixture['login'], password=fixture['password'], trust_certificate=True, access='operation'))
            tools.catalogue.install(package('1.0.0'))
            tools.sources.bind_operation(PACKAGE, 'writer')

            native = DatabaseService()
            native._primary_config = dict(driver='{ODBC Driver 17 for SQL Server}', server=fixture['server'],
                                          database=database, trusted_connection='yes')
            manager = SimpleNamespace(lab=load_lab_integration(storage, native, root), sqlite_db=storage,
                                      should_block_due_to_abort=lambda _: None)
            scheduler = SimpleNamespace(add_schedule=storage.create_schedule, get_schedule=storage.get_schedule_by_id, _schedules_lock=threading.RLock(),
                                        update_schedule=lambda s, expected_updated_at=None: storage.update_schedule(s, expected_updated_at=expected_updated_at),
                                        invalidate_schedule=lambda _: None)
            method = root / 'fixture.med'
            method.write_text('fixture')
            launched = []

            def execute(schedule_id, execution_id=None):
                schedule = storage.get_schedule_by_id(schedule_id)
                execution = JobExecution(execution_id or str(uuid.uuid4()), schedule.schedule_id, 'running')
                with patch('backend.services.scheduling.experiment_executor.get_scheduling_database_manager', return_value=manager):
                    executor = ExperimentExecutor(ExecutionConfig(hxrun_path=str(root / 'not-a-robot.exe')))
                def command(*args):
                    launched.append(execution.execution_id)
                    return ExecutionResult(True, 0, '', '', 0, 'fixture-command')
                executor._execute_hamilton_command = command
                with patch('backend.services.scheduling.experiment_executor.get_experiment_discovery_service',
                           return_value=SimpleNamespace(db=SimpleNamespace(update_method_usage=lambda _: None))):
                    ok = executor.execute_experiment(schedule, execution)
                return ok, execution.execution_id

            def receipt(execution_id):
                with storage._get_connection() as conn:
                    row = conn.execute('SELECT status, message, package FROM LabPreparation WHERE execution_id=?', (execution_id,)).fetchone()
                return dict(row) if row else None

            app = FastAPI()
            app.include_router(api.router)
            def user(request: Request):
                name = request.headers.get('authorization', 'admin')
                return {'username': name, 'role': 'user' if name == 'user' else 'admin'}
            app.dependency_overrides[get_current_user] = user
            app.add_exception_handler(SafetyConflict, lambda req, exc: JSONResponse(status_code=409, content={'detail': str(exc)}))

            with patch.object(api, 'get_services', return_value=(scheduler, storage, None)), \
                 patch('backend.services.database_tools.get_database_tools', return_value=tools), \
                 TestClient(app, client=('127.0.0.1', 1)) as client:

                def create(mode, role='admin', name='Prepared run'):
                    body = dict(experiment_name=name, experiment_path=str(method), schedule_type='once', estimated_duration=5, is_active=True,
                                preparation=dict(tool_id=PACKAGE, inputs=dict(mode=mode)))
                    return client.post('/api/scheduling/create', json=body, headers={'authorization': role})

                def update(schedule_id, changes, role='admin'):
                    current = client.get(f'/api/scheduling/{schedule_id}').json()['data']
                    return client.put(f'/api/scheduling/{schedule_id}', json={**changes, 'expected_updated_at': current['updated_at']},
                                      headers={'authorization': role})

                # Permissions: attaching uploaded Python needs an administrator.
                denied = create('ok', role='user')
                assert denied.status_code == 403, denied.text
                response = create('ok')
                assert response.status_code == 200, response.text
                schedule_id = response.json()['data']['schedule_id']
                saved = storage.get_schedule_by_id(schedule_id).preparation
                assert saved['sha256'] == tools.catalogue.index[PACKAGE]['sha256'] and saved['source_id'] == 'writer'
                assert client.get(f'/api/scheduling/{schedule_id}').json()['data']['preparation_state'] == 'ready'
                assert update(schedule_id, {'estimated_duration': 7}, role='user').status_code == 200
                assert storage.get_schedule_by_id(schedule_id).preparation == saved
                assert update(schedule_id, {'preparation': dict(tool_id=PACKAGE, inputs=dict(mode='ok'))}, role='user').status_code == 200
                assert update(schedule_id, {'preparation': dict(tool_id=PACKAGE, inputs=dict(mode='raise'))}, role='user').status_code == 403
                assert update(schedule_id, {'preparation': None}, role='user').status_code == 403
                assert storage.get_schedule_by_id(schedule_id).preparation == saved
                result['checks'].append('Only an administrator attaches, changes or removes a step; the server pins package hash and connection; a user editing timing or resubmitting it unchanged keeps it')

                ok, first = execute(schedule_id)
                assert ok and launched == [first] and logged().get(first) == 'ok'
                assert receipt(first)['status'] == 'prepared' and 'Logged ok for Prepared run' in receipt(first)['message']
                assert json.loads(receipt(first)['package'])['sha256'] == saved['sha256']
                assert not execute(schedule_id, execution_id=first)[0] and launched == [first] and len(logged()) == 1
                result['checks'].append('Step commits in its own process before launch with run context; receipt records package and message; the same execution never repeats it')

                failures = {}
                for mode in ('raise', 'commit', 'sleep', 'crash'):
                    failing = create(mode, name=f'Prepared {mode}').json()['data']['schedule_id']
                    with patch('backend.services.database_tools.PREPARATION_TIMEOUT_SECONDS', 8):
                        ok, execution_id = execute(failing)
                    failures[mode] = execution_id
                    assert not ok and execution_id not in launched, mode
                    assert execution_id not in logged(), f'{mode}: uncommitted write remained'
                    assert receipt(execution_id)['status'] == ('failed' if mode in ('raise', 'commit') else 'unknown'), (mode, receipt(execution_id))
                    assert storage.get_schedule_by_id(failing).recovery_required, mode
                    assert not execute(failing, execution_id=execution_id)[0] and execution_id not in launched
                assert 'Fixture preparation failure' in receipt(failures['raise'])['message']
                assert 'The host commits a preparation step' in receipt(failures['commit'])['message']
                assert 'two-minute limit' in receipt(failures['sleep'])['message']
                result['checks'].append('Raise, or an attempted commit by the step, rolls back (failed); hang is stopped at the deadline and crash ends the process (unknown); none launches, all request recovery, retries never repeat')

                # An armed schedule keeps the package and connection it was saved with.
                tools.sources.save(ReportSource(id='other-writer', name='Other writer', server=fixture['server'], database=database,
                                                username=fixture['login'], password=fixture['password'], trust_certificate=True, access='operation'))
                for change in (lambda: tools.catalogue.install(package('1.0.1')), lambda: tools.catalogue.remove(PACKAGE),
                               lambda: tools.catalogue.refuse_if_scheduled(PACKAGE)):
                    try:
                        change()
                    except Exception as exc:
                        assert getattr(exc, 'status', None) == 409 and 'Prepared run' in str(exc), exc
                    else:
                        raise AssertionError('Changed a package used by an active schedule')
                for schedule in storage.get_schedules(active_only=True, archived_only=False):
                    schedule.is_active = False
                    assert storage.update_schedule(schedule)
                tools.catalogue.install(package('1.0.1'))
                assert client.get(f'/api/scheduling/{schedule_id}').json()['data']['preparation_state'] == 'needs_review'
                rows = len(logged())
                ok, blocked = execute(schedule_id)
                assert not ok and blocked not in launched and receipt(blocked) is None and len(logged()) == rows
                assert update(schedule_id, {'preparation': dict(tool_id=PACKAGE, inputs=dict(mode='ok'))}, role='user').status_code == 200
                assert client.get(f'/api/scheduling/{schedule_id}').json()['data']['preparation_state'] == 'needs_review'
                assert update(schedule_id, {'preparation': dict(tool_id=PACKAGE, inputs=dict(mode='ok'))}).status_code == 200
                assert client.get(f'/api/scheduling/{schedule_id}').json()['data']['preparation_state'] == 'ready'
                tools.sources.bind_operation(PACKAGE, 'other-writer')
                assert client.get(f'/api/scheduling/{schedule_id}').json()['data']['preparation_state'] == 'needs_review'
                ok, rebound = execute(schedule_id)
                assert not ok and rebound not in launched and receipt(rebound) is None
                result['checks'].append('Update, removal and rebinding refused while a schedule is active; a changed package or connection blocks dispatch before any write until an administrator saves again')
        result['fixtures_removed'] = True
        result['passed'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        (EVIDENCE / 'results.json').write_text(json.dumps(result, indent=2), 'utf-8')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
