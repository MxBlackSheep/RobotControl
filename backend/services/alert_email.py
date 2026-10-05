"""What a RobotControl alert email says, rendered once as plain text and once as HTML.

`AlertEmail` is built once per alert; `text()` and `html()` show the same content in the
same order, so the plain-text part (also stored in NotificationLog.message) and the HTML
part cannot drift apart. Every dynamic value is escaped in `html()`.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

SUBJECT_PREFIX = "RobotControl alert:"  # Recipients' mail rules match this prefix.
SCHEDULE_FOOTER = "You are receiving this message because you are listed as a notification contact for this schedule."
RECOVERY_FOOTER = ("You are receiving this message because you are listed for RobotControl recovery alerts "
                   "or as a notification contact for this schedule.")

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# tone -> (label, banner background, banner border, label colour, headline colour)
_TONES = {
    "warning": ("Warning", "#FFF6E0", "#D98E04", "#8A5A00", "#3D2A00"),
    "error": ("Problem", "#FDECEC", "#C62828", "#9B1C1C", "#3B0D0D"),
    "neutral": ("Update", "#EEF2F6", "#5B6B7F", "#3F4B5A", "#1F2933"),
}


@dataclass
class AlertEmail:
    tone: str
    headline: str
    experiment: str
    subject_fact: str
    summary: str
    rows: List[Tuple[str, str]] = field(default_factory=list)
    attached: List[str] = field(default_factory=list)
    troubleshooting: List[Tuple[str, str]] = field(default_factory=list)
    footer: str = SCHEDULE_FOOTER
    rows_heading: str = "Run"

    @property
    def subject(self) -> str:
        return _one_line(f"{SUBJECT_PREFIX} {self.experiment} – {self.subject_fact}")

    @property
    def title(self) -> str:
        return f"{self.headline} – {self.experiment}"

    def text(self) -> str:
        lines = [f"{_TONES[self.tone][0]}: {_one_line(self.title)}", "", self.summary]
        if self.rows:
            width = max(len(label) for label, _ in self.rows) + 2
            lines.extend(["", self.rows_heading])
            lines.extend(f"  {(label + ':').ljust(width)} {value}" for label, value in self.rows)
        if self.attached:
            lines.extend(["", "Attached"])
            lines.extend(f"  - {note}" for note in self.attached)
        if self.troubleshooting:
            lines.extend(["", "For troubleshooting"])
            lines.extend(f"  {label}: {value}" for label, value in self.troubleshooting)
        lines.extend(["", self.footer])
        return "\n".join(lines)

    def html(self) -> str:
        e = lambda value: html.escape(str(value), quote=True)
        label, background, border, label_colour, headline_colour = _TONES[self.tone]
        font = "font-family:'Segoe UI',-apple-system,Roboto,Helvetica,Arial,sans-serif;"
        heading = f"{font}font-size:12px;line-height:16px;font-weight:600;color:#4B5563;text-transform:uppercase;letter-spacing:0.04em;padding:0 0 6px 0;"
        sections = []
        if self.rows:
            cells = "".join(
                f'<tr><td valign="top" width="130" style="{font}font-size:14px;line-height:20px;color:#6B7280;padding:6px 12px 6px 0;border-top:1px solid #EEF0F3;">{e(row_label)}</td>'
                f'<td valign="top" style="{font}font-size:14px;line-height:20px;color:#1F2933;padding:6px 0;border-top:1px solid #EEF0F3;word-break:break-word;">{e(value)}</td></tr>'
                for row_label, value in self.rows)
            sections.append(
                f'<tr><td style="padding:20px 24px 0 24px;"><div style="{heading}">{e(self.rows_heading)}</div>'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{cells}</table></td></tr>')
        if self.attached:
            items = "".join(f'<li style="margin:0 0 4px 0;">{e(note)}</li>' for note in self.attached)
            sections.append(
                f'<tr><td style="padding:20px 24px 0 24px;"><div style="{heading}">Attached</div>'
                f'<ul style="{font}font-size:14px;line-height:20px;color:#1F2933;margin:0;padding:0 0 0 20px;">{items}</ul></td></tr>')
        details = "".join(
            f'<div style="word-break:break-all;">{e(item_label)}: {e(value)}</div>' for item_label, value in self.troubleshooting)
        if details:
            details = f'<div style="font-weight:600;color:#4B5563;padding:0 0 4px 0;">For troubleshooting</div>{details}<div style="height:10px;line-height:10px;">&nbsp;</div>'
        return (
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{e(self.subject)}</title></head>'
            '<body style="margin:0;padding:0;background-color:#F3F4F6;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#F3F4F6" style="background-color:#F3F4F6;">'
            '<tr><td align="center" style="padding:24px 12px;">'
            '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#FFFFFF" '
            'style="width:100%;max-width:600px;background-color:#FFFFFF;border:1px solid #E5E7EB;border-radius:6px;">'
            '<tr><td style="padding:24px 24px 0 24px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td bgcolor="{background}" style="background-color:{background};border-left:4px solid {border};padding:12px 16px;">'
            f'<div style="{font}font-size:12px;line-height:16px;font-weight:600;color:{label_colour};text-transform:uppercase;letter-spacing:0.04em;">{e(label)}</div>'
            f'<div style="{font}font-size:18px;line-height:24px;font-weight:600;color:{headline_colour};padding:2px 0 0 0;word-break:break-word;">{e(self.title)}</div>'
            '</td></tr></table></td></tr>'
            f'<tr><td style="{font}font-size:15px;line-height:22px;color:#1F2933;padding:16px 24px 0 24px;">{e(self.summary)}</td></tr>'
            + "".join(sections) +
            '<tr><td style="padding:24px 24px 24px 24px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td bgcolor="#F7F8FA" style="background-color:#F7F8FA;{font}font-size:12px;line-height:18px;color:#6B7280;padding:12px 16px;">'
            f'{details}<div>{e(self.footer)}</div></td></tr></table></td></tr>'
            '</table></td></tr></table></body></html>'
        )


# ----------------------------------------------------------------------
# Value formatting
# ----------------------------------------------------------------------

def _one_line(value: Any) -> str:
    return " ".join(str(value).split())


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def whole_minutes(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value + 0.5) if value >= 0 else None


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def duration(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def _as_local(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    # Stored times are local naive; an aware value is shown in the robot PC's zone.
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def moment(value: Any, now: datetime, *, ago: bool = True) -> Optional[str]:
    """"Sat 3 Oct, 14:02 (42 min ago)"; unparseable text is shown as given."""
    if not _present(value):
        return None
    local = _as_local(value)
    if local is None:
        return _one_line(value)
    shown = f"{_DAYS[local.weekday()]} {local.day} {_MONTHS[local.month - 1]}"
    if local.year != now.year:
        shown += f" {local.year}"
    shown += f", {local:%H:%M}"
    elapsed = whole_minutes((now - local).total_seconds() / 60)
    if ago and elapsed is not None:
        shown += " (just now)" if elapsed == 0 else f" ({duration(elapsed)} ago)"
    return shown


# ----------------------------------------------------------------------
# Schedule alerts
# ----------------------------------------------------------------------

@dataclass
class _Facts:
    experiment: str
    context: Dict[str, Any]
    estimated_duration: Optional[int]
    clip_attached: bool

    def minutes(self, key: str) -> Optional[int]:
        return whole_minutes(self.context.get(key))

    @property
    def clip(self) -> str:
        return " (camera clip attached)" if self.clip_attached else ""


def _log_inactive(f: _Facts) -> Tuple[str, str, set]:
    silent, threshold = f.minutes("inactivity_minutes"), f.minutes("threshold_minutes")
    if silent is None:
        return ("run log silent",
                f"The Hamilton run log for {f.experiment} has stopped updating. The run may have stopped. "
                f"Check the robot{f.clip} and the run trace.", set())
    after = f" (alert after {threshold})" if threshold is not None else ""
    return (f"run log silent for {duration(silent)}",
            f"The Hamilton run log for {f.experiment} has not updated for {_plural(silent, 'minute')}{after}. "
            f"The run may have stopped. Check the robot{f.clip} and the run trace.",
            # The monitor's note for this event restates the summary.
            {"inactivity_minutes", "threshold_minutes", "note"})


def _monitoring_unavailable(f: _Facts) -> Tuple[str, str, set]:
    unavailable = f.minutes("unavailable_minutes")
    since = f" for {_plural(unavailable, 'minute')}" if unavailable is not None else ""
    return (f"run not monitored for {duration(unavailable)}" if unavailable is not None else "run not monitored",
            f"RobotControl has not been able to check the run for {f.experiment}{since}, so it cannot tell whether "
            f"the run is still progressing. Check the robot{f.clip}; the reason is below.",
            {"unavailable_minutes", "threshold_minutes"})


def _long_running(f: _Facts) -> Tuple[str, str, set]:
    elapsed = f.minutes("elapsed_minutes")
    expected = f.minutes("expected_minutes")
    if expected is None and f.estimated_duration:
        expected = f.estimated_duration
    if elapsed is None:
        return ("running longer than expected",
                f"The run for {f.experiment} is taking longer than expected. Check the robot{f.clip} "
                "to see whether it is still progressing.", {"expected_minutes"})
    than = f", longer than the expected {_plural(expected, 'minute')}" if expected is not None else ""
    return (f"running for {duration(elapsed)}",
            f"The run for {f.experiment} has been running for {_plural(elapsed, 'minute')}{than}. "
            f"Check the robot{f.clip} to see whether it is still progressing.",
            {"elapsed_minutes", "expected_minutes"})


def _aborted(f: _Facts) -> Tuple[str, str, set]:
    ran = f.minutes("runtime_minutes")
    after = f" after {_plural(ran, 'minute')}" if ran is not None else ""
    # The scheduler applies manual recovery exactly when it passes a note with the abort.
    paused = (" Automatic scheduling is paused until someone acknowledges the recovery and chooses "
              "Resume queued jobs on the Scheduling page." if _present(f.context.get("note")) else "")
    return ("run aborted",
            f"The run for {f.experiment} was aborted{after}.{paused} Check the robot{f.clip} and the deck "
            "before the next run.", {"runtime_minutes"})


def _execution_failed(f: _Facts) -> Tuple[str, str, set]:
    return ("run failed",
            f"The run for {f.experiment} failed with the error shown below. Check the robot{f.clip} "
            "and the run trace.", set())


@dataclass(frozen=True)
class _Trigger:
    tone: str
    headline: str
    describe: Callable[[_Facts], Tuple[str, str, set]]
    note_label: str = "Note"


TRIGGERS: Dict[str, _Trigger] = {
    "log_inactive": _Trigger("warning", "Run log silent", _log_inactive),
    "monitoring_unavailable": _Trigger("warning", "Run not monitored", _monitoring_unavailable, "Reason"),
    "long_running": _Trigger("warning", "Running longer than expected", _long_running),
    "aborted": _Trigger("error", "Run aborted", _aborted),
    "execution_failed": _Trigger("error", "Run failed", _execution_failed),
}


def _unknown_trigger(name: str) -> _Trigger:
    label = _one_line(name.replace("_", " ")).capitalize() or "Alert"
    return _Trigger("warning", label, lambda f: (
        label.lower(), f'RobotControl raised a "{label}" alert for {f.experiment}. Check the details below.', set()))


# Context keys shown in the Run table, in order; anything else goes to troubleshooting.
_RUN_KEYS = (
    ("last_activity_at", "Last log", "moment"),
    ("observed_at", "Checked", "moment"),
    ("run_state", "Hamilton status", "text"),
    ("inactivity_minutes", "Log silent for", "minutes"),
    ("unavailable_minutes", "Not monitored for", "minutes"),
    ("elapsed_minutes", "Running for", "minutes"),
    ("expected_minutes", "Expected", "minutes"),
    ("threshold_minutes", "Alert after", "minutes"),
    ("failure_count", "Failures", "text"),
    ("error_message", "Error", "text"),
    ("note", None, "text"),
)
_TROUBLESHOOTING_KEYS = (
    ("method_path", "Method"),
    ("trace_filename", "Trace file"),
    ("run_guid", "Run GUID"),
)


def schedule_alert_email(
    *,
    trigger: str,
    experiment: str,
    schedule_id: str,
    execution_id: Optional[str],
    start_time: Any,
    end_time: Any,
    estimated_duration: Optional[int],
    recorded_minutes: Optional[float],
    context: Dict[str, Any],
    attached: List[str],
    clip_attached: bool,
    now: datetime,
) -> AlertEmail:
    context = {key: value for key, value in (context or {}).items() if _present(value)}
    kind = TRIGGERS.get(trigger) or _unknown_trigger(trigger)
    facts = _Facts(_one_line(experiment), context, estimated_duration, clip_attached)
    subject_fact, summary, used = kind.describe(facts)

    rows: List[Tuple[str, str]] = []
    def add(label: str, value: Optional[str]) -> None:
        if _present(value):
            rows.append((label, value))
    add("Started", moment(start_time, now))
    add("Ended", moment(end_time, now))
    if estimated_duration and "expected_minutes" not in context:
        add("Expected", f"about {duration(estimated_duration)}")
    ran = whole_minutes(context.get("runtime_minutes"))
    if ran is None:
        ran = whole_minutes(recorded_minutes)
    if ran is not None:
        add("Ran for", duration(ran))
    for key, label, style in _RUN_KEYS:
        if key not in context or key in used:
            continue
        value = context[key]
        if style == "moment":
            add(label, moment(value, now, ago=key != "observed_at"))
        elif style == "minutes" and whole_minutes(value) is not None:
            shown = duration(whole_minutes(value))
            add(label, f"about {shown}" if key == "expected_minutes" else shown)
        elif not (key == "note" and _one_line(value) == _one_line(context.get("error_message", ""))):
            add(label or kind.note_label, _one_line(value))

    troubleshooting: List[Tuple[str, str]] = []
    for key, label in _TROUBLESHOOTING_KEYS:
        if key in context:
            troubleshooting.append((label, _one_line(context[key])))
    troubleshooting.append(("Schedule ID", schedule_id))
    if _present(execution_id):
        troubleshooting.append(("Execution ID", str(execution_id)))
    if "raw_run_state" in context:
        troubleshooting.append(("Hamilton SQL state", _one_line(context["raw_run_state"])))
    known = {key for key, _, _ in _RUN_KEYS} | {key for key, _ in _TROUBLESHOOTING_KEYS} | {"raw_run_state"}
    if whole_minutes(context.get("runtime_minutes")) is not None:
        known.add("runtime_minutes")
    troubleshooting.extend((key, _one_line(value)) for key, value in context.items() if key not in known)

    return AlertEmail(kind.tone, kind.headline, facts.experiment, subject_fact, summary,
                      rows, list(attached), troubleshooting)


# ----------------------------------------------------------------------
# Manual recovery
# ----------------------------------------------------------------------

def manual_recovery_email(*, required: bool, experiment: str, schedule_id: str, actor: str,
                          at: Any, note: Optional[str], now: datetime) -> AlertEmail:
    experiment = _one_line(experiment)
    if required:
        tone, headline, fact = "error", "Manual recovery required", "manual recovery required"
        summary = (f"{experiment} needs manual recovery. Automatic scheduling is paused and this schedule is "
                   "inactive. Check the robot and the deck, then acknowledge the recovery and choose Resume "
                   "queued jobs on the Scheduling page.")
        labels = ("Flagged", "Flagged by", "Reason")
    else:
        tone, headline, fact = "neutral", "Recovery acknowledged", "recovery acknowledged"
        summary = (f"{_one_line(actor)} acknowledged the recovery for {experiment}. Queued jobs stay paused until "
                   "someone chooses Resume queued jobs on the Scheduling page, and this schedule stays inactive "
                   "until it is activated again.")
        labels = ("Acknowledged", "Acknowledged by", "Notes")
    rows = [(label, value) for label, value in (
        (labels[0], moment(at, now)), (labels[1], _one_line(actor) if _present(actor) else None),
        (labels[2], _one_line(note) if _present(note) else None)) if value]
    return AlertEmail(tone, headline, experiment, fact, summary, rows, [],
                      [("Schedule ID", schedule_id)], RECOVERY_FOOTER, "Recovery")
