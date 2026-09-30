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
from collections import defaultdict

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
    connection_pool_size: int
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

    def _check_table_has_data(self, table_name: str) -> Optional[bool]:
        """True or False when checked; None when the check failed, so it is not shown as empty."""
        quoted = table_name.replace("]", "]]")
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT TOP 1 1 FROM [{quoted}]")
                result = cursor.fetchone() is not None
                cursor.close()
                return result
        except Exception as exc:
            logger.warning("Could not check whether table %s has data: %s", table_name, exc)
            return None

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

    def _get_browse_metadata(self, conn, table_name: str):
        """Only scalar SQL types support text search; primary keys stabilize paging ties."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", table_name)
            scalar_types = {"char", "varchar", "nchar", "nvarchar", "text", "ntext", "int", "bigint", "smallint", "tinyint", "bit", "decimal", "numeric", "money", "smallmoney", "float", "real", "date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "time", "uniqueidentifier"}
            searchable = [row[0] for row in cursor.fetchall() if row[1].lower() in scalar_types]
            cursor.execute("""SELECT c.name FROM sys.indexes i
                JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
                JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
                WHERE i.object_id=OBJECT_ID(?) AND i.is_primary_key=1 AND ic.key_ordinal>0
                ORDER BY ic.key_ordinal""", table_name)
            return searchable, [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

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
        safe_table = self._quote_table(table_name)
        start_row = max(1, offset + 1)
        page_size = max(1, limit)
        end_row = start_row + page_size - 1

        base_query = (
            f"SELECT {select_columns}, ROW_NUMBER() OVER (ORDER BY {order_expression}) AS row_num "
            f"FROM {safe_table} {where_sql}"
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

    def _quote_table(self, name):
        return '[' + name.replace(']', ']]') + ']'

    def get_table_data(
        self,
        table_name: str,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        search: Optional[str] = None,
        sort_direction: str = "asc",
    ) -> QueryResult:
        if sort_direction not in ("asc", "desc"):
            raise ValueError("sort_direction must be asc or desc")
        if search is not None and (not isinstance(search, str) or len(search) > 200):
            raise ValueError("search must contain at most 200 characters")
        if filters is not None and not isinstance(filters, dict):
            raise ValueError("filters must be a JSON object keyed by column")
        quote = lambda name: "[" + name.replace("]", "]]") + "]"
        start = time.perf_counter()
        with self.get_connection() as conn:
            conn.timeout = 30  # Applies to metadata, row and count queries.
            cursor = conn.cursor()

            columns_info = self._get_table_columns(conn, table_name)
            if not columns_info:
                raise ValueError(f"Table '{table_name}' not found")

            searchable, unique_key = self._get_browse_metadata(conn, table_name)
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
                        where_clauses.append(f"CONVERT(NVARCHAR(MAX), {quote(column)}) LIKE ?")
                        params.append(f"%{value_str}%")
                    elif operator == "starts_with":
                        value_str = str(normalized_value)
                        where_clauses.append(f"CONVERT(NVARCHAR(MAX), {quote(column)}) LIKE ?")
                        params.append(f"{value_str}%")
                    elif operator == "ends_with":
                        value_str = str(normalized_value)
                        where_clauses.append(f"CONVERT(NVARCHAR(MAX), {quote(column)}) LIKE ?")
                        params.append(f"%{value_str}")
                    else:
                        if operator != "equals":
                            logger.debug(
                                "Unsupported filter operator '%s' for column '%s'; defaulting to equality",
                                operator,
                                column,
                            )
                        where_clauses.append(f"{quote(column)} = ?")
                        params.append(normalized_value)
            if search and search.strip():
                search_columns = [column for column in searchable if column in columns_info]
                if search_columns:
                    where_clauses.append("(" + " OR ".join(f"CONVERT(NVARCHAR(MAX), {quote(column)}) LIKE ?" for column in search_columns) + ")")
                    literal = search.strip().replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
                    params.extend([f"%{literal}%"] * len(search_columns))
                else:
                    where_clauses.append("1 = 0")
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            if order_by and order_by not in columns_info:
                raise ValueError("Unknown sort column")
            first = order_by or next(iter(unique_key), columns_info[0])
            order_columns = [first] + [col for col in unique_key if col != first and col in columns_info]
            order_expression = ", ".join(f"{quote(col)} {sort_direction.upper()}" for col in order_columns)
            order_clause = f"ORDER BY {order_expression}"

            page_size = limit if isinstance(limit, int) and limit > 0 else 100

            self._ensure_capabilities(conn)

            select_columns = ", ".join(f"{quote(col)}" for col in columns_info)
            supports_offset = self._supports_offset_fetch is not False
            page_cursor = cursor

            columns: List[str] = []
            rows: List[Dict[str, Any]] = []

            if supports_offset:
                try:
                    query = (
                        f"SELECT {select_columns} FROM {self._quote_table(table_name)} {where_sql} {order_clause} "
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
                count_query = f"SELECT COUNT(*) FROM {self._quote_table(table_name)} {where_sql}"
                cursor.execute(count_query, tuple(params))
            else:
                cursor.execute(f"SELECT COUNT(*) FROM {self._quote_table(table_name)}")
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

    def get_stored_procedures(self, use_cache: bool = True, qualified: bool = False) -> Dict[str, List[Dict[str, Any]]]:
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
                        ON sm.object_id = OBJECT_ID(QUOTENAME(r.ROUTINE_SCHEMA) + '.' + QUOTENAME(r.ROUTINE_NAME))
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
                        "name": ('[' + schema.replace(']', ']]') + '].[' + name.replace(']', ']]') + ']') if qualified else name,
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
            if qualified:
                raise
            logger.warning("Failed to load stored procedures: %s", exc)
        return {"procedures": procedures, "functions": functions}

_service_instance: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    global _service_instance
    if _service_instance is None:
        _service_instance = DatabaseService()
    return _service_instance

