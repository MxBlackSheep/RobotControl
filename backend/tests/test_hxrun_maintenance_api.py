from datetime import datetime
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

import backend.api.maintenance as maintenance_api
from backend.main import app
from backend.models import HxRunMaintenanceState
from backend.services.auth import get_current_user


class FakeHxRunMaintenanceService:
    def __init__(self) -> None:
        self._state = HxRunMaintenanceState()

    def get_state(self, force_refresh: bool = True) -> HxRunMaintenanceState:
        return self._state

    def set_state(self, *, enabled: bool, reason: Optional[str], actor: str) -> HxRunMaintenanceState:
        self._state = HxRunMaintenanceState(
            enabled=enabled,
            reason=reason,
            updated_by=actor,
            updated_at=datetime.now(),
        )
        return self._state


client = TestClient(app)


def _override_user() -> Dict[str, Any]:
    return {
        "user_id": "1",
        "username": "tester",
        "role": "user",
    }


def setup_function():
    app.dependency_overrides[get_current_user] = _override_user


def teardown_function():
    app.dependency_overrides.clear()


def test_hxrun_maintenance_read_remote_is_allowed(monkeypatch):
    fake_service = FakeHxRunMaintenanceService()
    monkeypatch.setattr(maintenance_api, "get_hxrun_maintenance_service", lambda: fake_service)

    response = client.get(
        "/api/maintenance/hxrun",
        headers={"x-forwarded-for": "8.8.8.8"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["permissions"]["can_edit"] is False
    assert payload["data"]["enabled"] is False


def test_hxrun_maintenance_write_requires_local_access(monkeypatch):
    fake_service = FakeHxRunMaintenanceService()
    monkeypatch.setattr(maintenance_api, "get_hxrun_maintenance_service", lambda: fake_service)

    response = client.put(
        "/api/maintenance/hxrun",
        json={"enabled": True, "reason": "Prevent manual starts"},
        headers={"x-forwarded-for": "8.8.8.8"},
    )

    assert response.status_code == 403
    assert "Local network access required" in response.json()["detail"]


def test_hxrun_maintenance_write_local_success(monkeypatch):
    fake_service = FakeHxRunMaintenanceService()
    monkeypatch.setattr(maintenance_api, "get_hxrun_maintenance_service", lambda: fake_service)

    response = client.put(
        "/api/maintenance/hxrun",
        json={"enabled": True, "reason": "Robot is under service"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["enabled"] is True
    assert payload["data"]["reason"] == "Robot is under service"
    assert payload["data"]["updated_by"] == "tester"
