"""
RobotControl Authentication Service (persistent edition).

Replaces the in-memory user store with a SQLite-backed implementation so that:
- Users, hashed passwords, and refresh tokens persist across restarts
- New lab members can self-register with email tracking
- Admins can reset passwords without exposing credentials in source control
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
import bcrypt

from backend.services.auth_database import get_auth_database, AuthDatabase
from backend.services.sqlite_safety import StorageUnavailable
from backend.utils.data_paths import get_path_manager
from backend.utils.record_check import CheckError

logger = logging.getLogger(__name__)



# Configuration (environment overrides supported for deployments)
DEFAULT_ADMIN_USERNAME = os.getenv("ROBOTCONTROL_ADMIN_USERNAME", "admin")
# Published in the public repository, so anyone can try it. The login route refuses it from
# outside the RobotControl computer (a deployment's own ROBOTCONTROL_ADMIN_PASSWORD is not public).
BUILT_IN_ADMIN_PASSWORD = "ShouGroupAdmin"
DEFAULT_ADMIN_PASSWORD = os.getenv("ROBOTCONTROL_ADMIN_PASSWORD", BUILT_IN_ADMIN_PASSWORD)
DEFAULT_ADMIN_EMAIL = os.getenv("ROBOTCONTROL_ADMIN_EMAIL", "admin@localhost")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ROBOTCONTROL_ACCESS_TOKEN_MINUTES", "240"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("ROBOTCONTROL_REFRESH_TOKEN_HOURS", "168"))

ALGORITHM = "HS256"
_token_secrets: Optional[Tuple[str, str]] = None


def token_secrets() -> Tuple[str, str]:
    """The (access, refresh) signing keys of this installation.

    Both environment variables win; otherwise data/config/token-secrets.json, created with
    random keys at first start. A file that cannot be read stops start-up: writing new keys
    would sign everyone out and hide the fault.
    """
    global _token_secrets
    if _token_secrets is None:
        access = os.getenv("ROBOTCONTROL_ACCESS_TOKEN_SECRET")
        refresh = os.getenv("ROBOTCONTROL_REFRESH_TOKEN_SECRET")
        if access and refresh:
            _token_secrets = (access, refresh)
            return _token_secrets
        path = get_path_manager().config_path / "token-secrets.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            keys = {"access": secrets.token_urlsafe(48), "refresh": secrets.token_urlsafe(48)}
            with open(path, "x", encoding="utf-8") as file:  # "x": never overwrite
                json.dump(keys, file)
            logger.info("Created sign-in keys in %s", path)
        try:
            keys = json.loads(path.read_text(encoding="utf-8"))
            _token_secrets = (str(keys["access"]), str(keys["refresh"]))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.critical("Sign-in keys in %s cannot be read (%s); fix or delete the file, then start again", path, exc)
            raise RuntimeError(f"Sign-in keys in {path} cannot be read") from exc
    return _token_secrets


# A storage failure says nothing about the token: answering 401 would make the browser
# delete a valid sign-in, so these answer 503 and the client keeps its tokens.
AUTH_STORAGE_ERRORS = (sqlite3.Error, StorageUnavailable)

BCRYPT_HASH = re.compile(r"\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}")


def check_user_email(email: Any) -> None:
    # Stored addresses need only "@": the built-in admin@localhost must pass. The forms keep
    # their stricter rule for what a person types.
    if not isinstance(email, str) or "@" not in email:
        raise CheckError('email has no "@"', "The user's email address has no @")


def check_user(fields: Dict[str, Any]) -> None:
    """Raise CheckError for a stored password hash or email that reset or Edit email must fix; read no files or network."""
    if not isinstance(fields.get("password_hash"), str) or not BCRYPT_HASH.fullmatch(fields["password_hash"]):
        raise CheckError("password hash is not recognised", "The user's saved password cannot be checked")
    check_user_email(fields.get("email"))


@dataclass
class User:
    """Persisted user model returned by the auth service."""

    id: int
    username: str
    email: str
    role: str
    is_active: bool = True
    must_reset: bool = False
    last_login_ip: Optional[str] = None
    last_login_ip_type: Optional[str] = None
    review_reason: Optional[str] = None  # derived from the stored row on every read, never stored

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": str(self.id),
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "must_reset": self.must_reset,
            "last_login_ip": self.last_login_ip,
            "last_login_ip_type": self.last_login_ip_type,
        }



class AuthService:
    """
    Authentication facade consumed by the FastAPI routers and other services.

    Responsibilities:
    - User authentication and registration
    - Access and refresh token lifecycle (creation / verification / rotation)
    - Password reset support for administrators
    - Basic user queries for admin dashboards
    """

    def __init__(self) -> None:
        self.db: AuthDatabase = get_auth_database()

        # One-time bootstrap for the default admin account. Checked only when it would be written,
        # so a later bad ROBOTCONTROL_ADMIN_EMAIL never stops an existing installation.
        if not self.db.get_user_by_username(DEFAULT_ADMIN_USERNAME):
            admin = {"username": DEFAULT_ADMIN_USERNAME, "email": DEFAULT_ADMIN_EMAIL,
                     "password_hash": self.get_password_hash(DEFAULT_ADMIN_PASSWORD)}
            try:
                check_user(admin)
            except ValueError:
                raise ValueError('ROBOTCONTROL_ADMIN_EMAIL has no "@"') from None
            self.db.ensure_admin(**admin)

        # Cache configuration values locally for quick access
        self.access_token_expiry = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        self.refresh_token_expiry = timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)

        # Purge stale refresh tokens opportunistically
        removed = self.db.purge_expired_tokens()
        if removed:
            logger.info("Purged %s expired refresh tokens", removed)

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------
    def get_password_hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))
        except Exception as exc:
            logger.error("Password verification error: %s", exc)
            return False

    @staticmethod
    def is_built_in_password(password: str) -> bool:
        return secrets.compare_digest(password.encode("utf-8"), BUILT_IN_ADMIN_PASSWORD.encode("utf-8"))

    def has_built_in_password(self, username: str, password: str) -> bool:
        """True when `password` is the built-in default and is this active account's current password.

        Checked at sign-in rather than stored: no schema change, and it stops applying the
        moment the password changes. A wrong password is always False, so callers answer it
        like any other wrong password.
        """
        if not self.is_built_in_password(password):
            return False
        row = self.db.get_user_by_username(username)
        return bool(row and row["is_active"] and self.verify_password(password, row["password_hash"]))

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------
    def register_user(self, username: str, email: str, password: str) -> User:
        if self.db.get_user_by_username(username):
            raise ValueError("Username already taken")

        if self.db.get_user_by_email(email):
            raise ValueError("Email already registered")

        password_hash = self.get_password_hash(password)
        check_user({"email": email, "password_hash": password_hash})
        user_row = self.db.create_user(
            username=username,
            email=email,
            password_hash=password_hash,
            role="user",
        )
        logger.info("User '%s' registered successfully", username)
        return self._row_to_user(user_row)

    def authenticate_user(
        self,
        username: str,
        password: str,
        client_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[User]:
        user_row = self.db.get_user_by_username(username)
        if not user_row:
            logger.warning("Authentication failed: user '%s' not found", username)
            return None

        if not user_row["is_active"]:
            logger.warning("Authentication failed: user '%s' inactive", username)
            return None

        user = self._row_to_user(user_row)
        if user.review_reason:
            logger.warning("Authentication failed: user '%s' needs review: %s", username, user.review_reason)
            return None

        if not self.verify_password(password, user_row["password_hash"]):
            logger.warning("Authentication failed: invalid password for '%s'", username)
            return None

        if client_info:
            self._record_successful_login(user, client_info)
            # Refresh the row with last_login metadata
            user_row = self.db.get_user_by_id(user.id)
            user = self._row_to_user(user_row)

        logger.info("User '%s' authenticated (role=%s)", username, user.role)
        return user

    def reset_password(self, username: str, new_password: str, must_reset: bool) -> bool:
        user_row = self.db.get_user_by_username(username)
        if not user_row:
            return False
        password_hash = self.get_password_hash(new_password)
        self.db.update_password(user_row["id"], password_hash, must_reset=must_reset)
        self.db.revoke_tokens_for_user(user_row["id"])
        logger.info("Password reset for user '%s'", username)
        return True

    def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        row = self.db.get_user_by_id(int(user_id))
        if not row:
            return False
        if not self.verify_password(current_password, row["password_hash"]):
            return False

        password_hash = self.get_password_hash(new_password)
        self.db.update_password(int(user_id), password_hash, must_reset=False)
        self.db.revoke_tokens_for_user(int(user_id))
        logger.info("User '%s' changed password", row["username"])
        return True

    def request_password_reset(
        self,
        username: Optional[str],
        email: Optional[str],
        note: Optional[str],
        client_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not username and not email:
            raise ValueError("Username or email is required")

        user_row = None
        if username:
            user_row = self.db.get_user_by_username(username)
        if not user_row and email:
            user_row = self.db.get_user_by_email(email)

        if user_row:
            if username and user_row["username"] != username:
                raise ValueError("Username and email do not match")
            if email and user_row["email"].lower() != email.lower():
                raise ValueError("Username and email do not match")

            client_ip = client_info.get("ip") if client_info else None
            user_agent = client_info.get("user_agent") if client_info else None
            request_row = self.db.create_password_reset_request(
                user_id=user_row["id"],
                username=user_row["username"],
                email=user_row["email"],
                note=note,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            logger.info(
                "Password reset request logged for user '%s' (ip=%s)",
                user_row["username"],
                client_ip,
            )
            return request_row

        logger.warning(
            "Password reset request for unknown account (username=%s, email=%s)",
            username,
            email,
        )
        return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Compatibility helper returning raw database row."""
        return self.db.get_user_by_username(username)


    def get_user_by_id(self, user_id: str) -> Optional[User]:
        row = self.db.get_user_by_id(int(user_id))
        return self._row_to_user(row) if row else None

    def get_user_list(self) -> List[Dict[str, Any]]:
        users = []
        for row in self.db.list_users():
            user = self._row_to_user(row)
            users.append(
                {
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "must_reset": user.must_reset,
                    "last_login": row.get("last_login_at"),
                    "last_login_ip": user.last_login_ip,
                    "last_login_ip_type": user.last_login_ip_type,
                    "created_at": row.get("created_at"),
                    "review_reason": user.review_reason,
                }
        )
        return users


    def get_password_reset_requests(
        self,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self.db.list_password_reset_requests(status=status)

    def resolve_password_reset_request(
        self,
        request_id: int,
        resolved_by: str,
        resolution_note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.db.resolve_password_reset_request(
            request_id=request_id,
            resolved_by=resolved_by,
            resolution_note=resolution_note,
        )


    def update_user_email(self, username: str, email: str) -> bool:
        normalized_email = (email or "").strip()
        if not normalized_email:
            raise ValueError("Email address is required")
        check_user_email(normalized_email)
        success = self.db.update_user_email(username, normalized_email)
        if success:
            logger.info("Updated email for user '%s'", username)
        return success

    def delete_user(self, username: str) -> bool:
        success = self.db.delete_user(username)
        if success:
            logger.info("Deleted user '%s'", username)
        return success

    def is_admin(self, user: User) -> bool:
        return user.role == "admin"

    # ------------------------------------------------------------------
    # Token operations
    # ------------------------------------------------------------------
    def create_access_token(
        self,
        user: User,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        expire = datetime.utcnow() + (expires_delta or self.access_token_expiry)
        payload = {"user_id": str(user.id), "type": "access", "exp": expire, "iat": datetime.utcnow()}
        token = jwt.encode(payload, token_secrets()[0], algorithm=ALGORITHM)
        logger.debug("Access token issued for %s (expires %s)", user.username, expire)
        return token

    def create_refresh_token(self, user: User) -> str:
        expire = datetime.utcnow() + self.refresh_token_expiry
        jti = secrets.token_hex(16)
        payload = {
            "user_id": user.to_dict()["user_id"],
            "jti": jti,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, token_secrets()[1], algorithm=ALGORITHM)
        token_hash = self._hash_token(token)
        self.db.store_refresh_token(user.id, token_hash, expire)
        # Keep only the most recent token active
        self.db.revoke_tokens_for_user(user.id, except_hash=token_hash)
        logger.debug("Refresh token stored for %s (expires %s)", user.username, expire)
        return token

    def verify_token(self, token: str) -> Optional[User]:
        try:
            payload = jwt.decode(token, token_secrets()[0], algorithms=[ALGORITHM])
            if payload.get("type") != "access":
                logger.warning("Invalid token type encountered during verification")
                return None

            row = self.db.get_user_by_id(int(payload["user_id"]))
            if not row or not row["is_active"]:
                logger.warning("Token verification failed: user inactive or missing")
                return None

            user = self._row_to_user(row)
            if user.review_reason:
                logger.warning("Token verification failed: user '%s' needs review", user.username)
                return None
            return user

        except jwt.ExpiredSignatureError:
            logger.debug("Access token expired")
            return None
        except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Invalid access token: %s", exc)
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        try:
            payload = jwt.decode(refresh_token, token_secrets()[1], algorithms=[ALGORITHM])
            if payload.get("type") != "refresh":
                logger.warning("Refresh attempt with incorrect token type")
                return None

            token_hash = self._hash_token(refresh_token)
            stored = self.db.get_refresh_token(token_hash)
            if not stored or stored.get("revoked_at"):
                logger.warning("Refresh attempt with revoked token")
                return None

            expires_at = datetime.fromisoformat(stored["expires_at"])
            if datetime.utcnow() > expires_at:
                logger.warning("Refresh attempt with expired token")
                self.db.revoke_refresh_token(token_hash)
                return None

            user = self.get_user_by_id(payload["user_id"])
            if not user or not user.is_active or user.review_reason:
                logger.warning("Refresh attempt for inactive user or user under review")
                return None

            return self.create_access_token(user)

        except jwt.ExpiredSignatureError:
            logger.warning("Refresh token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.warning("Invalid refresh token: %s", exc)
            return None

    def login(
        self,
        username: str,
        password: str,
        client_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        user = self.authenticate_user(username, password, client_info=client_info)
        if not user:
            return None

        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": int(self.access_token_expiry.total_seconds()),
            "user": user.to_dict(),
        }

    def revoke_refresh_token(self, refresh_token: str) -> None:
        token_hash = self._hash_token(refresh_token)
        self.db.revoke_refresh_token(token_hash)

    def _row_to_user(self, row: Dict[str, Any]) -> User:
        try:
            check_user(row)
            review_reason = None
        except CheckError as exc:
            review_reason = exc.review_reason
        return User(
            review_reason=review_reason,
            id=row["id"],
            username=row["username"],
            email=row["email"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            must_reset=bool(row.get("must_reset", 0)),
            last_login_ip=row.get("last_login_ip"),
            last_login_ip_type=row.get("last_login_ip_type"),
        )

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _record_successful_login(
        self,
        user: User,
        client_info: Dict[str, Any],
    ) -> None:
        ip_address = client_info.get("ip")
        ip_type = client_info.get("ip_classification")
        self.db.update_last_login(user.id, ip_address, ip_type)

# Global service instance
_auth_service: Optional[AuthService] = None

# Browsers keep the sign-in in two HttpOnly cookies, out of reach of page scripts.
ACCESS_COOKIE = "rc_access"
REFRESH_COOKIE = "rc_refresh"
_COOKIE_PATHS = {ACCESS_COOKIE: "/api", REFRESH_COOKIE: "/api/auth"}


def request_token(request: Request) -> str:
    """The access token: a Bearer header (programs) wins, else the rc_access cookie (browsers)."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip() if scheme.lower() == "bearer" else ""
    token = token or request.cookies.get(ACCESS_COOKIE, "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def _secure(request: Request) -> bool:
    # The tunnel serves HTTPS and forwards plain http; the lab PC opens http://localhost,
    # where a Secure cookie would not be kept by every browser.
    return request.url.scheme == "https" or "https" in request.headers.get("x-forwarded-proto", "").lower()


def set_sign_in_cookies(response: Response, request: Request, access_token: str,
                        refresh_token: Optional[str] = None) -> None:
    lifetimes = {ACCESS_COOKIE: ACCESS_TOKEN_EXPIRE_MINUTES * 60, REFRESH_COOKIE: REFRESH_TOKEN_EXPIRE_HOURS * 3600}
    for name, value in ((ACCESS_COOKIE, access_token), (REFRESH_COOKIE, refresh_token)):
        if value:
            response.set_cookie(name, value, max_age=lifetimes[name], path=_COOKIE_PATHS[name],
                                httponly=True, samesite="strict", secure=_secure(request))


def clear_sign_in_cookies(response: Response, request: Request) -> None:
    for name, path in _COOKIE_PATHS.items():
        response.delete_cookie(name, path=path, httponly=True, samesite="strict", secure=_secure(request))


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
        logger.info("AuthService singleton instance created")
    return _auth_service


def get_current_user(token: str = Depends(request_token)) -> Dict[str, Any]:
    service = get_auth_service()
    try:
        user = service.verify_token(token)
    except AUTH_STORAGE_ERRORS as exc:
        logger.error("Sign-in storage unavailable during token verification: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in storage is temporarily unavailable",
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user.to_dict()


def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_auth_service()
    user = service.get_user_by_id(current_user["user_id"])
    if not user or not service.is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
