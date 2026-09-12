"""Transactional storage for run observation and its notification outbox."""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from backend.models import JobExecution, ScheduledExperiment

MONITOR_EVENTS = ("log_inactive", "monitoring_unavailable")


class RunLogStore:
    def __init__(self, database):
        self.database = database

    def restore(self):
        with self.database._get_connection() as conn:
            rows = conn.execute("SELECT data FROM ExecutionMonitoring WHERE finished = 0").fetchall()
            # A crash may have happened between SMTP acceptance and recording success.
            conn.execute("UPDATE NotificationLog SET status = 'pending' WHERE status = 'sending' AND event_type IN (?, ?)", MONITOR_EVENTS)
            conn.execute("""
                UPDATE NotificationLog SET status = 'cancelled', processed_at = ?
                WHERE event_type IN (?, ?) AND status IN ('pending', 'error')
                  AND execution_id IN (SELECT execution_id FROM ExecutionMonitoring WHERE finished = 1)
            """, (datetime.now().isoformat(), *MONITOR_EVENTS))
            conn.commit()
            return [json.loads(row["data"]) for row in rows]

    def unfinished_executions(self):
        with self.database._get_connection() as conn:
            return [JobExecution.from_dict(dict(row)) for row in conn.execute(
                "SELECT * FROM JobExecutions WHERE status = 'running'"
            )]

    def save(self, data: Dict[str, Any], alert: Optional[Dict[str, Any]] = None):
        """Save observation and enqueue/cancel alerts in the same transaction."""
        with self.database._get_connection() as conn:
            conn.execute("""
                INSERT INTO ExecutionMonitoring (execution_id, schedule_id, finished, data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET finished = excluded.finished, data = excluded.data
            """, (data["execution_id"], data["schedule_id"], int(data["finished"]), json.dumps(data)))
            active_id = data.get("active_alert_id") or ""
            conn.execute("""
                UPDATE NotificationLog SET status = 'cancelled', processed_at = ?
                WHERE execution_id = ? AND event_type IN (?, ?)
                  AND status IN ('pending', 'error') AND log_id != ?
            """, (datetime.now().isoformat(), data["execution_id"], *MONITOR_EVENTS, active_id))
            if alert:
                conn.execute("""
                    INSERT OR IGNORE INTO NotificationLog
                    (log_id, schedule_id, execution_id, event_type, status, recipients, triggered_at, metadata)
                    VALUES (?, ?, ?, ?, 'pending', '[]', ?, ?)
                """, (active_id, data["schedule_id"], data["execution_id"], alert["event_type"],
                      datetime.now().isoformat(), json.dumps(alert)))
                # The episode may have been briefly unobservable, but has not resumed writing.
                conn.execute("UPDATE NotificationLog SET status = 'pending' WHERE log_id = ? AND status = 'cancelled'", (active_id,))
            conn.commit()

    def due_alerts(self):
        with self.database._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM NotificationLog WHERE event_type IN (?, ?)
                AND status IN ('pending', 'error') ORDER BY triggered_at
            """, MONITOR_EVENTS).fetchall()
            return [dict(row) for row in rows]

    def claim_alert(self, log_id):
        with self.database._get_connection() as conn:
            count = conn.execute("""
                UPDATE NotificationLog SET status = 'sending'
                WHERE log_id = ? AND status IN ('pending', 'error')
            """, (log_id,)).rowcount
            conn.commit()
            return count == 1

    def finalize(self, execution: JobExecution, schedule: ScheduledExperiment) -> bool:
        """Commit execution outcome and schedule advancement exactly once."""
        with self.database._get_connection() as conn:
            count = 0
            for table in ("JobExecutions", "JobExecutionsArchive"):
                count = conn.execute(f"""
                    UPDATE {table} SET status = ?, end_time = ?, duration_minutes = ?,
                        error_message = ?, hamilton_command = ?
                    WHERE execution_id = ? AND status IN ('running', 'pending')
                """, (execution.status, execution.end_time.isoformat() if execution.end_time else None,
                      execution.duration_minutes, execution.error_message, execution.hamilton_command,
                      execution.execution_id)).rowcount
                if count:
                    break
            if not count:
                return False
            # Do not overwrite settings or contacts edited while the method was running.
            conn.execute("UPDATE ScheduledExperiments SET is_active = ?, start_time = ? WHERE schedule_id = ?",
                         (int(schedule.is_active), schedule.start_time.isoformat() if schedule.start_time else None,
                          schedule.schedule_id))
            conn.commit()
            return True

    def execution(self, execution_id):
        with self.database._get_connection() as conn:
            row = conn.execute("SELECT * FROM JobExecutions WHERE execution_id = ?", (execution_id,)).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM JobExecutionsArchive WHERE execution_id = ?", (execution_id,)).fetchone()
            return JobExecution.from_dict(dict(row)) if row else None
