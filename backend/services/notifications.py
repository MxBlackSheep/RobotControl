"""Notification utilities for scheduling events."""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Optional, Union

from backend.models import ScheduledExperiment

logger = logging.getLogger(__name__)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EmailConfig:
    host: Optional[str]
    port: int
    username: Optional[str]
    password: Optional[str]
    sender: Optional[str]
    recipients: List[str]
    use_tls: bool
    use_ssl: bool

    @property
    def is_enabled(self) -> bool:
        if not self.host:
            return False
        if not self.sender or not self.recipients:
            return False
        return True


class EmailNotificationService:
    """Minimal SMTP client used for manual recovery alerts."""

    def __init__(self) -> None:
        recipients_raw = _env("PYROBOT_ALERT_RECIPIENTS") or _env("PYROBOT_SMTP_TO") or ""
        recipients = [addr.strip() for addr in recipients_raw.split(",") if addr.strip()]

        sender = _env("PYROBOT_SMTP_FROM") or _env("PYROBOT_SMTP_USERNAME")

        self.config = EmailConfig(
            host=_env("PYROBOT_SMTP_HOST"),
            port=int(_env("PYROBOT_SMTP_PORT", "587")),
            username=_env("PYROBOT_SMTP_USERNAME"),
            password=_env("PYROBOT_SMTP_PASSWORD"),
            sender=sender,
            recipients=recipients,
            use_tls=_env_bool("PYROBOT_SMTP_USE_TLS", True),
            use_ssl=_env_bool("PYROBOT_SMTP_USE_SSL", False),
        )

        if not self.config.is_enabled:
            logger.info("Email notifications disabled: missing SMTP configuration")

    def send(self, subject: str, body: str) -> bool:
        if not self.config.is_enabled:
            logger.debug("Skipping email '%s' because SMTP is not configured", subject)
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.sender
        message["To"] = ", ".join(self.config.recipients)
        message.set_content(body)

        try:
            if self.config.use_ssl:
                smtp: Union[smtplib.SMTP, smtplib.SMTP_SSL]
                smtp = smtplib.SMTP_SSL(self.config.host, self.config.port, timeout=15)
            else:
                smtp = smtplib.SMTP(self.config.host, self.config.port, timeout=15)

            with smtp as client:
                if self.config.use_tls and not self.config.use_ssl:
                    client.starttls()
                if self.config.username and self.config.password:
                    client.login(self.config.username, self.config.password)
                client.send_message(message)

            logger.info("Sent email notification to %s", message["To"])
            return True
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Failed to send email notification: %s", exc)
            return False


class SchedulingNotificationService:
    """High-level notification fa?ade used by the scheduler."""

    def __init__(self) -> None:
        self.email = EmailNotificationService()

    def _format_timestamp(self, value: Optional[object]) -> Optional[str]:
        if not value:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def manual_recovery_required(
        self,
        schedule: ScheduledExperiment,
        *,
        note: Optional[str],
        actor: str,
    ) -> None:
        subject = f"PyRobot manual recovery required: {schedule.experiment_name}"
        lines = [
            "A scheduled experiment requires manual recovery before it can run again.",
            "",
            f"Experiment: {schedule.experiment_name}",
            f"Schedule ID: {schedule.schedule_id}",
            f"Triggered by: {actor}",
        ]
        marked = self._format_timestamp(getattr(schedule, "recovery_marked_at", None))
        if marked:
            lines.append(f"Marked at: {marked}")
        if note:
            lines.extend(["", "Notes:", note])

        body = "\n".join(lines)
        self.email.send(subject, body)

    def manual_recovery_cleared(
        self,
        schedule: ScheduledExperiment,
        *,
        note: Optional[str],
        actor: str,
    ) -> None:
        subject = f"PyRobot manual recovery cleared: {schedule.experiment_name}"
        lines = [
            "Manual recovery has been cleared for a scheduled experiment.",
            "",
            f"Experiment: {schedule.experiment_name}",
            f"Schedule ID: {schedule.schedule_id}",
            f"Resolved by: {actor}",
        ]
        resolved = self._format_timestamp(getattr(schedule, "recovery_resolved_at", None))
        if resolved:
            lines.append(f"Resolved at: {resolved}")
        if note:
            lines.extend(["", "Resolution notes:", note])

        body = "\n".join(lines)
        self.email.send(subject, body)


_notification_service: Optional[SchedulingNotificationService] = None


def get_notification_service() -> SchedulingNotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = SchedulingNotificationService()
    return _notification_service
