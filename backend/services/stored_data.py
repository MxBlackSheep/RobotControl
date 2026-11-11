"""Ordered store upgrades. Each step and its version commit together."""
import json
from pathlib import Path
import tempfile

from backend.services.sqlite_safety import StorageUnavailable
from backend.utils.filesystem import replace_file


class UpgradeStopped(StorageUnavailable):
    def __init__(self, store, step, reason, backup_path=None):
        self.store, self.step, self.backup_path = store, step, backup_path
        super().__init__(f'Upgrade stopped at step {step}: {reason}. Backup: {backup_path or "not created"}')


def upgrade_sqlite(connect, steps, backup):
    """Apply numbered steps from version zero; connect supplies a closing context."""
    store, step, backup_path = None, None, None
    try:
        with connect() as conn:
            store = conn.execute('PRAGMA database_list').fetchone()[2]
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='SchemaMigrations'").fetchone()
            version = (conn.execute('SELECT COALESCE(MAX(version), 0) FROM SchemaMigrations').fetchone()[0]
                       if exists else 0)
            if version > len(steps):
                raise UpgradeStopped(store, version, 'data is from a newer RobotControl')
            if version == len(steps):
                return
            step = version + 1
            backup_path = backup()
            for step in range(version + 1, len(steps) + 1):
                try:
                    conn.execute('BEGIN IMMEDIATE')
                    conn.execute('CREATE TABLE IF NOT EXISTS SchemaMigrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
                    steps[step - 1](conn)
                    conn.execute('INSERT INTO SchemaMigrations VALUES (?, CURRENT_TIMESTAMP)', (step,))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
    except UpgradeStopped:
        raise
    except Exception as exc:
        raise UpgradeStopped(store, step, str(exc), backup_path) from exc


def upgrade_json(path, steps):
    """JSON starts at version 1; steps maps subsequent version numbers to functions."""
    path = Path(path)
    step, backup_path = None, None
    try:
        original = path.read_bytes()
        data = json.loads(original)
        version = data.get('version', 1)
        if type(version) is not int or version < 1:
            raise ValueError('Invalid stored version')
        latest = max(steps, default=1)
        if version > latest:
            raise UpgradeStopped(path, version, 'data is from a newer RobotControl')
        if version == latest:
            return
        step = version + 1
        backup_path = path.with_name(f'{path.stem}.before_v{version}{path.suffix}')
        # A retry keeps the original backup, including after a failed step.
        if backup_path.exists():
            if backup_path.read_bytes() != original:
                raise ValueError('Existing upgrade backup differs from this store')
        else:
            with backup_path.open('xb') as saved:
                saved.write(original)
        for step in range(version + 1, latest + 1):
            steps[step](data)
            data['version'] = step
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                    temporary = Path(output.name)
                    output.write(json.dumps(data, indent=2).encode('utf-8'))
                replace_file(temporary, path)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
    except UpgradeStopped:
        raise
    except Exception as exc:
        raise UpgradeStopped(path, step, str(exc), backup_path) from exc
