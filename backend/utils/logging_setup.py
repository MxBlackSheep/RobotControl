"""Utilities for configuring backend logging."""

from __future__ import annotations

import gzip
import logging
import logging.handlers
import os
import re
import shutil
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


logger = logging.getLogger(__name__)


execution_id_context = ContextVar("execution_id", default="")


@contextmanager
def run_log_context(execution_id: str):
    token = execution_id_context.set(execution_id)
    try:
        yield
    finally:
        execution_id_context.reset(token)


class RunLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        execution_id = execution_id_context.get()
        record.run_tag = f" | run={execution_id[:8]}" if execution_id else ""
        return True


class ImmediateFlushStreamHandler(logging.StreamHandler):
    """Stream handler that flushes immediately after each emit."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - passthrough logic
        super().emit(record)
        self.flush()


class ImmediateGZipTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotating handler that gzips rotated files, flushes immediately, and keeps history without expiration."""

    def __init__(
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        encoding: Optional[str] = "utf-8",
        delay: bool = False,
        utc: bool = False,
        atTime: Optional[time.struct_time] = None,
        *,
        history_dir: Optional[Path] = None,
    ) -> None:
        self._history_dir = Path(history_dir) if history_dir else None
        if self._history_dir:
            try:
                self._history_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("Unable to create log history directory %s: %s", self._history_dir, exc)
                self._history_dir = None
        super().__init__(
            filename,
            when=when,
            interval=interval,
            backupCount=0,
            encoding=encoding,
            delay=delay,
            utc=utc,
            atTime=atTime,
        )
        self._configure_compression()

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - passthrough logic
        super().emit(record)
        self.flush()

    def _configure_compression(self) -> None:
        self.namer = self._compressed_namer
        self.suffix = "%Y-%m-%d"

        def _rotator(source: str, dest: str) -> None:
            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(source, "rb") as src, gzip.open(dest_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.remove(source)

        self.rotator = _rotator
        if self.extMatch:
            pattern = self.extMatch.pattern
            if pattern.endswith("$"):
                pattern = pattern[:-1]
            if not pattern.endswith(r"(?:\.gz)?"):
                pattern = f"{pattern}(?:\\.gz)?"
            self.extMatch = re.compile(f"{pattern}$")

    def _compressed_namer(self, name: str) -> str:
        """Rename rotated files to include gzip suffix and align with alias naming."""
        base_path = Path(self.baseFilename)
        rotated = Path(name)
        target_dir = self._history_dir or base_path.parent
        timestamp = rotated.name[len(base_path.name) + 1 :] if rotated.name.startswith(base_path.name + ".") else rotated.suffix.lstrip('.')
        alias_friendly = f"{base_path.stem}_{timestamp}{base_path.suffix}" if timestamp else rotated.name
        final_path = target_dir / alias_friendly
        if final_path.suffix != base_path.suffix:
            final_path = final_path.with_suffix(base_path.suffix)
        compressed = final_path.with_suffix(final_path.suffix + ".gz")
        return str(compressed)


@dataclass(frozen=True)
class LoggingHandlers:
    console: logging.Handler
    application: ImmediateGZipTimedRotatingFileHandler
    error: ImmediateGZipTimedRotatingFileHandler

    @property
    def files(self) -> Dict[str, Path]:
        result: Dict[str, Path] = {}
        app_base = getattr(self.application, "baseFilename", None)
        if app_base:
            result["application"] = Path(app_base)
        error_base = getattr(self.error, "baseFilename", None)
        if error_base:
            result["error"] = Path(error_base)
        return result


DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s%(run_tag)s"


def setup_logging(
    logs_dir: Path,
    *,
    log_level: int = logging.INFO,
    console_level: Optional[int] = None,
) -> LoggingHandlers:
    logs_dir.mkdir(parents=True, exist_ok=True)
    history_dir = logs_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    console_handler = ImmediateFlushStreamHandler()
    console_handler_level = console_level if console_level is not None else log_level
    console_handler.setLevel(console_handler_level)
    console_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))

    formatter = logging.Formatter(DEFAULT_FORMAT)

    app_handler = ImmediateGZipTimedRotatingFileHandler(
        filename=str(logs_dir / "robotcontrol_backend.log"),
        when="midnight",
        encoding="utf-8",
        history_dir=history_dir,
    )
    app_handler.setLevel(log_level)
    app_handler.setFormatter(formatter)

    error_handler = ImmediateGZipTimedRotatingFileHandler(
        filename=str(logs_dir / "robotcontrol_backend_error.log"),
        when="midnight",
        encoding="utf-8",
        history_dir=history_dir,
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)

    run_filter = RunLogFilter()
    for handler in (console_handler, app_handler, error_handler):
        handler.addFilter(run_filter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)

    logging.captureWarnings(True)

    keep_paths = {
        Path(app_handler.baseFilename),
        Path(error_handler.baseFilename),
    }
    _relocate_historical_logs(logs_dir, history_dir, keep_paths)

    return LoggingHandlers(
        console=console_handler,
        application=app_handler,
        error=error_handler,
    )


def _relocate_historical_logs(logs_dir: Path, history_dir: Path, keep: Iterable[Path]) -> None:
    """Move historical log artifacts into the history directory so the root stays tidy."""
    try:
        keep_resolved = {path.resolve() for path in keep if path}
    except Exception:
        keep_resolved = {path for path in keep if path}

    dated_pattern = re.compile(r".*_\\d{4}-\\d{2}-\\d{2}\\.log(?:\\.gz)?$", re.IGNORECASE)

    for entry in logs_dir.iterdir():
        if not entry.is_file():
            continue
        try:
            resolved = entry.resolve()
        except OSError:
            resolved = entry
        if resolved in keep_resolved:
            continue

        name = entry.name
        is_dated_log = bool(dated_pattern.match(name))
        is_gzip_archive = name.endswith(".log.gz")
        if not (is_dated_log or is_gzip_archive):
            continue

        destination = history_dir / name
        suffixes = "".join(entry.suffixes)
        counter = 1
        while destination.exists():
            destination = history_dir / f"{entry.stem}-{counter}{suffixes}"
            counter += 1

        try:
            entry.replace(destination)
        except Exception as exc:
            logger.warning("Failed to move historical log %s to %s: %s", entry, destination, exc)


__all__ = [
    "ImmediateFlushStreamHandler",
    "ImmediateGZipTimedRotatingFileHandler",
    "LoggingHandlers",
    "setup_logging",
]
