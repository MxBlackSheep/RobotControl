"""
Global HxRun maintenance mode enforcement.

When enabled, this service blocks all HxRun launches by:
- exposing a persistent flag in scheduling SQLite state
- polling for HxRun once a second
- terminating HxRun if detected while maintenance mode is active
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import subprocess
import threading
import time
from typing import Optional

from backend.models import HxRunMaintenanceState
from backend.services.scheduling.database_manager import get_scheduling_database_manager
from backend.services.scheduling.process_monitor import get_hamilton_process_monitor

logger = logging.getLogger(__name__)


PROCESS_NAME = "HxRun.exe"
IDLE_SLEEP_SECONDS = 0.5
POLL_SECONDS = 1.0
POPUP_COOLDOWN_SECONDS = 10.0
STATE_REFRESH_SECONDS = 1.0


class HxRunMaintenanceService:
    """Singleton service that stores and enforces HxRun maintenance mode."""

    def __init__(self) -> None:
        self.db_manager = get_scheduling_database_manager()
        self.process_monitor = get_hamilton_process_monitor()

        self._state_lock = threading.RLock()
        self._cached_state = HxRunMaintenanceState()
        self._last_state_refresh = 0.0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._last_popup_at = 0.0

        # Prime cache once to avoid first-call latency.
        try:
            self.get_state(force_refresh=True)
        except Exception:
            logger.exception('Maintenance state unavailable at startup; storage review remains accessible')

    def start(self) -> None:
        """Start background enforcement thread if not already running."""
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._enforcement_loop,
                name="HxRunMaintenanceEnforcer",
                daemon=True,
            )
            self._thread.start()
            logger.info("HxRun maintenance enforcer started")

    def stop(self) -> None:
        """Stop background enforcement thread."""
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3.0)
        logger.info("HxRun maintenance enforcer stopped")

    def get_state(self, *, force_refresh: bool = True) -> HxRunMaintenanceState:
        """Return cached maintenance state, optionally forcing a DB refresh."""
        now = time.time()
        with self._state_lock:
            if (
                not force_refresh
                and (now - self._last_state_refresh) < STATE_REFRESH_SECONDS
            ):
                return self._cached_state

            state = self.db_manager.get_hxrun_maintenance_state()
            self._cached_state = state
            self._last_state_refresh = now
            return state

    def set_state(
        self,
        *,
        enabled: bool,
        reason: Optional[str],
        actor: str,
    ) -> HxRunMaintenanceState:
        """Persist and cache maintenance mode updates."""
        if enabled:
            from backend.services.scheduling.pyhsl_runner import require_no_active_run
            require_no_active_run()
        next_state = self.db_manager.set_hxrun_maintenance_state(enabled, reason, actor)
        with self._state_lock:
            self._cached_state = next_state
            self._last_state_refresh = time.time()

        # Keep enforcer alive so external HxRun starts are blocked as soon as enabled.
        self.start()
        return next_state

    def is_enabled(self) -> bool:
        """Fast helper used by scheduler/executor guards."""
        return bool(self.get_state(force_refresh=False).enabled)

    def is_hxrun_running(self) -> bool:
        """Return whether HxRun.exe is currently running."""
        return self.process_monitor.is_hamilton_running()

    def _enforcement_loop(self) -> None:
        """Poll while enabled; failed detection still counts as running."""
        while not self._stop_event.is_set():
            try:
                state = self.get_state(force_refresh=False)
            except Exception:
                logger.exception('Maintenance storage unavailable; keeping enforcement worker alive')
                self._stop_event.wait(IDLE_SLEEP_SECONDS)
                continue
            if not state.enabled:
                self._stop_event.wait(IDLE_SLEEP_SECONDS)
                continue
            if self.is_hxrun_running():
                self._handle_hxrun_detected(source="poll")
            self._stop_event.wait(POLL_SECONDS)

    def _handle_hxrun_detected(self, *, source: str) -> None:
        """Terminate blocked HxRun process and notify operator."""
        state = self.get_state(force_refresh=False)
        if not state.enabled:
            return

        terminated = self._terminate_hxrun_processes()
        logger.warning(
            "Blocked HxRun while maintenance mode is enabled (source=%s, terminated=%s)",
            source,
            terminated,
        )
        # Notify only after taskkill reports a termination.
        if terminated > 0:
            self._show_block_popup(state)

    def _terminate_hxrun_processes(self) -> int:
        """Terminate all HxRun.exe processes and return best-effort count."""
        if platform.system() != "Windows":
            return 0

        killed_count = 0

        try:
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                ["taskkill", "/F", "/IM", PROCESS_NAME],
                capture_output=True,
                text=True,
                timeout=5,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            if result.returncode == 0:
                # taskkill can kill more than one process; use output count as best effort.
                output = (result.stdout or "") + "\n" + (result.stderr or "")
                killed_count = max(1, output.count("SUCCESS:"))
        except Exception as exc:  # pragma: no cover - depends on host process state
            logger.warning("taskkill failed for HxRun: %s", exc)

        return killed_count

    def _show_block_popup(self, state: HxRunMaintenanceState) -> None:
        """Show operator-facing warning when HxRun is blocked."""
        if platform.system() != "Windows":
            return

        now = time.time()
        if (now - self._last_popup_at) < POPUP_COOLDOWN_SECONDS:
            return
        self._last_popup_at = now

        reason = state.reason or "HxRun maintenance mode is currently enabled."
        message = (
            "HxRun launch blocked.\n\n"
            f"{reason}\n\n"
            "Disable HxRun Maintenance Mode in RobotControl before launching HxRun."
        )
        title = "RobotControl - HxRun Maintenance Mode"

        try:
            user32 = ctypes.windll.user32
            # MB_ICONWARNING (0x30) + MB_TOPMOST (0x00040000)
            user32.MessageBoxW(0, message, title, 0x30 | 0x00040000)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Unable to show HxRun maintenance popup: %s", exc)


_hxrun_maintenance_service: Optional[HxRunMaintenanceService] = None
_hxrun_maintenance_lock = threading.Lock()


def get_hxrun_maintenance_service() -> HxRunMaintenanceService:
    """Return singleton HxRunMaintenanceService."""
    global _hxrun_maintenance_service
    with _hxrun_maintenance_lock:
        if _hxrun_maintenance_service is None:
            _hxrun_maintenance_service = HxRunMaintenanceService()
    return _hxrun_maintenance_service
