"""
Compatibility wrapper for legacy imports.

Historically the PyInstaller entry point imported
``backend.services.scheduling.database_manager_backup`` to avoid pulling in
heavy dependencies during bootstrap. The project now maintains a single
database manager implementation, and this module re-exports that primary
version so existing imports keep working without duplicating code.
"""

from .database_manager import (  # noqa: F401
    ABORT_STATES,
    SchedulingDatabaseManager,
    get_scheduling_database_manager,
)

__all__ = [
    "ABORT_STATES",
    "SchedulingDatabaseManager",
    "get_scheduling_database_manager",
]

