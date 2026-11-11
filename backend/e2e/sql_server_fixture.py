r"""Disposable SQL Server databases and a SELECT-only login for the HTTP/SQL checks.

Needs a local .\HAMILTON SQL Server administrator through Windows authentication. Creates
two UUID-named databases (dbo.Projects, dbo.Plates, dbo.Runs) and one login, and drops
them, with any login named <login>_<role>, when the block ends. Never touches existing
databases, users or grants.
"""
from contextlib import contextmanager
from pathlib import Path
import secrets
import uuid

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
BASE = '/api/database/tools'


@contextmanager
def sql_fixture():
    suffix = uuid.uuid4().hex[:12]
    login = 'rc_report_check_' + suffix
    names = [login + '_a', login + '_b']
    password = secrets.token_urlsafe(32)
    server = r'.\HAMILTON'
    admin = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE=master;Trusted_Connection=yes;TrustServerCertificate=yes', timeout=5, autocommit=True)
    created = []
    try:
        admin.execute(f"CREATE LOGIN [{login}] WITH PASSWORD='{password}', CHECK_POLICY=OFF")
        for name in names:
            assert name.startswith('rc_report_check_') and name.replace('_', '').isalnum()
            admin.execute(f'CREATE DATABASE [{name}]'); created.append(name)
            admin.execute(f'USE [{name}]')
            admin.execute(f'CREATE USER [{login}] FOR LOGIN [{login}]')
            admin.execute(f'GRANT SELECT TO [{login}]')
            admin.execute('CREATE TABLE dbo.Projects (id int PRIMARY KEY, label nvarchar(80)); INSERT dbo.Projects VALUES (1,N\'Yeast Ω\'),(2,N\'Other\')')
            admin.execute('CREATE TABLE dbo.Plates (id int PRIMARY KEY, project int, label nvarchar(80)); INSERT dbo.Plates VALUES (11,1,N\'Same name\'),(12,1,N\'Same name\'),(21,2,N\'Other plate\')')
            # 30 runs labelled by a permutation of 01..30 (id*7 mod 31): label order is not id order.
            admin.execute("CREATE TABLE dbo.Runs (id int PRIMARY KEY, label nvarchar(80)); INSERT dbo.Runs SELECT number, RIGHT('0' + CAST(number * 7 % 31 AS varchar(2)), 2) FROM master.dbo.spt_values WHERE type = 'P' AND number BETWEEN 1 AND 30")
        admin.execute('USE master')
        yield dict(server=server, names=names, login=login, password=password, admin=admin)
    finally:
        admin.execute('USE master')
        for name in reversed(created):
            admin.execute(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            admin.execute(f'DROP DATABASE [{name}]')
        # Checks name their extra logins login + '_<role>'; the UUID prefix makes every
        # match this run's own, whichever step failed. ODBC pooling keeps sessions open,
        # and DROP LOGIN fails while one exists, so end them first. One statement per
        # execute: pyodbc raises a later statement's error only on nextset().
        owned = admin.execute('SELECT name FROM sys.server_principals WHERE name=? OR LEFT(name, ?)=?',
                              login, len(login) + 1, login + '_').fetchall()
        for (name,) in owned:
            for (session,) in admin.execute('SELECT session_id FROM sys.dm_exec_sessions WHERE login_name=?', name).fetchall():
                admin.execute(f'KILL {int(session)}')
            admin.execute(f'DROP LOGIN [{name}]')
        admin.close()
