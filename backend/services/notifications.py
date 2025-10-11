"""Notification utilities for scheduling events."""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import smtplib
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore

from backend.config import VIDEO_PATH
from backend.models import (
    JobExecution,
    NotificationContact,
    ScheduledExperiment,
    NotificationSettings,
)
from backend.utils.secret_cipher import decrypt_secret, SecretCipherError

logger = logging.getLogger(__name__)

GMAIL_MESSAGE_SIZE_LIMIT = 24 * 1024 * 1024  # 24 MB safeguard below ESP limit


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


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
    manual_recovery_recipients: List[str]
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

    @staticmethod
    def _normalize_csv(values: Optional[Union[str, List[str]]]) -> List[str]:
        if not values:
            return []
        if isinstance(values, str):
            parts = values.split(",")
        else:
            parts = values
        return [part.strip() for part in parts if part and part.strip()]

    def __init__(self) -> None:
        self.last_error: Optional[str] = None
        self._settings_error: Optional[str] = None
        self._settings = NotificationSettings()

        try:
            self._settings = _load_notification_settings()
        except Exception as exc:  # pragma: no cover - initialization guard
            self._settings_error = str(exc)
            logger.warning("Failed to load notification settings: %s", exc)

        manual_recipients = self._normalize_csv(self._settings.manual_recovery_recipients)

        password_plain: Optional[str] = None
        if self._settings.password_encrypted:
            try:
                password_plain = decrypt_secret(self._settings.password_encrypted)
            except SecretCipherError as exc:
                self._settings_error = str(exc)
                logger.error("Failed to decrypt SMTP password: %s", exc)

        username = self._settings.username or self._settings.sender
        self.config = EmailConfig(
            host=self._settings.host,
            port=self._settings.port,
            username=username,
            password=password_plain,
            sender=self._settings.sender,
            recipients=manual_recipients,
            manual_recovery_recipients=manual_recipients,
            use_tls=self._settings.use_tls,
            use_ssl=self._settings.use_ssl,
        )

        if not self.config.is_enabled:
            logger.info("Email notifications disabled: SMTP host/sender not configured")
        elif not self.config.password:
            self._settings_error = self._settings_error or "SMTP password is not configured"
            logger.warning("SMTP password missing for host %s; email delivery will be blocked until configured", self.config.host)

        # Default delivery tuning (overridable via NotificationSettings in future revisions)
        self._smtp_timeout = 90
        self._smtp_retries = 3
        self._smtp_retry_delay = 8

    def get_manual_recovery_recipients(self) -> List[str]:
        return list(self.config.manual_recovery_recipients)

    def send(
        self,
        subject: str,
        body: str,
        *,
        to: Optional[List[str]] = None,
        attachments: Optional[List[Path]] = None,
    ) -> bool:
        self.last_error = None
        if not self.config.is_enabled:
            detail = self._settings_error or "missing SMTP host or sender configuration"
            self.last_error = detail
            logger.warning("Skipping email '%s' because SMTP is not configured: %s", subject, detail)
            return False
        if not self.config.password:
            detail = self._settings_error or "SMTP password is not configured"
            self.last_error = detail
            logger.warning("Skipping email '%s' because no SMTP password is available", subject)
            return False

        recipients = [addr for addr in (to or self.config.recipients) if addr]
        if not recipients:
            self.last_error = "No recipients were provided"
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

        attempts = max(1, self._smtp_retries)
        for attempt in range(1, attempts + 1):
            try:
                if self.config.use_ssl:
                    smtp: Union[smtplib.SMTP, smtplib.SMTP_SSL]
                    smtp = smtplib.SMTP_SSL(self.config.host, self.config.port, timeout=self._smtp_timeout)
                else:
                    smtp = smtplib.SMTP(self.config.host, self.config.port, timeout=self._smtp_timeout)

                with smtp as client:
                    if self.config.use_tls and not self.config.use_ssl:
                        client.starttls()
                    if self.config.username and self.config.password:
                        client.login(self.config.username, self.config.password)
                    client.send_message(message)

                logger.info("Sent email notification to %s (attempt %s/%s)", message["To"], attempt, attempts)
                return True
            except Exception as exc:  # pragma: no cover - network dependent
                self.last_error = str(exc)
                logger.warning(
                    "Failed to send email notification (attempt %s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    time.sleep(self._smtp_retry_delay)

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
        self._video_root_dir = self._resolve_video_root()
        self._hamilton_log_dir = self._resolve_trc_directory()
        self._rolling_clips_dir = self._video_root_dir / "rolling_clips"

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
        recipients = self._manual_recovery_recipients(schedule)
        if not recipients:
            logger.warning(
                "Skipping manual recovery notification for %s - no recipients configured",
                schedule.schedule_id,
            )
            return

        subject = f"PyRobot manual recovery required: {schedule.experiment_name}"
        lines = [
            "Status: Manual Recovery Required",
            "",
            f"Experiment: {schedule.experiment_name}",
            f"Schedule ID: {schedule.schedule_id}",
            f"Triggered by: {actor}",
        ]
        marked = self._format_timestamp(getattr(schedule, "recovery_marked_at", None))
        if marked:
            lines.append(f"Flagged at: {marked}")
        if note:
            lines.extend(["", "Reason:", note])

        body = "\n".join(lines)
        self.email.send(subject, body, to=recipients)

    def manual_recovery_cleared(
        self,
        schedule: ScheduledExperiment,
        *,
        note: Optional[str],
        actor: str,
    ) -> None:
        recipients = self._manual_recovery_recipients(schedule)
        if not recipients:
            logger.warning(
                "Skipping manual recovery clearance notification for %s - no recipients configured",
                schedule.schedule_id,
            )
            return

        subject = f"PyRobot manual recovery cleared: {schedule.experiment_name}"
        lines = [
            "Status: Manual Recovery Cleared",
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
        self.email.send(subject, body, to=recipients)

    def _manual_recovery_recipients(self, schedule: ScheduledExperiment) -> List[str]:
        recipients = self.email.get_manual_recovery_recipients()
        if recipients:
            return recipients
        return self._collect_contact_emails(schedule)

    def _collect_contact_emails(self, schedule: ScheduledExperiment) -> List[str]:
        emails: List[str] = []
        seen = set()
        for contact_id in schedule.notification_contacts or []:
            contact = self.get_notification_contact(contact_id)
            if contact and contact.is_active and contact.email_address:
                email = contact.email_address.strip()
                if email and email not in seen:
                    emails.append(email)
                    seen.add(email)
        return emails

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
            converted = self._convert_trc_to_log(trc_file)
            if converted and converted.exists():
                attachments.append(converted)
                cleanup.append(converted)
                attachment_notes.append(f"Hamilton TRC log attached as {converted.name}.")
            else:
                attachments.append(trc_file)
                attachment_notes.append("Hamilton TRC log attached in original .trc format.")
        else:
            attachment_notes.append("TRC log not found or unreadable.")

        # Rolling clip summary (always attempt for operator context)
        fallback_clips = self._collect_recent_rolling_clips(limit=3)
        if fallback_clips:
            summary_clip = self._transcode_clips_to_mp4(fallback_clips)
            if summary_clip and summary_clip.exists():
                size_bytes = summary_clip.stat().st_size
                if size_bytes <= GMAIL_MESSAGE_SIZE_LIMIT:
                    attachments.append(summary_clip)
                    cleanup.append(summary_clip)
                    attachment_notes.append(
                        f"Attached rolling clip summary ({self._format_size(size_bytes)})."
                    )
                else:
                    summary_clip.unlink(missing_ok=True)
                    attachment_notes.append(
                        f"Rolling clip summary skipped (size {self._format_size(size_bytes)} exceeds limit)."
                    )
            else:
                attachment_notes.append("Rolling clip summary unavailable (transcode failed).")
        else:
            attachment_notes.append("Rolling clip summary unavailable (no recent clips).")

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

    def _resolve_video_root(self) -> Path:
        override = _env("PYROBOT_VIDEO_ARCHIVE_PATH")
        return Path(override) if override else Path(VIDEO_PATH)

    def _resolve_trc_directory(self) -> Path:
        raw_path = _env("PYROBOT_HAMILTON_LOG_PATH", r"C:\Program Files\HAMILTON\LogFiles")
        return Path(raw_path)

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
        trigger_label = {
            "long_running": "Long-running Execution",
            "aborted": "Aborted Execution",
        }.get(trigger, trigger.replace("_", " ").title())

        lines: List[str] = [
            f"Status: {trigger_label}",
            "",
            f"Experiment: {schedule.experiment_name}",
            f"Schedule ID: {schedule.schedule_id}",
        ]
        if execution.execution_id:
            lines.append(f"Execution ID: {execution.execution_id}")
        if execution.start_time:
            lines.append(f"Started at: {self._format_timestamp(execution.start_time)}")
        if execution.end_time:
            lines.append(f"Ended at: {self._format_timestamp(execution.end_time)}")
        if schedule.estimated_duration:
            lines.append(f"Expected duration: {schedule.estimated_duration} minutes")
        if execution.duration_minutes is not None:
            lines.append(f"Recorded duration: {execution.duration_minutes} minutes")

        context_lines = self._format_context_lines(context)
        if context_lines:
            lines.extend(["", "Details:"])
            lines.extend(f"  - {line}" for line in context_lines)

        lines.extend(
            [
                "",
                "You are receiving this message because you are listed as a notification contact for this schedule.",
            ]
        )

        return lines, []
    def _format_context_lines(self, context: Dict[str, Any]) -> List[str]:
        if not context:
            return []
        formatted: List[str] = []
        mapping = [
            ("elapsed_minutes", "Elapsed runtime (minutes)", True),
            ("threshold_minutes", "Alert threshold (minutes)", True),
            ("expected_minutes", "Expected duration (minutes)", True),
            ("runtime_minutes", "Recorded runtime (minutes)", True),
            ("failure_count", "Failure count", False),
            ("error_message", "Error", False),
            ("note", "Note", False),
        ]
        seen = set()
        for key, label, is_numeric in mapping:
            if key in context and context[key] is not None:
                value = context[key]
                seen.add(key)
                if is_numeric and isinstance(value, (int, float)):
                    formatted.append(f"{label}: {float(value):.1f}")
                else:
                    formatted.append(f"{label}: {value}")
        for key, value in context.items():
            if key in seen or value is None:
                continue
            formatted.append(f"{key}: {value}")
        return formatted

    def _convert_trc_to_log(self, trc_file: Path) -> Optional[Path]:
        try:
            try:
                content = trc_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = trc_file.read_text(encoding="latin-1")
        except Exception as exc:
            try:
                data = trc_file.read_bytes()
                content = data.decode("utf-8", errors="replace")
            except Exception as inner_exc:
                logger.debug("Failed to read TRC file %s: %s / %s", trc_file, exc, inner_exc)
                return None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="pyrobot_trc_",
                suffix=".log",
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as temp:
                temp.write(content)
                temp_path = Path(temp.name)
            safe_stem = trc_file.stem or "hamilton_log"
            candidate = temp_path.with_name(f"{safe_stem}.log")
            if candidate.exists():
                candidate = temp_path.with_name(f"{safe_stem}_{int(time.time())}.log")
            try:
                temp_path.rename(candidate)
                temp_path = candidate
            except OSError as rename_exc:
                logger.debug("Unable to rename TRC conversion output %s: %s", temp_path, rename_exc)
            return temp_path
        except Exception as exc:
            logger.debug("Failed to convert TRC to log: %s", exc)
            return None

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

    def _transcode_clips_to_mp4(self, clips: List[Path]) -> Optional[Path]:
        """Stitch rolling clips into a single MP4 attachment."""
        if cv2 is None:  # pragma: no cover - optional dependency
            logger.debug("OpenCV unavailable; skipping rolling clip transcode")
            return None

        valid_clips = [clip for clip in clips if clip.exists() and clip.stat().st_size > 0]
        if not valid_clips:
            return None

        output_path = Path(tempfile.gettempdir()) / f"pyrobot_rolling_summary_{uuid.uuid4().hex}.mp4"
        writer: Optional["cv2.VideoWriter"] = None
        frame_size: Optional[Tuple[int, int]] = None
        target_fps = 7.5
        wrote_frames = False

        try:
            for clip in valid_clips:
                cap = cv2.VideoCapture(str(clip))
                if not cap.isOpened():
                    logger.debug("Skipping rolling clip %s (unable to open)", clip)
                    continue

                clip_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
                clip_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
                clip_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0

                if writer is None:
                    frame_size = (clip_width, clip_height)
                    target_fps = float(max(1.0, min(30.0, clip_fps if clip_fps and clip_fps > 0.5 else 7.5)))
                    writer = self._create_video_writer(str(output_path), frame_size, target_fps)
                    if writer is None:
                        cap.release()
                        return None

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame_size and (frame.shape[1], frame.shape[0]) != frame_size:
                        frame = cv2.resize(frame, frame_size)
                    writer.write(frame)
                    wrote_frames = True

                cap.release()
        finally:
            if writer is not None:
                writer.release()

        if not wrote_frames:
            logger.debug("No frames written during rolling clip transcode; removing output")
            output_path.unlink(missing_ok=True)
            return None

        return output_path

    def _create_video_writer(
        self,
        file_path: str,
        frame_size: Tuple[int, int],
        fps: float,
    ) -> Optional["cv2.VideoWriter"]:
        """Initialise a video writer with preferred codecs."""
        if cv2 is None:  # pragma: no cover - optional dependency
            return None

        codecs = ("mp4v", "XVID", "avc1", "H264")
        for codec in codecs:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(file_path, fourcc, fps, frame_size)
            if writer.isOpened():
                logger.debug("Using %s codec for rolling clip summary (fps=%.2f, size=%s)", codec, fps, frame_size)
                return writer
            writer.release()

        logger.warning("Failed to initialise MP4 writer for rolling clip summary (tried %s)", codecs)
        return None

    def _format_size(self, size_bytes: int) -> str:
        """Human-friendly byte formatter for attachment notes."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"

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

    def _collect_recent_rolling_clips(self, limit: int = 5) -> List[Path]:
        """Collect the most recent rolling clips to attach as fallback."""
        directory = self._rolling_clips_dir
        if not directory.exists():
            return []

        candidates: List[Tuple[float, Path]] = []
        try:
            for candidate in directory.iterdir():
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in {".avi", ".mp4", ".mov"}:
                    continue
                try:
                    stat_result = candidate.stat()
                except OSError:
                    continue
                if stat_result.st_size <= 0:
                    continue
                candidates.append((stat_result.st_mtime, candidate))
        except Exception as exc:  # pragma: no cover - filesystem dependent
            logger.debug("Failed to enumerate rolling clips: %s", exc)
            return []

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [path for _, path in candidates[:limit]]


_notification_service: Optional[SchedulingNotificationService] = None


def get_notification_service() -> SchedulingNotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = SchedulingNotificationService()
    return _notification_service


def reset_notification_service() -> None:
    """Force recreation of the global scheduling notification service."""
    global _notification_service
    _notification_service = None
