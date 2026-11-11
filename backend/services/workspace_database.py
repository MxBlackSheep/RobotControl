"""Database browsing against a captured external connection, never the robot DB."""
from contextlib import contextmanager
from backend.services.database import QueryResult, DatabaseService
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import logging
import time

logger = logging.getLogger(__name__)


class WorkspaceDatabase:
    def __init__(self, sources, source):
        self.sources = sources
        self.source = source
        self._tables = {}

    @contextmanager
    def get_connection(self):
        with self.sources.open(self.source) as conn:
            yield conn

    @staticmethod
    def qualified(schema, name):
        return '[' + schema.replace(']', ']]') + '].[' + name.replace(']', ']]') + ']'

    def get_tables(self):
        with self.get_connection() as conn, conn.cursor() as cursor:
            rows = cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_SCHEMA, TABLE_NAME").fetchall()
        self._tables = {self.qualified(s, n): (s, n) for s, n in rows}
        return [dict(name=name) for name in self._tables]

    def _identity(self, conn, name):
        if not self._tables:
            with conn.cursor() as cursor:
                rows = cursor.execute('SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES').fetchall()
            self._tables = {self.qualified(s, n): (s, n) for s, n in rows}
        if name not in self._tables:
            raise ValueError('Table or view not found. Refresh the list.')
        return self._tables[name]

    def _quote_table(self, name):
        # Names originate from metadata, not user SQL or a dotted-name parser.
        if name not in self._tables:
            raise ValueError('Table or view not found')
        return self.qualified(*self._tables[name])

    def _get_table_columns(self, conn, table_name):
        schema, name = self._identity(conn, table_name)
        with conn.cursor() as cursor:
            return [r[0] for r in cursor.execute('SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION', schema, name).fetchall()]

    def _get_browse_metadata(self, conn, table_name):
        schema, name = self._identity(conn, table_name)
        scalar = {'char', 'varchar', 'nchar', 'nvarchar', 'text', 'ntext', 'int', 'bigint', 'smallint', 'tinyint', 'bit', 'decimal', 'numeric', 'money', 'smallmoney', 'float', 'real', 'date', 'datetime', 'datetime2', 'smalldatetime', 'datetimeoffset', 'time', 'uniqueidentifier'}
        with conn.cursor() as cursor:
            searchable = [r[0] for r in cursor.execute('SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?', schema, name).fetchall() if r[1] in scalar]
            keys = cursor.execute('''SELECT c.name FROM sys.indexes i
                JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
                JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
                WHERE i.object_id=OBJECT_ID(?) AND i.is_primary_key=1 AND ic.key_ordinal>0 ORDER BY ic.key_ordinal''', table_name).fetchall()
        return searchable, [r[0] for r in keys]

    _format_row = staticmethod(DatabaseService._format_row)

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
        """Execute stable ROW_NUMBER pagination."""
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


    def get_table_data(
        self,
        table_name: str,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
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

            page_size = limit if isinstance(limit, int) and limit > 0 else 100

            select_columns = ", ".join(f"{quote(col)}" for col in columns_info)
            columns, rows = self._execute_row_number_pagination(
                cursor, table_name, select_columns, where_sql, params,
                order_expression, offset, page_size,
            )

            if where_clauses:
                count_query = f"SELECT COUNT(*) FROM {self._quote_table(table_name)} {where_sql}"
                cursor.execute(count_query, tuple(params))
            else:
                cursor.execute(f"SELECT COUNT(*) FROM {self._quote_table(table_name)}")
            total_count = int(cursor.fetchone()[0])
            cursor.close()

        duration_ms = (time.perf_counter() - start) * 1000

        return QueryResult(
            table_name=table_name,
            columns=columns,
            rows=rows,
            total_count=total_count,
            limit=page_size,
            offset=offset,
            execution_time_ms=round(duration_ms, 2),
        )


    def get_stored_procedures(self) -> Dict[str, List[Dict[str, Any]]]:
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
                        "name": self.qualified(schema, name),
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
            raise
        return {"procedures": procedures, "functions": functions}
