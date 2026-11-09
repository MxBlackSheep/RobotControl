"""Scheduled machine runs. Run Control owns execution; RobotControl only follows.

The JSON receipt distinguishes these runs from legacy VENUS observations. It is
written before POST, and recovery never re-enters preparation or launch gates.
"""
from datetime import datetime, timedelta
import json
import logging
import time
from urllib.parse import quote

from backend.models import JobExecution
from backend.services.pyhsl_client import PyHslError, PyHslUnavailable, PyHslTimeout, PyHslRefusal
from backend.services.pyhsl_monitor import TERMINAL_STATUSES
from backend.services.scheduling.pre_execution import PreExecutionPipeline
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable
from backend.utils.datetime import parse_iso_datetime_to_local

logger = logging.getLogger(__name__)
PYHSL_ALLOWED_MODES = frozenset({'simulation'})
UNAVAILABLE_REASON = 'PyHSL Run Control is not running'


def validate_protocol(protocol_id, parameters, mode):
    from backend.services.pyhsl_client import PyHslClient
    if mode not in PYHSL_ALLOWED_MODES:
        raise PyHslError('PyHSL schedules require Simulation mode')
    if not isinstance(protocol_id, str) or not protocol_id.strip():
        raise PyHslError('Choose a PyHSL protocol')
    if not isinstance(parameters, dict):
        raise PyHslError('PyHSL parameters must be a JSON object')
    result = PyHslClient().post('/validate', dict(protocol_id=protocol_id, parameters=parameters, mode=mode))
    if not isinstance(result, dict) or not isinstance(result.get('protocol'), dict) or not result['protocol'].get('revision'):
        raise PyHslError('Run Control returned an invalid protocol revision')
    return result


def dispatch_reason():
    from backend.services.pyhsl_monitor import get_pyhsl_monitor
    reading = get_pyhsl_monitor().status()
    if reading['state'] == 'not_running':
        return UNAVAILABLE_REASON
    if reading['state'] != 'running':
        return reading.get('reason') or 'PyHSL Run Control state is unknown'
    if reading['run']:
        return 'A PyHSL run is active'
    if not reading['reviews'].get('known'):
        return 'PyHSL Run review state is unknown'
    if reading['reviews']['blocked']:
        return 'PyHSL runs wait for a Run review'
    return None


def require_no_active_run():
    from backend.services.pyhsl_monitor import get_pyhsl_monitor
    reading = get_pyhsl_monitor().status()
    if reading['state'] == 'not_running':
        return
    if reading['state'] == 'running' and reading['reviews']['known'] and not reading['run']:
        return
    raise SafetyConflict('A PyHSL run is active' if reading['run'] else 'PyHSL Run Control state is unknown')


def review_state(reading, run_id):
    """None means cached/unknown; absence from a complete case list means clear."""
    if (not isinstance(reading, dict) or reading.get('active') is not False
            or type(reading.get('blocked')) is not bool or not isinstance(reading.get('cases'), list)):
        return None
    required = False
    for case in reading['cases']:
        if (not isinstance(case, dict) or not isinstance(case.get('run_id'), str)
                or type(case.get('requires_review')) is not bool):
            return None
        if case['run_id'] == run_id:
            required = required or case['requires_review']
    return required


