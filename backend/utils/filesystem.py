"""Small filesystem helpers: atomic replacement and directory listing for the host browsers."""
import ctypes
import os
from pathlib import Path
import sys

if sys.platform == 'win32':
    from ctypes import wintypes as wt

    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _kernel32.CreateFileW.restype = wt.HANDLE
    _kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
    _kernel32.SetFileInformationByHandle.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _INVALID_HANDLE = wt.HANDLE(-1).value
    _DELETE, _SHARE_ALL, _OPEN_EXISTING, _OPEN_REPARSE_POINT = 0x00010000, 0x7, 3, 0x00200000
    _FILE_RENAME_INFO_EX = 22
    _REPLACE_IF_EXISTS_POSIX = 0x1 | 0x2
    # Volumes such as FAT32, exFAT and some network shares do not support POSIX rename.
    _UNSUPPORTED = {1, 50, 87}  # ERROR_INVALID_FUNCTION, ERROR_NOT_SUPPORTED, ERROR_INVALID_PARAMETER


def replace_file(source: Path, target: Path) -> None:
    """Atomically replace target with source, like os.replace.

    On Windows, os.replace (MoveFileEx) fails with WinError 5 while any other program has
    target open, including antivirus and indexers that briefly open new files and allow
    deletion. A POSIX-semantics rename replaces the name and leaves such handles valid,
    so only an opener that forbids deletion can still block the replacement.
    """
    if sys.platform != 'win32':
        os.replace(source, target)
        return
    source, target = os.path.abspath(source), os.path.abspath(target)
    units = len(target.encode('utf-16-le')) // 2

    class RenameInfo(ctypes.Structure):
        _fields_ = [('Flags', wt.DWORD), ('RootDirectory', wt.HANDLE),
                    ('FileNameLength', wt.DWORD), ('FileName', wt.WCHAR * (units + 1))]

    info = RenameInfo(_REPLACE_IF_EXISTS_POSIX, None, units * 2, target)
    handle = _kernel32.CreateFileW(source, _DELETE, _SHARE_ALL, None, _OPEN_EXISTING, _OPEN_REPARSE_POINT, None)
    if handle == _INVALID_HANDLE:
        error = ctypes.get_last_error()
    else:
        try:
            if _kernel32.SetFileInformationByHandle(handle, _FILE_RENAME_INFO_EX, ctypes.byref(info), ctypes.sizeof(info)):
                return
            error = ctypes.get_last_error()
        finally:
            _kernel32.CloseHandle(handle)
        if error in _UNSUPPORTED:
            os.replace(source, target)
            return
    raise OSError(None, ctypes.FormatError(error).rstrip('.'), source, error, target)


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
