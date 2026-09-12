"""Observe a scheduler-owned Hamilton run; filesystem silence never stops the robot."""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Dict, Optional

from backend.constants import HAMILTON_STATE_MAPPING
from backend.models import JobExecution, ScheduledExperiment
from backend.services.scheduling.run_log_store import RunLogStore
from backend.utils.datetime import parse_iso_datetime_to_local

logger = logging.getLogger(__name__)
UNAVAILABLE_SECONDS = 180
RETRY_SECONDS = 60
TERMINAL_STATES = {"Complete", "Aborted", "Error"}


def hamilton_log_directory() -> Path:
    return Path(os.environ.get("ROBOTCONTROL_HAMILTON_LOG_PATH", "").strip()
                or r"C:\Program Files\HAMILTON\LogFiles")


def method_variants(path: str):
    method = PureWindowsPath(path)
    return (str(method.with_suffix(".hsl")), str(method.with_suffix(".med")))


class HamiltonRunReader:
    """Exact, parameterized SQL reads with a short query timeout on each connection."""

    def __init__(self, database):
        self.database = database

    def query(self, sql, params=()):
        with self.database.get_connection() as conn:
            conn.timeout = 5
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                columns = [c[0] for c in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                cursor.close()

    def boundary(self, method_path):
        row = self.query("""
            SELECT GETDATE() AS CapturedAt,
            (SELECT TOP 1 RunGUID FROM HamiltonVectorDB.dbo.HxRun
             WHERE MethodName IN (?, ?) ORDER BY StartTime DESC) AS PreviousRunGUID
        """, method_variants(method_path))[0]
        return row["CapturedAt"].isoformat(), str(row["PreviousRunGUID"] or "")

    def find(self, state):
        if state.run_guid:
            rows = self.query("""
                SELECT RunGUID, MethodName, StartTime, EndTime, RunState
                FROM HamiltonVectorDB.dbo.HxRun WHERE RunGUID = ?
            """, (state.run_guid,))
        else:
            boundary = parse_iso_datetime_to_local(state.sql_boundary or state.launched_at)
            # Initialization may take time; never adopt a much later manual rerun.
            rows = self.query("""
                SELECT TOP 3 RunGUID, MethodName, StartTime, EndTime, RunState
                FROM HamiltonVectorDB.dbo.HxRun
                WHERE MethodName IN (?, ?) AND StartTime >= ? AND StartTime <= ?
                  AND RunGUID <> ? ORDER BY StartTime
            """, (*method_variants(state.method_path), boundary, boundary + timedelta(minutes=5), state.previous_guid))
        if len(rows) != 1:
            raise LookupError("Waiting for the exact SQL run" if not rows else "Multiple matching SQL runs; association is ambiguous")
        row = rows[0]
        if str(PureWindowsPath(str(row["MethodName"])).with_suffix("")).casefold() != str(PureWindowsPath(state.method_path).with_suffix("")).casefold():
            raise LookupError("SQL run method does not match the launched method")
        guid = uuid.UUID(str(row["RunGUID"])).hex
        if state.run_guid and guid != state.run_guid:
            raise LookupError("SQL returned a different run GUID")
        return {"guid": guid, "state": HAMILTON_STATE_MAPPING.get(str(row["RunState"]), "Unknown"),
                "raw_state": str(row["RunState"]),
                "end_time": row["EndTime"].isoformat() if row["EndTime"] else None}


@dataclass
class RunObservation:
    execution_id: str
    schedule_id: str
    schedule: Dict[str, Any]
    execution: Dict[str, Any]
    method_path: str = ""
    method_name: str = ""
    threshold_minutes: int = 3
    launched_at: str = ""
    sql_boundary: Optional[str] = None
    previous_guid: str = ""
    launched: bool = False
    process_id: Optional[int] = None
    terminate_schedule: bool = False
    legacy: bool = False
    run_guid: Optional[str] = None
    run_state: Optional[str] = None
    raw_run_state: Optional[str] = None
    end_time: Optional[str] = None
    trace_path: Optional[str] = None
    signature: Optional[list] = None
    last_activity_at: Optional[str] = None
    observed_at: Optional[str] = None
    state: str = "waiting"
    reason: Optional[str] = None
    episode_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    unavailable_episode_id: Optional[str] = None
    active_alert_id: Optional[str] = None
    finished: bool = False
    process_finished: bool = False


class RunLogMonitor:
    def __init__(self, manager, *, reader=None, store=None, directory=None, clock=time.monotonic):
        self.manager = manager
        self._reader = reader
        self._store = store
        self.directory = Path(directory) if directory is not None else hamilton_log_directory()
        self.clock = clock
        self._lock = threading.RLock()
        self._poll_lock = threading.Lock()
        self._states: Dict[str, RunObservation] = {}
        self._activity_clocks: Dict[str, float] = {}
        self._unavailable_clocks: Dict[str, float] = {}
        self._delivery_stop = threading.Event()
        self._delivery_thread = None
        self._retry_at: Dict[str, float] = {}

    @property
    def store(self):
        if self._store is None:
            self._store = RunLogStore(self.manager.sqlite_db)
        return self._store

    @property
    def reader(self):
        if self._reader is None:
            self._reader = HamiltonRunReader(self.manager.main_db_service)
        return self._reader

    def snapshot(self, execution_id):
        with self._lock:
            return copy.deepcopy(self._states.get(execution_id))

    def snapshots(self):
        with self._lock:
            return copy.deepcopy(list(self._states.values()))

    def restore(self):
        for data in self.store.restore():
            state = RunObservation(**data)
            # Monotonic readings cannot be carried across an application restart.
            state.active_alert_id = None
            self._states[state.execution_id] = state
            self._activity_clocks[state.execution_id] = self.clock()
        for execution in self.store.unfinished_executions():
            if execution.execution_id in self._states:
                continue
            schedule = self.manager.get_schedule_by_id(execution.schedule_id)
            if schedule:
                state = RunObservation(execution.execution_id, execution.schedule_id,
                    schedule.to_dict(), execution.to_dict(), legacy=True,
                    threshold_minutes=schedule.log_inactivity_threshold_minutes,
                    reason="This older execution has no saved launch association")
                self._states[state.execution_id] = state
                self.store.save(asdict(state))
        return self.snapshots()

    def prepare(self, schedule, execution, method_path, terminate_schedule=False):
        state = RunObservation(execution.execution_id, schedule.schedule_id, schedule.to_dict(), execution.to_dict(),
            method_path=str(method_path), method_name=PureWindowsPath(str(method_path)).stem,
            threshold_minutes=schedule.log_inactivity_threshold_minutes,
            launched_at=datetime.now().isoformat(), terminate_schedule=terminate_schedule)
        try:
            state.sql_boundary, state.previous_guid = self.reader.boundary(state.method_path)
        except Exception as exc:
            state.reason = f"SQL launch baseline unavailable: {exc}"
            logger.warning("%s", state.reason)
        with self._lock:
            self.store.save(asdict(state))  # Persist intent before starting a process.
            self._states[state.execution_id] = state

    def launched(self, execution_id, process_id):
        with self._lock:
            state = self._states[execution_id]
            state.launched = True
            state.process_id = process_id
            self._activity_clocks[execution_id] = self.clock()
            self.store.save(asdict(state))

    def _trace_signature(self, state):
        root = self.directory.resolve()
        suffix = f"_{state.run_guid}_trace.trc"
        candidates = [p for p in root.iterdir() if p.name.casefold().endswith(suffix)]
        if len(candidates) != 1:
            raise LookupError("Exact run trace is missing" if not candidates else "Multiple traces match the run GUID")
        path = candidates[0].resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise LookupError("Run trace is outside the Hamilton log directory or is not a file")
        stat = path.stat()
        return str(path), [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]

    def process_finished(self, execution):
        """Keep the known process outcome if finalizing the schedule must be retried."""
        with self._lock:
            state = self._states.get(execution.execution_id)
            if state:
                state.execution = execution.to_dict()
                state.process_finished = True
                state.state = "terminal"
                state.active_alert_id = None
                self.store.save(asdict(state))

    def check(self, execution_id):
        # Scheduler, executor completion, and delivery revalidation share this gate.
        with self._poll_lock:
            state = self.snapshot(execution_id)
            if not state or state.finished or state.process_finished:
                return state
            row = None
            signature = None
            path = None
            reason = None
            try:
                if state.legacy or not state.launched:
                    raise LookupError("No confirmed process launch is available for this execution")
                row = self.reader.find(state)
                state.run_guid = row["guid"]
                if row["state"] not in TERMINAL_STATES:
                    if row["end_time"]:
                        raise LookupError("SQL end time is recorded; waiting for the final run state")
                    if row["state"] not in {"Running", "Paused"}:
                        raise LookupError(f"Unrecognized Hamilton SQL state: {row.get('raw_state', row['state'])}")
                    path, signature = self._trace_signature(state)
            except Exception as exc:
                reason = str(exc)
            now = self.clock()
            with self._lock:
                current = self._states.get(execution_id)
                if not current or current.finished or current.process_finished:
                    return copy.deepcopy(current)
                # The SQL GUID is bound even when trace discovery fails.
                if row:
                    current.run_guid = row["guid"]
                    current.run_state = row["state"]
                    current.raw_run_state = row.get("raw_state")
                    current.end_time = row["end_time"]
                current.observed_at = datetime.now().isoformat()
                current.active_alert_id = None
                alert = None
                if row and row["state"] in TERMINAL_STATES:
                    current.state = "terminal"
                    current.reason = None
                elif reason:
                    current.reason = reason
                    if current.unavailable_episode_id is None:
                        current.unavailable_episode_id = uuid.uuid4().hex
                    since = self._unavailable_clocks.setdefault(execution_id, now)
                    current.state = "waiting" if now - since <= UNAVAILABLE_SECONDS else "monitoring_unavailable"
                    if current.state == "monitoring_unavailable":
                        alert = self._alert(current, "monitoring_unavailable", current.unavailable_episode_id, now - since)
                else:
                    had_outage = execution_id in self._unavailable_clocks
                    self._unavailable_clocks.pop(execution_id, None)
                    current.unavailable_episode_id = None
                    current.reason = None
                    current.trace_path = path
                    if signature != current.signature:
                        current.signature = signature
                        current.last_activity_at = current.observed_at
                        current.episode_id = uuid.uuid4().hex
                        self._activity_clocks[execution_id] = now
                    elif had_outage:
                        # No claim about elapsed inactivity while observation was unavailable.
                        self._activity_clocks[execution_id] = now
                    since = self._activity_clocks.setdefault(execution_id, now)
                    current.state = "monitoring"
                    if now - since > current.threshold_minutes * 60:
                        current.state = "log_inactive"
                        alert = self._alert(current, "log_inactive", current.episode_id, now - since)
                self.store.save(asdict(current), alert)
                return copy.deepcopy(current)

    def _alert(self, state, event_type, episode, seconds):
        state.active_alert_id = uuid.uuid5(uuid.NAMESPACE_URL, f"robotcontrol/{state.execution_id}/{event_type}/{episode}").hex
        return {"event_type": event_type, "episode_id": episode, "context": {
            "run_guid": state.run_guid, "method_path": state.method_path,
            "run_state": state.run_state, "raw_run_state": state.raw_run_state,
            "trace_filename": Path(state.trace_path).name if state.trace_path else None,
            "inactivity_minutes" if event_type == "log_inactive" else "unavailable_minutes": round(seconds / 60, 1),
            "threshold_minutes": state.threshold_minutes if event_type == "log_inactive" else 3,
            "last_activity_at": state.last_activity_at, "observed_at": state.observed_at,
            "note": state.reason if event_type == "monitoring_unavailable" else
                "The run log has stopped updating; operator attention may be required.",
        }}

    def finish(self, execution_id):
        with self._lock:
            state = self._states.get(execution_id)
            if not state:
                return
            state.finished = True
            state.active_alert_id = None
            self.store.save(asdict(state))
            self._states.pop(execution_id, None)
            self._activity_clocks.pop(execution_id, None)
            self._unavailable_clocks.pop(execution_id, None)

    def details(self, schedule_id):
        with self._lock:
            state = next((s for s in self._states.values() if s.schedule_id == schedule_id and not s.finished), None)
            if state is None:
                return None
            return {"state": state.state, "run_guid": state.run_guid,
                    "run_state": state.run_state, "raw_run_state": state.raw_run_state,
                    "trace_filename": Path(state.trace_path).name if state.trace_path else None,
                    "last_activity_at": state.last_activity_at, "observed_at": state.observed_at,
                    "inactivity_seconds": max(0, self.clock() - self._activity_clocks.get(state.execution_id, self.clock())),
                    "threshold_minutes": state.threshold_minutes, "reason": state.reason}

    def start_delivery(self, service_getter: Callable):
        self._delivery_stop.clear()
        if self._delivery_thread and self._delivery_thread.is_alive():
            return
        self._delivery_thread = threading.Thread(target=self._delivery_loop, args=(service_getter,),
                                                 name="RunLogEmailDelivery", daemon=True)
        self._delivery_thread.start()

    def stop_delivery(self):
        self._delivery_stop.set()
        if self._delivery_thread:
            self._delivery_thread.join(timeout=2)

    def _delivery_loop(self, service_getter):
        while not self._delivery_stop.is_set():
            try:
                self.deliver_pending(service_getter)
            except Exception:
                logger.exception("Run log notification delivery failed")
            self._delivery_stop.wait(2)

    def deliver_pending(self, service_getter):
        for entry in self.store.due_alerts():
            if self._delivery_stop.is_set():
                break
            log_id = entry["log_id"]
            if entry["status"] == "error" and log_id not in self._retry_at:
                self._retry_at[log_id] = self.clock() + RETRY_SECONDS
            if self.clock() < self._retry_at.get(log_id, 0):
                continue
            # SQL and file observations are refreshed immediately before every attempt.
            state = self.check(entry["execution_id"])
            if not state or state.active_alert_id != log_id or not self.store.claim_alert(log_id):
                continue
            metadata = json.loads(entry["metadata"])
            try:
                schedule = self.manager.get_schedule_by_id(state.schedule_id) or ScheduledExperiment.from_dict(state.schedule)
                contacts = [self.manager.get_notification_contact(cid) for cid in schedule.notification_contacts]
                contacts = [c for c in contacts if c and c.is_active and c.email_address]
                if not contacts:
                    raise RuntimeError("No active notification contacts are configured for this schedule")
                service = service_getter()
                if service is None:
                    raise RuntimeError("Email notifications are disabled")
                result = service.schedule_alert(schedule, JobExecution.from_dict(state.execution), contacts=contacts,
                    trigger=entry["event_type"], context=metadata["context"],
                    trace_path=Path(state.trace_path) if state.trace_path else None, exact_trace=True,
                    message_id=f"<robotcontrol.{log_id}@robotcontrol.local>",
                    should_send=lambda: self.alert_is_current(state.execution_id, log_id))
                self.manager.update_notification_log(log_id, status="cancelled" if result.cancelled else "sent" if result.sent else "error",
                    error_message=result.error or "", processed_at=datetime.now(), recipients=result.recipients,
                    attachments=result.attachments, subject=result.subject, message=result.body,
                    metadata={**metadata, "attachment_notes": result.attachment_notes})
                if not result.sent and not result.cancelled:
                    self._retry_at[log_id] = self.clock() + RETRY_SECONDS
                else:
                    self._retry_at.pop(log_id, None)
            except Exception as exc:
                self.manager.update_notification_log(log_id, status="error", error_message=str(exc), processed_at=datetime.now())
                self._retry_at[log_id] = self.clock() + RETRY_SECONDS

    def alert_is_current(self, execution_id, log_id):
        if self._delivery_stop.is_set():
            return False
        state = self.check(execution_id)
        return bool(state and not state.finished and state.active_alert_id == log_id)
