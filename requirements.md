RobotControl Requirements and Packaging Guide

This document enumerates all third‑party dependencies used by the active backend, plus system prerequisites and reproducible build steps. Use this as the single source of truth to avoid ModuleNotFoundError issues (e.g., `pyodbc`).

System Requirements
- OS: Windows 10/11 (x64) recommended
- Python: 3.10 or 3.11 (use the same version for dev and packaging)
- Microsoft ODBC Driver for SQL Server: v17 or v18 (required for `pyodbc`)
  - Example: “Microsoft ODBC Driver 18 for SQL Server”
- Microsoft Visual C++ Redistributable x64: recommended

Complete Python Dependency List (application)
- fastapi==0.111.0
- uvicorn[standard]==0.30.0
- pydantic==2.7.1
- passlib==1.7.4
- bcrypt==4.1.3
- PyJWT==2.8.0  # imported as `jwt`
- pyodbc==5.1.0
- requests==2.31.0
- psutil==5.9.8
- numpy==1.26.4
- opencv-python==4.10.0.84  # provides `cv2`
- pillow==10.3.0  # provides `PIL` (optional; used by system tray)
- pystray==0.19.5  # optional; system tray integration
- python-multipart==0.0.9  # optional; only needed if using file uploads

Build/Packaging Tools
- PyInstaller==6.6.0

Copy‑ready requirements.txt (all runtime deps)
fastapi==0.111.0
uvicorn[standard]==0.30.0
pydantic==2.7.1
passlib==1.7.4
bcrypt==4.1.3
PyJWT==2.8.0
pyodbc==5.1.0
requests==2.31.0
psutil==5.9.8
numpy==1.26.4
opencv-python==4.10.0.84
pillow==10.3.0
pystray==0.19.5
python-multipart==0.0.9

Quick install
- Create/activate a virtualenv that matches your target Python version.
- `pip install -U pip setuptools wheel`
- `pip install -r requirements.txt` (use the block above if you don’t track a file)
- For packaging: `pip install PyInstaller==6.6.0`

Notes on `pyodbc`
- Import errors usually mean the system ODBC driver is missing. Install Microsoft ODBC Driver 17/18 for SQL Server on the host.
- Architecture must match: 64‑bit Python needs the 64‑bit ODBC driver.

Embedding Frontend (affects EXE size)
- To include the web UI in the binary, run: `python build_scripts/embed_resources.py` (creates `backend/embedded_static.py` from `frontend/dist`).
- Without this step, the EXE will be much smaller than historic builds that bundled the UI.

Build with PyInstaller
Option A — spec file (repeatable)
- `python build_scripts/embed_resources.py` (optional but recommended)
- `pyinstaller RobotControl.spec`

Option B — helper script
- `python build_scripts/pyinstaller_build.py`
- Already includes hidden‑imports for `pyodbc`, `bcrypt`, `passlib.handlers.*`, and collects `fastapi`, `uvicorn`, `pydantic`, `numpy`, `cv2`.

Operational Checks
- Start backend: `cd backend && python main.py --port 8005`
- Warm DB: `python -c "from backend.services.database import get_database_service; print(get_database_service().get_status())"`
- Logs: latest under `data/logs/robotcontrol_backend_*.log`
- Camera smoke tests: `python tmp_test_camera.py`

Change Management
- When adding a new import under `backend/`, add its pip package here and, if PyInstaller misses it, extend hidden‑imports or collect‑all in `RobotControl.spec` or `build_scripts/pyinstaller_build.py`.
