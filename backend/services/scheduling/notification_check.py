"""Stored-field checks for notification records; never inspect the network or files.

Each failure is a CheckError: its text is the route's 400 answer, its review_reason the plain
sentence a stored record shows after "Needs review".
"""
import re

from backend.models import NotificationContact, NotificationSettings
from backend.utils.record_check import CheckError

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_email_address(value, what='The email address'):
    if not isinstance(value, str):
        raise CheckError('Email address must be a string', f'{what} is not an email address')
    email = value.strip()
    if not EMAIL_REGEX.fullmatch(email):
        raise CheckError('Invalid email address format', f'{what} is not a valid email address')
    return email


def check_contact(fields):
    """Return a contact or raise CheckError."""
    name = fields.get('display_name')
    if not isinstance(name, str) or not name.strip():
        raise CheckError('display_name is required', 'The contact has no name')
    email = check_email_address(fields.get('email_address'), "The contact's address")
    return NotificationContact.from_dict({**fields, 'display_name': name.strip(), 'email_address': email,
                                          'is_active': bool(fields.get('is_active', True)), 'review_reason': None})


def check_email_settings(fields):
    """Return complete SMTP settings or raise CheckError."""
    host = fields.get('host')
    if not isinstance(host, str) or not host.strip():
        raise CheckError('host is required', 'The outgoing mail server is not set')
    try:
        port = int(fields.get('port', 587))
    except (TypeError, ValueError):
        raise CheckError('port must be an integer', 'The mail server port is not a number') from None
    if port < 1 or port > 65535:
        raise CheckError('port must be between 1 and 65535', f'The mail server port {port} is not between 1 and 65535')
    username = fields.get('username')
    if username is not None and not isinstance(username, str):
        raise CheckError('username must be a string if provided', 'The mail server login name is not text')
    sender = check_email_address(fields.get('sender'), 'The From address')
    recipients = fields.get('manual_recovery_recipients')
    if isinstance(recipients, str):
        recipients = recipients.split(',')
    elif isinstance(recipients, list):
        if not all(isinstance(value, str) for value in recipients):
            raise CheckError('manual_recovery_recipients must contain strings', 'A recovery recipient is not an email address')
    elif recipients is not None:
        raise CheckError('manual_recovery_recipients must be a string or list of strings',
                         'A recovery recipient is not an email address')
    recipients = [check_email_address(value, f"The recovery recipient '{value.strip()}'") for value in recipients or [] if value.strip()]
    # SSL replaces STARTTLS rather than conflicting with it.
    use_ssl = bool(fields.get('use_ssl'))
    return NotificationSettings(**{**fields, 'host': host.strip(), 'port': port, 'username': (username or '').strip() or None,
                                   'sender': sender, 'use_tls': bool(fields.get('use_tls', True)) and not use_ssl, 'use_ssl': use_ssl,
                                   'manual_recovery_recipients': list(dict.fromkeys(recipients)) or None, 'review_reason': None})
