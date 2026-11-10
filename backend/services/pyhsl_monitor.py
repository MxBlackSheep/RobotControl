"""One independent poller owns Run Control reads and run alert dispatch."""
import copy
import logging
import re
import threading
import time
from datetime import datetime, timedelta

from backend.services.alert_email import pyhsl_alert_email
from backend.services.notification_delivery import send_recorded
from backend.services.pyhsl_client import PyHslClient, PyHslError, PyHslUnavailable
from backend.utils.datetime import parse_iso_datetime_to_local

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {'completed', 'failed', 'stopped', 'outcome_unknown', 'reconciliation_required'}
FAILED_STATUSES = {'failed', 'outcome_unknown', 'reconciliation_required'}
REVIEW_READ_SECONDS = 120
REVIEW_READ_TIMEOUT = 30
RUN_FIELDS = ('run_id', 'protocol', 'status', 'mode', 'completed_count', 'error', 'origin', 'created_at')


class PyHslMonitor:
    def __init__(self, client=None, *, email=None):
        self.client = client or PyHslClient()
        self.email = email
        self._reading = self._unavailable('unknown', 'Run Control has not been checked')
        self._checked = None
        self._protocols = {}
        self._review_rows = None
        self._review_read = None
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def _unavailable(state, reason):
        return dict(state=state, reason=reason, checked_at=None, run=None,
                    reviews=dict(known=False, blocked=False, run_ids=[]))

    def status(self):
        reading, checked = self._reading, self._checked
        result = copy.deepcopy(reading)
        if checked is not None and time.monotonic() - checked > 60:
            result.update(state='unknown', reason='Run Control reading is stale', run=None)
            result['reviews']['known'] = False
        return result

    def protocol_for_session(self, session_id):
        return self._protocols.get(session_id.lower())

    def _reviews(self, runs):
        """Run Control parses every journal for this list, so read it when a run changes or every two minutes."""
        rows = sorted((str(row.get('run_id')), str(row.get('status'))) for row in runs) if isinstance(runs, list) else None
        now = time.monotonic()
        if (self._review_rows != rows or self._review_read is None or now - self._review_read[0] > REVIEW_READ_SECONDS
                or self._review_read[1].get('active')):
            self._review_rows = None
            self._review_read = (now, self.client.get('/reconciliation', timeout=REVIEW_READ_TIMEOUT))
            self._review_rows = rows
        return self._review_read[1]

    def poll(self):
        try:
            runs = self.client.get('/runs')['sessions']
            if isinstance(runs, list):
                self._protocols = {row['session_id'].lower(): row['protocol'] for row in runs
                                   if row.get('session_id') and row.get('protocol')}
            reviews = self._reviews(runs)
            if not isinstance(runs, list) or not isinstance(reviews['cases'], list):
                raise ValueError
            # Parse dates once; invalid rows must not produce a healthy reading or alerts.
            dated = [(parse_iso_datetime_to_local(row['created_at']), row) for row in runs]
            if any(date is None for date, _ in dated):
                raise ValueError
            active = sorted(((date, row) for date, row in dated if row['status'] not in TERMINAL_STATUSES),
                            key=lambda item: item[0], reverse=True)
            run = {key: active[0][1].get(key) for key in RUN_FIELDS} if active else None
            review_ids = [case['run_id'] for case in reviews['cases'] if case['requires_review']]
            cached = reviews['active']
            if type(cached) is not bool or type(reviews['blocked']) is not bool:
                raise ValueError
            reason = 'Run review summary is cached while Run Control is active' if cached else ''
            reading = dict(state='running', reason=reason, run=run,
                           reviews=dict(known=not cached, blocked=reviews['blocked'] or bool(review_ids), run_ids=review_ids))
        except PyHslError as exc:
            reading = self._unavailable('not_running' if isinstance(exc, PyHslUnavailable) else 'unknown', str(exc))
            dated = []
        except (KeyError, TypeError, ValueError, AttributeError):
            reading = self._unavailable('unknown', 'Run Control returned an invalid reading')
            dated = []
        reading['checked_at'] = datetime.now().astimezone().isoformat()
        self._reading, self._checked = reading, time.monotonic()
        for created, row in dated:
            if row.get('origin') == 'machine':
                continue
            if not timedelta(0) <= datetime.now() - created <= timedelta(hours=24):
                continue
            if row['status'] in FAILED_STATUSES:
                self._alert(row, 'pyhsl_run_failed')
            if row['run_id'] in reading['reviews']['run_ids']:
                self._alert(row, 'pyhsl_review_required')

    def _alert(self, run, trigger):
        from backend.services.scheduling import get_scheduling_database_manager
        from backend.services.notifications import EmailNotificationService
        manager = get_scheduling_database_manager()
        if manager.notification_log_exists(run['run_id'], trigger):
            return
        # Built per alert: saved recipient and mail settings take effect without a restart.
        email = self.email or EmailNotificationService()
        recipients = email.get_manual_recovery_recipients()
        if not recipients:
            return
        alert = pyhsl_alert_email(run=run, trigger=trigger)
        send_recorded(email, alert.subject, alert.text(), html=alert.html(), to=recipients,
                      event_type=trigger, execution_id=run['run_id'])

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='pyhsl-monitor', daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:
                # Do not expose credentials or upstream payloads through exception text.
                logger.warning('PyHSL monitoring or notification delivery failed')
            self._stop.wait(15)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)


_monitor = PyHslMonitor()


def get_pyhsl_monitor():
    return _monitor


def experiment_runner(method_name):
    """Identify ManagedHost methods using the monitor's last runs read, without I/O."""
    match = re.search(r'[\\/]sessions[\\/]([0-9a-f]{32})[\\/]host[\\/]ManagedHost\.hsl$',
                      method_name or '', re.IGNORECASE)
    if not match:
        return {'runner': 'venus'}
    result = {'runner': 'pyhsl'}
    protocol = get_pyhsl_monitor().protocol_for_session(match.group(1))
    if protocol is not None:
        result['protocol'] = protocol
    return result
