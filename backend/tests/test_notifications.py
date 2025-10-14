import os
import smtplib
from pathlib import Path

import pytest

from backend.models import (
    ScheduledExperiment,
    NotificationSettings,
    NotificationContact,
    JobExecution,
)
from backend.services.notifications import EmailNotificationService, SchedulingNotificationService
from backend.services.scheduling.database_manager import SchedulingDatabaseManager


class DummySMTP:
    def __init__(self, host, port, timeout=None):  # noqa: D401
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sent_messages = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def starttls(self):
        return None

    def login(self, username, password):
        self.username = username
        self.password = password

    def send_message(self, message):
        self.sent_messages.append(message)


class StubEmailService:
    def __init__(self):
        self.calls = []
        self.config = type(
            "Cfg",
            (),
            {"is_enabled": True, "recipients": [], "manual_recovery_recipients": []},
        )()
        self.last_error = None

    def send(self, subject, body, *, to=None, attachments=None):
        self.calls.append(
            {
                "subject": subject,
                "body": body,
                "recipients": list(to or []),
                "attachments": [str(path) for path in (attachments or [])],
            }
        )
        return True

    def get_manual_recovery_recipients(self):
        return list(self.config.manual_recovery_recipients)


@pytest.fixture(autouse=True)
def clear_smtp_env(monkeypatch):
    for key in [
        "ROBOTCONTROL_SMTP_HOST",
        "ROBOTCONTROL_SMTP_PORT",
        "ROBOTCONTROL_SMTP_USERNAME",
        "ROBOTCONTROL_SMTP_PASSWORD",
        "ROBOTCONTROL_SMTP_FROM",
        "ROBOTCONTROL_SMTP_TO",
        "ROBOTCONTROL_SMTP_USE_TLS",
        "ROBOTCONTROL_SMTP_USE_SSL",
        "ROBOTCONTROL_ALERT_RECIPIENTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def test_email_service_disabled_returns_false(monkeypatch):
    monkeypatch.setattr(
        "backend.services.notifications._load_notification_settings",
        lambda: NotificationSettings(),
    )

    service = EmailNotificationService()
    assert service.send("subject", "body") is False
    assert service.last_error is not None


def test_email_service_sends_when_configured(monkeypatch):
    stub_settings = NotificationSettings(
        host="smtp.test",
        port=1025,
        sender="noreply@test",
        use_tls=False,
        use_ssl=False,
        manual_recovery_recipients=["ops@test"],
        password_encrypted="token",
    )
    monkeypatch.setattr(
        "backend.services.notifications._load_notification_settings",
        lambda: stub_settings,
    )
    monkeypatch.setattr(
        "backend.services.notifications.decrypt_secret",
        lambda token: "secret" if token else None,
    )

    dummy = DummySMTP("smtp.test", 1025)
    monkeypatch.setattr(smtplib, "SMTP", lambda host, port, timeout=None: DummySMTP(host, port, timeout))
    service = EmailNotificationService()

    sent = service.send("subject", "body")
    assert sent is True


def test_schedule_alert_uses_rolling_clip_fallback(monkeypatch, tmp_path):
    video_root = tmp_path / "videos"
    rolling_dir = video_root / "rolling_clips"
    experiments_dir = video_root / "experiments"
    rolling_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    # Create six clips with increasing modification times.
    for idx in range(6):
        clip = rolling_dir / f"clip_{idx}.avi"
        clip.write_text("clip")
        os.utime(clip, (idx + 1, idx + 1))

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("backend.services.notifications.VIDEO_PATH", str(video_root))
    monkeypatch.setenv("ROBOTCONTROL_HAMILTON_LOG_PATH", str(logs_dir))

    service = SchedulingNotificationService()
    stub_email = StubEmailService()
    service.email = stub_email  # type: ignore[assignment]

    schedule = ScheduledExperiment(
        schedule_id="sched-1",
        experiment_name="Demo",
        experiment_path="C:/Methods/demo.med",
        schedule_type="once",
        estimated_duration=10,
        notification_contacts=["contact-1"],
    )
    execution = JobExecution(
        execution_id="exec-1",
        schedule_id="sched-1",
        status="running",
    )
    contact = NotificationContact(
        contact_id="contact-1",
        display_name="Ops",
        email_address="ops@test",
        is_active=True,
    )

    summary_clip = tmp_path / "summary.mp4"
    summary_clip.write_text("summary")

    monkeypatch.setattr(
        SchedulingNotificationService,
        "_transcode_clips_to_mp4",
        lambda self, clips: summary_clip,
    )

    result = service.schedule_alert(
        schedule,
        execution,
        contacts=[contact],
        trigger="long_running",
        context={},
    )

    assert stub_email.calls, "Expected email send to be invoked"
    attachments = stub_email.calls[0]["attachments"]
    assert attachments == [str(summary_clip)]
    assert any("summary" in note.lower() for note in result.attachment_notes)


def test_manual_recovery_prefers_configured_recipients():
    service = SchedulingNotificationService()
    stub_email = StubEmailService()
    stub_email.config.manual_recovery_recipients = ["manual@test"]
    service.email = stub_email  # type: ignore[assignment]

    schedule = ScheduledExperiment(
        schedule_id="sched-1",
        experiment_name="Demo Recovery",
        experiment_path="C:/Methods/demo.med",
        schedule_type="once",
        estimated_duration=30,
        notification_contacts=[],
    )

    service.manual_recovery_required(schedule, note=None, actor="ops")

    assert stub_email.calls, "Expected manual recovery email to be sent"
    assert stub_email.calls[0]["recipients"] == ["manual@test"]


def test_should_block_due_to_abort_detects_abort(monkeypatch):
    from backend.services import scheduling as scheduling_services

    class StubSQLiteDB:
        pass

    class StubDBService:
        def __init__(self, rows):
            self.rows = rows

        def execute_query(self, query, params):
            return {"rows": self.rows}

    stub_rows = [{"RunState": "64"}]
    stub_db = StubDBService(stub_rows)

    monkeypatch.setattr(
        scheduling_services.database_manager,  # type: ignore[attr-defined]
        "get_sqlite_scheduling_database",
        lambda: StubSQLiteDB(),
    )
    monkeypatch.setattr(
        scheduling_services.database_manager,
        "get_database_service",
        lambda: stub_db,
    )

    manager = SchedulingDatabaseManager()
    manager._hamilton_db_available = True
    manager.main_db_service = stub_db

    experiment = ScheduledExperiment(
        schedule_id="demo",
        experiment_name="SampleRun",
        experiment_path=r"C:\\Methods\\SampleRun.med",
        schedule_type="once",
        estimated_duration=30,
    )

    note = manager.should_block_due_to_abort(experiment)
    assert note is not None
    assert "Aborted" in note
