"""
Scheduling Database Management Service

Provides database layer for experiment scheduling system including:
- SQLite-based storage for scheduling data (auto-created in data directory)
- CRUD operations for scheduled experiments and job executions
- ScheduledToRun flag management for Hamilton integration
- Works in both development and compiled modes
"""

import logging
import json
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from backend.services.database import get_database_service
from backend.services.scheduling.sqlite_database import get_sqlite_scheduling_database
from backend.models import ScheduledExperiment, JobExecution, RetryConfig, ApiResponse

logger = logging.getLogger(__name__)


class SchedulingDatabaseManager:
    """Database management service for experiment scheduling"""
    
    def __init__(self):
        """Initialize the scheduling database manager"""
        # Use SQLite for scheduling data (auto-created)
        self.sqlite_db = get_sqlite_scheduling_database()
        
        # Keep reference to main Hamilton database for ScheduledToRun operations
        self.main_db_service = get_database_service()
        
        self._schema_initialized = True  # SQLite auto-initializes
        
    def initialize_schema(self) -> bool:
        """
        Initialize scheduling database schema
        SQLite database is auto-initialized, so this just returns success
        """
        try:
            # SQLite database is already initialized in constructor
            logger.info("SQLite scheduling database schema already initialized")
            
            # Get database info for logging
            db_info = self.sqlite_db.get_database_info()
            logger.info(f"Scheduling database: {db_info['scheduled_experiments']} schedules, {db_info['job_executions']} executions, {db_info['database_size_mb']}MB")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify scheduling schema: {e}")
            return False
    
    def store_scheduled_experiment(self, experiment: ScheduledExperiment) -> bool:
        """
        Store a scheduled experiment in the SQLite database
        
        Args:
            experiment: ScheduledExperiment object to store
            
        Returns:
            bool: True if stored successfully, False otherwise
        """
        try:
            return self.sqlite_db.create_schedule(experiment)
            
        except Exception as e:
            logger.error(f"Error storing scheduled experiment: {e}")
            return False
    
    def get_scheduled_experiment(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        """
        Retrieve a scheduled experiment by ID from SQLite
        
        Args:
            schedule_id: Unique identifier of the scheduled experiment
            
        Returns:
            ScheduledExperiment object or None if not found
        """
        try:
            return self.sqlite_db.get_schedule_by_id(schedule_id)
            
        except Exception as e:
            logger.error(f"Error retrieving scheduled experiment {schedule_id}: {e}")
            return None
    
    def get_active_schedules(self) -> List[ScheduledExperiment]:
        """
        Get all active scheduled experiments from SQLite
        
        Returns:
            List of active ScheduledExperiment objects
        """
        try:
            return self.sqlite_db.get_active_schedules()
            
        except Exception as e:
            logger.error(f"Error getting active schedules: {e}")
            return []
    
    def update_scheduled_experiment(self, experiment: ScheduledExperiment) -> bool:
        """
        Update a scheduled experiment in the SQLite database
        
        Args:
            experiment: Updated ScheduledExperiment object
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            return self.sqlite_db.update_schedule(experiment)
            
        except Exception as e:
            logger.error(f"Error updating scheduled experiment: {e}")
            return False
    
    def delete_scheduled_experiment(self, schedule_id: str) -> bool:
        """
        Delete a scheduled experiment and its associated job executions from SQLite
        
        Args:
            schedule_id: ID of the scheduled experiment to delete
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            return self.sqlite_db.delete_schedule(schedule_id)
            
        except Exception as e:
            logger.error(f"Error deleting scheduled experiment: {e}")
            return False
    
    def store_job_execution(self, execution: JobExecution) -> bool:
        """
        Store a job execution record in SQLite
        
        Args:
            execution: JobExecution object to store
            
        Returns:
            bool: True if stored successfully, False otherwise
        """
        try:
            return self.sqlite_db.create_job_execution(execution)
            
        except Exception as e:
            logger.error(f"Error storing job execution: {e}")
            return False
    
    def update_job_execution(self, execution: JobExecution) -> bool:
        """
        Update a job execution record
        
        Args:
            execution: Updated JobExecution object
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            sql = """
            UPDATE JobExecutions SET
                status = ?, start_time = ?, end_time = ?, duration_minutes = ?,
                retry_count = ?, error_message = ?, hamilton_command = ?
            WHERE execution_id = ?
            """
            
            params = [
                execution.status,
                execution.start_time,
                execution.end_time,
                execution.duration_minutes,
                execution.retry_count,
                execution.error_message,
                execution.hamilton_command,
                execution.execution_id
            ]
            
            result = self.db_service.execute_query(sql, params)
            if result.get("error"):
                logger.error(f"Failed to update job execution: {result['error']}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating job execution: {e}")
            return False
    
    def set_scheduled_to_run_flag(self, experiment_name: str, value: bool = True) -> bool:
        """
        Set the ScheduledToRun flag in the database for Hamilton integration
        Replicates VBS script database flag management
        
        Args:
            experiment_name: Name of the experiment to set the flag for
            value: True to set flag, False to clear
            
        Returns:
            bool: True if flag was set successfully, False otherwise
        """
        try:
            # This would typically update a flag in the Hamilton/EvoYeast database
            # Since we don't have access to the actual Hamilton database structure,
            # we'll implement a mock version that logs the action
            
            logger.info(f"Setting ScheduledToRun flag for {experiment_name} to {value}")
            
            # In a real implementation, this would be something like:
            # sql = "UPDATE ExperimentParameters SET ScheduledToRun = ? WHERE ExperimentName = ?"
            # result = self.db_service.execute_query(sql, [value, experiment_name])
            
            # For now, we'll use a mock table to track this state
            mock_sql = """
            IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'MockScheduledToRun')
            CREATE TABLE MockScheduledToRun (
                experiment_name NVARCHAR(255) PRIMARY KEY,
                scheduled_to_run BIT NOT NULL,
                updated_at DATETIME NOT NULL DEFAULT GETDATE()
            )
            """
            
            # Create mock table if needed
            self.db_service.execute_query(mock_sql)
            
            # Update or insert the flag
            upsert_sql = """
            IF EXISTS (SELECT 1 FROM MockScheduledToRun WHERE experiment_name = ?)
                UPDATE MockScheduledToRun SET scheduled_to_run = ?, updated_at = GETDATE() WHERE experiment_name = ?
            ELSE
                INSERT INTO MockScheduledToRun (experiment_name, scheduled_to_run, updated_at) VALUES (?, ?, GETDATE())
            """
            
            result = self.db_service.execute_query(upsert_sql, [experiment_name, value, experiment_name, experiment_name, value])
            
            if result.get("error"):
                logger.error(f"Failed to set ScheduledToRun flag: {result['error']}")
                return False
            
            logger.info(f"ScheduledToRun flag set successfully for {experiment_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting ScheduledToRun flag: {e}")
            return False
    
    def reset_all_scheduled_to_run_flags(self) -> bool:
        """
        Reset all ScheduledToRun flags to false
        Used to ensure only one experiment is scheduled at a time
        
        Returns:
            bool: True if reset successfully, False otherwise
        """
        try:
            # Reset all flags in the mock table
            sql = "UPDATE MockScheduledToRun SET scheduled_to_run = 0, updated_at = GETDATE()"
            result = self.db_service.execute_query(sql)
            
            if result.get("error"):
                logger.warning(f"Failed to reset ScheduledToRun flags: {result['error']}")
                return False
            
            logger.info("Reset all ScheduledToRun flags")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting ScheduledToRun flags: {e}")
            return False
    
    def get_upcoming_schedules(self, hours_ahead: int = 48) -> List[ScheduledExperiment]:
        """
        Get scheduled experiments for the next N hours
        
        Args:
            hours_ahead: Number of hours to look ahead (default 48)
            
        Returns:
            List of ScheduledExperiment objects
        """
        try:
            end_time = datetime.now() + timedelta(hours=hours_ahead)
            
            sql = """
            SELECT * FROM ScheduledExperiments 
            WHERE is_active = 1 
            AND start_time <= ? 
            AND start_time >= GETDATE()
            ORDER BY start_time ASC
            """
            
            result = self.db_service.execute_query(sql, [end_time])
            
            if result.get("error"):
                logger.error(f"Failed to get upcoming schedules: {result['error']}")
                return []
            
            schedules = []
            for row in result.get("rows", []):
                schedule = self._row_to_scheduled_experiment(row)
                if schedule:
                    schedules.append(schedule)
            
            return schedules
            
        except Exception as e:
            logger.error(f"Error getting upcoming schedules: {e}")
            return []
    
    def _row_to_scheduled_experiment(self, row: Dict[str, Any]) -> Optional[ScheduledExperiment]:
        """
        Convert database row to ScheduledExperiment object
        
        Args:
            row: Database row as dictionary
            
        Returns:
            ScheduledExperiment object or None if conversion fails
        """
        try:
            # Parse JSON fields
            retry_config = None
            if row.get("retry_config"):
                retry_config = RetryConfig.from_dict(json.loads(row["retry_config"]))
            
            prerequisites = []
            if row.get("prerequisites"):
                prerequisites = json.loads(row["prerequisites"])
            
            return ScheduledExperiment(
                schedule_id=row["schedule_id"],
                experiment_name=row["experiment_name"],
                experiment_path=row["experiment_path"],
                schedule_type=row["schedule_type"],
                interval_hours=row.get("interval_hours"),
                start_time=row.get("start_time"),
                estimated_duration=row.get("estimated_duration", 60),
                created_by=row.get("created_by", "system"),
                is_active=bool(row.get("is_active", True)),
                retry_config=retry_config,
                prerequisites=prerequisites,
                failed_execution_count=row.get("failed_execution_count", 0),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at")
            )
            
        except Exception as e:
            logger.error(f"Error converting row to ScheduledExperiment: {e}")
            return None


# Singleton instance management
_db_manager_instance = None
_db_manager_lock = threading.Lock()

def get_scheduling_database_manager() -> SchedulingDatabaseManager:
    """
    Get the singleton SchedulingDatabaseManager instance
    
    Returns:
        SchedulingDatabaseManager: The database manager instance
    """
    global _db_manager_instance
    
    with _db_manager_lock:
        if _db_manager_instance is None:
            _db_manager_instance = SchedulingDatabaseManager()
            
    return _db_manager_instance