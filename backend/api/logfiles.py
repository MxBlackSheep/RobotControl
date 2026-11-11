"""
Log file review API endpoints.

Provides a restricted, read-only browser and previewer for a fixed allowlist of
log directories. Plain-file tails and private reader sessions support text and compressed logs.
"""

from __future__ import annotations

import codecs
import logging
import time
import zipfile
import threading
from datetime import datetime, date
import errno
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from backend.services.log_readers import LogReaderManager, ReaderError, encoding_for

from backend.api.dependencies import ConnectionContext, get_connection_context
from backend.api.response_formatter import ResponseFormatter
from backend.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logfiles", tags=["logfiles"])
_reader_manager_lock = threading.Lock()

MAX_PREVIEW_BYTES = 1024 * 1024
MAX_BROWSE_ITEMS = 200


class OpenLogReader(BaseModel):
    source_id: str = Field(max_length=100)
    relative_path: str = Field(max_length=4096)
    entry_path: Optional[str] = Field(default=None, max_length=4096)


def _reader_manager(request: Request) -> LogReaderManager:
    with _reader_manager_lock:
        manager = getattr(request.app.state, "log_readers", None)
        if manager is None:
            directory = getattr(request.app.state, "log_reader_cache", None)
            if directory is None:
                from backend.utils.data_paths import get_path_manager
                directory = get_path_manager().temp_path / "log-readers"
            manager = LogReaderManager(Path(directory))
            request.app.state.log_readers = manager
        return manager


def _reader_access(request, ident, current_user, connection):
    manager = _reader_manager(request)
    reader = manager.get(ident, str(current_user["user_id"]))
    config, root, denied = _resolve_source_root(reader.source_id, request, connection, current_user)
    if denied is not None:
        return manager, reader, denied
    if root.resolve() != reader.root or not _is_allowed_file_for_source(config, reader.path):
        manager.release(reader.id, reader.owner)
        raise ReaderError("The log source changed. Reopen the selected file.", 404)
    with manager.lock:
        reader.touched = time.monotonic()
    return manager, reader, None


def _reader_error(exc: Exception):
    return ResponseFormatter.error(message=str(exc), error_code="LOG_READER_ERROR",
                                   status_code=exc.status if isinstance(exc, ReaderError) else 400)


@router.post("/readers")
def open_log_reader(body: OpenLogReader, request: Request,
                    current_user: Dict[str, Any] = Depends(get_current_user),
                    connection: ConnectionContext = Depends(get_connection_context)):
    try:
        config, root, denied = _resolve_source_root(body.source_id, request, connection, current_user)
        if denied is not None:
            return denied
        target = _resolve_child_path(root, body.relative_path)
        if not target.is_file():
            raise ReaderError("Log file not found.", 404)
        if not _is_allowed_file_for_source(config, target):
            raise ReaderError("This file type is not enabled for the selected source.")
        entry = _normalize_zip_entry_path(body.entry_path) if body.entry_path else None
        if bool(entry) != (target.suffix.lower() == '.zip'):
            raise ReaderError("Select a text entry inside the ZIP archive.")
        manager = _reader_manager(request)
        reader = manager.create(str(current_user['user_id']), body.source_id, target, root.resolve(), entry)
        return ResponseFormatter.success(data=manager.status(reader))
    except (ReaderError, ValueError, KeyError, OSError) as exc:
        return _reader_error(exc)


@router.get("/readers/{reader_id}")
def log_reader_status(reader_id: str, request: Request,
                      current_user: Dict[str, Any] = Depends(get_current_user),
                      connection: ConnectionContext = Depends(get_connection_context)):
    try:
        manager, reader, denied = _reader_access(request, reader_id, current_user, connection)
        return denied if denied is not None else ResponseFormatter.success(data=manager.status(reader))
    except (ReaderError, ValueError, KeyError) as exc:
        return _reader_error(exc)


@router.get("/readers/{reader_id}/sections")
def log_reader_section(reader_id: str, request: Request, cursor: str = Query('last', max_length=100),
                       current_user: Dict[str, Any] = Depends(get_current_user),
                       connection: ConnectionContext = Depends(get_connection_context)):
    try:
        manager, reader, denied = _reader_access(request, reader_id, current_user, connection)
        return denied if denied is not None else ResponseFormatter.success(data=manager.section(reader, cursor))
    except (ReaderError, ValueError, KeyError, OSError) as exc:
        return _reader_error(exc)


