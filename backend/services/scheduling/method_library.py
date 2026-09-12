"""Host method browsing and catalogue management. Never executes Hamilton methods."""
from pathlib import Path
from datetime import datetime

from backend.utils.filesystem import host_drives, restricted_directory, visible_children
from backend.utils.filesystem import method_path_key


def check_method_path(raw):
    result = {'path_status': 'available', 'validation_reason': None, 'last_checked_at': datetime.now().isoformat()}
    try:
        path = Path(raw)
        if not path.is_absolute() or path.suffix.lower() != '.med':
            raise ValueError('An absolute .med file path is required; legacy relative paths need manual correction.')
        path = path.resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != '.med':
            raise ValueError('The path must point to a .med file.')
        stat = path.stat()
        result.update(path=str(path), file_size=stat.st_size, file_modified=datetime.fromtimestamp(stat.st_mtime).isoformat())
    except FileNotFoundError as exc:
        result.update(path_status='missing', validation_reason=str(exc))
    except OSError as exc:
        result.update(path_status='inaccessible', validation_reason=str(exc))
    except ValueError as exc:
        result.update(path_status='invalid', validation_reason=str(exc))
    return result


def library_records(db):
    rows = db.get_experiment_methods(valid_only=False)
    keys = {}
    for row in rows:
        try:
            key = method_path_key(row['file_path'])
            keys[key] = keys.get(key, 0) + 1
        except (OSError, ValueError):
            pass
    for row in rows:
        row['containing_folder'] = str(Path(row['file_path']).parent)
        try:
            row['references'] = db.get_method_references(row['file_path'])
            row['duplicate_path'] = keys.get(method_path_key(row['file_path']), 0) > 1
        except (OSError, ValueError):
            row['references'] = []
            row['duplicate_path'] = False
        row['schedule_count'] = len({ref['schedule_id'] for ref in row['references']})
    return rows


def check_library_paths(db, method_ids):
    records = {row['method_id']: row for row in db.get_experiment_methods(valid_only=False)}
    outcomes = []
    for method_id in dict.fromkeys(method_ids):
        row = records.get(method_id)
        try:
            if not row:
                raise ValueError('Method no longer exists.')
            result = check_method_path(row['file_path'])
            db.save_method_validation(method_id, row['revision'], result)
            outcomes.append({'method_id': method_id, 'success': True, **result})
        except ValueError as exc:
            outcomes.append({'method_id': method_id, 'success': False, 'reason': str(exc)})
    return outcomes


def browse_methods(db, path=None):
    drives = host_drives()
    shortcuts = sorted({str(Path(row['file_path']).parent) for row in db.get_experiment_methods(valid_only=False)
                        if Path(row['file_path']).is_absolute()}, key=str.casefold)
    result = {'current_path': None, 'parent_path': None, 'folders': [], 'methods': [],
              'drives': drives, 'shortcuts': shortcuts, 'breadcrumbs': []}
    if path is None:
        default = Path(r'C:\Program Files\HAMILTON\Methods')
        path = str(default) if default.is_dir() else ''
    if not path:
        return result
    folder = Path(path.strip().strip('"'))
    if not folder.is_absolute():
        raise ValueError('Enter an absolute folder path on the RobotControl computer.')
    if folder.is_symlink() or folder.is_junction():
        raise ValueError('Linked folders cannot be selected. Enter the original folder path.')
    folder = folder.resolve(strict=True)
    if restricted_directory(folder):
        raise PermissionError('Access to this directory is restricted.')
    if not folder.is_dir():
        raise ValueError('The selected path is not a folder.')
    result.update(current_path=str(folder), parent_path=str(folder.parent) if folder.parent != folder else None,
                  breadcrumbs=[{'name': p.name or str(p), 'path': str(p)}
                               for p in [*reversed(folder.parents), folder]])
    for child in visible_children(folder):
        try:
            linked = child.is_symlink() or child.is_junction()
            if child.is_dir():
                result['folders'].append({'name': child.name, 'path': str(child), 'linked': linked})
            elif child.suffix.lower() == '.med' and not linked and child.is_file():
                child.stat()
                result['methods'].append({'name': child.name, 'path': str(child)})
        except OSError:
            continue
    for key in ('folders', 'methods'):
        result[key].sort(key=lambda row: row['name'].casefold())
    return result
