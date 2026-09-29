"""Read-only RobotControl/ZeroTier timing capture. No settings are changed.

Run on the affected browser's Windows PC during trouble:
  python network_probe.py --url http://10.215.61.125:8005 --samples 20
Run on the LabPC at the same time with --url http://127.0.0.1:8005.
Each run writes a separate timestamped JSON report alongside this script.
Use an administrator terminal if ZeroTier's CLI reports insufficient access.
"""
import argparse
import json
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://10.215.61.125:8005')
parser.add_argument('--samples', type=int, default=12)
parser.add_argument('--interval', type=float, default=2)
args = parser.parse_args()
if urlparse(args.url).scheme not in ('http', 'https') or args.samples < 1:
    parser.error('Use an HTTP(S) URL and at least one sample.')

cli = Path('C:/ProgramData/ZeroTier/One/zerotier-one_x64.exe')


def utc():
    return datetime.now(timezone.utc).isoformat()


def zerotier():
    result = {'at': utc()}
    if not cli.exists():
        return dict(result, error='ZeroTier CLI not found at the expected Windows path')
    for command in ['info', 'listnetworks', 'listpeers']:
        try:
            process = subprocess.run([str(cli), '-q', '-j', command], capture_output=True, text=True, timeout=10)
            result[command] = {'exit_code': process.returncode}
            try:
                result[command]['data'] = json.loads(process.stdout)
            except ValueError:
                result[command]['error'] = (process.stderr or process.stdout).strip()
        except subprocess.TimeoutExpired:
            result[command] = {'error': 'Local CLI query timed out'}
    return result


output = Path(__file__).with_name('network-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
report = {'host': socket.gethostname(), 'target': args.url, 'started': utc(), 'zerotier_before': zerotier(), 'samples': []}
for index in range(args.samples):
    path = '/' if index % 2 == 0 else '/health'
    row = {'at': utc(), 'path': path}
    command = ['curl.exe', '--noproxy', '*', '--connect-timeout', '8', '--max-time', '12', '--silent', '--show-error', '--output', 'NUL', '--write-out', '%{http_code}|%{time_connect}|%{time_starttransfer}|%{time_total}|%{remote_ip}|%{size_download}', args.url.rstrip('/')+path]
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=15)
        values = p.stdout.strip().split('|')
        row.update(exit_code=p.returncode, error=p.stderr.strip())
        if len(values) == 6:
            row.update(http_code=int(values[0]), connect_seconds=float(values[1]), first_byte_seconds=float(values[2]), total_seconds=float(values[3]), remote_ip=values[4], bytes_received=int(values[5]))
    except subprocess.TimeoutExpired:
        row['error'] = 'curl process exceeded 15 seconds'
    report['samples'].append(row)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(row), flush=True)
    if index+1 < args.samples:
        time.sleep(args.interval)
report['zerotier_after'] = zerotier()
report['finished'] = utc()
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print('REPORT='+str(output), flush=True)
