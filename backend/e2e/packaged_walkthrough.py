"""Open every page of a relocated Windows candidate in a real browser and record what breaks.

Run: uv run --locked python backend/e2e/packaged_walkthrough.py <candidate folder>
Uses disposable login data, an unreachable SQL Server address and disabled automation,
like packaged_viewer_smoke.py. Evidence: test-output/packaged-walkthrough/<candidate name>/
(summary.json, visits.json and one screenshot per page/section). The candidate is preserved.
Port: 8017, or PACKAGED_E2E_PORT; it refuses a port already in use (see packaged_app.py).

Pass criteria: no API 401/403/404/405 for the local admin, no failed asset, no page error or lazy-load failure, no blank
page, and no 5xx except where the page depends on the unreachable SQL Server (listed for review).
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.e2e import packaged_app

PORT = packaged_app.port(8017)
parser = argparse.ArgumentParser()
parser.add_argument('candidate', type=Path)
args = parser.parse_args()
candidate = args.candidate.resolve()
assert (candidate / 'RobotControl.exe').is_file(), candidate
evidence = ROOT / 'test-output/packaged-walkthrough' / candidate.parent.name
if evidence.exists():
    shutil.rmtree(evidence)
evidence.mkdir(parents=True)


def request(path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}' + path,
                                 data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())


summary = dict(candidate=str(candidate), sql_server='127.0.0.1,1 (deliberately unreachable)', automation_disabled=True)
with tempfile.TemporaryDirectory(prefix='relocated-walkthrough-', dir=ROOT / 'test-output') as temp:
    relocated = Path(temp) / 'RobotControl'
    shutil.copytree(candidate, relocated, ignore=shutil.ignore_patterns('data'))
    password = secrets.token_urlsafe(24)
    environment = {**os.environ, 'ROBOTCONTROL_AUTO_RECORDING_ENABLED': 'false',
                   'ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS': 'disabled',
                   'ROBOTCONTROL_ADMIN_USERNAME': 'walkthrough', 'ROBOTCONTROL_ADMIN_PASSWORD': password,
                   'ROBOTCONTROL_ACCESS_TOKEN_SECRET': secrets.token_urlsafe(32),
                   'ROBOTCONTROL_REFRESH_TOKEN_SECRET': secrets.token_urlsafe(32),
                   'VM_SQL_SERVER': '127.0.0.1,1', 'PACKAGED_E2E_PORT': str(PORT)}
    proc = packaged_app.launch(relocated, environment, PORT)
    try:
        packaged_app.wait_until_serving(proc, PORT, lambda: request('/health'))
        token = request('/api/auth/login', dict(username='walkthrough', password=password))['data']['access_token']
        request('/api/auth/change-password', dict(current_password=password, new_password=secrets.token_urlsafe(24)), token)
        subprocess.run(['node', str(ROOT / 'frontend/e2e/packaged-walkthrough.cjs')], cwd=ROOT / 'frontend', check=True,
                       env={**environment, 'WALKTHROUGH_TOKEN': token, 'WALKTHROUGH_EVIDENCE': str(evidence)})
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

visits = json.loads((evidence / 'visits.json').read_text(encoding='utf-8'))
problems, server_errors = [], []
for visit in visits:
    for r in visit['requests']:
        # A local admin may use every page, so a refusal is also a defect here.
        if r['status'] in (401, 403, 404, 405) or r['status'] == 'failed' and r['path'].startswith('/assets/'):
            problems.append(f"{visit['url']}: {r['method']} {r['path']} -> {r['status']}")
        elif isinstance(r['status'], int) and r['status'] >= 500:
            server_errors.append(f"{visit['url']}: {r['method']} {r['path']} -> {r['status']}")
    problems += [f"{visit['url']}: {e}" for e in visit['errors'] if 'status of 5' not in e and 'status of 4' not in e]
    if visit['loadFailure']:
        problems.append(f"{visit['url']}: lazy-load or error boundary text shown")
    if visit['visibleCharacters'] < 20:
        problems.append(f"{visit['url']}: page is blank")
summary.update(pages_visited=len(visits), problems=problems, server_errors_for_review=sorted(set(server_errors)),
               passed=not problems)
(evidence / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
