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
import os
import threading
import sqlite3
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.services.database import get_database_service
from backend.services.scheduling.sqlite_database import get_sqlite_scheduling_database
from backend.models import HxRunMaintenanceState, ScheduledExperiment, JobExecution, NotificationContact, NotificationLogEntry, NotificationSettings
from backend.constants import HAMILTON_STATE_MAPPING


logger = logging.getLogger(__name__)

ABORT_STATES = {"Aborted", "Error"}


class SchedulingDatabaseManager:
    """Database management service for experiment scheduling."""

    def __init__(self) -> None:
        """Initialize the scheduling database manager."""
        # Use SQLite for scheduling data (auto-created)
        self.sqlite_db = get_sqlite_scheduling_database()

        # Keep reference to main Hamilton database for ScheduledToRun operations
        # Make this optional to prevent SQL Server timeout issues
        try:
            self.main_db_service = get_database_service()
            self._hamilton_db_available = True
            logger.info("Hamilton database service configured; connections are checked on use")
        except Exception as exc:  # pragma: no cover - log only
            logger.warning("Hamilton SQL Server database not available: %s", exc)
            self.main_db_service = None
            self._hamilton_db_available = False

        from backend.services.scheduling.lab_integration import load_lab_integration
        from backend.utils.data_paths import get_data_path
        self._lab = None
        self._lab_error = None
        try:
            self._lab = load_lab_integration(self.sqlite_db, self.main_db_service, get_data_path())
        except Exception:
            logger.exception("Scheduling lab configuration could not be loaded")
            self._lab_error = 'Scheduling lab setup is unavailable. Restore the previous configuration or review scheduling-lab.json and recovery.'
        self._schema_initialized = True  # SQLite auto-initializes

    def initialize_schema(self) -> bool:
        """
        Initialize scheduling database schema.

        SQLite database is auto-initialized, so this just returns success.
        """
        try:
            # SQLite database is already initialized in constructor
            logger.info("SQLite scheduling database schema already initialized")

            # Get database info for logging
            db_info = self.sqlite_db.get_database_info()
            logger.info(
                "Scheduling database: %s schedules, %s executions, %sMB",
                db_info['scheduled_experiments'],
                db_info['job_executions'],
                db_info['database_size_mb'],
            )
            return True
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to verify scheduling schema: %s", exc)
            return False

    def store_scheduled_experiment(self, experiment: ScheduledExperiment) -> bool:
        """Store a scheduled experiment in the SQLite database."""
        try:
            return self.sqlite_db.create_schedule(experiment)
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error storing scheduled experiment: %s", exc)
            return False

    def get_schedule_by_id(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        """Retrieve a scheduled experiment by ID from SQLite."""
        try:
            return self.sqlite_db.get_schedule_by_id(schedule_id)
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error retrieving scheduled experiment %s: %s", schedule_id, exc)
            return None

    def get_active_schedules(self) -> List[ScheduledExperiment]:
        """Get all active scheduled experiments from SQLite."""
        try:
            return self.sqlite_db.get_active_schedules()
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error getting active schedules: %s", exc)
            return []

    def get_schedules(self, *, active_only: bool, archived_only: bool) -> List[ScheduledExperiment]:
        """Get schedules filtered by active/archive state."""
        try:
            return self.sqlite_db.get_schedules(active_only=active_only, archived_only=archived_only)
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error getting schedules: %s", exc)
            return []

    def update_scheduled_experiment(
        self,
        experiment: ScheduledExperiment,
        *,
        touch_updated_at: bool = True,
        expected_updated_at: Optional[str] = None,
    ) -> bool:
        """Update a scheduled experiment in the SQLite database."""
        try:
            return self.sqlite_db.update_schedule(experiment, touch_updated_at=touch_updated_at, expected_updated_at=expected_updated_at)
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error updating scheduled experiment: %s", exc)
            return False

    def mark_recovery_required(self, schedule_id, note, user, *, expected_updated_at=None, snapshot=None):
        return self.sqlite_db.mark_recovery_atomic(schedule_id, note, user, expected_updated_at=expected_updated_at, snapshot=snapshot)

    def resolve_recovery_required(self, schedule_id, note, user, expected_revision, *, expected_updated_at=None):
        return self.sqlite_db.resolve_recovery_atomic(schedule_id, note, user, expected_revision, expected_updated_at=expected_updated_at)

    def get_manual_recovery_state(self):
        return self.sqlite_db.get_manual_recovery_state()





    def get_hxrun_maintenance_state(self) -> HxRunMaintenanceState:
        """Return the persistent HxRun maintenance mode state."""
        try:
            return self.sqlite_db.get_hxrun_maintenance_state()
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to load HxRun maintenance state: %s", exc)
            return HxRunMaintenanceState()

    def set_hxrun_maintenance_state(
        self,
        enabled: bool,
        reason: Optional[str],
        user: str,
    ) -> HxRunMaintenanceState:
        """Persist HxRun maintenance mode updates."""
        try:
            return self.sqlite_db.set_hxrun_maintenance_state(enabled, reason, user)
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to update HxRun maintenance state: %s", exc)
            return self.sqlite_db.get_hxrun_maintenance_state()

    def delete_scheduled_experiment(
        self,
        schedule_id: str,
        schedule: Optional[ScheduledExperiment] = None,
        expected_updated_at: Optional[str] = None,
    ) -> bool:
        """Delete a scheduled experiment and its associated job executions from SQLite."""
        try:
            return self.sqlite_db.delete_schedule(
                schedule_id,
                name_snapshot=schedule.experiment_name if schedule else None,
                path_snapshot=schedule.experiment_path if schedule else None,
                expected_updated_at=expected_updated_at,
            )
        except (SafetyConflict, StorageUnavailable, sqlite3.Error):
            raise
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error deleting scheduled experiment: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Notification settings
    # ------------------------------------------------------------------

    def get_notification_settings(self) -> NotificationSettings:
        try:
            return self.sqlite_db.get_notification_settings()
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to load notification settings: %s", exc)
            return NotificationSettings()

    def update_notification_settings(
        self,
        settings: NotificationSettings,
        *,
        password_encrypted: Optional[str],
        update_password: bool,
    ) -> NotificationSettings:
        try:
            return self.sqlite_db.update_notification_settings(
                settings,
                update_password=update_password,
                password_encrypted=password_encrypted,
            )
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to update notification settings: %s", exc)
            return self.sqlite_db.get_notification_settings()

    # ------------------------------------------------------------------
    # Notification contacts
    # ------------------------------------------------------------------

    def get_notification_contacts(self, include_inactive: bool = False) -> List[NotificationContact]:
        """Return notification contacts from the scheduling database."""
        try:
            return self.sqlite_db.get_notification_contacts(include_inactive=include_inactive)
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to load notification contacts: %s", exc)
            return []

    def get_notification_contact(self, contact_id: str) -> Optional[NotificationContact]:
        """Return a single notification contact by ID."""
        if not contact_id:
            return None
        contacts = self.get_notification_contacts(include_inactive=True)
        for contact in contacts:
            if contact.contact_id == contact_id:
                return contact
        return None

    def create_notification_contact(self, contact: NotificationContact) -> Optional[NotificationContact]:
        """Persist a new notification contact."""
        try:
            created = self.sqlite_db.create_notification_contact(contact)
            if created is None:
                return None
            # Reload so timestamps mirror the database defaults
            created = self.get_notification_contact(created.contact_id) or created
            return created
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to create notification contact %s: %s", contact.contact_id, exc)
            return None

    def update_notification_contact(self, contact: NotificationContact) -> bool:
        """Update an existing notification contact."""
        try:
            updated = self.sqlite_db.update_notification_contact(contact)
            if not updated:
                return False
            # Refresh caller copy so downstream code sees database timestamps
            refreshed = self.get_notification_contact(contact.contact_id)
            if refreshed:
                contact.display_name = refreshed.display_name
                contact.email_address = refreshed.email_address
                contact.is_active = refreshed.is_active
                contact.created_at = refreshed.created_at
                contact.updated_at = refreshed.updated_at
            return True
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to update notification contact %s: %s", contact.contact_id, exc)
            return False

    def delete_notification_contact(self, contact_id: str) -> bool:
        """Delete a notification contact."""
        try:
            return self.sqlite_db.delete_notification_contact(contact_id)
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to delete notification contact %s: %s", contact_id, exc)
            return False

    # ------------------------------------------------------------------
    # Notification logs
    # ------------------------------------------------------------------

    def finalize_job_execution(self, execution: JobExecution, schedule: ScheduledExperiment) -> bool:
        from backend.services.scheduling.run_log_store import RunLogStore
        return RunLogStore(self.sqlite_db).finalize(execution, schedule)

    def create_notification_log(self, entry: NotificationLogEntry) -> Optional[NotificationLogEntry]:
        """Create a notification log entry."""
        try:
            return self.sqlite_db.create_notification_log(entry)
        except Exception as exc:  # pragma: no cover - log only
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
        """Update a notification log entry."""
        try:
            updated = self.sqlite_db.update_notification_log(
                log_id,
                status=status,
                error_message=error_message,
                processed_at=processed_at,
                recipients=recipients,
                attachments=attachments,
                subject=subject,
                message=message,
                metadata=metadata,
            )
            if not updated:
                logger.error("Delivery record %s could not be updated to %s; do not resend accepted mail", log_id, status)
            return updated
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to update notification log %s: %s", log_id, exc)
            return False

    def notification_log_exists(self, execution_id: str, event_type: str) -> bool:
        """Return True if a log already exists for the execution/event pair."""
        try:
            return self.sqlite_db.notification_log_exists(execution_id, event_type)
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to check notification log existence for %s/%s: %s", execution_id, event_type, exc)
            return False

    def get_notification_logs(
        self,
        limit: int = 50,
        *,
        schedule_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[NotificationLogEntry]:
        """Fetch notification log entries."""
        try:
            return self.sqlite_db.get_notification_logs(
                limit,
                schedule_id=schedule_id,
                event_type=event_type,
                status=status,
            )
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Failed to fetch notification logs: %s", exc)
            return []

    def store_job_execution(self, execution: JobExecution) -> bool:
        """Store a job execution record in SQLite."""
        try:
            return self.sqlite_db.create_job_execution(execution)
        except Exception as exc:  # pragma: no cover - log only
            logger.error("Error storing job execution: %s", exc)
            return False

    @property
    def lab(self):
        if self._lab_error:
            raise SafetyConflict(self._lab_error)
        return self._lab

    def get_latest_hamilton_run_state_by_name(
        self,
        method_name: str,
        experiment_path: Optional[str] = None,
    ) -> Optional[str]:
        """Return the most recent Hamilton run state for the given method name."""
        if not method_name and not experiment_path:
            return None
        if not self._hamilton_db_available or not self.main_db_service:
            return None

        search_terms: List[str] = []

        def add_term(value: Optional[str]) -> None:
            if not value:
                return
            norm = value.strip()
            if not norm:
                return
            if norm not in search_terms:
                search_terms.append(norm)

        add_term(method_name)
        if method_name:
            method_path = Path(method_name)
            add_term(method_path.name)
            add_term(method_path.stem)
            add_term(f"{method_path.stem}.med")
            add_term(f"{method_path.stem}.hsl")

        if experiment_path:
            exp_path = Path(experiment_path)
            add_term(str(exp_path))
            add_term(exp_path.as_posix())
            add_term(exp_path.name)
            add_term(exp_path.stem)
            add_term(f"{exp_path.stem}.med")
            add_term(f"{exp_path.stem}.hsl")
            if exp_path.suffix.lower() == '.med':
                hsl_variant = str(exp_path.with_suffix('.hsl'))
                add_term(hsl_variant)
                add_term(Path(hsl_variant).as_posix())

        def query_run_state(value: str, exact: bool) -> Optional[str]:
            comparator = '=' if exact else 'LIKE'
            clause = value if exact else f"%{value}%"
            sql = (
                "SELECT TOP 1 RunState FROM HamiltonVectorDB.dbo.HxRun "
                f"WHERE MethodName {comparator} ? ORDER BY StartTime DESC"
            )
            try:
                result = self.main_db_service.execute_query(sql, (clause,))
            except Exception as exc:  # pragma: no cover - log only
                logger.debug(
                    "Run state query failed for %s (%s): %s",
                    value,
                    'exact' if exact else 'like',
                    exc,
                )
                return None

            rows = result.get('rows') if isinstance(result, dict) else None
            if not rows:
                return None

            state = rows[0].get('RunState')
            if state is None:
                return None

            return HAMILTON_STATE_MAPPING.get(str(state), str(state))

        for term in search_terms:
            state = query_run_state(term, exact=True)
            if state:
                return state

        for term in search_terms:
            if len(term) < 3:
                continue
            state = query_run_state(term, exact=False)
            if state:
                return state

        return None

    def should_block_due_to_abort(self, experiment: ScheduledExperiment) -> Optional[str]:
        """Check latest Hamilton run state and return a note if manual recovery is required."""
        try:
            candidates: List[str] = []
            if experiment.experiment_name:
                candidates.append(experiment.experiment_name)
            if experiment.experiment_path:
                base = os.path.basename(experiment.experiment_path)
                if base:
                    stem, _ = os.path.splitext(base)
                    if stem and stem not in candidates:
                        candidates.append(stem)

            for candidate in candidates:
                state = self.get_latest_hamilton_run_state_by_name(
                    candidate,
                    experiment.experiment_path,
                )
                if not state:
                    continue
                if state in ABORT_STATES:
                    return f"Hamilton reported last run as {state}"

            return None
        except Exception as exc:  # pragma: no cover - log only
            logger.debug("Abort state check failed for %s: %s", experiment.experiment_name, exc)
            return None

# Singleton instance management
_db_manager_instance: Optional[SchedulingDatabaseManager] = None
_db_manager_lock = threading.Lock()


def get_scheduling_database_manager() -> SchedulingDatabaseManager:
    """Get the singleton SchedulingDatabaseManager instance."""
    global _db_manager_instance

    with _db_manager_lock:
        if _db_manager_instance is None:
            _db_manager_instance = SchedulingDatabaseManager()

    return _db_manager_instance
