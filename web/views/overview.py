"""总体查看：全员概览 + 全员趋势 + 异常指标解读。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from web.state import get_db, get_llm_agent, is_hr, is_manager
from web.components import breadcrumb, section_header


def render_overview() -> None:
    """总体查看页面，含三个 tab。"""
    breadcrumb("首页", "总体查看")
    st.title("📊 总体查看")

    tab1, tab2, tab3 = st.tabs(["全员概览", "全员趋势", "异常指标解读"])

    with tab1:
        _render_overview_tab()
    with tab2:
        _render_trend_tab()
    with tab3:
        _render_interpret_tab()


def _render_overview_tab() -> None:
    db = get_db()
    employees = db.get_all_employees()

    if not employees:
        st.info("数据库为空，请先导入报告数据。")
        return

    # 统计汇总
    total_reports = 0
    total_abnormal = 0
    all_abnormal_items: dict[str, dict] = {}

    emp_stats = []
    for emp in employees:
        history = db.get_history(emp["id"])
        total_reports += len(history)
        latest_date = history[-1]["report_date"] if history else "-"
        latest_abnormal = 0

        for record in history:
            indicators = record["report_data"].get("indicators", {})
            for name, info in indicators.items():
                if info.get("status") == "abnormal":
                    total_abnormal += 1
                    if name not in all_abnormal_items:
                        all_abnormal_items[name] = {"count": 0, "employees": set()}
                    all_abnormal_items[name]["count"] += 1
                    all_abnormal_items[name]["employees"].add(emp["name"])
                    if record is history[-1]:
                        latest_abnormal += 1

        emp_stats.append({
            "ID": emp["id"],
            "姓名": emp["name"],
            "性别": emp["gender"],
            "报告数": len(history),
            "最新体检": latest_date,
            "最新异常": latest_abnormal,
        })

    # 汇总卡片
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("员工数", len(employees))
    col2.metric("报告总数", total_reports)
    col3.metric("异常记录", total_abnormal)
    col4.metric("异常指标类型", len(all_abnormal_items))

    # 员工列表
    section_header("员工列表", f"共 {len(employees)} 名")
    st.dataframe(pd.DataFrame(emp_stats), use_container_width=True, hide_index=True)

    # 健康摘要
    section_header("健康摘要", "按员工展开查看最新报告详情")
    for emp in employees:
        history = db.get_history(emp["id"])
        if not history:
            continue
        latest = history[-1]
        indicators = latest["report_data"].get("indicators", {})
        abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}

        icon = "✅" if not abnormal else "⚠️"
        with st.expander(
            f"{icon} {emp['name']} ({emp['gender']}) — {latest['report_date']} | "
            f"{len(indicators)} 项指标, {len(abnormal)} 项异常, {len(history)} 份历史报告",
            expanded=False,
        ):
            if abnormal:
                abnormal_rows = []
                for name, info in abnormal.items():
                    val = info.get("value", "?")
                    unit = info.get("unit", "")
                    atype = info.get("abnormal_type", "?")
                    ref = info.get("ref_range", "?")
                    trend = db.check_trend_warning(emp["id"], name)
                    trend_str = ""
                    if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                        vals_str = " → ".join(str(v) for v in trend["values"])
                        trend_str = f"{trend['trend']} ({vals_str})"
                        if trend["warning"]:
                            trend_str += f" ⚠️ {trend['message']}"

                    abnormal_rows.append({
                        "指标": name,
                        "值": f"{val} {unit}",
                        "异常类型": atype,
                        "参考范围": ref,
                        "趋势": trend_str,
                    })
                st.dataframe(pd.DataFrame(abnormal_rows), use_container_width=True, hide_index=True)
            else:
                st.success("所有指标正常")

    # 异常指标排行
    if all_abnormal_items:
        section_header("异常指标排行", "按出现次数降序")
        rank_rows = []
        for name, data in sorted(all_abnormal_items.items(), key=lambda x: x[1]["count"], reverse=True):
            rank_rows.append({
                "指标": name,
                "出现次数": data["count"],
                "涉及员工": ", ".join(sorted(data["employees"])),
            })
        st.dataframe(pd.DataFrame(rank_rows), use_container_width=True, hide_index=True)


def _render_trend_tab() -> None:
    db = get_db()
    employees = db.get_all_employees()

    if not employees:
        st.info("数据库为空。")
        return

    found = False
    trend_data = []

    for emp in employees:
        history = db.get_history(emp["id"])
        if len(history) < 2:
            continue
        latest_indicators = history[-1]["report_data"].get("indicators", {})
        for ind_name in latest_indicators:
            trend = db.check_trend_warning(emp["id"], ind_name)
            if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                found = True
                vals_str = " → ".join(str(v) for v in trend["values"])
                trend_data.append({
                    "员工": emp["name"],
                    "指标": ind_name,
                    "数值变化": vals_str,
                    "趋势": trend["trend"],
                    "预警": "⚠️ " + trend["message"] if trend["warning"] else "",
                })

    if not found:
        st.info("无趋势数据（需要至少 2 份报告）。")
        return

    st.dataframe(pd.DataFrame(trend_data), use_container_width=True, hide_index=True)


def _render_interpret_tab() -> None:
    db = get_db()
    employees = db.get_all_employees()

    if not employees:
        st.info("数据库为空。")
        return

    # 汇总所有异常指标
    all_abnormal: dict[str, list] = {}
    for emp in employees:
        history = db.get_history(emp["id"])
        if not history:
            continue
        latest = history[-1]
        indicators = latest["report_data"].get("indicators", {})
        for name, info in indicators.items():
            if info.get("status") == "abnormal":
                if name not in all_abnormal:
                    all_abnormal[name] = []
                all_abnormal[name].append((emp["name"], info, latest["report_date"]))

    if not all_abnormal:
        st.success("🎉 所有指标均正常，无需解读。")
        return

    # 选择指标
    ind_names = list(all_abnormal.keys())
    selected = st.selectbox("选择异常指标进行解读", ind_names)

    if not selected:
        return

    # 解读模式
    detailed = st.checkbox("详细解读模式", value=False)

    records = all_abnormal[selected]

    if st.button("🔮 开始解读", type="primary"):
        agent = get_llm_agent()
        progress = st.progress(0, desc="正在解读...")

        for i, (emp_name, info, report_date) in enumerate(records):
            progress.progress((i) / len(records), desc=f"解读 {emp_name}...")
            with st.container():
                st.markdown("---")
                section_header(f"{emp_name} ({report_date})")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("指标值", f"{info.get('value')} {info.get('unit', '')}")
                col_b.metric("参考范围", info.get("ref_range", "未知"))
                col_c.metric("异常类型", info.get("abnormal_type", "?"))

                advice = agent.get_advice(
                    selected,
                    info.get("value", 0),
                    info.get("ref_range", ""),
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

            progress.progress((i + 1) / len(records), desc=f"已完成 {i + 1}/{len(records)}")

        progress.empty()
        st.success("解读完成！")
