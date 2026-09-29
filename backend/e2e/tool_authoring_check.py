"""Prepared Python → form → trial → activation over HTTP and disposable SQL Server.

Run: .venv/Scripts/python.exe -m backend.e2e.tool_authoring_check

Failure cases:
- Importing a prepared Python file never executes it. Reject nonliteral definitions,
  bad inputs or dependency cycles, missing entry functions, unavailable libraries and
  unsafe or duplicate supporting filenames. An ordinary script gets an explicit
  adaptation message. An existing definition is never overwritten silently.
- The same Add flow reaches a real report download and an operation preview without a
  manifest or ZIP. Selecting another experiment clears its plate; forged values fail
  on the server. Relative helper imports work.
- Only the draft owner or a local administrator can configure, try or enable. Report
  mappings cannot use writers. Operation trials use the robot safety gate and roll
  back, create no execution token and never call the execution function.
- Enabling requires a successful trial and review of the current code and connection.
  Replacement, stale draft saves, failed trials, source edits, concurrent updates and
  restarts cannot reuse old readiness.
- Publishing replaces a renamed defining file without losing helpers, rejects a second
  TOOL among supporting files, retires only its draft, survives a lost response or
  repeated submission, and leaves failed updates editable. History (publisher,
  version, note, file changes) is saved atomically with activation.
- Export carries code and definitions, never local credentials or mappings.
"""
from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import zipfile

import openpyxl
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from backend.e2e.report_wizard_check import sql_fixture, ROOT, BASE
from backend.api.database_tools import router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools

REPORT = '''from openpyxl import Workbook
from .helper import heading
TOOL = {'name':'Plate export', 'kind':'report', 'inputs':{
 'experiment':{'label':'Experiment','type':'integer','query':'SELECT id AS value, label FROM dbo.Projects'},
 'plate':{'label':'Plate','type':'integer','query':'SELECT id AS value, label FROM dbo.Plates WHERE project = ?', 'depends_on':['experiment']}}}
def run(context, inputs):
    with context.connection.cursor() as c:
        row = c.execute('SELECT label FROM dbo.Plates WHERE id=? AND project=?', (inputs['plate'], inputs['experiment'])).fetchone()
    b=Workbook(); b.active.append([heading, row[0], inputs['plate']]); b.save(context.output_dir/'plate.xlsx')
    return 'plate.xlsx'
'''


