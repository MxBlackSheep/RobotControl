"""Repeatable System Status stall check: actual component, simulated API, real browser HTTP.
Run from the repository root: uv run --locked python frontend/e2e/status-stall-probe.py

Failures checked: a held health response must time out and recover (about 20 s);
Refresh must start a new request once it has; an HTTP 502 must show an error and
retry; releasing a late response must not change the display. No production services start.
Open the printed loopback URL; use Hold next health response, Refresh Data,
Allow new requests, wait over 20 seconds, press Refresh Data, then Release stalled response.
Evidence is saved to recovery/status-stall-evidence.json (Git-ignored). Stop with Ctrl+C.
"""
import json
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = threading.Lock()
RELEASE = threading.Event()
STATE = {"hold_next": False, "fail_next": False, "requests": [], "actions": [], "browser": []}

HTML = '''<!doctype html><html><head><meta charset="utf-8"><title>Remote connection reproduction</title></head>
<body style="font-family:Arial;margin:24px"><h1>Isolated remote-connection reproduction</h1>
<p>Actual System Status component; simulated API; no robot hardware or real credentials.</p>
<button onclick="control('hold')">Hold next health response</button>
<button onclick="control('allow')">Allow new requests</button>
<button onclick="control('release')">Release stalled response</button>
<button onclick="control('fail')">Fail next health response</button>
<pre id="probe-state"></pre><div id="root"></div>
<script>
localStorage.setItem('access_token','local-disposable-probe');
async function control(mode){await fetch('/control?mode='+mode,{method:'POST'});}
setInterval(async()=>{
 const root=document.getElementById('root');
 const refresh=root.querySelector('button');
 const sample={at:new Date().toISOString(),refresh_disabled:refresh?.disabled,
  has_spinner:!!root.querySelector('[role="progressbar"]'),
  connection_lost:root.innerText.includes('Monitoring connection lost'),
  connected_icon:!!root.querySelector('[data-testid="WifiIcon"]'),
  text:root.innerText.slice(0,1600)};
 const r=await fetch('/evidence',{method:'POST',body:JSON.stringify(sample)});
 document.getElementById('probe-state').textContent=JSON.stringify(await r.json(),null,2);
},2000);
</script><script type="module" src="/bundle.js"></script></body></html>'''


def now():
    return datetime.now(timezone.utc).isoformat()


def persist():
    (ROOT / 'recovery' / 'status-stall-evidence.json').write_text(json.dumps(STATE, indent=2), encoding='utf-8')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, code=200, content_type='application/json'):
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        try:
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/control':
            mode = parse_qs(parsed.query)['mode'][0]
            with LOCK:
                STATE['actions'].append({'at': now(), 'mode': mode})
                if mode == 'hold':
                    RELEASE.clear()
                    STATE['hold_next'] = True
                elif mode == 'allow':
                    STATE['hold_next'] = False
                elif mode == 'release':
                    RELEASE.set()
                elif mode == 'fail':
                    STATE['fail_next'] = True
                persist()
            return self.reply({'mode': mode})
        if parsed.path == '/evidence':
            sample = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with LOCK:
                STATE['browser'].append(sample)
                persist()
                health = [r for r in STATE['requests'] if r['path'].endswith('/system-health')]
                summary = {'health_requests': len(health), 'held_requests': sum(r.get('held', False) and not r.get('finished') for r in health), 'latest_health_request': health[-1] if health else None, 'refresh_disabled': sample.get('refresh_disabled'), 'connection_lost': sample['connection_lost'], 'connected_icon': sample['connected_icon']}
            return self.reply(summary)
        self.reply({}, 404)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self.reply(HTML.encode(), content_type='text/html')
        if path == '/bundle.js':
            return self.reply(self.server.bundle, content_type='text/javascript')
        row = {'path': path, 'started': now()}
        with LOCK:
            STATE['requests'].append(row)
            held = path.endswith('/system-health') and STATE['hold_next']
            fail = path.endswith('/system-health') and STATE['fail_next']
            if held:
                STATE['hold_next'] = False
                row['held'] = True
            if fail:
                STATE['fail_next'] = False
            persist()
        if held:
            RELEASE.wait(300)
        if fail:
            self.reply({'detail': 'Injected transient HTTP failure'}, 502)
        else:
            if path == '/api/auth/me':
                data = {'user_id': 'probe', 'username': 'probe', 'role': 'user', 'session': {'is_local': False}}
            elif path == '/api/monitoring/experiments':
                data = []
            elif path == '/api/monitoring/system-health':
                data = {'sampled_at': now(), 'system': {'cpu_percent': 5, 'memory_percent': 20, 'memory_used_gb': 2, 'memory_total_gb': 12, 'disk_percent': 20, 'disk_used_gb': 20, 'disk_total_gb': 100}, 'database': {'is_connected': True, 'mode': 'mock', 'database_name': 'Disposable fixture', 'server_name': 'loopback'}, 'connections': {'active': 1}}
            elif path == '/api/camera/streaming/status':
                data = {'status': {'enabled': True, 'active_session_count': 0, 'max_sessions': 10, 'total_bandwidth_mbps': 0, 'resource_usage_percent': 5}}
            else:
                data = {}
            self.reply({'success': True, 'data': data, 'metadata': {'timestamp': now()}})
        with LOCK:
            row['finished'] = now()
            row['code'] = 502 if fail else 200
            persist()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='robotcontrol-remote-probe-') as directory:
        bundle = Path(directory) / 'bundle.js'
        source = "import React from 'react'; import {createRoot} from 'react-dom/client'; import {AuthProvider} from './src/context/AuthContext'; import SystemStatus from './src/components/SystemStatus'; createRoot(document.getElementById('root')).render(<AuthProvider><SystemStatus /></AuthProvider>);"
        options = {'stdin': {'contents': source, 'resolveDir': str(ROOT / 'frontend'), 'loader': 'tsx'}, 'bundle': True, 'format': 'esm', 'outfile': str(bundle), 'define': {'import.meta.env.VITE_API_BASE_URL': '""', 'process.env.NODE_ENV': '"production"'}, 'alias': {'@': str(ROOT / 'frontend/src')}, 'minify': True}
        subprocess.run(['node', '-e', 'require("esbuild").buildSync('+json.dumps(options)+')'], cwd=ROOT / 'frontend', check=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.bundle = bundle.read_bytes()
        print(f'PROBE_URL=http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            RELEASE.set()
            server.server_close()
            with LOCK:
                persist()
