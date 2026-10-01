from contextlib import closing
"""Disposable SQL adapter for HTTP workflows, never connected to Hamilton SQL Server.

SQLite stores the fixture rows. Only SQL Server metadata, Descendants and the delete
procedure are translated; packaged SQL Server/procedure compatibility still needs VM testing.
"""
import io
import json
import sqlite3
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path
from backend.services.report_worker import run_report as _production_report_worker


def package_zip(folder, manifest_changes=None, extras=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for file in Path(folder).iterdir():
            if file.suffix in {'.json', '.py', '.txt', '.md'}:
                value = file.read_bytes()
                if file.name == 'manifest.json' and manifest_changes:
                    value = json.dumps({**json.loads(value), **manifest_changes}).encode()
                archive.writestr(file.name, value)
        for name, value in (extras or {}).items():
            archive.writestr(name, value)
    return output.getvalue()


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.raw.cursor()

    @property
    def description(self): return self.cursor.description
    @property
    def rowcount(self): return self.cursor.rowcount
    def close(self): self.cursor.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    def fetchone(self): return self.cursor.fetchone()
    def fetchall(self): return self.cursor.fetchall()
    def nextset(self): return False

    def execute(self, sql, params=()):
        if 'INFORMATION_SCHEMA.TABLES' in sql:
            sql, params = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (params[1],)
        elif 'INFORMATION_SCHEMA.COLUMNS' in sql:
            sql, params = 'SELECT name AS COLUMN_NAME FROM pragma_table_info(?) ORDER BY cid', (params[1],)
        elif 'dbo.Descendants(?)' in sql:
            sql = 'SELECT DISTINCT DescPlateID FROM Descendants WHERE AncPlateID=?'
        elif sql.startswith('SET XACT_ABORT'):
            sql = 'SELECT 1'
        elif sql.startswith('EXEC dbo.DeleteExperiment'):
            sql = 'DELETE FROM Experiments WHERE ExperimentID=?'
            self.cursor.execute(sql, params)
            if self.connection.database.fail_delete:
                raise RuntimeError('Fixture SQL failure after delete')
            self.connection.database.deletes += 1
            return self
        self.cursor.execute(sql.replace('dbo.', ''), params)
        return self


class Connection:
    def __init__(self, database):
        self.database = database
        self.raw = sqlite3.connect(database.path)
        self.timeout = 30
    def cursor(self): return Cursor(self)
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class DatabaseFixture:
    def __init__(self, root):
        self.path = Path(root)/'experiments.db'
        self.fail_delete = False
        self.busy = False
        self.deletes = 0
        self.gate = threading.RLock()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executescript('''
                CREATE TABLE Experiments (ExperimentID INTEGER PRIMARY KEY, UserDefinedID TEXT, Note TEXT);
                INSERT INTO Experiments VALUES (42, 'Yeast Ω', 'Disposable culture fixture'), (43, 'Delete fixture', 'Safe disposable row');
                CREATE TABLE AncestPlatesInExperiments (ExperimentID INT, PlateID INT);
                INSERT INTO AncestPlatesInExperiments VALUES (42,10);
                CREATE TABLE Descendants (AncPlateID INT, DescPlateID INT);
                INSERT INTO Descendants VALUES (10,20);
                CREATE TABLE Cultures (CultureID INT, PlateID INT, WellID TEXT);
                INSERT INTO Cultures VALUES (1,10,'A1'),(2,10,'A2'),(3,20,'A1'),(4,20,'A2');
                CREATE TABLE ImportPlatePattern (PlateID INT, WellAssign TEXT);
                INSERT INTO ImportPlatePattern VALUES (10,'cells'),(10,'cells');
                CREATE TABLE Propagation (ParentCultureID INT, ChldCultureID INT);
                INSERT INTO Propagation VALUES (1,3),(2,4);
                CREATE TABLE CulturesHistory (CultureID INT, TimeStamp TEXT, OD_FlEx482Em510 REAL, OD_FlEx587Em611 REAL, FlEx482Em510 REAL, FlEx587Em611 REAL);
                INSERT INTO CulturesHistory VALUES
                  (1,'2026-01-01 00:00:00',0.1,0.2,10,20),(2,'2026-01-01 00:00:00',0.2,0.3,30,40),
                  (1,'2026-01-01 01:00:00',0.2,0.4,11,21),(2,'2026-01-01 01:00:00',0.4,0.6,31,41),
                  (3,'2026-01-01 02:00:00',0.3,0.6,12,22),(4,'2026-01-01 02:00:00',0.6,0.9,32,42);
                CREATE TABLE ChampionsCulturesHistory (CultureID INT, TimeStamp TEXT, OD_FlEx482Em510 REAL, OD_FlEx587Em611 REAL, FlEx482Em510 REAL, FlEx587Em611 REAL);
                INSERT INTO ChampionsCulturesHistory VALUES (1,'2026-01-01 01:30:00',0.25,0.5,15,25);
            ''')

    @contextmanager
    def get_connection(self):
        conn = Connection(self)
        try: yield conn
        finally: conn.close()

    @contextmanager
    def guard(self):
        with self.gate:
            if self.busy: raise ValueError('Robot is busy. Finish the run before changing the database.')
            yield

    def get_table_data(self, table_name, limit, offset, search, **kwargs):
        from types import SimpleNamespace
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute('SELECT * FROM Experiments ORDER BY ExperimentID DESC')]
        rows = [row for row in rows if search.lower() in str(row).lower()]
        return SimpleNamespace(rows=rows[offset:offset+limit], total_count=len(rows))


def run_fixture_report(channel, package_root, entry, definition, inputs, snapshot, folder):
    """Keep the existing disposable SQLite adapter inside the spawned child."""
    from backend.services.report_sources import ReportSources
    @contextmanager
    def open_source(self, source):
        db = object.__new__(DatabaseFixture)
        db.path = Path(source['fixture_path'])
        with db.get_connection() as conn:
            conn.raw.execute('PRAGMA query_only=ON')
            yield conn
    ReportSources.open = open_source
    _production_report_worker(channel, package_root, entry, definition, inputs, snapshot, folder)


def configure_fixture_report_sources(service):
    """Legacy workflow fixture only. SQL Server permission checks use a real fixture."""
    @contextmanager
    def open_source(source):
        with service.database.get_connection() as conn:
            if source.get('access') != 'operation':
                conn.raw.execute('PRAGMA query_only=ON')
            yield conn
    service.sources.open = open_source
    service.sources.snapshot = lambda package_id, aliases, mapping=None: {alias: {'id': 'fixture', 'fixture_path':str(service.database.path)} for alias in aliases}
    import backend.services.report_worker as worker
    worker.run_report = run_fixture_report
    service.sources.state['sources'] = {name: dict(id=name, name=name.title(), server='fixture', database='disposable',
        username='fixture', driver='fixture', trust_certificate=False) for name in ('primary', 'plates')}

    target = dict(id='operation', name='Disposable fixture', server='fixture', database='disposable', access='operation', revision='1')
    service.sources.state['sources']['operation'] = target
    service.sources.operation_target = lambda package_id: dict(target)
    service.operation_experiments = lambda tool_id, search, page: vars(service.database.get_table_data('Experiments', limit=25, offset=(page-1)*25, search=search))
