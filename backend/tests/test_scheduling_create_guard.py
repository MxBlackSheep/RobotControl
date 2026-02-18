from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

import backend.api.scheduling as scheduling_api
from backend.main import app
from backend.models import ScheduledExperiment
from backend.services.auth import get_current_user


class FakeScheduler:
    def __init__(self):
        self.add_calls: List[ScheduledExperiment] = []
        self.update_calls: List[ScheduledExperiment] = []

    def add_schedule(self, experiment: ScheduledExperiment) -> bool:
        self.add_calls.append(experiment)
        return True

    def update_schedule(self, experiment: ScheduledExperiment) -> bool:
        self.update_calls.append(experiment)
        return True

    def invalidate_schedule(self, schedule_id: str) -> None:
        return None


class FakeDB:
    def __init__(self):
        self.schedules: Dict[str, ScheduledExperiment] = {}

    def get_notification_contacts(self, include_inactive: bool = False):
        return []

    def get_schedule_by_id(self, schedule_id: str) -> Optional[ScheduledExperiment]:
        return self.schedules.get(schedule_id)

    def update_scheduled_experiment(self, schedule: ScheduledExperiment) -> bool:
        self.schedules[schedule.schedule_id] = schedule
        return True


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


def test_create_schedule_allows_same_start_minute(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_db = FakeDB()
    monkeypatch.setattr(
        scheduling_api,
        "get_services",
        lambda: (fake_scheduler, fake_db, object(), object()),
    )

    future_start = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=45, microsecond=0)
    response = client.post(
        "/api/scheduling/create",
        json={
            "experiment_name": "New",
            "experiment_path": "new.med",
            "schedule_type": "once",
            "start_time": future_start.isoformat(),
            "estimated_duration": 30,
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    assert len(fake_scheduler.add_calls) == 1


def test_create_schedule_preserves_start_time_precision(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_db = FakeDB()
    monkeypatch.setattr(
        scheduling_api,
        "get_services",
        lambda: (fake_scheduler, fake_db, object(), object()),
    )

    future_start = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=7, second=59, microsecond=0)
    response = client.post(
        "/api/scheduling/create",
        json={
            "experiment_name": "MinuteNormalize",
            "experiment_path": "minute.med",
            "schedule_type": "once",
            "start_time": future_start.isoformat(),
            "estimated_duration": 30,
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    assert fake_scheduler.add_calls
    created = fake_scheduler.add_calls[0]
    assert created.start_time is not None
    assert created.start_time.second == 59
    assert created.start_time.microsecond == 0


def test_update_schedule_allows_same_start_minute(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_db = FakeDB()
    fake_db.schedules["target-1"] = ScheduledExperiment(
        schedule_id="target-1",
        experiment_name="Target",
        experiment_path=r"C:\\Hamilton\\Methods\\target.med",
        schedule_type="once",
        start_time=datetime(2026, 2, 17, 10, 0, 0),
        estimated_duration=30,
    )
    monkeypatch.setattr(
        scheduling_api,
        "get_services",
        lambda: (fake_scheduler, fake_db, object(), object()),
    )

    response = client.put(
        "/api/scheduling/target-1",
        json={"start_time": "2026-02-17T10:15:42"},
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 200
    assert len(fake_scheduler.update_calls) == 1
    updated = fake_scheduler.update_calls[0]
    assert updated.start_time is not None
    assert updated.start_time.second == 42


def test_create_schedule_rejects_past_start_time(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_db = FakeDB()
    monkeypatch.setattr(
        scheduling_api,
        "get_services",
        lambda: (fake_scheduler, fake_db, object(), object()),
    )

    past_start = (datetime.now() - timedelta(minutes=5)).replace(microsecond=0)
    response = client.post(
        "/api/scheduling/create",
        json={
            "experiment_name": "PastStart",
            "experiment_path": "past.med",
            "schedule_type": "once",
            "start_time": past_start.isoformat(),
            "estimated_duration": 30,
        },
        headers={"x-forwarded-for": "127.0.0.1"},
    )

    assert response.status_code == 400
    assert "start_time cannot be in the past" in response.text
