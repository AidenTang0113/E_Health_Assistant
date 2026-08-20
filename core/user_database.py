"""用户数据库模块 — 企业级用户管理、认证、审计日志。

表结构:
    users          - 用户账号（username, password_hash, role, employee_name, employee_key, ...）
    user_audit_log - 操作审计日志

角色:
    HR      - 管理员（全权限）
    manager - 经理（查看全员）
    employee - 员工（仅个人）
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime
from typing import Optional

# ── 常量 ──────────────────────────────────────────────
HR = "HR"
MANAGER = "manager"
EMPLOYEE = "employee"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123456"
ADMIN_EMPLOYEE_KEY = "__admin__"

PBKDF2_ITERATIONS = 210_000
SALT_BYTES = 16
HASH_ALGO = "sha256"


# ── 密码哈希 ──────────────────────────────────────────
def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """pbkdf2_sha256 哈希，格式: pbkdf2_sha256$iterations$salt$digest"""
    if salt is None:
        salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        HASH_ALGO, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    import base64
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """验证密码（恒定时间比较）。"""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        import base64
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
        actual = hashlib.pbkdf2_hmac(
            HASH_ALGO, password.encode("utf-8"), salt, iterations
        )
        return secrets.compare_digest(expected, actual)
    except Exception:
        return False


class UserDatabase:
    """用户管理数据库。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._ensure_role_column()
        self._ensure_admin_account()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                employee_name TEXT,
                employee_key TEXT,
                gender TEXT,
                birth_year INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS user_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                target TEXT,
                operator TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)
        self._conn.commit()

    def _ensure_role_column(self) -> None:
        """处理旧库迁移：确保 role 列存在且 admin 角色正确。"""
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(users)").fetchall()]
        if "role" not in cols:
            self._conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'employee'")
            self._conn.commit()
        # 修正旧库中 admin 的角色
        admin = self._conn.execute(
            "SELECT id, role FROM users WHERE username = ?", (ADMIN_USERNAME,)
        ).fetchone()
        if admin and admin["role"] != HR:
            self._conn.execute(
                "UPDATE users SET role = ? WHERE username = ?", (HR, ADMIN_USERNAME)
            )
            self._conn.commit()

    def _ensure_admin_account(self) -> None:
        """确保 HR 管理员账号存在。"""
        admin = self._conn.execute(
            "SELECT id FROM users WHERE employee_key = ?", (ADMIN_EMPLOYEE_KEY,)
        ).fetchone()
        if not admin:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, role, employee_name, employee_key, is_active) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (ADMIN_USERNAME, _hash_password(ADMIN_PASSWORD), HR, ADMIN_USERNAME, ADMIN_EMPLOYEE_KEY),
            )
            self._conn.commit()
        else:
            # 已存在则仅更新角色和激活状态，不覆盖密码
            self._conn.execute(
                "UPDATE users SET role = ?, is_active = 1 WHERE employee_key = ?",
                (HR, ADMIN_EMPLOYEE_KEY),
            )
            self._conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def _log_action(self, action: str, target: str = "", operator: str = "", detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO user_audit_log (action, target, operator, detail) VALUES (?, ?, ?, ?)",
            (action, target, operator, detail),
        )
        self._conn.commit()

    # ── 认证 ──────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """验证登录，成功返回用户 dict 并更新 last_login_at。"""
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        if not row:
            return None
        if not _verify_password(password, row["password_hash"]):
            return None
        self._conn.execute(
            "UPDATE users SET last_login_at = datetime('now','localtime') WHERE id = ?",
            (row["id"],),
        )
        self._conn.commit()
        self._log_action("login", username, username)
        return dict(row)

    # ── 查询 ──────────────────────────────────────────

    def list_users(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_users_by_role(self, role: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM users WHERE role = ? AND is_active = 1 ORDER BY id",
            (role,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_user(self, username: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_employee_key(self, key: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE employee_key = ?", (key,)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_employee_name(self, name: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE employee_name = ? AND is_active = 1",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    # ── 员工账号同步 ──────────────────────────────────

    def ensure_employee_account(
        self, employee: dict, employee_id: Optional[int] = None
    ) -> tuple[bool, str]:
        """为员工创建或更新账号。

        - 新员工：默认密码 = 用户名
        - 已有账号：更新 employee_name/gender，不覆盖密码
        - legacy 迁移：username 与 employee_name 不一致时更新
        """
        name = employee.get("name") or employee.get("employee_name", "")
        gender = employee.get("gender", "")
        emp_key = str(employee_id) if employee_id else name

        existing = self._conn.execute(
            "SELECT * FROM users WHERE employee_key = ?", (emp_key,)
        ).fetchone()

        if existing:
            # 更新姓名和性别，不改密码
            updates = []
            params = []
            if existing["employee_name"] != name:
                updates.append("employee_name = ?")
                params.append(name)
            if existing["gender"] != gender:
                updates.append("gender = ?")
                params.append(gender)
            # legacy: 如果 username 和 employee_name 不一致，统一
            if existing["username"] != name and existing["role"] == EMPLOYEE:
                # 检查目标用户名是否已被其他账号占用
                clash = self._conn.execute(
                    "SELECT id FROM users WHERE username = ? AND id != ?",
                    (name, existing["id"]),
                ).fetchone()
                if not clash:
                    updates.append("username = ?")
                    params.append(name)
            if updates:
                params.append(existing["id"])
                self._conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params
                )
                self._conn.commit()
                self._log_action("update_employee_account", name, "system")
                return (True, "账号已更新")
            return (False, "账号无变化")

        # 新建账号
        username = name
        # 避免用户名冲突
        clash = self._conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if clash:
            username = f"{name}_{emp_key}"

        self._conn.execute(
            "INSERT INTO users (username, password_hash, role, employee_name, employee_key, gender, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (username, _hash_password(name), EMPLOYEE, name, emp_key, gender),
        )
        self._conn.commit()
        self._log_action("create_employee_account", name, "system")
        return (True, f"已创建账号 {username}，初始密码为用户名")

    def sync_employees(self, employees: list[dict]) -> int:
        """批量同步员工账号，返回新建数量。"""
        count = 0
        for emp in employees:
            created, _ = self.ensure_employee_account(emp, employee_id=emp.get("id"))
            if created:
                count += 1
        return count

    # ── 个人资料 ──────────────────────────────────────

    def update_user_profile(
        self,
        username: str,
        new_username: Optional[str] = None,
        old_password: Optional[str] = None,
        new_password: Optional[str] = None,
        birth_year: Optional[int] = None,
    ) -> tuple[bool, str]:
        """修改用户名/密码/出生年。改密码需验证旧密码。"""
        user = self.get_user(username)
        if not user:
            return (False, "用户不存在")

        updates = []
        params = []

        if new_username and new_username != username:
            clash = self._conn.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (new_username, user["id"]),
            ).fetchone()
            if clash:
                return (False, "用户名已存在")
            updates.append("username = ?")
            params.append(new_username)

        if new_password:
            if not old_password:
                return (False, "修改密码需提供旧密码")
            if not _verify_password(old_password, user["password_hash"]):
                return (False, "旧密码错误")
            updates.append("password_hash = ?")
            params.append(_hash_password(new_password))

        if birth_year is not None:
            updates.append("birth_year = ?")
            params.append(birth_year)

        if not updates:
            return (False, "未检测到更改")

        params.append(user["id"])
        self._conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params
        )
        self._conn.commit()
        self._log_action("update_profile", username, username)
        return (True, "资料更新成功")

    # ── 管理操作 ──────────────────────────────────────

    def reset_password(self, username: str, operator: str = "") -> Optional[str]:
        """重置密码为用户名，返回新密码。"""
        user = self.get_user(username)
        if not user:
            return None
        if user["role"] == HR:
            return None
        new_pw = username  # 重置密码 = 用户名
        self._conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(new_pw), user["id"]),
        )
        self._conn.commit()
        self._log_action("reset_password", username, operator)
        return new_pw

    def deactivate_user(self, username: str, operator: str = "") -> bool:
        """停用账号（软删除）。admin 不可停用。"""
        user = self.get_user(username)
        if not user or user["role"] == HR:
            return False
        self._conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?", (user["id"],)
        )
        self._conn.commit()
        self._log_action("deactivate", username, operator)
        return True

    def reactivate_user(self, username: str, operator: str = "") -> bool:
        """启用账号。"""
        user = self.get_user(username)
        if not user:
            return False
        self._conn.execute(
            "UPDATE users SET is_active = 1 WHERE id = ?", (user["id"],)
        )
        self._conn.commit()
        self._log_action("reactivate", username, operator)
        return True

    def delete_user(
        self,
        username: str,
        operator: str = "",
        delete_records: bool = False,
        health_db=None,
    ) -> bool:
        """删除账号。admin 不可删除。delete_records=True 时连带删除健康档案。"""
        user = self.get_user(username)
        if not user or user["role"] == HR:
            return False

        if delete_records and health_db and user.get("employee_key"):
            try:
                conn = health_db._get_conn()
                emp_key = user["employee_key"]
                # 按 employee_key 查找员工并删除其健康记录
                emp_row = conn.execute(
                    "SELECT id FROM employees WHERE name = ?", (user["employee_name"],)
                ).fetchone()
                if emp_row:
                    conn.execute(
                        "DELETE FROM health_records WHERE employee_id = ?",
                        (emp_row["id"],),
                    )
                    conn.execute("DELETE FROM employees WHERE id = ?", (emp_row["id"],))
                    conn.commit()
            except Exception:
                pass

        self._conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        self._conn.commit()
        self._log_action("delete_user", username, operator, "delete_records=" + str(delete_records))
        return True

    def delete_all_users(self, keep_admin: bool = True) -> int:
        """删除所有用户账号，返回删除数量。"""
        if keep_admin:
            count = self._conn.execute(
                "SELECT COUNT(*) as c FROM users WHERE role != ?", (HR,)
            ).fetchone()["c"]
            self._conn.execute("DELETE FROM users WHERE role != ?", (HR,))
        else:
            count = self._conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            self._conn.execute("DELETE FROM users")
        self._conn.commit()
        self._log_action("delete_all_users", "", "system", f"deleted={count}")
        return count

    # ── 角色管理 ──────────────────────────────────────

    def promote_employee_to_manager(self, employee_name: str) -> bool:
        """将员工提升为经理。"""
        user = self.get_user_by_employee_name(employee_name)
        if not user or user["role"] != EMPLOYEE:
            return False
        self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?", (MANAGER, user["id"])
        )
        self._conn.commit()
        self._log_action("promote_to_manager", employee_name, "HR")
        return True

    def demote_manager_by_name(self, employee_name: str) -> bool:
        """将经理降为员工。"""
        user = self.get_user_by_employee_name(employee_name)
        if not user or user["role"] != MANAGER:
            return False
        self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?", (EMPLOYEE, user["id"])
        )
        self._conn.commit()
        self._log_action("demote_to_employee", employee_name, "HR")
        return True

    def create_manager_account(self, name: str, username: str, password: str) -> bool:
        """创建经理账号。用户名冲突时 raise ValueError。"""
        clash = self._conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if clash:
            raise ValueError("用户名已存在")
        self._conn.execute(
            "INSERT INTO users (username, password_hash, role, employee_name, employee_key, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (username, _hash_password(password), MANAGER, name, f"mgr_{username}",),
        )
        self._conn.commit()
        self._log_action("create_manager", name, "HR")
        return True

    # ── 审计日志 ──────────────────────────────────────

    def list_audit_logs(self, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM user_audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 清理 ──────────────────────────────────────────

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
