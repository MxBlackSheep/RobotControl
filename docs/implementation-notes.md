## 2025-10-14
- Hid the Hamilton process monitor `tasklist` fallback window by running it with `CREATE_NO_WINDOW`.
- Added dedicated `pyinstaller_build_onefile.py` and `pyinstaller_build_onedir.py` wrappers that keep PyInstaller’s default layout and default to no-console builds.

## 2025-10-14
- Added `build_scripts/run_full_build.py` to run frontend build, embed step, and PyInstaller in one command with optional skips/extra args.
- Updated `build_scripts/pyinstaller_build.py` to support a configurable `--layout` (default `onedir`) and optional console flag.
- Onedir builds now ship as `dist/pyrobot.exe` plus `dist/init/` holding support files instead of the previous single-file executable.
