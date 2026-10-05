"""Start a relocated packaged RobotControl on a port nobody else holds, and prove it answers.

Used by packaged_viewer_smoke.py, packaged_walkthrough.py and packaged_database_smoke.py.
PACKAGED_E2E_PORT overrides each check's port (default 8017; the database smoke 8018), so
two worktrees can run packaged checks at once, for example $env:PACKAGED_E2E_PORT='8027'.

The app is identified by the process that owns the listening socket: /health carries no
identity, and no production route is added for tests. Failure cases:
- the port is already in use (another worktree's app or any other program): refuse before
  starting, naming the PID and program, and send it nothing;
- another process starts listening on the port while ours starts: refuse;
- ours exits, or does not listen within the time limit: refuse with its exit code.
Each caller stops only the process it started (in its finally block); nothing here stops
or calls a shutdown route on a server it did not start.
"""
import os
import socket
import subprocess
import time

import psutil


def port(default):
    value = os.environ.get('PACKAGED_E2E_PORT')
    if not value:
        return default
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise SystemExit(f'PACKAGED_E2E_PORT={value!r} is not a port number between 1024 and 65535.')
    return int(value)


def _listeners(number):
    return {c.pid for c in psutil.net_connections('tcp')
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == number}


def _describe(pids):
    names = []
    for pid in sorted(pids):
        try:
            names.append(f'PID {pid} ({psutil.Process(pid).exe()})')
        except (psutil.Error, OSError):
            names.append(f'PID {pid}')
    return ', '.join(names) or 'an unidentified process'


def _refuse(message, number):
    raise SystemExit(f'{message} This check tests only an app it started, so it stopped without '
                     f'sending that server anything. Stop that program, or choose a free port, '
                     f"for example $env:PACKAGED_E2E_PORT='{number + 10}'.")


def launch(relocated, environment, number):
    """Start the relocated executable after confirming nothing holds the port."""
    holders = _listeners(number)
    if not holders:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(('127.0.0.1', number))
            except OSError as error:
                _refuse(f'Port {number} is already in use ({error.strerror}).', number)
    else:
        _refuse(f'Port {number} is already in use by {_describe(holders)}.', number)
    return subprocess.Popen([str(relocated / 'RobotControl.exe'), '--host', '127.0.0.1', '--port', str(number),
                             '--no-browser'], cwd=relocated, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)


def wait_until_serving(process, number, health, seconds=90):
    """Return once only `process` listens on the port and its /health answers.

    No request is sent until the listening socket is shown to be ours."""
    deadline = time.monotonic() + seconds
    while True:
        holders = _listeners(number)
        if holders - {process.pid}:
            _refuse(f'Port {number} was taken by {_describe(holders - {process.pid})} while RobotControl '
                    f'(PID {process.pid}) was starting.', number)
        if process.pid in holders:
            break
        if process.poll() is not None:
            raise SystemExit(f'RobotControl (PID {process.pid}) exited with code {process.returncode} '
                             f'before listening on port {number}.')
        if time.monotonic() > deadline:
            raise SystemExit(f'RobotControl (PID {process.pid}) did not listen on port {number} within {seconds} s.')
        time.sleep(.5)
    while True:
        try:
            return health()
        except Exception:
            if process.poll() is not None or time.monotonic() > deadline:
                raise
            time.sleep(.5)

