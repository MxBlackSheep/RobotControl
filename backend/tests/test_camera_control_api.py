from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.camera import router
from backend.services.auth import get_current_user, get_current_admin_user


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "viewer", "username": "viewer"}
    with patch("backend.services.auth.get_auth_service") as auth:
        auth.return_value.is_admin.return_value = False
        yield app, TestClient(app)


def test_status_does_not_enumerate_hardware(client):
    _, browser = client
    with patch("backend.api.camera.get_camera_service") as get:
        get.return_value.get_camera_status.return_value = {"health": {"capture_state": "disconnected"}}
        assert browser.get("/api/camera/control-status").status_code == 200
        get.return_value.detect_cameras.assert_not_called()


@pytest.mark.parametrize("action", ["connect", "reconnect", "devices/refresh", "recording/start", "recording/stop"])
def test_hardware_actions_require_admin(client, action):
    _, browser = client
    assert browser.post(f"/api/camera/{action}").status_code in (401, 403)


def test_reconnect_accepted_and_busy_rejected(client):
    app, browser = client
    app.dependency_overrides[get_current_admin_user] = lambda: SimpleNamespace(username="admin")
    with patch("backend.api.camera.get_camera_service") as get:
        get.return_value.runtime.submit.return_value = {"id": "operation", "state": "pending"}
        response = browser.post("/api/camera/reconnect")
        assert response.status_code == 202
        assert response.json()["data"]["operation"]["id"] == "operation"
        get.return_value.runtime.submit.side_effect = ValueError("A camera operation is already in progress")
        assert browser.post("/api/camera/reconnect").status_code == 409


def test_selection_requires_identity(client):
    app, browser = client
    app.dependency_overrides[get_current_admin_user] = lambda: SimpleNamespace(username="admin")
    assert browser.patch("/api/camera/selection", json={"device_identity": ""}).status_code == 422
