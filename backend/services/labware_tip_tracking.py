"""
Labware tip-tracking service.

Provides read and write access for tip usage state across 1000ul and 300ul
rack families used by the web TipTracking UI.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import pyodbc

from backend.config import settings
from backend.utils.odbc_driver import resolve_driver_clause

logger = logging.getLogger(__name__)

GRID_COLS = 12
GRID_ROWS = 8
POSITIONS_PER_RACK = GRID_COLS * GRID_ROWS
AUTO_REFRESH_MS = 15_000

STATUS_ORDER: Tuple[str, ...] = (
    "clean",
    "empty",
    "dirty",
    "rinsed",
    "washed",
    "reserved",
    "unclear",
)
STATUS_SET = set(STATUS_ORDER)

STATUS_COLORS: Dict[str, str] = {
    "clean": "#22c55e",
    "empty": "#d1d5db",
    "dirty": "#ef4444",
    "rinsed": "#3b82f6",
    "washed": "#a855f7",
    "reserved": "#f59e0b",
    "unclear": "#6b7280",
}
UNKNOWN_STATUS = "unclear"


@dataclass(frozen=True)
class TipFamilyConfig:
    family_id: str
    display_name: str
    left_racks: Tuple[str, ...]
    right_racks: Tuple[str, ...]
    table_cola: str
    table_colb: str
    reset_map: Mapping[str, Mapping[str, Tuple[str, ...]]]

    @property
    def all_racks(self) -> Tuple[str, ...]:
        return self.left_racks + self.right_racks

    @property
    def left_rack_set(self) -> set[str]:
        return set(self.left_racks)

    @property
    def right_rack_set(self) -> set[str]:
        return set(self.right_racks)


@dataclass(frozen=True)
class TipStatusUpdate:
    labware_id: str
    position_id: int
    status: str


class TipTrackingValidationError(ValueError):
    """Raised when input data is invalid."""


class TipTrackingDatabaseError(RuntimeError):
    """Raised when database operations fail."""


TIP_FAMILY_CONFIGS: Dict[str, TipFamilyConfig] = {
    "1000ul": TipFamilyConfig(
        family_id="1000ul",
        display_name="1000ul Tips",
        left_racks=("VER_HT_0005", "VER_HT_0001", "VER_HT_0002", "VER_HT_0006", "VER_HT_0009"),
        right_racks=("VER_HT_0003", "VER_HT_0004", "VER_HT_0007", "VER_HT_0008", "VER_HT_0010"),
        table_cola="[dbo].[TipUsage_ColA]",
        table_colb="[dbo].[TipUsage_ColB]",
        reset_map={
            "ColA": {
                "clean": ("VER_HT_0005", "VER_HT_0001", "VER_HT_0002", "VER_HT_0006"),
                "empty": ("VER_HT_0009",),
            },
            "ColB": {
                "clean": ("VER_HT_0003", "VER_HT_0004", "VER_HT_0007", "VER_HT_0008"),
                "empty": ("VER_HT_0010",),
            },
        },
    ),
    "300ul": TipFamilyConfig(
        family_id="300ul",
        display_name="300ul Tips",
        left_racks=("VER_ST_0001", "VER_ST_0002", "VER_ST_0003", "VER_ST_0006", "VER_ST_0009"),
        right_racks=("VER_ST_0004", "VER_ST_0005", "VER_ST_0007", "VER_ST_0008", "VER_ST_0010"),
        table_cola="[dbo].[TipUsage_300ul_ColA]",
        table_colb="[dbo].[TipUsage_300ul_ColB]",
        reset_map={
            "ColA": {
                "clean": ("VER_ST_0001", "VER_ST_0006", "VER_ST_0003", "VER_ST_0002"),
                "empty": ("VER_ST_0009",),
            },
            "ColB": {
                "clean": ("VER_ST_0004", "VER_ST_0008", "VER_ST_0007", "VER_ST_0005"),
                "empty": ("VER_ST_0010",),
            },
        },
    ),
}


class TipTrackingService:
    """Read/write operations for labware tip tracking."""

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
            base = {
                "driver": "{ODBC Driver 11 for SQL Server}",
                "server": "LOCALHOST\\HAMILTON",
                "database": "EvoYeast",
                "user": "Hamilton",
                "password": "mkdpw:V43",
                "trust_connection": "no",
                "timeout": 5,
            }

        base["database"] = os.getenv("ROBOTCONTROL_LABWARE_DATABASE", "Labwares")
        return base

    def _build_connection_string(self) -> str:
        configured_driver = self._config.get("driver")
        driver_clause = resolve_driver_clause(configured_driver)
        if not driver_clause:
            raise TipTrackingDatabaseError("No SQL Server ODBC driver is available")

        server = self._config.get("server")
        database = self._config.get("database")

        if not server or not database:
            raise TipTrackingDatabaseError("Labware database configuration is incomplete")

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
            logger.error("Labware database operation failed: %s", exc)
            raise TipTrackingDatabaseError("Unable to reach labware database") from exc
        finally:
            try:
                connection.close()  # type: ignore[name-defined]
            except Exception:
                pass

    @staticmethod
    def _normalize_status(value: Any) -> str:
        if value is None:
            return UNKNOWN_STATUS
        status = str(value).strip().lower()
        return status if status in STATUS_SET else UNKNOWN_STATUS

    @staticmethod
    def _normalize_input_status(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_family_id(family_id: str) -> str:
        return str(family_id or "").strip().lower()

    def get_family_config(self, family_id: str) -> TipFamilyConfig:
        normalized = self._normalize_family_id(family_id)
        config = TIP_FAMILY_CONFIGS.get(normalized)
        if not config:
            supported = ", ".join(sorted(TIP_FAMILY_CONFIGS.keys()))
            raise TipTrackingValidationError(f"Unknown tip family '{family_id}'. Supported values: {supported}")
        return config

    def fetch_tip_map(self, family_id: str) -> Dict[str, Dict[int, str]]:
        config = self.get_family_config(family_id)

        query = (
            f"SELECT labware_id, position_id, status FROM {config.table_cola} "
            "UNION ALL "
            f"SELECT labware_id, position_id, status FROM {config.table_colb}"
        )

        rack_whitelist = set(config.all_racks)
        tip_map: Dict[str, Dict[int, str]] = {rack: {} for rack in config.all_racks}

        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            for labware_id, position_id, status in cursor.fetchall():
                rack = str(labware_id).strip()
                if rack not in rack_whitelist:
                    continue
                try:
                    pos = int(position_id)
                except (TypeError, ValueError):
                    continue
                if pos < 1 or pos > POSITIONS_PER_RACK:
                    continue
                tip_map[rack][pos] = self._normalize_status(status)
            cursor.close()

        return tip_map

    def build_snapshot(self) -> Dict[str, Any]:
        families: List[Dict[str, Any]] = []

        for family_id, config in TIP_FAMILY_CONFIGS.items():
            families.append(
                {
                    "family_id": family_id,
                    "display_name": config.display_name,
                    "left_racks": list(config.left_racks),
                    "right_racks": list(config.right_racks),
                    "reset_map": {
                        side: {status: list(racks) for status, racks in status_map.items()}
                        for side, status_map in config.reset_map.items()
                    },
                    "tips": self.fetch_tip_map(family_id),
                }
            )

        return {
            "grid": {
                "rows": GRID_ROWS,
                "cols": GRID_COLS,
                "positions_per_rack": POSITIONS_PER_RACK,
            },
            "auto_refresh_ms": AUTO_REFRESH_MS,
            "status_order": list(STATUS_ORDER),
            "status_colors": STATUS_COLORS.copy(),
            "unknown_status": UNKNOWN_STATUS,
            "families": families,
            "refreshed_at": datetime.now().isoformat(),
        }

    def _validate_update(self, config: TipFamilyConfig, update: TipStatusUpdate) -> TipStatusUpdate:
        labware_id = str(update.labware_id or "").strip()
        if labware_id not in set(config.all_racks):
            raise TipTrackingValidationError(
                f"Labware '{labware_id}' is not part of the '{config.family_id}' tip family"
            )

        try:
            position_id = int(update.position_id)
        except (TypeError, ValueError):
            raise TipTrackingValidationError("position_id must be an integer") from None

        if position_id < 1 or position_id > POSITIONS_PER_RACK:
            raise TipTrackingValidationError(
                f"position_id must be between 1 and {POSITIONS_PER_RACK}"
            )

        status = self._normalize_input_status(update.status)
        if status not in STATUS_SET:
            supported = ", ".join(STATUS_ORDER)
            raise TipTrackingValidationError(f"Unsupported status '{update.status}'. Supported values: {supported}")

        return TipStatusUpdate(labware_id=labware_id, position_id=position_id, status=status)

    def apply_updates(self, family_id: str, updates: Iterable[TipStatusUpdate]) -> int:
        config = self.get_family_config(family_id)

        deduped: Dict[Tuple[str, int], TipStatusUpdate] = {}
        for update in updates:
            normalized = self._validate_update(config, update)
            deduped[(normalized.labware_id, normalized.position_id)] = normalized

        if not deduped:
            return 0

        cola_updates: List[Tuple[str, str, int]] = []
        colb_updates: List[Tuple[str, str, int]] = []

        left_racks = set(config.left_racks)
        for normalized in deduped.values():
            payload = (normalized.status, normalized.labware_id, normalized.position_id)
            if normalized.labware_id in left_racks:
                cola_updates.append(payload)
            else:
                colb_updates.append(payload)

        total_updated = 0
        with self._get_connection() as connection:
            cursor = connection.cursor()
            try:
                if cola_updates:
                    cursor.executemany(
                        f"UPDATE {config.table_cola} SET status=? WHERE labware_id=? AND position_id=?",
                        cola_updates,
                    )
                    total_updated += cursor.rowcount if cursor.rowcount != -1 else len(cola_updates)

                if colb_updates:
                    cursor.executemany(
                        f"UPDATE {config.table_colb} SET status=? WHERE labware_id=? AND position_id=?",
                        colb_updates,
                    )
                    total_updated += cursor.rowcount if cursor.rowcount != -1 else len(colb_updates)

                connection.commit()
            except pyodbc.Error as exc:
                connection.rollback()
                logger.error("Failed to update tip statuses: %s", exc)
                raise TipTrackingDatabaseError("Failed to update tip tracking state") from exc
            finally:
                cursor.close()

        return total_updated

    def reset_family(self, family_id: str) -> int:
        config = self.get_family_config(family_id)

        reset_updates: List[TipStatusUpdate] = []
        for status_map in config.reset_map.values():
            for status, racks in status_map.items():
                normalized_status = self._normalize_status(status)
                if normalized_status not in STATUS_SET:
                    raise TipTrackingValidationError(f"Invalid reset status '{status}' in configuration")
                for rack in racks:
                    for position_id in range(1, POSITIONS_PER_RACK + 1):
                        reset_updates.append(
                            TipStatusUpdate(
                                labware_id=rack,
                                position_id=position_id,
                                status=normalized_status,
                            )
                        )

        return self.apply_updates(config.family_id, reset_updates)


_tip_tracking_service: Optional[TipTrackingService] = None


def get_tip_tracking_service() -> TipTrackingService:
    global _tip_tracking_service
    if _tip_tracking_service is None:
        _tip_tracking_service = TipTrackingService()
    return _tip_tracking_service
