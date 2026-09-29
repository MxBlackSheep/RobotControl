"""Relocated executable check with no Python/UV on its PATH and disposable SQL rows.

The uploaded fixture package substitutes the database connection in this temporary
process. There is no production test endpoint. Real SQL Server remains a VM check.
"""
import argparse
import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request
from urllib.error import HTTPError
import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]


def wizard_check(request, token, result, evidence):
    from backend.e2e.report_wizard_check import sql_fixture
    with sql_fixture() as fixture:
        created_login = fixture['login'] + '_packaged'
        try:
            result['fixture'] = {'databases': fixture['names'], 'login': fixture['login']}
            for alias, database in zip(('primary', 'plates'), fixture['names']):
                request('/api/database/tools/sources', dict(id=alias, name=alias, server=fixture['server'],
                    database=database, username=fixture['login'], password=fixture['password'], trust_certificate=True), token)
            profile = dict(id='created-reader', name='Created reader', server=fixture['server'], database=fixture['names'][0],
                username=created_login, trust_certificate=True)
            fixture['admin'].execute('USE ['+fixture['names'][0]+']')
            fixture['admin'].execute('CREATE PROCEDURE dbo.sp_helpdiagrams AS SELECT 1 AS value')
            fixture['admin'].execute('GRANT EXECUTE ON dbo.sp_helpdiagrams TO public')
            fixture['admin'].execute('USE master')
            review = request('/api/database/tools/sources/access/review', profile, token)
            request('/api/database/tools/sources/access/create', {'token':review['token'], 'windows_auth':True}, token)
            conflict = request('/api/database/tools/sources/access/review', dict(profile, id='conflicting-reader'), token)
            try:
                request('/api/database/tools/sources/access/create', {'token':conflict['token'], 'windows_auth':True}, token)
                raise AssertionError('Existing login was accepted')
            except HTTPError as exc:
                assert exc.code == 400
                assert 'already exists' in exc.read().decode()
            result['checks'].append('Packaged duplicate-login error identifies the conflict without changing the existing account')
            request('/api/database/tools/viewer-source', {'source_id':'created-reader'}, token, method='PUT')
            tables = request('/api/database/tables?source_id=created-reader', token=token)['data']['tables']
            assert '[dbo].[Projects]' in tables
            assert request('/api/database/tables/%5Bdbo%5D.%5BProjects%5D?source_id=created-reader',token=token)['data']['total_count']==2
            fixture['admin'].execute('USE ['+fixture['names'][0]+']; REVOKE EXECUTE ON dbo.sp_helpdiagrams FROM public; USE master')
            result['checks'].append('Packaged account creation succeeds with inherited public EXECUTE while retaining read-only verification')
            request('/api/database/stored-procedures?source_id=created-reader',token=token)
            scan = request('/api/database/tools/authoring/inspect-python',{'source':'def example():\n    import openpyxl\n'},token)
            assert scan['available']==['openpyxl']
            result['checks'].append('Packaged read-only account provisioning, schema-qualified viewer and upload import detection passed')
            handler = '''import pandas as pd
def run(context, inputs):
    rows = []
    for source in ('primary', 'plates'):
        row = context.connections[source].cursor().execute('SELECT label FROM dbo.Projects WHERE id=?', inputs['project']).fetchone()
        rows.append([source, row[0]])
    pd.DataFrame(rows).to_excel(context.output_dir / 'portable.xlsx', engine='openpyxl', index=False, header=False)
    return 'portable.xlsx'
'''
            draft = dict(name='Portable SQL report', package_id='portable-sql-report', version='1.0.0',
                libraries=['pandas','openpyxl'], original='raise RuntimeError("reference only")', handler=handler,
                sources=['primary','plates'], mappings={'primary':'primary','plates':'plates'}, step=2,
                inputs=[dict(name='project',label='Project',type='lookup',required=True,choices=[],
                    lookup=dict(source='primary',query='SELECT id AS value, label FROM dbo.Projects',parameters=[],value_type='integer'))])
            saved = request('/api/database/tools/drafts', {'draft': draft}, token)
            prefix = '/api/database/tools/drafts/' + saved['id']
            with zipfile.ZipFile(io.BytesIO(request(prefix+'/editing-files',token=token))) as editing:
                assert editing.read('original.py').decode() == draft['original']
                assert 'EDITING.md' in editing.namelist()
            choices = request(prefix+'/choices/project', {'inputs':{}}, token)
            assert {x['value'] for x in choices['options']} == {1,2}
            def finished(job):
                deadline=time.monotonic()+60
                while job['status'] in {'pending','running'}:
                    assert time.monotonic()<deadline,job
                    time.sleep(.1);job=request('/api/database/tools/reports/'+job['id'],token=token)
                assert job['status']=='ready',job
                return job
            job=finished(request(prefix+'/try', {'inputs':{'project':1}},token))
            content=request('/api/database/tools/reports/'+job['id']+'/download',token=token)
            assert list(openpyxl.load_workbook(io.BytesIO(content)).active.values)==[('primary','Yeast Ω'),('plates','Yeast Ω')]
            (evidence/'packaged-two-source.xlsx').write_bytes(content)
            package=request(prefix+'/package',token=token)
            request('/api/database/tools/packages',token=token,upload=package)
            assert request('/api/database/tools/packages/portable-sql-report/export',token=token) == package
            request('/api/database/tools/packages/portable-sql-report/sources',{'mappings':draft['mappings']},token,method='PUT')
            finished(request('/api/database/tools/reports/portable-sql-report',{'inputs':{'project':2}},token))
            result['checks'].append('Relocated executable: DPAPI source storage, SQL permission checks, private draft, dependent input API, trial workbook, exported ZIP upload and installed generation passed')
            result['workbook_sha256']=hashlib.sha256(content).hexdigest()
            result['package_sha256']=hashlib.sha256(package).hexdigest()
            request(prefix,token=token,method='DELETE')
            request('/api/database/tools/packages/portable-sql-report',token=token,method='DELETE')
            # Prepared Python uses the same bundled runtime, including relative helpers.
            from backend.e2e.tool_authoring_check import REPORT
            for kind in ('report', 'operation'):
                assert b'TOOL' in request('/api/database/tools/authoring/examples/'+kind,token=token)
            saved=request('/api/database/tools/authoring/import',{'files':{
                'report.py':REPORT, 'helper.py':"heading='Packaged'\n"}},token)
            prefix='/api/database/tools/drafts/'+saved['id']
            saved=request(prefix,{'draft':{**saved['draft'],'mappings':{'primary':'primary'}},'revision':saved['revision']},token,method='PUT')
            request(prefix+'/check',{},token)
            choices=request(prefix+'/choices/plate',{'inputs':{'experiment':1}},token)
            assert {x['value'] for x in choices['options']}=={11,12}
            job=finished(request(prefix+'/try',{'inputs':{'experiment':1,'plate':11},'revision':saved['revision']},token))
            content=request('/api/database/tools/reports/'+job['id']+'/download',token=token)
            assert list(openpyxl.load_workbook(io.BytesIO(content)).active.values)==[('Packaged','Same name',11)]
            (evidence/'packaged-python-tool.xlsx').write_bytes(content)
            reviewed=request(prefix+'/review',token=token)
            request(prefix+'/install',{'revision':saved['revision'],'expected_current':reviewed['current_sha256'],'reviewed':True,'change_note':'Packaged authoring check.'},token)
            finished(request('/api/database/tools/reports/plate-export',{'inputs':{'experiment':2,'plate':21}},token))
            assert not any(d['id']==saved['id'] for d in request('/api/database/tools/drafts',token=token))
            assert request('/api/database/tools/packages/plate-export/history',token=token)[0]['note']=='Packaged authoring check.'
            request('/api/database/tools/packages/plate-export',token=token,method='DELETE')
            result['checks'].append('Prepared Python: bundled examples, relative helper import, dependent form, real SQL Excel trial, enable and installed generation passed')
            result['python_tool_workbook_sha256']=hashlib.sha256(content).hexdigest()
        finally:
            admin = fixture['admin']
            admin.execute('USE master')
            if admin.execute('SELECT name FROM sys.server_principals WHERE name=?', created_login).fetchone():
                admin.execute('USE ['+fixture['names'][0]+']')
                if admin.execute('SELECT name FROM sys.database_principals WHERE name=?', created_login).fetchone():
                    admin.execute('DROP USER ['+created_login+']')
                admin.execute('USE master')
                # The packaged process can retain idle ODBC pooled sessions. Only
                # terminate sessions owned by this UUID-named disposable login.
                for row in admin.execute('SELECT session_id FROM sys.dm_exec_sessions WHERE login_name=?',created_login).fetchall():
                    admin.execute('KILL '+str(int(row[0])))
                admin.execute('DROP LOGIN ['+created_login+']')
    result['sql_fixture_removed']=True
    result['passed']=True


