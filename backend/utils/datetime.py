"""
Datetime helpers for RobotControl.

Provides utilities to safely parse ISO8601 timestamps originating from the
frontend (which may be serialized in UTC) and convert them to system-local,
timezone-naive ``datetime`` objects for use throughout the scheduler and
backend services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _normalize_iso_string(value: str) -> str:
    """
    Ensure ISO strings with 'Z' suffix are converted to '+00:00' so that
    :func:`datetime.fromisoformat` can parse them on older Python versions.
    """
    if value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


def parse_iso_datetime_to_local(value: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO8601 timestamp and return a system-local timezone-naive datetime.

    Args:
        value: ISO8601 timestamp string or ``None``.

    Returns:
        ``datetime`` without timezone information (interpreted in system local time),
        or ``None`` if the input is falsy.
    """
    if not value:
        return None

    # Allow passing an existing datetime
    if isinstance(value, datetime):
        return ensure_local_naive(value)

    value_str = _normalize_iso_string(str(value).strip())
    try:
        dt = datetime.fromisoformat(value_str)
    except ValueError:
        # Last resort: try parsing without replacements (helps for already naive values)
        dt = datetime.fromisoformat(str(value).strip())
    return ensure_local_naive(dt)


def ensure_local_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert an aware datetime to system-local naive datetime. If the datetime is
    already naive, it is returned unchanged.
    """
    if dt is None:
        return None

    if dt.tzinfo is not None:
        # Convert to local timezone (no argument defaults to local tz)
        dt = dt.astimezone()
        return dt.replace(tzinfo=None)

    return dt


def utc_now_as_local_naive() -> datetime:
    """
    Convenience helper for callers that currently rely on ``datetime.utcnow``.

    Returns:
        Current time as local timezone-naive datetime.
    """
    return ensure_local_naive(datetime.now(timezone.utc))
