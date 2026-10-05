from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from backend.services.notifications import SchedulingNotificationService


def test_preparation_failure_removes_already_converted_trace(tmp_path):
    converted = tmp_path / "trace.log"
    converted.write_text("run trace")
    service = object.__new__(SchedulingNotificationService)
    service._alert_email = Mock(return_value=Mock(subject="Alert", text=Mock(return_value="Body")))
    service._convert_trc_to_log = Mock(return_value=converted)
    service._collect_recent_rolling_clips = Mock(side_effect=OSError("disk unavailable"))
    service.email = Mock()
    result = service.schedule_alert(SimpleNamespace(), SimpleNamespace(), contacts=[],
                                    trigger="log_inactive", context={}, trace_path=tmp_path / "run.trc", exact_trace=True)
    assert not result.sent
    assert "disk unavailable" in result.error
    assert not converted.exists()
    service.email.send.assert_not_called()


def test_failed_transcode_releases_capture_writer_and_partial_file(tmp_path, monkeypatch):
    from backend.services import notifications
    service = object.__new__(SchedulingNotificationService)
    clip = tmp_path / "source.avi"
    clip.write_bytes(b"fixture")
    cap = Mock()
    cap.isOpened.return_value = True
    cap.get.return_value = 30
    cap.read.side_effect = OSError("capture failed")
    writer = Mock()
    outputs = []
    def create_writer(path, *args):
        from pathlib import Path
        output = Path(path)
        output.write_bytes(b"partial")
        outputs.append(output)
        return writer
    monkeypatch.setattr(notifications.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(notifications.cv2, "VideoCapture", lambda path: cap)
    service._create_video_writer = create_writer
    with pytest.raises(OSError, match="capture failed"):
        service._transcode_clips_to_mp4([clip])
    cap.release.assert_called_once()
    writer.release.assert_called_once()
    assert not outputs[0].exists()
    assert clip.exists()

