"""系统设置：LLM 配置 + 数据库管理 + 操作日志（仅 HR）。"""

from __future__ import annotations

import streamlit as st

from web.state import get_db, get_user_db, current_user, is_hr, PROJECT_ROOT
from web.config_manager import load_config, save_config, get_status_text


def render_settings() -> None:
    """系统设置页面（仅 HR）。"""
    st.title("🔧 系统设置")

    if not is_hr():
        st.warning("仅 HR 管理员可访问系统设置。")
        return

    tab1, tab2, tab3 = st.tabs(["🤖 LLM 配置", "🗑️ 数据库管理", "📋 操作日志"])

    with tab1:
        _render_llm_config()
    with tab2:
        _render_db_management()
    with tab3:
        _render_audit_logs()


def _render_llm_config() -> None:
    config = load_config()

    st.markdown(f"**当前状态**: {get_status_text()}")

    st.markdown("---")

    with st.form("llm_config"):
        mode = st.radio(
            "LLM 模式",
            ["api", "local"],
            index=0 if config["mode"] == "api" else 1,
            format_func=lambda x: "第三方 API" if x == "api" else "本地模型 (LM Studio)",
            horizontal=True,
        )

        if mode == "api":
            api_key = st.text_input(
                "API Key",
                value=config["api_key"],
                type="password",
                help="将加密存储（Windows DPAPI）",
            )
            base_url = st.text_input(
                "API Base URL",
                value=config["base_url"],
                placeholder="https://api.openai.com/v1",
            )
            api_model = st.text_input(
                "模型名称",
                value=config["api_model"],
                placeholder="gpt-4o-mini",
            )
        else:
            local_url = st.text_input(
                "本地模型地址",
                value=config.get("local_url", "http://localhost:1234/v1"),
            )
            local_model = st.text_input(
                "本地模型名称",
                value=config.get("local_model", ""),
                placeholder="qwen2.5-7b-instruct",
            )

        submitted = st.form_submit_button("💾 保存配置", type="primary")

        if submitted:
            new_config = dict(config)
            new_config["mode"] = mode
            if mode == "api":
                new_config["api_key"] = api_key
                new_config["base_url"] = base_url
                new_config["api_model"] = api_model
            else:
                new_config["local_url"] = local_url
                new_config["local_model"] = local_model

            if save_config(new_config):
                st.success("配置已保存")
                # 重置 LLM Agent 单例，下次使用时重新初始化
                from web.state import get_llm_agent
                agent = st.session_state.get("llm_agent")
                if agent:
                    try:
                        agent.close()
                    except Exception:
                        pass
                st.session_state["llm_agent"] = None
            else:
                st.error("保存失败")

    # 测试连接
    st.markdown("---")
    if st.button("🔌 测试连接"):
        _test_connection()


def _test_connection() -> None:
    from web.state import get_llm_agent

    # 强制重新初始化
    agent = st.session_state.get("llm_agent")
    if agent:
        try:
            agent.close()
        except Exception:
            pass
    st.session_state["llm_agent"] = None

    with st.spinner("正在测试连接..."):
        agent = get_llm_agent()
        advice = agent.get_advice("空腹血糖", 6.5, "3.9-6.1")

    source = advice.get("source", "?")

    if source == "llm":
        st.success(f"✅ 连接成功 (LLM)")
        st.markdown(f"**概述**: {advice.get('summary', '')}")
    elif source == "mock":
        st.info("📦 Mock 模式正常")
        st.markdown(f"**概述**: {advice.get('summary', '')}")
    elif source == "mock_fallback":
        st.warning("⚠️ 连接失败，已回退到 Mock 模式")
        if advice.get("error"):
            st.error(f"错误: {advice['error']}")
        st.markdown(f"**Mock 结果**: {advice.get('summary', '')}")
    else:
        st.error(f"未知状态: {source}")


def _render_db_management() -> None:
    st.markdown("### 数据库管理")

    db = get_db()
    employees = db.get_all_employees()
    total_reports = sum(len(db.get_history(e["id"])) for e in employees)

    col1, col2 = st.columns(2)
    col1.metric("员工数", len(employees))
    col2.metric("报告数", total_reports)

    st.markdown("---")

    st.markdown("#### 🗑️ 清空数据库")
    st.warning("⚠️ 此操作将删除所有员工和报告数据，不可恢复！")

    with st.form("reset_db"):
        confirm_password = st.text_input("请输入 HR 密码确认", type="password")
        confirm_text = st.text_input('请输入 "YES" 确认清空')
        if st.form_submit_button("🔴 清空数据库", type="primary"):
            if not confirm_password:
                st.error("请输入密码")
                return
            if confirm_text != "YES":
                st.error('请输入 "YES" 确认')
                return

            # 验证密码
            user_db = get_user_db()
            user = current_user()
            auth = user_db.authenticate(user["username"], confirm_password)
            if not auth:
                st.error("密码错误")
                return

            # 执行清空
            try:
                db.reset_database()
                st.success("数据库已清空")
                # 刷新员工列表
                st.rerun()
            except Exception as e:
                st.error(f"清空失败: {e}")


def _render_audit_logs() -> None:
    st.markdown("### 操作日志")

    user_db = get_user_db()
    logs = user_db.list_audit_logs(limit=50)

    if not logs:
        st.info("暂无操作日志")
        return

    import pandas as pd
    rows = []
    for log in logs:
        rows.append({
            "ID": log["id"],
            "操作": log["action"],
            "目标": log["target"],
            "操作者": log["operator"],
            "详情": log.get("detail") or "",
            "时间": log["created_at"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
