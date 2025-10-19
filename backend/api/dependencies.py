"""
Common FastAPI dependencies shared across RobotControl API routers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from backend.utils.network_utils import classify_ip, is_local_ip, normalize_ip


@dataclass
class ConnectionContext:
    """Metadata describing the incoming HTTP request connection."""

    client_ip: Optional[str]
    is_local: bool
    ip_classification: str


async def get_connection_context(request: Request) -> ConnectionContext:
    """
    Inspect the incoming request and determine whether the caller is local.

    Preference is given to the left-most X-Forwarded-For header which allows the
    application to sit behind a trusted reverse proxy.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip: Optional[str] = None

    if forwarded_for:
        client_ip = normalize_ip(forwarded_for.split(",")[0])

    if not client_ip and request.client:
        client_ip = normalize_ip(request.client.host)

    classification = classify_ip(client_ip)
    return ConnectionContext(
        client_ip=client_ip,
        is_local=classification == "local",
        ip_classification=classification,
    )


async def require_local_access(
    context: ConnectionContext = Depends(get_connection_context),
) -> ConnectionContext:
    """FastAPI dependency that ensures the caller is on a trusted/local network."""

    if not context.is_local:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local network access required for this operation",
        )
    return context
