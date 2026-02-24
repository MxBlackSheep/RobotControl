"""
Log file review API endpoints.

Provides a restricted, read-only browser and previewer for a fixed allowlist of
log directories. Supports plain text files plus gzip/zip archive previews.
"""

from __future__ import annotations

import gzip
import logging
import time
import zipfile
from collections import deque
from datetime import datetime
import errno
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Deque, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Query, status

from backend.api.dependencies import ConnectionContext, get_connection_context
from backend.api.response_formatter import ResponseFormatter, ResponseMetadata
from backend.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logfiles", tags=["logfiles"])

MAX_PREVIEW_BYTES = 1024 * 1024
MAX_BROWSE_ITEMS = 200
PREVIEW_MODES = {"head", "tail"}

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
        "path": r"C:\Users\Hamilton\Desktop\RobotControl\data\logs",
        "access_scope": "local_only",
    },
}


def _format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _path_to_str(path: Path) -> str:
    return str(path)


def _get_sources() -> Dict[str, Dict[str, Any]]:
    return {source_id: dict(config) for source_id, config in LOGFILE_SOURCES.items()}


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


def _enforce_source_access(source_id: str, source_config: Dict[str, Any], connection: ConnectionContext):
    access_scope = str(source_config.get("access_scope") or "local_only")
    if access_scope == "all_authenticated":
        return None
    if access_scope == "local_only" and connection.is_local:
        return None
    return ResponseFormatter.forbidden(
        message="Local access required for this log source",
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


def _resolve_source_root(source_id: str) -> Tuple[Dict[str, Any], Path]:
    sources = _get_sources()
    if source_id not in sources:
        raise KeyError(f"Unknown source_id '{source_id}'")

    config = sources[source_id]
    root = Path(config["path"])
    return config, root


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
    is_archive = ext in {".gz", ".zip"}

    payload: Dict[str, Any] = {
        "name": item.name,
        "path": _path_to_str(item),
        "is_directory": is_dir,
        "extension": ext,
        "is_archive": is_archive,
        "archive_type": ext[1:] if is_archive else None,
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


def _sort_and_limit_items(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, bool]:
    def _sort_key(item: Dict[str, Any]):
        if item.get("is_directory"):
            return (0, item.get("name", "").lower())
        modified_ts = float(item.get("modified_timestamp") or 0.0)
        # Files: newest first, then name
        return (1, -modified_ts, item.get("name", "").lower())

    items.sort(key=_sort_key)
    total_items = len(items)
    truncated = total_items > MAX_BROWSE_ITEMS
    visible_items = items[:MAX_BROWSE_ITEMS]

    for item in visible_items:
        item.pop("modified_timestamp", None)

    return visible_items, total_items, truncated


def _looks_binary(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    if b"\x00" in sample:
        return True
    control_count = sum(1 for byte in sample if byte < 9 or (13 < byte < 32))
    return (control_count / len(sample)) > 0.2


def _text_quality_score(text: str) -> float:
    if not text:
        return 1.0
    good = 0
    bad = 0
    line_breaks = 0
    replacements = 0
    for char in text[:8000]:
        if char == "\ufffd":
            replacements += 1
            bad += 1
            continue
        if char in ("\n", "\r", "\t"):
            good += 1
            if char in ("\n", "\r"):
                line_breaks += 1
            continue
        if char.isprintable():
            good += 1
        else:
            bad += 1

    total = max(1, good + bad)
    score = good / total
    if line_breaks:
        score += 0.05
    if replacements:
        score -= min(0.15, replacements / total)
    return score


def _decode_preview(data: bytes) -> Tuple[Optional[str], Optional[str], bool]:
    if not data:
        return "", "utf-8", False

    sample = data[:4096]
    null_ratio = sample.count(b"\x00") / max(1, len(sample))
    utf16_likely = null_ratio > 0.08

    candidates: List[Tuple[float, str, str, bool]] = []

    def _try_decode(encoding: str, *, offset: int = 0, errors: str = "strict") -> None:
        if offset >= len(data):
            return
        try:
            text = data[offset:].decode(encoding, errors=errors)
        except UnicodeDecodeError:
            return
        score = _text_quality_score(text)
        if errors == "strict":
            score += 0.03
        if offset:
            score -= 0.01
        candidates.append((score, text, f"{encoding}{'+1' if offset else ''}{'-replace' if errors != 'strict' else ''}", errors == "strict"))

    if utf16_likely:
        preferred = ["utf-16-le", "utf-16-be", "utf-16"]
        fallback = ["utf-8", "cp1252", "latin-1"]
    else:
        preferred = ["utf-8", "cp1252", "latin-1"]
        fallback = ["utf-16-le", "utf-16-be", "utf-16"]

    for encoding in preferred + fallback:
        _try_decode(encoding, errors="strict")
        if encoding.startswith("utf-16"):
            _try_decode(encoding, offset=1, errors="strict")

    if not candidates:
        for encoding in preferred + fallback:
            _try_decode(encoding, errors="replace")
            if encoding.startswith("utf-16"):
                _try_decode(encoding, offset=1, errors="replace")

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_text, best_encoding, _ = candidates[0]
        if best_score >= 0.45 or not _looks_binary(data):
            return best_text, best_encoding, False

    return None, None, True


def _read_stream_head(stream: BinaryIO, max_bytes: int) -> Tuple[bytes, bool, int]:
    raw = stream.read(max_bytes + 1)
    total_read = len(raw)
    if len(raw) > max_bytes:
        return raw[:max_bytes], True, total_read
    return raw, False, total_read


def _read_stream_tail(stream: BinaryIO, max_bytes: int, chunk_size: int = 64 * 1024) -> Tuple[bytes, bool, int]:
    chunks: Deque[bytes] = deque()
    kept_bytes = 0
    total_read = 0

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        chunks.append(chunk)
        kept_bytes += len(chunk)
        while kept_bytes > max_bytes and chunks:
            overflow = kept_bytes - max_bytes
            first = chunks[0]
            if len(first) <= overflow:
                chunks.popleft()
                kept_bytes -= len(first)
            else:
                chunks[0] = first[overflow:]
                kept_bytes -= overflow

    return b"".join(chunks), total_read > max_bytes, total_read


def _read_regular_file_preview(path: Path, mode: Literal["head", "tail"], max_bytes: int) -> Tuple[bytes, bool, int]:
    with open(path, "rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(0)
        if mode == "head":
            data = handle.read(max_bytes)
            return data, size > max_bytes, min(size, max_bytes)

        if size <= max_bytes:
            return handle.read(), False, size

        # Read a small overlap before the tail window so UTF-16-like files have a
        # better chance of decoding cleanly when the tail starts mid-character.
        overlap = min(8192, max(512, max_bytes // 64))
        start = max(0, size - (max_bytes + overlap))
        handle.seek(start)
        return handle.read(size - start), True, min(size, max_bytes + overlap)


def _classify_permission_error(exc: PermissionError) -> Tuple[int, str, str]:
    winerror = getattr(exc, "winerror", None)
    err_no = getattr(exc, "errno", None)

    # Windows sharing violations are the common "file is in use" case.
    if winerror in (32, 33):
        return status.HTTP_423_LOCKED, "FILE_LOCKED", "File is currently locked by another program"

    if err_no in (errno.EACCES, errno.EPERM) or winerror == 5:
        return status.HTTP_403_FORBIDDEN, "FILE_ACCESS_DENIED", "Permission denied while reading file"

    return status.HTTP_403_FORBIDDEN, "FILE_ACCESS_DENIED", "File is inaccessible"


def _read_gzip_preview(path: Path, mode: Literal["head", "tail"], max_bytes: int) -> Tuple[bytes, bool, int]:
    with gzip.open(path, "rb") as gz:
        if mode == "head":
            return _read_stream_head(gz, max_bytes)
        return _read_stream_tail(gz, max_bytes)


def _normalize_zip_entry_path(entry_path: Optional[str]) -> str:
    normalized = _sanitize_relative_path(entry_path)
    return normalized


def _read_zip_entry_preview(
    archive_path: Path,
    entry_path: str,
    mode: Literal["head", "tail"],
    max_bytes: int,
) -> Tuple[bytes, bool, int, zipfile.ZipInfo]:
    with zipfile.ZipFile(archive_path, "r") as zf:
        try:
            info = zf.getinfo(entry_path)
        except KeyError as exc:
            raise FileNotFoundError(f"Archive entry not found: {entry_path}") from exc

        if info.is_dir():
            raise IsADirectoryError(f"Archive entry is a directory: {entry_path}")

        with zf.open(info, "r") as handle:
            if mode == "head":
                data, truncated, total_read = _read_stream_head(handle, max_bytes)
            else:
                data, truncated, total_read = _read_stream_tail(handle, max_bytes)
        return data, truncated, total_read, info


def _build_preview_response(
    *,
    source_id: str,
    source_label: str,
    file_path: str,
    display_name: str,
    mode: Literal["head", "tail"],
    max_bytes: int,
    raw_bytes: bytes,
    truncated: bool,
    total_bytes_read: int,
    file_locked: bool = False,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    content, encoding_used, is_binary = _decode_preview(raw_bytes)
    payload: Dict[str, Any] = {
        "source_id": source_id,
        "source_label": source_label,
        "file_path": file_path,
        "display_name": display_name,
        "mode": mode,
        "max_bytes": max_bytes,
        "bytes_returned": len(raw_bytes),
        "bytes_scanned": total_bytes_read,
        "truncated": truncated,
        "encoding_used": encoding_used,
        "is_binary": is_binary,
        "file_locked": file_locked,
        "content": None if is_binary else content,
    }
    if extra_metadata:
        payload.update(extra_metadata)
    return payload


def _response_metadata(start_time: float, operation: str, current_user: Dict[str, Any], **extras: Any) -> ResponseMetadata:
    metadata = ResponseMetadata()
    metadata.set_execution_time(start_time)
    metadata.add_metadata("operation", operation)
    metadata.add_metadata("user_id", current_user.get("user_id"))
    for key, value in extras.items():
        metadata.add_metadata(key, value)
    return metadata


@router.get("/sources")
async def list_logfile_sources(
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    start_time = time.time()

    entries: List[Dict[str, Any]] = []
    for source_id, config in _get_sources().items():
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
                "permissions": {
                    "is_local_session": connection.is_local,
                    "can_access": (
                        str(config.get("access_scope") or "local_only") == "all_authenticated"
                        or connection.is_local
                    ),
                    "access_scope": str(config.get("access_scope") or "local_only"),
                    "ip_classification": connection.ip_classification,
                    "client_ip": connection.client_ip,
                },
            }
        )

    return ResponseFormatter.success(
        data=entries,
        metadata=_response_metadata(start_time, "logfiles_sources", current_user, source_count=len(entries)),
        message="Log file sources retrieved",
    )


@router.get("/browse")
async def browse_logfiles(
    source_id: str = Query(..., description="Configured source identifier"),
    relative_path: str = Query("", description="Path relative to the selected source"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    start_time = time.time()

    try:
        source_config, root = _resolve_source_root(source_id)
        target = _resolve_child_path(root, relative_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid relative path", details=str(exc))

    access_error = _enforce_source_access(source_id, source_config, connection)
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

    items, total_items, truncated = _sort_and_limit_items(items)

    relative_current = ""
    try:
        relative_current = target.relative_to(root.resolve(strict=False)).as_posix()  # type: ignore[assignment]
    except Exception:
        relative_current = _sanitize_relative_path(relative_path)

    return ResponseFormatter.success(
        data={
            "source": {
                "id": source_id,
                "label": source_config["label"],
                "path": source_config["path"],
            },
            "current_path": _path_to_str(target),
            "relative_path": relative_current,
            "items": items,
            "total_items": total_items,
            "returned_items": len(items),
            "truncated": truncated,
            "max_items": MAX_BROWSE_ITEMS,
        },
        metadata=_response_metadata(
            start_time,
            "logfiles_browse",
            current_user,
            source_id=source_id,
            relative_path=relative_current,
            item_count=total_items,
            returned_items=len(items),
            truncated=truncated,
            max_items=MAX_BROWSE_ITEMS,
        ),
        message="Log directory listed",
    )


@router.get("/preview")
async def preview_logfile(
    source_id: str = Query(..., description="Configured source identifier"),
    relative_path: str = Query(..., description="File path relative to source"),
    mode: str = Query("tail", description="Preview mode: head or tail"),
    max_bytes: int = Query(MAX_PREVIEW_BYTES, ge=1, le=MAX_PREVIEW_BYTES, description="Max preview bytes"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    start_time = time.time()

    if mode not in PREVIEW_MODES:
        return ResponseFormatter.bad_request(message="Invalid preview mode", details={"mode": mode, "allowed": sorted(PREVIEW_MODES)})

    try:
        source_config, root = _resolve_source_root(source_id)
        target = _resolve_child_path(root, relative_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid relative path", details=str(exc))

    access_error = _enforce_source_access(source_id, source_config, connection)
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

    lowered = target.name.lower()
    try:
        if lowered.endswith(".zip"):
            return ResponseFormatter.bad_request(
                message="ZIP archives require archive browse/preview endpoints",
                details={"relative_path": relative_path},
            )

        if lowered.endswith(".gz"):
            raw, truncated, total_read = _read_gzip_preview(target, mode, max_bytes)  # type: ignore[arg-type]
            payload = _build_preview_response(
                source_id=source_id,
                source_label=source_config["label"],
                file_path=_path_to_str(target),
                display_name=target.name,
                mode=mode,  # type: ignore[arg-type]
                max_bytes=max_bytes,
                raw_bytes=raw,
                truncated=truncated,
                total_bytes_read=total_read,
                extra_metadata={"compressed": True, "archive_type": "gz"},
            )
        else:
            raw, truncated, total_read = _read_regular_file_preview(target, mode, max_bytes)  # type: ignore[arg-type]
            stat_obj = _safe_stat(target)
            payload = _build_preview_response(
                source_id=source_id,
                source_label=source_config["label"],
                file_path=_path_to_str(target),
                display_name=target.name,
                mode=mode,  # type: ignore[arg-type]
                max_bytes=max_bytes,
                raw_bytes=raw,
                truncated=truncated,
                total_bytes_read=total_read,
                extra_metadata={
                    "compressed": False,
                    **(
                        {
                            "file_size": stat_obj.st_size,
                            "file_size_formatted": _format_file_size(stat_obj.st_size),
                            "modified_date": datetime.fromtimestamp(stat_obj.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        if stat_obj is not None
                        else {}
                    ),
                },
            )
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
    except gzip.BadGzipFile as exc:
        return ResponseFormatter.bad_request(message="Invalid gzip file", details=str(exc))
    except OSError as exc:
        logger.warning("Failed to preview file %s: %s", target, exc)
        return ResponseFormatter.server_error(message="Failed to preview log file", details=str(exc))

    return ResponseFormatter.success(
        data=payload,
        metadata=_response_metadata(start_time, "logfiles_preview", current_user, source_id=source_id, relative_path=relative_path),
        message="Log file preview generated",
    )


@router.get("/archive/browse")
async def browse_archive_entries(
    source_id: str = Query(...),
    archive_relative_path: str = Query(..., description="ZIP archive path relative to source"),
    entry_path: str = Query("", description="Directory path inside archive"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    start_time = time.time()

    try:
        source_config, root = _resolve_source_root(source_id)
        archive_path = _resolve_child_path(root, archive_relative_path)
        normalized_entry_path = _normalize_zip_entry_path(entry_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid path", details=str(exc))

    access_error = _enforce_source_access(source_id, source_config, connection)
    if access_error:
        return access_error

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
                    "is_archive": (Path(child_key).suffix.lower() in {".gz", ".zip"}) if not child_is_dir else False,
                }

                if not child_is_dir:
                    payload.update(
                        {
                            "size": info.file_size,
                            "size_formatted": _format_file_size(info.file_size),
                            "compressed_size": info.compress_size,
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

    items, total_items, truncated = _sort_and_limit_items(list(children.values()))

    return ResponseFormatter.success(
        data={
            "source": {
                "id": source_id,
                "label": source_config["label"],
                "path": source_config["path"],
            },
            "archive": {
                "relative_path": _sanitize_relative_path(archive_relative_path),
                "path": _path_to_str(archive_path),
                "name": archive_path.name,
            },
            "entry_path": normalized_entry_path,
            "items": items,
            "total_items": total_items,
            "returned_items": len(items),
            "truncated": truncated,
            "max_items": MAX_BROWSE_ITEMS,
        },
        metadata=_response_metadata(
            start_time,
            "logfiles_archive_browse",
            current_user,
            source_id=source_id,
            archive_relative_path=archive_relative_path,
            entry_path=normalized_entry_path,
            item_count=total_items,
            returned_items=len(items),
            truncated=truncated,
            max_items=MAX_BROWSE_ITEMS,
        ),
        message="Archive entries listed",
    )


@router.get("/archive/preview")
async def preview_archive_entry(
    source_id: str = Query(...),
    archive_relative_path: str = Query(..., description="ZIP archive path relative to source"),
    entry_path: str = Query(..., description="File path inside zip archive"),
    mode: str = Query("tail"),
    max_bytes: int = Query(MAX_PREVIEW_BYTES, ge=1, le=MAX_PREVIEW_BYTES),
    current_user: Dict[str, Any] = Depends(get_current_user),
    connection: ConnectionContext = Depends(get_connection_context),
):
    start_time = time.time()

    if mode not in PREVIEW_MODES:
        return ResponseFormatter.bad_request(message="Invalid preview mode", details={"mode": mode, "allowed": sorted(PREVIEW_MODES)})

    try:
        source_config, root = _resolve_source_root(source_id)
        archive_path = _resolve_child_path(root, archive_relative_path)
        normalized_entry_path = _normalize_zip_entry_path(entry_path)
    except KeyError:
        return ResponseFormatter.not_found(message="Unknown log source", details={"source_id": source_id})
    except ValueError as exc:
        return ResponseFormatter.bad_request(message="Invalid path", details=str(exc))

    access_error = _enforce_source_access(source_id, source_config, connection)
    if access_error:
        return access_error

    if not archive_path.exists() or not archive_path.is_file():
        return ResponseFormatter.not_found(message="Archive not found", details={"archive_relative_path": archive_relative_path})
    if archive_path.suffix.lower() != ".zip":
        return ResponseFormatter.bad_request(message="Archive preview only supports .zip files")

    try:
        raw, truncated, total_read, info = _read_zip_entry_preview(
            archive_path,
            normalized_entry_path,
            mode,  # type: ignore[arg-type]
            max_bytes,
        )
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
    except FileNotFoundError:
        return ResponseFormatter.not_found(message="Archive entry not found", details={"entry_path": normalized_entry_path})
    except IsADirectoryError:
        return ResponseFormatter.bad_request(message="Archive entry is a directory", details={"entry_path": normalized_entry_path})
    except zipfile.BadZipFile as exc:
        return ResponseFormatter.bad_request(message="Invalid zip archive", details=str(exc))
    except OSError as exc:
        return ResponseFormatter.server_error(message="Failed to preview archive entry", details=str(exc))

    payload = _build_preview_response(
        source_id=source_id,
        source_label=source_config["label"],
        file_path=f"{_path_to_str(archive_path)}::{normalized_entry_path}",
        display_name=Path(normalized_entry_path).name or normalized_entry_path,
        mode=mode,  # type: ignore[arg-type]
        max_bytes=max_bytes,
        raw_bytes=raw,
        truncated=truncated,
        total_bytes_read=total_read,
        extra_metadata={
            "compressed": True,
            "archive_type": "zip",
            "archive_relative_path": _sanitize_relative_path(archive_relative_path),
            "entry_path": normalized_entry_path,
            "entry_size": info.file_size,
            "entry_size_formatted": _format_file_size(info.file_size),
            "entry_compressed_size": info.compress_size,
            "modified_date": datetime(*info.date_time).strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

    return ResponseFormatter.success(
        data=payload,
        metadata=_response_metadata(
            start_time,
            "logfiles_archive_preview",
            current_user,
            source_id=source_id,
            archive_relative_path=archive_relative_path,
            entry_path=normalized_entry_path,
        ),
        message="Archive entry preview generated",
    )
