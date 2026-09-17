"""Transactional scheduler safety state; schedule edits must not write these fields."""
import json

from backend.models import ManualRecoveryState
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable, check_timestamp
from backend.utils.datetime import utc_now_as_local_naive

RECOVERY_DELETE_MESSAGE = "Resolve manual recovery before deleting or archiving this schedule."


class SchedulerSafetyStore:
    def _safety_row(self, conn):
        row = conn.execute("SELECT * FROM SchedulerState WHERE id = 1").fetchone()
        if row is None:
            raise StorageUnavailable("Scheduler safety state is missing; review SQLite storage health")
        return row

    def _safety_event(self, conn, action, actor, note=None):
        conn.execute("UPDATE SchedulerState SET safety_revision = safety_revision + 1 WHERE id = 1")
        state = dict(self._safety_row(conn))
        conn.execute("INSERT INTO SchedulerSafetyEvents(revision, action, actor, note, state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (state['safety_revision'], action, actor, note, json.dumps(state), utc_now_as_local_naive().isoformat()))

    def _check_revision(self, conn, expected_revision):
        state = self._safety_row(conn)
        if type(expected_revision) is not int or expected_revision != state['safety_revision']:
            raise SafetyConflict("Scheduler safety state changed. Refresh and review it again.")
        return state

    def _guard_schedule_removal(self, conn, schedule_id):
        state = self._safety_row(conn)
        schedule = conn.execute("SELECT recovery_required FROM ScheduledExperiments WHERE schedule_id = ?", (schedule_id,)).fetchone()
        if (schedule and schedule['recovery_required']) or (state['recovery_required'] and state['recovery_schedule_id'] == schedule_id):
            raise SafetyConflict(RECOVERY_DELETE_MESSAGE)
        if conn.execute("SELECT 1 FROM JobExecutions WHERE schedule_id = ? AND status = 'running'", (schedule_id,)).fetchone() or conn.execute(
            "SELECT 1 FROM ExecutionMonitoring WHERE schedule_id = ? AND finished = 0", (schedule_id,)).fetchone():
            raise SafetyConflict("This schedule has a running execution or unfinished monitoring. Reconcile it before deleting or archiving.")

    def get_manual_recovery_state(self):
        with self._get_connection() as conn:
            # A failed read/write latches a hold, including after the connection recovers.
            conn.execute("BEGIN IMMEDIATE" if getattr(self, '_safety_fault', False) else "BEGIN")
            if getattr(self, '_safety_fault', False):
                self._safety_row(conn)
                conn.execute("UPDATE SchedulerState SET resume_required = 1 WHERE id = 1")
                self._safety_event(conn, 'storage_recovered', 'system', 'Explicit Resume required after a storage failure')
            row = self._safety_row(conn)
            pending = []
            for schedule in conn.execute("SELECT * FROM ScheduledExperiments WHERE recovery_required = 1 ORDER BY recovery_marked_at, schedule_id"):
                pending.append(dict(schedule_id=schedule['schedule_id'], experiment_name=schedule['experiment_name'],
                                    note=schedule['recovery_note'], triggered_at=schedule['recovery_marked_at'],
                                    triggered_by=schedule['recovery_marked_by'], schedule_missing=False, archived=bool(schedule['archived'])))
            origin = row['recovery_schedule_id']
            exists = origin is not None and conn.execute("SELECT 1 FROM ScheduledExperiments WHERE schedule_id = ?", (origin,)).fetchone() is not None
            if row['recovery_required'] and not any(item['schedule_id'] == origin for item in pending):
                pending.insert(0, dict(schedule_id=origin, experiment_name=row['recovery_experiment_name'], note=row['recovery_note'],
                                       triggered_at=row['recovery_triggered_at'], triggered_by=row['recovery_triggered_by'],
                                       schedule_missing=not exists, archived=False))
            broken_links = conn.execute("PRAGMA foreign_key_check").fetchone() is not None
            archived_unfinished = conn.execute("SELECT 1 FROM JobExecutionsArchive WHERE status IN ('pending', 'queued', 'running')").fetchone() is not None
            structural_error = getattr(self, '_integrity_error', None)
            healthy = not broken_links and not structural_error and not archived_unfinished
            result = ManualRecoveryState(
                active=bool(pending), note=row['recovery_note'], schedule_id=origin, experiment_name=row['recovery_experiment_name'],
                triggered_by=row['recovery_triggered_by'], triggered_at=self._parse_timestamp(row['recovery_triggered_at']),
                resolved_by=row['recovery_resolved_by'], resolved_at=self._parse_timestamp(row['recovery_resolved_at']),
                safety_revision=row['safety_revision'], resume_required=bool(row['resume_required']),
                pending_recoveries=pending, schedule_missing=bool(row['recovery_required'] and not exists),
                storage_healthy=healthy, storage_error=(structural_error or 'SQLite storage needs administrator review') if not healthy else None)
            if row['hxrun_maintenance_enabled']:
                result.resume_block_reason = 'Leave HxRun maintenance mode before resuming.'
            elif conn.execute('SELECT 1 FROM ExecutionMonitoring WHERE finished = 0').fetchone() or conn.execute("SELECT 1 FROM JobExecutions WHERE status = 'running' UNION SELECT 1 FROM JobExecutionsArchive WHERE status IN ('pending', 'queued', 'running')").fetchone():
                result.resume_block_reason = 'Reconcile unfinished executions before resuming.'
            conn.commit()
            self._safety_fault = False
            return result

    def mark_recovery_atomic(self, schedule_id, note, user, *, expected_updated_at=None, snapshot=None):
        timestamp = utc_now_as_local_naive().isoformat()
        with self._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            state = self._safety_row(conn)
            row = conn.execute('SELECT * FROM ScheduledExperiments WHERE schedule_id = ?', (schedule_id,)).fetchone()
            if row:
                check_timestamp(expected_updated_at, row['updated_at'])
                conn.execute('''UPDATE ScheduledExperiments SET is_active = 0, recovery_required = 1,
                    recovery_note = COALESCE(?, recovery_note), recovery_marked_at = ?, recovery_marked_by = ?,
                    recovery_resolved_at = NULL, recovery_resolved_by = NULL, updated_at = ? WHERE schedule_id = ?''',
                             (note, timestamp, user, timestamp, schedule_id))
            elif snapshot is None:
                raise SafetyConflict('Schedule no longer exists. Refresh and review recovery.')
            # Keep the first global incident, particularly one whose schedule was deleted.
            if not state['recovery_required']:
                conn.execute('''UPDATE SchedulerState SET recovery_required = 1, recovery_schedule_id = ?,
                    recovery_experiment_name = ?, recovery_note = ?, recovery_triggered_at = ?, recovery_triggered_by = ?,
                    recovery_resolved_at = NULL, recovery_resolved_by = NULL WHERE id = 1''',
                             (schedule_id, row['experiment_name'] if row else snapshot.experiment_name, note, timestamp, user))
            conn.execute('UPDATE SchedulerState SET resume_required = 1 WHERE id = 1')
            self._safety_event(conn, 'recovery_required', user, note)
            conn.commit()
        return self.get_schedule_by_id(schedule_id) if row else None

    def resolve_recovery_atomic(self, schedule_id, note, user, expected_revision, *, expected_updated_at=None):
        timestamp = utc_now_as_local_naive().isoformat()
        with self._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            state = self._check_revision(conn, expected_revision)
            row = conn.execute('SELECT * FROM ScheduledExperiments WHERE schedule_id = ?', (schedule_id,)).fetchone()
            global_match = state['recovery_required'] and state['recovery_schedule_id'] == schedule_id
            if not global_match and not (row and row['recovery_required']):
                raise SafetyConflict('This recovery has already been acknowledged or changed. Refresh and review it again.')
            if not row and not (note and note.strip()):
                raise SafetyConflict('A recovery note is required when the originating schedule is missing.')
            if row:
                check_timestamp(expected_updated_at, row['updated_at'])
                conn.execute('''UPDATE ScheduledExperiments SET recovery_required = 0, is_active = 0,
                    recovery_note = COALESCE(?, recovery_note), recovery_resolved_at = ?, recovery_resolved_by = ?,
                    updated_at = ? WHERE schedule_id = ?''', (note, timestamp, user, timestamp, schedule_id))
            if global_match:
                other = conn.execute('SELECT * FROM ScheduledExperiments WHERE recovery_required = 1 ORDER BY recovery_marked_at, schedule_id LIMIT 1').fetchone()
                if other:
                    conn.execute('''UPDATE SchedulerState SET recovery_required = 1, recovery_schedule_id = ?, recovery_experiment_name = ?,
                        recovery_note = ?, recovery_triggered_at = ?, recovery_triggered_by = ?, recovery_resolved_at = NULL,
                        recovery_resolved_by = NULL WHERE id = 1''', (other['schedule_id'], other['experiment_name'], other['recovery_note'], other['recovery_marked_at'], other['recovery_marked_by']))
                else:
                    conn.execute('UPDATE SchedulerState SET recovery_required = 0, recovery_resolved_at = ?, recovery_resolved_by = ? WHERE id = 1', (timestamp, user))
            conn.execute('UPDATE SchedulerState SET resume_required = 1 WHERE id = 1')
            self._safety_event(conn, 'recovery_acknowledged', user, note)
            conn.commit()
        return self.get_schedule_by_id(schedule_id) if row else None

    def validate_recovery_resolution(self, schedule_id, note, expected_revision):
        """Reject stale requests before touching execution observations; commit rechecks too."""
        with self._get_connection() as conn:
            conn.execute('BEGIN')
            state = self._check_revision(conn, expected_revision)
            row = conn.execute('SELECT recovery_required FROM ScheduledExperiments WHERE schedule_id = ?', (schedule_id,)).fetchone()
            if not (row and row[0]) and not (state['recovery_required'] and state['recovery_schedule_id'] == schedule_id):
                raise SafetyConflict('This recovery has already been acknowledged or changed. Refresh and review it again.')
            if not row and not (note and note.strip()):
                raise SafetyConflict('A recovery note is required when the originating schedule is missing.')

    def resume_dispatch(self, expected_revision, user):
        with self._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            state = self._check_revision(conn, expected_revision)
            if state['recovery_required'] or state['hxrun_maintenance_enabled'] or conn.execute('SELECT 1 FROM ScheduledExperiments WHERE recovery_required = 1').fetchone():
                raise SafetyConflict('Resolve all recovery issues and leave maintenance mode before resuming.')
            if conn.execute('SELECT 1 FROM ExecutionMonitoring WHERE finished = 0').fetchone() or conn.execute("SELECT 1 FROM JobExecutions WHERE status = 'running' UNION SELECT 1 FROM JobExecutionsArchive WHERE status IN ('pending', 'queued', 'running')").fetchone():
                raise SafetyConflict('Reconcile unfinished executions before resuming.')
            if getattr(self, '_safety_fault', False) or getattr(self, '_integrity_error', None) or conn.execute('PRAGMA foreign_key_check').fetchone():
                raise StorageUnavailable('Scheduler safety state unavailable. Review SQLite storage health.')
            conn.execute('UPDATE SchedulerState SET resume_required = 0 WHERE id = 1')
            self._safety_event(conn, 'dispatch_resumed', user)
            conn.commit()
        return self.get_manual_recovery_state()
