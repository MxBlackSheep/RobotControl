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


# Set by a proxy on behalf of another client. Their presence on a loopback peer
# means a tunnel or reverse proxy on this computer relayed the request.
_PROXY_CLIENT_HEADERS = ("cf-connecting-ip", "true-client-ip", "x-real-ip")
_PROXY_MARKER_HEADERS = (*_PROXY_CLIENT_HEADERS, "cf-ray", "forwarded")


async def get_connection_context(request: Request) -> ConnectionContext:
    """
    Inspect the incoming request and determine whether the caller is local.

    Only a loopback socket peer can be local, and only when no proxy reports
    another client. A tunnel such as cloudflared on this computer connects from
    loopback; clients control the first X-Forwarded-For entry (proxies append the
    real address after it), so any non-loopback entry or proxy header means remote.
    The app disables Uvicorn peer rewriting.
    """
    peer_ip = normalize_ip(request.client.host) if request.client else None
    forwarded_for = [
        address
        for address in (normalize_ip(part) for part in request.headers.get("x-forwarded-for", "").split(","))
        if address
    ]
    proxied = any(request.headers.get(name) for name in _PROXY_MARKER_HEADERS) or any(
        not is_local_ip(address) for address in forwarded_for
    )

    # Only a proxy on this computer (loopback peer) can vouch for another address; a LAN peer's
    # headers are its own claims. Never use the client-supplied first X-Forwarded-For entry.
    client_ip: Optional[str] = peer_ip
    if is_local_ip(peer_ip):
        reported = next((normalize_ip(request.headers.get(name)) for name in _PROXY_CLIENT_HEADERS
                         if normalize_ip(request.headers.get(name))), None)
        client_ip = reported or (forwarded_for[-1] if forwarded_for else None) or peer_ip

    if not is_local_ip(peer_ip):
        classification = classify_ip(peer_ip)
    elif proxied:
        classification = "remote"
    else:
        classification = "local"
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
