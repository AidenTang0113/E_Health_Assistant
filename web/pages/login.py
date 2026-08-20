"""登录页面。"""

from __future__ import annotations

import streamlit as st

from web.state import init_session_state, get_user_db, init_db_if_needed


def render_login() -> None:
    """渲染登录界面。"""
    init_session_state()
    init_db_if_needed()

    st.markdown(
        """
        <style>
        .login-header {
            text-align: center;
            padding: 2rem 0 1rem;
        }
        .login-header h1 {
            font-size: 2rem;
            margin-bottom: 0.3rem;
        }
        .login-header p {
            color: #888;
            font-size: 0.9rem;
        }
        </style>
        <div class="login-header">
            <h1>🏥 E-Health Agent</h1>
            <p>AI 体检报告智能解读系统</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_center, col_right = st.columns([1, 1.5, 1])
    with col_center:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")

            if submitted:
                if not username or not password:
                    st.error("请输入用户名和密码")
                else:
                    user_db = get_user_db()
                    user = user_db.authenticate(username.strip(), password)
                    if user:
                        st.session_state["user"] = user
                        st.session_state["page"] = "home"
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")

    st.markdown(
        "<p style='text-align:center; color:#aaa; margin-top:2rem;'>"
        "首次启动默认管理员: admin / 123456"
        "</p>",
        unsafe_allow_html=True,
    )
