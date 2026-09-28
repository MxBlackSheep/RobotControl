from contextlib import closing
"""HTTP checks for package lifecycle, destructive actions and downloadable reports."""
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import time
from pathlib import Path
from unittest.mock import patch

import openpyxl
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from backend.api.database_tools import router
from backend.api.database import router as legacy_router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools
from backend.e2e.database_fixture import DatabaseFixture, package_zip

ROOT = Path(__file__).resolve().parents[2]
BASE = '/api/database/tools'


def run():
    evidence = ROOT/'recovery/database-verification'
    evidence.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix='rc-database-') as temp:
        database = DatabaseFixture(temp)
        service = DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', database, database.guard)
        from backend.services.scheduling.scheduler_engine import SchedulerEngine
        engine = SchedulerEngine.__new__(SchedulerEngine)
        engine._schedules_lock, engine._jobs_lock = threading.RLock(), threading.RLock()
        engine._owned_execution_ids = set()
        safety = SimpleNamespace(storage_healthy=True, active=False, resume_required=False)
        engine._refresh_manual_recovery_state = lambda **kw: safety
        engine.process_monitor = SimpleNamespace(get_hamilton_processes=lambda: ['fixture'] if database.busy else [])
        engine.run_log_monitor = SimpleNamespace(snapshots=lambda: [])
        engine.db_manager = SimpleNamespace(get_hxrun_maintenance_state=lambda: SimpleNamespace(enabled=False),
            sqlite_db=SimpleNamespace(_connection_lock=threading.RLock()),
            get_schedule_by_id=lambda _: SimpleNamespace(is_active=True, archived=False, recovery_required=False),
            store_job_execution=lambda _: True)
        service.guard = engine.database_change_guard
        app = FastAPI()
        app.include_router(router)
        app.include_router(legacy_router)
        def user(request: Request):
            token = request.headers.get('authorization', '')
            if not token: raise HTTPException(401)
            return dict(username=token, role='user' if token == 'user' else 'admin')
        app.dependency_overrides[get_current_user] = user
        app.dependency_overrides[get_database_tools] = lambda: service
        try:
            with TestClient(app, client=('127.0.0.1', 1234)) as client:
                client.headers['authorization'] = 'admin'
                assert len(client.get(BASE+'/packages').json()) == 2
                assert client.post('/api/database/query', params={'query': 'DELETE FROM Experiments'}).status_code == 410
                client.headers['authorization'] = 'user'
                assert client.get(BASE+'/packages').status_code == 403
                assert client.post(BASE+'/operations/delete-experiment/preview', json={'inputs': {'experiment_id': 43}}).status_code == 403
                client.headers['authorization'] = 'admin'
                with TestClient(app, client=('10.1.2.3', 1234), headers={'authorization':'admin','x-forwarded-for':'127.0.0.1'}) as remote:
                    assert remote.get(BASE+'/packages').status_code == 403
                checks.append('Local administrator checks, forwarded-header denial and retired SQL route: passed')
                # Exercise the author's actual CLI, then upload its output through HTTP.
                project = Path(temp)/'author-report'
                original = ROOT/'database_packages/culture-history/handler.py'
                def helper(*args):
                    return subprocess.run([sys.executable, str(ROOT/'build_scripts/database_package.py'), *map(str,args)],
                        cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
                created = helper('create', project, '--script', original, '--name', 'Culture history', '--id', 'culture-history',
                    '--kind', 'report', '--libraries', 'pandas,openpyxl,pyodbc')
                assert created.returncode == 0, created.stderr
                assert (project/'reference/handler.py').read_bytes() == original.read_bytes()
                assert helper('build', project).returncode != 0  # Unfinished adapter cannot masquerade as a package.
                (project/'handler.py').write_bytes(original.read_bytes())
                built = helper('build', project, '--version', '1.0.2')
                assert built.returncode == 0, built.stderr
                authored = (Path(temp)/'culture-history-1.0.2.zip').read_bytes()
                reviewed = client.post(BASE+'/packages/inspect', files={'file': ('report.zip', authored)}).json()
                assert reviewed['current_version'] == '1.0.1' and reviewed['package']['version'] == '1.0.2'
                fields = dict(expected_current=reviewed['current_sha256'], expected_package='culture-history')
                assert client.post(BASE+'/packages', files={'file': ('report.zip', authored)}, data={**fields,'expected_package':'wrong-package'}).status_code == 409
                assert client.post(BASE+'/packages', files={'file': ('report.zip', authored)}, data=fields).status_code == 200
                assert client.post(BASE+'/packages', files={'file': ('report.zip', authored)}, data=fields).status_code == 409
                # Inspection must not run imports. Activation failure must preserve the working version.
                poisoned = package_zip(ROOT/'database_packages/culture-history', {'version':'1.0.3'},
                    extras={'probe.py': 'raise RuntimeError("inspection executed code")'})
                assert client.post(BASE+'/packages/inspect', files={'file': ('probe.zip', poisoned)}).status_code == 200
                broken = package_zip(ROOT/'database_packages/culture-history', {'version':'1.0.3','tools':[
                    {**reviewed['package']['tools'][0], 'entrypoint':'broken:run'}]},
                    extras={'broken.py':'raise RuntimeError("import failure")\ndef run(context, inputs):\n    pass\n'})
                assert client.post(BASE+'/packages/inspect', files={'file': ('broken.zip', broken)}).status_code == 200
                assert client.post(BASE+'/packages', files={'file': ('broken.zip', broken)}).status_code == 400
                assert client.get(BASE+'/catalogue',params={'kind':'report'}).json()[0]['package_version']=='1.0.2'
                checks.append('Author CLI → non-executing inspection → reviewed update; stale/wrong/failed updates preserve installed code: passed')
                folder = ROOT/'database_packages/delete-experiment'
                def upload(content): return client.post(BASE+'/packages', files={'file': ('package.zip', content, 'application/zip')})
                for content in [package_zip(folder, extras={'../escape.py':'bad'}), package_zip(folder, extras={'binary.exe':'bad'}),
                                package_zip(folder, {'libraries':['not-bundled']}), package_zip(folder, {'contract_version':99}),
                                package_zip(folder, {'id':'collision'})]:
                    assert upload(content).status_code in (400,409)
                assert upload(package_zip(folder, {'version':'1.1.0'})).status_code == 200
                assert client.get(BASE+'/catalogue', params={'kind':'operation'}).json()[0]['package_version'] == '1.1.0'
                with service.catalogue.reserve('delete-experiment','operation'):
                    assert client.delete(BASE+'/packages/delete-experiment').status_code == 409
                    assert upload(package_zip(folder)).status_code == 409
                checks.append('Atomic update, incompatible/unsafe packages, collisions and running-package protection: passed')
                def preview():
                    response = client.post(BASE+'/operations/delete-experiment/preview', json={'inputs': {'experiment_id':43}})
                    assert response.status_code == 200, response.text
                    return response.json()['token']
                def execute(token, confirmation='43'):
                    return client.post(BASE+'/operations/execute', json={'token':token, 'confirmation':confirmation})
                token = preview()
                assert execute(token,'42').status_code == 400
                database.busy=True
                assert execute(token).json()['status']=='error'
                database.busy=False
                safety.active=True
                assert execute(preview()).json()['status']=='error'
                safety.active=False; safety.storage_healthy=False
                assert execute(preview()).json()['status']=='error'
                safety.storage_healthy=True; database.fail_delete=True
                assert execute(preview()).json()['status']=='error'
                with closing(sqlite3.connect(database.path)) as conn, conn: assert conn.execute('SELECT COUNT(*) FROM Experiments WHERE ExperimentID=43').fetchone()[0]==1
                database.fail_delete=False
                token=preview()
                entered, release, launched = threading.Event(), threading.Event(), threading.Event()
                from backend.e2e.database_fixture import Cursor
                original_execute=Cursor.execute
                def hold_delete(cursor, sql, params=()):
                    if sql.startswith('EXEC dbo.DeleteExperiment'):
                        entered.set()
                        assert release.wait(5)
                    return original_execute(cursor,sql,params)
                results=[]
                def launch():
                    with engine.launch_guard(None, SimpleNamespace(schedule_id='fixture', status='pending', start_time=None)):
                        launched.set()
                with patch.object(Cursor,'execute',hold_delete):
                    delete_thread=threading.Thread(target=lambda: results.append(execute(token)))
                    delete_thread.start()
                    try:
                        assert entered.wait(3)
                        launch_thread=threading.Thread(target=launch); launch_thread.start()
                        assert not launched.wait(.15)
                    finally:
                        release.set(); delete_thread.join(5); launch_thread.join(5)
                assert launched.is_set() and results[0].json()['status']=='succeeded'
                checks.append('Real scheduler guard blocks recovery/storage faults and serializes launch with delete: passed')
                assert execute(token).json()['status']=='succeeded'
                assert database.deletes==1
                checks.append('Typed confirmation, idle block, rollback and duplicate submission: passed')
                response=client.post(BASE+'/reports/culture-history', json={'inputs':{'experiment_id':42}})
                assert response.status_code==200, response.text
                job=response.json()
                deadline=time.monotonic()+30
                while job['status'] in {'pending','running'} and time.monotonic()<deadline:
                    time.sleep(.1); job=client.get(BASE+'/reports/'+job['id']).json()
                assert job['status']=='ready', job
                content=client.get(BASE+'/reports/'+job['id']+'/download').content
                (evidence/'culture-history.xlsx').write_bytes(content)
                workbook=openpyxl.load_workbook(io.BytesIO(content)); sheet=workbook.active
                assert sheet.title=='CultureHistory' and sheet.freeze_panes=='D2'
                assert sheet.max_row==6 and sheet.max_column==15, (sheet.max_row,sheet.max_column)
                client.headers['authorization']='other'
                assert client.get(BASE+'/reports/'+job['id']).status_code==404
                assert client.get(BASE+'/reports/'+job['id']+'/download').status_code==404
                client.headers['authorization']='admin'
                service.jobs[job['id']]['expires']=0; service.cleanup()
                assert client.get(BASE+'/reports/'+job['id']).status_code==404
                checks.append('Excel generation, private download and expiry: passed')
                # Converted_OD and converted_od describe one SQL column, not two.
                with closing(sqlite3.connect(database.path)) as connection, connection:
                    connection.execute('ALTER TABLE CulturesHistory ADD COLUMN Converted_OD REAL')
                    connection.execute('UPDATE CulturesHistory SET Converted_OD=0.75')
                job2=client.post(BASE+'/reports/culture-history', json={'inputs':{'experiment_id':42}}).json()
                deadline=time.monotonic()+20
                while job2['status'] in {'pending','running'} and time.monotonic()<deadline:
                    time.sleep(.05); job2=client.get(BASE+'/reports/'+job2['id']).json()
                assert job2['status']=='ready',job2
                sheet2=openpyxl.load_workbook(io.BytesIO(client.get(BASE+'/reports/'+job2['id']+'/download').content)).active
                assert sheet2.cell(2,4).value==0.75
                with closing(sqlite3.connect(database.path)) as connection, connection:
                    connection.execute('ALTER TABLE CulturesHistory DROP COLUMN Converted_OD')
                checks.append('Converted_OD casing aliases select one column and retain its value: passed')
                def report_result():
                    result=client.post(BASE+'/reports/culture-history',json={'inputs':{'experiment_id':42}}).json()
                    deadline=time.monotonic()+20
                    while result['status'] in {'pending','running'}:
                        assert time.monotonic()<deadline
                        time.sleep(.05); result=client.get(BASE+'/reports/'+result['id']).json()
                    return result
                with closing(sqlite3.connect(database.path)) as connection, connection:
                    connection.execute('UPDATE Cultures SET WellID=NULL WHERE CultureID IN (1,3)')
                missing=report_result()
                assert missing['status']=='ready',missing
                missing_sheet=openpyxl.load_workbook(io.BytesIO(client.get(BASE+'/reports/'+missing['id']+'/download').content)).active
                id_columns=[cell.column for cell in missing_sheet[1] if str(cell.value).endswith(' ID')]
                assert {missing_sheet.cell(2,column).value for column in id_columns} == {3,4}
                with closing(sqlite3.connect(database.path)) as connection, connection:
                    connection.execute('INSERT INTO Cultures VALUES (5,20,NULL)')
                ambiguous=report_result()
                assert ambiguous['status']=='error' and 'Plate 20' in ambiguous['error'] and 'missing well positions' in ambiguous['error'],ambiguous
                with closing(sqlite3.connect(database.path)) as connection, connection:
                    connection.execute('DELETE FROM Cultures WHERE CultureID=5')
                    connection.execute("UPDATE Cultures SET WellID='A1' WHERE CultureID IN (1,3)")
                checks.append('Missing well labels retain all selected cultures; ambiguous subset selection gives plate/culture guidance: passed')
                # Hold both actual report workers, checking HTTP admission and package removal.
                release_reports=threading.Event()
                original_function=service.catalogue.function
                def held_function(entry,name):
                    function=original_function(entry,name)
                    def held(context,inputs):
                        assert release_reports.wait(5)
                        return function(context,inputs)
                    return held
                with patch.object(service.catalogue,'function',side_effect=held_function):
                    first=client.post(BASE+'/reports/culture-history',json={'inputs':{'experiment_id':42}}).json()
                    second=client.post(BASE+'/reports/culture-history',json={'inputs':{'experiment_id':42}}).json()
                    try:
                        assert client.post(BASE+'/reports/culture-history',json={'inputs':{'experiment_id':42}}).status_code==429
                        assert client.delete(BASE+'/packages/culture-history').status_code==409
                    finally: release_reports.set()
                    deadline=time.monotonic()+20
                    for running in [first,second]:
                        while client.get(BASE+'/reports/'+running['id']).json()['status'] in {'pending','running'}:
                            assert time.monotonic()<deadline
                            time.sleep(.05)
                checks.append('Two-worker report limit and in-flight removal protection: passed')

                assert client.delete(BASE+'/packages/delete-experiment').status_code==200
            service.close()
            service=DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', database, database.guard)
            assert not service.catalogue.tools('operation')
            checks.append('Removal persists across restart: passed')
            checks.append(compare_upstream(database, evidence))
        finally:
            service.close()
    (evidence/'http-results.json').write_text(json.dumps(checks, indent=2))
    (evidence/'fixture-manifest.json').write_text(json.dumps({'fixture':'backend/e2e/database_fixture.py',
        'fixture_sha256':hashlib.sha256((ROOT/'backend/e2e/database_fixture.py').read_bytes()).hexdigest(),
        'upstream':(ROOT/'database_packages/culture-history/UPSTREAM.txt').read_text()},indent=2))
    print('\n'.join(checks))


def compare_upstream(database, evidence):
    # Execute the unmodified upstream main/calculation functions with only I/O replaced.
    source=(evidence/'upstream.py').read_text(encoding='utf-8-sig')
    namespace={}
    exec('import os\nimport re\nimport sys\nfrom datetime import datetime\nfrom typing import *\nimport pandas as pd\nimport pyodbc\n'+source[source.index('def fetch_df('):source.index('if __name__')], namespace)
    namespace.update(log=lambda *args:None, safe_print=lambda *args:None, connect=lambda:database.get_connection(),
                     OUT_DIR=str(evidence), TS='reference', SCRIPT_NAME='reference')
    with patch('sys.argv',['Data.py','42']): assert namespace['main']()==0
    expected=openpyxl.load_workbook(evidence/'Experiment_42_CultureHistory_reference.xlsx').active
    actual=openpyxl.load_workbook(evidence/'culture-history.xlsx').active
    def cells(sheet): return [[(cell.value,cell.number_format,cell.fill.fgColor.rgb,cell.alignment.horizontal) for cell in row] for row in sheet]
    assert cells(actual)==cells(expected)
    assert str(actual.merged_cells)==str(expected.merged_cells)
    return 'Workbook values, order, formatting and propagation merges match pinned upstream: passed'


if __name__=='__main__': run()
