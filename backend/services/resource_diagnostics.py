"""Opt-in, bounded resource measurements; never initialize operational services."""

import json
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone

import psutil


def runtime_counts():
    """Inspect already loaded services only. No payloads, credentials or SQL queries."""
    counts = {"python_threads": threading.active_count()}
    targets = (
        ("backend.services.live_streaming", "_service_instance", "streaming", ("sessions", "sessions_by_user")),
        ("backend.services.shared_frame_buffer", "_shared_buffer_instance", "frames", ("buffer", "streaming_callbacks")),
        ("backend.services.database", "_service_instance", "database", ("_table_columns_cache",)),
        ("backend.services.embedded_resources", "_resource_manager", "static", ("_cache",)),
    )
    for module_name, attribute, prefix, fields in targets:
        service = getattr(sys.modules.get(module_name), attribute, None)
        if service is None:
            continue
        for field in fields:
            value = getattr(service, field, None)
            if value is not None:
                counts[f"{prefix}.{field}"] = len(value)
        if prefix == "frames":
            with service.streaming_lock:
                counts["frames.bytes"] = sum(frame.size_bytes for frame in service.buffer)
        if prefix == "streaming":
            counts["streaming.delivery_tasks"] = len(getattr(service, "_delivery_tasks", {}))
    camera = getattr(sys.modules.get("backend.services.camera"), "_camera_service", None)
    if camera is not None:
        health = camera.runtime.status()
        for field in ("generation", "capture_state", "recording_state", "frame_sequence",
                      "last_frame_age_seconds", "last_write_age_seconds", "heartbeat_age_seconds", "read_failures"):
            counts[f"camera.{field}"] = health[field]
    return counts


class ResourceDiagnostics:
    """One owned thread and a maximum 25 MiB JSONL log set per process."""

    def __init__(self, directory: Path, interval=60, pid=None, loop=None):
        self.directory = Path(directory)
        self.interval = interval
        self.pid = pid or os.getpid()
        self.loop = loop
        self._stop = threading.Event()
        self._thread = None
        self._handler = None
        self._processes = {}
        self._logger = logging.Logger(f"resource-diagnostics-{self.pid}", logging.INFO)

    def sample(self):
        root = psutil.Process(self.pid)
        tree = {root.pid, *(p.pid for p in root.children(recursive=True))}
        rows, retained = [], {}
        for candidate in psutil.process_iter(["pid", "name", "create_time"]):
            name = (candidate.info["name"] or "").lower()
            group = "robotcontrol" if candidate.pid in tree else (
                "sql_server" if name == "sqlservr.exe" else
                "browser" if name in {"chrome.exe", "msedge.exe", "firefox.exe"} else None)
            if group is None:
                continue
            key = (candidate.pid, candidate.info["create_time"])
            process = self._processes.get(key, candidate)
            retained[key] = process
            try:
                with process.oneshot():
                    memory = process.memory_info()
                    io = process.io_counters()
                    rows.append({
                        "pid": process.pid, "name": name, "group": group,
                        "working_set_bytes": memory.rss,
                        "private_bytes": getattr(memory, "private", None),
                        "cpu_percent_one_core": process.cpu_percent(interval=None),
                        "threads": process.num_threads(),
                        "handles": process.num_handles() if hasattr(process, "num_handles") else None,
                        "read_bytes": io.read_bytes, "write_bytes": io.write_bytes,
                    })
            except (psutil.Error, OSError) as exc:
                rows.append({"pid": process.pid, "name": name, "group": group, "unavailable": type(exc).__name__})
        self._processes = retained  # Dead processes must not accumulate across reconnects.
        memory = psutil.virtual_memory()
        runtime = runtime_counts() if self.pid == os.getpid() else {}
        if self.loop and self.loop.is_running():
            async def task_count():
                return len(asyncio.all_tasks()) - 1
            future = asyncio.run_coroutine_threadsafe(task_count(), self.loop)
            try:
                runtime["asyncio_tasks"] = future.result(timeout=2)
            except Exception:
                future.cancel()
                runtime["asyncio_tasks"] = None
        return {"observed_at": datetime.now(timezone.utc).isoformat(),
                "root_pid": self.pid, "logical_cpus": psutil.cpu_count(),
                "system": {"total_bytes": memory.total, "available_bytes": memory.available,
                           "used_bytes": memory.used, "percent": memory.percent},
                "processes": rows, "runtime": runtime}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        self._handler = RotatingFileHandler(self.directory / f"resources-{self.pid}.jsonl",
                                           maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8")
        self._logger.addHandler(self._handler)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ResourceDiagnostics", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._logger.info(json.dumps(self.sample(), separators=(",", ":")))
            except Exception as exc:
                self._logger.info(json.dumps({"diagnostic_error": type(exc).__name__}))
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                return  # Keep ownership until the worker actually exits.
            self._thread = None
        if self._handler:
            self._logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None
        self._processes.clear()
