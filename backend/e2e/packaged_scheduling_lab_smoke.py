"""Read-only scheduler catalogue checks in a relocated, disposable executable.

No schedule is created or launched. HTTP/executor preparation is covered by
scheduling_lab_check; this check covers frozen imports, configuration and restart.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def run(candidate):
    evidence=ROOT/'recovery/scheduling-lab-verification'
    evidence.mkdir(parents=True,exist_ok=True)
    result=dict(passed=False, candidate=str(candidate), checks=[],
                exe_sha256=hashlib.sha256((candidate/'RobotControl.exe').read_bytes()).hexdigest())
    def request(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token: headers['Authorization']='Bearer '+token
        req=urllib.request.Request('http://127.0.0.1:8019'+path,headers=headers,
                                   data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)
    process=None
    try:
        with tempfile.TemporaryDirectory(prefix='relocated-scheduling-',dir=ROOT/'recovery') as temporary:
            relocated=Path(temporary)/'Lab candidate in another folder'
            shutil.copytree(candidate,relocated,ignore=shutil.ignore_patterns('data'))
            data=relocated/'data';data.mkdir()
            with closing(sqlite3.connect(data/'batches.db')) as conn,conn:
                conn.executescript((ROOT/'backend/services/scheduling/examples/batch-schema.sql').read_text('utf-8'))
            (data/'scheduling-lab.json').write_text(json.dumps(dict(adapter='batch-sqlite',sqlite_path='batches.db')),'utf-8')
            password=secrets.token_urlsafe(24)
            environment={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','UV_PROJECT_ENVIRONMENT'}}
            environment.update(PATH=str(Path(os.environ['SystemRoot'])/'System32'),
                ROBOTCONTROL_AUTO_RECORDING_ENABLED='false', ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS='disabled',
                ROBOTCONTROL_ADMIN_USERNAME='lab-smoke',ROBOTCONTROL_ADMIN_PASSWORD=password,
                ROBOTCONTROL_ACCESS_TOKEN_SECRET=secrets.token_urlsafe(32),ROBOTCONTROL_REFRESH_TOKEN_SECRET=secrets.token_urlsafe(32))
            assert shutil.which('python',path=environment['PATH']) is None and shutil.which('uv',path=environment['PATH']) is None
            for iteration in range(2):
                try:
                    process=subprocess.Popen([str(relocated/'RobotControl.exe'),'--host','127.0.0.1','--port','8019','--no-browser'],
                        cwd=relocated,env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
                    deadline=time.monotonic()+90
                    while True:
                        try: request('/health');break
                        except Exception:
                            if process.poll() is not None or time.monotonic()>deadline: raise
                            time.sleep(.5)
                    token=request('/api/auth/login',dict(username='lab-smoke',password=password))['data']['access_token']
                    if iteration==0:
                        new_password=secrets.token_urlsafe(24)
                        request('/api/auth/change-password',dict(current_password=password,new_password=new_password),token)
                        password=new_password
                    catalogue=request('/api/scheduling/lab/preparation',token=token)
                    assert catalogue['id']=='batch-sqlite' and [r['value'] for r in catalogue['choices']]==['B-01','B-02']
                    assert catalogue['selection_label']=='Batch'
                    with closing(sqlite3.connect(data/'batches.db')) as conn:
                        assert conn.execute('SELECT batch_code FROM InstrumentWorkOrder').fetchone()[0] is None
                    with closing(sqlite3.connect(data/'robotcontrol_scheduling.db')) as conn:
                        assert conn.execute('SELECT COUNT(*) FROM ScheduledExperiments').fetchone()[0]==0
                        identity=json.loads(conn.execute('SELECT identity FROM LabInstallation WHERE id=1').fetchone()[0])
                        assert identity['database']==str((data/'batches.db').resolve())
                    result['checks'].append('Restart catalogue and captured lab identity passed' if iteration else 'Relocated executable: bundled lab adapter and relative SQLite path passed; no writes or schedules')
                finally:
                    if process is not None:
                        process.terminate()
                        try: process.wait(timeout=15)
                        except subprocess.TimeoutExpired: process.kill();process.wait(timeout=10)
                        process=None
        result.update(passed=True,process_stopped=True,fixture_removed=True,
            limit='Python/UV absent from child PATH, not uninstalled from host. No hardware launch or second laboratory validation.')
    finally:
        (evidence/'packaged-results.json').write_text(json.dumps(result,indent=2),'utf-8')
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('candidate',type=Path)
    run(parser.parse_args().candidate.resolve())
