"""Disposable SQL Server + SQLite + HTTP/executor integration; no robot launch.

Run: .venv/Scripts/python.exe -m backend.e2e.scheduling_lab_check
Uses the existing SQL fixture's UUID databases, never application credentials.
Failure scenarios are recorded in frontend/e2e/scenarios.md.
"""
from contextlib import contextmanager, closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import traceback
from unittest.mock import patch
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.e2e.report_wizard_check import sql_fixture
from backend.services.auth import get_current_user
from backend.services.database import DatabaseService
from backend.services.scheduling.lab_integration import load_lab_integration, LabIntegration, BatchSqliteLab
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase
from backend.services.scheduling.experiment_executor import ExperimentExecutor, ExecutionConfig, ExecutionResult
from backend.services.sqlite_safety import SafetyConflict
from backend.models import ScheduledExperiment, JobExecution
import backend.api.scheduling as api

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'test-output/scheduling-lab-verification'


def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, checks=[], command='.venv/Scripts/python.exe -m backend.e2e.scheduling_lab_check',
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  source_sha256=hashlib.sha256((ROOT/'backend/services/scheduling/lab_integration.py').read_bytes()).hexdigest())
    try:
        with sql_fixture() as fixture, tempfile.TemporaryDirectory(prefix='rc-lab-check-') as temporary:
            root = Path(temporary)
            result['fixture'] = dict(databases=fixture['names'], sqlite='temporary scheduler.db and batches.db',
                                     rows='Experiments 41/42; Batches B-01/B-02; no hardware')
            admin = fixture['admin']
            admin.execute('USE ['+fixture['names'][0]+']')
            admin.execute('CREATE TABLE Experiments(ExperimentID int PRIMARY KEY, UserDefinedID nvarchar(100), Note nvarchar(100), ScheduledToRun bit); INSERT Experiments VALUES(41,\'Previous\',NULL,1),(42,\'Reference\',NULL,0)')
            admin.execute("CREATE PROCEDURE ResetHamiltonTables @ExperimentName nvarchar(100), @TablesJson nvarchar(max)=NULL AS BEGIN RAISERROR('Fixture reset failure',16,1) END")
            native = DatabaseService()
            native._primary_config = dict(driver='{ODBC Driver 17 for SQL Server}', server=fixture['server'],
                                          database=fixture['names'][0], trusted_connection='yes')
            storage = SQLiteSchedulingDatabase(str(root/'scheduler.db'))
            lab = load_lab_integration(storage, native, root)
            manager = SimpleNamespace(lab=lab, sqlite_db=storage, should_block_due_to_abort=lambda _: None)
            app = FastAPI(); app.include_router(api.router)
            app.dependency_overrides[get_current_user] = lambda: {'username': 'fixture', 'role': 'admin'}
            app.add_exception_handler(SafetyConflict, lambda req, exc: JSONResponse(status_code=409, content={'detail': str(exc)}))
            launched = []

            def execute(steps, *, execution_id=None, schedule=None):
                experiment = schedule or ScheduledExperiment('', 'Reference method', str(root/'never-launch.med'), 'once', prerequisites=steps, is_active=False)
                execution = JobExecution(execution_id or str(uuid.uuid4()), experiment.schedule_id, 'running')
                with patch('backend.services.scheduling.experiment_executor.get_scheduling_database_manager', return_value=manager):
                    executor = ExperimentExecutor(ExecutionConfig(hxrun_path=str(root/'not-a-robot.exe')))
                def command(*args):
                    launched.append(execution.execution_id)
                    return ExecutionResult(True, 0, '', '', 0, 'fixture-command')
                executor._execute_hamilton_command = command
                # No real catalogue singleton or filesystem method is involved.
                with patch('backend.services.scheduling.experiment_executor.get_experiment_discovery_service',
                           return_value=SimpleNamespace(db=SimpleNamespace(update_method_usage=lambda _: None))):
                    ok = executor.execute_experiment(experiment, execution)
                return ok, execution

            with patch.object(api, 'get_services', return_value=(None, manager, None)), TestClient(app) as client:
                response = client.get('/api/scheduling/lab/preparation')
                assert response.status_code == 200, response.text
                assert response.json()['choices'][0]['value']=='42'
                ok, execution = execute(['ScheduledToRun','EvoYeastExperiment:42|set'])
                assert ok and len(launched)==1
                assert [tuple(r) for r in admin.execute('SELECT ExperimentID,ScheduledToRun FROM Experiments ORDER BY ExperimentID')]==[(41,False),(42,True)]
                with storage._get_connection() as conn:
                    receipt=dict(conn.execute('SELECT * FROM LabPreparation WHERE execution_id=?',(execution.execution_id,)).fetchone())
                assert receipt['status']=='prepared' and fixture['names'][0] in receipt['identity']
                result['checks'].append('HTTP catalogue + existing form tokens reach executor; SQL flags match reference; identity receipt saved before launch boundary')
                # Restart the lab/storage, not a new in-memory deduplication list.
                manager.lab=load_lab_integration(SQLiteSchedulingDatabase(str(root/'scheduler.db')), native, root)
                assert not execute(['ScheduledToRun','EvoYeastExperiment:42|set'],execution_id=execution.execution_id)[0]
                assert len(launched)==1
                for steps in [['ScheduledToRun'], ['EvoYeastExperiment:41|set','Batch:B-01'], ['Unknown']]:
                    assert not execute(steps)[0]
                assert len(launched)==1
                result['checks'].append('Restart/repeated execution cannot repeat preparation; standalone marker, unknown and foreign steps rejected before SQL/launch')
                for steps in [['EvoYeastExperiment:999|set'], ['EvoYeastExperiment:41|set','ResetHamiltonTables:Fail']]:
                    assert not execute(steps)[0]
                    assert [tuple(r) for r in admin.execute('SELECT ExperimentID,ScheduledToRun FROM Experiments ORDER BY ExperimentID')]==[(41,False),(42,True)]
                assert storage.get_manual_recovery_state().active
                assert len(launched)==1
                result['checks'].append('Missing target and failing stored procedure roll back flags; preparation error blocks launch and requests recovery')
                original=manager.lab.adapter.connect
                @contextmanager
                def offline():
                    raise ConnectionError('Disposable unavailable database')
                    yield
                manager.lab.adapter.connect=offline
                assert client.get('/api/scheduling/lab/preparation').status_code==502
                assert not execute(['EvoYeastExperiment:42|set'])[0]
                assert execute(['EvoYeastExperiment:42|none'])[0]
                manager.lab.adapter.connect=original
                result['checks'].append('Connection failure is unavailable (HTTP 502), not empty choices or successful no-op')

                batch_file=root/'batches.db'
                with closing(sqlite3.connect(batch_file)) as conn, conn:
                    conn.executescript((ROOT/'backend/services/scheduling/examples/batch-schema.sql').read_text('utf-8'))
                (root/'scheduling-lab.json').write_text(json.dumps(dict(adapter='batch-sqlite',sqlite_path='batches.db')),'utf-8')
                try: load_lab_integration(storage,native,root)
                except SafetyConflict: pass
                else: raise AssertionError('Changed lab during recovery')
                # A separate installation with a genuinely different schema.
                batch_storage=SQLiteSchedulingDatabase(str(root/'second-scheduler.db'))
                manager.lab=load_lab_integration(batch_storage,native,root)
                assert client.get('/api/scheduling/lab/preparation').json()['selection_label']=='Batch'
                assert execute(['Batch:B-02'])[0]
                with closing(sqlite3.connect(batch_file)) as conn, conn:
                    assert conn.execute('SELECT batch_code,method FROM InstrumentWorkOrder WHERE slot=1').fetchone()==('B-02','Reference method')
                assert not execute(['EvoYeastExperiment:42|set'])[0]
                assert [tuple(r) for r in admin.execute('SELECT ExperimentID,ScheduledToRun FROM Experiments ORDER BY ExperimentID')]==[(41,False),(42,True)]
                result['checks'].append('Batch HTTP catalogue and executor use different SQLite schema; EvoYeast rows and Hamilton/native connection unchanged')
                saved=ScheduledExperiment('', 'Saved batch', 'fixture.med','once',is_active=False,prerequisites=['Batch:B-02'])
                assert batch_storage.create_schedule(saved)
                second_batch=root/'other-batches.db'
                with closing(sqlite3.connect(second_batch)) as conn, conn:
                    conn.executescript((ROOT/'backend/services/scheduling/examples/batch-schema.sql').read_text('utf-8'))
                (root/'scheduling-lab.json').write_text(json.dumps(dict(adapter='batch-sqlite',sqlite_path='other-batches.db')),'utf-8')
                manager.lab=load_lab_integration(batch_storage,native,root)
                before=len(launched)
                assert not execute(saved.prerequisites,schedule=saved)[0]
                assert len(launched)==before
                with closing(sqlite3.connect(second_batch)) as conn:
                    assert conn.execute('SELECT batch_code FROM InstrumentWorkOrder').fetchone()[0] is None
                result['checks'].append('Inactive saved schedule retains original database binding; same batch code in a different database cannot redirect its launch')
                for busy_kind in ('active', 'pending', 'monitoring'):
                    busy_storage=SQLiteSchedulingDatabase(str(root/f'{busy_kind}.db'))
                    # Bind first, then add live work using the ordinary scheduler store.
                    bound=load_lab_integration(busy_storage,native,root)
                    schedule=ScheduledExperiment('', 'Waiting', 'fixture.med','once',is_active=busy_kind=='active')
                    assert busy_storage.create_schedule(schedule)
                    if busy_kind=='pending':
                        busy_storage.create_job_execution(JobExecution('',schedule.schedule_id,'pending'))
                    if busy_kind=='monitoring':
                        # Reuse the existing monitor persistence schema rather than inventing one.
                        from backend.services.scheduling.run_log_store import RunLogStore
                        from backend.services.scheduling.run_log_monitor import RunObservation
                        from dataclasses import asdict
                        RunLogStore(busy_storage).save(asdict(RunObservation(str(uuid.uuid4()),schedule.schedule_id,schedule.to_dict(),{})))
                    try: LabIntegration(BatchSqliteLab(batch_file),busy_storage,dict(source='different'))
                    except SafetyConflict: pass
                    else: raise AssertionError('Changed configuration with '+busy_kind)
                result['checks'].append('Installation change rejected during active schedule, pending job, unfinished monitoring and recovery')
                empty_root=root/'empty';empty_root.mkdir()
                other_storage=SQLiteSchedulingDatabase(str(root/'empty-scheduler.db'))
                manager.lab=load_lab_integration(other_storage,native,empty_root)
                assert execute([])[0]
                assert execute(['scheduled_to_run','evoYeastExperiment: 42 | SET'])[0]
                result['checks'].append('Explicit no-preparation method remains supported; old registry name/action aliases still select the intended record')
        result['fixtures_removed']=True
        result['passed']=True
    except Exception:
        result['error']=traceback.format_exc()
        raise
    finally:
        (EVIDENCE/'http-results.json').write_text(json.dumps(result,indent=2),'utf-8')
        print(json.dumps(result,indent=2))


if __name__ == '__main__': run()