@router.delete("/readers/{reader_id}")
def close_log_reader(reader_id: str, request: Request,
                     current_user: Dict[str, Any] = Depends(get_current_user),
                     connection: ConnectionContext = Depends(get_connection_context)):
    try:
        manager, reader, denied = _reader_access(request, reader_id, current_user, connection)
        if denied is not None:
            return denied
        manager.release(reader.id, reader.owner)
        return ResponseFormatter.success(data={"released": True})
    except (ReaderError, ValueError, KeyError) as exc:
        return _reader_error(exc)

LOGFILE_SOURCES: Dict[str, Dict[str, Any]] = {
    "python_log": {
        "label": "Python Log",
        "path": r"C:\Python Log",
        "access_scope": "all_authenticated",
    },
    "hamilton_logfiles": {
        "label": "Hamilton LogFiles",
        "path": r"C:\Program Files\HAMILTON\LogFiles",
        "allowed_extensions": [".trc"],
        "access_scope": "all_authenticated",
    },
    "robotcontrol_logs": {
        "label": "RobotControl Logs",
        "path": None,
        "access_scope": "admin_or_local",
    },
}


def _format_file_size(size_bytes: int) -> str:
    # Whole bytes have no fraction: "537 B", not "537.0 B".
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size = size_bytes / 1024.0
    for unit in ["KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _get_sources(request: Optional[Request] = None) -> Dict[str, Dict[str, Any]]:
    sources = {source_id: dict(config) for source_id, config in LOGFILE_SOURCES.items()}
    config = sources.get("robotcontrol_logs")
    if config is not None and config.get("path") is None:
        root = getattr(request.app.state, "log_root", None) if request else None
        if root is None:
            from backend.utils.data_paths import get_path_manager
            root = get_path_manager().logs_path
        config["path"] = str(Path(root).resolve())
    return sources


def _get_allowed_extensions_for_source(source_config: Dict[str, Any]) -> Optional[set[str]]:
    raw = source_config.get("allowed_extensions")
    if not raw:
        return None
    return {str(ext).lower() for ext in raw}


def _is_allowed_file_for_source(source_config: Dict[str, Any], file_path: Path) -> bool:
    allowed = _get_allowed_extensions_for_source(source_config)
    if not allowed:
        return True
    return file_path.suffix.lower() in allowed


def _enforce_source_access(source_id: str, source_config: Dict[str, Any], connection: ConnectionContext, current_user: Optional[Dict[str, Any]] = None):
    access_scope = str(source_config.get("access_scope") or "local_only")
    if access_scope == "all_authenticated":
        return None
    if access_scope == "admin_or_local" and (connection.is_local or (current_user or {}).get("role") == "admin"):
        return None
    if access_scope == "local_only" and connection.is_local:
        return None
    return ResponseFormatter.forbidden(
        message="An administrator or a local session is required for this log source",
        details={
            "source_id": source_id,
            "source_label": source_config.get("label"),
            "access_scope": access_scope,
            "ip_classification": connection.ip_classification,
        },
    )


def _sanitize_relative_path(relative_path: Optional[str]) -> str:
    if not relative_path:
        return ""

    normalized = relative_path.replace("\\", "/").strip()
    if not normalized or normalized == ".":
        return ""
    if normalized.startswith("/") or ":" in normalized:
        raise ValueError("Absolute paths are not allowed")

    pure = PurePosixPath(normalized)
    if any(part in ("..", "") for part in pure.parts):
        # Reject traversal and malformed duplicate separators.
        raise ValueError("Invalid relative path")

    return pure.as_posix()


def _resolve_source_root(source_id, request, connection, current_user):
    sources = _get_sources(request)
    if source_id not in sources:
        raise KeyError(f"Unknown source_id '{source_id}'")

    config = sources[source_id]
    root = Path(config["path"])
    return config, root, _enforce_source_access(source_id, config, connection, current_user)


def _resolve_child_path(root: Path, relative_path: Optional[str]) -> Path:
    normalized = _sanitize_relative_path(relative_path)
    candidate = (root / normalized) if normalized else root
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)

    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Path escapes source root") from exc

    return resolved_candidate


def _safe_stat(path: Path):
    try:
        return path.stat()
    except (OSError, PermissionError):
        return None


