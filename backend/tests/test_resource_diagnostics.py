import json
import time

from backend.services.resource_diagnostics import ResourceDiagnostics, runtime_counts


def test_diagnostics_lifecycle_and_bounded_output(tmp_path):
    recorder = ResourceDiagnostics(tmp_path, interval=0.01)
    recorder.start()
    worker = recorder._thread
    recorder.start()
    assert recorder._thread is worker
    deadline = time.monotonic() + 5
    path = tmp_path / f"resources-{recorder.pid}.jsonl"
    while (not path.exists() or not path.stat().st_size) and time.monotonic() < deadline:
        time.sleep(.01)
    recorder.stop()
    recorder.stop()
    assert not worker.is_alive()
    assert not recorder._processes
    row = json.loads(path.read_text().splitlines()[0])
    assert row["system"]["total_bytes"] > 0
    own = next(p for p in row["processes"] if p["pid"] == recorder.pid)
    assert own["working_set_bytes"] > 0
    assert "private_bytes" in own
    assert runtime_counts()["python_threads"] > 0
