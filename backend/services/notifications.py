"""Notification utilities for scheduling events."""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import smtplib
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from backend.config import VIDEO_PATH
from backend.models import (
    JobExecution,
    NotificationContact,
    ScheduledExperiment,
    NotificationSettings,
)
from backend.utils.secret_cipher import decrypt_secret, SecretCipherError

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


def _load_notification_settings() -> NotificationSettings:
    from backend.services.scheduling.sqlite_database import get_sqlite_scheduling_database

    return get_sqlite_scheduling_database().get_notification_settings()


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
        if not self.sender:
            return False
        return True


class EmailNotificationService:
    """Minimal SMTP client used for manual recovery alerts."""

    def __init__(self) -> None:
        recipients_raw = _env("PYROBOT_ALERT_RECIPIENTS") or _env("PYROBOT_SMTP_TO") or ""
        recipients = [addr.strip() for addr in recipients_raw.split(",") if addr.strip()]

        self._settings_error: Optional[str] = None
        self._settings = NotificationSettings()

        try:
            self._settings = _load_notification_settings()
        except Exception as exc:  # pragma: no cover - initialization guard
            self._settings_error = str(exc)
            logger.warning("Failed to load notification settings: %s", exc)

        password_plain: Optional[str] = None
        if self._settings.password_encrypted:
            try:
                password_plain = decrypt_secret(self._settings.password_encrypted)
            except SecretCipherError as exc:
                self._settings_error = str(exc)
                logger.error("Failed to decrypt SMTP password: %s", exc)

        self.config = EmailConfig(
            host=self._settings.host,
            port=self._settings.port,
            username=self._settings.username,
            password=password_plain,
            sender=self._settings.sender,
            recipients=recipients,
            use_tls=self._settings.use_tls,
            use_ssl=self._settings.use_ssl,
        )

        if not self.config.is_enabled:
            logger.info("Email notifications disabled: SMTP host/sender not configured")

    def send(
        self,
        subject: str,
        body: str,
        *,
        to: Optional[List[str]] = None,
        attachments: Optional[List[Path]] = None,
    ) -> bool:
        if not self.config.is_enabled:
            detail = self._settings_error or "missing SMTP host or sender configuration"
            logger.warning("Skipping email '%s' because SMTP is not configured: %s", subject, detail)
            return False

        recipients = [addr for addr in (to or self.config.recipients) if addr]
        if not recipients:
            logger.warning("Skipping email '%s' because no recipients were provided", subject)
            return False

        attachments = attachments or []
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.sender
        message["To"] = ", ".join(recipients)
        message.set_content(body)

        for attachment in attachments:
            try:
                with attachment.open("rb") as file_handle:
                    data = file_handle.read()
                mime_type, _ = mimetypes.guess_type(str(attachment))
                if not mime_type:
                    mime_type = "application/octet-stream"
                maintype, subtype = mime_type.split("/", 1)
                message.add_attachment(
                    data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment.name,
                )
            except Exception as exc:  # pragma: no cover - I/O best effort
                logger.warning("Failed to attach %s: %s", attachment, exc)

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


@dataclass
class ScheduleAlertResult:
    """Result from attempting to deliver a schedule alert email."""

    sent: bool
    subject: str
    body: str
    recipients: List[str]
    attachments: List[str] = field(default_factory=list)
    attachment_notes: List[str] = field(default_factory=list)
    error: Optional[str] = None


