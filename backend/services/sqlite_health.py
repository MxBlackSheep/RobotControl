"""Reviewed SQLite repairs. Previews contain IDs/counts, never account secrets."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager, closing
from pathlib import Path

from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable, configure_connection

TERMINAL = {'completed', 'failed', 'cancelled', 'aborted', 'missed'}


class SQLiteHealthService:
    def __init__(self, path, kind, backup_directory):
        self.path = Path(path)
        self.kind = kind
        self.backup_directory = Path(backup_directory)

    @contextmanager
    def connection(self):
        # Never create an empty replacement for missing application storage.
        conn = sqlite3.connect(self.path.resolve().as_uri() + '?mode=rw', uri=True, timeout=2)
        try:
            configure_connection(conn)
            yield conn
        finally:
            conn.close()

    @staticmethod
    def fingerprint(conn):
        digest = hashlib.sha256()
        for line in conn.iterdump():
            digest.update(line.encode('utf-8'))
        return digest.hexdigest()

    def _inspect(self, conn):
        if [row[0] for row in conn.execute('PRAGMA quick_check')] != ['ok']:
            return {'healthy': False, 'structural_error': True, 'issues': [], 'message': 'Structural corruption: restore a verified backup.', 'token': None}
        issues = []
        def add(kind, identifier, description, repairable=True):
            issues.append(dict(kind=kind, id=identifier, description=description, repairable=repairable))
        if self.kind == 'authentication':
            for row in conn.execute('SELECT id FROM refresh_tokens WHERE user_id NOT IN (SELECT id FROM users)'):
                add('orphan_token', row[0], 'Remove a refresh token belonging to a deleted user.')
            for row in conn.execute('SELECT id FROM password_reset_requests WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users)'):
                add('orphan_reset', row[0], 'Keep reset history and clear its deleted-user reference.')
        else:
            for row in conn.execute('SELECT rowid FROM ScheduleNotificationContacts WHERE schedule_id NOT IN (SELECT schedule_id FROM ScheduledExperiments) OR contact_id NOT IN (SELECT contact_id FROM NotificationContacts)'):
                add('orphan_contact_link', row[0], 'Remove a contact association whose schedule or contact is missing.')
            for row in conn.execute('SELECT log_id FROM NotificationLog WHERE schedule_id IS NOT NULL AND schedule_id NOT IN (SELECT schedule_id FROM ScheduledExperiments)'):
                add('orphan_notification', row[0], 'Keep notification history and preserve its original schedule ID in metadata.')
            for row in conn.execute('SELECT * FROM JobExecutions WHERE schedule_id NOT IN (SELECT schedule_id FROM ScheduledExperiments)'):
                archive = conn.execute('SELECT * FROM JobExecutionsArchive WHERE execution_id = ?', (row['execution_id'],)).fetchone()
                conflict = archive is not None and any(archive[key] != row[key] for key in row.keys())
                if conflict:
                    add('execution_conflict', row['execution_id'], 'Live and archived history disagree; preserve both for offline review.', False)
                elif row['status'] not in TERMINAL:
                    add('unfinished_execution', row['execution_id'], 'Unfinished orphan execution: confirm the robot is ready and reconcile this run separately.', False)
                else:
                    add('orphan_execution', row['execution_id'], 'Preserve terminal execution in the archive, then remove the orphan live row.')
            for row in conn.execute("SELECT execution_id FROM JobExecutionsArchive WHERE status IN ('pending', 'queued', 'running') AND execution_id NOT IN (SELECT execution_id FROM JobExecutions)"):
                add('unfinished_archived_execution', row[0], 'Unfinished archived execution: confirm the robot is ready and reconcile this run separately.', False)
            for row in conn.execute('SELECT execution_id FROM ExecutionMonitoring WHERE finished = 0 AND execution_id NOT IN (SELECT execution_id FROM JobExecutions UNION SELECT execution_id FROM JobExecutionsArchive)'):
                add('missing_execution_history', row[0], 'An unfinished observation has no execution history; restore history from backup before reconciliation.', False)
            state = conn.execute('SELECT * FROM SchedulerState WHERE id = 1').fetchone()
            if not state:
                add('missing_state', 1, 'Restore a paused scheduler state requiring operator recovery acknowledgement.')
            else:
                flagged = conn.execute('SELECT 1 FROM ScheduledExperiments WHERE recovery_required = 1').fetchone()
                if flagged and not state['recovery_required']:
                    add('missing_global_recovery', 1, 'Restore the global recovery hold from the pending schedule flags.')
                if state['recovery_required'] and conn.execute('SELECT 1 FROM ScheduledExperiments WHERE schedule_id = ? AND (recovery_required = 0 OR is_active = 1)', (state['recovery_schedule_id'],)).fetchone():
                    add('missing_schedule_recovery', state['recovery_schedule_id'], 'Restore the schedule recovery flag and make it inactive.')
                for row in conn.execute('SELECT schedule_id FROM ScheduledExperiments WHERE recovery_required = 1 AND is_active = 1'):
                    add('active_recovery_schedule', row[0], 'Make this recovery-flagged schedule inactive.')
            # Catch relationships not explicitly handled; never guess at a repair.
            known_tables = {'JobExecutions', 'NotificationLog', 'ScheduleNotificationContacts'}
            for row in conn.execute('PRAGMA foreign_key_check'):
                if row[0] not in known_tables:
                    add('unknown_reference', row[0], 'Unsupported broken relationship; offline review required.', False)
        return dict(healthy=not issues, structural_error=False, issues=issues, token=self.fingerprint(conn),
                    message='Checks passed' if not issues else 'Review the proposed changes. Recovery is never cleared by a repair.')

    def preview(self):
        try:
            with self.connection() as conn:
                conn.execute('BEGIN')
                return self._inspect(conn)
        except (sqlite3.Error, OSError):
            return dict(healthy=False, structural_error=True, issues=[], token=None,
                        message='Storage could not be inspected. Check file access or restore a verified backup.')

    def _backup(self):
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        destination = self.backup_directory / f'{self.kind}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}.db'
        started = time.monotonic()
        def progress(status, remaining, total):
            if time.monotonic() - started > 30:
                raise StorageUnavailable('Backup timed out. No repairs were applied.')
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as source:
                with closing(sqlite3.connect(destination)) as target:
                    source.backup(target, pages=128, progress=progress, sleep=0.05)
                    if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                        raise StorageUnavailable('Backup verification failed. No repairs were applied.')
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination

    def _archive_orphan(self, conn, execution_id):
        columns = [row[1] for row in conn.execute('PRAGMA table_info(JobExecutions)')]
        names = ', '.join(columns)
        assignments = ', '.join(f'{name} = excluded.{name}' for name in columns if name != 'execution_id')
        conn.execute(f'INSERT INTO JobExecutionsArchive ({names}) SELECT {names} FROM JobExecutions WHERE execution_id = ? ON CONFLICT(execution_id) DO UPDATE SET {assignments}', (execution_id,))
        conn.execute('DELETE FROM JobExecutions WHERE execution_id = ?', (execution_id,))

    def _hold(self, conn, actor, action):
        if self.kind != 'scheduling':
            return
        conn.execute('UPDATE SchedulerState SET resume_required = 1, safety_revision = safety_revision + 1 WHERE id = 1')
        state = dict(conn.execute('SELECT * FROM SchedulerState WHERE id = 1').fetchone())
        conn.execute('INSERT INTO SchedulerSafetyEvents(revision, action, actor, state, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
                     (state['safety_revision'], action, actor, json.dumps(state)))

    def repair(self, token, actor):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            preview = self._inspect(conn)
            if preview['structural_error'] or not token or token != preview['token']:
                raise SafetyConflict('Storage changed or failed validation. Preview again; no repairs were applied.')
            repairs = [issue for issue in preview['issues'] if issue['repairable']]
            if not repairs:
                raise SafetyConflict('There are no automatic repairs in this preview. Resolve the remaining items explicitly.')
            backup = self._backup()
            for issue in repairs:
                kind, key = issue['kind'], issue['id']
                if kind == 'orphan_token':
                    conn.execute('DELETE FROM refresh_tokens WHERE id = ?', (key,))
                elif kind == 'orphan_reset':
                    conn.execute('UPDATE password_reset_requests SET user_id = NULL WHERE id = ?', (key,))
                elif kind == 'orphan_contact_link':
                    conn.execute('DELETE FROM ScheduleNotificationContacts WHERE rowid = ?', (key,))
                elif kind == 'orphan_notification':
                    row = conn.execute('SELECT schedule_id, metadata FROM NotificationLog WHERE log_id = ?', (key,)).fetchone()
                    try:
                        metadata = json.loads(row['metadata'] or '{}')
                        if not isinstance(metadata, dict):
                            metadata = {'original_metadata': metadata}
                    except ValueError:
                        metadata = {'original_metadata': row['metadata']}
                    metadata['original_schedule_id'] = row['schedule_id']
                    conn.execute('UPDATE NotificationLog SET schedule_id = NULL, metadata = ? WHERE log_id = ?', (json.dumps(metadata), key))
                elif kind == 'orphan_execution':
                    self._archive_orphan(conn, key)
                elif kind == 'missing_state':
                    revision = conn.execute('SELECT COALESCE(MAX(revision), 0) FROM SchedulerSafetyEvents').fetchone()[0]
                    conn.execute("INSERT INTO SchedulerState(id, recovery_required, recovery_note, resume_required, safety_revision) VALUES (1, 1, 'Missing scheduler state restored; operator acknowledgement required', 1, ?)", (revision,))
                elif kind == 'missing_global_recovery':
                    row = conn.execute('SELECT * FROM ScheduledExperiments WHERE recovery_required = 1 ORDER BY recovery_marked_at, schedule_id LIMIT 1').fetchone()
                    conn.execute('UPDATE SchedulerState SET recovery_required = 1, recovery_schedule_id = ?, recovery_experiment_name = ?, recovery_note = ?, recovery_triggered_at = ?, recovery_triggered_by = ? WHERE id = 1',
                                 (row['schedule_id'], row['experiment_name'], row['recovery_note'], row['recovery_marked_at'], row['recovery_marked_by']))
                elif kind == 'missing_schedule_recovery':
                    conn.execute('''UPDATE ScheduledExperiments SET recovery_required = 1, is_active = 0,
                        recovery_note = (SELECT recovery_note FROM SchedulerState WHERE id = 1),
                        recovery_marked_at = (SELECT recovery_triggered_at FROM SchedulerState WHERE id = 1),
                        recovery_marked_by = (SELECT recovery_triggered_by FROM SchedulerState WHERE id = 1),
                        updated_at = CURRENT_TIMESTAMP WHERE schedule_id = ?''', (key,))
                elif kind == 'active_recovery_schedule':
                    conn.execute('UPDATE ScheduledExperiments SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE schedule_id = ?', (key,))
            self._hold(conn, actor, 'storage_repaired')
            conn.commit()
        return {'backup': str(backup), 'repaired': len(repairs), 'preview': self.preview()}

    def reconcile_orphan(self, token, execution_id, actor, note):
        """Caller must hold scheduling locks and establish HxRun is absent."""
        if self.kind != 'scheduling' or not note.strip():
            raise SafetyConflict('A reconciliation note is required')
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            preview = self._inspect(conn)
            if preview['token'] != token or not any(i['kind'] in ('unfinished_execution', 'unfinished_archived_execution') and i['id'] == execution_id for i in preview['issues']):
                raise SafetyConflict('Execution changed. Preview and review it again.')
            backup = self._backup()
            conn.execute("UPDATE JobExecutions SET status = 'cancelled', end_time = CURRENT_TIMESTAMP, error_message = ? WHERE execution_id = ?", (f'Operator reconciliation by {actor}: {note}', execution_id))
            self._archive_orphan(conn, execution_id)
            conn.execute("UPDATE JobExecutionsArchive SET status = 'cancelled', end_time = CURRENT_TIMESTAMP, error_message = ? WHERE execution_id = ?", (f'Operator reconciliation by {actor}: {note}', execution_id))
            self._hold(conn, actor, 'orphan_execution_reconciled')
            conn.commit()
        return {'backup': str(backup), 'preview': self.preview()}
