"""Shared system metrics sampled outside the API event loop."""
from datetime import datetime, timezone
import logging
import os
import threading
import time
import psutil


class HealthSampler:
    def __init__(self, pid=None):
        self._lock = threading.Lock()
        # sample() runs on the sampler thread, or from snapshot() before the first sample exists.
        self._sample_lock = threading.Lock()
        self._snapshot = None
        self._stop = threading.Event()
        self._thread = None
        self._pid = pid or os.getpid()
        self._process_cpu = {}  # (pid, create_time) -> CPU seconds at the previous sample
        self._previous_sample = None  # (monotonic, wall clock) of the previous sample

    def sample(self):
        with self._sample_lock:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("C:" if psutil.WINDOWS else "/")
            result = {"timestamp": datetime.now(timezone.utc).isoformat(),
                      "cpu_percent": psutil.cpu_percent(interval=None),
                      "robotcontrol_cpu_percent": self._robotcontrol_cpu_percent(),
                      "memory_percent": memory.percent,
                      "memory_used_gb": round(memory.used / 1024**3, 2),
                      "memory_total_gb": round(memory.total / 1024**3, 2),
                      "disk_percent": disk.percent,
                      "disk_used_gb": round(disk.used / 1024**3, 2),
                      "disk_total_gb": round(disk.total / 1024**3, 2)}
        with self._lock:
            self._snapshot = result
        return dict(result)

    def _robotcontrol_cpu_percent(self):
        """CPU used by this process and all its descendants (camera helper, ffmpeg children, package
        scripts) since the previous sample, as % of the whole machine. None when unknown: on the
        first sample or when the process tree cannot be read.

        Processes are keyed by pid and start time, so a reused pid never inherits another's total.
        A child started since the previous sample counts from its start; CPU a child used after the
        previous sample is lost if it also exited before this one.
        """
        now, wall = time.monotonic(), time.time()
        previous, self._previous_sample = self._previous_sample, (now, wall)
        cpu_seconds, used = {}, 0.0
        try:
            root = psutil.Process(self._pid)
            tree = [root, *root.children(recursive=True)]
        except psutil.Error:
            self._process_cpu, self._previous_sample = {}, None
            return None
        for process in tree:
            try:
                with process.oneshot():
                    key = (process.pid, process.create_time())
                    times = process.cpu_times()
            except psutil.Error:
                continue  # exited while the tree was read
            cpu_seconds[key] = times.user + times.system
            if key in self._process_cpu:
                used += cpu_seconds[key] - self._process_cpu[key]
            elif previous and key[1] >= previous[1]:
                used += cpu_seconds[key]
        self._process_cpu = cpu_seconds
        logical_cpus = psutil.cpu_count()
        if not previous or not logical_cpus or now <= previous[0]:
            return None
        return round(min(100.0, max(0.0, 100 * used / ((now - previous[0]) * logical_cpus))), 1)

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
