"""
Labware Cytomat service.

Provides read and write access for Cytomat plate placement state and
valid PlateID options sourced from the Plates table.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, Dict, Iterable, List, Optional, Set

import pyodbc

from backend.config import settings
from backend.utils.odbc_driver import resolve_driver_clause

logger = logging.getLogger(__name__)

AUTO_REFRESH_MS = 15_000

DEFAULT_DB_CONFIG: Dict[str, Any] = {
    "driver": "{ODBC Driver 11 for SQL Server}",
    "server": "LOCALHOST\\HAMILTON",
    "database": "EvoYeast",
    "user": "Hamilton",
    "password": "mkdpw:V43",
    "trust_connection": "no",
    "timeout": 5,
}


@dataclass(frozen=True)
class CytomatPlateUpdate:
    cytomat_pos: str
    plate_id: str


class CytomatValidationError(ValueError):
    """Raised when Cytomat input data is invalid."""


class CytomatDatabaseError(RuntimeError):
    """Raised when Cytomat database operations fail."""


class CytomatService:
    """Read/write operations for Cytomat plate placement."""

    def __init__(self) -> None:
        self._config = self._build_db_config()

    def _build_db_config(self) -> Dict[str, Any]:
        base = {}
        try:
            if isinstance(settings.DB_CONFIG_PRIMARY, dict):
                base = settings.DB_CONFIG_PRIMARY.copy()
        except Exception:
            base = {}

        if not base:
            base = DEFAULT_DB_CONFIG.copy()

        base["database"] = "EvoYeast"
        return base

    def _build_connection_string(self) -> str:
        configured_driver = self._config.get("driver")
        driver_clause = resolve_driver_clause(configured_driver)
        if not driver_clause:
            raise CytomatDatabaseError("No SQL Server ODBC driver is available")

        server = self._config.get("server")
        database = self._config.get("database")
        if not server or not database:
            raise CytomatDatabaseError("Cytomat database configuration is incomplete")

        parts = [
            f"DRIVER={driver_clause}",
            f"SERVER={server}",
            f"DATABASE={database}",
        ]

        user = self._config.get("user")
        password = self._config.get("password")
        trusted = str(self._config.get("trusted_connection", self._config.get("trust_connection", "no"))).lower()

        if user and password:
            parts.extend([f"UID={user}", f"PWD={password}"])
        elif trusted in {"yes", "true", "1"}:
            parts.append("Trusted_Connection=yes")

        encrypt = self._config.get("encrypt")
        if encrypt:
            parts.append(f"Encrypt={encrypt}")

        trust_server_certificate = self._config.get("trust_server_certificate", "yes")
        parts.append(f"TrustServerCertificate={trust_server_certificate}")

        return ";".join(parts)

    @contextmanager
    def _get_connection(self):
        conn_str = self._build_connection_string()
        timeout = int(self._config.get("timeout", 5) or 5)
        connection = None
        try:
            connection = pyodbc.connect(conn_str, timeout=timeout)
            yield connection
        except pyodbc.Error as exc:
            logger.error("Cytomat database operation failed: %s", exc)
            raise CytomatDatabaseError("Unable to reach Cytomat database") from exc
        finally:
            try:
                connection.close()  # type: ignore[name-defined]
            except Exception:
                pass

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def fetch_plate_options(self) -> List[str]:
        query = "SELECT DISTINCT PlateID FROM [dbo].[Plates]"
        values: Set[str] = set()

        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            for (plate_id,) in cursor.fetchall():
                normalized = self._normalize_text(plate_id)
                if normalized:
                    values.add(normalized)
            cursor.close()

        numeric_values: List[tuple[int, str]] = []
        text_values: List[str] = []

        for value in values:
            try:
                numeric_values.append((int(value), value))
            except ValueError:
                text_values.append(value)

        numeric_values.sort(key=lambda item: (item[0], item[1]), reverse=True)
        text_values.sort(reverse=True)

        ordered = [value for _, value in numeric_values] + text_values
        return [""] + ordered

    def fetch_cytomat_rows(self) -> List[Dict[str, str]]:
        query = (
            "SELECT CytomatPos, PlateID "
            "FROM [dbo].[Cytomat] "
            "ORDER BY CytomatPos"
        )

        rows: List[Dict[str, str]] = []
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            for cytomat_pos, plate_id in cursor.fetchall():
                position = self._normalize_text(cytomat_pos)
                if not position:
                    continue
                rows.append(
                    {
                        "cytomat_pos": position,
                        "plate_id": self._normalize_text(plate_id),
                    }
                )
            cursor.close()

        return rows

    def build_snapshot(self) -> Dict[str, Any]:
        return {
            "rows": self.fetch_cytomat_rows(),
            "plate_options": self.fetch_plate_options(),
            "auto_refresh_ms": AUTO_REFRESH_MS,
            "refreshed_at": datetime.now().isoformat(),
        }

    def _validate_update(
        self,
        update: CytomatPlateUpdate,
        valid_positions: Set[str],
        valid_plate_ids: Set[str],
    ) -> CytomatPlateUpdate:
        cytomat_pos = self._normalize_text(update.cytomat_pos)
        if not cytomat_pos:
            raise CytomatValidationError("cytomat_pos is required")

        if cytomat_pos not in valid_positions:
            raise CytomatValidationError(f"Unknown Cytomat position '{update.cytomat_pos}'")

        plate_id = self._normalize_text(update.plate_id)
        if plate_id and plate_id not in valid_plate_ids:
            raise CytomatValidationError(
                f"PlateID '{update.plate_id}' is not valid. PlateID must exist in Plates table or be empty."
            )

        return CytomatPlateUpdate(cytomat_pos=cytomat_pos, plate_id=plate_id)

    def apply_updates(self, updates: Iterable[CytomatPlateUpdate]) -> int:
        current_rows = self.fetch_cytomat_rows()
        valid_positions = {row["cytomat_pos"] for row in current_rows}

        plate_options = self.fetch_plate_options()
        valid_plate_ids = {item for item in plate_options if item}

        deduped: Dict[str, CytomatPlateUpdate] = {}
        for update in updates:
            normalized = self._validate_update(update, valid_positions, valid_plate_ids)
            deduped[normalized.cytomat_pos] = normalized

        if not deduped:
            return 0

        payload = [
            (item.plate_id if item.plate_id else None, item.cytomat_pos)
            for item in deduped.values()
        ]

        with self._get_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.executemany(
                    "UPDATE [dbo].[Cytomat] SET PlateID=? WHERE CytomatPos=?",
                    payload,
                )
                connection.commit()
                updated_count = cursor.rowcount if cursor.rowcount != -1 else len(payload)
            except pyodbc.Error as exc:
                connection.rollback()
                logger.error("Failed to update Cytomat rows: %s", exc)
                raise CytomatDatabaseError("Failed to update Cytomat plate assignments") from exc
            finally:
                cursor.close()

        return updated_count


_cytomat_service: Optional[CytomatService] = None


def get_cytomat_service() -> CytomatService:
    global _cytomat_service
    if _cytomat_service is None:
        _cytomat_service = CytomatService()
    return _cytomat_service