def run():
    evidence = Path(os.environ.get('ROBOTCONTROL_E2E_EVIDENCE', ROOT/'test-output/tool-authoring-verification'))
    evidence.mkdir(parents=True, exist_ok=True)
    result = dict(command='.venv/Scripts/python.exe -m backend.e2e.tool_authoring_check', checks=[], passed=False)
    try:
        with sql_fixture() as fixture, tempfile.TemporaryDirectory(prefix='rc-tool-authoring-') as temp:
            admin = fixture['admin']; writer = fixture['login']+'_writer'
            admin.execute(f"CREATE LOGIN [{writer}] WITH PASSWORD='{fixture['password']}', CHECK_POLICY=OFF")
            admin.execute(f"USE [{fixture['names'][0]}]; CREATE USER [{writer}] FOR LOGIN [{writer}]; GRANT SELECT, DELETE TO [{writer}]")
            admin.execute("CREATE TABLE dbo.DemoItems(id int PRIMARY KEY,label nvarchar(60)); INSERT dbo.DemoItems VALUES(7,'Disposable item')")
            result['fixture'] = dict(databases=fixture['names'], rows='Projects 1/2; Plates 11/12/21; DemoItems 7')
            service = DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', database=object(), guard=nullcontext)
            app = FastAPI(); app.include_router(router)
            def user(request: Request):
                name = request.headers.get('authorization')
                if not name: raise HTTPException(401)
                return dict(username=name, role='user' if name == 'user' else 'admin')
            app.dependency_overrides[get_current_user] = user
            app.dependency_overrides[get_database_tools] = lambda: service
            try:
                with TestClient(app, client=('127.0.0.1',1234), headers={'authorization':'admin'}) as client:
                    def call(method, path, body=None, status=200):
                        r = client.request(method,BASE+path,json=body) if body is not None else client.request(method,BASE+path)
                        assert r.status_code == status, (path,r.status_code,r.text)
                        return r.json() if 'application/json' in r.headers.get('content-type','') else r.content
                    read = dict(id='reader',name='Reader',server=fixture['server'],database=fixture['names'][0],username=fixture['login'],password=fixture['password'],trust_certificate=True)
                    call('POST','/sources',read)
                    call('POST','/sources',dict(read,id='writer',name='Writer',username=writer,access='operation'))
                    files={'report.py':REPORT,'helper.py':"heading = 'Plate'\n"}
                    for bad in ({'x.py':'raise RuntimeError("must not run")'}, {'x.py':REPORT.replace("'Plate export'",'str(42)')},
                                {'../report.py':REPORT}, {'report.py':REPORT+'\nimport missing_library'}, {'report.py':REPORT}):
                        call('POST','/authoring/import',dict(files=bad),400)
                    poisoned = call('POST','/authoring/import',dict(files={'x.py':"TOOL={'name':'No import','kind':'report','connections':[]}\nraise RuntimeError('must not run')\ndef run(context, inputs): pass\n"}))
                    call('POST',f"/drafts/{poisoned['id']}/check",{})
                    call('DELETE',f"/drafts/{poisoned['id']}")
                    result['checks'].append('Static imports/checks do not execute code; unsupported scripts, expressions, helper omissions, unsafe paths and libraries rejected')
                    saved=call('POST','/authoring/import',dict(files=files)); key=saved['id']
                    assert saved['draft']['libraries']==['openpyxl']
                    assert saved['draft']['inputs'][1]['lookup']['parameters']==['experiment']
                    def save(s, **patch):
                        return call('PUT',f"/drafts/{s['id']}",dict(draft={**s['draft'],**patch},revision=s['revision']))
                    saved=save(saved,mappings={'primary':'reader'})
                    call('PUT',f'/drafts/{key}',dict(draft=saved['draft'],revision=1),409)
                    client.headers['authorization']='another-admin';call('GET',f'/drafts/{key}',status=404)
                    client.headers['authorization']='user';call('POST','/authoring/import',dict(files=files),403)
                    client.headers['authorization']='admin'
                    with TestClient(app,client=('10.1.2.3',1234),headers={'authorization':'admin','x-forwarded-for':'127.0.0.1'}) as remote:
                        assert remote.post(BASE+'/authoring/import',json=dict(files=files)).status_code==403
                    call('POST',f'/drafts/{key}/check',{})
                    choices=call('POST',f'/drafts/{key}/choices/plate',dict(inputs={'experiment':1}))
                    assert {r['value'] for r in choices['options']}=={11,12}
                    def trial(s,inputs): return call('POST',f"/drafts/{s['id']}/try",dict(inputs=inputs,revision=s['revision']))
                    def finish(job):
                        deadline=time.monotonic()+40
                        while job['status'] in {'pending','running'}:
                            assert time.monotonic()<deadline,job
                            time.sleep(.1);job=call('GET','/reports/'+job['id'])
                        return job
                    def enable(s,status=200,reviewed=True):
                        review=call('GET',f"/drafts/{s['id']}/review")
                        payload=dict(revision=s['revision'],expected_current=review['current_sha256'],reviewed=reviewed)
                        result=call('POST',f"/drafts/{s['id']}/install",payload,status)
                        if status==200:
                            assert call('POST',f"/drafts/{s['id']}/install",payload)==result
                            assert not any(d['id']==s['id'] for d in call('GET','/drafts'))
                        return result
                    enable(saved,409)
                    forged=finish(trial(saved,{'experiment':2,'plate':11}));assert forged['status']=='error',forged
                    enable(saved,409)
                    job=finish(trial(saved,{'experiment':1,'plate':11}));assert job['status']=='ready',job
                    content=call('GET',f"/reports/{job['id']}/download")
                    assert list(openpyxl.load_workbook(io.BytesIO(content)).active.values)==[('Plate','Same name',11)]
                    (evidence/'plate.xlsx').write_bytes(content)
                    enable(saved,409,reviewed=False)
                    call('POST','/sources',read)  # Same settings, new verified connection revision.
                    enable(saved,409)
                    assert finish(trial(saved,{'experiment':1,'plate':11}))['status']=='ready'
                    enable(saved)
                    installed=call('GET','/catalogue?kind=report');assert any(t['id']=='plate-export' for t in installed)
                    exported=call('GET','/packages/plate-export/export')
                    with zipfile.ZipFile(io.BytesIO(exported)) as z:
                        assert {'manifest.json','report.py','helper.py'}==set(z.namelist())
                        assert fixture['password'].encode() not in b''.join(z.read(n) for n in z.namelist())
                    result['checks'].append('Prepared multi-file report → dependent form → real SQL → Excel → enable/export; ownership, local admin, forged choices, trial and source revision gates')
                    edit=call('POST','/authoring/report/plate-export/edit',{})
                    assert edit['draft']['version']=='1.0.1' and edit['draft']['files']['helper.py']==files['helper.py']
                    parallel=call('POST','/authoring/report/plate-export/edit',{})
                    renamed=call('POST','/authoring/import',dict(files={'renamed.py':REPORT},key=edit['id'],revision=edit['revision'],mode='python'))
                    assert set(renamed['draft']['files'])=={'renamed.py','helper.py'}
                    call('POST','/authoring/import',dict(files={'extra.py':REPORT},key=edit['id'],revision=renamed['revision'],mode='supporting'),400)
                    edit=renamed
                    # Replace the complete source set: rename the entry file and remove a helper.
                    replacement={'export.py':REPORT.replace('from .helper import heading', "heading='Updated'")}
                    edit=call('POST','/authoring/import',dict(files=replacement,key=edit['id'],revision=edit['revision']))
                    enable(edit,409)
                    assert finish(trial(edit,{'experiment':2,'plate':21}))['status']=='ready'
                    edit=save(edit,change_note='Use Updated heading; remove obsolete helper.')
                    enable(edit)
                    with zipfile.ZipFile(io.BytesIO(call('GET','/packages/plate-export/export'))) as z:
                        assert set(z.namelist())=={'manifest.json','export.py'}
                    call('GET',f'/drafts/{key}/review',status=404)
                    call('GET',f"/drafts/{edit['id']}/review",status=404)
                    assert any(d['id']==parallel['id'] for d in call('GET','/drafts'))
                    history=call('GET','/packages/plate-export/history')
                    assert len(history)==2 and history[0]['actor']=='admin'
                    assert history[0]['note']=='Use Updated heading; remove obsolete helper.'
                    assert history[0]['files']['removed']==['helper.py','report.py']
                    assert history[0]['files']['added']==['export.py']
                    client.headers['authorization']='user';call('GET','/packages/plate-export/history',status=403)
                    client.headers['authorization']='admin'
                    call('DELETE',f"/drafts/{parallel['id']}")
                    # ZIP imports remain the alternate route, with the same history.
                    exported=call('GET','/packages/plate-export/export')
                    buffer=io.BytesIO()
                    with zipfile.ZipFile(io.BytesIO(exported)) as source, zipfile.ZipFile(buffer,'w') as target:
                        for name in source.namelist():
                            value=source.read(name)
                            if name=='manifest.json':
                                manifest=json.loads(value);manifest['version']='1.0.2';value=json.dumps(manifest).encode()
                            target.writestr(name,value)
                    current=service.catalogue.index['plate-export']['sha256']
                    response=client.post(BASE+'/packages',files={'file':('report.zip',buffer.getvalue())},data={'expected_current':current,'change_note':'Imported reviewed ZIP.'})
                    assert response.status_code==200,response.text
                    history=call('GET','/packages/plate-export/history')
                    assert len(history)==3 and history[0]['note']=='Imported reviewed ZIP.'
                    assert history[0]['files']['changed']==['manifest.json']
                    response=client.post(BASE+'/packages',files={'file':('report.zip',buffer.getvalue())},data={'expected_current':current})
                    assert response.status_code==409 and call('GET','/packages/plate-export/history')==history
                    result['checks'].append('Edit retains source files and identity; complete replacement renames entry file/removes helper; version, readiness and stale-base checks passed')
                    op=call('POST','/authoring/import',dict(files={'operation.py':(ROOT/'database_packages/examples/operation.py').read_text('utf-8')}))
                    op=save(op,operation_source='writer')
                    call('POST',f"/drafts/{op['id']}/check",{})
                    def blocked(): raise ValueError('Robot is busy')
                    service.guard=blocked
                    call('POST',f"/drafts/{op['id']}/try",dict(inputs={'item_id':7},revision=op['revision']),400)
                    service.guard=nullcontext
                    preview=trial(op,{'item_id':7})
                    assert 'token' not in preview and preview['details']['Rows to delete']==1
                    assert admin.execute('SELECT COUNT(*) FROM dbo.DemoItems').fetchone()[0]==1
                    enable(op)
                    confirmed=call('POST','/operations/delete-demo-item/preview',dict(inputs={'item_id':7}))
                    call('POST','/operations/execute',dict(token=confirmed['token'],confirmation='wrong'),400)
                    execution=call('POST','/operations/execute',dict(token=confirmed['token'],confirmation='7'))
                    assert execution['status']=='succeeded',execution
                    assert call('POST','/operations/execute',dict(token=confirmed['token'],confirmation='7'))==execution
                    assert admin.execute('SELECT COUNT(*) FROM dbo.DemoItems').fetchone()[0]==0
                    result['checks'].append('Operation Python → preview only → enable → separate confirmed real SQL execution; robot busy and duplicate submission protection')
                    # Crash before package-index activation must restore old mappings.
                    service.authoring.begin_activation('plate-export',b'never-activated')
                    service.sources.bind('plate-export',['primary'],{'primary':'reader'})
                    service.authoring.recover_activation()
                    assert not service.authoring.activation.exists()
                    call('DELETE',f"/drafts/{op['id']}",status=404)
                    assert any(t['id']=='delete-demo-item' for t in call('GET','/catalogue?kind=operation'))
                    result['checks'].append('Activation journal recovery and discard preserve installed tools')
                    service.close()
                    service=DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', database=object(), guard=nullcontext)
                    assert call('GET','/packages/plate-export/history')==history
                    assert not call('GET','/drafts')
                    result['checks'].append('Renamed Python replacement preserves helpers; supporting TOOL rejected; publication retires only its draft; notes, file changes and duplicate-publish receipts survive restart')
                    result['workbook_sha256']=hashlib.sha256(content).hexdigest()
                    result['passed']=True
            finally:
                service.close()
                admin.execute('USE master')
                sessions=admin.execute('SELECT session_id FROM sys.dm_exec_sessions WHERE login_name=?',writer).fetchall()
                for session in sessions: admin.execute(f'KILL {int(session[0])}')
                admin.execute(f'DROP LOGIN [{writer}]')
        result['fixtures_removed']=True
    except Exception:
        result['failure']=traceback.format_exc()
    (evidence/'http-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(1)


if __name__=='__main__': run()
