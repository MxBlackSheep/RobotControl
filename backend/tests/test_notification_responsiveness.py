"""Slow SMTP must leave the same API event loop available to other requests."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI

from backend.api import scheduling
from backend.models import ScheduledExperiment, NotificationContact
from backend.services.auth import get_current_user


@pytest.mark.parametrize("route,payload", [
    ("/notifications/settings/test", {"recipient": "operator@example.com"}),
    ("/notifications/send", {"schedule_id": "schedule", "subject": "Test", "body": "Test"}),
    ("/schedule/recovery/require", {}),
    ("/schedule/recovery/resolve", {}),
])
@pytest.mark.parametrize("delivery_succeeds", [True, False])
def test_health_responds_while_email_or_recovery_is_waiting(monkeypatch, route, payload, delivery_succeeds):
    app = FastAPI()
    app.include_router(scheduling.router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.dependency_overrides[get_current_user] = lambda: {"username": "tester", "role": "admin"}
    monkeypatch.setattr(scheduling, "log_action", Mock())
    schedule = ScheduledExperiment("schedule", "Demo", "demo.med", "once", notification_contacts=["contact"])
    contact = NotificationContact("contact", "Operator", "operator@example.com")
    db = SimpleNamespace(get_schedule_by_id=lambda key: schedule, get_notification_contacts=lambda **kw: [contact])
    entered, release = threading.Event(), threading.Event()
    worker_ids = []
    send_options = []

    def wait_for_delivery(*args, **kwargs):
        worker_ids.append(threading.get_ident())
        send_options.append(kwargs)
        entered.set()
        assert release.wait(3), "Request handler blocked the API event loop"
        return delivery_succeeds

    email = SimpleNamespace(config=SimpleNamespace(is_enabled=True), last_error="SMTP server greeting timed out", send=wait_for_delivery)
    monkeypatch.setattr(scheduling, "EmailNotificationService", lambda: email)

    def recovery(*args):
        wait_for_delivery()
        return schedule  # Recovery succeeds even when its notification fails.

    engine = SimpleNamespace(require_manual_recovery=recovery, resolve_manual_recovery=recovery, get_manual_recovery_state=lambda: None)
    monkeypatch.setattr(scheduling, "get_services", lambda: (engine, db, None, None))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            pending = asyncio.create_task(client.post("/api/scheduling" + route, json=payload))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert worker_ids[0] != threading.get_ident()
                response = await asyncio.wait_for(client.get("/health"), timeout=0.5)
                assert response.status_code == 200
                assert not pending.done()
            finally:
                release.set()
                response = await pending
            assert response.status_code == (502 if not delivery_succeeds and "/notifications/" in route else 200)
            if "/notifications/" in route:
                assert send_options[0]["timeout_seconds"] == 10
                assert send_options[0]["attempts"] == 1

    asyncio.run(scenario())
