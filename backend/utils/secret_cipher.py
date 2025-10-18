"""Helpers for encrypting reversible secrets (SMTP passwords, API keys, etc.)."""

from __future__ import annotations

import base64
import sys
from typing import Optional

class SecretCipherError(RuntimeError):
    """Raised when a secret cannot be encrypted or decrypted."""


_win32 = None


def _get_win32crypt():
    global _win32
    if _win32 is not None:
        return _win32
    try:
        import win32crypt as _module  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SecretCipherError("win32crypt (pywin32) is required for DPAPI secret protection.") from exc
    _win32 = _module
    return _win32


def _ensure_windows() -> None:
    if sys.platform != "win32":  # pragma: no cover - platform guard
        raise SecretCipherError("DPAPI secret storage is only available on Windows hosts.")


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string using Windows DPAPI (machine scope)."""
    _ensure_windows()
    if plaintext is None:
        raise SecretCipherError("Cannot encrypt a null secret")
    win32 = _get_win32crypt()
    flags = getattr(win32, "CRYPTPROTECT_LOCAL_MACHINE", 0x4)
    try:
        protected = win32.CryptProtectData(
            plaintext.encode("utf-8"),
            None,
            None,
            None,
            None,
            flags,
        )
    except Exception as exc:  # pragma: no cover - OS-level failure
        raise SecretCipherError(f"DPAPI encryption failed: {exc}") from exc
    return base64.b64encode(protected).decode("ascii")


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    """Decrypt a previously encrypted token; returns None if no token provided."""
    if not token:
        return None
    _ensure_windows()
    try:
        blob = base64.b64decode(token.encode("ascii"))
    except Exception as exc:
        raise SecretCipherError("Encrypted secret payload is not valid base64") from exc
    win32 = _get_win32crypt()
    try:
        description, decrypted = win32.CryptUnprotectData(
            blob,
            None,
            None,
            None,
            0,
        )
    except Exception as exc:  # pragma: no cover - OS-level failure
        raise SecretCipherError(f"DPAPI decryption failed: {exc}") from exc
    return decrypted.decode("utf-8")


__all__ = ["encrypt_secret", "decrypt_secret", "SecretCipherError"]
