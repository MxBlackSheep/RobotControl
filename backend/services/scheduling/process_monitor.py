"""
Hamilton Process Monitoring Service

Monitors Hamilton HxRun.exe process status for scheduling system.
Replicates VBS script functionality for process detection and availability checking.

Features:
- Thread-independent process inspection using psutil, with tasklist fallback
- Process availability detection and waiting
- Hamilton robot status monitoring
"""

import csv
import logging
import threading
import subprocess
import platform
import os
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)

# Development mode detection - if HxRun.exe is not available
# Process monitor for Hamilton HxRun.exe processes


@dataclass
class ProcessInfo:
    """Information about a running process"""
    process_id: int
    process_name: str
    command_line: Optional[str]
    start_time: Optional[datetime]


class HamiltonProcessMonitor:
    """Process monitoring service for Hamilton HxRun.exe"""
    
    def __init__(self):
        """
        Initialize the Hamilton process monitor
        """
        self._monitoring = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        logger.info("Hamilton process monitor initialized")
    
    def start_monitoring(self, check_interval: float = 5.0) -> bool:
        """
        Start process monitoring in background thread
        
        Args:
            check_interval: Seconds between process checks
            
        Returns:
            bool: True if monitoring started successfully
        """
        try:
            if self._monitoring:
                logger.warning("Process monitoring already running")
                return True
            if self._monitor_thread and self._monitor_thread.is_alive():
                logger.warning("Previous process monitor is still stopping")
                return False
            
            self._stop_event.clear()
            self._monitoring = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                args=(check_interval,),
                daemon=True,
                name="HamiltonProcessMonitor"
            )
            self._monitor_thread.start()
            
            logger.info("Hamilton process monitoring started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start process monitoring: {e}")
            self._monitoring = False
            return False
    
    def stop_monitoring(self):
        """Stop process monitoring"""
        self._monitoring = False
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        logger.info("Hamilton process monitoring stopped")
    
    def is_hamilton_running(self) -> bool:
        """Return whether HxRun is running; block dispatch if detection fails."""
        try:
            return bool(self.get_hamilton_processes())
        except Exception as exc:
            logger.error("Cannot determine Hamilton availability; blocking dispatch: %s", exc)
            return True

    def get_hamilton_processes(self) -> List[ProcessInfo]:
        """Inspect HxRun from any thread. Raise if neither detector is usable."""
        if platform.system() != "Windows":
            return []
        try:
            return self._read_psutil_processes()
        except Exception as exc:
            logger.debug("Process inspection failed; using tasklist: %s", exc)
            return self._read_tasklist_processes()

    @staticmethod
    def _read_psutil_processes() -> List[ProcessInfo]:
        processes = []
        for proc in psutil.process_iter(["pid", "name"]):
            info = dict(proc.info)
            name = info.get("name")
            if not name:
                raise RuntimeError(f"Cannot inspect process name for PID {proc.pid}")
            if name.lower() != "hxrun.exe":
                continue
            try:
                # Access to optional details may be denied even when the name is readable.
                details = proc.as_dict(attrs=["cmdline", "create_time"], ad_value=None)
            except psutil.NoSuchProcess:
                continue
            command = details.get("cmdline")
            created = details.get("create_time")
            processes.append(ProcessInfo(
                process_id=info["pid"], process_name=name,
                command_line=subprocess.list2cmdline(command) if command else None,
                start_time=datetime.fromtimestamp(created) if created is not None else None,
            ))
        return processes

    @staticmethod
    def _read_tasklist_processes() -> List[ProcessInfo]:
        # Unfiltered CSV avoids localized "no matching tasks" messages.
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
            timeout=5, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        rows = list(csv.reader(result.stdout.splitlines()))
        if not rows or any(len(row) < 2 or not row[1].isdigit() for row in rows):
            raise RuntimeError("tasklist returned an unreadable process list")
        return [ProcessInfo(int(row[1]), row[0], None, None)
                for row in rows if row[0].lower() == "hxrun.exe"]
    
    def _monitor_loop(self, check_interval: float):
        """Log changes; dispatch and status requests always inspect processes live."""
        previous = None
        while self._monitoring:
            reason = None
            try:
                processes = self.get_hamilton_processes()
                state = "busy" if processes else "available"
            except Exception as exc:
                state, reason = "error", str(exc)
            if state != previous:
                if reason:
                    logger.error("Hamilton status changed: error; blocking dispatch: %s", reason)
                else:
                    logger.info("Hamilton status changed: %s (%s processes)", state, len(processes))
                previous = state
            self._stop_event.wait(check_interval)


# Singleton instance management
_process_monitor_instance = None
_process_monitor_lock = threading.Lock()


def get_hamilton_process_monitor() -> HamiltonProcessMonitor:
    """
    Get the singleton HamiltonProcessMonitor instance
    
    Returns:
        HamiltonProcessMonitor: The process monitor instance
    """
    global _process_monitor_instance
    
    with _process_monitor_lock:
        if _process_monitor_instance is None:
            _process_monitor_instance = HamiltonProcessMonitor()
            
    return _process_monitor_instance
