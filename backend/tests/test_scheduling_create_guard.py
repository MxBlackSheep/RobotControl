from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient
import pytest

import backend.api.scheduling as scheduling_api
from backend.main import app
from backend.models import ScheduledExperiment
from backend.services.auth import get_current_user


@pytest.fixture
def stored_schedule(tmp_path, monkeypatch):
    from backend.services.scheduling import sqlite_database
    from backend.tests.test_sqlite_safety import engine
    monkeypatch.setattr(sqlite_database, 'get_data_path', lambda: tmp_path)
    storage = sqlite_database.SQLiteSchedulingDatabase()
    scheduler = engine(storage)
    schedule = ScheduledExperiment('paused', 'Paused', 'paused.med', 'once', created_by='tester', is_active=False)
    assert storage.create_schedule(schedule)
    monkeypatch.setattr(scheduling_api, 'get_services', lambda: (scheduler, scheduler.db_manager, None))
    return storage, scheduler, schedule


def test_paused_delete_uses_engine_locks(stored_schedule, monkeypatch):
    storage, scheduler, schedule = stored_schedule
    delete = storage.delete_schedule
    def locked_delete(*args, **kwargs):
        assert scheduler._schedules_lock._is_owned()
        assert scheduler._jobs_lock._is_owned()
        return delete(*args, **kwargs)
    monkeypatch.setattr(storage, 'delete_schedule', locked_delete)
    response = client.delete('/api/scheduling/paused', headers={'If-Unmodified-Since': schedule.updated_at.isoformat()})
    assert response.status_code == 200, response.text
    assert storage.get_schedule_by_id('paused') is None
    assert 'deleted_via' not in response.json()['data']


def test_paused_delete_rejects_stale_version(stored_schedule):
    storage, scheduler, schedule = stored_schedule
    response = client.delete('/api/scheduling/paused', headers={'If-Unmodified-Since': '2000-01-01T00:00:00'})
    assert response.status_code == 409, response.text
    assert storage.get_schedule_by_id('paused').to_dict() == schedule.to_dict()


def test_refused_update_writes_nothing(stored_schedule, monkeypatch):
    storage, scheduler, schedule = stored_schedule
    monkeypatch.setattr(scheduler, 'update_schedule', lambda *args, **kwargs: False)
    before = storage.db_path.read_bytes()
    response = client.put('/api/scheduling/paused', json={'estimated_duration': 45})
    assert response.status_code == 400 and response.json()['detail'] == 'Failed to update schedule', response.text
    assert storage.db_path.read_bytes() == before
    assert storage.get_schedule_by_id('paused').to_dict() == schedule.to_dict()


class FakeScheduler:
    def __init__(self):
        self._schedules_lock = RLock()
        self.add_calls: List[ScheduledExperiment] = []
        self.update_calls: List[ScheduledExperiment] = []

    def add_schedule(self, experiment: ScheduledExperiment) -> bool:
        self.add_calls.append(experiment)
        return True

    def update_schedule(self, experiment: ScheduledExperiment, **kwargs) -> bool:
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

    def update_scheduled_experiment(self, schedule: ScheduledExperiment, **kwargs) -> bool:
        self.schedules[schedule.schedule_id] = schedule
        return True


# Local access is decided by the socket peer; x-forwarded-for can only restrict it.
# Requests come like the page's: the header the server requires for a change without a Bearer token.
client = TestClient(app, client=("127.0.0.1", 50000), headers={"X-Requested-With": "RobotControl"})


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


@pytest.mark.parametrize("threshold", [0, -1, 1.5, True, None, "3"])
def test_create_rejects_invalid_log_inactivity_threshold(monkeypatch, threshold):
    scheduler = FakeScheduler()
    monkeypatch.setattr(scheduling_api, "get_services", lambda: (scheduler, FakeDB(), object()))
    response = client.post("/api/scheduling/create", json={
        "experiment_name": "test", "experiment_path": "test.med", "schedule_type": "once",
        "estimated_duration": 30, "log_inactivity_threshold_minutes": threshold,
    }, headers={"x-forwarded-for": "127.0.0.1"})
    assert response.status_code == 400
    assert not scheduler.add_calls


def test_threshold_defaults_and_update_omission_preserves_value(monkeypatch):
    scheduler, db = FakeScheduler(), FakeDB()
    monkeypatch.setattr(scheduling_api, "get_services", lambda: (scheduler, db, object()))
    response = client.post("/api/scheduling/create", json={
        "experiment_name": "test", "experiment_path": "test.med", "schedule_type": "once", "estimated_duration": 30,
    }, headers={"x-forwarded-for": "127.0.0.1"})
    assert response.status_code == 200
    schedule = scheduler.add_calls[0]
    assert schedule.log_inactivity_threshold_minutes == 3
    schedule.log_inactivity_threshold_minutes = 7
    db.schedules[schedule.schedule_id] = schedule
    response = client.put(f"/api/scheduling/{schedule.schedule_id}", json={"estimated_duration": 45}, headers={"x-forwarded-for": "127.0.0.1"})
    assert response.status_code == 200
    assert scheduler.update_calls[0].log_inactivity_threshold_minutes == 7
    response = client.put(f"/api/scheduling/{schedule.schedule_id}", json={"log_inactivity_threshold_minutes": 9}, headers={"x-forwarded-for": "127.0.0.1"})
    assert response.status_code == 200
    assert scheduler.update_calls[-1].log_inactivity_threshold_minutes == 9


def test_create_schedule_allows_same_start_minute(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_db = FakeDB()
    monkeypatch.setattr(
        scheduling_api,
        "get_services",
        lambda: (fake_scheduler, fake_db, object()),
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
        lambda: (fake_scheduler, fake_db, object()),
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
        lambda: (fake_scheduler, fake_db, object()),
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
        lambda: (fake_scheduler, fake_db, object()),
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
