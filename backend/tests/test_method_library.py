from pathlib import Path
from unittest.mock import Mock
import pytest
from backend.services.scheduling.method_library import browse_methods


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
