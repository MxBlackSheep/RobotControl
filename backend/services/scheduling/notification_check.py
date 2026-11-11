"""Stored-field checks for notification records; never inspect the network or files."""
import re

from backend.models import NotificationContact, NotificationSettings

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_email_address(value):
    if not isinstance(value, str):
        raise ValueError('Email address must be a string')
    email = value.strip()
    if not EMAIL_REGEX.fullmatch(email):
        raise ValueError('Invalid email address format')
    return email


def check_contact(fields):
    """Return a contact or raise ValueError with the route's 400 text."""
    name = fields.get('display_name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('display_name is required')
    email = check_email_address(fields.get('email_address'))
    return NotificationContact.from_dict({**fields, 'display_name': name.strip(), 'email_address': email,
                                          'is_active': bool(fields.get('is_active', True)), 'review_reason': None})


def check_email_settings(fields):
    """Return complete SMTP settings or raise ValueError with the settings route's 400 text."""
    host = fields.get('host')
    if not isinstance(host, str) or not host.strip():
        raise ValueError('host is required')
    try:
        port = int(fields.get('port', 587))
    except (TypeError, ValueError):
        raise ValueError('port must be an integer') from None
    if port < 1 or port > 65535:
        raise ValueError('port must be between 1 and 65535')
    username = fields.get('username')
    if username is not None and not isinstance(username, str):
        raise ValueError('username must be a string if provided')
    sender = check_email_address(fields.get('sender'))
    if fields.get('use_tls') and fields.get('use_ssl'):
        raise ValueError('use_tls and use_ssl cannot both be on')
    recipients = [check_email_address(value) for value in fields.get('manual_recovery_recipients') or [] if value.strip()]
    return NotificationSettings(**{**fields, 'host': host.strip(), 'port': port, 'username': (username or '').strip() or None,
                                   'sender': sender, 'use_tls': bool(fields.get('use_tls')), 'use_ssl': bool(fields.get('use_ssl')),
                                   'manual_recovery_recipients': list(dict.fromkeys(recipients)) or None, 'review_reason': None})
