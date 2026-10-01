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
import copy
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from backend.services.database import get_database_service
from backend.services.database_packages import PackageCatalogue, PackageError
from backend.services.report_sources import ReportSources, lookup_rows
from backend.utils.audit import log_action
from backend.utils.data_paths import get_path_manager

logger = logging.getLogger(__name__)
REPORT_TIMEOUT_SECONDS = 300
# Preparation is short data setup before a launch; a longer step is treated as hung.
PREPARATION_TIMEOUT_SECONDS = 120


class PreparationFailed(Exception):
    """A preparation step did not complete. status: 'failed' (nothing was committed) or
    'unknown' (the commit may have happened; an operator must check before resuming)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class DatabaseTools:
    def __init__(self, root, defaults, database=None, guard=None):
        self.root = Path(root)
        self.catalogue = PackageCatalogue(self.root / "packages", defaults)
        self.catalogue.in_use = self.schedules_using
        self.database = database or get_database_service()
        self.sources = ReportSources(self.root)
        from backend.services.database_access import DatabaseAccess
        self.access = DatabaseAccess(self.sources)
        from backend.services.report_authoring import ReportAuthoring
        self.authoring = ReportAuthoring(self.root, self)
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
            with self.guard(), self.catalogue.lock, self.sources.lock:
                target = self.sources.operation_target(entry['manifest']['id'])
                choices = self.sources.snapshot(entry['manifest']['id'], tool.sources)
                with self.sources.connections(choices) as connections, self.sources.open(target) as conn:
                    conn.timeout = 30
                    self.validate_choices(tool, inputs, connections)
                    try:
                        result = self.catalogue.function(entry, tool.preview)(SimpleNamespace(connection=conn, connections=connections), inputs)
                    finally:
                        conn.rollback()
            token = uuid.uuid4().hex
            with self.lock:
                self.cleanup()
                if len(self.previews) >= 200:
                    raise PackageError("Too many open confirmations. Try again shortly.", 429)
                self.previews[token] = dict(owner=owner, tool_id=tool_id, inputs=inputs,
                    target=target, choices=choices, sha256=entry['sha256'], package_id=entry['manifest']['id'], package_version=entry['manifest']['version'], snapshot=digest(result), expires=time.time()+600)
            return dict(token=token, confirmation=str(inputs[tool.confirmation_field]), target=self.target_label(target), **result)

    def preview_draft(self, draft, inputs):
        """Explicit authoring trial: preview only, without an execution token."""
        catalogue = self.authoring.trials
        with catalogue.reserve(draft.package_id, 'operation') as (entry, tool):
            inputs = tool.validate_values(inputs)
            with self.sources.lock:
                target = self.sources.get(draft.operation_source, 'operation')
                snapshot = self.sources.snapshot(draft.package_id, tool.sources, draft.mappings)
                with self.sources.connections(snapshot) as connections, self.sources.open(target) as conn:
                    self.validate_choices(tool, inputs, connections)
                    try:
                        result = catalogue.function(entry, tool.preview)(SimpleNamespace(connection=conn, connections=connections), inputs)
                    finally:
                        conn.rollback()
            if not isinstance(result, dict):
                raise PackageError('Preview must return a summary and details dictionary.')
            return dict(summary=result.get('summary', ''), details=result.get('details', {}), target=self.target_label(target))

    @staticmethod
    def target_label(target):
        return f"{target['name']} · {target['server']} / {target['database']}"

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
                # Hold configuration lock through commit; a target cannot be edited
                # or remapped between this check and the destructive transaction.
                with self.guard(), self.catalogue.lock, self.sources.lock:
                    target = self.sources.operation_target(preview['package_id'])
                    if target != preview['target']:
                        raise PackageError('Connection changed. Review the operation again.', 409)
                    if self.sources.snapshot(preview['package_id'], tool.sources) != preview['choices']:
                        raise PackageError('Choice connections changed. Review the operation again.', 409)
                    result, committing, committed = self._execute_operation(entry, tool, preview, target)
        except Exception as exc:
            logger.exception("Database operation failed")
            result = dict(status='unknown' if committing else 'error', message=('Commit could not be confirmed. Check the database before repeating. ' if committing else '') + str(exc))
        log_action(actor=owner, action=preview['tool_id'], scope='database', client_ip=client_ip,
                   success=committed, details=dict(target=self.target_label(preview['target']), target_revision=preview['target'].get('revision'), inputs=preview['inputs'], package_id=preview['package_id'], package_version=preview['package_version'], package_sha256=preview['sha256'], outcome=result))
        try:
            with closing(sqlite3.connect(self.receipts)) as journal, journal:
                journal.execute("UPDATE receipts SET result=? WHERE id=?", (json.dumps(result, default=str), token))
        except Exception:
            logger.exception("Operation finished but its receipt could not be updated; never retry automatically")
            result['warning'] = 'Result could not be saved to the operation journal. Do not repeat without checking the database.'
        return result

    def _execute_operation(self, entry, tool, preview, target):
        committing = committed = False
        try:
            with self.sources.connections(preview['choices']) as connections, self.sources.open(target) as conn:
                conn.timeout = 30
                context = SimpleNamespace(connection=conn, connections=connections)
                try:
                    # Serializable protects the selected target until commit.
                    cursor = conn.cursor()
                    cursor.execute("SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    cursor.close()
                    self.validate_choices(tool, preview['inputs'], connections)
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
        return result, committing, committed

    def public_catalogue(self, kind):
        tools = copy.deepcopy(self.catalogue.tools(kind))
        for tool in tools:
            if kind == 'report':
                try:
                    self.sources.snapshot(tool['package_id'], self.sources.aliases(self.catalogue.index[tool['package_id']]['manifest']))
                    tool['setup_needed'] = False
                except PackageError:
                    tool['setup_needed'] = True
            else:
                try:
                    self.sources.snapshot(tool['package_id'], tool.get('sources', []))
                    target = self.sources.operation_target(tool['package_id'])
                    tool['target'] = self.target_label(target)
                    tool['setup_needed'] = False
                except PackageError:
                    tool['setup_needed'] = True
            for field in tool['inputs']:
                if field.get('lookup'):
                    field['lookup'] = {k: v for k, v in field['lookup'].items() if k in {'parameters', 'value_type'}}
        return tools

    @staticmethod
    def validate_choices(tool, inputs, connections):
        for field in tool.inputs:
            if field.lookup and field.name in inputs:
                options = lookup_rows(connections[field.lookup.source], field, inputs, selected=inputs[field.name])['options']
                if not any(x['value'] == inputs[field.name] for x in options):
                    raise PackageError(f'{field.label} is no longer available. Choose it again.')

    def choices(self, tool_id, field_name, inputs, search, page, catalogue=None, mapping=None, kind='report'):
        catalogue = catalogue or self.catalogue
        with catalogue.reserve(tool_id, kind) as (entry, tool):
            values = tool.validate_values(inputs, partial=True)
            field = next((x for x in tool.inputs if x.name == field_name and x.lookup), None)
            if field is None:
                raise PackageError('Database choice not found', 404)
            snapshot = self.sources.snapshot(entry['manifest']['id'], tool.sources if entry['manifest']['contract_version'] == 2 else ['primary'], mapping)
            with self.sources.open(snapshot[field.lookup.source]) as conn:
                return lookup_rows(conn, field, values, search, page)

    def report_experiments(self, tool_id, search, page):
        with self.catalogue.reserve(tool_id, 'report') as (entry, tool):
            if not any(x.type == 'experiment' for x in tool.inputs):
                raise PackageError('Report has no experiment input', 404)
            snapshot = self.sources.snapshot(entry['manifest']['id'], tool.sources if entry['manifest']['contract_version'] == 2 else ['primary'])
            with self.sources.open(snapshot.get('primary', next(iter(snapshot.values())))) as conn, conn.cursor() as cursor:
                pattern = '%' + search.replace('[', '[[]').replace('%', '[%]').replace('_', '[_]') + '%'
                where = '(CAST(ExperimentID AS nvarchar(40)) LIKE ? OR UserDefinedID LIKE ? OR Note LIKE ?)'
                params = [pattern] * 3
                total = cursor.execute('SELECT COUNT(*) FROM dbo.Experiments WHERE ' + where, params).fetchone()[0]
                rows = cursor.execute('SELECT ExperimentID, UserDefinedID, Note FROM (SELECT ExperimentID, UserDefinedID, Note, ROW_NUMBER() OVER (ORDER BY ExperimentID DESC) AS rn FROM dbo.Experiments WHERE ' + where + ') AS numbered WHERE rn>? AND rn<=? ORDER BY rn', params + [(page-1)*25, page*25]).fetchall()
                return dict(rows=[dict(zip(('ExperimentID', 'UserDefinedID', 'Note'), row)) for row in rows], total_count=total)

    def operation_experiments(self, tool_id, search, page):
        from backend.services.workspace_database import WorkspaceDatabase
        with self.catalogue.reserve(tool_id, 'operation') as (entry, tool):
            if not any(x.type == 'experiment' for x in tool.inputs):
                raise PackageError('Operation has no experiment input', 404)
            target = self.sources.operation_target(entry['manifest']['id'])
            db = WorkspaceDatabase(self.sources, target)
            result = db.get_table_data('[dbo].[Experiments]', limit=25, offset=(page-1)*25,
                                       search=search, order_by='ExperimentID', sort_direction='desc')
            return dict(rows=result.rows, total_count=result.total_count)

    def start_report(self, tool_id, inputs, owner, catalogue=None, mapping=None):
        catalogue = catalogue or self.catalogue
        if not self.slots.acquire(blocking=False):
            raise PackageError("Two reports are already running. Try again when one finishes.", 429)
        reservation = catalogue.reserve(tool_id, 'report')
        entered = False
        try:
            entry, tool = reservation.__enter__()
            entered = True
            inputs = tool.validate_values(inputs)
            snapshot = self.sources.snapshot(entry['manifest']['id'], tool.sources if entry['manifest']['contract_version'] == 2 else ['primary'], mapping)
            key = uuid.uuid4().hex
            folder = self.temp / key
            folder.mkdir()
            with self.lock:
                self.jobs[key] = dict(id=key, owner=owner, status='pending', tool_id=tool_id,
                                     package_version=entry['manifest']['version'], expires=time.time()+900)
            self.pool.submit(self._report, key, entry, tool, inputs, reservation, catalogue, snapshot)
            return self.report(key, owner)
        except Exception:
            if entered:
                reservation.__exit__(None, None, None)
            self.slots.release()
            raise

    def _report(self, key, entry, tool, inputs, reservation, catalogue, snapshot):
        folder = self.temp / key
        with self.lock:
            self.jobs[key]['status'] = 'running'
        try:
            from backend.services.report_worker import run_report
            context = multiprocessing.get_context('spawn')
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=run_report, args=(sender, str(catalogue.root), entry, tool.model_dump(), inputs, snapshot, str(folder)), daemon=True)
            try:
                process.start()
                sender.close()
                deadline = time.monotonic() + REPORT_TIMEOUT_SECONDS
                while not receiver.poll(0.2):
                    if self.stop.is_set():
                        raise PackageError('Report stopped because RobotControl is shutting down.')
                    if time.monotonic() >= deadline:
                        raise PackageError('Report exceeded the five-minute limit. Reduce the selected data and try again.')
                    if not process.is_alive():
                        raise PackageError('Report process stopped unexpectedly. Check the Python script.')
                try:
                    response = receiver.recv()
                except EOFError:
                    raise PackageError('Report process stopped unexpectedly. Check the Python script.') from None
                if response.get('error'):
                    raise (PackageError if response.get('expected') else RuntimeError)(response['error'])
                output = response['output']
            finally:
                sender.close(); receiver.close()
                if process.pid:
                    process.join(timeout=1)
                    if process.is_alive():
                        process.terminate(); process.join(timeout=5)
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

    @staticmethod
    def schedules_using(package_id):
        """Names of active schedules whose preparation step uses this package."""
        from backend.services.scheduling.database_manager import get_scheduling_database_manager
        return [schedule.experiment_name
                for schedule in get_scheduling_database_manager().get_schedules(active_only=True, archived_only=False)
                if (schedule.preparation or {}).get('package_id') == package_id]

    def pin_preparation(self, tool_id, inputs, actor):
        """Validate a preparation step for a schedule and pin what it will run: the package
        file hash and the operation connection. Runs only the declared lookup queries."""
        with self.catalogue.reserve(tool_id, 'preparation') as (entry, tool):
            package_id = entry['manifest']['id']
            inputs = tool.validate_values(inputs or {})
            with self.sources.lock:
                target = self.sources.operation_target(package_id)
                snapshot = self.sources.snapshot(package_id, tool.sources)
            with self.sources.connections(snapshot) as connections:
                self.validate_choices(tool, inputs, connections)
            from backend.utils.datetime import utc_now_as_local_naive
            return dict(package_id=package_id, tool_id=tool.id, tool_name=tool.name,
                        package_version=entry['manifest']['version'], sha256=entry['sha256'],
                        source_id=target['id'], inputs=inputs, attached_by=actor,
                        attached_at=utc_now_as_local_naive().isoformat())

    def preparation_state(self, preparation):
        """ready | needs_review (package or connection changed since saving) | missing."""
        if not preparation or preparation.get('invalid'):
            return 'missing' if preparation else None
        with self.catalogue.lock:
            try:
                _, entry, _ = self.catalogue.resolve(preparation.get('tool_id'), 'preparation')
            except PackageError:
                return 'missing'
            if entry['manifest']['id'] != preparation.get('package_id') or entry['sha256'] != preparation.get('sha256'):
                return 'needs_review'
        try:
            target = self.sources.operation_target(preparation['package_id'])
        except PackageError:
            return 'needs_review'
        return 'ready' if target['id'] == preparation.get('source_id') else 'needs_review'

    def prepare_for_run(self, preparation, run):
        """Run a schedule's pinned preparation step before its launch.

        Holds no scheduler lock: the caller has already registered the execution, so
        database_change_guard refuses manual operations meanwhile. Returns the step's
        message; raises PreparationFailed otherwise.
        """
        if not preparation or preparation.get('invalid'):
            raise PreparationFailed('failed', 'The saved preparation step is unreadable. Review the schedule.')
        try:
            reservation = self.catalogue.reserve(preparation['tool_id'], 'preparation')
            entry, tool = reservation.__enter__()
        except PackageError as exc:
            raise PreparationFailed('failed', f'Preparation step unavailable: {exc}') from exc
        try:
            if entry['manifest']['id'] != preparation['package_id'] or entry['sha256'] != preparation['sha256']:
                raise PreparationFailed('failed', 'The package changed after this schedule was saved. Review and save the schedule again.')
            try:
                with self.sources.lock:
                    target = self.sources.operation_target(preparation['package_id'])
                    snapshot = self.sources.snapshot(preparation['package_id'], tool.sources)
                inputs = tool.validate_values(preparation.get('inputs') or {})
            except PackageError as exc:
                raise PreparationFailed('failed', str(exc)) from exc
            # A rotated password keeps the connection id; another database does not.
            if target['id'] != preparation['source_id']:
                raise PreparationFailed('failed', 'The package uses a different connection than when this schedule was saved. Review the schedule.')
            outcome = self._run_preparation(entry, tool, inputs, snapshot, target, run)
        finally:
            reservation.__exit__(None, None, None)
        return outcome

    def _run_preparation(self, entry, tool, inputs, snapshot, target, run):
        from backend.services.report_worker import run_preparation
        context = multiprocessing.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=run_preparation, daemon=True,
            args=(sender, str(self.catalogue.root), entry, tool.model_dump(), inputs, snapshot, target, run))
        committing = False
        try:
            process.start()
            sender.close()
            deadline = time.monotonic() + PREPARATION_TIMEOUT_SECONDS
            while True:
                if receiver.poll(0.2):
                    try:
                        message = receiver.recv()
                    except EOFError:
                        break
                    if message.get('committing'):
                        committing = True
                    elif message.get('committed'):
                        return message.get('message') or 'Preparation completed.'
                    elif message.get('error'):
                        if committing:
                            break
                        raise PreparationFailed('failed', message['error'])
                    continue
                if time.monotonic() >= deadline:
                    # Even before 'committing' a stopped process is not proof of a rollback
                    # an operator can rely on before a robot run, so the outcome is unknown.
                    raise PreparationFailed('unknown',
                        'Preparation exceeded the two-minute limit and was stopped. Its database changes may or may not '
                        'have been committed: check the database before resuming.')
                if not process.is_alive() and not receiver.poll(0):
                    break
            raise PreparationFailed('unknown', 'The preparation process stopped without confirming its result. '
                                    'Check the database before resuming.')
        finally:
            sender.close(); receiver.close()
            if process.pid:
                process.join(timeout=1)
                if process.is_alive():
                    process.terminate(); process.join(timeout=5)

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
