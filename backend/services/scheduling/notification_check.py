"""Stored-field checks for notification records; never inspect the network or files."""
import re

from backend.models import NotificationContact

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
