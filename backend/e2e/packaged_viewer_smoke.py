"""Verify a relocated Windows candidate with disposable data and automation disabled.

Run: .venv/Scripts/python.exe backend/e2e/packaged_viewer_smoke.py <candidate folder>
The candidate itself is preserved; its temporary relocated copy is removed.
"""
import argparse
import gzip
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('candidate', type=Path)
args = parser.parse_args()
candidate = args.candidate.resolve()
assert (candidate/'RobotControl.exe').is_file(), candidate
evidence = ROOT/'recovery/viewer-verification'
evidence.mkdir(parents=True, exist_ok=True)
result = dict(candidate=str(candidate), checks=[], automation_disabled=True)


def request(path, body=None, token=None, method=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request('http://127.0.0.1:8017'+path,
        data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=10) as response:
        data=response.read()
        return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data


with tempfile.TemporaryDirectory(prefix='relocated-viewer-',dir=ROOT/'recovery') as temp:
    relocated=Path(temp)/'different application folder'
    shutil.copytree(candidate,relocated,ignore=shutil.ignore_patterns('data'))
    history=relocated/'data/logs/history'
    history.mkdir(parents=True)
    orphan=relocated/'data/temp/log-readers/reader-process-2147483647-fixture'
    orphan.mkdir(parents=True)
    (orphan/'partial.txt').write_text('Disposable orphaned reading copy')
    expected=('Packaged archive verification αβγ\r\n'*50000).encode()
    (history/'packaged-check.log.gz').write_bytes(gzip.compress(expected))
    password=secrets.token_urlsafe(24)
    environment={**os.environ,'ROBOTCONTROL_AUTO_RECORDING_ENABLED':'false',
        'ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS':'disabled',
        'ROBOTCONTROL_ADMIN_USERNAME':'viewer-smoke','ROBOTCONTROL_ADMIN_PASSWORD':password,
        'ROBOTCONTROL_ACCESS_TOKEN_SECRET':secrets.token_urlsafe(32),
        'ROBOTCONTROL_REFRESH_TOKEN_SECRET':secrets.token_urlsafe(32),
        'VM_SQL_SERVER':'127.0.0.1,1'}
    proc=subprocess.Popen([str(relocated/'RobotControl.exe'),'--host','127.0.0.1','--port','8017','--no-browser'],
        cwd=relocated,env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+90
        while True:
            try: request('/health');break
            except Exception:
                if proc.poll() is not None or time.monotonic()>deadline:raise
                time.sleep(.5)
        result['checks'].append('packaged health')
        assert not orphan.exists()
        result['checks'].append('startup removes orphaned reading copies')
        html=request('/').decode()
        assert 'assets/' in html
        result['checks'].append('embedded frontend')
        token=request('/api/auth/login',dict(username='viewer-smoke',password=password))['data']['access_token']
        request('/api/auth/change-password',dict(current_password=password,new_password=secrets.token_urlsafe(24)),token)
        sources=request('/api/logfiles/sources',token=token)['data']
        root=Path(next(s['path'] for s in sources if s['id']=='robotcontrol_logs'))
        assert root.resolve()==(relocated/'data/logs').resolve()
        assert (root/'robotcontrol_backend.log').is_file()
        result['checks'].append('source root matches relocated logger')
        reader=request('/api/logfiles/readers',dict(source_id='robotcontrol_logs',relative_path='history/packaged-check.log.gz'),token)['data']
        deadline=time.monotonic()+30
        while reader['state']=='preparing':
            assert time.monotonic()<deadline
            time.sleep(.1);reader=request('/api/logfiles/readers/'+reader['id'],token=token)['data']
        assert reader['state']=='ready',reader
        cursor='first';parts=[]
        while cursor:
            section=request('/api/logfiles/readers/'+reader['id']+'/sections?cursor='+cursor,token=token)['data']
            parts.append(section['content']);cursor=section['next_cursor']
        actual=''.join(parts).encode()
        assert actual==expected
        result['archive_sha256']=hashlib.sha256(actual).hexdigest()
        result['checks'].append('complete packaged archive through real authenticated HTTP')
        request('/api/logfiles/readers/'+reader['id'],token=token,method='DELETE')
        subprocess.run(['node',str(ROOT/'frontend/e2e/packaged-smoke.cjs')],
            cwd=ROOT/'frontend',env={**environment,'VIEWER_SMOKE_TOKEN':token},check=True)
        result['checks'].append('packaged desktop/phone archive viewer and expansion')
        result['checks'].append('embedded ten-rack deck preserves carrier order on desktop and phone with read-only fixtures')
        result['checks'].append('embedded compact connection details omit ambiguous metrics')
        time.sleep(.2)
        assert not list((relocated/'data/temp/log-readers').rglob('*.txt'))
        result['checks'].append('reader temporary file released')
        result['passed']=True
    finally:
        proc.terminate()
        try:proc.wait(timeout=15)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        result['exit_code']=proc.returncode
        result['stopped_by_test_harness']=True
        result['relocated_path']=str(relocated)
        (evidence/'packaged-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
