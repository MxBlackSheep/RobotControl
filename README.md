# RobotControl

Join different system utilities and provide unified control surface for the ShouGroup Hamilton Liquid Handling Robot.

# Usage

## Run-Time Logs, Backups, and Data Paths
- Auto-generated folder to hold run-time data. 
- Rotating backend logs live in `data/logs/` (main + error aliases). 
- Automatic recordings accumulate in `data/videos/` (clean periodically).
- Database backups `data/backups/`;
- Scheduling metadata persists in `data/robotcontrol_scheduling.db`; removing it resets the scheduler state.
- User Auth persists in `data/robotcontrol_auth.db`; Local admin generated automatically with default username "admin" and password "ShouGroupAdmin"

## SQL Server Access
- PyODBC-backed service to view database, perform basic operations and restore the database if needed.

## Camera Access for Recording and Streaming
- Camera service to handle detection, rolling recordings, archiving, and live streams.

## Scheduling Engine
- SQLite-backed job store and queue with retry policy, grace windows, and manual recovery gating.

## Repository Layout

### backend/ 
- FastAPI application (routers, services, utils, tests)
### frontend/
- React + Vite client (TypeScript, MUI)
### build_scripts/   
- Asset embedding & PyInstaller automation
### Others
- docs: Supplemental design and logging
- AGENTS.md: This project was developed with OpenAI CodeX. This file provides some basic context if to work with CodeX.

# Installation

## Compiled Release

This repository provides compiled binary release that could be run directly on target machine. To fully utilize the features implemented, please make sure:
- ODBC driver has been installed on the target machine ([Microsoft ODBC Driver](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server?view=sql-server-ver17))
- [optional]: To use camera service please make sure at least one camera is connected to the PC.

## Local Usage

For local usage, double-click the binary to run the application. Then access the frontend interface via `localhost:8005`

## Remote Usage

To access RobotControl remotely (e.g. From mobile/other PCs), a static IP address or VPN is required. For simplicity, we recommended using [ZeroTier](https://www.zerotier.com/download/)
- The host needs to join the virtual network and obtain a managed IP address [e.g. 192.168.xxx.xxx]
- The remote device needs to join the same virtual network as the host, connect to ZeroTier, then access RobotControl via 192.168.xxx.xxx:8005. 

## Source Code (Windows)

### First setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Node.js 24 LTS with npm](https://nodejs.org/en/download). Open a new PowerShell
window after installation so the commands are on PATH. Run all commands below
from the **RobotControl repository root**.

```powershell
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
```

uv automatically installs the Python version in `.python-version` (64-bit Python
3.14.7) and creates `.venv`. No separate Python installation or environment
activation is needed. `pyproject.toml` declares dependencies; `uv.lock` records the
exact versions for repeatable installations. Commit both when dependencies change.

### Run

```powershell
uv run --locked python backend/main.py --host 127.0.0.1 --port 8005 --no-browser
```

Open [RobotControl](http://127.0.0.1:8005). The backend serves the built frontend.
Local authentication uses SQLite and works without SQL Server. The default account
is `admin` / `ShouGroupAdmin`; change its password after first login. Stop the
server with Ctrl+C. For frontend development, run `npm --prefix frontend run dev`
in another terminal and open port 3005; API requests are proxied to port 8005.

SQL Server, its Microsoft ODBC driver, cameras, and the Hamilton software are
separate machine dependencies. uv installs Python packages, not those drivers or
services. Unavailable integrations can report errors while the web app and local
login remain usable. Only start schedules when the target robot is configured.

To work on the interface without starting scheduled jobs or automatic recordings,
set these optional flags in the same PowerShell window before starting the app:

```powershell
$env:ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS = "disable"
$env:ROBOTCONTROL_AUTO_RECORDING_ENABLED = "0"
```

These flags also work with the executable. Without them, existing automatic-start
behavior is preserved.

### Test and manage Python dependencies

```powershell
uv run --locked python -m pytest backend/tests
uv lock --check
uv pip check
```

The default `dev` dependency group includes pytest and HTTPX. Use `uv sync --locked
--no-dev` for runtime dependencies only. PyInstaller belongs to the opt-in `build`
group. Windows-only packages (including WMI and pywin32) have platform markers.

Use `uv add PACKAGE`, `uv add --dev PACKAGE`, or `uv remove PACKAGE` to change
dependencies. To update an existing package, run `uv lock --upgrade-package PACKAGE`,
then `uv sync --locked` and the tests. Review and commit the manifest and lockfile.
Passlib **1.7.4** and bcrypt **4.3.0** are deliberately pinned together to preserve
password compatibility; bcrypt 5 requires a separate password-library migration.

### Build the Windows executable

```powershell
npm --prefix frontend run build
uv run --locked python build_scripts/embed_resources.py
uv run --locked --group build python build_scripts/pyinstaller_build.py --layout onedir
```

The output is `dist/RobotControl/RobotControl.exe`. Copy the **whole RobotControl
folder**, including `_internal`, to the target Windows machine. It does not need
Python, uv, or Node installed. Runtime data stays in the `data` folder beside the
executable. Keep that folder when updating a deployed installation.

Use `--layout onefile` instead for `dist/RobotControl.exe`, or add `--console` to
show diagnostic output. The convenience scripts `pyinstaller_build_onedir.py`
and `pyinstaller_build_onefile.py` accept `--console` too; run either with
`uv run --locked --group build python build_scripts/SCRIPT_NAME.py`.

### Existing Linux container recipe

After building the frontend, run from the repository root:

```powershell
docker build -f backend/Dockerfile -t robotcontrol .
docker run --rm -p 8005:8005 -v robotcontrol-data:/app/data robotcontrol
```

The backend image uses the same uv lockfile and serves the frontend on port 8005.
It includes ODBC Driver 18, but the application's SQL connection configuration must
be adapted to the container's reachable server and installed driver. Windows-only
Hamilton integration and DPAPI secret storage are unavailable in Linux. This
recipe is aligned with uv; Linux deployment has not been verified by this migration.

# Contacts/Issues

- This project will be primarily maintained by Andy Sun (sunfangziyue@gmail.com and zcbtunx@ucl.ac.uk)
- For usage issues please either log under 'Issues' on Github or contact Andy directly. 
