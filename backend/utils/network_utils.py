"""
Helpers for classifying client IP addresses and determining whether a request
originated from the local network.
"""

from __future__ import annotations

import ipaddress
from typing import Optional


def normalize_ip(ip_value: Optional[str]) -> Optional[str]:
    """Return a trimmed IP string or None if the input is falsy."""
    if not ip_value:
        return None
    candidate = ip_value.strip()
    return candidate or None


def is_local_ip(ip_value: Optional[str]) -> bool:
    """
    Determine whether an IP address should be treated as local/trusted.

    Currently only loopback addresses (e.g., 127.0.0.1 or ::1) are considered local.
    """
    ip_str = normalize_ip(ip_value)
    if not ip_str:
        return False

    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    return ip_obj.is_loopback


def classify_ip(ip_value: Optional[str]) -> str:
    """
    Return a textual classification for the provided IP address.

    Values: "local", "remote", "unknown".
    """
    ip_str = normalize_ip(ip_value)
    if not ip_str:
        return "unknown"

    try:
        ipaddress.ip_address(ip_str)
    except ValueError:
        return "unknown"

    return "local" if is_local_ip(ip_str) else "remote"
