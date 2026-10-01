"""Verify a relocated Windows candidate with disposable data and automation disabled.

Run: .venv/Scripts/python.exe backend/e2e/packaged_viewer_smoke.py <candidate folder>
The candidate itself is preserved; its temporary relocated copy is removed.

Failure cases include: the packaged app publishes /docs, /openapi.json, source maps or the
bundle report through the remote tunnel; a missing hashed chunk answers index.html (200)
instead of 404, so pages fail to load after an upgrade; the relocated package cannot find or
start its own ffmpeg.exe for live view (or its kill-on-close Job Object), starts it with nobody
watching, keeps it after the viewer leaves, or leaves it running after RobotControl is killed.
No camera is attached, so this proves the encoder process boundary, not encoding.
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
import urllib.error
import urllib.request
from pathlib import Path

import psutil
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('candidate', type=Path)
args = parser.parse_args()
candidate = args.candidate.resolve()
assert (candidate/'RobotControl.exe').is_file(), candidate
evidence = ROOT/'test-output/viewer-verification'
evidence.mkdir(parents=True, exist_ok=True)
result = dict(candidate=str(candidate), checks=[], automation_disabled=True)


def wait_for(condition, seconds=10):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, condition
        time.sleep(.2)


def request(path, body=None, token=None, method=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request('http://127.0.0.1:8017'+path,
        data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=10) as response:
        data=response.read()
        return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data


with tempfile.TemporaryDirectory(prefix='relocated-viewer-',dir=ROOT/'test-output') as temp:
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
        # Reachable through the remote tunnel: no API description, maps or bundle report; a
        # missing chunk is 404 (not index.html) so the browser reloads instead of failing to parse.
        for hidden in ('/docs','/redoc','/openapi.json','/bundle-analysis.html','/assets/index-missing0.js','/assets/index-missing0.js.map'):
            try:
                request(hidden); raise AssertionError(f'{hidden} is served')
            except urllib.error.HTTPError as error:
                assert error.code==404,(hidden,error.code)
        assert 'assets/' in request('/scheduling').decode()
        result['checks'].append('no API docs, source maps or bundle report; missing assets 404, page routes serve the app')
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
        result['checks'].append('embedded rack scales from desktop to 4K')
        result['checks'].append('embedded full-width 40/60 workspace has aligned diagrams and circular dots')
        result['checks'].append('embedded focused tip has no repeating animation')
        result['checks'].append('embedded Cytomat preserves positions 1 through 7 and marks 8 and 9 unused')
        result['checks'].append('embedded Cytomat fills desktop width and remaining height')
        result['checks'].append('embedded connection facts shown in cards without ambiguous metrics')
        time.sleep(.2)
        assert not list((relocated/'data/temp/log-readers').rglob('*.txt'))
        result['checks'].append('reader temporary file released')

        def encoders():
            found = []
            for process in psutil.process_iter(['exe', 'ppid']):
                exe = process.info['exe']
                if exe and Path(exe).resolve() == (relocated/'ffmpeg.exe').resolve():
                    found.append(process)
            return found
        def viewer():
            session = request('/api/camera/streaming/session', token=token, method='POST')['data']
            return connect(f"ws://127.0.0.1:8017/api/camera/streaming/video/{session['session_id']}")
        encoder_running = lambda: request('/api/camera/streaming/status', token=token)['data']['status']['encoder']['running']
        assert (relocated/'ffmpeg.exe').is_file() and (relocated/'THIRD_PARTY_NOTICES'/'FFmpeg.txt').is_file()
        assert not encoders() and not encoder_running()
        with viewer():
            wait_for(lambda: encoders() and encoder_running())
            assert [process.info['ppid'] for process in encoders()] == [proc.pid]
            result['checks'].append("live view starts the relocated package's own ffmpeg.exe, as a RobotControl child, only once someone watches")
        wait_for(lambda: not encoders() and not encoder_running())
        result['checks'].append('the encoder stops when the last viewer leaves')
        with viewer():
            wait_for(encoders)
            proc.kill()  # TerminateProcess: no shutdown code runs; only the Job Object can end ffmpeg
            proc.wait(15)
            wait_for(lambda: not encoders())
        result['checks'].append('no ffmpeg.exe remains after RobotControl is killed while a viewer watches')
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
