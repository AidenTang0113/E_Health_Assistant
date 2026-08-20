"""账号设置：修改用户名/密码/出生年。"""

from __future__ import annotations

import streamlit as st

from web.state import get_user_db, current_user, is_hr, can_view_all
from web.components import breadcrumb, section_header


def render_account() -> None:
    """账号设置页面。"""
    breadcrumb("首页", "账号设置")
    st.title("⚙️ 账号设置")

    user = current_user()
    user_db = get_user_db()

    # 个人资料修改
    section_header("个人资料")
    with st.form("profile_form"):
        current_username = user["username"]
        new_username = st.text_input("用户名", value=current_username)

        col1, col2 = st.columns(2)
        with col1:
            old_password = st.text_input("旧密码（修改密码时填写）", type="password")
        with col2:
            new_password = st.text_input("新密码（留空则不修改）", type="password")

        birth_year = st.number_input(
            "出生年份",
            min_value=1900,
            max_value=2025,
            value=user.get("birth_year") or 1990,
            step=1,
        )

        submitted = st.form_submit_button("保存", type="primary")

        if submitted:
            updates = []
            if new_username and new_username != current_username:
                updates.append("用户名")
            if new_password:
                if not old_password:
                    st.error("修改密码需提供旧密码")
                    return
                updates.append("密码")

            if not updates and birth_year == (user.get("birth_year") or 1990):
                st.info("未检测到更改")
                return

            ok, msg = user_db.update_user_profile(
                current_username,
                new_username=new_username if new_username != current_username else None,
                old_password=old_password if new_password else None,
                new_password=new_password if new_password else None,
                birth_year=birth_year,
            )

            if ok:
                st.success(msg)
                # 更新 session_state 中的用户名
                if new_username and new_username != current_username:
                    st.session_state["user"]["username"] = new_username
            else:
                st.error(msg)

    # HR/经理的账号管理
    if can_view_all():
        _render_account_management(user_db)


def _render_account_management(user_db) -> None:
    section_header("员工账号管理")

    users = user_db.list_users()

    import pandas as pd
    rows = []
    for u in users:
        rows.append({
            "ID": u["id"],
            "用户名": u["username"],
            "姓名": u["employee_name"],
            "性别": u["gender"],
            "角色": u["role"],
            "状态": "启用" if u["is_active"] else "停用",
            "最近登录": u.get("last_login_at") or "从未",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 操作
    section_header("账号操作")

    user_options = {f"{u['username']} ({u['employee_name']})": u for u in users}
    selected_label = st.selectbox("选择账号", list(user_options.keys()))
    target_user = user_options[selected_label]

    if target_user["username"] == "admin" or target_user["role"] == "HR":
        st.info("HR 管理员账号不可操作")
        return

    col1, col2 = st.columns(2)

    with col1:
        if target_user["is_active"]:
            if st.button("🚫 停用"):
                if user_db.deactivate_user(target_user["username"], operator=current_user()["username"]):
                    st.success("已停用")
                    st.rerun()
                else:
                    st.error("停用失败")
        else:
            if st.button("✅ 启用"):
                if user_db.reactivate_user(target_user["username"], operator=current_user()["username"]):
                    st.success("已启用")
                    st.rerun()
                else:
                    st.error("启用失败")

    with col2:
        if st.button("🔑 重置密码"):
            new_pw = user_db.reset_password(
                target_user["username"],
                operator=current_user()["username"],
            )
            if new_pw:
                st.success(f"已重置，新密码: {new_pw}")
            else:
                st.error("重置失败")

    # 经理管理（仅 HR）
    if is_hr():
        section_header("角色管理")

        if target_user["role"] == "employee":
            if st.button("⬆️ 提升为经理"):
                result = user_db.promote_employee_to_manager(target_user["employee_name"])
                if result:
                    st.success(f"已将 {target_user['employee_name']} 提升为经理")
                    st.rerun()
        elif target_user["role"] == "manager":
            if st.button("⬇️ 降为员工"):
                result = user_db.demote_manager_by_name(target_user["employee_name"])
                if result:
                    st.success(f"已将 {target_user['employee_name']} 降为员工")
                    st.rerun()

    # 创建经理账号（仅 HR）
    if is_hr():
        section_header("创建经理账号")
        with st.form("create_manager"):
            mgr_name = st.text_input("经理姓名")
            mgr_username = st.text_input("用户名")
            mgr_password = st.text_input("密码", type="password")
            if st.form_submit_button("创建", type="primary"):
                if not mgr_name or not mgr_username or not mgr_password:
                    st.error("请填写所有字段")
                else:
                    try:
                        user_db.create_manager_account(mgr_name, mgr_username, mgr_password)
                        st.success(f"经理账号 {mgr_username} 创建成功")
                    except ValueError as e:
                        st.error(str(e))
