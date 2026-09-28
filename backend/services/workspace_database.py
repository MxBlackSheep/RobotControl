"""Database browsing against a captured external connection, never the robot DB."""
from contextlib import contextmanager
from backend.services.database import DatabaseService


class WorkspaceDatabase(DatabaseService):
    def __init__(self, sources, source):
        super().__init__()
        self.sources = sources
        self.source = source
        # ROW_NUMBER works on every supported SQL Server, including 2008.
        self._supports_offset_fetch = False
        self._tables = {}

    @contextmanager
    def get_connection(self):
        with self.sources.open(self.source) as conn:
            yield conn

    @staticmethod
    def qualified(schema, name):
        return '[' + schema.replace(']', ']]') + '].[' + name.replace(']', ']]') + ']'

    def get_tables(self, use_cache=True):
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

    def get_stored_procedures(self, use_cache=True):
        return super().get_stored_procedures(use_cache, qualified=True)
