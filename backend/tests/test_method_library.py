from pathlib import Path
from unittest.mock import Mock
import pytest
from backend.services.scheduling.method_library import browse_methods
from backend.tests.test_method_import import service, methods, client
from backend.services.scheduling.method_library import check_library_paths, library_records, check_method_path
from backend.models import ScheduledExperiment, TimeoutConfig
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase


def test_host_browser_metadata_and_navigation(tmp_path):
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'Upper.MED').write_text('metadata fixture')
    (tmp_path / 'ignore.txt').write_text('ignore')
    (tmp_path / '.hidden').mkdir()
    db = Mock()
    db.get_experiment_methods.return_value = [{'file_path': str(tmp_path / 'Upper.MED')}, {'file_path': 'old/relative.med'}]
    result = browse_methods(db, str(tmp_path))
    assert result['current_path'] == str(tmp_path)
    assert result['parent_path'] == str(tmp_path.parent)
    assert [row['name'] for row in result['folders']] == ['nested']
    assert [row['name'] for row in result['methods']] == ['Upper.MED']
    assert result['shortcuts'] == [str(tmp_path)]
    assert result['breadcrumbs'][-1]['path'] == str(tmp_path)
    with pytest.raises(ValueError): browse_methods(db, 'relative')
    with pytest.raises(OSError): browse_methods(db, str(tmp_path / 'missing'))


def test_drives_and_linked_folder(monkeypatch, tmp_path):
    db = Mock(); db.get_experiment_methods.return_value = []
    monkeypatch.setattr('backend.services.scheduling.method_library.host_drives', lambda: ['C:\\'])
    assert browse_methods(db, '')['drives'] == ['C:\\']
    linked = tmp_path / 'linked'; linked.mkdir()
    original = Path.is_junction
    monkeypatch.setattr(Path, 'is_junction', lambda path: path == linked or original(path))
    assert browse_methods(db, str(tmp_path))['folders'][0]['linked'] is True
    with pytest.raises(ValueError, match='Linked'): browse_methods(db, str(linked))


def test_browse_permission_failure(monkeypatch, tmp_path):
    db = Mock(); db.get_experiment_methods.return_value = []
    def denied(folder): raise PermissionError('denied')
    monkeypatch.setattr('backend.services.scheduling.method_library.visible_children', denied)
    with pytest.raises(PermissionError): browse_methods(db, str(tmp_path))


def add_schedule(db, path, schedule_id='uses-method'):
    schedule = ScheduledExperiment(schedule_id=schedule_id, experiment_name='Keep this label', experiment_path=str(path),
                                   schedule_type='once', timeout_config=TimeoutConfig(cleanup_experiment_path=str(path)))
    assert db.create_schedule(schedule)
    return schedule


def test_archive_restore_import_preserve_schedule_and_provenance(service, methods):
    service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    row = library_records(service.db)[0]
    add_schedule(service.db, row['file_path'])
    before = service.db.get_schedule_by_id('uses-method').to_dict()
    service.db.set_method_archived(row['method_id'], True, row['revision'])
    assert service.db.get_experiment_methods() == []
    preview = service.preview_methods(str(methods), ['Same.med'])
    assert preview['methods'][0]['archived'] is True
    result = service.import_methods_from_folder(str(methods), 'again', ['Same.med'])
    assert result['updated_methods'] == 1
    after = library_records(service.db)[0]
    assert after['archived'] == 1 and after['imported_by'] == 'tester'
    assert after['schedule_count'] == 1 and len(after['references']) == 2
    assert service.db.get_schedule_by_id('uses-method').to_dict() == before
    with pytest.raises(ValueError): service.db.set_method_archived(row['method_id'], False, row['revision'])
    service.db.set_method_archived(row['method_id'], False, after['revision'])
    assert len(service.db.get_experiment_methods()) == 1


def test_path_checks_and_legacy_identity(service, methods):
    service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    row = library_records(service.db)[0]
    (methods / 'Same.med').unlink()
    result = check_library_paths(service.db, [row['method_id']])
    assert result[0]['path_status'] == 'missing'
    assert service.db.get_experiment_methods() == []
    assert check_method_path('relative.med')['path_status'] == 'invalid'
    assert check_method_path(str(methods / 'ignore.txt'))['path_status'] == 'invalid'
    assert check_library_paths(service.db, ['absent'])[0]['success'] is False


def test_archive_resolves_legacy_duplicate_import(service, methods):
    service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    with service.db._get_connection() as conn:
        conn.execute('INSERT INTO ExperimentMethods (method_id, method_name, file_path, archived) VALUES (?, ?, ?, ?)',
                     ('archived-copy', 'Copy', str(methods / 'nested' / '..' / 'Same.med'), 1))
        conn.commit()
    assert service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])['updated_methods'] == 1
    assert len(library_records(service.db)) == 2


def test_existing_catalogue_migration_preserves_validity(service):
    service.db.import_experiment_methods([{'name': 'Legacy', 'path': 'relative.med'}], 'old')
    with service.db._get_connection() as conn:
        conn.execute('UPDATE ExperimentMethods SET is_valid = 0')
        for name in ('archived', 'revision', 'path_status', 'last_checked_at', 'validation_reason'):
            conn.execute(f'ALTER TABLE ExperimentMethods DROP COLUMN {name}')
        conn.commit()
    migrated = SQLiteSchedulingDatabase(str(service.db.db_path))
    row = migrated.get_experiment_methods(valid_only=False)[0]
    assert row['is_valid'] == 0 and row['archived'] == 0 and row['path_status'] == 'not_checked'
    assert row['file_path'] == 'relative.med' and row['imported_by'] == 'old'


def test_library_api_and_local_access(client, service, methods):
    service.import_methods_from_folder(str(methods), 'tester', ['Same.med'])
    base = '/api/scheduling/experiments/library'
    row = client.get(base).json()['data']['methods'][0]
    assert client.patch(f"{base}/{row['method_id']}", json={'archived': True, 'expected_revision': row['revision']}).status_code == 200
    assert client.patch(f"{base}/{row['method_id']}", json={'archived': False, 'expected_revision': row['revision']}).status_code == 409
    assert client.post(base + '/check', json={'method_ids': [row['method_id']]}).json()['data']['outcomes'][0]['success']
    remote = {'x-forwarded-for': '8.8.8.8'}
    assert client.get(base, headers=remote).status_code == 403
    assert client.post(base + '/check', json={'method_ids': [row['method_id']]}, headers=remote).status_code == 403
    assert client.patch(f"{base}/{row['method_id']}", json={'archived': True, 'expected_revision': 1}, headers=remote).status_code == 403
