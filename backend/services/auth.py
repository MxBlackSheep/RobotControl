"""
PyRobot Authentication Service (persistent edition).

Replaces the in-memory user store with a SQLite-backed implementation so that:
- Users, hashed passwords, and refresh tokens persist across restarts
- New lab members can self-register with email tracking
- Admins can reset passwords without exposing credentials in source control
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import ipaddress
import logging
import os
import secrets
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext

from backend.services.auth_database import get_auth_database, AuthDatabase

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Configuration (environment overrides supported for deployments)
DEFAULT_ADMIN_USERNAME = os.getenv("PYROBOT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("PYROBOT_ADMIN_PASSWORD", "ShouGroupAdmin")
DEFAULT_ADMIN_EMAIL = os.getenv("PYROBOT_ADMIN_EMAIL", "admin@localhost")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("PYROBOT_ACCESS_TOKEN_MINUTES", "240"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("PYROBOT_REFRESH_TOKEN_HOURS", "168"))

ACCESS_TOKEN_SECRET = os.getenv(
    "PYROBOT_ACCESS_TOKEN_SECRET", "PyRobot_Access_Secret_2025"
)
REFRESH_TOKEN_SECRET = os.getenv(
    "PYROBOT_REFRESH_TOKEN_SECRET", "PyRobot_Refresh_Secret_2025"
)
ALGORITHM = "HS256"


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

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "User":
        return cls(
            id=int(payload["user_id"]),
            username=payload["username"],
            email=payload.get("email", ""),
            role=payload["role"],
            is_active=payload.get("is_active", True),
            must_reset=payload.get("must_reset", False),
            last_login_ip=payload.get("last_login_ip"),
            last_login_ip_type=payload.get("last_login_ip_type"),
        )


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

        # One-time bootstrap for the default admin account
        self.db.ensure_admin(
            username=DEFAULT_ADMIN_USERNAME,
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=pwd_context.hash(DEFAULT_ADMIN_PASSWORD),
        )

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
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as exc:
            logger.error("Password verification error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------
    def register_user(self, username: str, email: str, password: str) -> User:
        if self.db.get_user_by_username(username):
            raise ValueError("Username already taken")

        if self.db.get_user_by_email(email):
            raise ValueError("Email already registered")

        password_hash = self.get_password_hash(password)
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

        if not self.verify_password(password, user_row["password_hash"]):
            logger.warning("Authentication failed: invalid password for '%s'", username)
            return None

        user = self._row_to_user(user_row)

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

    def change_password(self, user: User, current_password: str, new_password: str) -> bool:
        row = self.db.get_user_by_id(user.id)
        if not row:
            return False
        if not self.verify_password(current_password, row["password_hash"]):
            return False

        password_hash = self.get_password_hash(new_password)
        self.db.update_password(user.id, password_hash, must_reset=False)
        self.db.revoke_tokens_for_user(user.id)
        self.db.clear_must_reset(user.id)
        logger.info("User '%s' changed password", user.username)
        return True

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Compatibility helper returning raw database row."""
        return self.db.get_user_by_username(username)

    def clear_must_reset(self, user_id: int) -> None:
        self.db.clear_must_reset(user_id)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        row = self.db.get_user_by_id(int(user_id))
        return self._row_to_user(row) if row else None

    def get_user_list(self) -> List[Dict[str, Any]]:
        users = []
        for row in self.db.list_users():
            user = self._row_to_user(row)
            users.append(
                {
                    "user_id": user.to_dict()["user_id"],
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "must_reset": user.must_reset,
                    "last_login_at": row.get("last_login_at"),
                    "last_login_ip": user.last_login_ip,
                    "last_login_ip_type": user.last_login_ip_type,
                    "created_at": row.get("created_at"),
                }
        )
        return users

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Backward-compatible alias for admin API."""
        return self.get_user_list()

    def toggle_user_active(self, username: str) -> bool:
        success = self.db.toggle_user_active(username)
        if success:
            logger.info("Toggled active state for user '%s'", username)
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
        payload = {
            "user_id": user.to_dict()["user_id"],
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "must_reset": user.must_reset,
            "last_login_ip": user.last_login_ip,
            "last_login_ip_type": user.last_login_ip_type,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        }
        token = jwt.encode(payload, ACCESS_TOKEN_SECRET, algorithm=ALGORITHM)
        logger.debug("Access token issued for %s (expires %s)", user.username, expire)
        return token

    def create_refresh_token(self, user: User) -> str:
        expire = datetime.utcnow() + self.refresh_token_expiry
        jti = secrets.token_hex(16)
        payload = {
            "user_id": user.to_dict()["user_id"],
            "username": user.username,
            "role": user.role,
            "jti": jti,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, REFRESH_TOKEN_SECRET, algorithm=ALGORITHM)
        token_hash = self._hash_token(token)
        self.db.store_refresh_token(user.id, token_hash, expire)
        # Keep only the most recent token active
        self.db.revoke_tokens_for_user(user.id, except_hash=token_hash)
        logger.debug("Refresh token stored for %s (expires %s)", user.username, expire)
        return token

    def verify_token(self, token: str) -> Optional[User]:
        try:
            payload = jwt.decode(token, ACCESS_TOKEN_SECRET, algorithms=[ALGORITHM])
            if payload.get("type") != "access":
                logger.warning("Invalid token type encountered during verification")
                return None

            user = User.from_payload(payload)
            row = self.db.get_user_by_id(user.id)
            if not row or not row["is_active"]:
                logger.warning("Token verification failed: user inactive or missing")
                return None

            return self._row_to_user(row)

        except jwt.ExpiredSignatureError:
            logger.warning("Access token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.warning("Invalid access token: %s", exc)
            return None
        except Exception as exc:
            logger.error("Token verification error: %s", exc)
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        try:
            payload = jwt.decode(
                refresh_token, REFRESH_TOKEN_SECRET, algorithms=[ALGORITHM]
            )
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
            if not user or not user.is_active:
                logger.warning("Refresh attempt for inactive user")
                return None

            return self.create_access_token(user)

        except jwt.ExpiredSignatureError:
            logger.warning("Refresh token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.warning("Invalid refresh token: %s", exc)
            return None
        except Exception as exc:
            logger.error("Refresh token processing error: %s", exc)
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

    def get_auth_stats(self) -> Dict[str, Any]:
        users = self.db.list_users()
        active_users = [u for u in users if u["is_active"]]
        admin_users = [u for u in users if u["role"] == "admin"]
        return {
            "total_users": len(users),
            "active_users": len(active_users),
            "admin_users": len(admin_users),
            "user_list": [u["username"] for u in active_users],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _row_to_user(self, row: Dict[str, Any]) -> User:
        return User(
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
        ip_type = self._classify_ip(ip_address)
        self.db.update_last_login(user.id, ip_address, ip_type)

    def _classify_ip(self, ip_address: Optional[str]) -> Optional[str]:
        if not ip_address:
            return None
        try:
            ip_obj = ipaddress.ip_address(ip_address)
            if ip_obj.is_loopback or ip_obj.is_private:
                return "local"
            return "remote"
        except ValueError:
            return "unknown"


# Global service instance
_auth_service: Optional[AuthService] = None
security = HTTPBearer()


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
        logger.info("AuthService singleton instance created")
    return _auth_service


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    service = get_auth_service()
    user = service.verify_token(credentials.credentials)

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


# Convenience wrappers for legacy imports
def authenticate_user(username: str, password: str) -> Optional[User]:
    service = get_auth_service()
    return service.authenticate_user(username, password)


def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    service = get_auth_service()
    return service.create_access_token(user, expires_delta)


def verify_token(token: str) -> Optional[User]:
    service = get_auth_service()
    return service.verify_token(token)


if __name__ == "__main__":
    service = get_auth_service()
    print("=== PyRobot Authentication Service ===")

    demo_user = service.authenticate_user("admin", DEFAULT_ADMIN_PASSWORD)
    if demo_user:
        login_payload = service.login("admin", DEFAULT_ADMIN_PASSWORD)
        print(f"Login successful: {login_payload['user']['username']}")
        print(f"Access token: {login_payload['access_token'][:32]}…")

    stats = service.get_auth_stats()
    print(f"Users: total={stats['total_users']} active={stats['active_users']}")
