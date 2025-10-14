"""
Orchestrate the full build pipeline:
1. Build the frontend assets via npm.
2. Embed the generated static resources into the backend.
3. Build the PyInstaller executable/distribution.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List


logger = logging.getLogger("pyrobot.build")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full PyRobot build pipeline")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip the frontend npm build step",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip embedding frontend resources into the backend",
    )
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="Skip the PyInstaller build step",
    )
    parser.add_argument(
        "--pyinstaller-args",
        nargs=argparse.REMAINDER,
        default=None,
        help="Additional arguments passed to pyinstaller_build.py (prefix with '--' before first arg)",
    )
    return parser.parse_args()


def run_step(command: List[str], cwd: Path, description: str) -> None:
    logger.info("Starting: %s", description)
    logger.debug("Command: %s (cwd=%s)", command, cwd)
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{description} failed with exit code {result.returncode}")
    logger.info("Completed: %s", description)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent

    try:
        if not args.skip_frontend:
            run_step(
                ["npm", "run", "build"],
                cwd=project_root / "frontend",
                description="Frontend build (npm run build)",
            )
        else:
            logger.info("Skipping frontend build")

        if not args.skip_embed:
            run_step(
                [sys.executable, "build_scripts/embed_resources.py"],
                cwd=project_root,
                description="Embedding frontend resources",
            )
        else:
            logger.info("Skipping resource embedding")

        if not args.skip_pyinstaller:
            pyinstaller_cmd = [sys.executable, "build_scripts/pyinstaller_build.py"]
            if args.pyinstaller_args:
                pyinstaller_cmd.extend(args.pyinstaller_args)
            run_step(
                pyinstaller_cmd,
                cwd=project_root,
                description="PyInstaller build",
            )
        else:
            logger.info("Skipping PyInstaller build")

    except subprocess.SubprocessError as exc:
        logger.error("Build halted: %s", exc)
        return 1
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    logger.info("Build pipeline completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

