from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.scheduling as api
from backend.services.auth import get_current_user
from backend.services.scheduling.experiment_discovery import ExperimentDiscoveryService
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase


@pytest.fixture
def service(tmp_path):
    instance = ExperimentDiscoveryService.__new__(ExperimentDiscoveryService)
    instance.db = SQLiteSchedulingDatabase(str(tmp_path / 'catalogue.db'))
    instance.discovered_experiments = []
    instance._last_scan = None
    return instance


@pytest.fixture
def methods(tmp_path):
    folder = tmp_path / 'methods'
    folder.mkdir()
    (folder / 'nested').mkdir()
    (folder / 'Same.med').write_text('first')
    (folder / 'nested' / 'Same.MED').write_text('second method')
    (folder / 'ignore.txt').write_text('ignore')
    return folder


@pytest.fixture
def client(service, monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {'username': 'tester', 'role': 'user'}
    monkeypatch.setattr(api, 'get_experiment_discovery_service', lambda: service)
    # Local access is decided by the socket peer; x-forwarded-for can only restrict it.
    return TestClient(app, client=('127.0.0.1', 50000))


def test_preview_is_read_only_and_preserves_distinct_paths(service, methods, monkeypatch):
    write = Mock(side_effect=AssertionError('Preview must not import'))
    monkeypatch.setattr(service.db, 'import_experiment_methods', write)
    preview = service.preview_methods(str(methods))
    assert len(preview['methods']) == 2
    assert {row['action'] for row in preview['methods']} == {'new'}
    assert len({row['path'] for row in preview['methods']}) == 2
    assert all(Path(row['path']).is_absolute() for row in preview['methods'])
    assert service.db.get_experiment_methods() == []
    write.assert_not_called()


def test_import_and_repeat_update_use_host_metadata(service, methods):
    first = service.import_methods_from_folder(str(methods), 'tester')
    assert (first['new_methods'], first['failed_methods']) == (2, 0)
    (methods / 'Same.med').write_text('modified content')
    second = service.import_methods_from_folder(str(methods), 'tester')
    assert (second['new_methods'], second['updated_methods']) == (0, 2)
    assert len(service.db.get_experiment_methods()) == 2
    row = next(row for row in second['methods'] if row['relative_path'] == 'Same.med')
    assert row['size'] == len('modified content')
    assert all(row['action'] == 'update' for row in service.preview_methods(str(methods))['methods'])


def test_disappearing_file_is_reported_after_preview(service, methods):
    preview = service.preview_methods(str(methods))
    (methods / 'Same.med').unlink()
    result = service.import_methods_from_folder(str(methods), 'tester', [row['relative_path'] for row in preview['methods']])
    assert (result['new_methods'], result['failed_methods']) == (1, 1)
    assert result['success'] is False
    assert len(service.db.get_experiment_methods()) == 1


def test_invalid_and_duplicate_paths_are_not_imported(service, methods):
    result = service.import_methods_from_folder(str(methods), 'tester',
        ['Same.med', 'Same.med', '../escape.med', str(methods / 'Same.med'), 'ignore.txt', 'missing.med'])
    assert result['new_methods'] == 1
    assert result['failed_methods'] == 5
    assert len(result['errors']) == 5


def test_resolved_escape_and_inaccessible_metadata(service, methods, monkeypatch):
    original_resolve, original_stat = Path.resolve, Path.stat
    outside = methods.parent / 'outside.med'
    outside.write_text('outside')
    target = methods / 'Same.med'
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'resolve', lambda path, *args, **kwargs: outside if path == target else original_resolve(path, *args, **kwargs))
        assert service.preview_methods(str(methods), ['Same.med'])['methods'][0]['action'] == 'invalid'
    with monkeypatch.context() as patch:
        def denied(path, *args, **kwargs):
            if path == target:
                raise PermissionError('metadata unavailable')
            return original_stat(path, *args, **kwargs)
        patch.setattr(Path, 'stat', denied)
        row = service.preview_methods(str(methods), ['Same.med'])['methods'][0]
        assert row['action'] == 'invalid'
        assert 'metadata unavailable' in row['reason']


def test_database_partial_failure_counts_only_written_rows(service, methods):
    (methods / 'Bad.med').write_text('bad')
    with service.db._get_connection() as conn:
        conn.execute("CREATE TRIGGER fail_bad BEFORE INSERT ON ExperimentMethods WHEN NEW.method_name = 'Bad' BEGIN SELECT RAISE(ABORT, 'test write failure'); END")
        conn.commit()
    result = service.import_methods_from_folder(str(methods), 'tester')
    assert (result['new_methods'], result['failed_methods']) == (2, 1)
    assert next(row for row in result['methods'] if row['name'] == 'Bad')['status'] == 'failed'


