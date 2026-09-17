"""Shared SQLite connection policy and explicit failure types."""
import sqlite3


class SafetyConflict(ValueError):
    """The requested change conflicts with current, authoritative state."""


class StorageUnavailable(RuntimeError):
    """A storage failure must never be interpreted as an empty database."""


def configure_connection(conn):
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise StorageUnavailable("SQLite foreign-key enforcement is unavailable")


def check_timestamp(expected, actual):
    if expected is None:
        return
    from backend.utils.datetime import parse_iso_datetime_to_local
    try:
        matches = parse_iso_datetime_to_local(expected) == parse_iso_datetime_to_local(actual)
    except (TypeError, ValueError):
        matches = False
    if not matches:
        raise SafetyConflict("Schedule was modified by another user. Refresh and try again.")
