"""Host method browsing and catalogue management. Never executes Hamilton methods."""
from pathlib import Path

from backend.utils.filesystem import host_drives, restricted_directory, visible_children


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
