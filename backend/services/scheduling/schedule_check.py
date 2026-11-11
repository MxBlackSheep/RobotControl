"""Schedule field validation without filesystem or live-service reads."""
import math
from pathlib import Path

from backend.models import ScheduledExperiment, TimeoutConfig

INTERVAL_TYPE_DEFAULT_HOURS = {'hourly': 1.0, 'daily': 24.0, 'weekly': 168.0}
INTERVAL_SCHEDULE_TYPES = {'interval'} | set(INTERVAL_TYPE_DEFAULT_HOURS)
SUPPORTED_SCHEDULE_TYPES = {'once', 'cron'} | INTERVAL_SCHEDULE_TYPES
SUPPORTED_TIMEOUT_ACTIONS = {'continue', 'run_cleanup_and_terminate'}


def _normalize_schedule_request(schedule_type, interval_hours):
    if not isinstance(schedule_type, str):
        raise ValueError('schedule_type must be a string')
    normalized = schedule_type.strip().lower()
    if normalized not in SUPPORTED_SCHEDULE_TYPES:
        raise ValueError(f"Unsupported schedule_type '{schedule_type}'")
    if normalized == 'interval':
        if interval_hours is None:
            raise ValueError('interval_hours is required for interval schedules')
        try:
            hours = float(interval_hours)
        except (TypeError, ValueError):
            raise ValueError('interval_hours must be a numeric value') from None
        if not math.isfinite(hours) or hours <= 0:
            raise ValueError('interval_hours must be greater than zero')
        return normalized, hours
    return normalized, INTERVAL_TYPE_DEFAULT_HOURS.get(normalized)


def _normalize_timeout_config(raw):
    if raw is None:
        return TimeoutConfig()
    if not isinstance(raw, dict):
        raise ValueError('timeout_config must be an object')
    minutes = raw.get('timeout_minutes')
    if minutes not in (None, ''):
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise ValueError('timeout_minutes must be an integer') from None
        if minutes <= 0:
            raise ValueError('timeout_minutes must be greater than zero')
    else:
        minutes = None
    action = str(raw.get('action', 'continue')).strip().lower() or 'continue'
    if action not in SUPPORTED_TIMEOUT_ACTIONS:
        raise ValueError(f"Unsupported timeout action '{action}'")
    path = name = None
    if action == 'run_cleanup_and_terminate':
        path = raw.get('cleanup_experiment_path')
        if not isinstance(path, str) or not path.strip():
            raise ValueError('cleanup_experiment_path is required when timeout action is run_cleanup_and_terminate')
        name = raw.get('cleanup_experiment_name')
        name = name.strip() if isinstance(name, str) and name.strip() else Path(path).stem
    return TimeoutConfig(minutes, action, path, name)


def check_schedule(fields):
    """Return a schedule or raise ValueError; never inspect files or live services."""
    fields = dict(fields)
    runner = fields.get('runner', 'venus')
    for field, label in [('experiment_name', 'Experiment name'), ('experiment_path', 'Experiment path')]:
        if not isinstance(fields.get(field), str) or not fields[field]:
            raise ValueError(f'{label} is required')
    duration = fields.get('estimated_duration', 60)
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Estimated duration must be positive')
    fields['schedule_type'], fields['interval_hours'] = _normalize_schedule_request(
        fields.get('schedule_type'), fields.get('interval_hours'))
    timeout = _normalize_timeout_config(fields.get('timeout_config'))
    if runner == 'pyhsl' and timeout.action != 'continue':
        raise ValueError('PyHSL schedules cannot run a cleanup method')
    if not isinstance(fields.get('parameters', {}), dict):
        raise ValueError('parameters must be an object')
    fields['timeout_config'] = timeout.to_dict()
    return ScheduledExperiment.from_dict(fields)
