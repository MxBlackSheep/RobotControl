"""Process inspection must work across threads and fail closed when unavailable."""

import subprocess
import threading
from datetime import datetime
from unittest.mock import Mock

import psutil
import pytest

from backend.services.scheduling import process_monitor


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr(process_monitor.platform, "system", lambda: "Windows")
    return process_monitor.HamiltonProcessMonitor()


def fake_process(pid=123, name="HxRun.exe", details=None):
    proc = Mock()
    proc.pid = pid
    proc.info = {"pid": pid, "name": name}
    proc.as_dict.return_value = details or {"cmdline": ["HxRun.exe", "C:\\Methods\\demo.med"], "create_time": 1000}
    return proc


@pytest.mark.parametrize("name,expected", [("hxrun.EXE", True), ("Other.exe", False)])
def test_main_and_worker_inspection_agree(monitor, monkeypatch, name, expected):
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([fake_process(name=name)]))
    fallback = Mock(side_effect=AssertionError("No fallback expected"))
    monkeypatch.setattr(process_monitor.subprocess, "run", fallback)
    assert monitor.is_hamilton_running() is expected
    results = []
    worker = threading.Thread(target=lambda: results.append(monitor.get_hamilton_processes()))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert bool(results[0]) is expected
    if expected:
        assert results[0][0].process_id == 123
        assert results[0][0].start_time == datetime.fromtimestamp(1000)
        assert "demo.med" in results[0][0].command_line
    fallback.assert_not_called()


def test_missing_optional_details_still_marks_busy(monitor, monkeypatch):
    proc = fake_process(details={"cmdline": None, "create_time": None})
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([proc]))
    info = monitor.get_hamilton_processes()[0]
    assert info.command_line is None
    assert info.start_time is None
    assert monitor.is_hamilton_running()


def test_process_exiting_during_inspection_is_ignored(monitor, monkeypatch):
    proc = fake_process()
    proc.as_dict.side_effect = psutil.NoSuchProcess(123)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([proc]))
    assert not monitor.is_hamilton_running()


@pytest.mark.parametrize("output,expected", [
    ('"HxRun.exe","123","Console","1","12,345 K"', True),
    ('"Other.exe","456","Console","1","1,234 K"', False),
])
def test_failed_inspection_uses_csv_tasklist_for_both_callers(monitor, monkeypatch, output, expected):
    monkeypatch.setattr(psutil, "process_iter", Mock(side_effect=psutil.AccessDenied()))
    fallback = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output))
    monkeypatch.setattr(process_monitor.subprocess, "run", fallback)
    assert monitor.is_hamilton_running() is expected
    assert bool(monitor.get_hamilton_processes()) is expected
    assert fallback.call_args.args[0] == ["tasklist", "/FO", "CSV", "/NH"]
    assert fallback.call_args.kwargs["timeout"] == 5
    assert fallback.call_args.kwargs["check"] is True


def test_unreadable_name_cannot_be_assumed_unrelated(monitor, monkeypatch):
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter([fake_process(name=None)]))
    fallback = Mock(return_value=subprocess.CompletedProcess([], 0, stdout='"HxRun.exe","123"'))
    monkeypatch.setattr(process_monitor.subprocess, "run", fallback)
    assert monitor.is_hamilton_running()
    fallback.assert_called_once()


@pytest.mark.parametrize("output", ["", "ERROR: Access denied", '"HxRun.exe","not a PID"'])
def test_unreadable_fallback_blocks_dispatch(monitor, monkeypatch, output):
    monkeypatch.setattr(psutil, "process_iter", Mock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(process_monitor.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output)))
    assert monitor.is_hamilton_running()
    with pytest.raises(RuntimeError):
        monitor.get_hamilton_processes()


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("tasklist", 5), subprocess.CalledProcessError(1, "tasklist")])
def test_all_detection_failures_block_dispatch_and_publish_error(monitor, monkeypatch, failure, caplog):
    monkeypatch.setattr(psutil, "process_iter", Mock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(process_monitor.subprocess, "run", Mock(side_effect=failure))
    assert monitor.is_hamilton_running()
    monitor._monitoring = True
    monkeypatch.setattr(monitor._stop_event, "wait", lambda _: setattr(monitor, "_monitoring", False))
    monitor._monitor_loop(0)
    assert "Hamilton status changed: error; blocking dispatch:" in caplog.text


def test_background_status_recovers_and_logs_only_changes(monitor, monkeypatch, caplog):
    readings = iter([[fake_process()], [fake_process()], [], []])
    monkeypatch.setattr(monitor, "get_hamilton_processes", lambda: next(readings))
    count = 0
    def wait(_):
        nonlocal count
        count += 1
        monitor._monitoring = count < 4
    monkeypatch.setattr(monitor._stop_event, "wait", wait)
    monitor._monitoring = True
    with caplog.at_level("INFO"):
        monitor._monitor_loop(0)
    assert caplog.text.count("Hamilton status changed: busy") == 1
    assert caplog.text.count("Hamilton status changed: available") == 1
