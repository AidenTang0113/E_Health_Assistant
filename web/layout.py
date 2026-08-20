"""主布局：侧边栏导航 + 内容区。"""

from __future__ import annotations

import streamlit as st

from web.state import (
    current_user,
    current_role,
    is_hr,
    is_manager,
    is_employee,
    can_view_all,
    logout,
    get_db,
    get_user_db,
)
from web.config_manager import get_status_text


def _render_sidebar() -> str:
    """侧边栏：用户信息 + 系统状态 + 页面导航 + 退出按钮。返回选中的页面标识。"""
    user = current_user()
    role = current_role()

    with st.sidebar:
        # 用户信息
        st.markdown(f"""
        👤 **{user['employee_name']}**
        \n🏷️ {role} | @{user['username']}
        """)

        st.divider()

        # LLM 状态
        try:
            st.caption(f"🤖 {get_status_text()}")
        except Exception:
            st.caption("🤖 LLM 状态未知")

        # 数据库状态
        try:
            db = get_db()
            employees = db.get_all_employees()
            if employees:
                total_reports = sum(len(db.get_history(e["id"])) for e in employees)
                st.caption(f"📊 {len(employees)} 名员工, {total_reports} 份报告")
            else:
                st.caption("📊 数据库为空")
        except Exception:
            st.caption("📊 数据库未初始化")

        st.divider()

        # 页面导航
        if is_employee():
            nav = st.radio(
                "功能导航",
                ["📋 我的健康", "⚙️ 账号设置"],
                label_visibility="collapsed",
            )
            page_map = {
                "📋 我的健康": "personal",
                "⚙️ 账号设置": "account",
            }
        else:
            nav_options = [
                "📊 总体查看",
                "👥 个人查看",
                "📁 报告管理",
                "⚙️ 账号设置",
            ]
            if is_hr():
                nav_options.append("🔧 系统设置")

            nav = st.radio(
                "功能导航",
                nav_options,
                label_visibility="collapsed",
            )
            page_map = {
                "📊 总体查看": "overview",
                "👥 个人查看": "personal",
                "📁 报告管理": "reports",
                "⚙️ 账号设置": "account",
                "🔧 系统设置": "settings",
            }

        st.divider()

        # 退出登录
        if st.button("🚪 退出登录", use_container_width=True):
            logout()
            st.rerun()

    return page_map.get(nav, "home")


def render_layout() -> None:
    """主布局入口：侧边栏导航 + 内容区渲染。"""
    page = _render_sidebar()

    if page == "overview":
        from web.views.overview import render_overview
        render_overview()
    elif page == "personal":
        from web.views.personal import render_personal
        render_personal()
    elif page == "reports":
        from web.views.reports import render_reports
        render_reports()
    elif page == "account":
        from web.views.account import render_account
        render_account()
    elif page == "settings":
        from web.views.settings import render_settings
        render_settings()
    elif page == "home":
        if can_view_all():
            from web.views.overview import render_overview
            render_overview()
        else:
            from web.views.personal import render_personal
            render_personal()
