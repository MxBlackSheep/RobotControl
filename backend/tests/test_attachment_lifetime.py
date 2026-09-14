from types import SimpleNamespace
from unittest.mock import Mock

from backend.services.notifications import SchedulingNotificationService


def test_preparation_failure_removes_already_converted_trace(tmp_path):
    converted = tmp_path / "trace.log"
    converted.write_text("run trace")
    service = object.__new__(SchedulingNotificationService)
    service._render_alert_subject = Mock(return_value="Alert")
    service._render_alert_body = Mock(return_value=(["Body"], []))
    service._convert_trc_to_log = Mock(return_value=converted)
    service._collect_recent_rolling_clips = Mock(side_effect=OSError("disk unavailable"))
    service.email = Mock()
    result = service.schedule_alert(SimpleNamespace(), SimpleNamespace(), contacts=[],
                                    trigger="log_inactive", context={}, trace_path=tmp_path / "run.trc", exact_trace=True)
    assert not result.sent
    assert "disk unavailable" in result.error
    assert not converted.exists()
    service.email.send.assert_not_called()

