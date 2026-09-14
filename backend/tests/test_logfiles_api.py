import os
import gzip
import zipfile
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

import backend.api.logfiles as logfiles_api
from backend.main import app
from backend.services.auth import get_current_user


client = TestClient(app)


def _override_user() -> Dict[str, Any]:
    return {
        "user_id": "1",
        "username": "tester",
        "role": "admin",
    }


def setup_function():
    app.dependency_overrides[get_current_user] = _override_user


def teardown_function():
    app.dependency_overrides.clear()


def _set_test_sources(monkeypatch, tmp_path: Path) -> Dict[str, Path]:
    primary = tmp_path / "primary"
    secondary = tmp_path / "secondary"
    missing = tmp_path / "missing"
    primary.mkdir(parents=True, exist_ok=True)
    secondary.mkdir(parents=True, exist_ok=True)

    test_sources = {
        "primary": {"label": "Primary", "path": str(primary)},
        "secondary": {"label": "Secondary", "path": str(secondary)},
        "missing": {"label": "Missing", "path": str(missing)},
    }
    monkeypatch.setattr(logfiles_api, "LOGFILE_SOURCES", test_sources)
    return {"primary": primary, "secondary": secondary, "missing": missing}


def test_logfiles_sources_reports_accessibility(monkeypatch, tmp_path):
    _set_test_sources(monkeypatch, tmp_path)

    response = client.get("/api/logfiles/sources", headers={"x-forwarded-for": "127.0.0.1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = {row["id"]: row for row in payload["data"]}
    assert data["primary"]["exists"] is True
    assert data["primary"]["accessible"] is True
    assert data["missing"]["exists"] is False


def test_logfiles_browse_and_preview_text(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    log_dir = roots["primary"] / "session"
    log_dir.mkdir()
    log_file = log_dir / "run.trc"
    log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

    browse_response = client.get(
        "/api/logfiles/browse",
        params={"source_id": "primary", "relative_path": "session"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    assert browse_response.status_code == 200
    browse_payload = browse_response.json()
    assert browse_payload["success"] is True
    assert browse_payload["data"]["items"][0]["name"] == "run.trc"

    preview_response = client.get(
        "/api/logfiles/preview",
        params={"source_id": "primary", "relative_path": "session/run.trc", "mode": "tail"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["success"] is True
    assert "line3" in preview_payload["data"]["content"]
    assert preview_payload["data"]["is_binary"] is False


def test_logfiles_browse_rejects_path_traversal(monkeypatch, tmp_path):
    _set_test_sources(monkeypatch, tmp_path)

    response = client.get(
        "/api/logfiles/browse",
        params={"source_id": "primary", "relative_path": "../secret"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False


def test_logfiles_browse_newest_first_and_limited(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    folder = roots["primary"] / "many"
    folder.mkdir()

    for i in range(210):
        path = folder / f"file_{i:03d}.trc"
        path.write_text(f"line {i}\n", encoding="utf-8")
        # Ensure deterministic modified ordering (newer = larger timestamp)
        ts = 1_700_000_000 + i
        path.touch()
        os.utime(path, (ts, ts))

    response = client.get(
        "/api/logfiles/browse",
        params={"source_id": "primary", "relative_path": "many"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["total_items"] == 210
    assert data["returned_items"] == 200
    assert data["truncated"] is True
    assert data["max_items"] == 200
    assert data["items"][0]["name"] == "file_209.trc"
    assert data["items"][1]["name"] == "file_208.trc"


def test_logfiles_preview_gzip(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    gz_path = roots["primary"] / "robot.log.gz"
    with gzip.open(gz_path, "wb") as handle:
        handle.write(b"alpha\nbeta\ngamma\n")

    response = client.get(
        "/api/logfiles/preview",
        params={"source_id": "primary", "relative_path": "robot.log.gz", "mode": "tail"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["archive_type"] == "gz"
    assert "gamma" in payload["data"]["content"]


def test_logfiles_preview_utf16_trc_tail_not_marked_binary(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    trc_path = roots["primary"] / "huge.trc"
    lines = [f"row {i:04d}" for i in range(800)]
    trc_path.write_bytes(("\n".join(lines) + "\n").encode("utf-16-le"))

    response = client.get(
        "/api/logfiles/preview",
        params={
            "source_id": "primary",
            "relative_path": "huge.trc",
            "mode": "tail",
            "max_bytes": 101,  # intentionally odd to force misaligned UTF-16 tail reads
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["is_binary"] is False
    assert payload["data"]["content"] is not None
    assert "row 079" in payload["data"]["content"]


def test_logfiles_zip_archive_browse_and_preview(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    zip_path = roots["primary"] / "history.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("today/run1.txt", "hello\nworld\n")
        zf.writestr("today/sub/info.md", "# header\ncontent\n")

    browse_response = client.get(
        "/api/logfiles/archive/browse",
        params={"source_id": "primary", "archive_relative_path": "history.zip", "entry_path": "today"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert browse_response.status_code == 200
    browse_payload = browse_response.json()
    items = {item["name"]: item for item in browse_payload["data"]["items"]}
    assert "run1.txt" in items
    assert "sub" in items
    assert items["sub"]["is_directory"] is True

    preview_response = client.get(
        "/api/logfiles/archive/preview",
        params={
            "source_id": "primary",
            "archive_relative_path": "history.zip",
            "entry_path": "today/run1.txt",
            "mode": "head",
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["data"]["archive_type"] == "zip"
    assert "hello" in preview_payload["data"]["content"]


def test_logfiles_preview_locked_file_returns_423(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    (roots["primary"] / "busy.log").write_text("content", encoding="utf-8")

    def _raise_locked(*args, **kwargs):
        error = PermissionError("locked")
        error.winerror = 32  # Windows sharing violation, distinct from access denied.
        raise error

    monkeypatch.setattr(logfiles_api, "_read_regular_file_preview", _raise_locked)

    response = client.get(
        "/api/logfiles/preview",
        params={"source_id": "primary", "relative_path": "busy.log"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 423
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FILE_LOCKED"


def test_hamilton_logfiles_source_shows_only_trc_and_blocks_other_preview(monkeypatch, tmp_path):
    hamilton_root = tmp_path / "hamilton"
    hamilton_root.mkdir(parents=True, exist_ok=True)
    (hamilton_root / "alpha.trc").write_text("trace", encoding="utf-8")
    (hamilton_root / "notes.txt").write_text("note", encoding="utf-8")
    (hamilton_root / "subdir").mkdir()

    monkeypatch.setattr(
        logfiles_api,
        "LOGFILE_SOURCES",
        {
            "hamilton_logfiles": {
                "label": "Hamilton LogFiles",
                "path": str(hamilton_root),
                "allowed_extensions": [".trc"],
            }
        },
    )

    browse_response = client.get(
        "/api/logfiles/browse",
        params={"source_id": "hamilton_logfiles", "relative_path": ""},
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    assert browse_response.status_code == 200
    names = [item["name"] for item in browse_response.json()["data"]["items"]]
    assert "subdir" in names
    assert "alpha.trc" in names
    assert "notes.txt" not in names

    preview_response = client.get(
        "/api/logfiles/preview",
        params={"source_id": "hamilton_logfiles", "relative_path": "notes.txt"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    assert preview_response.status_code == 400
    payload = preview_response.json()
    assert payload["success"] is False
    assert "not enabled" in payload["message"].lower()


def test_logfiles_remote_can_access_allowed_source_but_not_local_only(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    (roots["primary"] / "remote_ok.trc").write_text("remote ok", encoding="utf-8")
    (roots["secondary"] / "local_only.trc").write_text("local only", encoding="utf-8")

    monkeypatch.setattr(
        logfiles_api,
        "LOGFILE_SOURCES",
        {
            "python_log": {
                "label": "Python Log",
                "path": str(roots["primary"]),
                "access_scope": "all_authenticated",
            },
            "robotcontrol_logs": {
                "label": "RobotControl Logs",
                "path": str(roots["secondary"]),
                "access_scope": "local_only",
            },
        },
    )

    sources_response = client.get("/api/logfiles/sources", headers={"x-forwarded-for": "8.8.8.8"})
    assert sources_response.status_code == 200
    sources_payload = {item["id"]: item for item in sources_response.json()["data"]}
    assert sources_payload["python_log"]["permissions"]["can_access"] is True
    assert sources_payload["robotcontrol_logs"]["permissions"]["can_access"] is False

    remote_ok_response = client.get(
        "/api/logfiles/browse",
        params={"source_id": "python_log"},
        headers={"x-forwarded-for": "8.8.8.8"},
    )
    assert remote_ok_response.status_code == 200

    remote_blocked_response = client.get(
        "/api/logfiles/browse",
        params={"source_id": "robotcontrol_logs"},
        headers={"x-forwarded-for": "8.8.8.8"},
    )
    assert remote_blocked_response.status_code == 403


def test_paged_search_reaches_old_files_and_has_deterministic_ties(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    for i in range(251):
        path = roots["primary"] / f"file_{i:03d}.TRC"
        path.write_text("data", encoding="utf-8")
        os.utime(path, (1700000000, 1700000000))
    headers = {"x-forwarded-for": "127.0.0.1"}
    params = {"source_id":"primary", "limit":25, "sort_by":"name", "sort_direction":"asc"}
    response = client.get("/api/logfiles/browse", params={**params,"page":11}, headers=headers).json()["data"]
    assert response["items"][0]["name"] == "file_250.TRC"
    assert response["relative_path"] == ""
    found = client.get("/api/logfiles/browse", params={**params,"search":"FILE_250","file_type":"traces"}, headers=headers).json()["data"]
    assert found["total_items"] == 1
    assert client.get("/api/logfiles/browse", params={**params,"limit":201}, headers=headers).status_code == 422
    assert client.get("/api/logfiles/browse", params={**params,"modified_from":"2026-01-02","modified_to":"2026-01-01"}, headers=headers).status_code == 400


def test_zip_search_and_paging_beyond_200(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    with zipfile.ZipFile(roots["primary"] / "many.zip", "w") as archive:
        for i in range(225): archive.writestr(f"nested/run_{i:03d}.log", "hello")
    headers = {"x-forwarded-for":"127.0.0.1"}
    params = {"source_id":"primary","archive_relative_path":"many.zip","entry_path":"nested","limit":25,"sort_by":"name","sort_direction":"asc"}
    data = client.get("/api/logfiles/archive/browse", params={**params,"page":9}, headers=headers).json()["data"]
    assert data["items"][0]["name"] == "run_200.log"
    data = client.get("/api/logfiles/archive/browse", params={**params,"search":"224"}, headers=headers).json()["data"]
    assert data["total_items"] == 1 and data["items"][0]["name"] == "run_224.log"


def test_archive_routes_preserve_source_extension_restrictions(monkeypatch, tmp_path):
    roots = _set_test_sources(monkeypatch, tmp_path)
    with zipfile.ZipFile(roots["primary"] / "hidden.zip", "w") as archive: archive.writestr("secret.txt", "not a trace")
    logfiles_api.LOGFILE_SOURCES["primary"]["allowed_extensions"] = [".trc"]
    for endpoint in ["browse", "preview"]:
        response = client.get(f"/api/logfiles/archive/{endpoint}", params={"source_id":"primary","archive_relative_path":"hidden.zip","entry_path":"secret.txt"}, headers={"x-forwarded-for":"127.0.0.1"})
        assert response.status_code == 400
