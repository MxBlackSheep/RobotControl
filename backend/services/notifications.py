"""Notification utilities for scheduling events."""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
import ssl
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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
from backend.services.alert_email import AlertEmail, manual_recovery_email, schedule_alert_email
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
        message_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        attempts: Optional[int] = None,
        html: Optional[str] = None,
    ) -> bool:
        self.last_error = None
        self.last_delivery_status = None
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
        if message_id:
            message["Message-ID"] = message_id
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        if html:
            # multipart/alternative: a client that blocks or cannot show HTML shows the text part.
            message.add_alternative(html, subtype="html")

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

        delivery_attempts = max(1, self._smtp_retries if attempts is None else attempts)
        timeout = self._smtp_timeout if timeout_seconds is None else timeout_seconds
        for attempt in range(1, delivery_attempts + 1):
            smtp = None
            stage = "connection / server greeting"
            try:
                if self.config.use_ssl:
                    stage = "SSL connection / server greeting"
                    smtp = smtplib.SMTP_SSL(
                        self.config.host, self.config.port, timeout=timeout,
                        context=ssl.create_default_context(),
                    )
                else:
                    smtp = smtplib.SMTP(self.config.host, self.config.port, timeout=timeout)

                if self.config.use_tls and not self.config.use_ssl:
                    stage = "STARTTLS negotiation"
                    smtp.starttls(context=ssl.create_default_context())
                if self.config.username and self.config.password:
                    stage = "authentication"
                    smtp.login(self.config.username, self.config.password)
                stage = "message submission"
                refused = smtp.send_message(message)
                if refused:
                    self.last_delivery_status = 'partial'
                    self.last_error = 'Some recipients were refused: ' + ', '.join(refused) + '. Other recipients accepted; do not resend to everyone.'
                    logger.warning(self.last_error)
                    return False
                self.last_delivery_status = 'sent'

                self.last_error = None
                logger.info("Sent email notification to %s (attempt %s/%s)", message["To"], attempt, delivery_attempts)
                return True
            except Exception as exc:  # pragma: no cover - network dependent
                detail = str(exc)
                if isinstance(exc, smtplib.SMTPAuthenticationError):
                    detail = "Authentication rejected; check the SMTP username and SMTP/app password."
                elif isinstance(exc, TimeoutError) or "timed out" in detail.lower():
                    detail = f"No response within {timeout:g} seconds. Check SMTP reachability, port and encryption settings."
                self.last_error = f"SMTP {stage} failed ({self.config.host}:{self.config.port}): {detail}"
                logger.warning(
                    "Failed to send email notification (attempt %s/%s): %s",
                    attempt,
                    delivery_attempts,
                    self.last_error,
                )
                if isinstance(exc, smtplib.SMTPAuthenticationError):
                    break  # Repeating unchanged credentials cannot resolve rejection.
            finally:
                if smtp is not None:
                    try:
                        # A disconnect failure must not retry an already accepted message.
                        smtp.close()
                    except Exception as exc:
                        logger.debug("SMTP socket cleanup failed: %s", exc)
            if attempt < delivery_attempts:
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
    cancelled: bool = False
    delivery_status: Optional[str] = None


