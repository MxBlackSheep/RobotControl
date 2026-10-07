"""Relocated executable check with no Python/UV on its PATH and disposable SQL rows.

Usage: packaged_database_smoke.py dist/<candidate>/RobotControl [--report-package ZIP]
[--evidence DIR] [--wizard]. Port: 8018, or PACKAGED_E2E_PORT; it refuses a port already
in use (see packaged_app.py). Needs local .\\HAMILTON with Windows administrator access
to create and drop a UUID-named database and login (report_wizard_check.sql_fixture).

Reports run in a spawned process that opens only configured read-only connections,
and installing a package never imports it. So the check configures the report
connection through the same HTTP routes an administrator uses (save a read-only
connection, assign it to each package) against a disposable SQL Server copy of the
DatabaseFixture rows. There is no production test endpoint. VM data, dbo.DeleteExperiment
and hardware remain a VM check.

Failure cases:
- Test suites are shipped in the frozen archive or support files.
- The relocated executable, with Python/UV absent from PATH, does not load both packages.
- An uploaded package is not usable without restart/recompile: its report does not
  run through the assigned connection.
- A report ZIP (--report-package) does not replace the bundled version.
- The installed culture-history report cannot read through the read-only connection,
  or its Excel output (bundled pandas/openpyxl) is wrong.
- Removing a package leaves it listed, or data is not kept beside the relocated copy.
- --wizard: DPAPI connection storage, read-only login creation, duplicate-login
  conflicts, private drafts, dependent inputs, trial/installed generation and prepared
  Python with relative helpers fail in the packaged process.
"""
import argparse
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import closing
from urllib.error import HTTPError
import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.e2e import packaged_app

PORT = packaged_app.port(8018)


def wizard_check(request, token, result, evidence):
    from backend.e2e.report_wizard_check import sql_fixture
    with sql_fixture() as fixture:
        created_login = fixture['login'] + '_packaged'
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
    result['sql_fixture_removed']=True
    result['passed']=True


