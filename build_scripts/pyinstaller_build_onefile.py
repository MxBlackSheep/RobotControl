"""
Convenience wrapper to build RobotControl as a single-file PyInstaller executable without a console window.
"""

from __future__ import annotations

import argparse
import sys

from pyinstaller_build import build_with_pyinstaller


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build RobotControl using PyInstaller (onefile, no-console by default)",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep console window open (disabled by default)",
    )
    args = parser.parse_args()

    success = build_with_pyinstaller(layout="onefile", console=args.console)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
