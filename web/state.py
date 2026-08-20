"""会话状态与数据库连接管理。

所有 core/ 实例通过 st.session_state 缓存，避免每次交互重建。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def init_session_state() -> None:
    """初始化所有 session_state 键（仅执行一次）。"""
    defaults = {
        "user": None,              # 当前登录用户 dict
        "page": "login",           # 当前页面标识
        "selected_employee_id": None,  # 个人查看选中的员工
        "db": None,
        "user_db": None,
        "llm_agent": None,
        "toast": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_db():
    """获取 HealthDatabase 单例（缓存在 session_state）。"""
    if st.session_state.get("db") is None:
        from core.database import HealthDatabase
        st.session_state["db"] = HealthDatabase(
            str(PROJECT_ROOT / "data" / "health.db")
        )
    return st.session_state["db"]


def get_user_db():
    """获取 UserDatabase 单例。"""
    if st.session_state.get("user_db") is None:
        from core.user_database import UserDatabase
        st.session_state["user_db"] = UserDatabase(
            str(PROJECT_ROOT / "data" / "users.db")
        )
    return st.session_state["user_db"]


def get_llm_agent():
    """获取 LLMAgent 单例。"""
    if st.session_state.get("llm_agent") is None:
        from core.llm_agent import LLMAgent
        from core.config_manager import get_llm_config
        cfg = get_llm_config()
        st.session_state["llm_agent"] = LLMAgent(
            base_url=cfg["base_url"] or None,
            api_key=cfg["api_key"] or None,
            model_name=cfg["model"] or None,
        )
    return st.session_state["llm_agent"]


def current_user() -> dict | None:
    return st.session_state.get("user")


def current_role() -> str:
    user = current_user()
    return user.get("role", "employee") if user else ""


def is_logged_in() -> bool:
    return current_user() is not None


def is_hr() -> bool:
    return current_role() == "HR"


def is_manager() -> bool:
    return current_role() == "manager"


def is_employee() -> bool:
    return current_role() == "employee"


def can_view_all() -> bool:
    """HR 和经理可以查看全员数据。"""
    return is_hr() or is_manager()


def init_db_if_needed() -> None:
    """首次启动时自动初始化数据库 + 同步员工账号。"""
    from core.database import HealthDatabase
    from core.user_database import UserDatabase

    health_path = PROJECT_ROOT / "data" / "health.db"
    if not health_path.exists():
        db = HealthDatabase(str(health_path))
        db.close()

    # 同步员工账号
    db = HealthDatabase(str(health_path))
    try:
        employees = db.get_all_employees()
        if employees:
            user_db = UserDatabase(str(PROJECT_ROOT / "data" / "users.db"))
            try:
                user_db.sync_employees(employees)
            finally:
                user_db.close()
    finally:
        db.close()


def logout() -> None:
    """退出登录，清理会话状态。"""
    # 关闭 DB 连接
    for key in ("db", "user_db", "llm_agent"):
        obj = st.session_state.get(key)
        if obj and hasattr(obj, "close"):
            try:
                obj.close()
            except Exception:
                pass
        st.session_state[key] = None
    st.session_state["user"] = None
    st.session_state["page"] = "login"
    st.session_state["selected_employee_id"] = None
