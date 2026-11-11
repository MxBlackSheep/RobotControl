"""
Lightweight database service for RobotControl.
Provides the small subset of features the API relies on without
connection pooling, failover orchestration, or mock data layers.
"""

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pyodbc

from backend.config import settings
from backend.utils.odbc_driver import build_connection_string

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Standardised query result payload used by the API layer."""

    table_name: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_count: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    execution_time_ms: Optional[float] = None


@dataclass
class DatabaseStatus:
    """Basic status information exposed by /api/database/status."""

    is_connected: bool
    mode: str
    database_name: Optional[str]
    server_name: Optional[str]
    last_check: datetime
    error_message: Optional[str] = None


class DatabaseConnectionError(RuntimeError):
    """Raised when the primary database connection cannot be established."""


class DatabaseService:
    """Small wrapper around pyodbc for the FastAPI endpoints.

    The service connects to the primary SQL Server instance (localhost) and
    records minimal performance stats so the UI can display activity metrics.
    """

    def __init__(self) -> None:
        self._primary_config = dict(settings.DB_CONFIG_PRIMARY)

        self._lock = threading.Lock()
        self._active_mode: Optional[str] = None
        self._last_error: Optional[str] = None
        self._initialized = True

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _open_connection(self) -> Tuple[pyodbc.Connection, str]:
        config = self._primary_config
        conn_str = build_connection_string(config)
        timeout = config.get("timeout", 5)

        try:
            conn = pyodbc.connect(conn_str, timeout=timeout)
        except pyodbc.Error as exc:  # pragma: no cover - depends on environment
            self._last_error = str(exc)
            logger.warning("Database connection attempt failed (primary): %s", exc)
            raise DatabaseConnectionError(self._last_error or "Unable to connect to database")

        self._active_mode = "primary"
        self._last_error = None
        return conn, "primary"


    @contextmanager
    def get_connection(self):
        conn, _ = self._open_connection()
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover - defensive
                pass

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------
    def get_status(self) -> DatabaseStatus:
        now = datetime.now()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DB_NAME(), @@SERVERNAME")
                row = cursor.fetchone() or (None, None)
                cursor.close()

                database_name, server_name = row
                return DatabaseStatus(
                    is_connected=True,
                    mode=self._active_mode or "primary",
                    database_name=database_name,
                    server_name=server_name,
                    last_check=now,
                )
        except Exception as exc:  # pragma: no cover - connection failure path
            logger.error("Database status check failed: %s", exc)
            return DatabaseStatus(
                is_connected=False,
                mode=self._active_mode or "unavailable",
                database_name=None,
                server_name=None,
                last_check=now,
                error_message=str(exc),
            )


    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_row(columns: List[str], row: Tuple[Any, ...]) -> Dict[str, Any]:
        formatted: Dict[str, Any] = {}
        for column, value in zip(columns, row):
            if hasattr(value, "isoformat"):
                formatted[column] = value.isoformat()  # datetime/date objects
            else:
                formatted[column] = value
        return formatted


    def execute_query(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> Dict[str, Any]:
        start = time.perf_counter()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())

            if cursor.description:
                columns = [column[0] for column in cursor.description]
                rows = [self._format_row(columns, row) for row in cursor.fetchall()]
            else:
                columns = []
                rows = []
            rowcount = cursor.rowcount
            cursor.close()

        duration_ms = (time.perf_counter() - start) * 1000

        return {
            "columns": columns,
            "rows": rows,
            "rowcount": rowcount,
            "execution_time_ms": round(duration_ms, 2),
        }


_service_instance: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    global _service_instance
    if _service_instance is None:
        _service_instance = DatabaseService()
    return _service_instance
