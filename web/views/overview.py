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

    # 关键趋势图：展示异常最多的指标全员对比
    if all_abnormal_items:
        _render_overview_trend_chart(db, employees, all_abnormal_items)


def _render_overview_trend_chart(db, employees: list, all_abnormal_items: dict) -> None:
    """全员概览页底部：最关键指标的趋势对比图。"""
    from web.components import render_trend_chart

    # 按异常次数排序，取最多的几个指标
    top_indicators = sorted(
        all_abnormal_items.items(), key=lambda x: x[1]["count"], reverse=True
    )
    indicator_names = [name for name, _ in top_indicators[:10]]

    section_header("关键指标趋势", "选择指标查看全员历年变化")

    selected_ind = st.selectbox("选择指标", indicator_names, key="overview_trend_ind")
    if not selected_ind:
        return

    # 收集所有有该指标历史数据的员工
    emp_options = []
    emp_data_map = {}
    for emp in employees:
        history = db.get_history(emp["id"])
        ind_values = []
        abnormal_flags = []
        dates = []
        ref_range = ""
        unit = ""
        for record in history:
            indicators = record["report_data"].get("indicators", {})
            info = indicators.get(selected_ind)
            if info and info.get("value") is not None:
                dates.append(record["report_date"])
                ind_values.append(info.get("value"))
                abnormal_flags.append(info.get("status") == "abnormal")
                if not ref_range:
                    ref_range = info.get("ref_range", "")
                if not unit:
                    unit = info.get("unit", "")
        if ind_values:
            label = f"{emp['name']} ({emp['gender']})"
            emp_options.append(label)
            emp_data_map[label] = {
                "dates": dates,
                "values": ind_values,
                "abnormal_flags": abnormal_flags,
                "ref_range": ref_range,
                "unit": unit,
            }

    if not emp_options:
        st.info(f"无 {selected_ind} 的历史数据")
        return

    # 默认展示所有员工（最多 5 个）
    default_sel = emp_options[:min(5, len(emp_options))]
    selected_emps = st.multiselect(
        "选择员工（最多 5 名）",
        emp_options,
        default=default_sel,
        key="overview_trend_emp",
        max_selections=5,
    )

    if not selected_emps:
        return

    # 多员工折线图
    import plotly.graph_objects as go

    fig = go.Figure()
    colors = ["#0891b2", "#f59e0b", "#6366f1", "#10b981", "#ef4444"]

    # 参考范围色带（取第一个员工的）
    first_data = emp_data_map[selected_emps[0]]
    from web.components import _parse_ref_range
    lo, hi = _parse_ref_range(first_data["ref_range"])
    if lo is not None and hi is not None:
        fig.add_hrect(
            y0=lo, y1=hi,
            fillcolor="rgba(16, 185, 129, 0.10)",
            layer="below", line_width=0,
            annotation_text=f"正常范围 {lo}-{hi}",
            annotation_position="top left",
            annotation_font_size=10,
            annotation_font_color="#10b981",
        )
    if lo is not None:
        fig.add_hline(y=lo, line_dash="dash", line_color="#10b981", line_width=1, opacity=0.5)
    if hi is not None:
        fig.add_hline(y=hi, line_dash="dash", line_color="#10b981", line_width=1, opacity=0.5)

    for idx, label in enumerate(selected_emps):
        d = emp_data_map[label]
        color = colors[idx % len(colors)]

        # 正常点连线
        normal_x = [d["dates"][i] for i in range(len(d["dates"])) if not d["abnormal_flags"][i]]
        normal_y = [d["values"][i] for i in range(len(d["dates"])) if not d["abnormal_flags"][i]]
        if normal_x:
            fig.add_trace(go.Scatter(
                x=normal_x, y=normal_y,
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=7, color=color),
                hovertemplate=f"<b>{label}</b><br>日期: %{{x}}<br>数值: %{{y}} {d['unit']}<br><extra></extra>",
                connectgaps=True,
            ))

        # 异常点
        abnormal_x = [d["dates"][i] for i in range(len(d["dates"])) if d["abnormal_flags"][i]]
        abnormal_y = [d["values"][i] for i in range(len(d["dates"])) if d["abnormal_flags"][i]]
        if abnormal_x:
            fig.add_trace(go.Scatter(
                x=abnormal_x, y=abnormal_y,
                mode="markers",
                name=f"{label} ⚠️",
                marker=dict(size=10, color="#ef4444", symbol="circle",
                           line=dict(width=2, color="white")),
                hovertemplate=f"<b>{label} ⚠️ 异常</b><br>日期: %{{x}}<br>数值: %{{y}} {d['unit']}<br>参考范围: {d['ref_range']}<br><extra></extra>",
            ))

    unit_str = f" ({first_data['unit']})" if first_data['unit'] else ""
    fig.update_layout(
        title=dict(text=f"{selected_ind}{unit_str}", font=dict(size=14, color="#64748b")),
        xaxis=dict(tickfont=dict(size=11, color="#94a3b8"), gridcolor="#e2e8f0", showgrid=True),
        yaxis=dict(tickfont=dict(size=11, color="#94a3b8"), gridcolor="#e2e8f0", showgrid=True),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, sans-serif", color="#64748b"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=40, r=20, t=50, b=20),
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_trend_tab() -> None:
    db = get_db()
    employees = db.get_all_employees()

    if not employees:
        st.info("数据库为空。")
        return

    # 收集所有有趋势数据的员工
    emp_trends: dict[str, list] = {}  # 员工名 -> 趋势行
    trend_table_rows = []

    for emp in employees:
        history = db.get_history(emp["id"])
        if len(history) < 2:
            continue
        latest_indicators = history[-1]["report_data"].get("indicators", {})
        for ind_name in latest_indicators:
            trend = db.check_trend_warning(emp["id"], ind_name)
            if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                vals_str = " → ".join(str(v) for v in trend["values"])
                trend_table_rows.append({
                    "员工": emp["name"],
                    "指标": ind_name,
                    "数值变化": vals_str,
                    "趋势": trend["trend"],
                    "预警": "⚠️ " + trend["message"] if trend["warning"] else "",
                })
                emp_trends.setdefault(emp["name"], []).append((ind_name, history, trend))

    if not trend_table_rows:
        st.info("无趋势数据（需要至少 2 份报告）。")
        return

    # 折线图视图
    section_header("趋势可视化", "选择员工查看指标变化曲线")

    emp_names = sorted(emp_trends.keys())
    selected_emp = st.selectbox("选择员工", emp_names, key="trend_emp_select")

    if selected_emp:
        history = db.get_history(
            next(e["id"] for e in employees if e["name"] == selected_emp)
        )
        dates = [r["report_date"] for r in history]

        # 收集该员工所有有趋势的指标
        ind_data: dict[str, dict] = {}
        for ind_name, _, trend in emp_trends[selected_emp]:
            # 从历史报告中提取该指标每次的值和状态
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

            # 过滤掉 None 值的日期（该次报告无此指标）
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

        if ind_data:
            # 选择单个指标查看详细图
            ind_names = list(ind_data.keys())
            selected_ind = st.selectbox("选择指标", ind_names, key="trend_ind_select")

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
                # 统一日期轴：取所有指标的并集
                all_dates = sorted(set(d for d in dates))
                # 为每个指标构建对齐的数据（缺失值用 None）
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

    # 表格视图（放下方）
    section_header("趋势汇总表", f"{len(trend_table_rows)} 条趋势记录")
    st.dataframe(pd.DataFrame(trend_table_rows), use_container_width=True, hide_index=True)


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
