"""Disposable SQL Server + SQLite + HTTP/executor check of the EvoYeast preparation package
and of schedules saved with the retired built-in adapter's tokens. No robot launch.

Run: .venv/Scripts/python.exe -m backend.e2e.scheduling_lab_check
Installs database_packages/evoyeast-experiment into a temporary catalogue, with a read-only
login for experiment choices and a separate writer login, in the SQL fixture's UUID database.

Failure cases:
- The package does not mark exactly the chosen experiment ScheduledToRun, or does not run
  dbo.ResetHamiltonTables with the method name and listed tables in the schedule's saved
  order (reset first when the old tokens had it first), in one host-committed transaction.
- An experiment duplicated, or deleted after the schedule was saved, a failing reset
  procedure, or tables listed with reset off leaves any flag changed or launches the run.
- A schedule saved with adapter tokens runs without them: it must show Needs review with
  the tokens prefilled as the package step, refuse the run before any write (also after a
  restart), keep the tokens when a user edits timing, and change only when a local
  administrator saves the step; the saved step then runs the same SQL.
- Tokens the package cannot express (batch example, unknown, ScheduledToRun without an ID,
  two selections, or a schedule that already has a database step) lose the step silently
  or are prefilled with a guess. A no-op selection (|none) blocks a run that wrote nothing.
- A client adds or edits adapter tokens through the schedule API.
Supervised acceptance with a real method and the lab's ResetHamiltonTables is separate.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import traceback
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/scheduling-lab-verification'
TOOL = 'evoyeast-experiment'
OLD_FORM = ['ResetHamiltonTables:Runtime', 'ScheduledToRun', 'EvoYeastExperiment:42|set']


def run():
    from backend.e2e.report_wizard_check import sql_fixture
    from backend.api import scheduling as api
    from backend.models import JobExecution, ScheduledExperiment
    from backend.services.auth import get_current_user
    from backend.services.database_tools import DatabaseTools
    from backend.services.report_sources import ReportSource
    from backend.services.scheduling.experiment_executor import ExecutionConfig, ExecutionResult, ExperimentExecutor
    from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase
    from backend.services.sqlite_safety import SafetyConflict

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    package = ROOT / 'database_packages/evoyeast-experiment/evoyeast_experiment.py'
    result = dict(passed=False, checks=[], command='.venv/Scripts/python.exe -m backend.e2e.scheduling_lab_check',
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  package_sha256=hashlib.sha256(package.read_bytes()).hexdigest())
    try:
        with sql_fixture() as fixture, tempfile.TemporaryDirectory(prefix='rc-lab-check-') as temporary:
            root = Path(temporary)
            database, admin = fixture['names'][0], fixture['admin']
            writer, writer_password = fixture['login'] + '_writer', secrets.token_urlsafe(32)
            admin.execute(f"CREATE LOGIN [{writer}] WITH PASSWORD='{writer_password}', CHECK_POLICY=OFF")
            admin.execute(f'USE [{database}]')
            # No primary key: a duplicated ID must be refused by the package's own lock query.
            admin.execute("CREATE TABLE dbo.Experiments(ExperimentID int NOT NULL, UserDefinedID nvarchar(100), Note nvarchar(100), ScheduledToRun bit)")
            admin.execute("INSERT dbo.Experiments VALUES(41,'Previous',NULL,1),(42,'Reference',NULL,0),(43,'Copied',NULL,0),(43,'Copied',NULL,0),(44,'Deleted later',NULL,0)")
            admin.execute('CREATE TABLE dbo.ResetLog(ExperimentName nvarchar(200), TablesJson nvarchar(max) NULL, FlaggedAtCall int NULL)')
            # Records which experiment was flagged when the reset ran, which shows the step order.
            admin.execute("CREATE PROCEDURE dbo.ResetHamiltonTables @ExperimentName nvarchar(200), @TablesJson nvarchar(max) = NULL AS BEGIN "
                          "IF @TablesJson LIKE '%Fail%' BEGIN RAISERROR('Fixture reset failure', 16, 1); RETURN; END; "
                          "INSERT dbo.ResetLog VALUES(@ExperimentName, @TablesJson, (SELECT MIN(ExperimentID) FROM dbo.Experiments WHERE ScheduledToRun = 1)) END")
            admin.execute(f'CREATE USER [{writer}] FOR LOGIN [{writer}]')
            admin.execute(f'GRANT SELECT, UPDATE ON dbo.Experiments TO [{writer}]')
            admin.execute(f'GRANT EXECUTE ON dbo.ResetHamiltonTables TO [{writer}]')
            admin.execute('USE master')
            flags = lambda: sorted(tuple(r) for r in admin.execute(f'SELECT ExperimentID, ScheduledToRun FROM [{database}].dbo.Experiments'))
            resets = lambda: [tuple(r) for r in admin.execute(f'SELECT ExperimentName, TablesJson, FlaggedAtCall FROM [{database}].dbo.ResetLog')]
            result['fixture'] = dict(database=database, reader=fixture['login'], writer=writer, sqlite='temporary scheduler.db',
                                     rows='Experiments 41 (flagged), 42, 43 twice, 44; no hardware')

            tools = DatabaseTools(root / 'tools', ROOT / 'database_packages', database=object())
            storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))
            tools.catalogue.in_use = lambda package_id: [s.experiment_name for s in storage.get_schedules(active_only=True, archived_only=False)
                                                         if (s.preparation or {}).get('package_id') == package_id]
            common = dict(server=fixture['server'], database=database, trust_certificate=True)
            tools.sources.save(ReportSource(id='reader', name='EvoYeast reader', username=fixture['login'], password=fixture['password'], access='read', **common))
            tools.sources.save(ReportSource(id='writer', name='EvoYeast writer', username=writer, password=writer_password, access='operation', **common))
            tools.sources.bind(TOOL, ['primary'], {'primary': 'reader'})
            tools.sources.bind_operation(TOOL, 'writer')

            manager = SimpleNamespace(sqlite_db=storage, should_block_due_to_abort=lambda _: None)
            scheduler = SimpleNamespace(add_schedule=storage.create_schedule, get_schedule=storage.get_schedule_by_id, _schedules_lock=threading.RLock(),
                                        update_schedule=lambda s, expected_updated_at=None: storage.update_schedule(s, expected_updated_at=expected_updated_at),
                                        invalidate_schedule=lambda _: None)
            method = root / 'Reference method.med'
            method.write_text('fixture')
            launched = []

            def execute(schedule_id):
                schedule = storage.get_schedule_by_id(schedule_id)
                execution = JobExecution(str(uuid.uuid4()), schedule.schedule_id, 'running')
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
                    row = conn.execute('SELECT status, message FROM LabPreparation WHERE execution_id=?', (execution_id,)).fetchone()
                return dict(row) if row else None

            def saved(tokens, name='Reference method', **extra):
                schedule = ScheduledExperiment('', name, str(method), 'interval', interval_hours=6, prerequisites=tokens, is_active=True, **extra)
                assert storage.create_schedule(schedule)
                return schedule.schedule_id

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

                def read(schedule_id):
                    return client.get(f'/api/scheduling/{schedule_id}').json()['data']

                def update(schedule_id, changes, role='admin'):
                    return client.put(f'/api/scheduling/{schedule_id}', json={**changes, 'expected_updated_at': read(schedule_id)['updated_at']},
                                      headers={'authorization': role})

                def create(inputs, name='Reference method'):
                    body = dict(experiment_name=name, experiment_path=str(method), schedule_type='once', estimated_duration=5, is_active=True,
                                preparation=dict(tool_id=TOOL, inputs=inputs))
                    response = client.post('/api/scheduling/create', json=body)
                    assert response.status_code == 200, response.text
                    return response.json()['data']['schedule_id']

                # A schedule saved by the old form, with a reset saved before the selection.
                old = saved(OLD_FORM)
                view = read(old)
                assert view['preparation_state'] == 'needs_review' and view['preparation'] is None
                suggestion = view['legacy_preparation']['suggestion']
                assert suggestion == dict(tool_id=TOOL, inputs=dict(experiment_id=42, reset_tables=True, table_list='Runtime', reset_first=True)), suggestion
                ok, blocked = execute(old)
                assert not ok and not launched and receipt(blocked) is None and flags() == [(41, True), (42, False), (43, False), (43, False), (44, False)]
                storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))  # Restart: derived again, never rewritten.
                manager.sqlite_db = storage
                assert update(old, {'estimated_duration': 9}, role='user').status_code == 200
                assert update(old, {'preparation': suggestion}, role='user').status_code == 403
                assert storage.get_schedule_by_id(old).prerequisites == OLD_FORM and read(old)['preparation_state'] == 'needs_review'
                assert not execute(old)[0] and not launched and not resets()
                assert update(old, {'prerequisites': ['EvoYeastExperiment:41|set']}).status_code == 400
                body = dict(experiment_name='Tokens', experiment_path=str(method), schedule_type='once', estimated_duration=5, prerequisites=['ScheduledToRun'])
                assert client.post('/api/scheduling/create', json=body).status_code == 400
                result['checks'].append('Old-form schedule is Needs review with its tokens prefilled in saved order; the run is refused before any write, also after a restart; a user edit keeps the tokens; clients cannot add or edit tokens')

                response = update(old, {'preparation': suggestion})
                assert response.status_code == 200, response.text
                migrated = storage.get_schedule_by_id(old)
                assert migrated.prerequisites == [] and migrated.preparation['inputs'] == suggestion['inputs'] and read(old)['preparation_state'] == 'ready'
                assert migrated.preparation['source_id'] == 'writer' and migrated.preparation['database'] == database
                ok, first = execute(old)
                assert ok and launched == [first] and receipt(first)['status'] == 'prepared', receipt(first)
                assert flags() == [(41, False), (42, True), (43, False), (43, False), (44, False)]
                assert resets() == [('Reference method', '["Runtime"]', 41)], resets()  # Reset ran while 41 was still flagged.
                selected_first = create(dict(experiment_id=41, reset_tables=True), name='Select first')
                ok, second = execute(selected_first)
                assert ok and launched[-1] == second and flags()[:2] == [(41, True), (42, False)]
                assert resets()[-1] == ('Select first', None, 41) and 'Experiment 41 marked' in receipt(second)['message']
                result['checks'].append('After an administrator saves the prefilled step it is pinned, the tokens are cleared and the package clears all flags, sets one and resets tables with the method name in the saved order; select-then-reset and reset-all also verified')

                failing = {'duplicate': create(dict(experiment_id=43)),
                           'deleted': create(dict(experiment_id=44)),
                           'reset fails': create(dict(experiment_id=42, reset_tables=True, table_list='Fail')),
                           'tables without reset': create(dict(experiment_id=42, table_list='Runtime'))}
                admin.execute(f'DELETE FROM [{database}].dbo.Experiments WHERE ExperimentID = 44')
                before, messages = flags(), {}
                for case, schedule_id in failing.items():
                    ok, execution_id = execute(schedule_id)
                    assert not ok and execution_id not in launched, case
                    assert flags() == before and len(resets()) == 2, case
                    messages[case] = receipt(execution_id)
                    assert messages[case]['status'] == 'failed' and storage.get_schedule_by_id(schedule_id).recovery_required, (case, messages[case])
                assert 'missing or not unique' in messages['duplicate']['message'], messages
                assert 'Fixture reset failure' in messages['reset fails']['message'], messages
                result['failure_messages'] = {case: value['message'] for case, value in messages.items()}
                result['checks'].append('Duplicated or deleted experiment, failing reset procedure and tables listed with reset off roll back every flag, never launch and request recovery')

                expressed = saved(['scheduled_to_run', 'evoYeastExperiment: 42 | SET'], name='Alias form')
                assert read(expressed)['legacy_preparation']['suggestion'] == dict(tool_id=TOOL, inputs=dict(experiment_id=42))
                with_step = create(dict(experiment_id=42), name='Has a step')
                with storage._get_connection() as conn:
                    conn.execute('UPDATE ScheduledExperiments SET prerequisites=? WHERE schedule_id=?', (json.dumps(['EvoYeastExperiment:41|set']), with_step))
                    conn.commit()
                for schedule_id in [saved(['Batch:B-01']), saved(['Unknown']), saved(['ScheduledToRun']),
                                    saved(['EvoYeastExperiment:41|set', 'EvoYeastExperiment:42|set']), with_step]:
                    view = read(schedule_id)
                    assert view['preparation_state'] == 'needs_review' and view['legacy_preparation']['suggestion'] is None, view
                    assert 'cannot be carried over' in view['legacy_preparation']['message']
                    count, rows = len(launched), flags()
                    assert not execute(schedule_id)[0] and len(launched) == count and flags() == rows
                noop = saved(['EvoYeastExperiment:42|none'], name='No selection')
                assert 'legacy_preparation' not in read(noop)
                rows = flags()
                assert execute(noop)[0] and flags() == rows
                result['checks'].append('Old registry aliases still prefill the intended experiment; batch, unknown, marker-only, double selection and token+step schedules are Needs review without a guess and refused; a no-op selection still runs and writes nothing')
        result['fixtures_removed'] = True
        result['passed'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        (EVIDENCE / 'http-results.json').write_text(json.dumps(result, indent=2), 'utf-8')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
