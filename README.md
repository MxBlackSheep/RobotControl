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

## Source Code

### Requirements
If you would like make changes and compile on your own machine, make sure the following dependencies is in place. 
- **Python** 3.11 (recommended)
- **Node.js** 18+ and npm.

#### Frontend
**Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

#### Backend
**Install packages**
   ```bash
pip install -r requirements.txt
   ```

### Build

#### Frontend
**Build Frontend**
   ```bash
   cd frontend
   npm run build
   ```

#### Backend
**PyInstaller-based Build**
   ```bash
python build_scripts/embed_resources.py
python build_scripts/pyinstaller_build_ondir.py or python build_scripts/pyinstaller_build_onefile.py
   ```

# Contacts/Issues

- This project will be primarily maintained by Andy Sun (sunfangziyue@gmail.com and zcbtunx@ucl.ac.uk)
- For usage issues please either log under 'Issues' on Github or contact Andy directly. 
