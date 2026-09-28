"""Focused HTTP/SQL workflow. Only UUID-named disposable SQL objects are changed.
Run: .venv/Scripts/python.exe -m backend.e2e.database_workspace_check
"""
from contextlib import nullcontext
import io
import json
from pathlib import Path
import tempfile
import time
import traceback
import zipfile
import os
import openpyxl
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from backend.e2e.report_wizard_check import sql_fixture, ROOT, BASE
from backend.api.database_tools import router
from backend.api.database import router as viewer_router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools

EVIDENCE = Path(os.environ.get('ROBOTCONTROL_E2E_EVIDENCE', str(ROOT / 'recovery/database-workspace-verification')))


def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, command='.venv/Scripts/python.exe -m backend.e2e.database_workspace_check', checks=[])
    try:
        with sql_fixture() as fixture, tempfile.TemporaryDirectory(prefix='rc-workspace-') as temp:
            admin = fixture['admin']; new_login = fixture['login'] + '_reader'
            result['fixture'] = dict(databases=fixture['names'], new_account=new_login)
            admin.execute('USE [' + fixture['names'][0] + ']')
            admin.execute('CREATE SCHEMA other')
            admin.execute("CREATE TABLE other.Projects (id int PRIMARY KEY, label nvarchar(80)); INSERT other.Projects VALUES (7, 'Other schema')")
            admin.execute('CREATE PROCEDURE other.PreviewOnly AS SELECT 1 AS value')
            admin.execute('CREATE PROCEDURE dbo.sp_helpdiagrams AS SELECT 1 AS value')
            admin.execute('GRANT EXECUTE ON dbo.sp_helpdiagrams TO public')
            admin.execute('USE master')
            service = DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', database=object(), guard=nullcontext)
            app = FastAPI(); app.include_router(router); app.include_router(viewer_router)
            def user(request: Request):
                name = request.headers.get('authorization')
                if not name: raise HTTPException(401)
                return dict(username=name, role='user' if name == 'user' else 'admin')
            app.dependency_overrides[get_current_user] = user
            app.dependency_overrides[get_database_tools] = lambda: service
            try:
                with TestClient(app, client=('127.0.0.1', 1234), headers={'authorization':'admin'}) as client:
                    def call(method, path, body=None, status=200):
                        r = client.request(method, path, json=body) if body is not None else client.request(method, path)
                        assert r.status_code == status, (path, r.status_code, r.text)
                        return r.json() if 'application/json' in r.headers.get('content-type','') else r.content
                    source = dict(id='lab-a', name='Lab A', server=fixture['server'], database=fixture['names'][0],
                                  username=new_login, trust_certificate=True)
                    # Verification fails after commit, with a pooled reader session.
                    admin.execute('USE ['+fixture['names'][0]+']; GRANT INSERT ON dbo.Projects TO public; USE master')
                    failed_login = new_login+'_verification'
                    failed_review = call('POST',BASE+'/sources/access/review',dict(source,id='failed-verification',username=failed_login))
                    failure = call('POST',BASE+'/sources/access/create',dict(token=failed_review['token'],windows_auth=True),400)
                    assert 'INSERT' in failure['detail'] and 'check/remove' not in failure['detail'], failure
                    assert not admin.execute('SELECT 1 FROM sys.server_principals WHERE name=?', failed_login).fetchone()
                    admin.execute('USE ['+fixture['names'][0]+']; REVOKE INSERT ON dbo.Projects FROM public; USE master')
                    review = call('POST', BASE+'/sources/access/review', source)
                    assert review['account']==new_login and 'SELECT' in review['sql'] and 'DENY EXECUTE' in review['sql']
                    assert not admin.execute('SELECT name FROM sys.server_principals WHERE name=?',new_login).fetchone()
                    client.headers['authorization']='other-admin'
                    call('POST',BASE+'/sources/access/create',dict(token=review['token'],windows_auth=True),409)
                    client.headers['authorization']='admin'
                    call('POST',BASE+'/sources/access/create',dict(token=review['token'],windows_auth=True))
                    call('POST',BASE+'/sources/access/create',dict(token=review['token'],windows_auth=True),409)
                    created = service.sources.get('lab-a')
                    assert 'password' not in json.dumps(call('GET',BASE+'/viewer-sources'))
                    with service.sources.open(created) as conn:
                        assert conn.execute('SELECT COUNT(*) FROM dbo.Projects').fetchone()[0] == 2
                        for sql in ["INSERT dbo.Projects VALUES(99,'bad')", 'DELETE dbo.Projects', "UPDATE dbo.Projects SET label='bad'", 'CREATE TABLE dbo.Bad(id int)', 'EXEC dbo.sp_helpdiagrams']:
                            try: conn.execute(sql)
                            except Exception: conn.rollback()
                            else: raise AssertionError('New identity can write')
                    inherited = call('POST',BASE+'/sources',dict(source,id='inherited',username=fixture['login'],password=fixture['password']),400)
                    assert 'EXECUTE' in inherited['detail'] and 'sp_helpdiagrams' in inherited['detail'], inherited
                    admin.execute('USE ['+fixture['names'][0]+']; REVOKE EXECUTE ON dbo.sp_helpdiagrams FROM public; USE master')
                    result['checks'].append('New reader denies inherited public EXECUTE; existing reader with EXECUTE rejected; failed verification removes only newly created login and pooled session')
                    collision = call('POST',BASE+'/sources/access/review',dict(source,id='collision',username=fixture['login']))
                    conflict = call('POST',BASE+'/sources/access/create',dict(token=collision['token'],windows_auth=True),400)
                    assert 'already exists' in conflict['detail'] and 'RobotControl_ReadOnly' in conflict['detail']
                    assert admin.execute('SELECT name FROM sys.server_principals WHERE name=?', fixture['login']).fetchone()
                    denied = call('POST',BASE+'/sources/access/review',dict(source,id='denied',username=new_login+'_denied'))
                    error = call('POST',BASE+'/sources/access/create',dict(token=denied['token'],username=fixture['login'],password=fixture['password']),400)
                    assert 'lacks permission' in error['detail'] and 'create login' in error['detail'], error
                    assert fixture['password'] not in json.dumps(error)
                    assert not admin.execute('SELECT name FROM sys.server_principals WHERE name=?',new_login+'_denied').fetchone()
                    signin = call('POST',BASE+'/sources/access/review',dict(source,id='signin',username=new_login+'_signin'))
                    error = call('POST',BASE+'/sources/access/create',dict(token=signin['token'],username=fixture['login'],password='disposable-wrong-password'),400)
                    assert 'rejected the administrator sign-in' in error['detail'], error
                    assert 'disposable-wrong-password' not in json.dumps(error)
                    bad_login = new_login + '_bad'
                    bad = call('POST',BASE+'/sources/access/review',dict(source,id='bad-database',username=bad_login,database=bad_login))
                    missing = call('POST',BASE+'/sources/access/create',dict(token=bad['token'],windows_auth=True),400)
                    assert 'Cannot open database' in missing['detail'], missing
                    assert not admin.execute('SELECT name FROM sys.server_principals WHERE name=?',bad_login).fetchone()
                    result['checks'].append('Existing login never modified; failed database grant transaction removes new login')
                    result['checks'].append('Duplicate name, insufficient SQL authority, rejected sign-in and missing database have distinct actionable HTTP errors; passwords are absent')
                    result['checks'].append('Reviewed create-account HTTP flow; no creation on review; owner/replay enforced; SELECT works and writes/DDL denied')
                    call('POST',BASE+'/sources',dict(source,id='lab-b',name='Lab B',database=fixture['names'][1],username=fixture['login'],password=fixture['password']))
                    a=call('GET','/api/database/tables?source_id=lab-a')['data']['tables']
                    b=call('GET','/api/database/tables?source_id=lab-b')['data']['tables']
                    assert '[other].[Projects]' in a and '[other].[Projects]' not in b
                    rows=call('GET','/api/database/tables/%5Bother%5D.%5BProjects%5D?source_id=lab-a')['data']['rows']
                    assert rows[0]['id']==7
                    procedures=call('GET','/api/database/stored-procedures?source_id=lab-a')['data']['procedures']
                    assert any(p['name']=='[other].[PreviewOnly]' and 'SELECT 1' in p['definition'] for p in procedures)
                    call('GET','/api/database/tables',status=422)
                    client.headers['authorization']='user'
                    call('GET','/api/database/tables?source_id=lab-b')
                    call('POST',BASE+'/sources',source,403)
                    client.headers['authorization']='admin'
                    with TestClient(app, client=('10.2.3.4',5),headers={'authorization':'admin','x-forwarded-for':'127.0.0.1'}) as remote:
                        assert remote.post(BASE+'/sources/access/review',json=source).status_code==403
                    result['checks'].append('Two databases and duplicate schema table names browsed; procedure text visible; no native database needed; missing target blocked')
                    # Use a disposable login with write grants in the disposable DB only.
                    admin.execute('USE [' + fixture['names'][1] + ']')
                    admin.execute('GRANT DELETE TO ['+fixture['login']+']')
                    writer=dict(source,id='writer',name='Disposable writer',database=fixture['names'][1],username=fixture['login'],password=fixture['password'],access='operation')
                    call('POST',BASE+'/sources',writer)
                    call('GET','/api/database/tables?source_id=writer',status=409)
                    call('PUT',BASE+'/packages/culture-history/sources',dict(mappings={'primary':'writer'}),400)
                    manifest=dict(contract_version=1,id='remove-project',name='Remove project',version='1.0.0',libraries=[],tools=[dict(id='remove-project',name='Remove project',kind='operation',preview='handler:preview',entrypoint='handler:run',confirmation_field='id',inputs=[dict(name='id',label='Project',type='integer',required=True)])])
                    handler = "def preview(context, inputs):\n    row=context.connection.execute('SELECT label FROM dbo.Projects WHERE id=?', inputs['id']).fetchone()\n    return dict(summary='Remove project', details=dict(label=row[0] if row else None))\ndef run(context, inputs):\n    context.connection.execute('DELETE dbo.Projects WHERE id=?', inputs['id'])\n    if inputs['id']==2: raise ValueError('Fixture rollback')\n    return dict(message='Removed')\n"
                    output=io.BytesIO()
                    with zipfile.ZipFile(output,'w') as z:
                        z.writestr('manifest.json',json.dumps(manifest));z.writestr('handler.py',handler)
                    assert client.post(BASE+'/packages',files={'file':('operation.zip',output.getvalue())}).status_code==200
                    call('PUT',BASE+'/packages/remove-project/sources',dict(mappings={},operation_source='writer'))
                    def preview(i): return call('POST',BASE+'/operations/remove-project/preview',dict(inputs={'id':i}))
                    def execute(p,i): return call('POST',BASE+'/operations/execute',dict(token=p['token'],confirmation=str(i)))
                    p=preview(1); assert fixture['names'][1] in p['target']
                    call('POST',BASE+'/sources',writer)
                    assert execute(p,1)['status']=='error'
                    p=preview(2); assert execute(p,2)['status']=='error'
                    p=preview(1); assert execute(p,1)['status']=='succeeded'; assert execute(p,1)['status']=='succeeded'
                    assert admin.execute('SELECT id FROM dbo.Projects').fetchone()[0]==2
                    result['checks'].append('Writer cannot be used by viewers/reports; changed configuration blocks confirmation; rollback and duplicate execution protected')
                    script="import pandas\ndef helper():\n    from openpyxl.styles import Font\n    import missing_library\n    __import__('math')\nraise RuntimeError('MUST NOT EXECUTE')\n"
                    scan=call('POST',BASE+'/authoring/inspect-python',{'source':script})
                    assert scan['available']==['openpyxl','pandas'] and scan['unavailable']==['missing_library'] and scan['undetermined'] and not scan['compatible']
                    call('POST',BASE+'/authoring/inspect-python',{'source':'def ('},400)
                    example="from openpyxl import Workbook\ndef run(context, inputs):\n    b=Workbook(); b.active.append([inputs['label'],42]); b.save(context.output_dir/'example.xlsx'); return 'example.xlsx'\n"
                    assert call('POST',BASE+'/authoring/inspect-python',{'source':example})['compatible']
                    draft=dict(name='Example',package_id='example',sources=[],mappings={},handler=example,original=example,inputs=[dict(name='label',label='Sample name',type='text')])
                    saved=call('POST',BASE+'/drafts',{'draft':draft})
                    job=call('POST',BASE+'/drafts/'+saved['id']+'/try',dict(inputs={'label':'Demo'}))
                    deadline=time.monotonic()+30
                    while job['status'] in {'pending','running'}:
                        assert time.monotonic()<deadline
                        time.sleep(.05);job=call('GET',BASE+'/reports/'+job['id'])
                    assert job['status']=='ready',job
                    content=call('GET',BASE+'/reports/'+job['id']+'/download')
                    assert list(openpyxl.load_workbook(io.BytesIO(content)).active.values)==[('Demo',42)]
                    (EVIDENCE/'example.xlsx').write_bytes(content)
                    result['checks'].append('Nested/unavailable/dynamic imports detected without running upload; no-database draft generates correct workbook')
                    result['passed']=True
            finally:
                service.close()
                admin.execute('USE master')
                if admin.execute('SELECT name FROM sys.server_principals WHERE name=?',new_login).fetchone():
                    admin.execute('USE ['+fixture['names'][0]+']; DROP USER ['+new_login+']; USE master; DROP LOGIN ['+new_login+']')
    except Exception:
        result['passed']=False
        result['failure']=traceback.format_exc()
        raise
    finally:
        (EVIDENCE/'workspace-http-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

if __name__=='__main__': run()
