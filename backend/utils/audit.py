"""
Centralised helper for recording high-sensitivity actions to the audit log.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from datetime import datetime

audit_logger = logging.getLogger("pyrobot.audit")


def log_action(
    *,
    actor: str,
    action: str,
    scope: str,
    client_ip: Optional[str],
    success: bool,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a structured audit log entry for security-sensitive operations."""
    payload: Dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": actor,
        "action": action,
        "scope": scope,
        "client_ip": client_ip,
        "success": success,
    }
    if details:
        payload["details"] = details
    audit_logger.info(payload)
