"""Shared system metrics sampled outside the API event loop."""
from datetime import datetime, timezone
import logging
import threading
import psutil


class HealthSampler:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = None
        self._stop = threading.Event()
        self._thread = None

    def sample(self):
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:" if psutil.WINDOWS else "/")
        result = {"timestamp": datetime.now(timezone.utc).isoformat(),
                  "cpu_percent": psutil.cpu_percent(interval=None),
                  "memory_percent": memory.percent,
                  "memory_used_gb": round(memory.used / 1024**3, 2),
                  "memory_total_gb": round(memory.total / 1024**3, 2),
                  "disk_percent": disk.percent,
                  "disk_used_gb": round(disk.used / 1024**3, 2),
                  "disk_total_gb": round(disk.total / 1024**3, 2)}
        with self._lock:
            self._snapshot = result
        return dict(result)

    def snapshot(self):
        with self._lock:
            current = self._snapshot
        return dict(current) if current else self.sample()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="HealthSampler", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.sample()
            except Exception:
                logging.getLogger(__name__).exception("System metrics sample failed")
            self._stop.wait(5)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


health_sampler = HealthSampler()
