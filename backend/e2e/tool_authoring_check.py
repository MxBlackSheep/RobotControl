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
- A report with no assigned connection refuses instead of falling back. SQL Server
  permissions, not a successful SELECT, decide eligibility: writes and DDL are denied,
  and a write grant in another database of the same login is rejected. Saved passwords
  never appear in replies or the settings file.
- A lookup's order (value_desc) holds across pages, search and the membership check; a
  lookup without one stays alphabetical by label; an unknown order is refused in a
  Python TOOL and in a manifest.
- Only the draft owner or a local administrator can configure, try or enable. Report
  mappings cannot use writers. Operation trials use the robot safety gate and roll
  back, create no execution token and never call the execution function.
- Enabling requires a successful trial and review of the current code and connection.
  Replacement, stale draft saves, failed trials, source edits, concurrent updates and
  restarts cannot reuse old readiness.
- Publishing replaces a renamed defining file without losing helpers, rejects a second
  TOOL among supporting files, retires only its draft, survives a lost response or
  repeated submission, and leaves failed updates editable. Replaying a publish after a
  newer version is installed returns 409 and keeps the newer version and its history.
  History (publisher, version, note, file changes) is saved atomically with activation.
- Export carries code and definitions, never local credentials, mappings or history.
- A published change note becomes the new version's section at the top of CHANGELOG.md:
  the file is created when missing, kept when Replace all files omits it, earlier sections
  survive and a section already written for that version is replaced, never duplicated.
  Download package returns the installed bytes unchanged (schedules pin their sha256),
  including an imported ZIP; import review returns only that version's CHANGELOG section.
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
import pyodbc
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from backend.e2e.sql_server_fixture import sql_fixture, ROOT, BASE
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


ORDERED_TOOL = """import openpyxl
TOOL = {'name': 'Ordered runs', 'kind': 'report', 'inputs': {'run': {
    'type': 'integer', 'query': 'SELECT id AS value, label FROM dbo.Runs', 'order': %r}}}
def run(context, inputs):
    book = openpyxl.Workbook()
    book.active.append([inputs['run']])
    book.save(context.output_dir / 'runs.xlsx')
    return 'runs.xlsx'
"""


