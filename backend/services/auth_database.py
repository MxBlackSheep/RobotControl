"""
SQLite-backed persistence layer for the authentication service.

Stores user accounts, refresh tokens, and login metadata in a lightweight
database that lives alongside other RobotControl data artefacts. Designed to work
both in development and when the application is packaged with PyInstaller.
"""

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.utils.data_paths import get_data_path

logger = logging.getLogger(__name__)


class AuthDatabase:
    """Lightweight SQLite wrapper for authentication data."""

    def __init__(self, db_name: str = "robotcontrol_auth.db") -> None:
        db_filename = os.getenv("ROBOTCONTROL_AUTH_DB_FILENAME", db_name)
        self.db_path: Path = get_data_path() / db_filename
        self._lock = threading.RLock()
        self._initialised = False
        self._ensure_database()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_database(self) -> None:
        """Create schema lazily on first use."""
        with self._lock:
            if self._initialised:
                return

            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                        is_active INTEGER NOT NULL DEFAULT 1,
                        must_reset INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_login_at TEXT,
                        last_login_ip TEXT,
                        last_login_ip_type TEXT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS refresh_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        issued_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        revoked_at TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tokens_user ON refresh_tokens(user_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tokens_hash ON refresh_tokens(token_hash)"
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS password_reset_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT NOT NULL,
                        email TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        note TEXT,
                        client_ip TEXT,
                        user_agent TEXT,
                        requested_at TEXT NOT NULL,
                        resolved_at TEXT,
                        resolved_by TEXT,
                        resolution_note TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_password_reset_status
                    ON password_reset_requests(status, requested_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_password_reset_user
                    ON password_reset_requests(username)
                    """
                )
                conn.commit()

            self._initialised = True
            logger.info("Auth database initialised at %s", self.db_path)

    @contextmanager
    def _get_connection(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------
    def ensure_admin(self, username: str, email: str, password_hash: str) -> None:
        """Guarantee a single bootstrap admin user exists."""
        now = datetime.utcnow().isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            )
            if cursor.fetchone():
                return

            cursor.execute(
                """
                INSERT INTO users (
                    username, email, password_hash, role,
                    is_active, must_reset, created_at, updated_at
                )
                VALUES (?, ?, ?, 'admin', 1, 0, ?, ?)
                """,
                (username, email, password_hash, now, now),
            )
            conn.commit()
            logger.info("Bootstrap admin user '%s' created", username)

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: str,
        must_reset: bool = False,
    ) -> Dict[str, Any]:
        """Create a new user account."""
        now = datetime.utcnow().isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (
                    username, email, password_hash, role,
                    is_active, must_reset, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (username, email, password_hash, role, int(must_reset), now, now),
            )
            user_id = cursor.lastrowid
            conn.commit()
            return self.get_user_by_id(user_id)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_last_login(
        self,
        user_id: int,
        ip_address: Optional[str],
        ip_type: Optional[str],
    ) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET last_login_at = ?, last_login_ip = ?, last_login_ip_type = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    datetime.utcnow().isoformat(),
                    ip_address,
                    ip_type,
                    datetime.utcnow().isoformat(),
                    user_id,
                ),
            )
            conn.commit()

    def list_users(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY username ASC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def toggle_user_active(self, username: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, is_active FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            new_status = 0 if row["is_active"] else 1
            cursor.execute(
                """
                UPDATE users
                SET is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_status, datetime.utcnow().isoformat(), row["id"]),
            )
            conn.commit()
            return True

    def update_user_email(self, username: str, email: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE users
                    SET email = ?, updated_at = ?
                    WHERE username = ?
                    """,
                    (email, datetime.utcnow().isoformat(), username),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return False
            return cursor.rowcount > 0

    def delete_user(self, username: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if not row:
                return False
            user_id = row["id"]
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_password(
        self,
        user_id: int,
        password_hash: str,
        must_reset: bool = False,
    ) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, must_reset = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    password_hash,
                    int(must_reset),
                    datetime.utcnow().isoformat(),
                    user_id,
                ),
            )
            conn.commit()

    def clear_must_reset(self, user_id: int) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET must_reset = 0, updated_at = ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), user_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Refresh token management
    # ------------------------------------------------------------------
    def store_refresh_token(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, issued_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    token_hash,
                    datetime.utcnow().isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()

    def revoke_refresh_token(self, token_hash: str) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE refresh_tokens
                SET revoked_at = ?
                WHERE token_hash = ?
                """,
                (datetime.utcnow().isoformat(), token_hash),
            )
            conn.commit()

    def revoke_tokens_for_user(
        self,
        user_id: int,
        except_hash: Optional[str] = None,
    ) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if except_hash:
                cursor.execute(
                    """
                    UPDATE refresh_tokens
                    SET revoked_at = ?
                    WHERE user_id = ? AND token_hash != ?
                    """,
                    (datetime.utcnow().isoformat(), user_id, except_hash),
                )
            else:
                cursor.execute(
                    """
                    UPDATE refresh_tokens
                    SET revoked_at = ?
                    WHERE user_id = ?
                    """,
                    (datetime.utcnow().isoformat(), user_id),
                )
            conn.commit()

    def get_refresh_token(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM refresh_tokens WHERE token_hash = ?",
                (token_hash,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def purge_expired_tokens(self) -> int:
        """Delete tokens that expired more than 24h ago to keep the table tidy."""
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM refresh_tokens
                WHERE expires_at < ?
                """,
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    # ------------------------------------------------------------------
    # Password reset request management
    # ------------------------------------------------------------------
    def create_password_reset_request(
        self,
        user_id: Optional[int],
        username: str,
        email: str,
        note: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO password_reset_requests (
                    user_id, username, email, status, note,
                    client_ip, user_agent, requested_at
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    email,
                    note,
                    client_ip,
                    user_agent,
                    now,
                ),
            )
            request_id = cursor.lastrowid
            conn.commit()
            return self.get_password_reset_request(request_id)

    def get_password_reset_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM password_reset_requests WHERE id = ?",
                (request_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_password_reset_requests(
        self,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    """
                    SELECT * FROM password_reset_requests
                    WHERE status = ?
                    ORDER BY requested_at DESC
                    """,
                    (status,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM password_reset_requests
                    ORDER BY requested_at DESC
                    """
                )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def resolve_password_reset_request(
        self,
        request_id: int,
        resolved_by: str,
        resolution_note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE password_reset_requests
                SET status = 'resolved',
                    resolved_at = ?,
                    resolved_by = ?,
                    resolution_note = ?
                WHERE id = ?
                """,
                (
                    now,
                    resolved_by,
                    resolution_note,
                    request_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
            return self.get_password_reset_request(request_id)

    def delete_password_reset_request(self, request_id: int) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM password_reset_requests WHERE id = ?",
                (request_id,),
            )
            conn.commit()


_auth_db_instance: Optional[AuthDatabase] = None
_auth_db_lock = threading.Lock()


def get_auth_database() -> AuthDatabase:
    """Singleton accessor so multiple services reuse the same database manager."""
    global _auth_db_instance
    if _auth_db_instance is None:
        with _auth_db_lock:
            if _auth_db_instance is None:
                _auth_db_instance = AuthDatabase()
    return _auth_db_instance