def test_commit_failure_never_reports_success(service, methods, monkeypatch):
    original_connection = service.db._get_connection
    class FailedCommit:
        def __init__(self, connection): self.connection = connection
        def __getattr__(self, name): return getattr(self.connection, name)
        def commit(self): raise sqlite3.OperationalError('test commit failure')
    @contextmanager
    def connection():
        with original_connection() as conn:
            yield FailedCommit(conn)
    with monkeypatch.context() as patch:
        patch.setattr(service.db, '_get_connection', connection)
        result = service.import_methods_from_folder(str(methods), 'tester')
    assert result['new_methods'] == 0
    assert result['failed_methods'] == 2
    assert service.db.get_experiment_methods() == []


def test_transaction_rollback_invalidates_earlier_successes(service, methods):
    (methods / 'AFirst.med').write_text('first')
    (methods / 'Rollback.med').write_text('rollback')
    with service.db._get_connection() as conn:
        conn.execute("CREATE TRIGGER rollback_import BEFORE INSERT ON ExperimentMethods WHEN NEW.method_name = 'Rollback' BEGIN SELECT RAISE(ROLLBACK, 'test rollback'); END")
        conn.commit()
    result = service.import_methods_from_folder(str(methods), 'tester')
    assert result['new_methods'] == 0
    assert result['failed_methods'] == 4
    assert service.db.get_experiment_methods() == []


def test_old_relative_catalogue_entries_are_left_unchanged(service, methods):
    service.db.import_experiment_methods([{'name': 'Legacy', 'path': 'Legacy/Method.med'}], 'legacy')
    assert service.preview_methods(str(methods))['total_found'] == 2
    assert service.db.get_experiment_methods()[0]['file_path'] == 'Legacy/Method.med'


def test_canonical_update_preserves_older_path_and_identity(service, methods):
    original_path = str(methods / 'Same.med').replace('\\', '/')
    service.db.import_experiment_methods([{'name': 'Older name', 'path': original_path}], 'legacy')
    before = service.db.get_experiment_methods()[0]
    result = service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    after = service.db.get_experiment_methods()[0]
    assert (result['new_methods'], result['updated_methods']) == (0, 1)
    assert after['method_id'] == before['method_id']
    assert after['file_path'] == original_path


def test_ambiguous_existing_canonical_paths_fail_without_repair(service, methods):
    target = str(methods / 'Same.med')
    alternate = str(methods / 'nested' / '..' / 'Same.med')
    service.db.import_experiment_methods([{'name': 'First', 'path': target}], 'legacy')
    with service.db._get_connection() as conn:
        conn.execute('INSERT INTO ExperimentMethods (method_id, method_name, file_path) VALUES (?, ?, ?)',
                     ('old-duplicate', 'Second', alternate))
        conn.commit()
    result = service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    assert result['failed_methods'] == 1
    assert 'Multiple catalogue entries' in result['methods'][0]['reason']
    assert len(service.db.get_experiment_methods()) == 2


@pytest.mark.parametrize('endpoint', ['import-preview', 'import-folder'])
def test_import_endpoints_require_local_access(client, methods, endpoint):
    response = client.post(f'/api/scheduling/experiments/{endpoint}', json={'folder_path': str(methods)}, headers={'x-forwarded-for': '8.8.8.8'})
    assert response.status_code == 403


def test_api_preview_then_selected_import_and_update(client, service, methods):
    preview = client.post('/api/scheduling/experiments/import-preview', json={'folder_path': str(methods)}).json()['data']
    assert len(preview['methods']) == 2
    assert service.db.get_experiment_methods() == []
    response = client.post('/api/scheduling/experiments/import-folder', json={'folder_path': str(methods), 'relative_paths': ['Same.med']})
    assert response.json()['data']['new_methods'] == 1
    response = client.post('/api/scheduling/experiments/import-folder', json={'folder_path': str(methods), 'relative_paths': ['Same.med']})
    assert response.json()['data']['updated_methods'] == 1


@pytest.mark.parametrize('payload', [{'folder_path': 'relative'}, {'folder_path': ''}, {'folder_path': 4}, {}])
def test_invalid_folder_requests(client, payload):
    assert client.post('/api/scheduling/experiments/import-preview', json=payload).status_code in {400, 422}


def test_empty_selection_is_not_treated_as_import_all(client, methods):
    response = client.post('/api/scheduling/experiments/import-folder', json={'folder_path': str(methods), 'relative_paths': []})
    assert response.status_code == 400


def test_browse_endpoint_requires_local_access(client, methods):
    url = '/api/scheduling/experiments/browse'
    assert client.get(url, params={'path': str(methods)}).json()['data']['current_path'] == str(methods)
    assert client.get(url, params={'path': str(methods)}, headers={'x-forwarded-for': '8.8.8.8'}).status_code == 403
