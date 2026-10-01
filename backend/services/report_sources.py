"""Local SQL Server report connections. Database grants, not Python isolation."""
from contextlib import contextmanager, ExitStack
import copy
import json
import math
import re
import threading
import uuid
from pathlib import Path
from typing import Literal

import pyodbc
from pydantic import BaseModel, ConfigDict, Field
from backend.services.database_packages import PackageError, IDENTIFIER
from backend.utils.filesystem import replace_file
from backend.utils.secret_cipher import encrypt_secret, decrypt_secret


class ReportSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=IDENTIFIER)
    name: str = Field(min_length=1, max_length=100)
    server: str = Field(min_length=1, max_length=300)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=1000)
    driver: str = Field(default='ODBC Driver 17 for SQL Server', max_length=128)
    trust_certificate: bool = False
    access: Literal['read', 'operation'] = 'read'


def _check_database_permissions(cursor, allowed):
    permissions = {r[0] for r in cursor.execute("SELECT permission_name FROM sys.fn_my_permissions(NULL, 'DATABASE')").fetchall()}
    denied = permissions - allowed['DATABASE']
    if denied:
        raise PackageError(f'Report account has database permission {sorted(denied)[0]}. Use a dedicated SELECT-only account.')
    # Per-user IMPERSONATE and other securables are outside database/object grants.
    extra = cursor.execute("SELECT TOP 1 permission_name FROM sys.database_permissions WHERE grantee_principal_id IN (SELECT principal_id FROM sys.user_token) AND state IN ('G','W') AND class NOT IN (0,1,3)").fetchone()
    if extra:
        raise PackageError(f'Report account has additional permission {extra[0]}. Use a dedicated SELECT-only account.')
    for scope, objects in (
        # SQL Server's guest owns an empty guest schema in system databases.
        # It has no CREATE TABLE permission; ignore that empty placeholder only.
        ('SCHEMA', "SELECT QUOTENAME(name) AS securable FROM sys.schemas s WHERE name NOT IN ('sys','INFORMATION_SCHEMA') AND NOT (name='guest' AND DB_ID()<=4 AND USER_NAME()='guest' AND NOT EXISTS (SELECT 1 FROM sys.objects o WHERE o.schema_id=s.schema_id))"),
        ('OBJECT', "SELECT QUOTENAME(SCHEMA_NAME(schema_id))+'.'+QUOTENAME(name) AS securable FROM sys.objects WHERE is_ms_shipped=0"),
    ):
        denied = cursor.execute(f"SELECT TOP 1 securable, permission_name FROM ({objects}) AS objects CROSS APPLY sys.fn_my_permissions(securable, '{scope}') AS permissions WHERE permission_name NOT IN ('SELECT','VIEW DEFINITION')").fetchone()
        if denied:
            raise PackageError(f'Report account has {denied[1]} on {denied[0]}. Use SELECT-only access.')


def assert_read_only(conn):
    """Conservatively reject effective grants beyond reading, at every SQL scope.

    No probe writes or permission changes. Called for each opened connection, so
    previously checked credentials cannot silently acquire write privileges.
    Trusted Python can still obtain other credentials; this is not a sandbox.
    """
    allowed = {
        'SERVER': {'CONNECT SQL', 'VIEW ANY DATABASE', 'VIEW ANY DEFINITION', 'VIEW SERVER STATE'},
        'DATABASE': {'CONNECT', 'SELECT', 'VIEW DEFINITION', 'VIEW DATABASE STATE',
                     'VIEW ANY COLUMN MASTER KEY DEFINITION', 'VIEW ANY COLUMN ENCRYPTION KEY DEFINITION'},
        'SCHEMA': {'SELECT', 'VIEW DEFINITION'},
        'OBJECT': {'SELECT', 'VIEW DEFINITION'},
    }
    with conn.cursor() as cursor:
        permissions = {r[0] for r in cursor.execute("SELECT permission_name FROM sys.fn_my_permissions(NULL, 'SERVER')").fetchall()}
        denied = permissions - allowed['SERVER']
        if denied:
            raise PackageError(f'Report account has server permission {sorted(denied)[0]}. Use a dedicated SELECT-only account.')
        if 'VIEW ANY DATABASE' not in permissions:
            raise PackageError('Report account needs VIEW ANY DATABASE so access to other databases can be checked.')
        extra = cursor.execute("SELECT TOP 1 permission_name FROM sys.server_permissions WHERE grantee_principal_id IN (SELECT principal_id FROM sys.login_token) AND state IN ('G','W') AND class<>100 AND NOT (class=105 AND permission_name='CONNECT')").fetchone()
        if extra:
            raise PackageError(f'Report account has additional server permission {extra[0]}. Use a dedicated SELECT-only account.')
        original = cursor.execute('SELECT DB_NAME()').fetchone()[0]
        # Check all accessible user databases, including permissions reached by
        # three-part table names. System temp objects are outside report data.
        names = [r[0] for r in cursor.execute("SELECT name FROM sys.databases WHERE database_id<>2 AND HAS_DBACCESS(name)=1").fetchall()]
        try:
            for name in set(names + [original]):
                cursor.execute('USE [' + name.replace(']', ']]') + ']')
                _check_database_permissions(cursor, allowed)
        finally:
            cursor.execute('USE [' + original.replace(']', ']]') + ']')


