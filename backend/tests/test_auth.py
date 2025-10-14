import os
import uuid

import pytest
from fastapi.testclient import TestClient

TEST_DB_NAME = f"test_auth_{uuid.uuid4().hex}.db"
os.environ["ROBOTCONTROL_AUTH_DB_FILENAME"] = TEST_DB_NAME

from backend.utils.data_paths import get_data_path
from backend.services import auth as auth_module
from backend.services.auth import AuthService, DEFAULT_ADMIN_PASSWORD
from backend.main import app


DB_PATH = get_data_path() / TEST_DB_NAME
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_auth_service():
    if DB_PATH.exists():
        DB_PATH.unlink()
    auth_module._auth_service = None  # type: ignore[attr-defined]
    yield
    if DB_PATH.exists():
        DB_PATH.unlink()
    auth_module._auth_service = None  # type: ignore[attr-defined]


def get_service() -> AuthService:
    return AuthService()


def test_register_and_login_flow():
    service = get_service()
    user = service.register_user("alice", "alice@example.com", "SecurePass!1")
    assert user.username == "alice"
    result = service.login("alice", "SecurePass!1")
    assert result is not None
    assert "access_token" in result
    assert result["user"]["username"] == "alice"


def test_duplicate_registration_rejected():
    service = get_service()
    service.register_user("bob", "bob@example.com", "SecurePass!1")
    with pytest.raises(ValueError):
        service.register_user("bob", "another@example.com", "OtherPass!2")
    with pytest.raises(ValueError):
        service.register_user("bobby", "bob@example.com", "OtherPass!2")


def test_change_password_requires_current_password():
    service = get_service()
    service.register_user("carol", "carol@example.com", "SecurePass!1")
    user = service.authenticate_user("carol", "SecurePass!1")
    assert user is not None
    assert service.change_password(user, "wrong", "NewPass!1") is False
    assert service.change_password(user, "SecurePass!1", "NewPass!1") is True
    assert service.login("carol", "NewPass!1") is not None


def test_refresh_token_cycle():
    service = get_service()
    service.register_user("dave", "dave@example.com", "SecurePass!1")
    login_payload = service.login("dave", "SecurePass!1")
    assert login_payload is not None
    refresh_token = login_payload["refresh_token"]
    new_access_token = service.refresh_access_token(refresh_token)
    assert isinstance(new_access_token, str)
    # Revoke the refresh token and ensure it no longer works
    service.revoke_refresh_token(refresh_token)
    assert service.refresh_access_token(refresh_token) is None


def test_api_registration_and_login():
    payload = {
        "username": "erin",
        "email": "erin@example.com",
        "password": "SecurePass!1",
    }
    register_response = client.post("/api/auth/register", json=payload)
    assert register_response.status_code == 201
    data = register_response.json()
    assert data["success"] is True
    assert data["data"]["user"]["username"] == "erin"

    login_response = client.post(
        "/api/auth/login",
        json={"username": "erin", "password": "SecurePass!1"},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["success"] is True
    assert login_data["data"]["user"]["username"] == "erin"


def test_api_change_password_and_refresh():
    register_response = client.post(
        "/api/auth/register",
        json={
            "username": "frank",
            "email": "frank@example.com",
            "password": "SecurePass!1",
        },
    )
    assert register_response.status_code == 201
    tokens = register_response.json()["data"]

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    change_response = client.post(
        "/api/auth/change-password",
        json={"current_password": "SecurePass!1", "new_password": "NewPass!2"},
        headers=headers,
    )
    assert change_response.status_code == 200

    # Existing refresh token should be invalidated
    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 401

    # Login with new password works
    login_response = client.post(
        "/api/auth/login",
        json={"username": "frank", "password": "NewPass!2"},
    )
    assert login_response.status_code == 200


def test_password_reset_request_flow():
    service = get_service()
    service.register_user("gina", "gina@example.com", "SecurePass!1")

    request_response = client.post(
        "/api/auth/password-reset/request",
        json={"username": "gina", "note": "forgot password"},
    )
    assert request_response.status_code == 202
    payload = request_response.json()
    assert payload["success"] is True

    # Authenticate as admin to inspect and resolve the request
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["data"]["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    list_response = client.get(
        "/api/admin/password-reset/requests",
        headers=admin_headers,
    )
    assert list_response.status_code == 200
    request_list = list_response.json()["data"]
    assert len(request_list) == 1
    request_entry = request_list[0]
    assert request_entry["username"] == "gina"
    assert request_entry["status"] == "pending"

    resolve_response = client.post(
        f"/api/admin/password-reset/requests/{request_entry['id']}/resolve",
        json={"resolution_note": "Reset completed"},
        headers=admin_headers,
    )
    assert resolve_response.status_code == 200
    resolved_payload = resolve_response.json()["data"]
    assert resolved_payload["status"] == "resolved"
