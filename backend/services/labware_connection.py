"""SQL Server connection shared by the Labware tip-tracking and Cytomat services."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Iterator, Type

import pyodbc

from backend.config import settings
from backend.utils.odbc_driver import build_connection_string, resolve_driver_clause

logger = logging.getLogger(__name__)


@contextmanager
def labware_connection(database: str, error_type: Type[Exception], name: str) -> Iterator[pyodbc.Connection]:
    """Open ``database`` on the primary server with the primary login.

    Unlike the Database viewer, Labware falls back to any installed SQL Server
    driver and trusts the server certificate unless configured otherwise.
    Driver/configuration problems and pyodbc errors (including those raised
    inside the ``with`` block) become ``error_type``.
    """
    config = {"trust_server_certificate": "yes", **settings.DB_CONFIG_PRIMARY, "database": database}
    config["driver"] = resolve_driver_clause(config.get("driver"))
    if not config["driver"]:
        raise error_type("No SQL Server ODBC driver is available")
    if not config.get("server") or not database:
        raise error_type(f"{name} database configuration is incomplete")

    connection = None
    try:
        connection = pyodbc.connect(build_connection_string(config), timeout=int(config.get("timeout", 5) or 5))
        yield connection
    except pyodbc.Error as exc:
        logger.error("%s database operation failed: %s", name, exc)
        raise error_type(f"Unable to reach {name} database") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
