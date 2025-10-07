"""
Utilities for resolving Microsoft SQL Server ODBC drivers.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable, Optional

try:
    import pyodbc  # type: ignore
except ImportError:  # pragma: no cover - optional dependency during packaging
    pyodbc = None  # type: ignore

logger = logging.getLogger(__name__)

_PREFERRED_DRIVERS = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "ODBC Driver 11 for SQL Server",
    "SQL Server",
)


def _normalise(driver: Optional[str]) -> Optional[str]:
    if not driver:
        return None
    return driver.strip().strip("{}")


def _available_drivers_map() -> dict[str, str]:
    drivers = list_available_drivers()
    mapping: dict[str, str] = {}
    for name in drivers:
        normalised = _normalise(name)
        if normalised:
            mapping[normalised.lower()] = normalised
    return mapping


@lru_cache(maxsize=1)
def list_available_drivers() -> tuple[str, ...]:
    """Return the installed ODBC drivers as reported by pyodbc."""
    if pyodbc is None:
        logger.warning("pyodbc is not available; SQL Server connectivity will be disabled")
        return tuple()
    try:
        drivers = tuple(pyodbc.drivers())
        if not drivers:
            logger.warning("No ODBC drivers detected; install the Microsoft ODBC Driver for SQL Server")
        return drivers
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Unable to enumerate ODBC drivers via pyodbc: %s", exc)
        return tuple()


def choose_driver(explicit_driver: Optional[str] = None, preferred: Iterable[str] = _PREFERRED_DRIVERS) -> Optional[str]:
    """Resolve the best driver name (without braces) to use for SQL Server."""
    available_map = _available_drivers_map()
    explicit_normalised = _normalise(explicit_driver)

    if explicit_normalised:
        if not available_map or explicit_normalised.lower() in available_map:
            return explicit_normalised
        logger.warning(
            "Configured SQL Server ODBC driver '%s' is not installed; attempting fallback",
            explicit_driver,
        )

    for candidate in preferred:
        candidate_normalised = _normalise(candidate)
        if candidate_normalised and candidate_normalised.lower() in available_map:
            return candidate_normalised

    if available_map:
        # Deterministic selection of the first available driver
        first_available = next(iter(available_map.values()))
        logger.info("Falling back to first available ODBC driver '%s'", first_available)
        return first_available

    # No drivers detected; return explicit driver as last resort for clearer failure downstream
    return explicit_normalised


def format_driver_for_connection(driver: Optional[str]) -> Optional[str]:
    """Return the driver token ready for use in an ODBC connection string."""
    normalised = _normalise(driver)
    if not normalised:
        return None
    return f"{{{normalised}}}"


def resolve_driver_clause(explicit_driver: Optional[str] = None) -> Optional[str]:
    """Resolve and format the driver entry for use in a connection string."""
    chosen_driver = choose_driver(explicit_driver)
    clause = format_driver_for_connection(chosen_driver)
    if clause is None:
        logger.error(
            "No suitable SQL Server ODBC driver found. Install Microsoft ODBC Driver 17 or 18 for SQL Server."
        )
    return clause


__all__ = [
    "choose_driver",
    "format_driver_for_connection",
    "list_available_drivers",
    "resolve_driver_clause",
]
