"""A rejected schedule keeps its stored fields for repair and existing-run tracking."""
from dataclasses import dataclass

from backend.utils.datetime import parse_iso_datetime_to_local


@dataclass
class ScheduleReview:
    fields: dict
    review_reason: str

    def to_dict(self):
        return {**self.fields, 'review_reason': self.review_reason}

    def __getattr__(self, name):
        if name not in self.fields:
            raise AttributeError(name)
        value = self.fields[name]
        if name in {'start_time', 'created_at', 'updated_at', 'recovery_marked_at', 'recovery_resolved_at'}:
            return parse_iso_datetime_to_local(value)
        return value
