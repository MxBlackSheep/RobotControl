"""Explicit, reviewed creation of a new SQL read-only identity."""
import secrets
import logging
import re
import time
import uuid
import pyodbc
from pydantic import BaseModel, ConfigDict, Field
from backend.services.database_packages import PackageError
from backend.services.report_sources import ReportSource

logger = logging.getLogger(__name__)


def setup_error(exc, stage, source, authority):
    """Expose known causes and numeric diagnostics, never raw ODBC/SQL text."""
    if isinstance(exc, PackageError):
        return str(exc)
    args = getattr(exc, 'args', ())
    state = str(args[0]) if args and re.fullmatch(r'[A-Z0-9]{5}', str(args[0])) else None
    codes = sorted({int(x) for arg in args[1:] for x in re.findall(r'\((-?\d+)\)', str(arg))})[:8]
    logger.warning('Read-only account setup failed: stage=%s sqlstate=%s codes=%s', stage, state, codes)
    if 15025 in codes:
        return f"SQL login '{source.username}' already exists. Choose a new name, such as RobotControl_ReadOnly. Existing logins are not changed."
    if 15023 in codes:
        return f"Database user '{source.username}' already exists in {source.database}. Choose a different new login name."
    if state == '28000' or 18456 in codes:
        return ('SQL Server rejected RobotControl\'s Windows sign-in. Uncheck the Windows option and use an authorized SQL administrator.'
                if authority.windows_auth else 'SQL Server rejected the administrator sign-in. Check the SQL administrator account and password.')
    if any(code in codes for code in (15247, 229)):
        who = "RobotControl's Windows account" if authority.windows_auth else 'This SQL account'
        return f'{who} lacks permission for {stage}. Use an authorized SQL administrator or download the setup SQL for them.'
    if any(code in codes for code in (911, 4060, 916)):
        return f"Cannot open database '{source.database}' with the setup account. Check the database name and that account's access."
    if state in ('IM002', 'IM003'):
        return 'The selected ODBC driver is unavailable on the RobotControl computer. Check Driver in Details.'
    if stage == 'connect':
        return f'Cannot connect to SQL Server using the setup account. Check Server and the certificate settings in Details. SQLSTATE: {state or "unavailable"}.'
    diagnostic = ' · '.join(x for x in [f'SQLSTATE {state}' if state else '', 'SQL '+', '.join(map(str,codes)) if codes else ''] if x)
    return f'Account setup failed during {stage}. {diagnostic}. Download the setup SQL for your administrator.'


