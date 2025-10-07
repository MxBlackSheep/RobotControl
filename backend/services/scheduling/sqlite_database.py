"""
SQLite Database Manager for Scheduling System

Provides a lightweight SQLite-based database for scheduling data that:
- Auto-creates in the data directory
- Works in both development and compiled modes
- Stores scheduling metadata separately from Hamilton's read-only database
- Can be extended for user management and other PyRobot-specific data
"""

import sqlite3
import logging
import threading
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager
from backend.utils.data_paths import get_data_path
from backend.models import ScheduledExperiment, JobExecution, RetryConfig, ManualRecoveryState

logger = logging.getLogger(__name__)


class SQLiteSchedulingDatabase:
    """SQLite database manager for scheduling system"""
    
    def __init__(self, db_name: str = "pyrobot_scheduling.db"):
        """
        Initialize SQLite database for scheduling
        
        Args:
            db_name: Name of the SQLite database file
        """
        self.db_path = get_data_path() / db_name
        self._connection_lock = threading.RLock()
        self._schema_initialized = False
        
        logger.info(f"SQLite scheduling database: {self.db_path}")
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database schema"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
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
                        retry_config TEXT,
                        prerequisites TEXT,
                        failed_execution_count INTEGER NOT NULL DEFAULT 0,
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
                        recovery_resolved_at TEXT
                    )
                """)
                cursor.execute("INSERT OR IGNORE INTO SchedulerState (id) VALUES (1)")

                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_start_time ON ScheduledExperiments(start_time)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_active ON ScheduledExperiments(is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON JobExecutions(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_schedule_id ON JobExecutions(schedule_id)")
                
                conn.commit()

                existing_columns = {col['name'] for col in cursor.execute("PRAGMA table_info(ScheduledExperiments)")}
                column_alterations = [
                    ('recovery_required', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_required INTEGER NOT NULL DEFAULT 0"),
                    ('recovery_note', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_note TEXT"),
                    ('recovery_marked_at', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_marked_at TEXT"),
                    ('recovery_marked_by', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_marked_by TEXT"),
                    ('recovery_resolved_at', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_resolved_at TEXT"),
                    ('recovery_resolved_by', "ALTER TABLE ScheduledExperiments ADD COLUMN recovery_resolved_by TEXT")
                ]
                for column_name, alter_sql in column_alterations:
                    if column_name not in existing_columns:
                        try:
                            cursor.execute(alter_sql)
                            logger.info("SQLite scheduling database: added column %s", column_name)
                        except Exception as alter_exc:
                            logger.warning("SQLite scheduling database: unable to add column %s (%s)", column_name, alter_exc)

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_recovery_required ON ScheduledExperiments(recovery_required)")

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
        """Get a thread-safe database connection"""
        with self._connection_lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            try:
                yield conn
            finally:
                conn.close()
    

    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        value_str = str(value).replace('Z', '').replace('+00:00', '')
        try:
            return datetime.fromisoformat(value_str)
        except ValueError:
            return None

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
                        is_active, retry_config, prerequisites, failed_execution_count,
                        recovery_required, recovery_note, recovery_marked_at, recovery_marked_by,
                        recovery_resolved_at, recovery_resolved_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    schedule.schedule_id,
                    schedule.experiment_name,
                    schedule.experiment_path,
                    schedule.schedule_type,
                    schedule.interval_hours,
                    schedule.start_time.isoformat() if schedule.start_time else None,
                    schedule.estimated_duration,
                    schedule.created_by,
                    1 if schedule.is_active else 0,
                    json.dumps(schedule.retry_config.to_dict()) if schedule.retry_config else None,
                    json.dumps(schedule.prerequisites) if schedule.prerequisites else None,
                    schedule.failed_execution_count,
                    1 if schedule.recovery_required else 0,
                    schedule.recovery_note,
                    schedule.recovery_marked_at.isoformat() if schedule.recovery_marked_at else None,
                    schedule.recovery_marked_by,
                    schedule.recovery_resolved_at.isoformat() if schedule.recovery_resolved_at else None,
                    schedule.recovery_resolved_by
                ))
                
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
                    WHERE is_active = 1 
                    ORDER BY start_time ASC
                """)
                
                rows = cursor.fetchall()
                
                for row in rows:
                    schedule = self._row_to_scheduled_experiment(row)
                    if schedule:
                        schedules.append(schedule)
                        
        except Exception as e:
            logger.error(f"Failed to get active schedules from SQLite: {e}")
        
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
                    return self._row_to_scheduled_experiment(row)
                    
        except Exception as e:
            logger.error(f"Failed to get schedule {schedule_id} from SQLite: {e}")
        
        return None
    
    def update_schedule(self, schedule: ScheduledExperiment) -> bool:
        """
        Update an existing scheduled experiment
        
        Args:
            schedule: Updated ScheduledExperiment
            
        Returns:
            bool: True if updated successfully
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE ScheduledExperiments SET
                        experiment_name = ?, experiment_path = ?, schedule_type = ?,
                        interval_hours = ?, start_time = ?, estimated_duration = ?,
                        is_active = ?, retry_config = ?, prerequisites = ?,
                        failed_execution_count = ?,
                        recovery_required = ?, recovery_note = ?,
                        recovery_marked_at = ?, recovery_marked_by = ?,
                        recovery_resolved_at = ?, recovery_resolved_by = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE schedule_id = ?
                """, (
                    schedule.experiment_name,
                    schedule.experiment_path,
                    schedule.schedule_type,
                    schedule.interval_hours,
                    schedule.start_time.isoformat() if schedule.start_time else None,
                    schedule.estimated_duration,
                    1 if schedule.is_active else 0,
                    json.dumps(schedule.retry_config.to_dict()) if schedule.retry_config else None,
                    json.dumps(schedule.prerequisites) if schedule.prerequisites else None,
                    schedule.failed_execution_count,
                    1 if schedule.recovery_required else 0,
                    schedule.recovery_note,
                    schedule.recovery_marked_at.isoformat() if schedule.recovery_marked_at else None,
                    schedule.recovery_marked_by,
                    schedule.recovery_resolved_at.isoformat() if schedule.recovery_resolved_at else None,
                    schedule.recovery_resolved_by,
                    schedule.schedule_id
                ))
                
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Updated schedule in SQLite: {schedule.experiment_name}")
                    return True
                else:
                    logger.warning(f"No schedule found to update: {schedule.schedule_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to update schedule in SQLite: {e}")
            return False
    
    def set_recovery_required(
        self, schedule_id: str, note: Optional[str], user: str
    ) -> bool:
        """Mark a schedule as requiring manual recovery."""
        timestamp = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ScheduledExperiments SET
                        recovery_required = 1,
                        recovery_note = COALESCE(?, recovery_note),
                        recovery_marked_at = ?,
                        recovery_marked_by = ?,
                        recovery_resolved_at = NULL,
                        recovery_resolved_by = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE schedule_id = ?
                """, (note, timestamp, user, schedule_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to mark schedule {schedule_id} for recovery: {exc}")
            return False

    def resolve_recovery_required(
        self, schedule_id: str, note: Optional[str], user: str
    ) -> bool:
        """Clear the manual recovery requirement for a schedule."""
        timestamp = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ScheduledExperiments SET
                        recovery_required = 0,
                        recovery_note = COALESCE(?, recovery_note),
                        recovery_resolved_at = ?,
                        recovery_resolved_by = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE schedule_id = ?
                """, (note, timestamp, user, schedule_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to resolve recovery for schedule {schedule_id}: {exc}")
            return False



    def get_manual_recovery_state(self) -> ManualRecoveryState:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT recovery_required, recovery_note, recovery_schedule_id, "
                    "recovery_experiment_name, recovery_triggered_by, recovery_triggered_at, "
                    "recovery_resolved_by, recovery_resolved_at FROM SchedulerState WHERE id = 1"
                )
                row = cursor.fetchone()
        except Exception as exc:
            logger.error(f"Failed to load manual recovery state: {exc}")
            row = None

        if not row:
            return ManualRecoveryState()

        return ManualRecoveryState(
            active=bool(row["recovery_required"]),
            note=row["recovery_note"],
            schedule_id=row["recovery_schedule_id"],
            experiment_name=row["recovery_experiment_name"],
            triggered_by=row["recovery_triggered_by"],
            triggered_at=self._parse_timestamp(row["recovery_triggered_at"]),
            resolved_by=row["recovery_resolved_by"],
            resolved_at=self._parse_timestamp(row["recovery_resolved_at"]),
        )

    def set_global_recovery_required(
        self,
        schedule: Optional[ScheduledExperiment],
        note: Optional[str],
        user: str,
    ) -> ManualRecoveryState:
        timestamp = datetime.now().isoformat()
        schedule_id = schedule.schedule_id if schedule else None
        experiment_name = schedule.experiment_name if schedule else None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE SchedulerState SET
                        recovery_required = 1,
                        recovery_note = COALESCE(?, recovery_note),
                        recovery_schedule_id = ?,
                        recovery_experiment_name = ?,
                        recovery_triggered_by = ?,
                        recovery_triggered_at = ?,
                        recovery_resolved_by = NULL,
                        recovery_resolved_at = NULL
                    WHERE id = 1
                    """,
                    (note, schedule_id, experiment_name, user, timestamp),
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"Failed to update scheduler recovery state: {exc}")

        return self.get_manual_recovery_state()

    def clear_global_recovery(
        self,
        note: Optional[str],
        user: str,
    ) -> ManualRecoveryState:
        timestamp = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE SchedulerState SET
                        recovery_required = 0,
                        recovery_note = COALESCE(?, recovery_note),
                        recovery_resolved_by = ?,
                        recovery_resolved_at = ?
                    WHERE id = 1
                    """,
                    (note, user, timestamp),
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"Failed to clear scheduler recovery state: {exc}")

        return self.get_manual_recovery_state()

    def delete_schedule(self, schedule_id: str) -> bool:
        """
        Delete a scheduled experiment
        
        Args:
            schedule_id: Schedule identifier to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete related job executions first (CASCADE should handle this, but being explicit)
                cursor.execute("DELETE FROM JobExecutions WHERE schedule_id = ?", (schedule_id,))
                
                # Delete the schedule
                cursor.execute("DELETE FROM ScheduledExperiments WHERE schedule_id = ?", (schedule_id,))
                
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Deleted schedule from SQLite: {schedule_id}")
                    return True
                else:
                    logger.warning(f"No schedule found to delete: {schedule_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to delete schedule from SQLite: {e}")
            return False
    
    def create_job_execution(self, execution: JobExecution) -> bool:
        """
        Create a job execution record
        
        Args:
            execution: JobExecution to create
            
        Returns:
            bool: True if created successfully
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO JobExecutions (
                        execution_id, schedule_id, status, start_time, end_time,
                        duration_minutes, retry_count, error_message, hamilton_command
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    execution.execution_id,
                    execution.schedule_id,
                    execution.status,
                    execution.start_time.isoformat() if execution.start_time else None,
                    execution.end_time.isoformat() if execution.end_time else None,
                    execution.duration_minutes,
                    execution.retry_count,
                    execution.error_message,
                    execution.hamilton_command
                ))
                
                conn.commit()
                logger.info(f"Created job execution in SQLite: {execution.execution_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create job execution in SQLite: {e}")
            return False
    
    def import_experiment_methods(self, methods: List[Dict[str, Any]], imported_by: str) -> Tuple[int, int]:
        """
        Import discovered experiment methods into the database
        
        Args:
            methods: List of method dictionaries with file info
            imported_by: Username of who imported the methods
            
        Returns:
            Tuple of (new_methods_count, updated_methods_count)
        """
        new_count = 0
        updated_count = 0
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                for method in methods:
                    try:
                        # Check if method already exists
                        cursor.execute(
                            "SELECT method_id FROM ExperimentMethods WHERE file_path = ?",
                            (method['path'],)
                        )
                        existing = cursor.fetchone()
                        
                        if existing:
                            # Update existing method
                            cursor.execute("""
                                UPDATE ExperimentMethods
                                SET method_name = ?, category = ?, description = ?,
                                    file_size = ?, file_modified = ?, is_valid = 1,
                                    metadata = ?
                                WHERE file_path = ?
                            """, (
                                method.get('name'),
                                method.get('category', 'Custom'),
                                method.get('description', ''),
                                method.get('file_size', 0),
                                method.get('last_modified'),
                                json.dumps(method.get('metadata', {})),
                                method['path']
                            ))
                            updated_count += 1
                        else:
                            # Insert new method
                            import uuid
                            method_id = str(uuid.uuid4())
                            
                            cursor.execute("""
                                INSERT INTO ExperimentMethods
                                (method_id, method_name, file_path, category, description,
                                 file_size, file_modified, imported_by, source_folder,
                                 is_valid, metadata)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                method_id,
                                method.get('name'),
                                method['path'],
                                method.get('category', 'Custom'),
                                method.get('description', ''),
                                method.get('file_size', 0),
                                method.get('last_modified'),
                                imported_by,
                                method.get('source_folder', ''),
                                1,
                                json.dumps(method.get('metadata', {}))
                            ))
                            new_count += 1
                            
                    except Exception as e:
                        logger.warning(f"Failed to import method {method.get('name')}: {e}")
                        continue
                
                conn.commit()
                logger.info(f"Imported {new_count} new methods, updated {updated_count} existing methods")
                
        except Exception as e:
            logger.error(f"Failed to import experiment methods: {e}")
            
        return new_count, updated_count
    
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
                    query += " AND is_valid = 1"
                    
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
    
    def _row_to_scheduled_experiment(self, row: sqlite3.Row) -> Optional[ScheduledExperiment]:
        """Convert database row to ScheduledExperiment object"""
        try:
            # Parse datetime (ensure timezone-naive)
            start_time = None
            if row['start_time']:
                # Remove timezone info to ensure naive datetime for consistent comparison
                start_time_str = row['start_time'].replace('Z', '').replace('+00:00', '')
                start_time = datetime.fromisoformat(start_time_str)
            
            # Parse retry config
            retry_config = None
            if row['retry_config']:
                retry_config = RetryConfig.from_dict(json.loads(row['retry_config']))

            # Parse prerequisites
            prerequisites = []
            if row['prerequisites']:
                prerequisites = json.loads(row['prerequisites'])

            recovery_marked_at = None
            if 'recovery_marked_at' in row.keys() and row['recovery_marked_at']:
                marked_str = row['recovery_marked_at'].replace('Z', '').replace('+00:00', '')
                recovery_marked_at = datetime.fromisoformat(marked_str)

            recovery_resolved_at = None
            if 'recovery_resolved_at' in row.keys() and row['recovery_resolved_at']:
                resolved_str = row['recovery_resolved_at'].replace('Z', '').replace('+00:00', '')
                recovery_resolved_at = datetime.fromisoformat(resolved_str)

            return ScheduledExperiment(
                schedule_id=row['schedule_id'],
                experiment_name=row['experiment_name'],
                experiment_path=row['experiment_path'],
                schedule_type=row['schedule_type'],
                interval_hours=row['interval_hours'],
                start_time=start_time,
                estimated_duration=row['estimated_duration'],
                created_by=row['created_by'],
                is_active=bool(row['is_active']),
                retry_config=retry_config,
                prerequisites=prerequisites,
                failed_execution_count=row['failed_execution_count'] if 'failed_execution_count' in row.keys() else 0,
                recovery_required=bool(row['recovery_required']) if 'recovery_required' in row.keys() else False,
                recovery_note=row['recovery_note'] if 'recovery_note' in row.keys() else None,
                recovery_marked_at=recovery_marked_at,
                recovery_marked_by=row['recovery_marked_by'] if 'recovery_marked_by' in row.keys() else None,
                recovery_resolved_at=recovery_resolved_at,
                recovery_resolved_by=row['recovery_resolved_by'] if 'recovery_resolved_by' in row.keys() else None
            )

        except Exception as e:
            logger.error(f"Failed to convert row to ScheduledExperiment: {e}")
            return None


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
                
                if schedule_id:
                    cursor.execute("""
                        SELECT je.*, se.experiment_name, se.experiment_path
                        FROM JobExecutions je
                        JOIN ScheduledExperiments se ON je.schedule_id = se.schedule_id
                        WHERE je.schedule_id = ?
                        ORDER BY je.created_at DESC
                        LIMIT ?
                    """, (schedule_id, limit))
                else:
                    cursor.execute("""
                        SELECT je.*, se.experiment_name, se.experiment_path
                        FROM JobExecutions je
                        JOIN ScheduledExperiments se ON je.schedule_id = se.schedule_id
                        ORDER BY je.created_at DESC
                        LIMIT ?
                    """, (limit,))
                
                columns = [col[0] for col in cursor.description]
                
                executions = []
                for row in cursor.fetchall():
                    execution = dict(zip(columns, row))
                    
                    # Calculate duration if end_time exists
                    if execution.get('start_time') and execution.get('end_time'):
                        try:
                            start = datetime.fromisoformat(execution['start_time'])
                            end = datetime.fromisoformat(execution['end_time'])
                            execution['calculated_duration_minutes'] = int((end - start).total_seconds() / 60)
                        except:
                            execution['calculated_duration_minutes'] = execution.get('duration_minutes')
                    
                    # Add status information
                    execution['status_display'] = self._format_execution_status(execution['status'])
                    
                    executions.append(execution)
                
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
                
                # Get basic schedule info
                cursor.execute("""
                    SELECT experiment_name, experiment_path, created_at, is_active
                    FROM ScheduledExperiments 
                    WHERE schedule_id = ?
                """, (schedule_id,))
                
                schedule_row = cursor.fetchone()
                if not schedule_row:
                    return {}
                
                schedule_info = dict(schedule_row)
                
                # Get execution statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                        MAX(start_time) as last_run_time,
                        MAX(CASE WHEN status = 'completed' THEN start_time END) as last_successful_run,
                        AVG(CASE WHEN duration_minutes IS NOT NULL THEN duration_minutes END) as avg_duration,
                        MIN(start_time) as first_run_time
                    FROM JobExecutions 
                    WHERE schedule_id = ?
                """, (schedule_id,))
                
                stats_row = cursor.fetchone()
                stats = dict(stats_row) if stats_row else {}
                
                # Get last execution details
                cursor.execute("""
                    SELECT status, start_time, end_time, error_message, retry_count
                    FROM JobExecutions 
                    WHERE schedule_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (schedule_id,))
                
                last_execution_row = cursor.fetchone()
                last_execution = dict(last_execution_row) if last_execution_row else {}
                
                # Get next run time from schedule
                cursor.execute("""
                    SELECT start_time, schedule_type, interval_hours
                    FROM ScheduledExperiments 
                    WHERE schedule_id = ? AND is_active = 1
                """, (schedule_id,))
                
                next_run_row = cursor.fetchone()
                next_run_info = dict(next_run_row) if next_run_row else {}
                
                return {
                    **schedule_info,
                    **stats,
                    'last_execution': last_execution,
                    'next_run_time': next_run_info.get('start_time'),
                    'schedule_type': next_run_info.get('schedule_type'),
                    'interval_hours': next_run_info.get('interval_hours'),
                    'success_rate': round((stats.get('successful_runs', 0) / stats.get('total_runs', 1)) * 100, 1) if stats.get('total_runs', 0) > 0 else 0
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
            'missed': 'Missed',
            'retrying': 'Retrying',
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
