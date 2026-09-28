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
import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]


def run(candidate, report_package=None, evidence=ROOT/'recovery/database-verification'):
    evidence.mkdir(parents=True, exist_ok=True)
    result = dict(candidate=str(candidate), checks=[], passed=False)
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
    with tempfile.TemporaryDirectory(prefix='relocated-database-',dir=ROOT/'recovery') as temp:
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
            fixture=(ROOT/'backend/e2e/database_fixture.py').read_text()
            fixture+='''
from backend.services.database_tools import get_database_tools
service = get_database_tools()
service.database = DatabaseFixture(service.root)
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
            result['limit']='SQL Server/ODBC and dbo.DeleteExperiment execution require VM verification; disposable adapter used here.'
            (evidence/'packaged-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('candidate',type=Path)
    parser.add_argument('--report-package',type=Path)
    parser.add_argument('--evidence',type=Path,default=ROOT/'recovery/database-verification')
    args=parser.parse_args()
    run(args.candidate.resolve(),args.report_package,args.evidence.resolve())
