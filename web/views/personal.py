"""个人查看：档案 + 趋势 + 指标解读 + 账号设置入口。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from web.state import (
    get_db,
    get_llm_agent,
    current_user,
    is_employee,
    can_view_all,
)
from web.components import breadcrumb, section_header


def render_personal() -> None:
    """个人查看页面。"""
    breadcrumb("首页", "个人查看")
    st.title("👥 个人查看")

    db = get_db()

    # 确定查看的员工
    if is_employee():
        employee_id = current_user().get("employee_id")
        if not employee_id:
            st.warning("当前账号未关联员工档案")
            return
        employee = db.get_employee(employee_id)
        if not employee:
            st.warning("未找到员工档案")
            return
    else:
        # HR/经理选择员工
        employees = db.get_all_employees()
        if not employees:
            st.info("数据库为空，请先导入报告。")
            return

        emp_options = {f"{e['name']} ({e['gender']}, ID:{e['id']})": e["id"] for e in employees}
        selected_label = st.selectbox("选择员工", list(emp_options.keys()))
        employee_id = emp_options[selected_label]
        employee = db.get_employee(employee_id)
        if not employee:
            st.warning("未找到员工档案")
            return

    emp_id = employee["id"]
    emp_name = employee["name"]
    history = db.get_history(emp_id)

    # 员工信息卡片
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("姓名", emp_name)
    col2.metric("性别", employee["gender"])
    col3.metric("报告数", len(history))
    col4.metric("最新体检", history[-1]["report_date"] if history else "无")

    if employee.get("birth_year"):
        st.caption(f"出生年份: {employee['birth_year']}")

    if not history:
        st.info("该员工暂无体检报告。")
        return

    # 三个 tab
    tab1, tab2, tab3 = st.tabs(["📋 个人档案", "📈 个人趋势", "🔮 指标解读"])

    with tab1:
        _render_profile_tab(db, emp_id, history)
    with tab2:
        _render_trend_tab(db, emp_id, emp_name, history)
    with tab3:
        _render_interpret_tab(db, emp_id, emp_name, history)


def _render_profile_tab(db, emp_id: int, history: list) -> None:
    """个人档案：历史报告列表 + 最新指标详情。"""
    section_header("报告历史", f"{len(history)} 份")

    for i, record in enumerate(history, 1):
        indicators = record["report_data"].get("indicators", {})
        abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}
        icon = "⚠️" if abnormal else "✅"
        is_latest = (i == len(history))

        with st.expander(
            f"[{i}] {record['report_date']}  {icon}  "
            f"{len(indicators)} 项指标, {len(abnormal)} 项异常"
            + (" — 最新" if is_latest else ""),
            expanded=is_latest,
        ):
            if is_latest:
                # 最新报告展示完整指标
                rows = []
                for name, info in indicators.items():
                    val = info.get("value", "?")
                    unit = info.get("unit", "")
                    status = info.get("status", "?")
                    ref = info.get("ref_range", "")
                    tag = "⚠️" if status == "abnormal" else "✅"

                    trend = db.check_trend_warning(emp_id, name)
                    trend_str = ""
                    if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                        vals_str = " → ".join(str(v) for v in trend["values"])
                        trend_str = f"{trend['trend']} ({vals_str})"
                        if trend["warning"]:
                            trend_str += f" ⚠️"

                    rows.append({
                        "": tag,
                        "指标": name,
                        "值": f"{val} {unit}",
                        "参考范围": ref,
                        "状态": status,
                        "趋势": trend_str,
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                # 历史报告只展示异常项
                if abnormal:
                    rows = []
                    for name, info in abnormal.items():
                        val = info.get("value", "?")
                        unit = info.get("unit", "")
                        rows.append({
                            "指标": name,
                            "值": f"{val} {unit}",
                            "异常类型": info.get("abnormal_type", "?"),
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.success("所有指标正常")


def _render_trend_tab(db, emp_id: int, emp_name: str, history: list) -> None:
    """个人趋势：各项指标历史变化 + 折线图可视化。"""
    if len(history) < 2:
        st.info("历史报告不足 2 份，无法分析趋势。")
        return

    dates = [r["report_date"] for r in history]
    latest_indicators = history[-1]["report_data"].get("indicators", {})

    # 收集所有指标的时序数据
    ind_data: dict[str, dict] = {}
    trend_table_rows = []

    for ind_name in latest_indicators:
        trend = db.check_trend_warning(emp_id, ind_name)
        if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
            vals_str = " → ".join(str(v) for v in trend["values"])
            trend_table_rows.append({
                "指标": ind_name,
                "数值变化": vals_str,
                "趋势": trend["trend"],
                "预警": "⚠️ " + trend["message"] if trend["warning"] else "",
            })

            # 提取每次报告该指标的值和状态
            ind_values = []
            abnormal_flags = []
            ref_range = ""
            unit = ""
            for record in history:
                indicators = record["report_data"].get("indicators", {})
                info = indicators.get(ind_name)
                if info:
                    ind_values.append(info.get("value"))
                    abnormal_flags.append(info.get("status") == "abnormal")
                    if not ref_range:
                        ref_range = info.get("ref_range", "")
                    if not unit:
                        unit = info.get("unit", "")
                else:
                    ind_values.append(None)
                    abnormal_flags.append(False)

            # 过滤缺失值
            valid_pairs = [
                (d, v, f) for d, v, f in zip(dates, ind_values, abnormal_flags)
                if v is not None
            ]
            if valid_pairs:
                ind_data[ind_name] = {
                    "values": [v for _, v, _ in valid_pairs],
                    "dates": [d for d, _, _ in valid_pairs],
                    "ref_range": ref_range,
                    "unit": unit,
                    "abnormal_flags": [f for _, _, f in valid_pairs],
                }

    if not ind_data:
        st.info("无趋势数据。")
        return

    # 趋势汇总表
    section_header("趋势汇总", f"{len(trend_table_rows)} 项指标有趋势数据")
    st.dataframe(pd.DataFrame(trend_table_rows), use_container_width=True, hide_index=True)

    # 单指标详细折线图
    section_header("趋势可视化", "选择指标查看变化曲线")
    ind_names = list(ind_data.keys())
    selected_ind = st.selectbox("选择指标", ind_names, key="personal_trend_ind")

    if selected_ind:
        d = ind_data[selected_ind]
        from web.components import render_trend_chart
        render_trend_chart(
            indicator_name=selected_ind,
            dates=d["dates"],
            values=d["values"],
            ref_range=d["ref_range"],
            unit=d["unit"],
            abnormal_flags=d["abnormal_flags"],
            height=400,
        )

    # 多指标小倍数图
    if len(ind_data) > 1:
        section_header("全部指标对比", "小倍数图并排展示")
        from web.components import render_multi_trend
        all_dates = sorted(set(dates))
        multi_data: dict[str, dict] = {}
        for name, d in ind_data.items():
            date_value_map = dict(zip(d["dates"], d["values"]))
            date_flag_map = dict(zip(d["dates"], d["abnormal_flags"]))
            multi_data[name] = {
                "values": [date_value_map.get(dt) for dt in all_dates],
                "ref_range": d["ref_range"],
                "unit": d["unit"],
                "abnormal_flags": [date_flag_map.get(dt, False) for dt in all_dates],
            }
        render_multi_trend(multi_data, all_dates, height=260)


def _render_interpret_tab(db, emp_id: int, emp_name: str, history: list) -> None:
    """个人指标解读。"""
    latest = history[-1]
    indicators = latest["report_data"].get("indicators", {})

    if not indicators:
        st.info("最新报告无指标数据。")
        return

    detailed = st.checkbox("详细解读模式", value=False, key="personal_detailed")

    # 列出所有指标
    ind_names = list(indicators.keys())
    display_names = []
    for name in ind_names:
        info = indicators[name]
        val = info.get("value", "?")
        unit = info.get("unit", "")
        status = info.get("status", "?")
        tag = "⚠️" if status == "abnormal" else "✅"
        display_names.append(f"{tag} {name}: {val} {unit}")

    selected = st.selectbox("选择要解读的指标", display_names)
    if not selected:
        return

    idx = display_names.index(selected)
    ind_name = ind_names[idx]
    ind_info = indicators[ind_name]

    st.markdown(f"**指标**: {ind_name}")
    st.markdown(f"**值**: {ind_info.get('value')} {ind_info.get('unit', '')}")
    st.markdown(f"**参考范围**: {ind_info.get('ref_range', '未知')}")

    if st.button("🔮 解读", type="primary", key="personal_interpret"):
        with st.spinner("正在解读..."):
            agent = get_llm_agent()
            advice = agent.get_advice(
                ind_name,
                ind_info.get("value", 0),
                ind_info.get("ref_range", ""),
                detailed=detailed,
            )

        source = advice.get("source", "?")
        source_icon = {"llm": "🤖", "mock": "📦", "mock_fallback": "⚠️"}.get(source, "❓")

        st.markdown(f"**来源**: {source_icon} {source}")
        st.markdown(f"**概述**: {advice.get('summary', '?')}")
        st.markdown(f"**风险等级**: {advice.get('risk_level', '?')}")

        if detailed:
            interp = advice.get("interpretation", "")
            if interp:
                st.markdown(f"**解读**: {interp}")
            causes = advice.get("possible_causes", [])
            if causes:
                st.markdown("**可能原因:**")
                for c in causes:
                    st.markdown(f"- {c}")

        st.markdown("**建议:**")
        for item in advice.get("advice", []):
            st.markdown(f"- {item}")

        if detailed:
            lifestyle = advice.get("lifestyle", [])
            if lifestyle:
                st.markdown("**生活方式建议:**")
                for item in lifestyle:
                    st.markdown(f"- {item}")
            follow = advice.get("follow_up", "")
            if follow:
                st.markdown(f"**复查建议**: {follow}")
            urgency = advice.get("urgency", "")
            if urgency:
                st.markdown(f"**就医建议**: {urgency}")

        st.caption(f"📚 {advice.get('knowledge_ref', '无')}")