class SchedulingNotificationService:
    """High-level notification fa?ade used by the scheduler."""

    def __init__(self) -> None:
        self.email = EmailNotificationService()
        self._video_root_dir = self._resolve_video_root()
        self._hamilton_log_dir = self._resolve_trc_directory()
        self._rolling_clips_dir = self._video_root_dir / "rolling_clips"

    def manual_recovery_required(
        self,
        schedule: ScheduledExperiment,
        *,
        note: Optional[str],
        actor: str,
    ) -> None:
        self._send_manual_recovery(schedule, note=note, actor=actor, required=True)

    def manual_recovery_cleared(
        self,
        schedule: ScheduledExperiment,
        *,
        note: Optional[str],
        actor: str,
    ) -> None:
        self._send_manual_recovery(schedule, note=note, actor=actor, required=False)

    def _send_manual_recovery(self, schedule: ScheduledExperiment, *, note: Optional[str], actor: str, required: bool) -> None:
        event_type = "manual_recovery_required" if required else "manual_recovery_cleared"
        recipients = self._manual_recovery_recipients(schedule)
        if not recipients:
            logger.warning("Skipping %s notification for %s - no recipients configured", event_type, schedule.schedule_id)
            return

        alert = manual_recovery_email(
            required=required,
            experiment=schedule.experiment_name,
            schedule_id=schedule.schedule_id,
            actor=actor,
            at=getattr(schedule, "recovery_marked_at" if required else "recovery_resolved_at", None),
            note=note,
            now=datetime.now(),
        )
        from backend.services.notification_delivery import send_recorded
        send_recorded(self.email, alert.subject, alert.text(), html=alert.html(), to=recipients,
                      event_type=event_type, schedule_id=schedule.schedule_id, actor=actor)

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
        trace_path: Optional[Path] = None,
        exact_trace: bool = False,
        message_id: Optional[str] = None,
        should_send: Optional[Callable[[], bool]] = None,
    ) -> ScheduleAlertResult:
        """Send an alert for a schedule execution event."""
        recipients = [contact.email_address for contact in contacts if contact.is_active and contact.email_address]
        attachment_notes: List[str] = []
        clip_attached = False
        alert = self._alert_email(schedule, execution, trigger, context, attachment_notes, clip_attached)
        subject, body = alert.subject, alert.text()

        attachments: List[Path] = []
        cleanup: List[Path] = []

        try:
            # Collect TRC file
            trc_file = trace_path if exact_trace else self._locate_trc_file(schedule, execution)
            if trc_file:
                converted = self._convert_trc_to_log(trc_file)
                if converted and converted.exists():
                    attachments.append(converted)
                    cleanup.append(converted)
                    attachment_notes.append(f"Run trace: {converted.name}")
                elif not exact_trace:
                    attachments.append(trc_file)
                    attachment_notes.append(f"Run trace: {trc_file.name} (original .trc file)")
                else:
                    attachment_notes.append("Run trace: could not be read, so no substitute log was attached")
            else:
                attachment_notes.append("Run trace: not found")

            # Rolling clip summary (always attempt for operator context)
            fallback_clips = self._collect_recent_rolling_clips(limit=3)
            if fallback_clips:
                summary_clip = self._transcode_clips_to_mp4(fallback_clips)
                if summary_clip:
                    cleanup.append(summary_clip)
                if summary_clip and summary_clip.exists():
                    size_bytes = summary_clip.stat().st_size
                    if size_bytes <= GMAIL_MESSAGE_SIZE_LIMIT:
                        attachments.append(summary_clip)
                        clip_attached = True
                        attachment_notes.append(
                            f"Camera clip: the latest camera recordings ({self._format_size(size_bytes)})"
                        )
                    else:
                        summary_clip.unlink(missing_ok=True)
                        attachment_notes.append(
                            f"Camera clip: not attached, {self._format_size(size_bytes)} is over the email size limit"
                        )
                else:
                    attachment_notes.append("Camera clip: could not be prepared")
            else:
                attachment_notes.append("Camera clip: no recent camera recordings")

            alert = self._alert_email(schedule, execution, trigger, context, attachment_notes, clip_attached)
            subject, body = alert.subject, alert.text()
            send_error: Optional[str] = None
            if should_send is not None and not should_send():
                return ScheduleAlertResult(False, subject, body, recipients, cancelled=True)
            sent = self.email.send(
                subject,
                body,
                html=alert.html(),
                to=recipients,
                attachments=attachments or None,
                **({"message_id": message_id} if message_id else {}),
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
        override = _env("ROBOTCONTROL_VIDEO_ARCHIVE_PATH")
        return Path(override) if override else Path(VIDEO_PATH)

    def _resolve_trc_directory(self) -> Path:
        from backend.services.scheduling.run_log_monitor import hamilton_log_directory
        return hamilton_log_directory()

    def _alert_email(
        self,
        schedule: ScheduledExperiment,
        execution: JobExecution,
        trigger: str,
        context: Dict[str, Any],
        attachment_notes: List[str],
        clip_attached: bool,
    ) -> AlertEmail:
        return schedule_alert_email(
            trigger=trigger,
            experiment=schedule.experiment_name,
            schedule_id=schedule.schedule_id,
            execution_id=execution.execution_id,
            start_time=execution.start_time,
            end_time=execution.end_time,
            estimated_duration=schedule.estimated_duration,
            recorded_minutes=execution.duration_minutes,
            context=context,
            attached=attachment_notes,
            clip_attached=clip_attached,
            now=datetime.now(),
        )

    def _convert_trc_to_log(self, trc_file: Path) -> Optional[Path]:
        try:
            data = trc_file.read_bytes()
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                content = data.decode("utf-16")
            else:
                try:
                    content = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    content = data.decode("cp1252", errors="replace")
        except Exception as exc:
            try:
                data = trc_file.read_bytes()
                content = data.decode("utf-8", errors="replace")
            except Exception as inner_exc:
                logger.debug("Failed to read TRC file %s: %s / %s", trc_file, exc, inner_exc)
                return None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="robotcontrol_trc_",
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

        output_path = Path(tempfile.gettempdir()) / f"robotcontrol_rolling_summary_{uuid.uuid4().hex}.mp4"
        writer: Optional["cv2.VideoWriter"] = None
        frame_size: Optional[Tuple[int, int]] = None
        target_fps = 7.5
        wrote_frames = False
        completed = False

        try:
            for clip in valid_clips:
                cap = cv2.VideoCapture(str(clip))
                try:
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
                            return None

                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        if frame_size and (frame.shape[1], frame.shape[0]) != frame_size:
                            frame = cv2.resize(frame, frame_size)
                        writer.write(frame)
                        wrote_frames = True

                finally:
                    cap.release()
            completed = True
        finally:
            if writer is not None:
                writer.release()
            if not completed:
                output_path.unlink(missing_ok=True)

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