def run(candidate, report_package=None, evidence=ROOT/'test-output/database-verification', wizard=False):
    evidence.mkdir(parents=True, exist_ok=True)
    result = dict(candidate=str(candidate), checks=[], passed=False)
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(candidate/'RobotControl.exe')).open_embedded_archive('PYZ.pyz')
    tests = [name for name in archive.toc if name.endswith('.tests') or '.tests.' in name or name.startswith('backend.e2e')]
    test_files = [str(p.relative_to(candidate)) for p in candidate.rglob('*') if p.is_file() and 'tests' in p.relative_to(candidate).parts]
    (evidence/'release-contents.json').write_text(json.dumps({'modules':len(archive.toc),'test_modules':tests,'test_files':test_files},indent=2))
    assert not tests and not test_files, 'Test suites included in the release; see release-contents.json'
    result['checks'].append('Frozen module archive and support files contain no test suites')
    def request(path, body=None, token=None, method=None, upload=None):
        headers={}
        if token: headers['Authorization']='Bearer '+token
        if upload:
            boundary='rc-package-'+secrets.token_hex(8)
            data=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="fixture.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode()+upload+f'\r\n--{boundary}--\r\n'.encode())
            headers['Content-Type']='multipart/form-data; boundary='+boundary
        else:
            headers['Content-Type']='application/json'
            data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request('http://127.0.0.1:8018'+path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req,timeout=40) as response:
            data=response.read()
            return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data
    with tempfile.TemporaryDirectory(prefix='relocated-database-',dir=ROOT/'test-output') as temp:
        relocated=Path(temp)/'Application in another folder'
        shutil.copytree(candidate, relocated, ignore=shutil.ignore_patterns('data'))
        password=secrets.token_urlsafe(24)
        environment={key:value for key,value in os.environ.items() if key not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','UV_PROJECT_ENVIRONMENT'}}
        environment.update(PATH=str(Path(os.environ['SystemRoot'])/'System32'), ROBOTCONTROL_AUTO_RECORDING_ENABLED='false',
            ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS='disabled', ROBOTCONTROL_ADMIN_USERNAME='package-smoke',
            ROBOTCONTROL_ADMIN_PASSWORD=password, ROBOTCONTROL_ACCESS_TOKEN_SECRET=secrets.token_urlsafe(32),
            ROBOTCONTROL_REFRESH_TOKEN_SECRET=secrets.token_urlsafe(32), VM_SQL_SERVER='127.0.0.1,1')
        process=subprocess.Popen([str(relocated/'RobotControl.exe'),'--host','127.0.0.1','--port','8018','--no-browser'],
            cwd=relocated, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline=time.monotonic()+90
            while True:
                try: request('/health'); break
                except Exception:
                    if process.poll() is not None or time.monotonic()>deadline: raise
                    time.sleep(.5)
            token=request('/api/auth/login',dict(username='package-smoke',password=password))['data']['access_token']
            request('/api/auth/change-password',dict(current_password=password,new_password=secrets.token_urlsafe(24)),token)
            packages=request('/api/database/tools/packages',token=token)
            assert {p['id'] for p in packages}=={'culture-history','delete-experiment'}
            result['checks'].append('Relocated executable loads both packages with Python/UV absent from PATH')
            if wizard:
                wizard_check(request, token, result, evidence)
                return
            fixture=(ROOT/'backend/e2e/database_fixture.py').read_text()
            fixture+='''
from backend.services.database_tools import get_database_tools
service = get_database_tools()
service.database = DatabaseFixture(service.root)
configure_fixture_report_sources(service)
def run(context, inputs):
    import openpyxl
    book=openpyxl.Workbook()
    book.active.append(['Fixture'])
    book.save(context.output_dir/'fixture.xlsx')
    return 'fixture.xlsx'
'''
            if report_package:
                fixture += '\nwith closing(sqlite3.connect(service.database.path)) as connection, connection:\n    connection.execute("INSERT INTO Cultures VALUES (2000000,20,NULL)")\n'
            manifest={'contract_version':1,'id':'verification-fixture','name':'Disposable verification fixture','version':'1.0.0','libraries':['openpyxl'],
                'tools':[{'id':'verification-fixture','name':'Fixture','kind':'report','entrypoint':'handler:run','inputs':[]}]}
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as archive:
                archive.writestr('manifest.json',json.dumps(manifest)); archive.writestr('handler.py',fixture)
            request('/api/database/tools/packages',token=token,upload=output.getvalue())
            result['checks'].append('Trusted fixture package uploaded and activated without restart/recompile')
            if report_package:
                inspected=request('/api/database/tools/packages/inspect',token=token,upload=report_package.read_bytes())
                request('/api/database/tools/packages',token=token,upload=report_package.read_bytes())
                result['checks'].append('Report ZIP replaces bundled version without rebuilding the executable: '+inspected['package']['version'])
                result['package_sha256']=hashlib.sha256(report_package.read_bytes()).hexdigest()
            job=request('/api/database/tools/reports/culture-history',{'inputs':{'experiment_id':42}},token)
            deadline=time.monotonic()+60
            while job['status'] in {'pending','running'}:
                assert time.monotonic()<deadline, job
                time.sleep(.2); job=request('/api/database/tools/reports/'+job['id'],token=token)
            assert job['status']=='ready',job
            content=request('/api/database/tools/reports/'+job['id']+'/download',token=token)
            (evidence/'packaged-culture-history.xlsx').write_bytes(content)
            sheet=openpyxl.load_workbook(io.BytesIO(content)).active
            assert sheet.title=='CultureHistory' and sheet.max_row==6 and sheet.max_column==15 and sheet.freeze_panes=='D2'
            result['checks'].append('Real installed culture-history handler generates and downloads Excel with bundled pandas/openpyxl')
            result['workbook_sha256']=hashlib.sha256(content).hexdigest()
            request('/api/database/tools/packages/verification-fixture',token=token,method='DELETE')
            assert all(p['id']!='verification-fixture' for p in request('/api/database/tools/packages',token=token))
            assert (relocated/'data/database-tools/packages/installed.json').is_file()
            result['checks'].append('Removal and relocated data root verified')
            result['passed']=True
        finally:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
            result['process_stopped']=True
            result['limit']='Real SQL Server uses disposable databases; actual VM data and hardware are not exercised.' if wizard else 'SQL Server/ODBC and dbo.DeleteExperiment execution require VM verification; disposable adapter used here.'
            (evidence/'packaged-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('candidate',type=Path)
    parser.add_argument('--report-package',type=Path)
    parser.add_argument('--evidence',type=Path,default=ROOT/'test-output/database-verification')
    parser.add_argument('--wizard',action='store_true')
    args=parser.parse_args()
    run(args.candidate.resolve(),args.report_package,args.evidence.resolve(),args.wizard)