class ProvisionAuthority(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(pattern=r'^[0-9a-f]{32}$')
    windows_auth: bool = False
    username: str = Field(default='', max_length=128)
    password: str = Field(default='', max_length=1000)


def identifier(value):
    return '[' + value.replace(']', ']]') + ']'


class DatabaseAccess:
    def __init__(self, sources):
        self.sources = sources
        self.reviews = {}

    def review(self, source: ReportSource, owner):
        if source.access != 'read' or source.password:
            raise PackageError('Create a new read-only account; its password is generated automatically.')
        with self.sources.lock:
            if source.id in self.sources.state['sources']:
                raise PackageError('Choose a new connection ID. Existing accounts are never changed.')
            self.reviews = {k: v for k, v in self.reviews.items() if v['expires'] > time.time()}
            if len(self.reviews) >= 50:
                raise PackageError('Too many open account reviews. Try again later.', 429)
            token = uuid.uuid4().hex
            self.reviews[token] = dict(source=source, owner=owner, expires=time.time()+600)
        return dict(token=token, server=source.server, database=source.database, account=source.username,
                    grants=['CONNECT', 'SELECT on this database', 'VIEW DEFINITION on this database', 'EXECUTE denied on this database'],
                    sql=self.script(source, '<REPLACE_WITH_STRONG_PASSWORD>'))

    @staticmethod
    def script(source, password):
        login = identifier(source.username)
        return (f"CREATE LOGIN {login} WITH PASSWORD=N'{password.replace(chr(39), chr(39)*2)}', CHECK_POLICY=ON;\n"
                f"USE {identifier(source.database)};\nCREATE USER {login} FOR LOGIN {login};\n"
                f"GRANT CONNECT, SELECT, VIEW DEFINITION TO {login};\n"
                f"DENY EXECUTE TO {login};\n")

    def create(self, authority, owner):
        with self.sources.lock:
            review = self.reviews.get(authority.token)
            if not review or review['owner'] != owner or review['expires'] < time.time():
                raise PackageError('Account review expired. Review the settings again.', 409)
            source = review['source']
            del self.reviews[authority.token]  # Do not repeat a partially completed setup.
            if source.id in self.sources.state['sources']:
                raise PackageError('Connection already exists. Review a new connection.', 409)
            quote = lambda v: '{' + str(v).replace('}', '}}') + '}'
            config = dict(DRIVER=source.driver, SERVER=source.server, DATABASE='master', Encrypt='yes',
                          TrustServerCertificate='yes' if source.trust_certificate else 'no')
            if authority.windows_auth:
                config['Trusted_Connection'] = 'yes'
            else:
                if not authority.username or not authority.password:
                    raise PackageError('Enter the SQL administrator account and password.')
                config.update(UID=authority.username, PWD=authority.password)
            conn = None
            created = False
            password = secrets.token_urlsafe(36) + 'aA1!'
            stage = 'connect'
            try:
                conn = pyodbc.connect(';'.join(f'{k}={quote(v)}' for k, v in config.items()), timeout=8)
                conn.timeout = 30
                stage = 'check login name'
                if conn.execute('SELECT 1 FROM sys.server_principals WHERE name = ?', (source.username,)).fetchone():
                    raise PackageError(f"SQL login '{source.username}' already exists. Choose a new name, such as RobotControl_ReadOnly. Existing logins are not changed.")
                # CREATE rejects an existing name; never ALTER an existing principal.
                login = identifier(source.username)
                stage = 'create login'
                conn.execute(f"CREATE LOGIN {login} WITH PASSWORD=N'{password}', CHECK_POLICY=ON")
                stage = 'open database'
                conn.execute(f'USE {identifier(source.database)}')
                stage = 'create database user'
                conn.execute(f'CREATE USER {login} FOR LOGIN {login}')
                stage = 'grant read-only access'
                conn.execute(f'GRANT CONNECT, SELECT, VIEW DEFINITION TO {login}')
                # Database diagram procedures commonly grant EXECUTE to public.
                # Override inherited execution for this new reader; never relax verification.
                conn.execute(f'DENY EXECUTE TO {login}')
                stage = 'commit account'
                conn.commit()
                created = True
                stage = 'verify and save connection'
                self.sources.save(source.model_copy(update={'password': password}))
                return {'message': 'Read-only account created, checked and saved.'}
            except Exception as exc:
                detail = setup_error(exc, stage, source, authority)
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        raise PackageError(f'{detail} Rollback could not be confirmed. Ask the SQL administrator to check the new login {source.username} before retrying.') from None
                    if created:
                        try:
                            # Verification closed its connection, but ODBC pooling
                            # can retain a session and prevent DROP LOGIN. Only this
                            # newly created identity belongs to the failed setup.
                            conn.autocommit = True
                            sessions = conn.execute('SELECT session_id FROM sys.dm_exec_sessions WHERE login_name=?', (source.username,)).fetchall()
                            for session in sessions:
                                conn.execute(f'KILL {int(session[0])}')
                            conn.autocommit = False
                            conn.execute(f'USE {identifier(source.database)}')
                            conn.execute(f'DROP USER {identifier(source.username)}')
                            conn.execute('USE master')
                            conn.execute(f'DROP LOGIN {identifier(source.username)}')
                            conn.commit()
                        except Exception:
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            raise PackageError(f'{detail} Connection was not saved. Ask the SQL administrator to check/remove the new account {source.username} from {source.database} and its server login before retrying.') from None
                raise PackageError(detail) from None
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        logger.warning('Could not close the account setup connection')
