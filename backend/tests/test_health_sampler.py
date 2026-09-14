from unittest.mock import patch
from backend.services.health_sampler import HealthSampler


def test_health_snapshot_does_not_resample_or_block_for_cpu():
    sampler = HealthSampler()
    with patch('backend.services.health_sampler.psutil.cpu_percent', return_value=12) as cpu:
        first = sampler.sample()
        second = sampler.snapshot()
        assert first == second
        cpu.assert_called_once_with(interval=None)
        second['cpu_percent'] = 99
        assert sampler.snapshot()['cpu_percent'] == 12


def test_health_worker_has_one_owner_and_stops():
    sampler = HealthSampler()
    sampler.start()
    thread = sampler._thread
    sampler.start()
    assert sampler._thread is thread
    sampler.stop()
    sampler.stop()
    assert not thread.is_alive()