def copy_fixture_rows(admin, database, extra_culture):
    """Copy the DatabaseFixture rows into a disposable SQL Server database.

    The report calls the dbo.Descendants(?) table-valued function, which the SQLite
    fixture models as a Descendants table.
    """
    from backend.e2e.database_fixture import DatabaseFixture
    types = {'INTEGER': 'int', 'INT': 'int', 'TEXT': 'nvarchar(200)', 'REAL': 'float'}
    with tempfile.TemporaryDirectory(dir=ROOT/'test-output') as temp, closing(sqlite3.connect(DatabaseFixture(temp).path)) as source:
        cursor = admin.cursor()
        cursor.execute('USE ['+database+']')
        for (table,) in source.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            columns = source.execute('SELECT name, type FROM pragma_table_info(?) ORDER BY cid', (table,)).fetchall()
            target = 'DescendantRows' if table == 'Descendants' else table
            cursor.execute(f'CREATE TABLE dbo.[{target}] ('+', '.join(
                f"[{name}] {'datetime' if name == 'TimeStamp' else types[kind]}" for name, kind in columns)+')')
            cursor.executemany(f'INSERT dbo.[{target}] VALUES ('+','.join('?'*len(columns))+')',
                               source.execute(f'SELECT * FROM [{table}]').fetchall())
        cursor.execute('CREATE FUNCTION dbo.Descendants(@plate int) RETURNS TABLE AS RETURN '
                       'SELECT DescPlateID FROM dbo.DescendantRows WHERE AncPlateID=@plate')
        if extra_culture:
            cursor.execute('INSERT dbo.Cultures VALUES (2000000,20,NULL)')
        cursor.execute('USE master')
        cursor.close()


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
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}'+path, data=data, headers=headers, method=method)
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
        process=packaged_app.launch(relocated, environment, PORT)
        try:
            packaged_app.wait_until_serving(process, PORT, lambda: request('/health'))
            token=request('/api/auth/login',dict(username='package-smoke',password=password))['data']['access_token']
            request('/api/auth/change-password',dict(current_password=password,new_password=secrets.token_urlsafe(24)),token)
            packages=request('/api/database/tools/packages',token=token)
            assert {p['id'] for p in packages}=={'culture-history','delete-experiment','evoyeast-experiment','plate-data-export'}
            assert {f.name for f in (candidate/'starter-packages').iterdir()}=={'culture-history.zip','delete-experiment.zip','evoyeast-experiment.zip','plate-data-export.zip'}
            result['checks'].append('Relocated executable loads the three starter packages with Python/UV absent from PATH; their ZIPs ship beside it')
            if wizard:
                wizard_check(request, token, result, evidence)
                return
            from backend.e2e.report_wizard_check import sql_fixture
            def report(package_id, inputs):
                job=request('/api/database/tools/reports/'+package_id,{'inputs':inputs},token)
                deadline=time.monotonic()+60
                while job['status'] in {'pending','running'}:
                    assert time.monotonic()<deadline, job
                    time.sleep(.2); job=request('/api/database/tools/reports/'+job['id'],token=token)
                assert job['status']=='ready',job
                return request('/api/database/tools/reports/'+job['id']+'/download',token=token)
            with sql_fixture() as sql:
                result['fixture']={'database':sql['names'][0],'login':sql['login'],'rows':'backend/e2e/database_fixture.py DatabaseFixture'}
                copy_fixture_rows(sql['admin'], sql['names'][0], extra_culture=bool(report_package))
                request('/api/database/tools/sources',dict(id='primary',name='Primary',server=sql['server'],database=sql['names'][0],
                    username=sql['login'],password=sql['password'],trust_certificate=True),token)
                handler='''def run(context, inputs):
    import openpyxl
    book=openpyxl.Workbook()
    book.active.append(['Fixture'])
    book.save(context.output_dir/'fixture.xlsx')
    return 'fixture.xlsx'
'''
                manifest={'contract_version':1,'id':'verification-fixture','name':'Disposable verification fixture','version':'1.0.0','libraries':['openpyxl'],
                    'tools':[{'id':'verification-fixture','name':'Fixture','kind':'report','entrypoint':'handler:run','inputs':[]}]}
                output=io.BytesIO()
                with zipfile.ZipFile(output,'w') as archive:
                    archive.writestr('manifest.json',json.dumps(manifest)); archive.writestr('handler.py',handler)
                request('/api/database/tools/packages',token=token,upload=output.getvalue())
                # Installation never imports package code, so activation is shown by a run.
                request('/api/database/tools/packages/verification-fixture/sources',{'mappings':{'primary':'primary'}},token,method='PUT')
                assert list(openpyxl.load_workbook(io.BytesIO(report('verification-fixture',{}))).active.values)==[('Fixture',)]
                result['checks'].append('Trusted fixture package uploaded and activated without restart/recompile')
                if report_package:
                    inspected=request('/api/database/tools/packages/inspect',token=token,upload=report_package.read_bytes())
                    request('/api/database/tools/packages',token=token,upload=report_package.read_bytes())
                    result['checks'].append('Report ZIP replaces bundled version without rebuilding the executable: '+inspected['package']['version'])
                    result['package_sha256']=hashlib.sha256(report_package.read_bytes()).hexdigest()
                request('/api/database/tools/packages/culture-history/sources',{'mappings':{'primary':'primary'}},token,method='PUT')
                content=report('culture-history',{'experiment_id':42})
                (evidence/'packaged-culture-history.xlsx').write_bytes(content)
                sheet=openpyxl.load_workbook(io.BytesIO(content)).active
                assert sheet.title=='CultureHistory' and sheet.max_row==6 and sheet.max_column==15 and sheet.freeze_panes=='D2'
                result['checks'].append('Real installed culture-history handler reads the read-only SQL Server connection, generates and downloads Excel with bundled pandas/openpyxl')
                result['workbook_sha256']=hashlib.sha256(content).hexdigest()
                request('/api/database/tools/packages/verification-fixture',token=token,method='DELETE')
                assert all(p['id']!='verification-fixture' for p in request('/api/database/tools/packages',token=token))
                assert (relocated/'data/database-tools/packages/installed.json').is_file()
                result['checks'].append('Removal and relocated data root verified')
            result['sql_fixture_removed']=True
            result['passed']=True
        finally:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
            result['process_stopped']=True
            result['limit']='Real SQL Server uses disposable databases; actual VM data and hardware are not exercised.' if wizard else 'Culture history reads a disposable local SQL Server copy of the fixture rows; VM data, dbo.DeleteExperiment execution and hardware are not exercised.'
            (evidence/'packaged-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('candidate',type=Path)
    parser.add_argument('--report-package',type=Path)
    parser.add_argument('--evidence',type=Path,default=ROOT/'test-output/database-verification')
    parser.add_argument('--wizard',action='store_true')
    args=parser.parse_args()
    run(args.candidate.resolve(),args.report_package,args.evidence.resolve(),args.wizard)
