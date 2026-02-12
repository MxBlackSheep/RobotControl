"""
Global HxRun maintenance mode enforcement.

When enabled, this service blocks all HxRun launches by:
- exposing a persistent flag in scheduling SQLite state
- watching for HxRun process starts (event-driven when possible)
- falling back to periodic process checks
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
from dataclasses import dataclass
from typing import Any, Callable, Optional

from backend.models import HxRunMaintenanceState
from backend.services.scheduling.database_manager import get_scheduling_database_manager
from backend.services.scheduling.process_monitor import get_hamilton_process_monitor

logger = logging.getLogger(__name__)


@dataclass
class HxRunMaintenanceConfig:
    """Runtime controls for the maintenance enforcer loop."""

    process_name: str = "HxRun.exe"
    idle_sleep_seconds: float = 0.5
    fallback_poll_seconds: float = 1.0
    event_timeout_seconds: float = 0.8
    event_retry_seconds: float = 30.0
    popup_cooldown_seconds: float = 10.0
    state_refresh_seconds: float = 1.0


class HxRunMaintenanceService:
    """Singleton service that stores and enforces HxRun maintenance mode."""

    def __init__(self, config: Optional[HxRunMaintenanceConfig] = None) -> None:
        self.config = config or HxRunMaintenanceConfig()
        self.db_manager = get_scheduling_database_manager()
        self.process_monitor = get_hamilton_process_monitor()

        self._state_lock = threading.RLock()
        self._cached_state = HxRunMaintenanceState()
        self._last_state_refresh = 0.0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._wmi_client: Any = None
        self._process_start_watcher: Optional[Callable[..., Any]] = None
        self._next_event_retry_at = 0.0

        self._last_popup_at = 0.0

        # Prime cache once to avoid first-call latency.
        self.get_state(force_refresh=True)

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
                and (now - self._last_state_refresh) < self.config.state_refresh_seconds
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

    def _enforcement_loop(self) -> None:
        """Background loop: event watcher + fallback polling."""
        next_poll_at = 0.0

        while not self._stop_event.is_set():
            state = self.get_state(force_refresh=False)
            if not state.enabled:
                self._process_start_watcher = None
                self._stop_event.wait(self.config.idle_sleep_seconds)
                continue

            event_handled = self._check_event_watcher()

            now = time.time()
            if now >= next_poll_at:
                next_poll_at = now + max(self.config.fallback_poll_seconds, 0.2)
                if self._is_hxrun_running():
                    self._handle_hxrun_detected(source="poll")

            if not event_handled:
                self._stop_event.wait(0.1)

    def _check_event_watcher(self) -> bool:
        """Check one event watcher cycle; returns True when an event is handled."""
        if platform.system() != "Windows":
            return False

        now = time.time()
        if self._process_start_watcher is None and now >= self._next_event_retry_at:
            self._process_start_watcher = self._build_process_start_watcher()
            if self._process_start_watcher is None:
                self._next_event_retry_at = now + self.config.event_retry_seconds

        watcher = self._process_start_watcher
        if watcher is None:
            return False

        try:
            event = watcher(timeout_ms=int(self.config.event_timeout_seconds * 1000))
            if event:
                self._handle_hxrun_detected(source="event")
                return True
            return False
        except Exception as exc:  # pragma: no cover - depends on wmi runtime behavior
            name = exc.__class__.__name__.lower()
            message = str(exc).lower()
            if "timed out" in name or "timed out" in message:
                return False
            logger.warning("HxRun event watcher failed; retrying with fallback poll: %s", exc)
            self._process_start_watcher = None
            self._next_event_retry_at = time.time() + self.config.event_retry_seconds
            return False

    def _build_process_start_watcher(self) -> Optional[Callable[..., Any]]:
        """Create a WMI process-start watcher for HxRun.exe."""
        if platform.system() != "Windows":
            return None
        try:
            if self._wmi_client is None:
                import wmi  # type: ignore

                self._wmi_client = wmi.WMI()
            return self._wmi_client.Win32_ProcessStartTrace.watch_for(
                "creation",
                ProcessName=self.config.process_name,
            )
        except Exception as exc:  # pragma: no cover - depends on host OS/libs
            logger.warning("Unable to initialize HxRun event watcher: %s", exc)
            return None

    def _is_hxrun_running(self) -> bool:
        try:
            return self.process_monitor.is_hamilton_running()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("HxRun fallback poll failed: %s", exc)
            return False

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
        # Event path should always notify; poll path only notifies if a process was terminated.
        if source == "event" or terminated > 0:
            self._show_block_popup(state)

    def _terminate_hxrun_processes(self) -> int:
        """Terminate all HxRun.exe processes and return best-effort count."""
        if platform.system() != "Windows":
            return 0

        killed_count = 0

        if self._wmi_client is not None:
            try:
                for proc in self._wmi_client.Win32_Process(name=self.config.process_name):
                    proc.Terminate()
                    killed_count += 1
            except Exception as exc:  # pragma: no cover - depends on WMI host permissions
                logger.warning("WMI terminate failed for HxRun: %s", exc)

        if killed_count > 0:
            return killed_count

        try:
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                ["taskkill", "/F", "/IM", self.config.process_name],
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
            logger.warning("taskkill fallback failed for HxRun: %s", exc)

        return killed_count

    def _show_block_popup(self, state: HxRunMaintenanceState) -> None:
        """Show operator-facing warning when HxRun is blocked."""
        if platform.system() != "Windows":
            return

        now = time.time()
        if (now - self._last_popup_at) < self.config.popup_cooldown_seconds:
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