def lookup_order(call, client, wait):
    """A package's lookup order holds across pages, search and the membership check."""
    bad = client.post(BASE+'/authoring/import', json=dict(files={'ordered.py': ORDERED_TOOL % 'newest'}))
    assert bad.status_code == 400 and 'order' in bad.text and 'value_desc' in bad.text, bad.text
    imported = call('POST', '/authoring/import', dict(files={'ordered.py': ORDERED_TOOL % 'value_desc'}))
    key = imported['id']
    saved = call('PUT', f'/drafts/{key}', dict(draft={**imported['draft'], 'mappings': {'primary': 'reader'}}, revision=imported['revision']))
    first, second = (call('POST', f'/drafts/{key}/choices/run', dict(inputs={}, page=page)) for page in (1, 2))
    assert [x['value'] for x in first['options']] == list(range(30, 5, -1)) and first['has_more'], first
    assert [x['value'] for x in second['options']] == list(range(5, 0, -1)) and not second['has_more'], second
    label = {n: f'{n * 7 % 31:02d}' for n in range(1, 31)}
    assert all(x['label'] == label[x['value']] for x in first['options'] + second['options'])
    searched = call('POST', f'/drafts/{key}/choices/run', dict(inputs={}, search='1'))
    assert [x['value'] for x in searched['options']] == [n for n in range(30, 0, -1) if '1' in label[n]], searched
    # Membership looks up the selected value directly, so one from the second page still passes.
    job = wait(call('POST', f'/drafts/{key}/try', dict(inputs={'run': 3}, revision=saved['revision'])))
    assert job['status'] == 'ready', job
    missing = wait(call('POST', f'/drafts/{key}/try', dict(inputs={'run': 31}, revision=saved['revision'])))
    assert 'no longer available' in missing['error'], missing
    call('DELETE', f'/drafts/{key}')
    # The manifest route refuses an unknown order before anything is installed.
    lookup = dict(source='primary', query='SELECT id AS value, label FROM dbo.Runs', parameters=[], value_type='integer', order='newest')
    manifest = dict(contract_version=2, id='ordered-runs', name='Ordered runs', version='1.0.0', libraries=[], tools=[dict(
        id='ordered-runs', name='Ordered runs', kind='report', entrypoint='handler:run', sources=['primary'],
        inputs=[dict(name='run', label='Run', type='lookup', lookup=lookup)])])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('manifest.json', json.dumps(manifest))
        package.writestr('handler.py', 'def run(context, inputs):\n    return None\n')
    refused = client.post(BASE+'/packages/inspect', files={'file': ('ordered.zip', archive.getvalue(), 'application/zip')})
    assert refused.status_code == 400 and 'order' in refused.text, refused.text


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
            service = DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', guard=nullcontext)
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
                    # No connection is assigned yet; a report must refuse, never fall back to another database.
                    call('POST','/reports/culture-history',{'inputs':{'experiment_id':42}},409)
                    read = dict(id='reader',name='Reader',server=fixture['server'],database=fixture['names'][0],username=fixture['login'],password=fixture['password'],trust_certificate=True)
                    call('POST','/sources',read)
                    call('POST','/sources',dict(read,id='writer',name='Writer',username=writer,access='operation'))
                    assert fixture['password'] not in json.dumps(call('GET','/sources'))
                    assert fixture['password'] not in service.sources.path.read_text()
                    # SQL Server denies direct writes, whatever query the tool would send.
                    snapshot = service.sources.snapshot('unused', ['primary'], {'primary': 'reader'})
                    for sql in ("INSERT dbo.Projects VALUES (3,'bad')", 'DELETE FROM dbo.Projects',
                                "UPDATE dbo.Projects SET label='bad'", 'CREATE TABLE dbo.Bad (id int)'):
                        with service.sources.open(snapshot['primary']) as conn:
                            try:
                                conn.execute(sql)
                            except pyodbc.Error:
                                conn.rollback()
                            else:
                                raise AssertionError('SQL Server allowed a write')
                    # Permission drift is rechecked on open; a saved connection is not a certificate.
                    admin.execute(f"USE [{fixture['names'][1]}]")
                    admin.execute(f"GRANT UPDATE ON dbo.Plates TO [{fixture['login']}]")
                    try:
                        with service.sources.open(snapshot['primary']):
                            raise AssertionError('Cross-database write grant accepted')
                    except ValueError as exc:
                        assert 'UPDATE' in str(exc)
                    admin.execute(f"REVOKE UPDATE ON dbo.Plates FROM [{fixture['login']}]")
                    admin.execute(f"USE [{fixture['names'][0]}]")
                    result['checks'].append('Unassigned report refused; passwords stored encrypted; INSERT/UPDATE/DELETE/DDL denied by SQL Server; cross-database write grant rejected')
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
                    # Without an order setting, choices stay alphabetical by label ('Other' before 'Yeast Ω').
                    assert [r['value'] for r in call('POST',f'/drafts/{key}/choices/experiment',dict(inputs={}))['options']]==[2,1]
                    assert call('POST',f'/drafts/{key}/choices/experiment',dict(inputs={},search="x' OR 1=1--"))['options']==[]
                    def trial(s,inputs): return call('POST',f"/drafts/{s['id']}/try",dict(inputs=inputs,revision=s['revision']))
                    def finish(job):
                        deadline=time.monotonic()+40
                        while job['status'] in {'pending','running'}:
                            assert time.monotonic()<deadline,job
                            time.sleep(.1);job=call('GET','/reports/'+job['id'])
                        return job
                    published={}  # Each draft's successful install request, to replay after a lost response.
                    def enable(s,status=200,reviewed=True):
                        review=call('GET',f"/drafts/{s['id']}/review")
                        payload=dict(revision=s['revision'],expected_current=review['current_sha256'],reviewed=reviewed)
                        result=call('POST',f"/drafts/{s['id']}/install",payload,status)
                        if status==200:
                            published[s['id']]=payload
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
                    def export():
                        content=call('GET','/packages/plate-export/export')
                        assert content==call('GET','/packages/plate-export/export')
                        assert hashlib.sha256(content).hexdigest()==service.catalogue.index['plate-export']['sha256']
                        return content
                    with zipfile.ZipFile(io.BytesIO(export())) as z:
                        assert set(z.namelist())=={'manifest.json','export.py','CHANGELOG.md'}
                        assert z.read('CHANGELOG.md').decode()=='# Plate export changes\n\n## 1.0.1\n\nUse Updated heading; remove obsolete helper.\n'
                    call('GET',f'/drafts/{key}/review',status=404)
                    call('GET',f"/drafts/{edit['id']}/review",status=404)
                    assert any(d['id']==parallel['id'] for d in call('GET','/drafts'))
                    history=call('GET','/packages/plate-export/history')
                    assert len(history)==2 and history[0]['actor']=='admin'
                    # Replaying the first publish once a newer version is installed must not report success over it.
                    newer=service.catalogue.index['plate-export']['sha256']
                    call('POST',f'/drafts/{key}/install',published[key],409)
                    assert service.catalogue.index['plate-export']['sha256']==newer
                    assert call('GET','/packages/plate-export/history')==history
                    assert history[0]['note']=='Use Updated heading; remove obsolete helper.'
                    assert history[0]['files']['removed']==['helper.py','report.py']
                    assert history[0]['files']['added']==['CHANGELOG.md','export.py']
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
                            if name=='CHANGELOG.md':  # As an author editing the package outside RobotControl.
                                value=value.replace(b'## 1.0.1',b'## 1.0.3 (unreleased)\n\nPlanned.\n\n## 1.0.2\n\nReviewed outside\nRobotControl.\n\n## 1.0.1')
                            target.writestr(name,value)
                    current=service.catalogue.index['plate-export']['sha256']
                    review=client.post(BASE+'/packages/inspect',files={'file':('report.zip',buffer.getvalue())}).json()
                    assert review['changelog']=='Reviewed outside RobotControl.',review
                    response=client.post(BASE+'/packages',files={'file':('report.zip',buffer.getvalue())},data={'expected_current':current,'change_note':'Imported reviewed ZIP.'})
                    assert response.status_code==200,response.text
                    history=call('GET','/packages/plate-export/history')
                    assert len(history)==3 and history[0]['note']=='Imported reviewed ZIP.'
                    assert history[0]['files']['changed']==['CHANGELOG.md','manifest.json']
                    assert export()==buffer.getvalue()
                    response=client.post(BASE+'/packages',files={'file':('report.zip',buffer.getvalue())},data={'expected_current':current})
                    assert response.status_code==409 and call('GET','/packages/plate-export/history')==history
                    # Replace all files without CHANGELOG.md; the author's planned 1.0.3 section is replaced.
                    edit=call('POST','/authoring/report/plate-export/edit',{})
                    assert edit['draft']['version']=='1.0.3' and 'CHANGELOG.md' in edit['draft']['files']
                    edit=call('POST','/authoring/import',dict(files=replacement,key=edit['id'],revision=edit['revision']))
                    assert finish(trial(edit,{'experiment':2,'plate':21}))['status']=='ready'
                    enable(save(edit,change_note='Third release:\n- reviewed in RobotControl'))
                    with zipfile.ZipFile(io.BytesIO(export())) as z:
                        changelog=z.read('CHANGELOG.md').decode()
                    assert changelog==('# Plate export changes\n\n## 1.0.3\n\nThird release:\n- reviewed in RobotControl\n\n'
                                       '## 1.0.2\n\nReviewed outside\nRobotControl.\n\n## 1.0.1\n\nUse Updated heading; remove obsolete helper.\n'),changelog
                    history=call('GET','/packages/plate-export/history')
                    assert len(history)==4 and history[0]['note']=='Third release:\n- reviewed in RobotControl'
                    result['checks'].append('Edit retains source files and identity; complete replacement renames entry file/removes helper; version, readiness and stale-base checks passed')
                    result['checks'].append('Published notes head CHANGELOG.md (created, kept through Replace all, no duplicate version); import review shows its version section; exports are byte-identical to the installed ZIP')
                    lookup_order(call, client, finish)
                    result['checks'].append('Lookup order: value_desc pages 30..6 then 5..1, search and membership in that order; an unknown order is refused in Python and in a manifest')
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
                    service=DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', guard=nullcontext)
                    assert call('GET','/packages/plate-export/history')==history
                    assert not call('GET','/drafts')
                    result['checks'].append('Renamed Python replacement preserves helpers; supporting TOOL rejected; publication retires only its draft; notes, file changes and duplicate-publish receipts survive restart')
                    result['workbook_sha256']=hashlib.sha256(content).hexdigest()
                    result['passed']=True
            finally:
                service.close()
        result['fixtures_removed']=True
    except Exception:
        result['failure']=traceback.format_exc()
    (evidence/'http-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(1)


if __name__=='__main__': run()
