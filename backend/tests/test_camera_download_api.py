from fastapi.testclient import TestClient

from backend.main import app
from backend.services.auth import get_current_user
from backend.api import camera as camera_api


client = TestClient(app)


def setup_function():
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "1",
        "username": "tester",
        "role": "user",
    }


def teardown_function():
    app.dependency_overrides.clear()


def _prepare_video_paths(tmp_path, monkeypatch):
    rolling = tmp_path / "rolling_clips"
    experiments = tmp_path / "experiments"
    rolling.mkdir(parents=True, exist_ok=True)
    experiments.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(camera_api, "ROLLING_CLIPS_PATH", rolling)
    monkeypatch.setattr(camera_api, "EXPERIMENTS_PATH", experiments)
    return rolling, experiments


def test_download_full_file_supports_range_headers(tmp_path, monkeypatch):
    rolling, _ = _prepare_video_paths(tmp_path, monkeypatch)
    payload = b"abcdefghijklmnopqrstuvwxyz"
    sample_file = rolling / "sample.avi"
    sample_file.write_bytes(payload)

    response = client.get("/api/camera/recording/sample.avi")

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == str(len(payload))
    assert "etag" in response.headers
    assert "last-modified" in response.headers


def test_download_partial_content_with_range(tmp_path, monkeypatch):
    rolling, _ = _prepare_video_paths(tmp_path, monkeypatch)
    sample_file = rolling / "range_test.avi"
    sample_file.write_bytes(b"0123456789")

    response = client.get(
        "/api/camera/recording/range_test.avi",
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"


def test_download_suffix_range(tmp_path, monkeypatch):
    rolling, _ = _prepare_video_paths(tmp_path, monkeypatch)
    sample_file = rolling / "suffix.avi"
    sample_file.write_bytes(b"ABCDEFGHIJ")

    response = client.get(
        "/api/camera/recording/suffix.avi",
        headers={"Range": "bytes=-3"},
    )

    assert response.status_code == 206
    assert response.content == b"HIJ"
    assert response.headers["content-range"] == "bytes 7-9/10"


def test_download_invalid_range_returns_416(tmp_path, monkeypatch):
    rolling, _ = _prepare_video_paths(tmp_path, monkeypatch)
    sample_file = rolling / "invalid_range.avi"
    sample_file.write_bytes(b"12345")

    response = client.get(
        "/api/camera/recording/invalid_range.avi",
        headers={"Range": "bytes=999-1000"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */5"


def test_if_range_mismatch_falls_back_to_full_download(tmp_path, monkeypatch):
    rolling, _ = _prepare_video_paths(tmp_path, monkeypatch)
    payload = b"resume-content"
    sample_file = rolling / "resume.avi"
    sample_file.write_bytes(payload)

    response = client.get(
        "/api/camera/recording/resume.avi",
        headers={
            "Range": "bytes=3-6",
            "If-Range": 'W/"mismatch"',
        },
    )

    assert response.status_code == 200
    assert response.content == payload
    assert "content-range" not in response.headers


def test_head_request_returns_metadata_without_body(tmp_path, monkeypatch):
    rolling, _ = _prepare_video_paths(tmp_path, monkeypatch)
    payload = b"head-metadata"
    sample_file = rolling / "head.avi"
    sample_file.write_bytes(payload)

    response = client.head("/api/camera/recording/head.avi")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-length"] == str(len(payload))
    assert response.headers["accept-ranges"] == "bytes"