class ReportSources:
    def __init__(self, root):
        self.path = Path(root) / 'report-sources.json'
        self.lock = threading.RLock()
        self.state = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'sources': {}, 'bindings': {}}
        self.state.setdefault('operation_bindings', {})

    def get(self, source_id, access='read'):
        with self.lock:
            source = self.state['sources'].get(source_id)
            if not source or source.get('access', 'read') != access:
                raise PackageError('Choose a configured ' + ('read-only' if access == 'read' else 'operation') + ' connection.', 409)
            return copy.deepcopy(source)

    def viewer(self):
        with self.lock:
            # Migrate the old first-available default once; do not silently switch
            # databases when an administrator removes or adds a connection.
            if 'viewer_source' not in self.state:
                first = next((s['id'] for s in self.state['sources'].values() if s.get('access', 'read') == 'read'), None)
                if first:
                    self.set_viewer(first)
            source_id = self.state.get('viewer_source')
            return self.get(source_id) if source_id else None

    def set_viewer(self, source_id):
        with self.lock:
            self.get(source_id)
            state = copy.deepcopy(self.state)
            state['viewer_source'] = source_id
            self._save(state)

    def operation_target(self, package_id):
        with self.lock:
            return self.get(self.state['operation_bindings'].get(package_id), 'operation')

    def bind_operation(self, package_id, source_id):
        with self.lock:
            if source_id:
                self.get(source_id, 'operation')
            state = copy.deepcopy(self.state)
            state['operation_bindings'][package_id] = source_id
            self._save(state)

    def _save(self, state):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        replace_file(temporary, self.path)
        self.state = state

    def list(self):
        with self.lock:
            return [{k: v for k, v in source.items() if k != 'password_encrypted'} | {'has_password': True}
                    for source in self.state['sources'].values()]

    def save(self, source):
        value = source.model_dump(exclude={'password'})
        with self.lock:
            old = self.state['sources'].get(source.id, {})
            if old and old.get('access', 'read') != source.access:
                raise PackageError('Create a separate connection when changing its access type.')
        if source.password is not None:
            value['password_encrypted'] = encrypt_secret(source.password)
        else:
            value['password_encrypted'] = old.get('password_encrypted')
        if not value['password_encrypted']:
            raise PackageError('Enter the account password.')
        value['revision'] = uuid.uuid4().hex
        with self.open(value):
            pass
        with self.lock:
            state = copy.deepcopy(self.state)
            state['sources'][source.id] = value
            self._save(state)
        return {'message': 'Connection and effective read permissions checked.' if source.access == 'read' else 'Operation connection checked and saved.'}

    def remove(self, source_id):
        with self.lock:
            if source_id == self.state.get('viewer_source'):
                raise PackageError('Tables and Stored procedures use this connection. Choose another in Database settings first.', 409)
            if any(source_id in mapping.values() for mapping in self.state['bindings'].values()) or source_id in self.state['operation_bindings'].values():
                raise PackageError('This connection is assigned to a package. Change its mappings first.', 409)
            state = copy.deepcopy(self.state)
            state['sources'].pop(source_id, None)
            self._save(state)

    @staticmethod
    def aliases(manifest):
        return sorted({alias for tool in manifest['tools']
                       for alias in (tool.get('sources', []) if manifest.get('contract_version') == 2 else ['primary'] if tool['kind'] == 'report' else [])})

    def bindings(self, package_id):
        with self.lock:
            return dict(self.state['bindings'].get(package_id, {}))

    def bind(self, package_id, aliases, mapping):
        with self.lock:
            if set(mapping) != set(aliases) or any(x not in self.state['sources'] or self.state['sources'][x].get('access', 'read') != 'read' for x in mapping.values()):
                raise PackageError('Choose a report connection for every source alias.')
            state = copy.deepcopy(self.state)
            state['bindings'][package_id] = mapping
            self._save(state)

    def unbind(self, package_id):
        with self.lock:
            state = copy.deepcopy(self.state)
            state['bindings'].pop(package_id, None)
            state['operation_bindings'].pop(package_id, None)
            self._save(state)

    def snapshot(self, package_id, aliases, mapping=None):
        with self.lock:
            mapping = mapping if mapping is not None else self.state['bindings'].get(package_id, {})
            if any(mapping.get(x) not in self.state['sources'] for x in aliases):
                raise PackageError('Connection setup needed. Ask a local administrator to assign read-only report connections.', 409)
            return {x: self.get(mapping[x]) for x in aliases}

    @contextmanager
    def open(self, source):
        # Braced ODBC values prevent connection-string injection through passwords.
        def quoted(value):
            return '{' + str(value).replace('}', '}}') + '}'
        config = {'DRIVER': source['driver'], 'SERVER': source['server'], 'DATABASE': source['database'],
                  'UID': source['username'], 'PWD': decrypt_secret(source['password_encrypted']),
                  'Encrypt': 'yes', 'TrustServerCertificate': 'yes' if source['trust_certificate'] else 'no'}
        conn = None
        try:
            conn = pyodbc.connect(';'.join(f'{k}={quoted(v)}' for k, v in config.items()), timeout=8)
            conn.timeout = 30
            if source.get('access', 'read') == 'read':
                assert_read_only(conn)
            else:
                conn.execute('SELECT DB_NAME()').fetchone()
            yield conn
        except pyodbc.Error as exc:
            # Driver errors can disclose addresses/usernames; never expose passwords.
            raise PackageError(f"Cannot use connection '{source['name']}'. Check the connection settings, account permissions and query.") from exc
        finally:
            if conn is not None:
                conn.close()

    @contextmanager
    def connections(self, snapshot):
        with ExitStack() as stack:
            yield {name: stack.enter_context(self.open(source)) for name, source in snapshot.items()}


