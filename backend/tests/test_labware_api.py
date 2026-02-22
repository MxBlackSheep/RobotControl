from typing import Any, Dict, List

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.auth import get_current_user
from backend.api.labware import get_cytomat_service, get_tip_tracking_service
from backend.services.labware_cytomat import CytomatValidationError


class FakeTipTrackingService:
    def build_snapshot(self) -> Dict[str, Any]:
        return {
            "grid": {"rows": 8, "cols": 12, "positions_per_rack": 96},
            "auto_refresh_ms": 15000,
            "status_order": ["clean", "empty", "dirty", "rinsed", "washed", "reserved", "unclear"],
            "status_colors": {
                "clean": "#22c55e",
                "empty": "#d1d5db",
                "dirty": "#ef4444",
                "rinsed": "#3b82f6",
                "washed": "#a855f7",
                "reserved": "#f59e0b",
                "unclear": "#6b7280",
            },
            "unknown_status": "unclear",
            "families": [
                {
                    "family_id": "1000ul",
                    "display_name": "1000ul Tips",
                    "left_racks": ["VER_HT_0001"],
                    "right_racks": ["VER_HT_0002"],
                    "reset_map": {"ColA": {"clean": ["VER_HT_0001"]}, "ColB": {"empty": ["VER_HT_0002"]}},
                    "tips": {
                        "VER_HT_0001": {"1": "clean"},
                        "VER_HT_0002": {"1": "empty"},
                    },
                }
            ],
            "refreshed_at": "2026-02-12T00:00:00",
        }

    def apply_updates(self, family_id: str, updates: List[Any]) -> int:
        return len(updates)

    def reset_family(self, family_id: str) -> int:
        return 192


class FakeCytomatService:
    _allowed = {"", "1003", "1002", "1001"}

    def build_snapshot(self) -> Dict[str, Any]:
        return {
            "rows": [
                {"cytomat_pos": "A01", "plate_id": "1003"},
                {"cytomat_pos": "A02", "plate_id": ""},
            ],
            "plate_options": ["", "1003", "1002", "1001"],
            "auto_refresh_ms": 15000,
            "refreshed_at": "2026-02-14T00:00:00",
        }

    def apply_updates(self, updates: List[Any]) -> int:
        for item in updates:
            if str(item.plate_id) not in self._allowed:
                raise CytomatValidationError("PlateID must exist in Plates table or be empty.")
        return len(updates)


client = TestClient(app)


def setup_function():
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "1",
        "username": "tester",
        "role": "user",
    }
    app.dependency_overrides[get_tip_tracking_service] = lambda: FakeTipTrackingService()
    app.dependency_overrides[get_cytomat_service] = lambda: FakeCytomatService()


def teardown_function():
    app.dependency_overrides.clear()


def test_tip_tracking_read_remote_is_allowed_but_read_only():
    response = client.get(
        "/api/labware/tip-tracking",
        headers={"x-forwarded-for": "8.8.8.8"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["permissions"]["can_update"] is False


def test_tip_tracking_update_requires_local_access():
    response = client.put(
        "/api/labware/tip-tracking",
        json={
            "family": "1000ul",
            "updates": [
                {"labware_id": "VER_HT_0001", "position_id": 1, "status": "dirty"}
            ],
        },
        headers={"x-forwarded-for": "8.8.8.8"},
    )

    assert response.status_code == 403
    assert "Local network access required" in response.json()["detail"]


def test_tip_tracking_update_local_success():
    response = client.put(
        "/api/labware/tip-tracking",
        json={
            "family": "1000ul",
            "updates": [
                {"labware_id": "VER_HT_0001", "position_id": 1, "status": "dirty"},
                {"labware_id": "VER_HT_0001", "position_id": 2, "status": "clean"},
            ],
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["updated_count"] == 2


def test_tip_tracking_role_guard():
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "2",
        "username": "viewer",
        "role": "viewer",
    }

    response = client.get(
        "/api/labware/tip-tracking",
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin or user role required"


def test_cytomat_read_remote_is_allowed_but_read_only():
    response = client.get(
        "/api/labware/cytomat",
        headers={"x-forwarded-for": "8.8.8.8"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["permissions"]["can_update"] is False
    assert payload["data"]["plate_options"][0] == ""


def test_cytomat_update_requires_local_access():
    response = client.put(
        "/api/labware/cytomat",
        json={
            "updates": [
                {"cytomat_pos": "A02", "plate_id": "1001"},
            ],
        },
        headers={"x-forwarded-for": "8.8.8.8"},
    )

    assert response.status_code == 403
    assert "Local network access required" in response.json()["detail"]


def test_cytomat_update_local_success():
    response = client.put(
        "/api/labware/cytomat",
        json={
            "updates": [
                {"cytomat_pos": "A01", "plate_id": ""},
                {"cytomat_pos": "A02", "plate_id": "1002"},
            ],
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["updated_count"] == 2


def test_cytomat_update_rejects_unknown_plate_id():
    response = client.put(
        "/api/labware/cytomat",
        json={
            "updates": [
                {"cytomat_pos": "A02", "plate_id": "9999"},
            ],
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
