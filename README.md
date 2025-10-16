# RobotControl

Join different system utilities and provide unified control surface for the ShouGroup Hamilton Liquid Handling Robot.

# Usage

## Run-Time Logs, Backups, and Data Paths
- Rotating backend logs live in `data/logs/` (main + error aliases). Leftover `performance_*.log` files are legacy artifacts and can be deleted safely.
- Automatic recordings accumulate in `data/videos/` (clean periodically).
- Database backups `data/backups/`;
- Scheduling metadata persists in `data/robotcontrol_scheduling.db`; removing it resets the scheduler state.
- User Auth persists in `data/robotcontrol_auth.db`; Local admin generated automatically with default username "admin" and password "ShouGroupAdmin"

## SQL Server Access
- PyODBC-backed service to view database, perform basic operations and restore the database if needed.

## Camera Access for Recording and Streaming
- Unified `CameraService` handles detection, rolling recordings, archiving, and live streams.

## Scheduling Engine
- SQLite-backed job store and queue with retry policy, grace windows, and manual recovery gating.

## Repository Layout
```
backend/                  FastAPI application (routers, services, utils, tests)
frontend/                 React + Vite client (TypeScript, MUI)
build_scripts/            Asset embedding & PyInstaller automation
docs/                     Supplemental design, logging, and scheduling notes
```

# Installation

## Compiled Release

This repository provides compiled binary release that could be run directly on target machine. To fully utilize the features implemented, please make sure:
- PYODBC driver has been installed on the target machine (https://learn.microsoft.com/en-us/sql/connect/python/pyodbc/python-sql-driver-pyodbc?view=sql-server-ver17)
- [optional]: USB Webcam is connected.

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
The generated binary appears under `dist/`; runtime assets (logs, backups, videos) live beside the executable in `data/`.

# Contacts/Issues

- This project will be primarily maintained by Andy Sun (sunfangziyue@gmail.com and zcbtunx@ucl.ac.uk)
- For usage issues please either log under 'Issues' on Github or contact Andy directly. 
