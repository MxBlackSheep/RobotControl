"""Backup boundaries with disposable files: refused list/restore remain 403;
create failure text is a sentence; managed names refuse json/bck; a failed
post-restore SELECT warns but leaves restore successful. No SQL is executed.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import backup as api
from backend.services import backup
from backend.services.auth import get_current_user

def run():
    app = FastAPI()
    app.include_router(api.router, prefix='/backup')
    app.dependency_overrides[get_current_user] = lambda: {'user_id':'fixture','username':'fixture','role':'viewer'}
    with TestClient(app, client=('203.0.113.1', 1000)) as client:
        response = client.get('/backup/list')
        assert response.status_code == 403, response.text
    with TestClient(app, client=('127.0.0.1', 1000)) as client:
        response = client.post('/backup/restore', json={'filename':'fixture.bak'})
        assert response.status_code == 403, response.text
    with tempfile.TemporaryDirectory(prefix='rc-backup-boundary-') as folder:
        with patch.object(backup, 'BACKUP_DIR', folder):
            service = backup.BackupService()
        with patch.object(backup, 'BACKUP_DIR', folder), patch.object(service._sql_executor, 'perform_backup', return_value=(False,'fixture failure')):
            try:
                service.create_backup('Fixture')
            except backup.BackupError as exc:
                assert str(exc) == 'SQL Server backup failed: fixture failure', str(exc)
            else:
                raise AssertionError('failed SQL accepted')
        for name in ['fixture.json','fixture.bck']:
            try:
                backup.validate_filename(name)
            except backup.BackupValidationError:
                pass
            else:
                raise AssertionError(name)
        path = Path(folder)/'fixture.bak'
        path.write_bytes(b'x'*2048)
        with patch.object(service, '_restore_database', return_value=(True,'ok')), patch.object(service, '_recover_database_connections', return_value='Database connectivity check after restore failed'):
            result = service.restore_backup_from_path(str(path))
        assert result.success and result.warnings == ['Database connectivity check after restore failed']
    print('PASS backup permissions, file names and failure text')

if __name__ == '__main__':
    run()