def _serialize_fs_item(item: Path) -> Optional[Dict[str, Any]]:
    try:
        is_dir = item.is_dir()
    except (OSError, PermissionError):
        return None

    stat_obj = None if is_dir else _safe_stat(item)
    ext = item.suffix.lower()

    payload: Dict[str, Any] = {
        "name": item.name,
        "path": str(item),
        "is_directory": is_dir,
        "extension": ext,
    }

    if not is_dir and stat_obj is not None:
        payload.update(
            {
                "size": stat_obj.st_size,
                "size_formatted": _format_file_size(stat_obj.st_size),
                "modified_timestamp": stat_obj.st_mtime,
                "modified_date": datetime.fromtimestamp(stat_obj.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return payload


def _sort_and_limit_items(items: List[Dict[str, Any]], *, search: str = "", file_type: str = "all", modified_from: Optional[date] = None, modified_to: Optional[date] = None, sort_by: str = "modified", sort_direction: str = "desc", page: int = 1, limit: int = MAX_BROWSE_ITEMS) -> Tuple[List[Dict[str, Any]], int, bool]:
    """Filter the entire current directory before paging; retain legacy 200-item defaults."""
    def matches(item):
        if search.casefold() not in item.get("name", "").casefold():
            return False
        if item.get("is_directory"):
            return True  # Keep folders reachable while narrowing file metadata.
        ext = item.get("extension", "").lower()
        if file_type == "archives" and ext not in {".zip", ".gz"}:
            return False
        if file_type == "text" and ext in {".zip", ".gz"}:
            return False
        if file_type == "traces" and ext != ".trc":
            return False
        modified = str(item.get("modified_date") or "")[:10]
        return not ((modified_from and modified < modified_from.isoformat()) or (modified_to and (not modified or modified > modified_to.isoformat())))
    filtered = [item for item in items if matches(item)]
    # Stable case-sensitive identity breaks equal names, timestamps and sizes.
    filtered.sort(key=lambda item: (item.get("name", "").casefold(), item.get("name", ""), item.get("entry_path", item.get("path", ""))))
    def key(item):
        if sort_by == "name": return item.get("name", "").casefold()
        if sort_by == "size": return item.get("size") or 0
        return item.get("modified_timestamp") or 0
    folders = sorted((item for item in filtered if item.get("is_directory")), key=lambda item: (item["name"].casefold(), item["name"]))
    files = sorted((item for item in filtered if not item.get("is_directory")), key=key, reverse=sort_direction == "desc")
    ordered = folders + files
    offset = (page - 1) * limit
    result = ordered[offset:offset + limit]
    return result, len(ordered), len(result) < len(ordered)


def _read_regular_file_preview(path: Path, max_bytes: int, manager: LogReaderManager):
    with open(path, "rb") as handle:
        sample = handle.read(64 * 1024)
        try:
            encoding = encoding_for(sample)
        except ReaderError:
            return None, True
        current = path.stat()
        fingerprint = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
        # Reuse only the same file version; a followed log may have rotated.
        with manager.lock:
            for reader in manager.readers.values():
                if reader.path == path and reader.entry is None and reader.state == "ready" and reader.fingerprint == fingerprint and reader.encoding == "cp1252":
                    encoding = reader.encoding
                    break
        if encoding in ("utf-8", "utf-8-sig"):
            # Late Windows-1252 bytes must select the same decoder as the reader.
            decoder = codecs.getincrementaldecoder(encoding)()
            handle.seek(0)
            try:
                while chunk := handle.read(64 * 1024):
                    decoder.decode(chunk, final=False)
                decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                encoding = "cp1252"
        if encoding == "utf-16":
            encoding = "utf-16-le" if sample.startswith(codecs.BOM_UTF16_LE) else "utf-16-be"
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - max_bytes)
        if encoding.startswith("utf-16"):
            start += start % 2
        handle.seek(start)
        content = handle.read(max_bytes).decode(encoding, errors="replace")
        if start:
            _, separator, content = content.partition("\n")
            if not separator:
                content = ""
        else:
            content = content.removeprefix("\ufeff")
        return content, False


def _classify_permission_error(exc: PermissionError) -> Tuple[int, str, str]:
    winerror = getattr(exc, "winerror", None)
    err_no = getattr(exc, "errno", None)

    # Windows sharing violations are the common "file is in use" case.
    if winerror in (32, 33):
        return status.HTTP_423_LOCKED, "FILE_LOCKED", "File is currently locked by another program"

    if err_no in (errno.EACCES, errno.EPERM) or winerror == 5:
        return status.HTTP_403_FORBIDDEN, "FILE_ACCESS_DENIED", "Permission denied while reading file"

    return status.HTTP_403_FORBIDDEN, "FILE_ACCESS_DENIED", "File is inaccessible"


def _normalize_zip_entry_path(entry_path: Optional[str]) -> str:
    normalized = _sanitize_relative_path(entry_path)
    return normalized


@router.get("/sources")
def list_logfile_sources(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):

    entries: List[Dict[str, Any]] = []
    for source_id, config in _get_sources(request).items():
        root = Path(config["path"])
        exists = False
        accessible = False
        error_message: Optional[str] = None

        try:
            exists = root.exists()
            accessible = exists and root.is_dir()
        except (OSError, PermissionError) as exc:
            error_message = str(exc)

        entries.append(
            {
                "id": source_id,
                "label": config["label"],
                "path": config["path"],
                "exists": exists,
                "accessible": accessible,
                "error": error_message,
                "shortcuts": [{"label": "Current logs", "relative_path": ""}, {"label": "History", "relative_path": "history"}] if source_id == "robotcontrol_logs" else [],
                "permissions": {
                    "is_local_session": connection.is_local,
                    "can_access": _enforce_source_access(source_id, config, connection, current_user) is None,
                    "access_scope": str(config.get("access_scope") or "local_only"),
                    "ip_classification": connection.ip_classification,
                    "client_ip": connection.client_ip,
                },
            }
        )

    return ResponseFormatter.success(
        data=entries,
        message="Log file sources retrieved",
    )


@router.get("/browse")
def browse_logfiles(
    request: Request,
    source_id: str = Query(..., description="Configured source identifier"),
    relative_path: str = Query("", description="Path relative to the selected source"),
    search: str = Query("", max_length=200),
    file_type: Literal["all", "text", "traces", "archives"] = Query("all"),
    modified_from: Optional[date] = Query(None),
    modified_to: Optional[date] = Query(None),
    sort_by: Literal["name", "modified", "size"] = Query("modified"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(MAX_BROWSE_ITEMS, ge=1, le=MAX_BROWSE_ITEMS),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    if modified_from and modified_to and modified_from > modified_to:
        return ResponseFormatter.bad_request(message="Modified-from date must not be later than modified-to date")

    try:
        source_config, root, access_error = _resolve_source_root(source_id, request, connection, current_user)
        target = _resolve_child_path(root, relative_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid relative path", details=str(exc))

    if access_error:
        return access_error

    if not target.exists():
        return ResponseFormatter.not_found(message="Directory not found", details={"relative_path": relative_path})
    if not target.is_dir():
        return ResponseFormatter.bad_request(message="Target path is not a directory", details={"relative_path": relative_path})

    items: List[Dict[str, Any]] = []
    try:
        for child in target.iterdir():
            if child.name.startswith("."):
                continue
            serialized = _serialize_fs_item(child)
            if serialized is not None:
                if not serialized.get("is_directory") and not _is_allowed_file_for_source(source_config, child):
                    continue
                items.append(serialized)
    except PermissionError:
        return ResponseFormatter.forbidden(message="Permission denied while browsing directory", details={"relative_path": relative_path})
    except OSError as exc:
        return ResponseFormatter.server_error(message="Failed to browse directory", details=str(exc))

    items, total_items, truncated = _sort_and_limit_items(items, search=search, file_type=file_type, modified_from=modified_from, modified_to=modified_to, sort_by=sort_by, sort_direction=sort_direction, page=page, limit=limit)

    return ResponseFormatter.success(
        data={"items": items, "total_items": total_items},
        message="Log directory listed",
    )


@router.get("/preview")
def preview_logfile(
    request: Request,
    source_id: str = Query(..., description="Configured source identifier"),
    relative_path: str = Query(..., description="File path relative to source"),
    max_bytes: int = Query(MAX_PREVIEW_BYTES, ge=1, le=MAX_PREVIEW_BYTES, description="Max preview bytes"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):

    try:
        source_config, root, access_error = _resolve_source_root(source_id, request, connection, current_user)
        target = _resolve_child_path(root, relative_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid relative path", details=str(exc))

    if access_error:
        return access_error

    if not target.exists():
        return ResponseFormatter.not_found(message="File not found", details={"relative_path": relative_path})
    if not target.is_file():
        return ResponseFormatter.bad_request(message="Target path is not a file", details={"relative_path": relative_path})
    if not _is_allowed_file_for_source(source_config, target):
        return ResponseFormatter.bad_request(
            message="This file type is not enabled for the selected log source",
            details={"relative_path": relative_path, "allowed_extensions": sorted(_get_allowed_extensions_for_source(source_config) or [])},
        )

    try:
        if target.suffix.lower() in {".zip", ".gz"}:
            return ResponseFormatter.bad_request(message="open compressed files in the reader")
        content, is_binary = _read_regular_file_preview(target, max_bytes, _reader_manager(request))
        stat_obj = _safe_stat(target)
        payload = {
            "content": content, "is_binary": is_binary, "file_path": str(target),
            "modified_date": datetime.fromtimestamp(stat_obj.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat_obj else None,
        }
    except PermissionError as exc:
        status_code, error_code, message = _classify_permission_error(exc)
        return ResponseFormatter.error(
            message=message,
            error_code=error_code,
            details={
                "relative_path": relative_path,
                "winerror": getattr(exc, "winerror", None),
                "errno": getattr(exc, "errno", None),
            },
            status_code=status_code,
        )
    except OSError as exc:
        logger.warning("Failed to preview file %s: %s", target, exc)
        return ResponseFormatter.server_error(message="Failed to preview log file", details=str(exc))

    return ResponseFormatter.success(
        data=payload,
        message="Log file preview generated",
    )


@router.get("/archive/browse")
def browse_archive_entries(
    request: Request,
    source_id: str = Query(...),
    archive_relative_path: str = Query(..., description="ZIP archive path relative to source"),
    entry_path: str = Query("", description="Directory path inside archive"),
    search: str = Query("", max_length=200),
    file_type: Literal["all", "text", "traces", "archives"] = Query("all"),
    modified_from: Optional[date] = Query(None),
    modified_to: Optional[date] = Query(None),
    sort_by: Literal["name", "modified", "size"] = Query("modified"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(MAX_BROWSE_ITEMS, ge=1, le=MAX_BROWSE_ITEMS),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    if modified_from and modified_to and modified_from > modified_to:
        return ResponseFormatter.bad_request(message="Modified-from date must not be later than modified-to date")

    try:
        source_config, root, access_error = _resolve_source_root(source_id, request, connection, current_user)
        archive_path = _resolve_child_path(root, archive_relative_path)
        normalized_entry_path = _normalize_zip_entry_path(entry_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid path", details=str(exc))

    if access_error:
        return access_error

    if not _is_allowed_file_for_source(source_config, archive_path):
        return ResponseFormatter.bad_request(message="This archive type is not enabled for the selected log source")
    if not archive_path.exists() or not archive_path.is_file():
        return ResponseFormatter.not_found(message="Archive not found", details={"archive_relative_path": archive_relative_path})
    if archive_path.suffix.lower() != ".zip":
        return ResponseFormatter.bad_request(message="Archive browse only supports .zip files")

    prefix = f"{normalized_entry_path}/" if normalized_entry_path else ""
    children: Dict[str, Dict[str, Any]] = {}

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if not name or name == prefix.rstrip("/"):
                    continue
                if prefix and not name.startswith(prefix):
                    continue
                rest = name[len(prefix):] if prefix else name
                if not rest:
                    continue

                parts = [part for part in rest.split("/") if part]
                if not parts:
                    continue

                first = parts[0]
                child_key = first
                child_is_dir = len(parts) > 1 or info.is_dir() or name.endswith("/")

                existing = children.get(child_key)
                if existing and existing["is_directory"]:
                    continue
                if existing and not existing["is_directory"] and not child_is_dir:
                    continue

                child_entry_path = f"{normalized_entry_path}/{child_key}" if normalized_entry_path else child_key
                payload: Dict[str, Any] = {
                    "name": child_key,
                    "entry_path": child_entry_path,
                    "is_directory": child_is_dir,
                    "extension": Path(child_key).suffix.lower() if not child_is_dir else "",
                }

                if not child_is_dir:
                    payload.update(
                        {
                            "size": info.file_size,
                            "size_formatted": _format_file_size(info.file_size),
                            "modified_timestamp": datetime(*info.date_time).timestamp(),
                            "modified_date": datetime(*info.date_time).strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                children[child_key] = payload
    except PermissionError as exc:
        status_code, error_code, message = _classify_permission_error(exc)
        return ResponseFormatter.error(
            message=message,
            error_code=error_code,
            details={
                "archive_relative_path": archive_relative_path,
                "winerror": getattr(exc, "winerror", None),
                "errno": getattr(exc, "errno", None),
            },
            status_code=status_code,
        )
    except zipfile.BadZipFile as exc:
        return ResponseFormatter.bad_request(message="Invalid zip archive", details=str(exc))
    except OSError as exc:
        return ResponseFormatter.server_error(message="Failed to read archive", details=str(exc))

    items, total_items, truncated = _sort_and_limit_items(list(children.values()), search=search, file_type=file_type, modified_from=modified_from, modified_to=modified_to, sort_by=sort_by, sort_direction=sort_direction, page=page, limit=limit)

    return ResponseFormatter.success(
        data={"items": items, "total_items": total_items},
        message="Archive entries listed",
    )
