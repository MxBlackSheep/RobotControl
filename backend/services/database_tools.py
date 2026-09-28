"""Execution, confirmations and private temporary report files for database packages."""
from __future__ import annotations
from contextlib import closing

import hashlib
import json
import logging
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from backend.services.database import get_database_service
from backend.services.database_packages import PackageCatalogue, PackageError
from backend.utils.audit import log_action
from backend.utils.data_paths import get_path_manager

logger = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class DatabaseTools:
    def __init__(self, root, defaults, database=None, guard=None):
        self.root = Path(root)
        self.catalogue = PackageCatalogue(self.root / "packages", defaults)
        self.database = database or get_database_service()
        self.guard = guard or self._guard
        self.lock = threading.RLock()
        self.previews = {}
        self.jobs = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="database-report")
        self.slots = threading.BoundedSemaphore(2)
        self.receipts = self.root / "operations.sqlite3"
        with closing(sqlite3.connect(self.receipts)) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, owner TEXT NOT NULL, result TEXT NOT NULL)")
        self.temp = self.root / "reports"
        self.temp.mkdir(exist_ok=True)
        for child in self.temp.iterdir():
            if child.is_dir() and len(child.name) == 32 and all(c in '0123456789abcdef' for c in child.name):
                shutil.rmtree(child)
        self.stop = threading.Event()
        self.cleaner = threading.Thread(target=self._cleanup_loop, daemon=True, name="report-expiry")
        self.cleaner.start()

    @staticmethod
    def _guard():
        from backend.services.scheduling import get_scheduler_engine
        return get_scheduler_engine().database_change_guard()

    def _cleanup_loop(self):
        while not self.stop.wait(60):
            self.cleanup()

    def cleanup(self):
        with self.lock:
            self.previews = {key: value for key, value in self.previews.items() if value['expires'] > time.time()}
            for key, job in list(self.jobs.items()):
                if job['status'] not in {'pending', 'running'} and job['expires'] < time.time():
                    shutil.rmtree(self.temp / key, ignore_errors=True)
                    del self.jobs[key]

    def close(self):
        self.stop.set()
        self.cleaner.join(timeout=2)
        self.pool.shutdown(wait=True)
        for key in self.jobs:
            shutil.rmtree(self.temp / key, ignore_errors=True)

    def preview(self, tool_id, inputs, owner):
        with self.catalogue.reserve(tool_id, "operation") as (entry, tool):
            inputs = tool.validate_values(inputs)
            with self.database.get_connection() as conn:
                conn.timeout = 30
                result = self.catalogue.function(entry, tool.preview)(SimpleNamespace(connection=conn), inputs)
            token = uuid.uuid4().hex
            with self.lock:
                self.cleanup()
                if len(self.previews) >= 200:
                    raise PackageError("Too many open confirmations. Try again shortly.", 429)
                self.previews[token] = dict(owner=owner, tool_id=tool_id, inputs=inputs,
                    sha256=entry['sha256'], package_id=entry['manifest']['id'], package_version=entry['manifest']['version'], snapshot=digest(result), expires=time.time()+600)
            return dict(token=token, confirmation=str(inputs[tool.confirmation_field]), **result)

    def execute(self, token, confirmation, owner, client_ip):
        with self.lock, closing(sqlite3.connect(self.receipts)) as journal, journal:
            saved = journal.execute("SELECT owner, result FROM receipts WHERE id=?", (token,)).fetchone()
            if saved:
                if saved[0] != owner:
                    raise PackageError("Confirmation not found", 404)
                return json.loads(saved[1])
            preview = self.previews.get(token)
            if not preview or preview['owner'] != owner or preview['expires'] < time.time():
                raise PackageError("Confirmation expired. Preview the operation again.", 409)
            # Check the typed confirmation before consuming it.
            with self.catalogue.lock:
                _, entry, tool = self.catalogue.resolve(preview['tool_id'], 'operation')
                if str(preview['inputs'].get(tool.confirmation_field)) != confirmation:
                    raise PackageError("Confirmation does not match")
            pending = dict(status='unknown', message='Execution is in progress or was interrupted. Check the database before trying again.')
            journal.execute("INSERT INTO receipts VALUES (?, ?, ?)", (token, owner, json.dumps(pending)))
            journal.commit()
            del self.previews[token]
        committed = False
        committing = False
        try:
            with self.catalogue.reserve(preview['tool_id'], 'operation') as (entry, tool):
                if entry['sha256'] != preview['sha256']:
                    raise PackageError("Package changed. Preview the operation again.", 409)
                with self.guard(), self.database.get_connection() as conn:
                    conn.timeout = 30
                    context = SimpleNamespace(connection=conn)
                    try:
                        # Serializable protects the selected target until commit.
                        cursor = conn.cursor()
                        cursor.execute("SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                        cursor.close()
                        current = self.catalogue.function(entry, tool.preview)(context, preview['inputs'])
                        if digest(current) != preview['snapshot']:
                            raise PackageError("Experiment changed. Preview the operation again.", 409)
                        value = self.catalogue.function(entry, tool.entrypoint)(context, preview['inputs'])
                        committing = True
                        conn.commit()
                        committed = True
                        result = dict(status='succeeded', result=value, message=value.get('message', 'Operation completed.'))
                    except Exception:
                        conn.rollback()
                        raise
        except Exception as exc:
            logger.exception("Database operation failed")
            result = dict(status='unknown' if committing else 'error', message=('Commit could not be confirmed. Check the database before repeating. ' if committing else '') + str(exc))
        log_action(actor=owner, action=preview['tool_id'], scope='database', client_ip=client_ip,
                   success=committed, details=dict(inputs=preview['inputs'], package_id=preview['package_id'], package_version=preview['package_version'], package_sha256=preview['sha256'], outcome=result))
        try:
            with closing(sqlite3.connect(self.receipts)) as journal, journal:
                journal.execute("UPDATE receipts SET result=? WHERE id=?", (json.dumps(result, default=str), token))
        except Exception:
            logger.exception("Operation finished but its receipt could not be updated; never retry automatically")
            result['warning'] = 'Result could not be saved to the operation journal. Do not repeat without checking the database.'
        return result

    def start_report(self, tool_id, inputs, owner):
        if not self.slots.acquire(blocking=False):
            raise PackageError("Two reports are already running. Try again when one finishes.", 429)
        reservation = self.catalogue.reserve(tool_id, 'report')
        entered = False
        try:
            entry, tool = reservation.__enter__()
            entered = True
            inputs = tool.validate_values(inputs)
            key = uuid.uuid4().hex
            folder = self.temp / key
            folder.mkdir()
            with self.lock:
                self.jobs[key] = dict(id=key, owner=owner, status='pending', tool_id=tool_id,
                                     package_version=entry['manifest']['version'], expires=time.time()+900)
            self.pool.submit(self._report, key, entry, tool, inputs, reservation)
            return self.report(key, owner)
        except Exception:
            if entered:
                reservation.__exit__(None, None, None)
            self.slots.release()
            raise

    def _report(self, key, entry, tool, inputs, reservation):
        folder = self.temp / key
        with self.lock:
            self.jobs[key]['status'] = 'running'
        try:
            with self.database.get_connection() as conn:
                conn.timeout = 120
                output = self.catalogue.function(entry, tool.entrypoint)(SimpleNamespace(connection=conn, output_dir=folder), inputs)
            path = (folder / output).resolve()
            if path.parent != folder.resolve() or path.suffix != '.xlsx' or not path.is_file() or path.is_symlink():
                raise ValueError("Report did not produce an Excel file in its output directory")
            if path.stat().st_size > 100 * 1024 * 1024:
                raise ValueError("Report exceeds the 100 MiB download limit")
            with self.lock:
                self.jobs[key].update(status='ready', filename=path.name, expires=time.time()+900)
        except Exception as exc:
            logger.exception("Report %s failed (tool=%s, version=%s)", key, tool.id, entry['manifest']['version'])
            shutil.rmtree(folder, ignore_errors=True)
            with self.lock:
                self.jobs[key].update(status='error',
                    error=str(exc) if isinstance(exc, ValueError) else 'Report generation failed. Check Details or the RobotControl log.',
                    error_details=None if isinstance(exc, ValueError) else str(exc), expires=time.time()+900)
        finally:
            reservation.__exit__(None, None, None)
            self.slots.release()

    def report(self, key, owner):
        with self.lock:
            self.cleanup()
            job = self.jobs.get(key)
            if not job or job['owner'] != owner:
                raise PackageError("Report not found or expired", 404)
            return {name: value for name, value in job.items() if name != 'owner'}

    def download(self, key, owner):
        with self.lock:
            job = self.report(key, owner)
            if job['status'] != 'ready':
                raise PackageError("Report is not ready", 409)
            # Renew before FileResponse opens the file so cleanup cannot race download.
            self.jobs[key]['expires'] = time.time()+900
            return self.temp / key / job['filename']


_instance = None
_instance_lock = threading.Lock()


def get_database_tools():
    global _instance
    with _instance_lock:
        if _instance is None:
            defaults = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'database_packages'
            _instance = DatabaseTools(get_path_manager().data_path / 'database-tools', defaults)
        return _instance


def close_database_tools():
    global _instance
    if _instance:
        _instance.close()
        _instance = None
