"""Explicit, reviewed creation of a new SQL read-only identity."""
import secrets
import time
import uuid
import pyodbc
from pydantic import BaseModel, ConfigDict, Field
from backend.services.database_packages import PackageError
from backend.services.report_sources import ReportSource


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
                    grants=['CONNECT', 'SELECT on this database', 'VIEW DEFINITION on this database'],
                    sql=self.script(source, '<REPLACE_WITH_STRONG_PASSWORD>'))

    @staticmethod
    def script(source, password):
        login = identifier(source.username)
        return (f"CREATE LOGIN {login} WITH PASSWORD=N'{password.replace(chr(39), chr(39)*2)}', CHECK_POLICY=ON;\n"
                f"USE {identifier(source.database)};\nCREATE USER {login} FOR LOGIN {login};\n"
                f"GRANT CONNECT, SELECT, VIEW DEFINITION TO {login};\n")

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
            try:
                conn = pyodbc.connect(';'.join(f'{k}={quote(v)}' for k, v in config.items()), timeout=8)
                conn.timeout = 30
                # CREATE rejects an existing name; never ALTER an existing principal.
                login = identifier(source.username)
                conn.execute(f"CREATE LOGIN {login} WITH PASSWORD=N'{password}', CHECK_POLICY=ON")
                conn.execute(f'USE {identifier(source.database)}')
                conn.execute(f'CREATE USER {login} FOR LOGIN {login}')
                conn.execute(f'GRANT CONNECT, SELECT, VIEW DEFINITION TO {login}')
                conn.commit()
                created = True
                self.sources.save(source.model_copy(update={'password': password}))
                return {'message': 'Read-only account created, checked and saved.'}
            except Exception as exc:
                if conn is not None:
                    conn.rollback()
                    if created:
                        try:
                            conn.execute(f'USE {identifier(source.database)}')
                            conn.execute(f'DROP USER {identifier(source.username)}')
                            conn.execute('USE master')
                            conn.execute(f'DROP LOGIN {identifier(source.username)}')
                            conn.commit()
                        except Exception:
                            conn.rollback()
                            raise PackageError(f'Connection was not saved. Ask the SQL administrator to remove the new account {source.username} from {source.database} and its server login before retrying.') from None
                detail = str(exc) if isinstance(exc, PackageError) else 'SQL setup failed. Check the server, database, new account name and administrator authority; alternatively give the reviewed SQL script to your database administrator.'
                raise PackageError(detail) from None
            finally:
                if conn is not None:
                    conn.close()
