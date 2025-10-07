"""
Lightweight database service for PyRobot.
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
from collections import defaultdict

import pyodbc

logger = logging.getLogger(__name__)


DEFAULT_PRIMARY: Dict[str, Any] = {
    "driver": "{ODBC Driver 11 for SQL Server}",
    "server": "LOCALHOST\\HAMILTON",
    "database": "EvoYeast",
    "user": "Hamilton",
    "password": "mkdpw:V43",
    "timeout": 5,
}

DEFAULT_SECONDARY: Dict[str, Any] = {
    "driver": "{ODBC Driver 11 for SQL Server}",
    "server": "192.168.3.21,50131",
    "database": "EvoYeast",
    "user": "Hamilton",
    "password": "mkdpw:V43",
    "encrypt": "no",
    "trust_server_certificate": "yes",
    "timeout": 5,
}

try:  # pragma: no cover - fallback for environments without backend.config
    from backend.config import settings  # type: ignore
except Exception:  # pragma: no cover
    class _DefaultSettings:
        DB_CONFIG_PRIMARY = DEFAULT_PRIMARY
        DB_CONFIG_SECONDARY = DEFAULT_SECONDARY

    settings = _DefaultSettings()



def _get_config(name: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    value = getattr(settings, name, None)
    if isinstance(value, dict):
        return value.copy()
    return fallback.copy()


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
    connection_pool_size: int
    last_check: datetime
    error_message: Optional[str] = None


class DatabaseConnectionError(RuntimeError):
    """Raised when neither primary nor secondary connection succeeds."""


class DatabaseService:
    """Small wrapper around pyodbc for the FastAPI endpoints.

    The service tries the primary connection first (localhost), falls back to
    the configured secondary connection, and records minimal performance stats
    so the UI can display activity metrics.
    """

    def __init__(self) -> None:
        self._primary_config = _get_config("DB_CONFIG_PRIMARY", DEFAULT_PRIMARY)
        self._secondary_config = _get_config("DB_CONFIG_SECONDARY", DEFAULT_SECONDARY)

        self._lock = threading.Lock()
        self._active_mode: Optional[str] = None
        self._query_count = 0
        self._total_execution_time_ms = 0.0
        self._last_error: Optional[str] = None
        self._supports_offset_fetch: Optional[bool] = None
        self._server_major_version: Optional[int] = None
        self._table_columns_cache: Dict[str, List[str]] = {}
        self._initialized = True

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _build_connection_string(self, config: Dict[str, Any]) -> str:
        parts: List[str] = []

        driver = config.get("driver")
        if driver:
            parts.append(f"DRIVER={driver}")

        server = config.get("server")
        if server:
            parts.append(f"SERVER={server}")

        database = config.get("database")
        if database:
            parts.append(f"DATABASE={database}")

        user = config.get("user")
        password = config.get("password")
        trusted = str(config.get("trusted_connection", config.get("trust_connection", "no"))).lower()

        if user and password:
            parts.append(f"UID={user}")
            parts.append(f"PWD={password}")
        elif trusted in ("yes", "true"):
            parts.append("Trusted_Connection=yes")

        if config.get("encrypt"):
            parts.append(f"Encrypt={config['encrypt']}")
        if config.get("trust_server_certificate"):
            parts.append(f"TrustServerCertificate={config['trust_server_certificate']}")

        return ';'.join(parts)

    def _open_connection(self) -> Tuple[pyodbc.Connection, str]:
        modes: List[str] = []
        if self._active_mode:
            modes.append(self._active_mode)
        for candidate in ("primary", "secondary"):
            if candidate not in modes:
                modes.append(candidate)

        last_error: Optional[str] = None
        for mode in modes:
            config = self._primary_config if mode == "primary" else self._secondary_config
            conn_str = self._build_connection_string(config)
            timeout = config.get("timeout", 5)
            try:
                conn = pyodbc.connect(conn_str, timeout=timeout)
                self._active_mode = mode
                self._last_error = None
                return conn, mode
            except pyodbc.Error as exc:  # pragma: no cover - depends on environment
                last_error = str(exc)
                logger.warning("Database connection attempt failed (%s): %s", mode, exc)

        self._last_error = last_error
        raise DatabaseConnectionError(last_error or "Unable to connect to database")

    def _ensure_capabilities(self, conn) -> None:
        """Populate feature flags based on SQL Server version."""
        if self._supports_offset_fetch is not None:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT CAST(SERVERPROPERTY('ProductMajorVersion') AS INT)")
            row = cursor.fetchone()
            cursor.close()
            if row and row[0] is not None:
                self._server_major_version = int(row[0])
                self._supports_offset_fetch = self._server_major_version >= 11
            else:
                self._supports_offset_fetch = True
        except Exception as exc:
            logger.warning("Database capability check failed, assuming OFFSET support: %s", exc)
            self._supports_offset_fetch = True

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
                    connection_pool_size=0,
                    last_check=now,
                )
        except Exception as exc:  # pragma: no cover - connection failure path
            logger.error("Database status check failed: %s", exc)
            return DatabaseStatus(
                is_connected=False,
                mode=self._active_mode or "unavailable",
                database_name=None,
                server_name=None,
                connection_pool_size=0,
                last_check=now,
                error_message=str(exc),
            )

    def perform_health_check(self) -> bool:
        try:
            with self.get_connection():
                return True
        except DatabaseConnectionError:
            return False

    def clear_connection_pool(self) -> None:
        """Compatibility shim - pyodbc pooling is managed globally."""
        # Nothing required for the lightweight service.

    def get_pool_stats(self) -> Dict[str, Any]:
        """Return minimal pool information for compatibility with legacy callers."""
        return {
            "active_mode": self._active_mode or "uninitialised",
            "query_count": self._query_count,
            "last_error": self._last_error,
        }

    def perform_pool_health_check(self) -> Dict[str, Any]:
        """Expose a simple health check report for callers expecting the old API."""
        healthy = self.perform_health_check()
        return {"healthy": healthy, "active_mode": self._active_mode or "unknown"}

    def warm_up_pool(self, min_connections: int = 1) -> Dict[str, Any]:
        """Attempt to establish a connection so the first query is fast."""
        try:
            with self.get_connection():
                pass
            return {"status": "success", "created_connections": 1}
        except Exception as exc:  # pragma: no cover - depends on environment
            return {"status": "error", "detail": str(exc)}

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def _record_query_metrics(self, duration_ms: float) -> None:
        self._query_count += 1
        self._total_execution_time_ms += duration_ms

    @staticmethod
    def _format_row(columns: List[str], row: Tuple[Any, ...]) -> Dict[str, Any]:
        formatted: Dict[str, Any] = {}
        for column, value in zip(columns, row):
            if hasattr(value, "isoformat"):
                formatted[column] = value.isoformat()  # datetime/date objects
            else:
                formatted[column] = value
        return formatted

    def get_tables(self, use_cache: bool = True) -> List[Dict[str, Any]]:  # pragma: no cover - simple passthrough
        tables: List[Dict[str, Any]] = []
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                """)
                names = [row[0] for row in cursor.fetchall()]
                cursor.close()

                for name in names:
                    tables.append({
                        "name": name,
                        "has_data": self._check_table_has_data(name),
                    })
        except Exception as exc:
            logger.error("Error loading table metadata: %s", exc)

        return tables

    def _check_table_has_data(self, table_name: str) -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT TOP 1 1 FROM [{table_name}]")
                result = cursor.fetchone() is not None
                cursor.close()
                return result
        except Exception:
            return False

    def _get_table_columns(self, conn, table_name: str) -> List[str]:
        """Return ordered column names for a table using a simple cache."""
        cache_key = table_name.lower()
        if cache_key in self._table_columns_cache:
            return self._table_columns_cache[cache_key]

        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
                """
            , table_name)
            columns = [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

        if columns:
            self._table_columns_cache[cache_key] = columns
        return columns

    def _execute_row_number_pagination(
        self,
        cursor,
        table_name: str,
        select_columns: str,
        where_sql: str,
        params: List[Any],
        order_expression: str,
        offset: int,
        limit: int,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Execute ROW_NUMBER pagination for servers without OFFSET support."""
        start_row = max(1, offset + 1)
        page_size = max(1, limit)
        end_row = start_row + page_size - 1

        base_query = (
            f"SELECT {select_columns}, ROW_NUMBER() OVER (ORDER BY {order_expression}) AS row_num "
            f"FROM [{table_name}] {where_sql}"
        )
        paged_query = (
            f"SELECT {select_columns} FROM ({base_query}) AS paged "
            f"WHERE paged.row_num BETWEEN ? AND ? "
            "ORDER BY paged.row_num"
        )

        cursor.execute(paged_query, (*params, start_row, end_row))
        columns = [column[0] for column in cursor.description]
        rows = [self._format_row(columns, row) for row in cursor.fetchall()]
        return columns, rows

    def get_table_data(
        self,
        table_name: str,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> QueryResult:
        start = time.perf_counter()
        with self.get_connection() as conn:
            cursor = conn.cursor()

            columns_info = self._get_table_columns(conn, table_name)
            if not columns_info:
                raise ValueError(f"Table '{table_name}' not found")

            where_clauses: List[str] = []
            params: List[Any] = []
            if filters:
                for column, raw_filter in filters.items():
                    if column not in columns_info:
                        continue

                    filter_value = raw_filter
                    operator = "equals"

                    if isinstance(raw_filter, dict):
                        operator = raw_filter.get("operator", "equals")
                        filter_value = raw_filter.get("value")

                    operator = (operator or "equals").lower()

                    normalized_value = filter_value
                    if isinstance(normalized_value, str):
                        normalized_value = normalized_value.strip()

                    if normalized_value is None or (isinstance(normalized_value, str) and normalized_value == ""):
                        continue

                    if operator == "contains":
                        value_str = str(normalized_value)
                        where_clauses.append(f"CONVERT(NVARCHAR(MAX), [{column}]) LIKE ?")
                        params.append(f"%{value_str}%")
                    elif operator == "starts_with":
                        value_str = str(normalized_value)
                        where_clauses.append(f"CONVERT(NVARCHAR(MAX), [{column}]) LIKE ?")
                        params.append(f"{value_str}%")
                    elif operator == "ends_with":
                        value_str = str(normalized_value)
                        where_clauses.append(f"CONVERT(NVARCHAR(MAX), [{column}]) LIKE ?")
                        params.append(f"%{value_str}")
                    else:
                        if operator != "equals":
                            logger.debug(
                                "Unsupported filter operator '%s' for column '%s'; defaulting to equality",
                                operator,
                                column,
                            )
                        where_clauses.append(f"[{column}] = ?")
                        params.append(normalized_value)
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            if order_by and order_by in columns_info:
                order_expression = f"[{order_by}]"
            else:
                order_expression = f"[{columns_info[0]}]"
            order_clause = f"ORDER BY {order_expression}"

            page_size = limit if isinstance(limit, int) and limit > 0 else 100

            self._ensure_capabilities(conn)

            select_columns = ", ".join(f"[{col}]" for col in columns_info)
            supports_offset = self._supports_offset_fetch is not False
            page_cursor = cursor

            columns: List[str] = []
            rows: List[Dict[str, Any]] = []

            if supports_offset:
                try:
                    query = (
                        f"SELECT {select_columns} FROM [{table_name}] {where_sql} {order_clause} "
                        f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
                    )
                    page_cursor.execute(query, (*params, offset, page_size))
                    columns = [column[0] for column in page_cursor.description]
                    rows = [self._format_row(columns, row) for row in page_cursor.fetchall()]
                except pyodbc.Error as exc:
                    message = str(exc).lower()
                    if "offset" in message and "fetch" in message:
                        logger.warning(
                            "Database server lacks OFFSET/FETCH support; using ROW_NUMBER pagination instead."
                        )
                        self._supports_offset_fetch = False
                        page_cursor.close()
                        page_cursor = conn.cursor()
                        columns, rows = self._execute_row_number_pagination(
                            page_cursor,
                            table_name,
                            select_columns,
                            where_sql,
                            params,
                            order_expression,
                            offset,
                            page_size,
                        )
                    else:
                        raise

            if not supports_offset:
                columns, rows = self._execute_row_number_pagination(
                    page_cursor,
                    table_name,
                    select_columns,
                    where_sql,
                    params,
                    order_expression,
                    offset,
                    page_size,
                )

            cursor = page_cursor

            if where_clauses:
                count_query = f"SELECT COUNT(*) FROM [{table_name}] {where_sql}"
                cursor.execute(count_query, tuple(params))
            else:
                cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            total_count = int(cursor.fetchone()[0])
            cursor.close()

        duration_ms = (time.perf_counter() - start) * 1000
        self._record_query_metrics(duration_ms)

        return QueryResult(
            table_name=table_name,
            columns=columns,
            rows=rows,
            total_count=total_count,
            limit=page_size,
            offset=offset,
            execution_time_ms=round(duration_ms, 2),
        )

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
        self._record_query_metrics(duration_ms)

        return {
            "columns": columns,
            "rows": rows,
            "rowcount": rowcount,
            "execution_time_ms": round(duration_ms, 2),
        }

    def get_monitoring_data(self) -> List[Dict[str, Any]]:  # pragma: no cover - thin wrapper
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'Experiments'
                """)
                available = {row[0] for row in cursor.fetchall()}

                if not available:
                    cursor.close()
                    return []

                preferred_order = [
                    "StartTime",
                    "LastUpdated",
                    "ExperimentID",
                ]
                order_column = next((col for col in preferred_order if col in available), next(iter(available)))

                fields = [col for col in (
                    "ExperimentID",
                    "MethodName",
                    "PlateID",
                    "StartTime",
                    "EndTime",
                    "Status",
                    "Progress",
                    "LastUpdated",
                ) if col in available]

                select_columns = ', '.join(f"[{col}]" for col in fields)
                cursor.execute(
                    f"SELECT TOP 10 {select_columns} FROM [Experiments] ORDER BY [{order_column}] DESC"
                )
                columns = [column[0] for column in cursor.description]
                rows = [self._format_row(columns, row) for row in cursor.fetchall()]
                cursor.close()
                return rows
        except Exception as exc:
            logger.warning("Monitoring query failed: %s", exc)
            return []

    def clear_cache(self, pattern: Optional[str] = None) -> int:
        """Compatibility shim - caching removed, so nothing to clear."""
        return 0

    def get_performance_stats(self) -> Dict[str, Any]:
        average = (self._total_execution_time_ms / self._query_count) if self._query_count else 0.0
        return {
            "query_count": self._query_count,
            "total_execution_time_ms": round(self._total_execution_time_ms, 2),
            "average_execution_time_ms": round(average, 2),
            "cache_hit_rate": 0.0,
            "cache_size": 0,
            "last_error": self._last_error,
        }

    def get_stored_procedures(self, use_cache: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        procedures: List[Dict[str, Any]] = []
        functions: List[Dict[str, Any]] = []
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        ROUTINE_SCHEMA,
                        ROUTINE_NAME,
                        ROUTINE_TYPE,
                        CREATED,
                        LAST_ALTERED,
                        sm.definition
                    FROM INFORMATION_SCHEMA.ROUTINES r
                    LEFT JOIN sys.sql_modules sm
                        ON sm.object_id = OBJECT_ID(r.ROUTINE_SCHEMA + '.' + r.ROUTINE_NAME)
                    ORDER BY ROUTINE_TYPE, ROUTINE_NAME
                """)
                routines = cursor.fetchall()

                cursor.execute("""
                    SELECT
                        SPECIFIC_SCHEMA,
                        SPECIFIC_NAME,
                        PARAMETER_NAME,
                        DATA_TYPE,
                        PARAMETER_MODE,
                        CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.PARAMETERS
                    ORDER BY SPECIFIC_SCHEMA, SPECIFIC_NAME, ORDINAL_POSITION
                """)
                parameters_map = defaultdict(list)
                for spec_schema, spec_name, param_name, data_type, param_mode, char_length in cursor.fetchall():
                    key = (spec_schema, spec_name)
                    parameters_map[key].append({
                        "name": param_name or '',
                        "data_type": data_type or 'UNKNOWN',
                        "mode": (param_mode or 'IN').upper(),
                        "max_length": char_length
                    })

                cursor.close()

                for schema, name, routine_type, created, last_altered, definition in routines:
                    entry = {
                        "name": name,
                        "type": routine_type,
                        "created_date": created.isoformat() if hasattr(created, 'isoformat') else None,
                        "modified_date": last_altered.isoformat() if hasattr(last_altered, 'isoformat') else None,
                        "definition": (definition.strip() if isinstance(definition, str) else None) or None,
                        "parameters": parameters_map.get((schema, name), [])
                    }
                    if routine_type == "PROCEDURE":
                        procedures.append(entry)
                    else:
                        functions.append(entry)
        except Exception as exc:
            logger.warning("Failed to load stored procedures: %s", exc)
        return {"procedures": procedures, "functions": functions}

    def execute_stored_procedure(self, procedure_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if parameters:
                    placeholder = ', '.join(f"@{key} = ?" for key in parameters.keys())
                    sql = f"EXEC [{procedure_name}] {placeholder}"
                    cursor.execute(sql, tuple(parameters.values()))
                else:
                    cursor.execute(f"EXEC [{procedure_name}]")

                if cursor.description:
                    columns = [column[0] for column in cursor.description]
                    rows = [self._format_row(columns, row) for row in cursor.fetchall()]
                else:
                    columns, rows = [], []

                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

        duration_ms = (time.perf_counter() - start) * 1000
        self._record_query_metrics(duration_ms)

        return {"columns": columns, "rows": rows, "execution_time_ms": round(duration_ms, 2)}


_service_instance: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    global _service_instance
    if _service_instance is None:
        _service_instance = DatabaseService()
    return _service_instance

