"""Small directory-listing helpers shared by the host browsers."""
from pathlib import Path


def visible_children(folder: Path):
    for child in folder.iterdir():
        if not child.name.startswith(('.', '$')):
            yield child


def restricted_directory(folder: Path) -> bool:
    return any(part in str(folder).lower() for part in
               ('windows\\system32', 'windows\\syswow64', 'program files\\windows'))


def host_drives():
    return [str(path) for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            if (path := Path(f'{letter}:\\')).exists()]


def method_path_key(value: str) -> str:
    """Canonical absolute identity, or exact legacy relative identity without guessing a root."""
    path = Path(value)
    if path.is_absolute():
        return str(path.resolve()).casefold()
    return 'relative:' + str(path).replace('/', '\\').casefold()
