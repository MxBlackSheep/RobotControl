"""Utilities for configuring backend logging."""

from __future__ import annotations

import gzip
import json
import logging
import logging.handlers
import os
import re
import shutil
import threading
from datetime import datetime
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


class ImmediateFlushStreamHandler(logging.StreamHandler):
    """Stream handler that flushes immediately after each emit."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - passthrough logic
        super().emit(record)
        self.flush()


class ImmediateGZipTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotating handler that gzips rotated files, flushes immediately, and maintains daily aliases."""

    def __init__(
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backupCount: int = 7,
        encoding: Optional[str] = "utf-8",
        delay: bool = False,
        utc: bool = False,
        atTime: Optional[time.struct_time] = None,
        *,
        daily_alias: bool = True,
        alias_format: str = "%Y-%m-%d",
    ) -> None:
        self._alias_enabled = daily_alias
        self._alias_format = alias_format
        self.alias_path: Optional[Path] = None
        super().__init__(
            filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            utc=utc,
            atTime=atTime,
        )
        self._configure_compression()
        if self._alias_enabled:
            self._update_daily_alias()

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - passthrough logic
        super().emit(record)
        self.flush()
        if self._alias_enabled:
            self._ensure_alias_current()

    def _configure_compression(self) -> None:
        self.namer = self._compressed_namer
        self.suffix = "%Y-%m-%d"

        def _rotator(source: str, dest: str) -> None:
            with open(source, "rb") as src, gzip.open(dest, "wb") as dst:
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
        timestamp = rotated.name[len(base_path.name) + 1 :] if rotated.name.startswith(base_path.name + ".") else rotated.suffix.lstrip('.')
        alias_friendly = f"{base_path.stem}_{timestamp}{base_path.suffix}" if timestamp else rotated.name
        final_path = rotated.parent / alias_friendly
        if final_path.suffix != base_path.suffix:
            final_path = final_path.with_suffix(base_path.suffix)
        compressed = final_path.with_suffix(final_path.suffix + ".gz")
        return str(compressed)

    def doRollover(self) -> None:
        super().doRollover()
        if self._alias_enabled:
            self._update_daily_alias()

    def _ensure_alias_current(self) -> None:
        """Ensure the alias matches the active base file."""
        if not self._alias_enabled:
            return
        try:
            current_alias = self.alias_path
            expected_alias = self._alias_path_for(datetime.now())
            if current_alias and current_alias.exists() and current_alias == expected_alias:
                return
        except Exception:
            pass
        self._update_daily_alias()

    def _alias_path_for(self, when: Optional[datetime] = None) -> Path:
        base_path = Path(self.baseFilename)
        timestamp = (when or datetime.now()).strftime(self._alias_format)
        alias_name = f"{base_path.stem}_{timestamp}{base_path.suffix}"
        return base_path.with_name(alias_name)

    def _update_daily_alias(self) -> None:
        if not self._alias_enabled:
            return
        base_path = Path(self.baseFilename)
        alias_path = self._alias_path_for()
        if alias_path == base_path:
            # Alias would collide with base file name; disable aliasing
            self._alias_enabled = False
            self.alias_path = None
            return
        try:
            if alias_path.exists():
                try:
                    if os.path.samefile(alias_path, base_path):
                        self.alias_path = alias_path
                        return
                except (OSError, FileNotFoundError):
                    pass
                try:
                    alias_path.unlink()
                except OSError:
                    pass
            os.link(base_path, alias_path)
            self.alias_path = alias_path
        except OSError:
            # Hard link unavailable (e.g., cross-device or permissions). Create informational stub once.
            try:
                with open(alias_path, "w", encoding="utf-8") as stub:
                    stub.write(f"Log writes are stored in {base_path.name}. Alias creation is not supported on this platform.\n")
            except Exception:
                pass
            self._alias_enabled = False
            self.alias_path = alias_path


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logging outputs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        if hasattr(record, "request_id"):
            payload["request_id"] = getattr(record, "request_id")
        if hasattr(record, "request_context"):
            payload["request_context"] = getattr(record, "request_context")
        return json.dumps(payload, ensure_ascii=False)


