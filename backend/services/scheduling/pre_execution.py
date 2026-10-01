"""Prepare laboratory data before launch, retaining a durable attempt receipt.

A schedule's preparation is its pinned database package step (kind "preparation"), which
DatabaseTools runs in a separate, time-limited process. Tokens of the retired built-in
adapters refuse the run until an administrator reviews them (legacy_preparation).
"""
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from typing import Optional

from backend.services.scheduling.legacy_preparation import legacy_review
from backend.services.sqlite_safety import SafetyConflict

logger = logging.getLogger(__name__)


@dataclass
class PreExecutionRun:
    success: bool
    steps: list = field(default_factory=list)
    failure_reason: Optional[str] = None
    cleanup_required: bool = False


class PreExecutionPipeline:
    def __init__(self, db_manager):
        self._db_manager = db_manager

    def run(self, experiment, execution_id):
        try:
            self.prepare(experiment, execution_id)
            return PreExecutionRun(success=True)
        except Exception as exc:
            logger.exception('Lab preparation failed for %s', experiment.schedule_id)
            return PreExecutionRun(success=False, failure_reason=str(exc))

    def prepare(self, experiment, execution_id):
        preparation = getattr(experiment, 'preparation', None)
        legacy = legacy_review(experiment.prerequisites, has_step=bool(preparation))
        if legacy:
            raise SafetyConflict(legacy['message'])
        tools = None
        if preparation:
            from backend.services.database_tools import get_database_tools
            tools = get_database_tools()
            state = tools.preparation_state(preparation)
            if state != 'ready':
                reason = {'missing': 'is no longer installed',
                          'invalid': 'saved with this schedule is unreadable'}.get(state, 'changed after this schedule was saved')
                raise SafetyConflict(f'The database preparation step {reason}. A local administrator must review and save the schedule.')
        storage = self._db_manager.sqlite_db
        with storage._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT 1 FROM LabPreparation WHERE execution_id=?', (execution_id,)).fetchone():
                raise SafetyConflict('Preparation was already attempted for this execution. Review recovery; it will not be repeated.')
            # identity described the retired adapter's target; the pinned step is in package.
            conn.execute('INSERT INTO LabPreparation(execution_id,identity,steps,status,package) VALUES (?,?,?,?,?)',
                         (execution_id, '{}', json.dumps(experiment.prerequisites or []), 'preparing',
                          json.dumps(preparation) if preparation else None))
            conn.commit()
        try:
            message = None
            if preparation:
                run = dict(schedule_id=experiment.schedule_id, execution_id=execution_id,
                           experiment_name=experiment.experiment_name, experiment_path=experiment.experiment_path,
                           scheduled_for=experiment.start_time.isoformat() if experiment.start_time else None,
                           started_at=datetime.now().isoformat())
                message = tools.prepare_for_run(preparation, run)
            self._result(execution_id, 'prepared', message)
        except Exception as exc:
            # Database changes and process launch cannot share a transaction. Leave a
            # durable receipt and use the existing operator recovery flow.
            from backend.services.database_tools import PreparationFailed
            status = exc.status if isinstance(exc, PreparationFailed) else 'failed'
            self._result(execution_id, status, str(exc)[:2000])
            if isinstance(exc, PreparationFailed):
                note = (('Database step failed; nothing it wrote was committed. ' if status == 'failed'
                         else 'Database step outcome unknown: check the database before resuming. ') + str(exc))[:1000]
            else:
                note = 'Lab preparation failed. Check laboratory data before resuming.'
            storage.mark_recovery_atomic(experiment.schedule_id, note, 'system', snapshot=experiment)
            raise

    def _result(self, execution_id, status, message=None):
        with self._db_manager.sqlite_db._get_connection() as conn:
            conn.execute('UPDATE LabPreparation SET status=?, message=? WHERE execution_id=?', (status, message, execution_id))
            conn.commit()

    def cleanup(self, results):
        # The EvoYeast selection remains active after a run. Do not invent a shared
        # post-run reset: the previous marker cleanup performed no SQL.
        pass
