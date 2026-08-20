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

    # ── 统计汇总 ──
    total_reports = 0
    total_abnormal = 0
    all_abnormal_items: dict[str, dict] = {}

    # 每员工最新报告的指标概况（用于柱状图 + 摘要）
    emp_latest: list[dict] = []  # [{name, gender, date, total, normal, abnormal, abnormal_names}]

    for emp in employees:
        history = db.get_history(emp["id"])
        total_reports += len(history)
        latest_date = history[-1]["report_date"] if history else "-"

        for record in history:
            indicators = record["report_data"].get("indicators", {})
            for name, info in indicators.items():
                if info.get("status") == "abnormal":
                    total_abnormal += 1
                    if name not in all_abnormal_items:
                        all_abnormal_items[name] = {"count": 0, "employees": set()}
                    all_abnormal_items[name]["count"] += 1
                    all_abnormal_items[name]["employees"].add(emp["name"])

        # 最新报告统计
        if history:
            latest = history[-1]
            indicators = latest["report_data"].get("indicators", {})
            abnormal_names = [n for n, v in indicators.items() if v.get("status") == "abnormal"]
            emp_latest.append({
                "name": emp["name"],
                "gender": emp["gender"],
                "date": latest_date,
                "total": len(indicators),
                "normal": len(indicators) - len(abnormal_names),
                "abnormal": len(abnormal_names),
                "abnormal_names": abnormal_names,
            })
        else:
            emp_latest.append({
                "name": emp["name"], "gender": emp["gender"], "date": "-",
                "total": 0, "normal": 0, "abnormal": 0, "abnormal_names": [],
            })

    # ── 最上方：最新体检异常概览图 ──
    _render_abnormal_overview_chart(emp_latest)

    # ── 汇总卡片 ──
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("员工数", len(employees))
    col2.metric("报告总数", total_reports)
    col3.metric("异常记录", total_abnormal)
    col4.metric("异常指标类型", len(all_abnormal_items))

    # ── 健康摘要 ──
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

    # ── 异常指标排行 ──
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


def _render_abnormal_overview_chart(emp_latest: list[dict]) -> None:
    """最新体检异常概览：分组柱状图，一目了然看到谁有异常、多少项。

    每个员工一组柱：正常项（绿）+ 异常项（红）堆叠，hover 显示异常指标名。
    """
    import plotly.graph_objects as go

    # 过滤掉无报告的员工
    has_data = [e for e in emp_latest if e["total"] > 0]
    if not has_data:
        return

    names = [f"{e['name']}\n{e['gender']}" for e in has_data]
    normal_vals = [e["normal"] for e in has_data]
    abnormal_vals = [e["abnormal"] for e in has_data]
    # hover 文本
    hover_normal = [
        f"{e['name']} ({e['gender']})<br>正常: {e['normal']} 项<br>异常: {e['abnormal']} 项<br>日期: {e['date']}<extra></extra>"
        for e in has_data
    ]
    hover_abnormal = [
        f"{e['name']} ({e['gender']})<br>⚠️ 异常指标: {', '.join(e['abnormal_names']) if e['abnormal_names'] else '无'}<br>日期: {e['date']}<extra></extra>"
        for e in has_data
    ]

    fig = go.Figure()

    # 正常 — 绿色底柱
    fig.add_trace(go.Bar(
        x=names, y=normal_vals,
        name="正常",
        marker_color="#10b981",
        hovertemplate=hover_normal,
        text=[str(v) for v in normal_vals],
        textposition="inside",
        textfont=dict(color="white", size=12),
    ))

    # 异常 — 红色顶柱（堆叠）
    fig.add_trace(go.Bar(
        x=names, y=abnormal_vals,
        name="异常",
        marker_color="#ef4444",
        hovertemplate=hover_abnormal,
        text=[str(v) if v > 0 else "" for v in abnormal_vals],
        textposition="inside",
        textfont=dict(color="white", size=12),
    ))

    fig.update_layout(
        title=dict(
            text="最新体检异常概览",
            font=dict(size=15, color="#0e7490"),
        ),
        barmode="stack",
        xaxis=dict(
            tickfont=dict(size=12, color="#64748b"),
            showgrid=False,
        ),
        yaxis=dict(
            title="指标项数",
            title_font=dict(size=11, color="#94a3b8"),
            tickfont=dict(size=11, color="#94a3b8"),
            gridcolor="#e2e8f0",
            showgrid=True,
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, sans-serif", color="#64748b"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=40, r=20, t=60, b=20),
        height=400,
        showlegend=True,
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
        progress_text = st.empty()
        progress = st.progress(0)

        for i, (emp_name, info, report_date) in enumerate(records):
            progress_text.text(f"解读 {emp_name}...")
            progress.progress((i) / len(records))
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

            progress_text.text(f"已完成 {i + 1}/{len(records)}")
            progress.progress((i + 1) / len(records))

        progress.empty()
        progress_text.empty()
        st.success("解读完成！")
