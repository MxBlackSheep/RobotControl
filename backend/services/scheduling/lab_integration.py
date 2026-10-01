"""Installation-selected laboratory preparation; never a robot/run-state reader.

Adapters own their schema and transactions. Scheduler storage owns the durable
preparation receipt. Adapters run no uploaded Python, SQL mapping language or hot
reloading. A schedule may add one pinned database package step (kind "preparation"),
which DatabaseTools runs in a separate, time-limited process under the same receipt.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import sqlite3

from backend.services.sqlite_safety import SafetyConflict


class EvoYeastLab:
    id = 'evoyeast'
    name = 'EvoYeast'
    version = 1
    selection_step = 'EvoYeastExperiment'
    selection_label = 'Experiment'
    preparation_label = 'Select experiment before running'

    def __init__(self, connect):
        self.connect = connect

    def choices(self, limit):
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT TOP {int(limit)} ExperimentID, UserDefinedID, Note, ScheduledToRun FROM Experiments ORDER BY ExperimentID DESC')
            return [dict(value=str(r[0]), label=str(r[1] or r[0]), note=r[2], selected=bool(r[3])) for r in cursor.fetchall()]

    @staticmethod
    def canonical_steps(steps):
        # Retain the old registry's case/punctuation aliases without rewriting
        # saved schedules or their audit receipts.
        names = {'scheduledtorun': 'ScheduledToRun', 'evoyeastexperiment': 'EvoYeastExperiment', 'resethamiltontables': 'ResetHamiltonTables'}
        result = []
        for step in steps:
            name, _, payload = step.partition(':')
            name = names.get(''.join(c for c in name.lower() if c.isalnum()), name)
            if name == 'EvoYeastExperiment':
                value, separator, action = payload.partition('|')
                payload = value.strip() + ('|' + action.strip().lower() if separator else '')
            result.append(name + (':' + payload if payload else ''))
        return result

    def validate(self, steps):
        steps = self.canonical_steps(steps)
        selections = []
        for step in steps:
            name, _, payload = step.partition(':')
            if name == 'ScheduledToRun' and not payload:
                continue  # Old form marker; the ID-bearing step performs the write.
            if name == self.selection_step:
                value, separator, action = payload.partition('|')
                if not value or not value.isdecimal() or (separator and action not in ('set', 'activate', 'exclusive', 'none', 'noop', 'skip')):
                    raise ValueError('Choose a valid EvoYeast experiment before running.')
                if action not in ('none', 'noop', 'skip'):
                    selections.append(value)
            elif name == 'ResetHamiltonTables':
                if payload and any(not x.strip() for x in payload.split(',')):
                    raise ValueError('Invalid reset table list.')
            else:
                raise ValueError(f'Preparation step {name!r} is not supported by EvoYeast.')
        if len(selections) > 1:
            raise ValueError('Select only one experiment per execution.')
        if 'ScheduledToRun' in steps and not selections:
            raise ValueError('ScheduledToRun requires an EvoYeast experiment ID. Edit preparation before running.')

    def prepare(self, experiment, steps):
        steps = self.canonical_steps(steps)
        steps = [step for step in steps if step != 'ScheduledToRun' and not (
            step.startswith('EvoYeastExperiment:') and step.partition('|')[2] in ('none', 'noop', 'skip'))]
        if not steps:
            return
        with self.connect() as conn:
            try:
                cursor = conn.cursor()
                for step in steps:
                    name, _, payload = step.partition(':')
                    if name == self.selection_step:
                        value, _, action = payload.partition('|')
                        if action in ('none', 'noop', 'skip'):
                            continue
                        # Lock the target before clearing any flags; reject missing/duplicate IDs.
                        cursor.execute('SELECT ExperimentID FROM Experiments WITH (UPDLOCK, HOLDLOCK) WHERE ExperimentID = ?', (value,))
                        if len(cursor.fetchall()) != 1:
                            raise ValueError(f'Experiment {value} is missing or not unique. Refresh the selection.')
                        cursor.execute('UPDATE Experiments SET ScheduledToRun = 0')
                        cursor.execute('UPDATE Experiments SET ScheduledToRun = 1 WHERE ExperimentID = ?', (value,))
                        if cursor.rowcount != 1:
                            raise ValueError('The selected experiment changed during preparation.')
                    elif name == 'ResetHamiltonTables':
                        tables = [x.strip() for x in payload.split(',')] if payload else []
                        params = [experiment.experiment_name]
                        sql = 'EXEC ResetHamiltonTables @ExperimentName = ?'
                        if tables:
                            sql += ', @TablesJson = ?'
                            params.append(json.dumps(tables))
                        cursor.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise


class BatchSqliteLab:
    """Second-schema example: batch code -> one instrument work order.

    This database is lab-owned and is not RobotControl's scheduling SQLite file.
    The example demonstrates the data boundary, not a second robot driver.
    """
    id = 'batch-sqlite'
    name = 'Batch example'
    version = 1
    selection_step = 'Batch'
    selection_label = 'Batch'
    preparation_label = 'Select batch before running'

    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        if not self.path.is_file():
            raise ValueError('Batch database must be an existing file.')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
        try:
            yield conn
        finally:
            conn.close()

    def choices(self, limit):
        with self.connect() as conn:
            return [dict(value=r[0], label=r[1], note=None, selected=False) for r in conn.execute(
                "SELECT batch_code, description FROM Batches WHERE state = 'ready' ORDER BY batch_code LIMIT ?", (limit,))]

    def validate(self, steps):
        if len(steps) > 1:
            raise ValueError('Select only one batch per execution.')
        for step in steps:
            name, _, value = step.partition(':')
            if name != self.selection_step or not value or len(value) > 100 or any(x in value for x in '|\r\n'):
                raise ValueError('This installation requires a Batch preparation step. Review the schedule.')

    def prepare(self, experiment, steps):
        if not steps:
            return
        value = steps[0].partition(':')[2]
        with self.connect() as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')
                row = conn.execute('SELECT state FROM Batches WHERE batch_code = ?', (value,)).fetchone()
                if row is None or row[0] != 'ready':
                    raise ValueError('This batch is no longer ready. Refresh the selection.')
                count = conn.execute('UPDATE InstrumentWorkOrder SET batch_code = ?, method = ? WHERE slot = 1',
                                     (value, experiment.experiment_name)).rowcount
                if count != 1:
                    raise ValueError('The batch database needs exactly one instrument work-order slot.')
                conn.commit()
            except Exception:
                conn.rollback()
                raise


class LabIntegration:
    def __init__(self, adapter, storage, target, *, legacy_default=False):
        self.adapter = adapter
        self.storage = storage
        self.identity = dict(adapter=adapter.id, version=adapter.version, **target)
        self.signature = hashlib.sha256(json.dumps(self.identity, sort_keys=True).encode()).hexdigest()
        # Credential rotation can retain schedules; another data target cannot.
        self.target = hashlib.sha256(json.dumps({k: v for k, v in self.identity.items()
            if k not in ('revision', 'hamilton_revision')}, sort_keys=True).encode()).hexdigest()
        self._bind(legacy_default)

    def _bind(self, legacy_default):
        # Configuration is captured for this process. A restarted installation may
        # change it only after existing jobs and recovery have been reconciled.
        with self.storage._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT signature FROM LabInstallation WHERE id=1').fetchone()
            if (old and old[0] != self.signature) or (not old and not legacy_default):
                blocked = conn.execute("SELECT 1 FROM JobExecutions WHERE status IN ('pending','queued','running') LIMIT 1").fetchone()
                blocked = blocked or conn.execute('SELECT 1 FROM ExecutionMonitoring WHERE finished=0 LIMIT 1').fetchone()
                blocked = blocked or conn.execute('SELECT 1 FROM SchedulerState WHERE recovery_required=1').fetchone()
                blocked = blocked or conn.execute('SELECT 1 FROM ScheduledExperiments WHERE recovery_required=1 LIMIT 1').fetchone()
                # Active saved schedules also belong to their original lab. Disable
                # and review them before changing an installation, even when idle.
                blocked = blocked or conn.execute('SELECT 1 FROM ScheduledExperiments WHERE is_active=1 AND archived=0 LIMIT 1').fetchone()
                if blocked:
                    raise SafetyConflict('Restore the previous lab configuration. Finish recovery and disable schedules before changing laboratories.')
            if not old:
                conn.execute('INSERT OR IGNORE INTO LabScheduleBinding(schedule_id,target) SELECT schedule_id,? FROM ScheduledExperiments', (self.target,))
            conn.execute('INSERT OR REPLACE INTO LabInstallation(id,signature,identity,target) VALUES (1,?,?,?)',
                         (self.signature, json.dumps(self.identity), self.target))
            conn.commit()

    def catalogue(self, limit=100):
        adapter = self.adapter
        return dict(id=adapter.id, name=adapter.name, selection_step=adapter.selection_step,
                    selection_label=adapter.selection_label, preparation_label=adapter.preparation_label,
                    choices=adapter.choices(max(1, min(int(limit), 500))))

    def prepare(self, experiment, execution_id, steps):
        self.adapter.validate(steps)  # All tokens checked before the first write.
        # A database package step (uploaded Python) runs after the adapter's step, in a
        # time-limited child process (DatabaseTools.prepare_for_run). Adapters never run
        # uploaded Python. Its pinned package and connection are checked before any write.
        preparation = getattr(experiment, 'preparation', None)
        tools = None
        if preparation:
            from backend.services.database_tools import get_database_tools
            tools = get_database_tools()
            state = tools.preparation_state(preparation)
            if state != 'ready':
                reason = {'missing': 'is no longer installed',
                          'invalid': 'saved with this schedule is unreadable'}.get(state, 'changed after this schedule was saved')
                raise SafetyConflict(f'The database preparation step {reason}. A local administrator must review and save the schedule.')
        with self.storage._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            bound = conn.execute('SELECT signature FROM LabInstallation WHERE id=1').fetchone()
            if not bound or bound[0] != self.signature:
                raise SafetyConflict('The scheduling lab configuration changed. Restart and review the schedules.')
            schedule_target = conn.execute('SELECT target FROM LabScheduleBinding WHERE schedule_id=?', (experiment.schedule_id,)).fetchone()
            if schedule_target and schedule_target[0] != self.target:
                raise SafetyConflict('This schedule belongs to a different lab database. Re-create it after reviewing its preparation.')
            conn.execute('INSERT OR IGNORE INTO LabScheduleBinding(schedule_id,target) VALUES (?,?)', (experiment.schedule_id, self.target))
            if conn.execute('SELECT 1 FROM LabPreparation WHERE execution_id=?', (execution_id,)).fetchone():
                raise SafetyConflict('Preparation was already attempted for this execution. Review recovery; it will not be repeated.')
            conn.execute('INSERT INTO LabPreparation(execution_id,identity,steps,status,package) VALUES (?,?,?,?,?)',
                         (execution_id, json.dumps(self.identity), json.dumps(steps), 'preparing',
                          json.dumps(preparation) if preparation else None))
            conn.commit()
        adapter_done = False
        try:
            self.adapter.prepare(experiment, steps)
            adapter_done = True
            message = None
            if preparation:
                from datetime import datetime
                run = dict(schedule_id=experiment.schedule_id, execution_id=execution_id,
                           experiment_name=experiment.experiment_name, experiment_path=experiment.experiment_path,
                           scheduled_for=experiment.start_time.isoformat() if experiment.start_time else None,
                           started_at=datetime.now().isoformat())
                message = tools.prepare_for_run(preparation, run)
            self._result(execution_id, 'prepared', message)
        except Exception as exc:
            # Cross-database changes and process launch cannot share a transaction.
            # Leave a durable receipt and use the existing operator recovery flow.
            from backend.services.database_tools import PreparationFailed
            status = exc.status if isinstance(exc, PreparationFailed) else 'failed'
            self._result(execution_id, status, str(exc)[:2000])
            if isinstance(exc, PreparationFailed):
                note = (('Lab selection applied. ' if adapter_done and steps else '')
                        + ('Database step failed; nothing it wrote was committed. ' if status == 'failed'
                           else 'Database step outcome unknown: check the database before resuming. ')
                        + str(exc))[:1000]
            else:
                note = 'Lab preparation failed. Check laboratory data before resuming.'
            self.storage.mark_recovery_atomic(experiment.schedule_id, note, 'system', snapshot=experiment)
            raise

    def _result(self, execution_id, status, message=None):
        with self.storage._get_connection() as conn:
            conn.execute('UPDATE LabPreparation SET status=?, message=? WHERE execution_id=?', (status, message, execution_id))
            conn.commit()


def load_lab_integration(storage, native_database, root):
    """Use existing credentials by default; optional profiles are captured once."""
    root = Path(root)
    path = root / 'scheduling-lab.json'
    configuration_bytes = path.read_bytes() if path.exists() else None
    config = json.loads(configuration_bytes) if configuration_bytes is not None else {'adapter': 'evoyeast'}
    if not isinstance(config, dict) or set(config) - {'adapter', 'source_id', 'sqlite_path'}:
        raise ValueError('Invalid scheduling-lab.json settings.')
    adapter_id = config.get('adapter')
    if adapter_id == 'evoyeast':
        if 'sqlite_path' in config:
            raise ValueError('EvoYeast requires SQL Server.')
        if config.get('source_id'):
            from backend.services.report_sources import ReportSources
            sources = ReportSources(root / 'database-tools')
            source = sources.get(config['source_id'], 'operation')
            adapter = EvoYeastLab(lambda: sources.open(source))
            target = dict(source=source['id'], revision=source['revision'], server=source['server'], database=source['database'])
        else:
            if native_database is None:
                raise ValueError('Native EvoYeast connection is unavailable.')
            from backend.services.database import DatabaseService
            database = DatabaseService()
            database._primary_config = copy.deepcopy(native_database._primary_config)
            adapter = EvoYeastLab(database.get_connection)
            target = dict(source='native', server=database._primary_config.get('server'), database=database._primary_config.get('database'),
                          revision=hashlib.sha256(json.dumps(database._primary_config, sort_keys=True).encode()).hexdigest())
    elif adapter_id == 'batch-sqlite':
        if config.get('source_id') or not config.get('sqlite_path'):
            raise ValueError('Batch example requires sqlite_path only.')
        location = Path(config['sqlite_path'])
        if not location.is_absolute():
            location = root / location
        if location.resolve() == storage.db_path.resolve():
            raise ValueError('The batch database must be separate from scheduler storage.')
        adapter = BatchSqliteLab(location)
        target = dict(source='sqlite', database=str(adapter.path))
    else:
        raise ValueError('Unknown scheduling lab adapter. Use evoyeast or batch-sqlite.')
    if native_database is not None:
        target['hamilton_revision'] = hashlib.sha256(json.dumps(native_database._primary_config, sort_keys=True).encode()).hexdigest()
    lab = LabIntegration(adapter, storage, target, legacy_default=not path.exists())
    lab.configuration = copy.deepcopy(config)
    lab.configuration_bytes = configuration_bytes
    return lab
