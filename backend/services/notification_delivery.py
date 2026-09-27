"""Record sends that do not already belong to the scheduler's alert log."""
import logging
from datetime import datetime
from backend.models import NotificationLogEntry

logger = logging.getLogger(__name__)


def send_recorded(email, subject, body, *, event_type, schedule_id=None, actor=None, **options):
    from backend.services.scheduling import get_scheduling_database_manager
    manager = get_scheduling_database_manager()
    entry = NotificationLogEntry('', schedule_id, None, event_type, 'pending',
        recipients=options.get('to') or [], subject=subject, message=body, metadata={'actor': actor})
    email.delivery_log_warning = None
    if not manager.create_notification_log(entry):
        email.last_error = 'Delivery log is unavailable. Email was not sent.'
        logger.error(email.last_error)
        return False
    try:
        sent = email.send(subject, body, **options)
    except Exception as exc:
        email.last_error = str(exc)
        sent = False
    status = 'sent' if sent else 'partial' if getattr(email, 'last_delivery_status', None) == 'partial' else 'error'
    if not manager.update_notification_log(entry.log_id, status=status, processed_at=datetime.now(), error_message=email.last_error or ''):
        email.delivery_log_warning = 'Email submission finished, but its delivery record could not be updated. Check the recipients before resending.'
        logger.error('%s Log ID: %s', email.delivery_log_warning, entry.log_id)
    return sent
