"""HTTP/SQLite run-start contract check; no robot or SQL Server is started.

Run: uv run --locked python backend/e2e/run_timing_check.py
Failure cases: prepare loses its offset; restart loses the original instant;
legacy local timestamps reach browsers without an offset; winter/summer or
repeated-hour qualified starts change instant; missing/invalid starts fail the
whole queue endpoint. Exports actual HTTP payloads for the browser timing probe.
Legacy naive starts assume the original server timezone; an autumn repeated hour
cannot be recovered unambiguously because the old record contains no offset.
"""
import argparse
import json
import sys
import tempfile
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import scheduling
from backend.models import JobExecution, ScheduledExperiment
from backend.services.auth import get_current_user
from backend.services.scheduling.run_log_monitor import RunLogMonitor
from backend.services.scheduling.run_log_store import RunLogStore
from backend.services.scheduling.scheduler_engine import SchedulerEngine
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase

def run(evidence):
    evidence.mkdir(parents=True, exist_ok=True)
    checks, payloads = [], {}
    with tempfile.TemporaryDirectory(prefix='rc-run-timing-') as folder:
        db = SQLiteSchedulingDatabase(str(Path(folder) / 'scheduling.db'))
        schedule = ScheduledExperiment('timing', 'Timing fixture run', 'Timing.hsl', 'once', estimated_duration=60)
        manager = SimpleNamespace(sqlite_db=db, get_schedule_by_id=lambda _: schedule)
        reader = SimpleNamespace(boundary=lambda _: (datetime.now().isoformat(), ''))
        monitor = RunLogMonitor(manager, reader=reader, store=RunLogStore(db), directory=folder)
        monitor.prepare(schedule, JobExecution('timing-execution', 'timing', 'running'), schedule.experiment_path)
        original = monitor.snapshot('timing-execution').launched_at
        assert datetime.fromisoformat(original).utcoffset() is not None, original
        monitor = RunLogMonitor(manager, reader=reader, store=RunLogStore(db), directory=folder)
        monitor.restore()
        assert monitor.snapshot('timing-execution').launched_at == original
        checks.append('prepare and SQLite restore retain offset-qualified launch instant')

        engine = SchedulerEngine.__new__(SchedulerEngine)
        engine._schedules_lock, engine._jobs_lock = threading.RLock(), threading.RLock()
        engine._active_schedules, engine._queue_runtime = {'timing': schedule}, {}
        engine._running_jobs, engine._queued_backlog = {'timing'}, set()
        engine.run_log_monitor = monitor
        engine.process_monitor = SimpleNamespace(is_hamilton_running=lambda: True)
        recovery = dict(active=False, storage_healthy=True, safety_revision=3, resume_required=False, pending_recoveries=[])
        engine.get_manual_recovery_state = lambda: SimpleNamespace(to_dict=lambda: recovery)
        process = SimpleNamespace(get_status=lambda: SimpleNamespace(is_running=True, process_count=1, availability='busy', last_check=datetime.now()))
        app = FastAPI()
        app.include_router(scheduling.router)
        app.dependency_overrides[get_current_user] = lambda: dict(username='fixture', role='admin')
        cases = {
            'summer': '2026-09-30T13:48:00+01:00',
            'winter': '2026-01-15T13:48:00+00:00',
            'fall_before': '2026-10-25T01:48:00+01:00',
            'fall_after': '2026-10-25T01:48:00+00:00',
            'legacy_summer': '2026-09-30T13:48:00',
            'legacy_winter': '2026-01-15T13:48:00',
            'missing': '',
            'invalid': 'not-a-time',
        }
        with patch.object(scheduling, 'get_services', return_value=(engine, manager, process)), TestClient(app) as client:
            for name, value in cases.items():
                state = monitor.snapshot('timing-execution')
                state.launched_at = value
                monitor.store.save(asdict(state))
                monitor = RunLogMonitor(manager, reader=reader, store=RunLogStore(db), directory=folder)
                monitor.restore()
                engine.run_log_monitor = monitor
                response = client.get('/api/scheduling/status/queue')
                assert response.status_code == 200, response.text
                payload = response.json()
                actual = payload['data']['queue']['running_job_details'][0]['monitoring']['launched_at']
                if name in {'missing', 'invalid'}:
                    assert actual is None, (name, actual)
                else:
                    parsed = datetime.fromisoformat(actual)
                    assert parsed.utcoffset() is not None, (name, actual)
                    expected = datetime.fromisoformat(value)
                    assert parsed.timestamp() == expected.timestamp(), (name, actual)
                payloads[name] = payload
                checks.append(f'{name}: actual HTTP serialization after SQLite restore passed')
    (evidence / 'queue-payloads.json').write_text(json.dumps(payloads, indent=2), encoding='utf-8')
    (evidence / 'backend-results.json').write_text(json.dumps(dict(checks=checks, local_zone=str(datetime.now().astimezone().tzinfo)), indent=2), encoding='utf-8')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'test-output/timezone-review-fix')
    run(parser.parse_args().evidence)
