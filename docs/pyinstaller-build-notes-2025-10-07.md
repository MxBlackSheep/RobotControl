PyInstaller Build Notes – 2025-10-07
====================================

Context
-------
- Encountered `ModuleNotFoundError: No module named 'pyodbc'` and a much smaller EXE when packaging with PyInstaller.
- Investigation showed the legacy `.venv` (Python 3.13) lacked compatible wheels, causing NumPy/OpenCV builds to fail and pyodbc not to bundle properly.

Actions Taken
-------------
- Created a dedicated Python 3.11 environment: `.venv311` (`C:\Users\BlackSheep\PycharmProjects\PyRobot\.venv311`).
- Installed the full dependency set (see `requirements.md`) plus PyInstaller 6.6.0 inside `.venv311`.
- Added helper scripts under `tools/` for auditing imports and verifying package availability:
  - `tools/list_imports.py` – scans the repo for import statements.
  - `tools/verify_imports.py` – imports all critical runtime packages; exits non-zero if any fail.
- Updated `PyRobot.spec` to exclude `pkg_resources` from the packaged binary to suppress runtime deprecation noise.
- Rebuilt via `.venv311\Scripts\python.exe -m PyInstaller PyRobot.spec` producing `dist\PyRobot.exe` (~79 MB) with bundled deps.

Verification
------------
- `tools/verify_imports.py` returns `ALL_OK` when run with `.venv311`.
- `dist\PyRobot.exe` launches without the `pkg_resources` deprecation warning.
- Build warning log (`build/PyRobot/warn-PyRobot.txt`) only lists optional/OS-specific modules.

Recommendations Going Forward
-----------------------------
1. **Use `.venv311`** for development and packaging (activate via `.\.venv311\Scripts\activate` on Windows).
2. Before packaging, ensure dependencies are current: `pip install -r requirements.md` (copy block) inside `.venv311`.
3. Run `python tools/verify_imports.py` to confirm third-party modules resolve before invoking PyInstaller.
4. Optional: Run `python build_scripts/embed_resources.py` prior to PyInstaller if you need the frontend embedded (larger EXE).
5. Keep virtualenv directories (`.venv`, `.venv311`) out of source control; `.gitignore` now enforces this.

Reference Commands
------------------
```
# Activate env
.\.venv311\Scripts\activate

# Install/refresh dependencies
pip install -r requirements.md
pip install PyInstaller==6.6.0

# Verify imports
python tools/verify_imports.py

# Build executable
python -m PyInstaller PyRobot.spec
```