class PyHslRunner:
    poll_seconds = 5
    unavailable_seconds = 180
    reconciliation_seconds = 300

    def __init__(self, engine):
        from backend.services.pyhsl_client import PyHslClient
        self.engine = engine
        self.client = PyHslClient()

    def unfinished(self):
        with self.engine.db_manager.sqlite_db._get_connection() as conn:
            return [JobExecution.from_dict(dict(row)) for row in conn.execute(
                "SELECT * FROM JobExecutions WHERE status = 'running' AND pyhsl IS NOT NULL")]

    def _save(self, execution):
        # Updating a running receipt is not a new launch: schedule edits or recovery
        # must not prevent recording the identity of a run that already exists.
        with self.engine.db_manager.sqlite_db._get_connection() as conn:
            changed = conn.execute("UPDATE JobExecutions SET pyhsl = ? WHERE execution_id = ? AND status = 'running'",
                (json.dumps(execution.pyhsl), execution.execution_id)).rowcount
            if changed != 1:
                raise StorageUnavailable('Could not persist the PyHSL execution receipt')
            conn.commit()

    def acknowledge(self, schedule_id):
        history = self.engine.db_manager.sqlite_db.get_execution_history(schedule_id, limit=1)
        run_id = (history[0].get('pyhsl') or {}).get('run_id') if history else None
        try:
            reading = self.client.get('/reconciliation', timeout=30)
        except PyHslError:
            raise SafetyConflict('Cannot read PyHSL Run Control; acknowledgement is unavailable') from None
        if isinstance(reading, dict) and reading.get('active') is True:
            raise SafetyConflict('A PyHSL run is active')
        review = review_state(reading, run_id)
        if review is None:
            raise SafetyConflict('PyHSL Run review state is unknown')
        if review or (not run_id and reading['blocked']):
            raise SafetyConflict('Save the Run review in PyHSL Run Control first')

    def execute(self, schedule, execution):
        engine = self.engine
        with engine._jobs_lock:
            engine._owned_execution_ids.add(execution.execution_id)
        try:
            self._execute(schedule, execution)
        except Exception:
            # Leave the running row for recovery, including interrupted finalization.
            logger.exception('Could not finish scheduled PyHSL execution')
        finally:
            with engine._jobs_lock:
                engine._owned_execution_ids.discard(execution.execution_id)
                engine._running_jobs.discard(schedule.schedule_id)

    def _execute(self, schedule, execution):
        engine = self.engine
        try:
            resumed = execution.status == 'running'
            if resumed and execution.pyhsl.get('result'):
                return self._finish(schedule, execution, **execution.pyhsl['result'])
            if not resumed:
                execution.pyhsl = {}
                with engine.launch_guard(schedule, execution):
                    pass
                unavailable = None
                while engine._running:
                    try:
                        validated = self.client.post('/validate', dict(protocol_id=schedule.protocol_id,
                            parameters=schedule.parameters, mode=schedule.mode))
                        break
                    except (PyHslUnavailable, PyHslTimeout):
                        unavailable = self._unavailable(schedule, execution, unavailable)
                        if time.monotonic() - unavailable >= 300:
                            return self._finish(schedule, execution, 'failed',
                                'PyHSL validation unavailable; check Run Control', 'execution_failed', hold=True)
                        if self._wait():
                            return
                else:
                    return
                if unavailable is not None:
                    with engine.launch_guard(schedule, execution):
                        pass
                if validated['protocol']['revision'] != schedule.protocol_revision:
                    return self._finish(schedule, execution, 'failed',
                        'Protocol revision changed in Run Control; save the schedule again', 'execution_failed', hold=True)
                if schedule.mode not in PYHSL_ALLOWED_MODES:
                    raise PyHslError('PyHSL schedules require Simulation mode')
                try:
                    PreExecutionPipeline(engine.db_manager).prepare(schedule, execution.execution_id)
                except SafetyConflict:
                    raise
                except Exception as exc:
                    return self._finish(schedule, execution, 'failed', str(exc), 'execution_failed', hold=True)
                execution.pyhsl = dict(request=dict(protocol_id=schedule.protocol_id, parameters=schedule.parameters,
                    mode=schedule.mode, protocol_revision=schedule.protocol_revision, request_id=execution.execution_id),
                    run_id=None, attempted_at=datetime.now().isoformat())
                self._save(execution)
            if not execution.pyhsl.get('run_id'):
                if not execution.pyhsl.get('request'):
                    return self._finish(schedule, execution, 'failed',
                        'PyHSL start was interrupted before its request was saved; check Before this run', 'aborted', hold=True)
                if not self._start(schedule, execution, resumed):
                    return
            self._follow(schedule, execution)
        except (PyHslError, SafetyConflict) as exc:
            self._finish(schedule, execution, 'failed', str(exc), 'execution_failed', hold=True)

    def _wait(self):
        return self.engine._stop_event.wait(self.poll_seconds)

    def _unavailable(self, schedule, execution, since):
        since = time.monotonic() if since is None else since
        if time.monotonic() - since >= self.unavailable_seconds:
            try:
                self.engine._notify_execution_event(schedule, execution, 'monitoring_unavailable',
                    {'note': 'Cannot read PyHSL Run Control; the execution is still being followed'})
            except Exception:
                logger.exception('PyHSL monitoring notification failed')
        return since

    def _start(self, schedule, execution, resumed):
        receipt = execution.pyhsl
        unavailable = None
        while self.engine._running:
            attempted = parse_iso_datetime_to_local(receipt.get('attempted_at'))
            expired = attempted is None or not timedelta(0) <= datetime.now() - attempted <= timedelta(minutes=5)
            try:
                if resumed or expired:
                    # Read first even after the resend window: an existing run must
                    # still be adopted. Do not use the current schedule's definition.
                    rows = self.client.get('/runs')['sessions']
                    for row in rows:
                        if row.get('origin') != 'machine' or row.get('protocol') != receipt['request']['protocol_id']:
                            continue
                        run = self.client.get('/runs/' + quote(row['run_id'], safe=''))
                        if run.get('configuration', {}).get('request_id') == execution.execution_id:
                            receipt['run_id'] = row['run_id']
                            self._save(execution)
                            return True
                if attempted is None or not timedelta(0) <= datetime.now() - attempted <= timedelta(minutes=5):
                    break
                run = self.client.post('/runs', receipt['request'], timeout=60)
                if not isinstance(run, dict) or not isinstance(run.get('run_id'), str) or not run['run_id']:
                    self._finish(schedule, execution, 'failed', 'PyHSL start returned no run ID', 'aborted', hold=True)
                    return False
                receipt['run_id'] = run['run_id']
                self._save(execution)
                return True
            except (PyHslUnavailable, PyHslTimeout):
                if expired:
                    break
                unavailable = self._unavailable(schedule, execution, unavailable)
            if self._wait():
                return False
        if self.engine._running:
            self._finish(schedule, execution, 'failed',
                'PyHSL start could not be confirmed; the saved attempt is too old to resend', 'aborted', hold=True)
        return False

    def _follow(self, schedule, execution):
        run_id = execution.pyhsl['run_id']
        unavailable = terminal_since = None
        terminal = None
        while self.engine._running:
            review = None
            try:
                if terminal is None:
                    try:
                        run = self.client.get('/runs/' + quote(run_id, safe=''))
                    except PyHslRefusal:
                        return self._finish(schedule, execution, 'failed',
                            'PyHSL run is unavailable; check Run Control', 'aborted', hold=True)
                    if run.get('status') in TERMINAL_STATUSES:
                        terminal = run
                        terminal_since = time.monotonic()
                if terminal is not None:
                    review = review_state(self.client.get('/reconciliation', timeout=30), run_id)
                unavailable = None
            except (PyHslError, KeyError, TypeError, AttributeError):
                unavailable = self._unavailable(schedule, execution, unavailable)
            if terminal is not None:
                unknown = terminal['status'] in {'outcome_unknown', 'reconciliation_required'}
                if review is not None or time.monotonic() - terminal_since >= self.reconciliation_seconds:
                    if unknown or review is None:
                        self._finish(schedule, execution, 'failed',
                            'PyHSL run outcome or Run review is unknown; check Run Control', 'aborted', hold=True)
                    else:
                        status = 'completed' if terminal['status'] == 'completed' else 'failed'
                        note = (f'PyHSL run {run_id} needs a Run review in Run Control' if review else
                                terminal.get('error') if status == 'failed' else None)
                        trigger = 'pyhsl_review_required' if review else 'execution_failed' if status == 'failed' else None
                        self._finish(schedule, execution, status, note, trigger, hold=review)
                    return
            if self._wait():
                return

    def _finish(self, schedule, execution, status, note, trigger, *, hold=False, end_time=None):
        ended = parse_iso_datetime_to_local(end_time) if end_time else datetime.now()
        if execution.status == 'running':
            # A refusal must not become a new POST if finalization is interrupted.
            execution.pyhsl['result'] = dict(status=status, note=note, trigger=trigger,
                                            hold=hold, end_time=ended.isoformat())
            self._save(execution)
        execution.status, execution.error_message = status, note
        execution.end_time = ended
        # Hold and deduplicated notification precede the terminal write, so a crash
        # cannot leave a finished row whose required recovery was never persisted.
        if hold:
            current = self.engine.db_manager.get_schedule_by_id(schedule.schedule_id)
            if not current or not current.recovery_required:
                self.engine._apply_manual_recovery(schedule, note, actor='scheduler')
        if trigger:
            context = {'error_message': note, 'schedule_active': False if hold else bool(self.engine._resolve_interval_hours(schedule))}
            if hold:
                context['note'] = note
            self.engine._notify_execution_event(schedule, execution, trigger, context)
        self.engine._finalize_execution(schedule, execution)
