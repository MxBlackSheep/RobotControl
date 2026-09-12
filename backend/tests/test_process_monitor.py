"""A failed WMI query must not let the scheduler dispatch to a busy robot."""

import subprocess
import threading
from unittest.mock import Mock

import pytest

from backend.services.scheduling import process_monitor


@pytest.fixture
def monitor(monkeypatch):
    # Avoid constructing a real COM client or inspecting host processes in tests.
    instance = object.__new__(process_monitor.HamiltonProcessMonitor)
    instance._wmi = Mock()
    monkeypatch.setattr(process_monitor.platform, "system", lambda: "Windows")
    return instance


@pytest.mark.parametrize("processes,expected", [([], False), ([object()], True)])
def test_successful_wmi_query_needs_no_fallback(monitor, monkeypatch, processes, expected):
    monitor._wmi.Win32_Process.return_value = processes
    fallback = Mock()
    monkeypatch.setattr(process_monitor.subprocess, "run", fallback)
    assert monitor.is_hamilton_running() is expected
    fallback.assert_not_called()


@pytest.mark.parametrize("output,expected", [("HxRun.exe 123 Console", True), ("No tasks match", False)])
def test_worker_wmi_failure_uses_tasklist(monitor, monkeypatch, output, expected):
    monitor._wmi.Win32_Process.side_effect = RuntimeError("CoInitialize has not been called")
    fallback = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output))
    monkeypatch.setattr(process_monitor.subprocess, "run", fallback)
    results = []
    worker = threading.Thread(target=lambda: results.append(monitor.is_hamilton_running()))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert results == [expected]
    assert fallback.call_args.args[0] == ["tasklist", "/FI", "IMAGENAME eq HxRun.exe"]
    assert fallback.call_args.kwargs["check"] is True


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("tasklist", 5), subprocess.CalledProcessError(1, "tasklist")])
def test_all_detection_failures_block_dispatch(monitor, monkeypatch, failure):
    monitor._wmi.Win32_Process.side_effect = RuntimeError("WMI unavailable")
    monkeypatch.setattr(process_monitor.subprocess, "run", Mock(side_effect=failure))
    assert monitor.is_hamilton_running() is True
