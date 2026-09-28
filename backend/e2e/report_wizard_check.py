"""Real SQL Server + HTTP report-authoring workflow using owned disposable data.

Run: .venv/Scripts/python.exe -m backend.e2e.report_wizard_check
Requires a local SQL Server administrator via Windows authentication. Never uses
application DB credentials or modifies existing databases/users/grants.
"""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import secrets
import tempfile
import time
import traceback
import uuid
import zipfile

import openpyxl
import pyodbc
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from backend.api.database_tools import router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'recovery/report-wizard-verification'
BASE = '/api/database/tools'


@contextmanager
def sql_fixture():
    suffix = uuid.uuid4().hex[:12]
    login = 'rc_report_check_' + suffix
    names = [login + '_a', login + '_b']
    password = secrets.token_urlsafe(32)
    server = r'.\HAMILTON'
    admin = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE=master;Trusted_Connection=yes;TrustServerCertificate=yes', timeout=5, autocommit=True)
    created = []
    logged = False
    try:
        admin.execute(f"CREATE LOGIN [{login}] WITH PASSWORD='{password}', CHECK_POLICY=OFF")
        logged = True
        for name in names:
            assert name.startswith('rc_report_check_') and name.replace('_', '').isalnum()
            admin.execute(f'CREATE DATABASE [{name}]'); created.append(name)
            admin.execute(f'USE [{name}]')
            admin.execute(f'CREATE USER [{login}] FOR LOGIN [{login}]')
            admin.execute(f'GRANT SELECT TO [{login}]')
            admin.execute('CREATE TABLE dbo.Projects (id int PRIMARY KEY, label nvarchar(80)); INSERT dbo.Projects VALUES (1,N\'Yeast Ω\'),(2,N\'Other\')')
            admin.execute('CREATE TABLE dbo.Plates (id int PRIMARY KEY, project int, label nvarchar(80)); INSERT dbo.Plates VALUES (11,1,N\'Same name\'),(12,1,N\'Same name\'),(21,2,N\'Other plate\')')
        admin.execute('USE master')
        yield dict(server=server, names=names, login=login, password=password, admin=admin)
    finally:
        admin.execute('USE master')
        for name in reversed(created):
            admin.execute(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            admin.execute(f'DROP DATABASE [{name}]')
        if logged:
            # ODBC pooling can retain this fixture's login after a failed setup.
            sessions = admin.execute('SELECT session_id FROM sys.dm_exec_sessions WHERE login_name=?', login).fetchall()
            for session in sessions:
                admin.execute(f'KILL {int(session[0])}')
            admin.execute(f'DROP LOGIN [{login}]')
        admin.close()


def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'checks': [], 'command': '.venv/Scripts/python.exe -m backend.e2e.report_wizard_check'}
    try:
        with sql_fixture() as fixture, tempfile.TemporaryDirectory(prefix='rc-report-author-') as temporary:
            result['fixture'] = {'databases': fixture['names'], 'login': fixture['login'], 'rows': 'Projects 1/2; Plates 11/12/21'}
            service = DatabaseTools(Path(temporary)/'tools', ROOT/'database_packages', database=object())
            app = FastAPI(); app.include_router(router)
            def user(request: Request):
                name = request.headers.get('authorization')
                if not name: raise HTTPException(401)
                return {'username': name, 'role': 'user' if name == 'user' else 'admin'}
            app.dependency_overrides[get_current_user] = user
            app.dependency_overrides[get_database_tools] = lambda: service
            try:
                with TestClient(app, client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
                    def call(method, path, payload=None, status=200):
                        r = client.request(method, BASE+path, json=payload) if payload is not None else client.request(method, BASE+path)
                        assert r.status_code == status, (path, r.status_code, r.text)
                        return r.json() if 'application/json' in r.headers.get('content-type','') else r.content
                    # A working app DB object is deliberately absent; fallback would crash.
                    call('POST', '/reports/culture-history', {'inputs': {'experiment_id': 42}}, 409)
                    for alias, database in zip(('primary', 'plates'), fixture['names']):
                        call('POST', '/sources', dict(id=alias, name=alias.title(), server=fixture['server'], database=database,
                            username=fixture['login'], password=fixture['password'], trust_certificate=True))
                    assert fixture['password'] not in json.dumps(call('GET', '/sources'))
                    assert fixture['password'] not in service.sources.path.read_text()
                    result['checks'].append('Missing mapping blocks; real SQL SELECT-only connections saved with encrypted passwords')
                    # Direct writes fail at SQL Server even outside our query composer.
                    snapshot = service.sources.snapshot('unused', ['primary'], {'primary': 'primary'})
                    for sql in ('INSERT dbo.Projects VALUES (3,\'bad\')', 'DELETE FROM dbo.Projects',
                                'UPDATE dbo.Projects SET label=\'bad\'', 'CREATE TABLE dbo.Bad (id int)'):
                        with service.sources.open(snapshot['primary']) as conn:
                            try:
                                conn.execute(sql)
                            except pyodbc.Error:
                                conn.rollback()
                            else:
                                raise AssertionError('SQL Server allowed a write')
                    # Permission drift is rechecked; a saved profile is not a certificate.
                    admin = fixture['admin']; admin.execute(f"USE [{fixture['names'][1]}]")
                    admin.execute(f"GRANT UPDATE ON dbo.Plates TO [{fixture['login']}]")
                    try:
                        with service.sources.open(snapshot['primary']):
                            raise AssertionError('Cross-database write grant accepted')
                    except ValueError as exc:
                        assert 'UPDATE' in str(exc)
                    admin.execute(f"REVOKE UPDATE ON dbo.Plates FROM [{fixture['login']}]")
                    admin.execute('USE master')
                    result['checks'].append('INSERT/UPDATE/DELETE/DDL denied by SQL Server; cross-database permission drift rejected')
                    def field(name, source, query, parameters=[]):
                        return dict(name=name, label=name.title(), type='lookup', required=True, choices=[],
                            lookup=dict(source=source, query=query, parameters=parameters, value_type='integer'))
                    draft = dict(name='Two-source report', package_id='two-source', version='1.0.0', libraries=['openpyxl'],
                        original="raise RuntimeError('ORIGINAL MUST NEVER IMPORT')\n", handler='', sources=['primary','plates'],
                        mappings={'primary':'primary','plates':'plates'}, inputs=[
                            field('project','primary','SELECT id AS value, label FROM dbo.Projects'),
                            field('plate','plates','SELECT id AS value, label FROM dbo.Plates WHERE project=?',['project']),
                            dict(name='day', label='Day', type='date', required=True, choices=[])], step=0)
                    saved = call('POST','/drafts',dict(draft=draft))
                    key = saved['id']
                    assert call('GET',f'/drafts/{key}')['draft']==draft
                    call('PUT',f'/drafts/{key}',dict(draft=draft, revision=0),409)
                    client.headers['authorization']='another-admin'; call('GET',f'/drafts/{key}',status=404)
                    client.headers['authorization']='user'; call('GET','/sources',status=403); call('GET',f'/drafts/{key}',status=403)
                    client.headers['authorization']='admin'
                    call('POST',f'/drafts/{key}/try',{'inputs':{}},400)
                    starter = call('GET',f'/drafts/{key}/handler').decode()
                    assert 'plate' in starter and 'ADAPT_BEFORE_BUILD' in starter
                    handler = '''import openpyxl
def run(context, inputs):
    book = openpyxl.Workbook()
    a = context.connections['primary'].cursor().execute('SELECT label FROM dbo.Projects WHERE id=?', inputs['project']).fetchone()[0]
    b = context.connections['plates'].cursor().execute('SELECT label FROM dbo.Plates WHERE id=?', inputs['plate']).fetchone()[0]
    book.active.append([a, b, inputs['day']])
    book.save(context.output_dir / 'report.xlsx')
    return 'report.xlsx'
'''
                    draft.update(handler=handler, step=2)
                    saved=call('PUT',f'/drafts/{key}',dict(draft=draft,revision=saved['revision']))
                    choices=call('POST',f'/drafts/{key}/choices/plate',dict(inputs={'project':1}))
                    assert [x['value'] for x in choices['options']]==[11,12]
                    assert len({x['label'] for x in choices['options']})==1
                    call('POST',f'/drafts/{key}/choices/plate',dict(inputs={}),400)
                    assert call('POST',f'/drafts/{key}/choices/project',dict(inputs={},search="x' OR 1=1--"))['options']==[]
                    def wait(job):
                        deadline=time.monotonic()+30
                        while job['status'] in {'pending','running'}:
                            assert time.monotonic()<deadline
                            time.sleep(.05);job=call('GET','/reports/'+job['id'])
                        return job
                    bad=wait(call('POST',f'/drafts/{key}/try',dict(inputs={'project':2,'plate':11,'day':'2026-09-28'})))
                    assert bad['status']=='error' and 'no longer available' in bad['error']
                    job=wait(call('POST',f'/drafts/{key}/try',dict(inputs={'project':1,'plate':12,'day':'2026-09-28'})))
                    assert job['status']=='ready',job
                    data=call('GET','/reports/'+job['id']+'/download')
                    assert list(openpyxl.load_workbook(io.BytesIO(data)).active.values)==[('Yeast Ω','Same name','2026-09-28')]
                    (EVIDENCE/'two-source-report.xlsx').write_bytes(data)
                    result['workbook_sha256']=hashlib.sha256(data).hexdigest()
                    exported=call('GET',f'/drafts/{key}/package')
                    (EVIDENCE/'two-source-1.0.0.zip').write_bytes(exported)
                    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
                        assert sorted(archive.namelist())==['handler.py','manifest.json']
                        assert fixture['password'].encode() not in b''.join(archive.read(x) for x in archive.namelist())
                    review=call('GET',f'/drafts/{key}/review')
                    call('POST',f'/drafts/{key}/install',dict(expected_current=review['current_sha256'],revision=saved['revision']))
                    client.headers['authorization']='user'
                    job=wait(call('POST','/reports/two-source',dict(inputs={'project':1,'plate':11,'day':'2026-09-28'})))
                    assert job['status']=='ready'
                    client.headers['authorization']='admin'
                    call('GET','/reports/'+job['id'],status=404)
                    call('POST',f'/drafts/{key}/install',dict(expected_current='',revision=saved['revision']),409)
                    call('DELETE',f'/drafts/{key}')
                    result['checks'].append('Draft ownership/revision, original never imported, starter/edit/reupload, dependent membership, private trial, Excel values, export/install and stale activation passed')
                    with TestClient(app,client=('10.0.0.1',1234),headers={'authorization':'admin','x-forwarded-for':'127.0.0.1'}) as remote:
                        assert remote.get(BASE+'/drafts').status_code==403
                    result['passed']=True
            finally:
                service.close()
        result['fixture_removed']=True
    except Exception:
        result['failure']=traceback.format_exc(); raise
    finally:
        (EVIDENCE/'sql-http-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    run()
