"""
SQLite Database Manager for Scheduling System

Provides a lightweight SQLite-based database for scheduling data that:
- Auto-creates in the data directory
- Works in both development and compiled modes
- Stores scheduling metadata separately from Hamilton's read-only database
- Can be extended for user management and other RobotControl-specific data
"""

import sqlite3
import logging
import threading
import json
import uuid
from backend.utils.filesystem import method_path_key
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager
from backend.utils.data_paths import get_data_path
from backend.models import (
    HxRunMaintenanceState,
    ScheduledExperiment,
    JobExecution,
    TimeoutConfig,
    ManualRecoveryState,
    NotificationContact,
    NotificationLogEntry,
    NotificationSettings,
)

try:
    from backend.utils.datetime import (
        ensure_local_naive,
        parse_iso_datetime_to_local,
        utc_now_as_local_naive,
    )
except ImportError:  # pragma: no cover - fallback
    from utils.datetime import (  # type: ignore
        ensure_local_naive,
        parse_iso_datetime_to_local,
        utc_now_as_local_naive,
    )

logger = logging.getLogger(__name__)


from backend.services.scheduling.safety_store import SchedulerSafetyStore
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable, configure_connection, check_timestamp


class SQLiteSchedulingDatabase(SchedulerSafetyStore):
    """SQLite database manager for scheduling system"""
    
    def __init__(self, db_name: str = "robotcontrol_scheduling.db"):
        """
        Initialize SQLite database for scheduling
        
        Args:
            db_name: Name of the SQLite database file
        """
        self.db_path = get_data_path() / db_name
        self._connection_lock = threading.RLock()
        self._schema_initialized = False
        self._safety_fault = False
        self._integrity_error = None
        
        logger.info(f"SQLite scheduling database: {self.db_path}")
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database schema"""
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                state_table_existed = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'SchedulerState'").fetchone() is not None
                cursor = conn.cursor()
                cursor.execute('''CREATE TABLE IF NOT EXISTS LabInstallation (
                    id INTEGER PRIMARY KEY CHECK(id=1), signature TEXT NOT NULL, identity TEXT NOT NULL, target TEXT NOT NULL)''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS LabScheduleBinding (
                    schedule_id TEXT PRIMARY KEY, target TEXT NOT NULL)''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS LabPreparation (
                    execution_id TEXT PRIMARY KEY, identity TEXT NOT NULL, steps TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
                
                # Create ExperimentMethods table to track all discovered .med files
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ExperimentMethods (
                        method_id TEXT PRIMARY KEY,
                        method_name TEXT NOT NULL,
                        file_path TEXT NOT NULL UNIQUE,
                        category TEXT,
                        description TEXT,
                        file_size INTEGER,
                        file_modified TEXT,
                        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        imported_by TEXT,
                        source_folder TEXT,
                        is_valid INTEGER DEFAULT 1,
                        last_used TEXT,
                        use_count INTEGER DEFAULT 0,
                        metadata TEXT
                    )
                """)
                
                # Create indexes for ExperimentMethods
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_method_name ON ExperimentMethods(method_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_method_category ON ExperimentMethods(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_method_valid ON ExperimentMethods(is_valid)")
                method_columns = {row[1] for row in cursor.execute('PRAGMA table_info(ExperimentMethods)')}
                for name, definition in (
                    ('archived', 'INTEGER NOT NULL DEFAULT 0'),
                    ('revision', 'INTEGER NOT NULL DEFAULT 1'),
                    ('path_status', "TEXT NOT NULL DEFAULT 'not_checked'"),
                    ('last_checked_at', 'TEXT'),
                    ('validation_reason', 'TEXT'),
                ):
                    if name not in method_columns:
                        cursor.execute(f'ALTER TABLE ExperimentMethods ADD COLUMN {name} {definition}')
                
                # Create ScheduledExperiments table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ScheduledExperiments (
                        schedule_id TEXT PRIMARY KEY,
                        experiment_name TEXT NOT NULL,
                        experiment_path TEXT NOT NULL,
                        schedule_type TEXT NOT NULL,
                        interval_hours INTEGER,
                        start_time TEXT,
                        estimated_duration INTEGER NOT NULL DEFAULT 60,
                        created_by TEXT NOT NULL DEFAULT 'system',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        timeout_minutes INTEGER,
                        timeout_action TEXT NOT NULL DEFAULT 'continue',
                        timeout_cleanup_experiment_name TEXT,
                        timeout_cleanup_experiment_path TEXT,
                        prerequisites TEXT,
                        archived INTEGER NOT NULL DEFAULT 0,
                        recovery_required INTEGER NOT NULL DEFAULT 0,
                        recovery_note TEXT,
                        recovery_marked_at TEXT,
                        recovery_marked_by TEXT,
                        recovery_resolved_at TEXT,
                        recovery_resolved_by TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create JobExecutions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS JobExecutions (
                        execution_id TEXT PRIMARY KEY,
                        schedule_id TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        start_time TEXT,
                        end_time TEXT,
                        duration_minutes INTEGER,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        error_message TEXT,
                        hamilton_command TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (schedule_id) REFERENCES ScheduledExperiments(schedule_id) ON DELETE CASCADE
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS JobExecutionsArchive (
                        execution_id TEXT PRIMARY KEY,
                        schedule_id TEXT NOT NULL,
                        experiment_name_snapshot TEXT,
                        experiment_path_snapshot TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        start_time TEXT,
                        end_time TEXT,
                        duration_minutes INTEGER,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        error_message TEXT,
                        hamilton_command TEXT,
                        created_at TEXT NOT NULL,
                        archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Scheduler state table for global recovery management
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS SchedulerState (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        recovery_required INTEGER NOT NULL DEFAULT 0,
                        recovery_note TEXT,
                        recovery_schedule_id TEXT,
                        recovery_experiment_name TEXT,
                        recovery_triggered_by TEXT,
                        recovery_triggered_at TEXT,
                        recovery_resolved_by TEXT,
                        recovery_resolved_at TEXT,
                        hxrun_maintenance_enabled INTEGER NOT NULL DEFAULT 0,
                        hxrun_maintenance_reason TEXT,
                        hxrun_maintenance_updated_by TEXT,
                        hxrun_maintenance_updated_at TEXT
                    )
                """)
                if not state_table_existed:
                    cursor.execute("INSERT INTO SchedulerState (id) VALUES (1)")


                # Create indexes for performance
                # No execution foreign key: legacy execution writes use INSERT OR REPLACE.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ExecutionMonitoring (
                        execution_id TEXT PRIMARY KEY,
                        schedule_id TEXT NOT NULL,
                        finished INTEGER NOT NULL DEFAULT 0,
                        data TEXT NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_start_time ON ScheduledExperiments(start_time)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_active ON ScheduledExperiments(is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON JobExecutions(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_schedule_id ON JobExecutions(schedule_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_archive_schedule_id ON JobExecutionsArchive(schedule_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_archive_created_at ON JobExecutionsArchive(created_at)")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS NotificationContacts (
                        contact_id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        email_address TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ScheduleNotificationContacts (
                        schedule_id TEXT NOT NULL,
                        contact_id TEXT NOT NULL,
                        added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (schedule_id, contact_id),
                        FOREIGN KEY (schedule_id) REFERENCES ScheduledExperiments(schedule_id) ON DELETE CASCADE,
                        FOREIGN KEY (contact_id) REFERENCES NotificationContacts(contact_id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_notification_contacts_active ON NotificationContacts(is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_contacts_schedule ON ScheduleNotificationContacts(schedule_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_contacts_contact ON ScheduleNotificationContacts(contact_id)")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS NotificationLog (
                        log_id TEXT PRIMARY KEY,
                        schedule_id TEXT,
                        execution_id TEXT,
                        event_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        subject TEXT,
                        message TEXT,
                        recipients TEXT NOT NULL,
                        attachments TEXT,
                        error_message TEXT,
                        triggered_at TEXT NOT NULL,
                        processed_at TEXT,
                        metadata TEXT,
                        FOREIGN KEY (schedule_id) REFERENCES ScheduledExperiments(schedule_id) ON DELETE SET NULL
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_notification_log_schedule ON NotificationLog(schedule_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_notification_log_execution ON NotificationLog(execution_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_notification_log_event ON NotificationLog(event_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_notification_log_status ON NotificationLog(status)")

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS NotificationSettings (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        smtp_host TEXT,
                        smtp_port INTEGER NOT NULL DEFAULT 587,
                        smtp_username TEXT,
                        smtp_sender TEXT,
                        smtp_password_encrypted TEXT,
                        use_tls INTEGER NOT NULL DEFAULT 1,
                        use_ssl INTEGER NOT NULL DEFAULT 0,
                        manual_recovery_recipients TEXT,
                        updated_at TEXT,
                        updated_by TEXT
                    )
                    """
                )
                # Ensure manual_recovery_recipients column exists for legacy databases
                settings_columns = {
                    column["name"]
                    for column in cursor.execute("PRAGMA table_info(NotificationSettings)")
                }
                if "manual_recovery_recipients" not in settings_columns:
                    cursor.execute(
                        "ALTER TABLE NotificationSettings ADD COLUMN manual_recovery_recipients TEXT DEFAULT ''"
                    )
                    logger.info("SQLite scheduling database: added manual_recovery_recipients column to NotificationSettings")
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO NotificationSettings (
                        id, smtp_port, use_tls, use_ssl, manual_recovery_recipients
                    ) VALUES (1, 587, 1, 0, '')
                    """
                )
                
                conn.commit()

                existing_columns = {col['name'] for col in cursor.execute("PRAGMA table_info(ScheduledExperiments)")}
                column_alterations = [
                    ('log_inactivity_threshold_minutes', "ALTER TABLE ScheduledExperiments ADD COLUMN log_inactivity_threshold_minutes INTEGER NOT NULL DEFAULT 3"),
                    ('recovery_required', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_required INTEGER NOT NULL DEFAULT 0"),
                    ('recovery_note', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_note TEXT"),
                    ('recovery_marked_at', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_marked_at TEXT"),
                    ('recovery_marked_by', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_marked_by TEXT"),
                    ('recovery_resolved_at', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_resolved_at TEXT"),
                    ('recovery_resolved_by', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_resolved_by TEXT"),
                    ('archived', "ALTER TABLE ScheduledExperiments ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"),
                    ('timeout_minutes', "ALTER TABLE ScheduledExperiments ADD COLUMN timeout_minutes INTEGER"),
                    ('timeout_action', "ALTER TABLE ScheduledExperiments ADD COLUMN timeout_action TEXT NOT NULL DEFAULT 'continue'"),
                    ('timeout_cleanup_experiment_name', "ALTER TABLE ScheduledExperiments ADD COLUMN timeout_cleanup_experiment_name TEXT"),
                    ('timeout_cleanup_experiment_path', "ALTER TABLE ScheduledExperiments ADD COLUMN timeout_cleanup_experiment_path TEXT"),
                ]
                for column_name, alter_sql in column_alterations:
                    if column_name not in existing_columns:
                        try:
                            cursor.execute(alter_sql)
                            logger.info("SQLite scheduling database: added column %s", column_name)
                        except Exception as alter_exc:
                            raise StorageUnavailable(f"Unable to migrate scheduling column {column_name}") from alter_exc

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_recovery_required ON ScheduledExperiments(recovery_required)")

                scheduler_state_columns = {col["name"] for col in cursor.execute("PRAGMA table_info(SchedulerState)")}
                scheduler_state_alterations = [
                    ('safety_revision', 'ALTER TABLE SchedulerState ADD COLUMN safety_revision INTEGER NOT NULL DEFAULT 0'),
                    ('resume_required', 'ALTER TABLE SchedulerState ADD COLUMN resume_required INTEGER NOT NULL DEFAULT 0'),
                    (
                        "hxrun_maintenance_enabled",
                        "ALTER TABLE SchedulerState ADD COLUMN hxrun_maintenance_enabled INTEGER NOT NULL DEFAULT 0",
                    ),
                    ("hxrun_maintenance_reason", "ALTER TABLE SchedulerState ADD COLUMN hxrun_maintenance_reason TEXT"),
                    ("hxrun_maintenance_updated_by", "ALTER TABLE SchedulerState ADD COLUMN hxrun_maintenance_updated_by TEXT"),
                    ("hxrun_maintenance_updated_at", "ALTER TABLE SchedulerState ADD COLUMN hxrun_maintenance_updated_at TEXT"),
                ]
                for column_name, alter_sql in scheduler_state_alterations:
                    if column_name not in scheduler_state_columns:
                        try:
                            cursor.execute(alter_sql)
                            logger.info("SQLite scheduling database: added SchedulerState column %s", column_name)
                        except Exception as alter_exc:
                            raise StorageUnavailable(f"Unable to migrate scheduler state {column_name}") from alter_exc
                cursor.execute("CREATE TABLE IF NOT EXISTS SchemaMigrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
                cursor.execute("CREATE TABLE IF NOT EXISTS SchedulerSafetyEvents (revision INTEGER PRIMARY KEY, action TEXT NOT NULL, actor TEXT NOT NULL, note TEXT, state TEXT NOT NULL, created_at TEXT NOT NULL)")
                if not cursor.execute('SELECT 1 FROM SchemaMigrations WHERE version = 1').fetchone():
                    cursor.execute('UPDATE SchedulerState SET resume_required = 1 WHERE recovery_required = 1 OR EXISTS(SELECT 1 FROM ScheduledExperiments WHERE recovery_required = 1)')
                    cursor.execute("INSERT INTO SchemaMigrations VALUES (1, CURRENT_TIMESTAMP)")
                conn.commit()
                checks = [row[0] for row in conn.execute('PRAGMA quick_check')]
                self._integrity_error = None if checks == ['ok'] else 'SQLite integrity check failed; restore a verified backup'

                # Test database access
                cursor.execute("SELECT COUNT(*) FROM ScheduledExperiments")
                count = cursor.fetchone()[0]
                
                self._schema_initialized = True
                logger.info(f"SQLite scheduling database initialized successfully ({count} existing schedules)")
                
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
            raise
    
    @contextmanager
    def _get_connection(self):
        """Bounded connections; storage failures latch a scheduler hold."""
        with self._connection_lock:
            conn = None
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=2.0)
                configure_connection(conn)
                yield conn
            except (sqlite3.Error, StorageUnavailable):
                self._safety_fault = True
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()

    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return parse_iso_datetime_to_local(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _serialize_timestamp(value: Optional[datetime]) -> Optional[str]:
        """Serialize a datetime to ISO string using local wall-clock semantics."""
        if value is None:
            return None
        return ensure_local_naive(value).isoformat()

    def create_schedule(self, schedule: ScheduledExperiment) -> bool:
        """
        Create a new scheduled experiment
        
        Args:
            schedule: ScheduledExperiment to create
            
        Returns:
            bool: True if created successfully
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO ScheduledExperiments (
                        schedule_id, experiment_name, experiment_path, schedule_type,
                        interval_hours, start_time, estimated_duration, created_by,
                        is_active, archived, timeout_minutes, timeout_action,
                        timeout_cleanup_experiment_name, timeout_cleanup_experiment_path, prerequisites,
                        recovery_required, recovery_note, recovery_marked_at, recovery_marked_by,
                        recovery_resolved_at, recovery_resolved_by, created_at, updated_at,
                        log_inactivity_threshold_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    schedule.schedule_id,
                    schedule.experiment_name,
                    schedule.experiment_path,
                    schedule.schedule_type,
                    schedule.interval_hours,
                    self._serialize_timestamp(schedule.start_time),
                    schedule.estimated_duration,
                    schedule.created_by,
                    1 if schedule.is_active else 0,
                    1 if getattr(schedule, "archived", False) else 0,
                    schedule.timeout_config.timeout_minutes if schedule.timeout_config else None,
                    schedule.timeout_config.action if schedule.timeout_config else "continue",
                    schedule.timeout_config.cleanup_experiment_name if schedule.timeout_config else None,
                    schedule.timeout_config.cleanup_experiment_path if schedule.timeout_config else None,
                    json.dumps(schedule.prerequisites) if schedule.prerequisites else None,
                    1 if schedule.recovery_required else 0,
                    schedule.recovery_note,
                    self._serialize_timestamp(schedule.recovery_marked_at),
                    schedule.recovery_marked_by,
                    self._serialize_timestamp(schedule.recovery_resolved_at),
                    schedule.recovery_resolved_by,
                    self._serialize_timestamp(schedule.created_at),
                    self._serialize_timestamp(schedule.updated_at),
                    schedule.log_inactivity_threshold_minutes,
                ))
                self._replace_schedule_contacts(conn, schedule.schedule_id, schedule.notification_contacts or [])
                conn.execute('INSERT INTO LabScheduleBinding(schedule_id,target) SELECT ?,target FROM LabInstallation WHERE id=1', (schedule.schedule_id,))
                conn.commit()
                logger.info(f"Created schedule in SQLite: {schedule.experiment_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create schedule in SQLite: {e}")
            return False
    
    def get_active_schedules(self) -> List[ScheduledExperiment]:
        """
        Get all active scheduled experiments
        
        Returns:
            List of active ScheduledExperiment objects
        """
        schedules = []
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM ScheduledExperiments 
                    WHERE is_active = 1 AND archived = 0
                    ORDER BY start_time ASC
                """)
                
                rows = cursor.fetchall()
                
                for row in rows:
                    schedule = self._row_to_scheduled_experiment(row, conn)
                    if schedule:
                        schedules.append(schedule)
                        
        except (sqlite3.Error, StorageUnavailable):
            raise
        except Exception as e:
            logger.error(f"Failed to get active schedules from SQLite: {e}")
        
        return schedules

    def get_schedules(self, *, active_only: bool, archived_only: bool) -> List[ScheduledExperiment]:
        """Fetch schedules filtered by active/archive state."""
        schedules: List[ScheduledExperiment] = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                clauses: List[str] = []

                if archived_only:
                    clauses.append("archived = 1")
                else:
                    clauses.append("archived = 0")
                    if active_only:
                        clauses.append("is_active = 1")

                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                query = f"""
                    SELECT * FROM ScheduledExperiments
                    {where}
                    ORDER BY start_time ASC
                """

                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    schedule = self._row_to_scheduled_experiment(row, conn)
                    if schedule:
                        schedules.append(schedule)
        except (sqlite3.Error, StorageUnavailable):
            raise
        except Exception as exc:
            logger.error("Failed to get schedules: %s", exc)
        return schedules

    def get_schedule_by_id(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        """
        Get a specific schedule by ID
        
        Args:
            schedule_id: Schedule identifier
            
        Returns:
            ScheduledExperiment or None if not found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM ScheduledExperiments WHERE schedule_id = ?", (schedule_id,))
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_scheduled_experiment(row, conn)
                    
        except (sqlite3.Error, StorageUnavailable):
            raise
        except Exception as e:
            logger.error(f"Failed to get schedule {schedule_id} from SQLite: {e}")
        
        return None

    def update_schedule(
        self,
        schedule: ScheduledExperiment,
        *,
        touch_updated_at: bool = True,
        expected_updated_at: Optional[str] = None,
    ) -> bool:
        """
        Update an existing scheduled experiment
        
        Args:
            schedule: Updated ScheduledExperiment
            
        Returns:
            bool: True if updated successfully
        """
        try:
            with self._get_connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                current = conn.execute('SELECT * FROM ScheduledExperiments WHERE schedule_id = ?', (schedule.schedule_id,)).fetchone()
                if not current:
                    raise SafetyConflict('Schedule no longer exists')
                check_timestamp(expected_updated_at, current['updated_at'])
                if schedule.archived and not current['archived']:
                    self._guard_schedule_removal(conn, schedule.schedule_id)
                if schedule.is_active and current['recovery_required']:
                    raise SafetyConflict('Resolve manual recovery before activating this schedule.')
                cursor = conn.cursor()
                
                set_clauses = [
                    "experiment_name = ?",
                    "experiment_path = ?",
                    "schedule_type = ?",
                    "interval_hours = ?",
                    "start_time = ?",
                    "estimated_duration = ?",
                    "log_inactivity_threshold_minutes = ?",
                    "is_active = CASE WHEN recovery_required = 1 OR archived = 1 THEN 0 ELSE ? END",
                    "archived = ?",
                    "timeout_minutes = ?",
                    "timeout_action = ?",
                    "timeout_cleanup_experiment_name = ?",
                    "timeout_cleanup_experiment_path = ?",
                    "prerequisites = ?",
                ]
                params: List[Any] = [
                    schedule.experiment_name,
                    schedule.experiment_path,
                    schedule.schedule_type,
                    schedule.interval_hours,
                    self._serialize_timestamp(schedule.start_time),
                    schedule.estimated_duration,
                    schedule.log_inactivity_threshold_minutes,
                    1 if schedule.is_active else 0,
                    1 if getattr(schedule, "archived", False) else 0,
                    schedule.timeout_config.timeout_minutes if schedule.timeout_config else None,
                    schedule.timeout_config.action if schedule.timeout_config else "continue",
                    schedule.timeout_config.cleanup_experiment_name if schedule.timeout_config else None,
                    schedule.timeout_config.cleanup_experiment_path if schedule.timeout_config else None,
                    json.dumps(schedule.prerequisites) if schedule.prerequisites else None,
                ]

                if touch_updated_at:
                    updated_value = self._serialize_timestamp(schedule.updated_at)
                    if not updated_value:
                        updated_value = utc_now_as_local_naive().isoformat()
                    set_clauses.append("updated_at = ?")
                    params.append(updated_value)

                params.append(schedule.schedule_id)

                sql = f"""
                    UPDATE ScheduledExperiments SET
                        {', '.join(set_clauses)}
                    WHERE schedule_id = ?
                """

                cursor.execute(sql, params)
                
                self._replace_schedule_contacts(conn, schedule.schedule_id, schedule.notification_contacts or [])
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Updated schedule in SQLite: {schedule.experiment_name}")
                    return True
                else:
                    logger.warning(f"No schedule found to update: {schedule.schedule_id}")
                    return False
                    
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as e:
            logger.error(f"Failed to update schedule in SQLite: {e}")
            return False

    # ------------------------------------------------------------------
    # Notification settings (global SMTP)
    # ------------------------------------------------------------------

    def get_notification_settings(self) -> NotificationSettings:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM NotificationSettings WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return NotificationSettings.from_row(row)
        except Exception as exc:
            logger.error("Failed to load notification settings: %s", exc)
        return NotificationSettings()

    def update_notification_settings(
        self,
        settings: NotificationSettings,
        *,
        update_password: bool,
        password_encrypted: Optional[str],
    ) -> NotificationSettings:
        timestamp = datetime.utcnow().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                set_clauses = [
                    "smtp_host = :smtp_host",
                    "smtp_port = :smtp_port",
                    "smtp_username = :smtp_username",
                    "smtp_sender = :smtp_sender",
                    "use_tls = :use_tls",
                    "use_ssl = :use_ssl",
                    "manual_recovery_recipients = :manual_recovery_recipients",
                    "updated_at = :updated_at",
                    "updated_by = :updated_by",
                ]
                params = {
                    "smtp_host": settings.host,
                    "smtp_port": settings.port,
                    "smtp_username": settings.username,
                    "smtp_sender": settings.sender,
                    "use_tls": 1 if settings.use_tls else 0,
                    "use_ssl": 1 if settings.use_ssl else 0,
                    "manual_recovery_recipients": ",".join(settings.manual_recovery_recipients or []),
                    "updated_at": timestamp,
                    "updated_by": settings.updated_by,
                }
                if update_password:
                    set_clauses.append("smtp_password_encrypted = :smtp_password_encrypted")
                    params["smtp_password_encrypted"] = password_encrypted
                query = f"""
                    UPDATE NotificationSettings
                    SET {", ".join(set_clauses)}
                    WHERE id = 1
                """
                cursor.execute(query, params)
                if cursor.rowcount == 0:
                    # Ensure the row exists, then retry (initialization resilience)
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO NotificationSettings (
                            id, smtp_host, smtp_port, smtp_username, smtp_sender,
                            smtp_password_encrypted, use_tls, use_ssl, manual_recovery_recipients, updated_at, updated_by
                        ) VALUES (
                            1, :smtp_host, :smtp_port, :smtp_username, :smtp_sender,
                            :smtp_password_encrypted, :use_tls, :use_ssl, :manual_recovery_recipients, :updated_at, :updated_by
                        )
                        """,
                        {
                            **params,
                            "smtp_password_encrypted": password_encrypted if update_password else None,
                        },
                    )
                conn.commit()

                cursor.execute("SELECT * FROM NotificationSettings WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return NotificationSettings.from_row(row)
        except Exception as exc:
            logger.error("Failed to update notification settings: %s", exc)
        return NotificationSettings()

    # ------------------------------------------------------------------
    # Notification contacts
    # ------------------------------------------------------------------

    def get_notification_contacts(self, include_inactive: bool = False) -> List[NotificationContact]:
        contacts: List[NotificationContact] = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if include_inactive:
                    cursor.execute(
                        "SELECT * FROM NotificationContacts ORDER BY is_active DESC, display_name ASC"
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM NotificationContacts WHERE is_active = 1 ORDER BY display_name ASC"
                    )
                rows = cursor.fetchall()
                for row in rows:
                    contacts.append(
                        NotificationContact.from_dict(
                            {
                                "contact_id": row["contact_id"],
                                "display_name": row["display_name"],
                                "email_address": row["email_address"],
                                "is_active": bool(row["is_active"]),
                                "created_at": row["created_at"],
                                "updated_at": row["updated_at"],
                            }
                        )
                    )
        except Exception as exc:
            logger.error(f"Failed to load notification contacts: {exc}")
        return contacts

    def create_notification_contact(self, contact: NotificationContact) -> Optional[NotificationContact]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO NotificationContacts (
                        contact_id, display_name, email_address, is_active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contact.contact_id,
                        contact.display_name,
                        contact.email_address,
                        1 if contact.is_active else 0,
                        contact.created_at.isoformat() if contact.created_at else datetime.now().isoformat(),
                        contact.updated_at.isoformat() if contact.updated_at else datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                return contact
        except Exception as exc:
            logger.error(f"Failed to create notification contact: {exc}")
            return None

    def update_notification_contact(self, contact: NotificationContact) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE NotificationContacts
                    SET display_name = ?, email_address = ?, is_active = ?, updated_at = ?
                    WHERE contact_id = ?
                    """,
                    (
                        contact.display_name,
                        contact.email_address,
                        1 if contact.is_active else 0,
                        datetime.now().isoformat(),
                        contact.contact_id,
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to update notification contact {contact.contact_id}: {exc}")
            return False

    def delete_notification_contact(self, contact_id: str) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Remove schedule associations first (cascade should handle, but ensure manual fallback)
                cursor.execute(
                    "DELETE FROM ScheduleNotificationContacts WHERE contact_id = ?", (contact_id,)
                )
                cursor.execute(
                    "DELETE FROM NotificationContacts WHERE contact_id = ?", (contact_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to delete notification contact {contact_id}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Notification logging
    # ------------------------------------------------------------------

    def create_notification_log(self, entry: NotificationLogEntry) -> Optional[NotificationLogEntry]:
        """Persist a new notification log entry."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if entry.schedule_id and not conn.execute('SELECT 1 FROM ScheduledExperiments WHERE schedule_id = ?', (entry.schedule_id,)).fetchone():
                    entry.metadata = {**(entry.metadata or {}), 'original_schedule_id': entry.schedule_id}
                    entry.schedule_id = None
                cursor.execute(
                    """
                    INSERT INTO NotificationLog (
                        log_id, schedule_id, execution_id, event_type, status,
                        subject, message, recipients, attachments, error_message,
                        triggered_at, processed_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.log_id,
                        entry.schedule_id,
                        entry.execution_id,
                        entry.event_type,
                        entry.status,
                        entry.subject,
                        entry.message,
                        json.dumps(entry.recipients or []),
                        json.dumps(entry.attachments or []),
                        entry.error_message,
                        entry.triggered_at.isoformat() if entry.triggered_at else datetime.now().isoformat(),
                        entry.processed_at.isoformat() if entry.processed_at else None,
                        json.dumps(entry.metadata or {}),
                    ),
                )
                conn.commit()
                return entry
        except Exception as exc:
            logger.error("Failed to create notification log %s: %s", entry.log_id, exc)
            return None

    def update_notification_log(
        self,
        log_id: str,
        *,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        processed_at: Optional[datetime] = None,
        recipients: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        subject: Optional[str] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update fields of a notification log entry."""
        fields: List[str] = []
        params: List[Any] = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if processed_at is not None:
            fields.append("processed_at = ?")
            params.append(processed_at.isoformat())
        if recipients is not None:
            fields.append("recipients = ?")
            params.append(json.dumps(recipients))
        if attachments is not None:
            fields.append("attachments = ?")
            params.append(json.dumps(attachments))
        if subject is not None:
            fields.append("subject = ?")
            params.append(subject)
        if message is not None:
            fields.append("message = ?")
            params.append(message)
        if metadata is not None:
            fields.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not fields:
            return True

        params.append(log_id)
        query = f"UPDATE NotificationLog SET {', '.join(fields)} WHERE log_id = ?"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("Failed to update notification log %s: %s", log_id, exc)
            return False

    def notification_log_exists(self, execution_id: str, event_type: str) -> bool:
        """Check if a notification log already exists for an execution/event pair."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM NotificationLog
                    WHERE execution_id = ? AND event_type = ?
                    LIMIT 1
                    """,
                    (execution_id, event_type),
                )
                return cursor.fetchone() is not None
        except Exception as exc:
            logger.error("Failed to query notification log existence for %s/%s: %s", execution_id, event_type, exc)
            return False

    def get_notification_logs(
        self,
        limit: int = 50,
        *,
        schedule_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[NotificationLogEntry]:
        """Return notification log entries ordered by trigger time descending."""
        logs: List[NotificationLogEntry] = []
        clauses: List[str] = []
        params: List[Any] = []
        if schedule_id:
            clauses.append("schedule_id = ?")
            params.append(schedule_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT *
            FROM NotificationLog
            {where}
            ORDER BY datetime(triggered_at) DESC
            LIMIT ?
        """
        params.append(max(1, limit))

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                for row in rows:
                    logs.append(self._row_to_notification_log(row))
        except Exception as exc:
            logger.error("Failed to load notification logs: %s", exc)
        return logs
    
    def get_hxrun_maintenance_state(self) -> HxRunMaintenanceState:
        """Return the persisted HxRun maintenance mode flag and metadata."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT hxrun_maintenance_enabled, hxrun_maintenance_reason, "
                    "hxrun_maintenance_updated_by, hxrun_maintenance_updated_at "
                    "FROM SchedulerState WHERE id = 1"
                )
                row = cursor.fetchone()
        except (sqlite3.Error, StorageUnavailable):
            raise
        except Exception as exc:
            logger.error(f"Failed to load HxRun maintenance state: {exc}")
            row = None

        if not row:
            raise StorageUnavailable("Scheduler maintenance state is missing; review SQLite storage health")

        return HxRunMaintenanceState(
            enabled=bool(row["hxrun_maintenance_enabled"]),
            reason=row["hxrun_maintenance_reason"],
            updated_by=row["hxrun_maintenance_updated_by"],
            updated_at=self._parse_timestamp(row["hxrun_maintenance_updated_at"]),
        )

    def set_hxrun_maintenance_state(
        self,
        enabled: bool,
        reason: Optional[str],
        user: str,
    ) -> HxRunMaintenanceState:
        """Persist HxRun maintenance mode flag updates."""
        timestamp = datetime.now().isoformat()
        normalized_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE SchedulerState SET
                        hxrun_maintenance_enabled = ?,
                        hxrun_maintenance_reason = ?,
                        hxrun_maintenance_updated_by = ?,
                        hxrun_maintenance_updated_at = ?
                    WHERE id = 1
                    """,
                    (1 if enabled else 0, normalized_reason, user, timestamp),
                )
                conn.commit()
        except (sqlite3.Error, StorageUnavailable):
            raise
        except Exception as exc:
            logger.error(f"Failed to persist HxRun maintenance state: {exc}")

        return self.get_hxrun_maintenance_state()

    def _archive_job_executions(
        self,
        cursor: sqlite3.Cursor,
        schedule_id: str,
        *,
        name_snapshot: Optional[str] = None,
        path_snapshot: Optional[str] = None,
    ) -> None:
        """Persist historical job executions before their schedule is removed."""
        cursor.execute(
            """
            INSERT OR IGNORE INTO JobExecutionsArchive (
                execution_id,
                schedule_id,
                experiment_name_snapshot,
                experiment_path_snapshot,
                status,
                start_time,
                end_time,
                duration_minutes,
                retry_count,
                error_message,
                hamilton_command,
                created_at,
                archived_at
            )
            SELECT
                je.execution_id,
                je.schedule_id,
                COALESCE(se.experiment_name, ?),
                COALESCE(se.experiment_path, ?),
                je.status,
                je.start_time,
                je.end_time,
                je.duration_minutes,
                je.retry_count,
                je.error_message,
                je.hamilton_command,
                je.created_at,
                CURRENT_TIMESTAMP
            FROM JobExecutions je
            LEFT JOIN ScheduledExperiments se ON je.schedule_id = se.schedule_id
            WHERE je.schedule_id = ?
            """,
            (name_snapshot, path_snapshot, schedule_id),
        )

        logger.debug(
            "Archived executions for %s using name=%r path=%r",
            schedule_id,
            name_snapshot,
            path_snapshot,
        )

    def delete_schedule(
        self,
        schedule_id: str,
        *,
        name_snapshot: Optional[str] = None,
        path_snapshot: Optional[str] = None,
        expected_updated_at: Optional[str] = None,
    ) -> bool:
        """
        Delete a scheduled experiment
        
        Args:
            schedule_id: Schedule identifier to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._guard_schedule_removal(conn, schedule_id)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT experiment_name, experiment_path, updated_at FROM ScheduledExperiments WHERE schedule_id = ?",
                    (schedule_id,)
                )
                schedule_row = cursor.fetchone()
                if not schedule_row:
                    logger.warning(f"No schedule found to delete: {schedule_id}")
                    return False

                check_timestamp(expected_updated_at, schedule_row['updated_at'])
                cursor.execute("UPDATE JobExecutions SET status = 'cancelled', end_time = ?, error_message = 'Schedule deleted before dispatch' WHERE schedule_id = ? AND status IN ('pending', 'queued')", (utc_now_as_local_naive().isoformat(), schedule_id))
                if not name_snapshot:
                    name_snapshot = schedule_row["experiment_name"]
                if not path_snapshot:
                    path_snapshot = schedule_row["experiment_path"]

                cursor.execute(
                    "SELECT COUNT(*) FROM JobExecutions WHERE schedule_id = ?",
                    (schedule_id,)
                )
                execution_count = cursor.fetchone()[0]

                if execution_count:
                    logger.debug(
                        "Archiving %d execution(s) for %s using name=%r path=%r",
                        execution_count,
                        schedule_id,
                        name_snapshot,
                        path_snapshot,
                    )
                    self._archive_job_executions(
                        cursor,
                        schedule_id,
                        name_snapshot=name_snapshot,
                        path_snapshot=path_snapshot,
                    )

                cursor.execute(
                    "DELETE FROM ScheduledExperiments WHERE schedule_id = ?",
                    (schedule_id,)
                )

                conn.commit()
                
                if cursor.rowcount > 0:
                    if execution_count:
                        logger.info(
                            "Archived %d execution(s) before deleting schedule %s",
                            execution_count,
                            schedule_id
                        )
                    logger.info(f"Deleted schedule from SQLite: {schedule_id}")
                    return True
                else:
                    logger.warning(f"No schedule found to delete: {schedule_id}")
                    return False
                    
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as e:
            logger.error(f"Failed to delete schedule from SQLite: {e}")
            return False
    
    def create_job_execution(self, execution: JobExecution) -> bool:
        """Upsert live runs; late callbacks only update existing archived history."""
        with self._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            schedule_exists = conn.execute('SELECT 1 FROM ScheduledExperiments WHERE schedule_id = ?', (execution.schedule_id,)).fetchone()
            if execution.status == 'running':
                state = self._safety_row(conn)
                current = conn.execute('SELECT is_active, archived, recovery_required FROM ScheduledExperiments WHERE schedule_id = ?', (execution.schedule_id,)).fetchone()
                if not current or not current['is_active'] or current['archived'] or current['recovery_required'] or state['recovery_required'] or state['resume_required'] or state['hxrun_maintenance_enabled']:
                    raise SafetyConflict('Scheduler safety state blocks this execution from starting')
                if self._safety_fault or self._integrity_error or conn.execute('PRAGMA foreign_key_check').fetchone():
                    raise StorageUnavailable('Scheduler safety state unavailable; execution was not started')
            values = (execution.status, self._serialize_timestamp(execution.start_time), self._serialize_timestamp(execution.end_time),
                      execution.duration_minutes, execution.retry_count, execution.error_message, execution.hamilton_command)
            if not schedule_exists:
                if execution.status in ('pending', 'queued', 'running'):
                    raise SafetyConflict('Cannot start an execution for a deleted schedule')
                count = conn.execute("""UPDATE JobExecutionsArchive SET status = ?, start_time = ?, end_time = ?,
                    duration_minutes = ?, retry_count = ?, error_message = ?, hamilton_command = ?
                    WHERE execution_id = ? AND status IN ('pending', 'queued', 'running')""", (*values, execution.execution_id)).rowcount
                conn.commit()
                return bool(count) or conn.execute('SELECT 1 FROM JobExecutionsArchive WHERE execution_id = ?', (execution.execution_id,)).fetchone() is not None
            conn.execute("""INSERT INTO JobExecutions (execution_id, schedule_id, status, start_time, end_time,
                duration_minutes, retry_count, error_message, hamilton_command) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET status = excluded.status, start_time = excluded.start_time,
                end_time = excluded.end_time, duration_minutes = excluded.duration_minutes, retry_count = excluded.retry_count,
                error_message = excluded.error_message, hamilton_command = excluded.hamilton_command
                WHERE JobExecutions.status IN ('pending', 'queued', 'running')""", (execution.execution_id, execution.schedule_id, *values))
            conn.commit()
            return True
    
    def import_experiment_methods(self, methods: List[Dict[str, Any]], imported_by: str) -> List[Dict[str, Any]]:
        """Write validated method metadata and report only committed per-file outcomes."""
        results = []
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing_paths = {}
                for stored in conn.execute("SELECT method_id, file_path, archived FROM ExperimentMethods").fetchall():
                    try:
                        path = Path(stored["file_path"])
                        if path.is_absolute():
                            existing_paths.setdefault(method_path_key(str(path)), []).append(dict(stored))
                    except (OSError, ValueError):
                        continue
                for method in methods:
                    outcome = {"path": method["path"], "status": "failed", "reason": None}
                    try:
                        key = method_path_key(method["path"])
                        existing = existing_paths.get(key, [])
                        existing = [row for row in existing if not row['archived']] or existing
                        if len(existing) > 1:
                            raise ValueError("Multiple catalogue entries resolve to this method; review the existing records.")
                        values = (method["name"], method.get("category", "Custom"),
                                  method.get("description", ""), method.get("file_size", 0),
                                  method.get("last_modified"), json.dumps(method.get("metadata", {})))
                        if existing:
                            conn.execute("""
                                UPDATE ExperimentMethods SET method_name = ?, category = ?, description = ?,
                                    file_size = ?, file_modified = ?, metadata = ?, is_valid = 1,
                                    revision = revision + 1, path_status = 'available',
                                    last_checked_at = ?, validation_reason = NULL
                                WHERE method_id = ?
                            """, (*values, datetime.now().isoformat(), existing[0]['method_id']))
                            outcome["status"] = "updated"
                        else:
                            method_id = str(uuid.uuid4())
                            conn.execute("""
                                INSERT INTO ExperimentMethods
                                    (method_name, category, description, file_size, file_modified, metadata,
                                     method_id, file_path, imported_by, source_folder, is_valid, path_status, last_checked_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'available', ?)
                            """, (*values, method_id, method["path"], imported_by, method.get("source_folder", ""), datetime.now().isoformat()))
                            existing_paths[key] = [{'method_id': method_id, 'archived': False}]
                            outcome["status"] = "added"
                    except Exception as exc:
                        if not conn.in_transaction:
                            # A trigger/driver may have rolled back earlier successful rows too.
                            raise
                        outcome["reason"] = f"Database write failed: {exc}"
                        logger.warning("Failed to import method %s: %s", method["path"], exc)
                    results.append(outcome)
                conn.commit()
        except Exception as exc:
            # A failed commit rolls back all rows; none may be reported as imported.
            logger.error("Method import transaction failed: %s", exc)
            return [{"path": method["path"], "status": "failed",
                     "reason": f"Database transaction failed: {exc}"} for method in methods]
        return results

    def get_method_references(self, path: str) -> List[Dict[str, Any]]:
        key = method_path_key(path)
        with self._get_connection() as conn:
            schedules = conn.execute('SELECT schedule_id, experiment_name, experiment_path, timeout_cleanup_experiment_path, is_active, archived, updated_at FROM ScheduledExperiments').fetchall()
            unfinished = {row[0] for row in conn.execute("SELECT DISTINCT schedule_id FROM JobExecutions WHERE status IN ('pending', 'queued', 'running')")}
        references = []
        for schedule in schedules:
            for field, role in (('experiment_path', 'primary'), ('timeout_cleanup_experiment_path', 'cleanup')):
                raw = schedule[field]
                if not raw:
                    continue
                try:
                    matches = method_path_key(raw) == key
                except (OSError, ValueError):
                    matches = raw == path
                if matches:
                    references.append({**dict(schedule), 'role': role, 'busy': schedule['schedule_id'] in unfinished})
        return references

    def apply_method_path_change(self, prepared: dict, expected_revision: int, selected: List[dict]):
        """Atomic catalogue/reference update. Caller holds scheduling locks; no filesystem work here."""
        method, target = prepared['method'], prepared['target']
        allowed = {(ref['schedule_id'], ref['role']): ref for ref in prepared['references']}
        with self._get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = [tuple(row) for row in conn.execute('SELECT method_id, file_path, revision FROM ExperimentMethods')]
            if set(current) != set(prepared['catalogue_snapshot']) or method['revision'] != expected_revision:
                raise ValueError('The method library changed. Preview the path correction again.')
            by_schedule = {}
            for reference in selected:
                pair = (reference['schedule_id'], reference['role'])
                if pair not in allowed:
                    raise ValueError('A selected schedule no longer references this method. Preview again.')
                by_schedule.setdefault(reference['schedule_id'], []).append(reference)
            updated_schedules = []
            now = utc_now_as_local_naive().isoformat()
            for schedule_id, references in by_schedule.items():
                row = conn.execute('SELECT * FROM ScheduledExperiments WHERE schedule_id = ?', (schedule_id,)).fetchone()
                if not row or row['archived']:
                    raise ValueError('A selected schedule is archived or no longer exists. Preview again.')
                pending = conn.execute("SELECT 1 FROM JobExecutions WHERE schedule_id = ? AND status IN ('pending', 'queued', 'running') LIMIT 1", (schedule_id,)).fetchone()
                if pending:
                    raise ValueError('A selected schedule is queued, running or paused. Wait for it to finish.')
                assignments, values = [], []
                for reference in references:
                    field = 'experiment_path' if reference['role'] == 'primary' else 'timeout_cleanup_experiment_path'
                    snapshot = allowed[(schedule_id, reference['role'])]
                    if row['updated_at'] != reference['expected_updated_at'] or row[field] != snapshot[field]:
                        raise ValueError('A selected schedule changed. Preview the path correction again.')
                    if field not in assignments:
                        assignments.append(field); values.append(target['path'])
                conn.execute('UPDATE ScheduledExperiments SET ' + ', '.join(f'{field} = ?' for field in assignments) + ', updated_at = ? WHERE schedule_id = ?',
                             (*values, now, schedule_id))
                saved = conn.execute('SELECT * FROM ScheduledExperiments WHERE schedule_id = ?', (schedule_id,)).fetchone()
                restored = self._row_to_scheduled_experiment(saved, conn)
                if restored is None:
                    raise ValueError('Could not reload the selected schedule. No changes were saved.')
                updated_schedules.append(restored)
            conn.execute('''UPDATE ExperimentMethods SET file_path = ?, method_name = ?, file_size = ?, file_modified = ?,
                            path_status = 'available', is_valid = 1, validation_reason = NULL, last_checked_at = ?, revision = revision + 1
                            WHERE method_id = ?''',
                         (target['path'], target['method_name'], target['file_size'], target['file_modified'], target['last_checked_at'], method['method_id']))
            conn.commit()
        return updated_schedules

    def set_method_archived(self, method_id: str, archived: bool, expected_revision: int):
        with self._get_connection() as conn:
            changed = conn.execute('UPDATE ExperimentMethods SET archived = ?, revision = revision + 1 WHERE method_id = ? AND revision = ?',
                                   (int(archived), method_id, expected_revision)).rowcount
            if not changed:
                raise ValueError('Method changed or was removed. Refresh the library and review it again.')
            conn.commit()

    def save_method_validation(self, method_id: str, expected_revision: int, result: dict):
        with self._get_connection() as conn:
            changed = conn.execute('''UPDATE ExperimentMethods SET path_status = ?, last_checked_at = ?, validation_reason = ?,
                                     is_valid = ?, revision = revision + 1 WHERE method_id = ? AND revision = ?''',
                                   (result['path_status'], result['last_checked_at'], result['validation_reason'],
                                    int(result['path_status'] == 'available'), method_id, expected_revision)).rowcount
            if not changed:
                raise ValueError('Method changed during validation. Check its path again.')
            conn.commit()

    def get_experiment_methods(self, category: Optional[str] = None, valid_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get experiment methods from the database
        
        Args:
            category: Optional category filter
            valid_only: Only return valid methods
            
        Returns:
            List of method dictionaries
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM ExperimentMethods WHERE 1=1"
                params = []
                
                if valid_only:
                    query += " AND is_valid = 1 AND archived = 0"
                    
                if category:
                    query += " AND category = ?"
                    params.append(category)
                    
                query += " ORDER BY category, method_name"
                
                cursor.execute(query, params)
                columns = [col[0] for col in cursor.description]
                
                methods = []
                for row in cursor.fetchall():
                    method = dict(zip(columns, row))
                    # Parse JSON metadata
                    if method.get('metadata'):
                        try:
                            method['metadata'] = json.loads(method['metadata'])
                        except:
                            method['metadata'] = {}
                    methods.append(method)
                    
                return methods
                
        except Exception as e:
            logger.error(f"Failed to get experiment methods: {e}")
            return []
    
    def update_method_usage(self, file_path: str):
        """
        Update usage statistics when a method is used
        
        Args:
            file_path: Path to the method file
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE ExperimentMethods
                    SET use_count = use_count + 1,
                        last_used = CURRENT_TIMESTAMP
                    WHERE file_path = ?
                """, (file_path,))
                
                conn.commit()
                
        except Exception as e:
            logger.warning(f"Failed to update method usage: {e}")
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get database status information
        
        Returns:
            Dictionary with database info
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get table counts
                cursor.execute("SELECT COUNT(*) FROM ScheduledExperiments")
                schedule_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM JobExecutions")
                execution_count = cursor.fetchone()[0]
                
                # Get database file size
                db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
                db_size_mb = db_size_bytes / (1024 * 1024)
                
                return {
                    "database_path": str(self.db_path),
                    "database_exists": self.db_path.exists(),
                    "schema_initialized": self._schema_initialized,
                    "database_size_mb": round(db_size_mb, 2),
                    "scheduled_experiments": schedule_count,
                    "job_executions": execution_count
                }
                
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {"error": str(e)}
    
    def _get_schedule_contact_ids(self, schedule_id: str, conn: Optional[sqlite3.Connection] = None) -> List[str]:
        if not schedule_id:
            return []
        if conn is None:
            with self._get_connection() as temp_conn:
                return self._get_schedule_contact_ids(schedule_id, temp_conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT contact_id FROM ScheduleNotificationContacts WHERE schedule_id = ?",
            (schedule_id,)
        )
        rows = cursor.fetchall()
        return [row["contact_id"] for row in rows]

    def _replace_schedule_contacts(self, conn: sqlite3.Connection, schedule_id: str, contact_ids: List[str]) -> None:
        cursor = conn.cursor()
        for contact_id in set(contact_ids):
            if not conn.execute('SELECT 1 FROM NotificationContacts WHERE contact_id = ?', (contact_id,)).fetchone():
                raise SafetyConflict('A selected notification contact was deleted. Refresh the schedule and review its contacts.')
        cursor.execute("DELETE FROM ScheduleNotificationContacts WHERE schedule_id = ?", (schedule_id,))
        if contact_ids:
            timestamp = datetime.now().isoformat()
            cursor.executemany(
                "INSERT OR IGNORE INTO ScheduleNotificationContacts (schedule_id, contact_id, added_at) VALUES (?, ?, ?)",
                [(schedule_id, contact_id, timestamp) for contact_id in contact_ids]
            )

    def _row_to_scheduled_experiment(self, row: sqlite3.Row, conn: Optional[sqlite3.Connection] = None) -> Optional[ScheduledExperiment]:
        """Convert database row to ScheduledExperiment object"""
        try:
            start_time = self._parse_timestamp(row["start_time"])
            row_keys = set(row.keys()) if hasattr(row, "keys") else set()
            created_at = self._parse_timestamp(row["created_at"]) if "created_at" in row_keys else None
            updated_at = self._parse_timestamp(row["updated_at"]) if "updated_at" in row_keys else None

            timeout_config = TimeoutConfig()
            raw_timeout_minutes = row["timeout_minutes"] if "timeout_minutes" in row_keys else None
            raw_timeout_action = row["timeout_action"] if "timeout_action" in row_keys else "continue"
            raw_cleanup_name = (
                row["timeout_cleanup_experiment_name"]
                if "timeout_cleanup_experiment_name" in row_keys
                else None
            )
            raw_cleanup_path = (
                row["timeout_cleanup_experiment_path"]
                if "timeout_cleanup_experiment_path" in row_keys
                else None
            )
            timeout_config = TimeoutConfig.from_dict(
                {
                    "timeout_minutes": raw_timeout_minutes,
                    "action": raw_timeout_action,
                    "cleanup_experiment_name": raw_cleanup_name,
                    "cleanup_experiment_path": raw_cleanup_path,
                }
            )

            prerequisites: List[str] = []
            raw_prereqs = row["prerequisites"] if "prerequisites" in row_keys else None
            if raw_prereqs:
                try:
                    prerequisites = json.loads(raw_prereqs)
                except Exception as exc:  # pragma: no cover
                    logger.debug("Failed to parse prerequisites: %s", exc)

            recovery_marked_at = self._parse_timestamp(row["recovery_marked_at"]) if "recovery_marked_at" in row_keys else None
            recovery_resolved_at = self._parse_timestamp(row["recovery_resolved_at"]) if "recovery_resolved_at" in row_keys else None

            schedule = ScheduledExperiment(
                schedule_id=row["schedule_id"],
                experiment_name=row["experiment_name"],
                experiment_path=row["experiment_path"],
                schedule_type=row["schedule_type"],
                interval_hours=row["interval_hours"],
                start_time=start_time,
                estimated_duration=row["estimated_duration"],
                log_inactivity_threshold_minutes=row["log_inactivity_threshold_minutes"],
                created_by=row["created_by"],
                is_active=bool(row["is_active"]),
                archived=bool(row["archived"]) if "archived" in row_keys else False,
                timeout_config=timeout_config,
                prerequisites=prerequisites,
                notification_contacts=[],
                recovery_required=bool(row["recovery_required"]) if "recovery_required" in row_keys else False,
                recovery_note=row["recovery_note"] if "recovery_note" in row_keys else None,
                recovery_marked_at=recovery_marked_at,
                recovery_marked_by=row["recovery_marked_by"] if "recovery_marked_by" in row_keys else None,
                recovery_resolved_at=recovery_resolved_at,
                recovery_resolved_by=row["recovery_resolved_by"] if "recovery_resolved_by" in row_keys else None,
                created_at=created_at,
                updated_at=updated_at,
            )

            schedule.notification_contacts = self._get_schedule_contact_ids(
                schedule.schedule_id,
                conn,
            )

            return schedule

        except Exception as exc:
            logger.error("Failed to convert row to ScheduledExperiment: %s", exc)
            raise StorageUnavailable('A stored schedule could not be read. Review SQLite storage health.') from exc

    def _row_to_notification_log(self, row: sqlite3.Row) -> NotificationLogEntry:
        """Convert database row to NotificationLogEntry."""
        try:
            recipients = json.loads(row["recipients"]) if row["recipients"] else []
            attachments = json.loads(row["attachments"]) if row["attachments"] else []
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        except Exception as exc:
            logger.debug("Failed to parse notification log json payloads: %s", exc)
            recipients = []
            attachments = []
            metadata = {}

        return NotificationLogEntry(
            log_id=row["log_id"],
            schedule_id=row["schedule_id"],
            execution_id=row["execution_id"],
            event_type=row["event_type"],
            status=row["status"],
            subject=row["subject"],
            message=row["message"],
            recipients=recipients,
            attachments=attachments,
            error_message=row["error_message"],
            triggered_at=parse_iso_datetime_to_local(row["triggered_at"]),
            processed_at=parse_iso_datetime_to_local(row["processed_at"]),
            metadata=metadata,
        )


    def get_execution_history(self, schedule_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get execution history for a specific schedule or all schedules
        
        Args:
            schedule_id: Optional schedule ID filter
            limit: Maximum number of results to return
            
        Returns:
            List of execution history dictionaries
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                where_clause = ""
                params: List[Any] = []
                if schedule_id:
                    where_clause = "WHERE je.schedule_id = ?"
                    params.append(schedule_id)

                cursor.execute(
                    f"""
                    SELECT
                        je.execution_id,
                        je.schedule_id,
                        je.status,
                        je.start_time,
                        je.end_time,
                        je.duration_minutes,
                        je.retry_count,
                        je.error_message,
                        je.hamilton_command,
                        je.created_at,
                        se.experiment_name AS experiment_name,
                        se.experiment_path AS experiment_path,
                        NULL AS experiment_name_snapshot,
                        NULL AS experiment_path_snapshot,
                        NULL AS archived_at
                    FROM JobExecutions je
                    LEFT JOIN ScheduledExperiments se ON je.schedule_id = se.schedule_id
                    {where_clause}
                    """,
                    params,
                )
                current_rows = [dict(row) for row in cursor.fetchall()]

                archive_where = "WHERE schedule_id = ?" if schedule_id else ""
                archive_params = [schedule_id] if schedule_id else []

                cursor.execute(
                    f"""
                    SELECT
                        execution_id,
                        schedule_id,
                        status,
                        start_time,
                        end_time,
                        duration_minutes,
                        retry_count,
                        error_message,
                        hamilton_command,
                        created_at,
                        experiment_name_snapshot AS experiment_name,
                        experiment_path_snapshot AS experiment_path,
                        experiment_name_snapshot,
                        experiment_path_snapshot,
                        archived_at
                    FROM JobExecutionsArchive
                    {archive_where}
                    """,
                    archive_params,
                )
                archived_rows = [dict(row) for row in cursor.fetchall()]

                def select_preferred(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
                    existing_archived = bool(existing.get("archived_at"))
                    candidate_archived = bool(candidate.get("archived_at"))
                    if candidate_archived and not existing_archived:
                        return candidate
                    if existing_archived and not candidate_archived:
                        return existing

                    existing_snapshot = bool(existing.get("experiment_name_snapshot"))
                    candidate_snapshot = bool(candidate.get("experiment_name_snapshot"))
                    if candidate_snapshot and not existing_snapshot:
                        return candidate
                    if existing_snapshot and not candidate_snapshot:
                        return existing

                    existing_name = (existing.get("experiment_name") or "").strip()
                    candidate_name = (candidate.get("experiment_name") or "").strip()
                    if candidate_name and not existing_name:
                        return candidate
                    if existing_name and not candidate_name:
                        return existing

                    return candidate

                merged: Dict[str, Dict[str, Any]] = {}
                for row in current_rows + archived_rows:
                    execution_id = row.get("execution_id")
                    if not execution_id:
                        continue
                    if execution_id in merged:
                        merged[execution_id] = select_preferred(merged[execution_id], row)
                    else:
                        merged[execution_id] = row

                executions = list(merged.values())
                executions.sort(key=lambda item: item.get("created_at") or "", reverse=True)

                if limit and len(executions) > limit:
                    executions = executions[:limit]

                for execution in executions:
                    if execution.get("start_time") and execution.get("end_time"):
                        try:
                            start = parse_iso_datetime_to_local(execution["start_time"])
                            end = parse_iso_datetime_to_local(execution["end_time"])
                            if start and end:
                                execution["calculated_duration_minutes"] = int((end - start).total_seconds() / 60)
                            else:
                                execution["calculated_duration_minutes"] = execution.get("duration_minutes")
                        except Exception:
                            execution["calculated_duration_minutes"] = execution.get("duration_minutes")
                    else:
                        execution["calculated_duration_minutes"] = execution.get("duration_minutes")

                    snapshot_name = execution.get("experiment_name_snapshot")
                    if snapshot_name:
                        execution["experiment_name"] = snapshot_name
                    elif not execution.get("experiment_name"):
                        execution["experiment_name"] = "Archived Schedule"

                    execution["status_display"] = self._format_execution_status(execution["status"])
                
                return executions
                
        except Exception as e:
            logger.error(f"Failed to get execution history: {e}")
            return []
    
    def get_schedule_execution_summary(self, schedule_id: str) -> Dict[str, Any]:
        """
        Get execution summary for a specific schedule (like Windows Task Scheduler)
        
        Args:
            schedule_id: Schedule ID to get summary for
            
        Returns:
            Dictionary with execution summary statistics
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    """
                    SELECT experiment_name, experiment_path, created_at, is_active
                    FROM ScheduledExperiments 
                    WHERE schedule_id = ?
                    """,
                    (schedule_id,),
                )

                schedule_info_row = cursor.fetchone()
                if schedule_info_row:
                    schedule_info = dict(schedule_info_row)
                else:
                    cursor.execute(
                        """
                        SELECT 
                            experiment_name_snapshot AS experiment_name,
                            experiment_path_snapshot AS experiment_path,
                            MIN(created_at) AS created_at
                        FROM JobExecutionsArchive
                        WHERE schedule_id = ?
                        """,
                        (schedule_id,),
                    )
                    archive_info = cursor.fetchone()
                    if archive_info:
                        schedule_info = dict(archive_info)
                        schedule_info.setdefault("is_active", 0)
                    else:
                        schedule_info = {
                            "experiment_name": "Archived Schedule",
                            "experiment_path": None,
                            "created_at": None,
                            "is_active": 0,
                        }

                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                        MAX(start_time) as last_run_time,
                        MAX(CASE WHEN status = 'completed' THEN start_time END) as last_successful_run,
                        AVG(CASE WHEN duration_minutes IS NOT NULL THEN duration_minutes END) as avg_duration,
                        MIN(start_time) as first_run_time
                    FROM (
                        SELECT status, start_time, duration_minutes
                        FROM JobExecutions WHERE schedule_id = ?
                        UNION ALL
                        SELECT status, start_time, duration_minutes
                        FROM JobExecutionsArchive WHERE schedule_id = ?
                    )
                    """,
                    (schedule_id, schedule_id),
                )

                stats_row = cursor.fetchone()
                stats = (
                    dict(stats_row)
                    if stats_row
                    else {
                        "total_runs": 0,
                        "successful_runs": 0,
                        "failed_runs": 0,
                        "last_run_time": None,
                        "last_successful_run": None,
                        "avg_duration": None,
                        "first_run_time": None,
                    }
                )

                cursor.execute(
                    """
                    SELECT status, start_time, end_time, error_message, retry_count
                    FROM (
                        SELECT status, start_time, end_time, error_message, retry_count, created_at
                        FROM JobExecutions WHERE schedule_id = ?
                        UNION ALL
                        SELECT status, start_time, end_time, error_message, retry_count, created_at
                        FROM JobExecutionsArchive WHERE schedule_id = ?
                    )
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (schedule_id, schedule_id),
                )

                last_execution_row = cursor.fetchone()
                last_execution = dict(last_execution_row) if last_execution_row else {}

                cursor.execute(
                    """
                    SELECT start_time, schedule_type, interval_hours
                    FROM ScheduledExperiments 
                    WHERE schedule_id = ? AND is_active = 1
                    """,
                    (schedule_id,),
                )

                next_run_row = cursor.fetchone()
                next_run_info = dict(next_run_row) if next_run_row else {}

                total_runs = stats.get("total_runs") or 0
                successful_runs = stats.get("successful_runs") or 0

                return {
                    **schedule_info,
                    **stats,
                    'last_execution': last_execution,
                    'next_run_time': next_run_info.get('start_time'),
                    'schedule_type': next_run_info.get('schedule_type'),
                    'interval_hours': next_run_info.get('interval_hours'),
                    'success_rate': round((successful_runs / total_runs) * 100, 1) if total_runs > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"Failed to get schedule execution summary: {e}")
            return {}
    
    def get_recent_executions(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get recent executions within the specified time period
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of recent execution dictionaries
        """
        try:
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT je.*, se.experiment_name, se.experiment_path
                    FROM JobExecutions je
                    JOIN ScheduledExperiments se ON je.schedule_id = se.schedule_id
                    WHERE je.created_at >= ?
                    ORDER BY je.created_at DESC
                """, (cutoff_time,))
                
                columns = [col[0] for col in cursor.description]
                
                executions = []
                for row in cursor.fetchall():
                    execution = dict(zip(columns, row))
                    execution['status_display'] = self._format_execution_status(execution['status'])
                    executions.append(execution)
                
                return executions
                
        except Exception as e:
            logger.error(f"Failed to get recent executions: {e}")
            return []
    
    def _format_execution_status(self, status: str) -> str:
        """Format execution status for display"""
        status_map = {
            'pending': 'Ready',
            'queued': 'Queued',
            'running': 'Running',
            'completed': 'Success',
            'failed': 'Failed',
            'blocked': 'Blocked',
            'cancelled': 'Cancelled'
        }
        return status_map.get(status, status.title())


# Singleton instance management
_sqlite_db_instance = None
_sqlite_db_lock = threading.Lock()


def get_sqlite_scheduling_database() -> SQLiteSchedulingDatabase:
    """
    Get the singleton SQLite scheduling database instance
    
    Returns:
        SQLiteSchedulingDatabase: The database instance
    """
    global _sqlite_db_instance
    
    with _sqlite_db_lock:
        if _sqlite_db_instance is None:
            _sqlite_db_instance = SQLiteSchedulingDatabase()
            
    return _sqlite_db_instance
