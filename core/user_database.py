"""
User account database for employee login and registration.

Accounts live in a separate SQLite file so report database resets do not
remove employee credentials.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class UserDatabase:
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "123456"
    ADMIN_EMPLOYEE_KEY = "__admin__"
    ADMIN_ROLE = "admin"
    EMPLOYEE_ROLE = "employee"

    def __init__(self, db_path: str = "data/users.db") -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_key  TEXT NOT NULL UNIQUE,
                employee_name TEXT NOT NULL,
                gender        TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'employee',
                birth_year    INTEGER,
                employee_id   INTEGER,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                last_login_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_users_employee_id
                ON users(employee_id);
            """
        )
        self._ensure_role_column()
        conn.commit()
        self._ensure_admin_account()

    def _ensure_role_column(self) -> None:
        conn = self._get_conn()
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'employee'"
            )
            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    @staticmethod
    def _employee_key(employee: Dict[str, Any]) -> str:
        name = str(employee.get("name", "")).strip()
        gender = str(employee.get("gender", "")).strip()
        return f"{name}|{gender}"

    @staticmethod
    def _default_username(employee: Dict[str, Any]) -> str:
        name = str(employee.get("name", "")).strip() or "employee"
        return name.replace(" ", "")

    @staticmethod
    def _legacy_username(employee: Dict[str, Any]) -> str:
        name = str(employee.get("name", "")).strip() or "employee"
        gender = str(employee.get("gender", "")).strip() or "user"
        return f"{name}_{gender}".replace(" ", "")

    def _ensure_admin_account(self) -> None:
        conn = self._get_conn()
        password_hash = self._hash_password(self.ADMIN_PASSWORD)
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (self.ADMIN_USERNAME,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users
                SET employee_key = ?, employee_name = ?, gender = ?, role = ?,
                    birth_year = NULL, employee_id = NULL, password_hash = ?,
                    is_active = 1,
                    updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (
                    self.ADMIN_EMPLOYEE_KEY,
                    self.ADMIN_USERNAME,
                    "admin",
                    self.ADMIN_ROLE,
                    password_hash,
                    row["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (
                    employee_key, employee_name, gender, role, birth_year,
                    employee_id, username, password_hash, is_active
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 1)
                """,
                (
                    self.ADMIN_EMPLOYEE_KEY,
                    self.ADMIN_USERNAME,
                    "admin",
                    self.ADMIN_ROLE,
                    self.ADMIN_USERNAME,
                    password_hash,
                ),
            )
        conn.commit()

    @staticmethod
    def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
        salt = salt or secrets.token_bytes(16)
        iterations = 210_000
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return "pbkdf2_sha256${}${}${}".format(
            iterations,
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            scheme, iter_text, salt_b64, digest_b64 = stored_hash.split("$", 3)
            if scheme != "pbkdf2_sha256":
                return False
            iterations = int(iter_text)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(digest_b64.encode("ascii"))
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
            )
            return secrets.compare_digest(actual, expected)
        except Exception:
            return False

    @staticmethod
    def _default_password(employee: Dict[str, Any]) -> str:
        # Simple default for internal CLI use: same as the username.
        return UserDatabase._default_username(employee)

    def _make_unique_username(self, base_username: str) -> str:
        conn = self._get_conn()
        username = base_username
        suffix = 2
        while conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        ).fetchone():
            username = f"{base_username}{suffix}"
            suffix += 1
        return username

    def list_users(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, employee_key, employee_name, gender, role, birth_year, employee_id, "
            "username, is_active, created_at, updated_at, last_login_at "
            "FROM users ORDER BY id"
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, employee_key, employee_name, gender, role, birth_year, employee_id, "
            "username, password_hash, is_active, created_at, updated_at, last_login_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_user_by_employee_key(self, employee_key: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, employee_key, employee_name, gender, role, birth_year, employee_id, "
            "username, password_hash, is_active, created_at, updated_at, last_login_at "
            "FROM users WHERE employee_key = ?",
            (employee_key,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def ensure_employee_account(
        self,
        employee: Dict[str, Any],
        employee_id: Optional[int] = None,
        password: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Ensure a persistent account exists for the given employee.

        Returns:
            (user_row, created_password_or_None)
        """
        conn = self._get_conn()
        key = self._employee_key(employee)
        name = str(employee.get("name", "")).strip() or "Unknown"
        gender = str(employee.get("gender", "")).strip() or "Unknown"
        birth_year = employee.get("birth_year")

        existing = conn.execute(
            "SELECT * FROM users WHERE employee_key = ?",
            (key,),
        ).fetchone()
        if existing:
            updates = []
            params: List[Any] = []
            legacy_username = self._legacy_username(employee)
            desired_username = self._default_username(employee)
            desired_password_hash = None
            password_needs_reset = False
            if employee_id is not None and existing["employee_id"] != employee_id:
                updates.append("employee_id = ?")
                params.append(employee_id)
            if existing["employee_name"] != name:
                updates.append("employee_name = ?")
                params.append(name)
            if existing["gender"] != gender:
                updates.append("gender = ?")
                params.append(gender)
            if existing["birth_year"] != birth_year:
                updates.append("birth_year = ?")
                params.append(birth_year)
            if existing["username"] == legacy_username and desired_username != existing["username"]:
                candidate = desired_username
                suffix = 2
                while conn.execute(
                    "SELECT 1 FROM users WHERE username = ? AND id != ?",
                    (candidate, existing["id"]),
                ).fetchone():
                    candidate = f"{desired_username}{suffix}"
                    suffix += 1
                if candidate != existing["username"]:
                    updates.append("username = ?")
                    params.append(candidate)
                    desired_username = candidate
                    desired_password_hash = self._hash_password(candidate)
                    password_needs_reset = True
            elif not self._verify_password(desired_username, existing["password_hash"]):
                desired_password_hash = self._hash_password(desired_username)
                password_needs_reset = True
            if updates:
                updates.append("updated_at = datetime('now', 'localtime')")
                params.append(existing["id"])
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
            if password_needs_reset and desired_password_hash:
                conn.execute(
                    "UPDATE users SET password_hash = ?, updated_at = datetime('now', 'localtime') "
                    "WHERE id = ?",
                    (desired_password_hash, existing["id"]),
                )
            if updates or password_needs_reset:
                conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (existing["id"],),
            ).fetchone()
            return self._row_to_dict(row), None

        base_username = self._default_username(employee)
        username = self._make_unique_username(base_username)
        plain_password = password or username
        password_hash = self._hash_password(plain_password)

        conn.execute(
            """
            INSERT INTO users (
                employee_key, employee_name, gender, birth_year,
                employee_id, username, password_hash, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                key,
                name,
                gender,
                birth_year,
                employee_id,
                username,
                password_hash,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM users WHERE employee_key = ?",
            (key,),
        ).fetchone()
        return self._row_to_dict(row), plain_password

    def sync_employees(
        self,
        employees: Iterable[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], Optional[str]]]:
        synced: List[Tuple[Dict[str, Any], Optional[str]]] = []
        for employee in employees:
            synced.append(
                self.ensure_employee_account(
                    employee,
                    employee_id=employee.get("id"),
                )
            )
        return synced

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        if not row:
            return None
        user = self._row_to_dict(row)
        if not self._verify_password(password, user["password_hash"]):
            return None
        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["id"]),
        )
        conn.commit()
        user.pop("password_hash", None)
        return user

    def reset_password(self, username: str, new_password: Optional[str] = None) -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, employee_name, gender, birth_year, username FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return None
        user = self._row_to_dict(row)
        password = new_password or self._default_password(user)
        password_hash = self._hash_password(password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (password_hash, user["id"]),
        )
        conn.commit()
        return password

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        self.close()
