import os
import smtplib
from types import SimpleNamespace

import pytest

from backend.models import ScheduledExperiment
from backend.services.notifications import EmailNotificationService
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


@pytest.fixture(autouse=True)
def clear_smtp_env(monkeypatch):
    for key in [
        "PYROBOT_SMTP_HOST",
        "PYROBOT_SMTP_PORT",
        "PYROBOT_SMTP_USERNAME",
        "PYROBOT_SMTP_PASSWORD",
        "PYROBOT_SMTP_FROM",
        "PYROBOT_SMTP_TO",
        "PYROBOT_SMTP_USE_TLS",
        "PYROBOT_SMTP_USE_SSL",
        "PYROBOT_ALERT_RECIPIENTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def test_email_service_disabled_returns_false(monkeypatch):
    service = EmailNotificationService()
    assert service.send("subject", "body") is False


def test_email_service_sends_when_configured(monkeypatch):
    monkeypatch.setenv("PYROBOT_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("PYROBOT_SMTP_PORT", "1025")
    monkeypatch.setenv("PYROBOT_SMTP_FROM", "noreply@test")
    monkeypatch.setenv("PYROBOT_ALERT_RECIPIENTS", "ops@test")
    monkeypatch.setenv("PYROBOT_SMTP_USE_TLS", "0")
    monkeypatch.setenv("PYROBOT_SMTP_USE_SSL", "0")

    dummy = DummySMTP("smtp.test", 1025)
    monkeypatch.setattr(smtplib, "SMTP", lambda host, port, timeout=None: DummySMTP(host, port, timeout))
    service = EmailNotificationService()

    sent = service.send("subject", "body")
    assert sent is True


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