class SchedulingNotificationService:
    """High-level notification fa?ade used by the scheduler."""

    def __init__(self) -> None:
        self.email = EmailNotificationService()
        self._hamilton_log_dir = self._resolve_trc_directory()
        self._video_archive_dir = self._resolve_video_directory()

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

    # ------------------------------------------------------------------
    # Schedule execution alerts
    # ------------------------------------------------------------------

    def schedule_alert(
        self,
        schedule: ScheduledExperiment,
        execution: JobExecution,
        *,
        contacts: List[NotificationContact],
        trigger: str,
        context: Dict[str, Any],
    ) -> ScheduleAlertResult:
        """Send an alert for a schedule execution event."""
        recipients = [contact.email_address for contact in contacts if contact.is_active and contact.email_address]
        subject = self._render_alert_subject(schedule, trigger)
        body_lines, attachment_notes = self._render_alert_body(schedule, execution, trigger, context)

        attachments: List[Path] = []
        cleanup: List[Path] = []

        # Collect TRC file
        trc_file = self._locate_trc_file(schedule, execution)
        if trc_file:
            attachments.append(trc_file)
        else:
            attachment_notes.append("TRC log not found or unreadable.")

        # Collect video archive
        archive = self._locate_video_archive(schedule, execution)
        if archive:
            zipped = self._zip_archive_folder(archive)
            if zipped:
                attachments.append(zipped)
                cleanup.append(zipped)
            else:
                attachment_notes.append(f"Failed to zip archive folder {archive}.")
        else:
            attachment_notes.append("No video archive folder located.")

        if attachment_notes:
            body_lines.extend(["", "Attachment notes:"])
            body_lines.extend(f"  - {note}" for note in attachment_notes)

        body = "\n".join(body_lines)
        send_error: Optional[str] = None
        try:
            sent = self.email.send(
                subject,
                body,
                to=recipients,
                attachments=attachments or None,
            )
            if not sent:
                send_error = "Email delivery reported failure (see logs for details)."
            return ScheduleAlertResult(
                sent=sent,
                subject=subject,
                body=body,
                recipients=recipients,
                attachments=[str(path) for path in attachments],
                attachment_notes=attachment_notes,
                error=send_error,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("Failed to send schedule alert: %s", exc)
            send_error = str(exc)
            return ScheduleAlertResult(
                sent=False,
                subject=subject,
                body=body,
                recipients=recipients,
                attachments=[str(path) for path in attachments],
                attachment_notes=attachment_notes,
                error=send_error,
            )
        finally:
            for temp_file in cleanup:
                try:
                    temp_file.unlink(missing_ok=True)
                except Exception as cleanup_exc:  # pragma: no cover - best effort
                    logger.debug("Failed to remove temporary archive %s: %s", temp_file, cleanup_exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_trc_directory(self) -> Path:
        raw_path = _env("PYROBOT_HAMILTON_LOG_PATH", r"C:\Program Files\HAMILTON\LogFiles")
        return Path(raw_path)

    def _resolve_video_directory(self) -> Path:
        override = _env("PYROBOT_VIDEO_ARCHIVE_PATH")
        base = Path(override) if override else Path(VIDEO_PATH)
        return base / "experiments"

    def _render_alert_subject(self, schedule: ScheduledExperiment, trigger: str) -> str:
        trigger_label = {
            "long_running": "Long-running execution",
            "aborted": "Aborted execution",
        }.get(trigger, trigger.replace("_", " ").title())
        return f"PyRobot alert: {schedule.experiment_name} [{trigger_label}]"

    def _render_alert_body(
        self,
        schedule: ScheduledExperiment,
        execution: JobExecution,
        trigger: str,
        context: Dict[str, Any],
    ) -> Tuple[List[str], List[str]]:
        lines = [
            "PyRobot detected an execution event that requires attention.",
            "",
            f"Experiment: {schedule.experiment_name}",
            f"Schedule ID: {schedule.schedule_id}",
            f"Trigger: {trigger}",
            f"Execution ID: {execution.execution_id}",
        ]
        if execution.start_time:
            lines.append(f"Started at: {self._format_timestamp(execution.start_time)}")
        if execution.end_time:
            lines.append(f"Completed at: {self._format_timestamp(execution.end_time)}")
        if schedule.estimated_duration:
            lines.append(f"Expected duration: {schedule.estimated_duration} minutes")
        if execution.duration_minutes:
            lines.append(f"Recorded duration: {execution.duration_minutes} minutes")
        if execution.error_message:
            lines.extend(["", "Last error message:", execution.error_message])

        if context:
            lines.extend(["", "Context:"])
            for key, value in context.items():
                lines.append(f"  - {key}: {value}")

        lines.extend(
            [
                "",
                "Attachments:",
                "  - Hamilton TRC log (if available)",
                "  - Experiment video archive (if available)",
                "",
                "You are receiving this message because you are listed as a notification contact for this schedule.",
            ]
        )

        return lines, []

    def _locate_trc_file(self, schedule: ScheduledExperiment, execution: JobExecution) -> Optional[Path]:
        """Find the most relevant TRC file for the execution."""
        directory = self._hamilton_log_dir
        if not directory.exists():
            return None

        tokens = {schedule.schedule_id.lower()}
        if schedule.experiment_name:
            tokens.add(schedule.experiment_name.lower())
        if schedule.experiment_path:
            tokens.add(Path(schedule.experiment_path).stem.lower())
        if execution.execution_id:
            tokens.add(execution.execution_id.lower())

        newest_match: Optional[Path] = None
        newest_any: Optional[Path] = None
        latest_mtime = float("-inf")
        latest_any_mtime = float("-inf")

        try:
            for candidate in directory.glob("*.trc"):
                if not candidate.is_file():
                    continue
                try:
                    stat = candidate.stat()
                except OSError:
                    continue
                name_lower = candidate.name.lower()
                if any(token and token in name_lower for token in tokens):
                    if stat.st_mtime > latest_mtime:
                        newest_match = candidate
                        latest_mtime = stat.st_mtime
                if stat.st_mtime > latest_any_mtime:
                    newest_any = candidate
                    latest_any_mtime = stat.st_mtime
        except Exception as exc:  # pragma: no cover - filesystem dependent
            logger.debug("Failed to scan TRC directory: %s", exc)
            return None

        return newest_match or newest_any

    def _locate_video_archive(self, schedule: ScheduledExperiment, execution: JobExecution) -> Optional[Path]:
        """Return the most recent video archive directory for the execution."""
        base = self._video_archive_dir
        if not base.exists():
            return None

        tokens = {
            schedule.schedule_id.lower(),
            (schedule.experiment_name or "").lower(),
            Path(schedule.experiment_path or "").stem.lower(),
            (execution.execution_id or "").lower(),
        }

        latest_path: Optional[Path] = None
        latest_mtime = float("-inf")
        try:
            for directory in base.iterdir():
                if not directory.is_dir():
                    continue
                try:
                    stat = directory.stat()
                except OSError:
                    continue
                name_lower = directory.name.lower()
                if any(token and token in name_lower for token in tokens):
                    if stat.st_mtime > latest_mtime:
                        latest_path = directory
                        latest_mtime = stat.st_mtime
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to locate video archive: %s", exc)
            return None

        return latest_path

    def _zip_archive_folder(self, folder: Path) -> Optional[Path]:
        """Zip the archive folder and return the zip path."""
        if not folder.exists():
            return None
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="pyrobot_alert_"))
            archive_base = temp_dir / f"{folder.name}"
            zip_path = Path(shutil.make_archive(str(archive_base), "zip", folder))
            return zip_path
        except Exception as exc:  # pragma: no cover - filesystem dependent
            logger.debug("Failed to zip archive folder %s: %s", folder, exc)
            return None


_notification_service: Optional[SchedulingNotificationService] = None


def get_notification_service() -> SchedulingNotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = SchedulingNotificationService()
    return _notification_service
