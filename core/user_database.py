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
    HR_ROLE = "HR"
    MANAGER_ROLE = "manager"
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

            CREATE TABLE IF NOT EXISTS user_audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                action     TEXT NOT NULL,
                target     TEXT NOT NULL,
                operator   TEXT NOT NULL,
                detail     TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
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
        conn.execute(
            "UPDATE users SET role = ? WHERE username = ? OR role = ?",
            (self.HR_ROLE, self.ADMIN_USERNAME, "admin"),
        )
        conn.commit()

    def _log_action(self, action: str, target: str, operator: str, detail: str = "") -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO user_audit_log (action, target, operator, detail) "
            "VALUES (?, ?, ?, ?)",
            (action, target, operator, detail),
        )
        conn.commit()

    def list_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, action, target, operator, detail, created_at "
            "FROM user_audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

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
                    self.HR_ROLE,
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
                    self.HR_ROLE,
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

    def list_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, employee_key, employee_name, gender, role, birth_year, employee_id, "
            "username, is_active, created_at, updated_at, last_login_at "
            "FROM users WHERE role = ? ORDER BY id",
            (role,),
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

    def get_user_by_employee_name(self, employee_name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, employee_key, employee_name, gender, role, birth_year, employee_id, "
            "username, password_hash, is_active, created_at, updated_at, last_login_at "
            "FROM users WHERE employee_name = ? ORDER BY id LIMIT 1",
            (employee_name.strip(),),
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
            if existing["role"] not in (self.EMPLOYEE_ROLE, self.MANAGER_ROLE):
                updates.append("role = ?")
                params.append(self.EMPLOYEE_ROLE)
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
                employee_key, employee_name, gender, role, birth_year,
                employee_id, username, password_hash, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                key,
                name,
                gender,
                self.EMPLOYEE_ROLE,
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

    def update_user_profile(
        self,
        username: str,
        new_username: str | None = None,
        old_password: str | None = None,
        new_password: str | None = None,
        birth_year: int | None = None,
    ) -> tuple[bool, str]:
        """
        更新用户资料（用户名/密码/出生年）。
        修改密码需验证旧密码，管理员不得通过此接口修改。

        Returns:
            (success, message)
        """
        conn = self._get_conn()
        user = conn.execute(
            "SELECT id, role, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            return False, "账号不存在"
        if user["role"] == self.HR_ROLE:
            return False, "管理员账号不允许自助修改"

        # 新用户名冲突检查
        if new_username and new_username != username:
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? AND username != ?",
                (new_username, username),
            ).fetchone()
            if existing:
                return False, f"用户名 '{new_username}' 已被使用"

        # 密码修改需验证旧密码
        if new_password:
            if not old_password:
                return False, "修改密码需提供旧密码"
            if not self._verify_password(old_password, user["password_hash"]):
                return False, "旧密码错误"
            password_hash = self._hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE username = ?",
                (password_hash, username),
            )

        # 更新用户名
        if new_username and new_username != username:
            conn.execute(
                "UPDATE users SET username = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE username = ?",
                (new_username, username),
            )

        # 更新出生年
        if birth_year is not None:
            conn.execute(
                "UPDATE users SET birth_year = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE username = ?",
                (birth_year, username),
            )

        conn.commit()
        return True, "更新成功"

    def reset_password(self, username: str, new_password: Optional[str] = None, operator: str = "system") -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, employee_name, gender, role, birth_year, username FROM users WHERE username = ?",
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
        self._log_action("reset_password", username, operator)
        return password

    def deactivate_user(self, username: str, operator: str = "system") -> bool:
        """停用用户账号（软删除），保留健康档案。"""
        if username == self.ADMIN_USERNAME:
            return False
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE users SET is_active = 0, updated_at = datetime('now', 'localtime') "
            "WHERE username = ? AND is_active = 1",
            (username,),
        )
        conn.commit()
        if cur.rowcount > 0:
            self._log_action("deactivate", username, operator)
            return True
        return False

    def reactivate_user(self, username: str, operator: str = "system") -> bool:
        """重新启用已停用的账号。"""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE users SET is_active = 1, updated_at = datetime('now', 'localtime') "
            "WHERE username = ? AND is_active = 0",
            (username,),
        )
        conn.commit()
        if cur.rowcount > 0:
            self._log_action("reactivate", username, operator)
            return True
        return False

    def delete_user(
        self,
        username: str,
        *,
        delete_records: bool = False,
        health_db=None,
        operator: str = "system",
    ) -> bool:
        """
        硬删除用户账号。

        Args:
            username: 用户名
            delete_records: 是否同时删除健康档案（默认 False）
            health_db: HealthDatabase 实例（delete_records=True 时必传）
            operator: 操作者（用于审计日志）
        """
        if username == self.ADMIN_USERNAME:
            return False

        conn = self._get_conn()
        user = self.get_user(username)
        if not user:
            return False

        # 可选：连带删除健康档案
        if delete_records and health_db and user.get("employee_id"):
            h_conn = health_db._get_conn()
            # health_records 通过 FK ON DELETE CASCADE 自动级联
            h_conn.execute("DELETE FROM employees WHERE id = ?", (user["employee_id"],))
            h_conn.commit()
            self._log_action(
                "delete_records", username, operator,
                detail=f"employee_id={user['employee_id']}",
            )

        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        self._log_action(
            "delete_user", username, operator,
            detail=f"delete_records={'yes' if delete_records else 'no'}",
        )
        return True

    def delete_all_users(self, keep_admin: bool = True) -> int:
        conn = self._get_conn()
        if keep_admin:
            cur = conn.execute("DELETE FROM users WHERE username <> ?", (self.ADMIN_USERNAME,))
        else:
            cur = conn.execute("DELETE FROM users")
        conn.commit()
        self._ensure_admin_account()
        return cur.rowcount

    def promote_employee_to_manager(self, employee_name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        user = self.get_user_by_employee_name(employee_name)
        if not user:
            return None
        if user.get("role") == self.HR_ROLE:
            return user
        conn.execute(
            "UPDATE users SET role = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (self.MANAGER_ROLE, user["id"]),
        )
        conn.commit()
        self._log_action("promote_to_manager", employee_name, "system")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return self._row_to_dict(row)

    def demote_manager_by_name(self, employee_name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        user = self.get_user_by_employee_name(employee_name)
        if not user or user.get("role") != self.MANAGER_ROLE:
            return None
        conn.execute(
            "UPDATE users SET role = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (self.EMPLOYEE_ROLE, user["id"]),
        )
        conn.commit()
        self._log_action("demote_to_employee", employee_name, "system")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return self._row_to_dict(row)

    def create_manager_account(
        self,
        employee_name: str,
        username: str,
        password: str,
        gender: str = "manager",
    ) -> Tuple[Dict[str, Any], str]:
        conn = self._get_conn()
        employee_name = employee_name.strip() or username.strip()
        username = username.strip()
        if not employee_name or not username or not password:
            raise ValueError("missing manager account fields")
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if existing:
            raise ValueError("username already exists")
        password_hash = self._hash_password(password)
        conn.execute(
            """
            INSERT INTO users (
                employee_key, employee_name, gender, role, birth_year,
                employee_id, username, password_hash, is_active
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 1)
            """,
            (
                f"manager|{username}",
                employee_name,
                gender,
                self.MANAGER_ROLE,
                username,
                password_hash,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return self._row_to_dict(row), password

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        self.close()
