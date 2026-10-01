"""Reviewed installation settings; compatibility reads never run preparation."""
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from contextlib import closing

from pydantic import BaseModel, ConfigDict
from typing import Literal
from backend.services.database_packages import PackageError
from backend.utils.filesystem import replace_file


class LabConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    adapter: Literal['evoyeast', 'batch-sqlite'] = 'evoyeast'
    source_id: str | None = None
    sqlite_path: str | None = None


class LabSettings:
    def __init__(self, manager, sources, root, guard):
        self.manager, self.sources, self.guard = manager, sources, guard
        self.root = Path(root)
        self.path = self.root / 'scheduling-lab.json'
        self.lock = threading.RLock()
        self.reviews = {}

    def _bytes(self):
        return self.path.read_bytes() if self.path.exists() else None

    def _revision(self):
        return hashlib.sha256(self._bytes() or b'absent').hexdigest()

    def _schedules(self, conn):
        return [dict(id=r[0], name=r[1], active=bool(r[2])) for r in conn.execute(
            'SELECT schedule_id,experiment_name,is_active FROM ScheduledExperiments WHERE archived=0 ORDER BY experiment_name')]

    def change_source(self, source_id, action):
        # Keep both the running connection and the reviewed restart target stable.
        with self.lock, self.sources.lock:
            raw = self._bytes()
            saved = json.loads(raw) if raw is not None else {}
            if source_id in (self.manager.lab.configuration.get('source_id'), saved.get('source_id')):
                raise PackageError('Scheduling uses this connection. Create a separate connection and review the change in Database settings.', 409)
            return action()

    def status(self):
        with self.lock, self.manager.sqlite_db._get_connection() as conn:
            lab = self.manager.lab
            raw = self._bytes()
            return dict(active=lab.configuration, target=lab.identity,
                        saved=json.loads(raw) if raw is not None else {'adapter':'evoyeast'},
                        pending=raw != lab.configuration_bytes, revision=self._revision(), schedules=self._schedules(conn))

    def _check(self, config):
        if config.adapter == 'evoyeast':
            if config.sqlite_path:
                raise PackageError('EvoYeast requires a SQL Server connection.')
            if config.source_id:
                source = self.sources.get(config.source_id, 'operation')
                context = self.sources.open(source)
                target = dict(server=source['server'], database=source['database'], revision=source['revision'])
            else:
                database = self.manager.main_db_service
                if database is None:
                    raise PackageError('The existing laboratory connection is unavailable.')
                context = database.get_connection()
                target = {k: database._primary_config.get(k) for k in ('server','database')}
            with context as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT TOP 0 ExperimentID, UserDefinedID, Note, ScheduledToRun FROM Experiments')
                # ResetHamiltonTables is optional. The preparation adapter only
                # invokes it when a schedule explicitly requests that step.
            return target
        if config.source_id or not config.sqlite_path:
            raise PackageError('Choose a separate SQLite file for the batch integration.')
        path = Path(config.sqlite_path)
        path = (path if path.is_absolute() else self.root/path).resolve(strict=True)
        if path == self.manager.sqlite_db.db_path.resolve():
            raise PackageError('The laboratory database must not be RobotControl scheduler storage.')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5)) as conn:
            conn.execute('SELECT batch_code, description, state FROM Batches LIMIT 0')
            conn.execute('SELECT slot, batch_code, method FROM InstrumentWorkOrder LIMIT 0')
            if conn.execute('SELECT COUNT(*) FROM InstrumentWorkOrder WHERE slot=1').fetchone()[0] != 1:
                raise PackageError('The batch database needs one instrument work-order slot.')
        return dict(database=str(path))

    def review(self, config, owner):
        with self.lock, self.sources.lock:
            try:
                target = self._check(config)
            except PackageError:
                raise
            except Exception:
                raise PackageError('Compatibility check failed. Check the database connection, required tables and procedures.') from None
            token = uuid.uuid4().hex
            self.reviews = {k:v for k,v in self.reviews.items() if v['expires'] > time.time()}
            if len(self.reviews) >= 50:
                raise PackageError('Too many open reviews. Try again later.', 429)
            status = self.status()
            self.reviews[token] = dict(owner=owner, config=config, target=target, revision=status['revision'], expires=time.time()+600)
            return dict(token=token, target=target, schedules=status['schedules'],
                        message='Required tables found. No preparation steps have been run. Each schedule keeps its own preparation choices.')

    def _idle(self, conn):
        # Recheck under the same SQLite write lock used by schedule changes.
        blocked = conn.execute("SELECT 1 FROM JobExecutions WHERE status IN ('pending','queued','running') LIMIT 1").fetchone()
        blocked = blocked or conn.execute('SELECT 1 FROM ExecutionMonitoring WHERE finished=0 LIMIT 1').fetchone()
        blocked = blocked or conn.execute('SELECT 1 FROM SchedulerState WHERE recovery_required=1').fetchone()
        blocked = blocked or conn.execute('SELECT 1 FROM ScheduledExperiments WHERE recovery_required=1 OR (is_active=1 AND archived=0) LIMIT 1').fetchone()
        if blocked:
            raise PackageError('Finish queued work and recovery, then disable schedules before saving laboratory settings.', 409)

    def save(self, token, owner):
        with self.guard(), self.lock, self.sources.lock, self.manager.sqlite_db._get_connection() as conn:
            review = self.reviews.get(token)
            if not review or review['owner'] != owner or review['expires'] < time.time() or review['revision'] != self._revision():
                raise PackageError('Settings changed or review expired. Review again.', 409)
            if review['config'].source_id:
                source = self.sources.get(review['config'].source_id, 'operation')
                if source['revision'] != review['target']['revision']:
                    raise PackageError('The connection changed. Review again.', 409)
            conn.execute('BEGIN IMMEDIATE')
            self._idle(conn)
            old = self.manager.lab.configuration_bytes
            backup = self.path.with_suffix('.previous.json')
            backup.write_text(json.dumps({'previous': old.decode('utf-8') if old is not None else None}), encoding='utf-8')
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(review['config'].model_dump_json(exclude_none=True, indent=2), encoding='utf-8')
            replace_file(temporary, self.path)
            del self.reviews[token]
            conn.commit()
        return self.status()

    def cancel(self, revision):
        with self.guard(), self.lock:
            if revision != self._revision():
                raise PackageError('Settings changed. Refresh before cancelling.', 409)
            original = self.manager.lab.configuration_bytes
            if original is None:
                self.path.unlink(missing_ok=True)
            else:
                temporary = self.path.with_suffix('.tmp')
                temporary.write_bytes(original)
                replace_file(temporary, self.path)
            self.reviews.clear()
        return self.status()
