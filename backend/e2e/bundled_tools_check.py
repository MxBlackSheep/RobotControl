"""Convert existing tools over HTTP; compare output with the pinned prior sources.

Run: .venv/Scripts/python.exe -m backend.e2e.bundled_tools_check
Uses the disposable SQL adapter, never the laboratory database or hardware.
"""
import ast
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import traceback

import openpyxl
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.database_tools import router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools
from backend.e2e.database_fixture import DatabaseFixture, configure_fixture_report_sources

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '5e9b4ff'
BASE = '/api/database/tools'


def workbook_signature(content):
    book = openpyxl.load_workbook(io.BytesIO(content))
    return [(sheet.title, sheet.freeze_panes, str(sheet.merged_cells),
             [(key, dim.width, dim.hidden) for key, dim in sheet.column_dimensions.items()],
             [[(cell.value, cell.number_format, str(cell.font), str(cell.fill), str(cell.alignment), str(cell.border))
               for cell in row] for row in sheet]) for sheet in book]


def run():
    evidence = ROOT/'recovery/bundled-tools-verification'
    evidence.mkdir(parents=True, exist_ok=True)
    result = dict(command='.venv/Scripts/python.exe -m backend.e2e.bundled_tools_check', baseline=BASELINE,
                  fixture='backend/e2e/database_fixture.py: disposable SQLite adapter, experiments 42 and 43', checks=[], passed=False)
    try:
        with tempfile.TemporaryDirectory(prefix='rc-bundled-tools-') as temp:
            temp = Path(temp); defaults = temp/'defaults'
            names = {'culture-history':'culture_history.py', 'delete-experiment':'delete_experiment.py'}
            for slug, filename in names.items():
                folder=defaults/slug; folder.mkdir(parents=True)
                for old_name in ('handler.py','manifest.json'):
                    content=subprocess.check_output(['git','show',f'{BASELINE}:database_packages/{slug}/{old_name}'],cwd=ROOT)
                    (folder/old_name).write_bytes(content)
                old=ast.parse((folder/'handler.py').read_text('utf-8'))
                new=ast.parse((ROOT/'database_packages'/slug/filename).read_text('utf-8'))
                functions=lambda tree: {n.name:ast.dump(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
                assert functions(old)==functions(new), 'Calculation/operation functions changed'
            db=DatabaseFixture(temp)
            service=DatabaseTools(temp/'tools',defaults,db,db.guard)
            configure_fixture_report_sources(service)
            app=FastAPI(); app.include_router(router)
            app.dependency_overrides[get_current_user]=lambda:dict(username='fixture-admin',role='admin')
            app.dependency_overrides[get_database_tools]=lambda:service
            try:
                with TestClient(app,client=('127.0.0.1',1234)) as client:
                    def call(method,path,body=None,status=200):
                        r=client.request(method,BASE+path,json=body) if body is not None else client.request(method,BASE+path)
                        assert r.status_code==status,(path,r.status_code,r.text)
                        return r.json() if 'application/json' in r.headers.get('content-type','') else r.content
                    def finish(job):
                        deadline=time.monotonic()+30
                        while job['status'] in {'pending','running'}:
                            assert time.monotonic()<deadline,job
                            time.sleep(.1); job=call('GET','/reports/'+job['id'])
                        assert job['status']=='ready',job
                        return call('GET','/reports/'+job['id']+'/download')
                    before=finish(call('POST','/reports/culture-history',{'inputs':{'experiment_id':42}}))
                    (evidence/'before.xlsx').write_bytes(before)
                    for slug,filename in names.items():
                        kind='report' if slug=='culture-history' else 'operation'
                        source=(ROOT/'database_packages'/slug/filename).read_text('utf-8')
                        draft=call('POST',f'/authoring/{kind}/{slug}/edit',{})
                        draft=call('POST','/authoring/import',dict(files={filename:source},key=draft['id'],revision=draft['revision']))
                        prefix='/drafts/'+draft['id']
                        settings={**draft['draft'],'mappings':{'primary':'primary'}}
                        if kind=='operation': settings['operation_source']='operation'
                        draft=call('PUT',prefix,dict(draft=settings,revision=draft['revision']))
                        call('POST',prefix+'/check',{})
                        options=call('POST',prefix+'/choices/experiment_id',{'inputs':{}})['options']
                        assert {r['value'] for r in options}=={42,43}
                        trial=call('POST',prefix+'/try',dict(inputs={'experiment_id':42 if kind=='report' else 43},revision=draft['revision']))
                        if kind=='report':
                            after=finish(trial); (evidence/'after.xlsx').write_bytes(after)
                            assert workbook_signature(before)==workbook_signature(after)
                            result['checks'].append('Culture history: identical function ASTs and complete workbook values, formatting, widths, merged cells and freeze panes')
                        else:
                            assert 'token' not in trial and trial['details']['ExperimentID']==43
                            with closing(sqlite3.connect(db.path)) as conn:
                                assert conn.execute('SELECT COUNT(*) FROM Experiments WHERE ExperimentID=43').fetchone()[0]==1
                        review=call('GET',prefix+'/review')
                        call('POST',prefix+'/install',dict(revision=draft['revision'],expected_current=review['current_sha256'],reviewed=True))
                        result['checks'].append(f'{slug}: existing identity retained through single-file replacement, choices, trial and enable')
                    preview=call('POST','/operations/delete-experiment/preview',{'inputs':{'experiment_id':43}})
                    call('POST','/operations/execute',dict(token=preview['token'],confirmation='wrong'),400)
                    db.fail_delete=True
                    failed=call('POST','/operations/execute',dict(token=preview['token'],confirmation='43'))
                    assert failed['status']=='error',failed
                    with closing(sqlite3.connect(db.path)) as conn:
                        assert conn.execute('SELECT COUNT(*) FROM Experiments WHERE ExperimentID=43').fetchone()[0]==1
                    db.fail_delete=False
                    preview=call('POST','/operations/delete-experiment/preview',{'inputs':{'experiment_id':43}})
                    executed=call('POST','/operations/execute',dict(token=preview['token'],confirmation='43'))
                    assert executed['status']=='succeeded',executed
                    assert call('POST','/operations/execute',dict(token=preview['token'],confirmation='43'))==executed
                    result['checks'].append('Delete Experiment: preview only, typed confirmation, rollback on procedure failure and duplicate execution protection')
                    for slug, filename in names.items():
                        call('DELETE','/packages/'+slug)
                        fresh=call('POST','/authoring/import',dict(files={filename:(ROOT/'database_packages'/slug/filename).read_text('utf-8')}))
                        assert fresh['draft']['package_id']==slug
                    result['checks'].append('Both single Python files import through Add tool without a manifest or supporting files')
                    result['passed']=True
            finally:
                service.close()
        result['fixtures_removed']=True
    except Exception:
        result['passed']=False
        result['failure']=traceback.format_exc()
    result['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (ROOT/'database_packages/culture-history/culture_history.py',ROOT/'database_packages/delete-experiment/delete_experiment.py')}
    (evidence/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(1)


if __name__=='__main__': run()