class RateLimitingFilter(logging.Filter):
    """Suppress repeated messages within a configurable interval."""

    def __init__(self, interval_seconds: float, *, exempt_level: int = logging.WARNING) -> None:
        super().__init__()
        self.interval = max(interval_seconds, 0.0)
        self.exempt_level = exempt_level
        self._state: Dict[tuple[str, str], tuple[float, int]] = {}
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - relies on runtime behaviour
        if self.interval <= 0:
            return True
        if record.levelno >= self.exempt_level:
            return True

        key = (record.name, record.msg if isinstance(record.msg, str) else str(record.msg))
        now = time.monotonic()
        with self._lock:
            last_state = self._state.get(key)
            if last_state is None:
                self._state[key] = (now, 0)
                return True

            last_emit, suppressed = last_state
            if now - last_emit >= self.interval:
                if suppressed:
                    formatted = record.getMessage()
                    record.msg = f"{formatted} (suppressed {suppressed} similar messages in {int(self.interval)}s)"
                    record.args = ()
                self._state[key] = (now, 0)
                return True

            self._state[key] = (last_emit, suppressed + 1)
            return False


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
        if getattr(self.application, "alias_path", None):
            result["application_alias"] = Path(self.application.alias_path)
        error_base = getattr(self.error, "baseFilename", None)
        if error_base:
            result["error"] = Path(error_base)
        if getattr(self.error, "alias_path", None):
            result["error_alias"] = Path(self.error.alias_path)
        return result


DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(
    logs_dir: Path,
    *,
    log_level: int = logging.INFO,
    retention_days: int = 14,
    error_retention_days: int = 30,
    use_json: bool = False,
    console_level: Optional[int] = None,
) -> LoggingHandlers:
    logs_dir.mkdir(parents=True, exist_ok=True)

    console_handler = ImmediateFlushStreamHandler()
    console_handler_level = console_level if console_level is not None else log_level
    console_handler.setLevel(console_handler_level)
    console_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))

    formatter: logging.Formatter
    if use_json:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(DEFAULT_FORMAT)

    app_handler = ImmediateGZipTimedRotatingFileHandler(
        filename=str(logs_dir / "pyrobot_backend.log"),
        when="midnight",
        backupCount=max(retention_days, 1),
        encoding="utf-8",
    )
    app_handler.setLevel(log_level)
    app_handler.setFormatter(formatter)

    error_handler = ImmediateGZipTimedRotatingFileHandler(
        filename=str(logs_dir / "pyrobot_backend_error.log"),
        when="midnight",
        backupCount=max(error_retention_days, 1),
        encoding="utf-8",
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)

    logging.captureWarnings(True)

    return LoggingHandlers(
        console=console_handler,
        application=app_handler,
        error=error_handler,
    )


def apply_rate_limit_filters(
    rate_limits: Mapping[str, float],
    *,
    exempt_level: int = logging.WARNING,
) -> None:
    for logger_name, interval in rate_limits.items():
        if interval is None:
            continue
        try:
            interval_value = float(interval)
        except (TypeError, ValueError):
            continue
        if interval_value <= 0:
            continue

        target_logger = logging.getLogger(logger_name)
        already_configured = any(
            isinstance(existing, RateLimitingFilter) and existing.interval == interval_value and existing.exempt_level == exempt_level
            for existing in target_logger.filters
        )
        if not already_configured:
            target_logger.addFilter(RateLimitingFilter(interval_value, exempt_level=exempt_level))


__all__ = [
    "ImmediateFlushStreamHandler",
    "ImmediateGZipTimedRotatingFileHandler",
    "JsonFormatter",
    "LoggingHandlers",
    "RateLimitingFilter",
    "apply_rate_limit_filters",
    "setup_logging",
]
