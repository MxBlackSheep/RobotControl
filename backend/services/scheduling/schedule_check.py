"""Schedule field validation without filesystem or live-service reads."""
import math
from pathlib import Path

from backend.models import ScheduledExperiment, TimeoutConfig
from backend.utils.record_check import CheckError

INTERVAL_TYPE_DEFAULT_HOURS = {'daily': 24.0, 'weekly': 168.0}
INTERVAL_SCHEDULE_TYPES = {'interval'} | set(INTERVAL_TYPE_DEFAULT_HOURS)
SUPPORTED_SCHEDULE_TYPES = {'once'} | INTERVAL_SCHEDULE_TYPES
SUPPORTED_TIMEOUT_ACTIONS = {'continue', 'run_cleanup_and_terminate'}


def _normalize_schedule_request(schedule_type, interval_hours):
    if not isinstance(schedule_type, str):
        raise CheckError('schedule_type must be a string', 'The schedule has no repeat type')
    normalized = schedule_type.strip().lower()
    if normalized not in SUPPORTED_SCHEDULE_TYPES:
        raise CheckError(f"Unsupported schedule_type '{schedule_type}'", f"The schedule type '{schedule_type}' is no longer supported")
    if normalized == 'interval':
        if interval_hours is None:
            raise CheckError('interval_hours is required for interval schedules', 'The interval schedule has no number of hours')
        try:
            hours = float(interval_hours)
        except (TypeError, ValueError):
            raise CheckError('interval_hours must be a numeric value', "The interval's hours are not a number") from None
        if not math.isfinite(hours) or hours <= 0:
            raise CheckError('interval_hours must be greater than zero', "The interval's hours are not above zero")
        return normalized, hours
    return normalized, INTERVAL_TYPE_DEFAULT_HOURS.get(normalized)


def _normalize_timeout_config(raw):
    if raw is None:
        return TimeoutConfig()
    if not isinstance(raw, dict):
        raise CheckError('timeout_config must be an object', 'The timeout settings cannot be read')
    minutes = raw.get('timeout_minutes')
    if minutes not in (None, ''):
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise CheckError('timeout_minutes must be an integer', 'The timeout minutes are not a whole number') from None
        if minutes <= 0:
            raise CheckError('timeout_minutes must be greater than zero', 'The timeout minutes are not above zero')
    else:
        minutes = None
    action = str(raw.get('action', 'continue')).strip().lower() or 'continue'
    if action not in SUPPORTED_TIMEOUT_ACTIONS:
        raise CheckError(f"Unsupported timeout action '{action}'", f"The timeout action '{action}' is not supported")
    path = name = None
    if action == 'run_cleanup_and_terminate':
        path = raw.get('cleanup_experiment_path')
        if not isinstance(path, str) or not path.strip():
            raise CheckError('cleanup_experiment_path is required when timeout action is run_cleanup_and_terminate',
                             'The timeout has no cleanup method')
        name = raw.get('cleanup_experiment_name')
        name = name.strip() if isinstance(name, str) and name.strip() else Path(path).stem
    return TimeoutConfig(minutes, action, path, name)


def check_schedule(fields):
    """Return a schedule or raise CheckError (route text, review reason); never inspect files or live services."""
    fields = dict(fields)
    runner = fields.get('runner', 'venus')
    for field, label in [('experiment_name', 'Experiment name'), ('experiment_path', 'Experiment path')]:
        if not isinstance(fields.get(field), str) or not fields[field]:
            raise CheckError(f'{label} is required')
    duration = fields.get('estimated_duration', 60)
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise CheckError('Estimated duration must be positive')
    fields['schedule_type'], fields['interval_hours'] = _normalize_schedule_request(
        fields.get('schedule_type'), fields.get('interval_hours'))
    timeout = _normalize_timeout_config(fields.get('timeout_config'))
    if runner == 'pyhsl' and timeout.action != 'continue':
        raise CheckError('PyHSL schedules cannot run a cleanup method')
    if not isinstance(fields.get('parameters', {}), dict):
        raise CheckError('parameters must be an object', 'The protocol parameters cannot be read')
    if fields.get('prerequisites'):
        tokens = fields['prerequisites']
        shown = ', '.join(map(str, tokens)) if isinstance(tokens, list) else str(tokens)
        raise CheckError(f"Old preparation step {tokens} is no longer supported",
                         f"Old preparation step '{shown}' is no longer supported")
    if fields.get('preparation') is not None and not isinstance(fields['preparation'], dict):
        raise CheckError('preparation must be {tool_id, inputs}', 'The database step cannot be read')
    fields['timeout_config'] = timeout.to_dict()
    return ScheduledExperiment.from_dict(fields)
