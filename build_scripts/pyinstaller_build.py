"""
PyInstaller build script for RobotControl executables.
Supports both onedir and onefile layouts without Visual C++ Build Tools.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _copy_directory_contents(src: Path, dst: Path) -> int:
    """Copy files from src directory into dst, skipping existing duplicates."""
    if not src.exists():
        return 0

    copied = 0
    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        target_root = dst / rel_root
        target_root.mkdir(parents=True, exist_ok=True)
        for filename in files:
            source_file = Path(root) / filename
            target_file = target_root / filename
            if target_file.exists():
                continue
            shutil.copy2(source_file, target_file)
            copied += 1
    return copied

def build_with_pyinstaller(layout: str = "onedir", console: bool = False) -> bool:
    """Build RobotControl with PyInstaller."""
    project_root = Path(".").resolve()
    backend_main = project_root / "backend" / "main.py"
    
    if not backend_main.exists():
        logger.error(f"Backend main file not found: {backend_main}")
        return False

    if layout not in {"onefile", "onedir"}:
        logger.error("Invalid layout: %s", layout)
        return False
    
    # Preserve existing backups inside dist before cleaning build artifacts
    dist_root = project_root / "dist"
    backup_candidates = [
        dist_root / "RobotControl" / "data" / "backups",
        dist_root / "data" / "backups",
        dist_root / "init" / "data" / "backups",
    ]
    dist_backups = next((candidate for candidate in backup_candidates if candidate.exists()), None)
    cache_root = project_root / ".build_cache"
    preserved_backups: Optional[Path] = None
    preserved_count = 0

    if dist_backups and dist_backups.exists():
        try:
            preserved_backups = cache_root / "dist_backups"
            if preserved_backups.exists():
                shutil.rmtree(preserved_backups)
            preserved_backups.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(dist_backups, preserved_backups)
            preserved_count = sum(1 for _ in preserved_backups.rglob("*") if _.is_file())
            logger.info("Preserved %s existing backup file(s) from %s", preserved_count, dist_backups)
        except Exception as exc:
            logger.warning("Could not preserve existing backup folder %s: %s", dist_backups, exc)
            preserved_backups = None

    # Clean previous builds (skip if files are locked)
    # for dir_name in ["build", "dist"]:
        # dir_path = project_root / dir_name
        # if dir_path.exists():
            # try:
                # shutil.rmtree(dir_path)
                # logger.info(f"Cleaned {dir_name} directory")
            # except PermissionError:
                # logger.warning(f"Could not clean {dir_name} directory (files may be in use) - continuing anyway")
    
    # PyInstaller command
    # Invoke via module to avoid PATH issues on some Windows setups
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(backend_main),

        "--name", "RobotControl",

        # Python path setup
        "--paths", ".",
        "--paths", str(project_root),
        
        # Add the entire backend directory as data
        "--add-data", f"{project_root / 'backend'};backend",
        
        # Include hidden imports with full paths
        "--hidden-import", "backend.embedded_static",
        "--hidden-import", "backend.services.embedded_resources", 
        "--hidden-import", "backend.utils.browser_launcher",
        "--hidden-import", "backend.utils.path_resolver",
        "--hidden-import", "backend.api.database",
        "--hidden-import", "backend.api.auth",
        "--hidden-import", "backend.api.admin",
        "--hidden-import", "backend.api.monitoring",
        "--hidden-import", "backend.api.experiments",
        "--hidden-import", "backend.api.backup",
        "--hidden-import", "backend.api.system_config",
        "--hidden-import", "backend.services.database",
        "--hidden-import", "backend.services.auth",
        "--hidden-import", "backend.services.monitoring",
        
        # Include passlib handlers
        "--hidden-import", "passlib.handlers.bcrypt",
        "--hidden-import", "passlib.handlers",
        "--hidden-import", "passlib.hash",
        
        # Include other commonly missing modules
        "--hidden-import", "pyodbc",
        "--hidden-import", "bcrypt",
        
        # Collect submodules
        "--collect-submodules", "backend",
        "--collect-all", "fastapi",
        "--collect-all", "uvicorn",
        "--collect-all", "pydantic",
        
        # Include required packages for OpenCV
        "--hidden-import", "numpy",
        "--hidden-import", "cv2",
        
        # Exclude unnecessary packages
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "jupyter",
        "--exclude-module", "IPython",
        
        # Optimization
        "--optimize", "2",
        
        # Output directory
        "--distpath", "dist",
        "--workpath", "build",
    ]

    if layout == "onefile":
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if console:
        cmd.append("--console")
    else:
        cmd.append("--noconsole")
    
    logger.info("Starting PyInstaller build...")
    logger.info("Layout: %s | Console: %s", layout, console)
    logger.info(f"Command: {' '.join(cmd[:10])}... (truncated)")
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=False, text=True)
        
        if result.returncode == 0:
            if layout == "onefile":
                exe_path = dist_root / "RobotControl.exe"
                support_root = dist_root
                if not exe_path.exists():
                    logger.error("Build succeeded but executable not found (onefile). Expected at %s", exe_path)
                    return False
            else:
                support_root = dist_root / "RobotControl"
                exe_path = support_root / "RobotControl.exe"

                if not support_root.exists():
                    logger.error("Onedir build output directory not found: %s", support_root)
                    return False
                if not exe_path.exists():
                    logger.error("Onedir build executable not found: %s", exe_path)
                    return False

            # Restore preserved backups into the newly built dist directory
            if preserved_backups and preserved_backups.exists():
                if layout == "onedir":
                    target_backups_dir = support_root / "data" / "backups"
                else:
                    target_backups_dir = dist_root / "data" / "backups"
                try:
                    restored = _copy_directory_contents(preserved_backups, target_backups_dir)
                    logger.info(
                        "Restored %s preserved backup file(s) into %s",
                        restored,
                        target_backups_dir,
                    )
                except Exception as exc:
                    logger.warning("Failed to restore preserved backups: %s", exc)
                finally:
                    shutil.rmtree(preserved_backups, ignore_errors=True)
            elif preserved_backups:
                shutil.rmtree(preserved_backups, ignore_errors=True)

            size_bytes = exe_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            
            logger.info("=" * 60)
            logger.info("[SUCCESS] BUILD SUCCESSFUL!")
            logger.info(f"[SUCCESS] Layout: {layout}")
            logger.info(f"[SUCCESS] Executable: {exe_path}")
            logger.info(f"[SUCCESS] Size: {size_mb:.1f} MB ({size_bytes:,} bytes)")
            logger.info(f"[SUCCESS] Target: {'ACHIEVED' if size_mb < 200 else 'EXCEEDED'} (<200MB)")
            if layout == "onedir":
                logger.info(f"[SUCCESS] Support files directory: {support_root}")
            logger.info("=" * 60)
            
            return True
        else:
            logger.error(f"PyInstaller build failed with return code {result.returncode}")
            return False
            
    except Exception as e:
        logger.error(f"Build error: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RobotControl using PyInstaller")
    parser.add_argument(
        "--layout",
        choices=["onefile", "onedir"],
        default="onedir",
        help="Select PyInstaller output layout (default: onedir)",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep console window open",
    )
    args = parser.parse_args()

    success = build_with_pyinstaller(layout=args.layout, console=args.console)
    sys.exit(0 if success else 1)
