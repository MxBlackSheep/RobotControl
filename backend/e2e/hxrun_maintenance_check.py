"""Maintenance polling kills only a disposable process, without WMI.

Run with the worktree Python and PYTHONPATH. No robot software is started or
inspected. A renamed Windows ping executable supplies the disposable process.
Failure cases: polling does not enforce maintenance, disabled maintenance kills
the process, WMI is still attempted, or shutdown leaves the worker alive.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

from backend.models import HxRunMaintenanceState
from backend.services.scheduling import process_monitor  # Match application import order.
from backend.services import hxrun_maintenance as maintenance


def run():
    if os.name != "nt":
        raise RuntimeError("This check needs Windows taskkill")
    maintenance.platform.system()  # Resolve platform before guarding subprocess calls.
    with tempfile.TemporaryDirectory(prefix="rc-maintenance-") as folder:
        executable = Path(folder) / f"rc_poll_{uuid.uuid4().hex}.exe"
        shutil.copy2(Path(os.environ["SystemRoot"]) / "System32/ping.exe", executable)
        process = subprocess.Popen(
            [str(executable), "-t", "127.0.0.1"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        state = HxRunMaintenanceState(enabled=False)
        database = Mock()
        database.get_hxrun_maintenance_state.side_effect = lambda: state
        monitor = SimpleNamespace(is_hamilton_running=lambda: process.poll() is None)
        real_run = subprocess.run

        def taskkill(command, **kwargs):
            # Never permit this check to target HxRun or another process name.
            assert command == ["taskkill", "/F", "/IM", executable.name], command
            result = real_run(command, **kwargs)
            if result.returncode:
                print(f"taskkill returned {result.returncode}: {result.stdout} {result.stderr}")
            return result

        service = None
        try:
            with patch.object(maintenance, "get_scheduling_database_manager", return_value=database), \
                 patch.object(maintenance, "get_hamilton_process_monitor", return_value=monitor), \
                 patch.object(maintenance, "PROCESS_NAME", executable.name, create=True), \
                 patch.object(maintenance.subprocess, "run", side_effect=taskkill), \
                 patch.dict("sys.modules", {"wmi": None}):
                service = maintenance.HxRunMaintenanceService()
                service._show_block_popup = Mock()
                service.start()
                time.sleep(1.2)
                assert process.poll() is None, "Disabled maintenance killed the process"
                state.enabled = True
                service.get_state(force_refresh=True)
                process.wait(timeout=5)
                service.stop()
                assert not service._thread.is_alive()
                assert not hasattr(service, "_process_start_watcher"), "WMI path remains"
        finally:
            if service is not None:
                service.stop()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
    print("PASS: disabled maintenance preserves the disposable process; polling/taskkill ends it; worker stops")


if __name__ == "__main__":
    run()