def lookup_rows(conn, field, values, search='', page=1, selected=None):
    lookup = field.lookup
    if any(values.get(x) is None or values.get(x) == '' for x in lookup.parameters):
        raise PackageError(f'Choose the inputs required by {field.label} first.')
    query = lookup.query.strip()
    # This restriction makes a composable subquery, not a security boundary.
    if not re.match(r'^SELECT\b', query, re.I) or ';' in query or '--' in query or '/*' in query:
        raise PackageError(f'{field.label}: use one SELECT query without comments or a trailing semicolon.')
    params = [values[x] for x in lookup.parameters]
    where = '[value] = ?' if selected is not None else 'CAST([label] AS nvarchar(2000)) LIKE ?'
    params.append(selected if selected is not None else '%' + search.replace('[', '[[]').replace('%', '[%]').replace('_', '[_]') + '%')
    # ROW_NUMBER also supports deployed SQL Server 2008 installations.
    sql = f'SELECT [value], [label] FROM (SELECT [value], [label], ROW_NUMBER() OVER (ORDER BY [label], [value]) AS rn FROM (SELECT DISTINCT [value], [label] FROM ({query}) AS options WHERE {where}) AS distinct_options) AS numbered WHERE rn > ? AND rn <= ? ORDER BY rn'
    params.extend([(page - 1) * 25, (page - 1) * 25 + 26])
    conn.timeout = 30
    with conn.cursor() as cursor:
        rows = cursor.execute(sql, params).fetchall()
    result = []
    for value, label in rows[:25]:
        if lookup.value_type == 'text':
            value = str(value) if value is not None else None
        elif lookup.value_type == 'integer':
            if value is None or int(value) != value:
                raise PackageError(f'{field.label}: query returned a non-integer value.')
            value = int(value)
        else:
            try:
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError()
            except (ValueError, TypeError, OverflowError):
                raise PackageError(f'{field.label}: query returned an invalid number.')
        if value is not None:
            result.append({'value': value, 'label': str(label) if label is not None else str(value)})
    return {'options': result, 'has_more': len(rows) > 25}
