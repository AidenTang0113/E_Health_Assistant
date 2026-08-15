"""Streamlit web interface for the E-Health Agent project."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import inspect
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import HealthDatabase
from core.llm_agent import LLMAgent
from core.ocr_engine import OCREngine
from core.parser import ReportParser
from core.parser import REFERENCE_RANGES
from utils.mock_data import get_mock_ocr_text, init_mock_database


SUPPORTED_EXTENSIONS = ["jpg", "jpeg", "png", "bmp", "tiff", "tif", "pdf"]
DB_PATH = PROJECT_ROOT / "data" / "health.db"


st.set_page_config(
    page_title="E-Health Agent",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

        :root {
            --bg: #f7f8fb;
            --surface: #ffffff;
            --surface-soft: #eef1f6;
            --ink: #1f2937;
            --muted: #6b7280;
            --accent: #2563eb;
            --accent-soft: #dbeafe;
            --line: #d9dee8;
            --success: #2f855a;
            --warning: #b45309;
            --danger: #b91c1c;
        }

        html, body, [class*="css"] {
            font-family: "DM Sans", sans-serif;
            color: var(--ink);
            background: var(--bg);
        }

        h1, h2, h3 {
            font-family: "Space Grotesk", sans-serif;
            letter-spacing: -0.03em;
        }

        .block-container {
            padding-top: 2rem;
            max-width: 1500px;
        }

        [data-testid="stSidebar"] {
            background: #f4f6fa;
            border-right: 1px solid var(--line);
        }

        [data-testid="stSidebar"] * {
            color: var(--ink);
        }

        [data-testid="stSidebar"] div[data-testid="stRadio"] > label {
            display: none;
        }

        [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] {
            display: flex;
            flex-direction: column;
            gap: .45rem;
        }

        [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label {
            align-items: center;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 10px;
            color: var(--muted);
            cursor: pointer;
            display: flex;
            font-size: .88rem;
            font-weight: 600;
            justify-content: flex-start;
            min-width: 0;
            min-height: 2.45rem;
            padding: 0 .9rem;
            transition: background .18s ease, border-color .18s ease, color .18s ease;
            width: 100%;
        }

        [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
            background: var(--surface);
            color: var(--ink);
        }

        [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
            background: var(--accent-soft);
            border-color: #bfd6fd;
            box-shadow: inset 3px 0 0 var(--accent);
            color: var(--accent);
        }

        [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
            display: none;
        }

        .hero {
            background:
                radial-gradient(circle at 90% 10%, rgba(37, 99, 235, .16), transparent 26%),
                linear-gradient(120deg, #111827 0%, #1f2937 48%, #334155 100%);
            border-radius: 22px;
            padding: 2.1rem 2.3rem;
            color: white;
            margin-bottom: 1.5rem;
            box-shadow: 0 18px 36px rgba(31, 41, 55, .12);
        }

        .hero h1 {
            color: white;
            font-size: clamp(2rem, 4vw, 3.4rem);
            margin: 0;
        }

        .hero p {
            color: #dbe4f0;
            max-width: 700px;
            font-size: 1.05rem;
            margin-bottom: 0;
        }

        .eyebrow {
            color: #93c5fd;
            font-size: .75rem;
            font-weight: 700;
            letter-spacing: .13em;
            text-transform: uppercase;
        }

        .card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1.1rem 1.2rem;
            height: 100%;
            box-shadow: 0 10px 30px rgba(15, 23, 42, .05);
        }

        .card-label {
            color: var(--muted);
            font-size: .8rem;
            text-transform: uppercase;
            letter-spacing: .08em;
        }

        .card-value {
            color: var(--accent);
            font-family: "Space Grotesk", sans-serif;
            font-size: 2rem;
            font-weight: 700;
            margin-top: .25rem;
        }

        .status-pill {
            border-radius: 999px;
            display: inline-block;
            font-size: .76rem;
            font-weight: 700;
            padding: .22rem .62rem;
        }

        .status-normal { background: #e8f5ee; color: var(--success); }
        .status-abnormal { background: #fdecec; color: var(--danger); }
        .status-warning { background: #fff4dd; color: var(--warning); }
        .status-muted { background: var(--surface-soft); color: var(--muted); }

        div[data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 1rem;
            box-shadow: 0 10px 30px rgba(15, 23, 42, .05);
        }

        .section-note {
            color: var(--muted);
            margin-top: -.6rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_db() -> HealthDatabase:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return HealthDatabase(str(DB_PATH))


def close_db(db: HealthDatabase) -> None:
    db.close()


def current_llm_config() -> Dict[str, str]:
    return {
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "base_url": os.environ.get("LLM_BASE_URL", ""),
        "model": os.environ.get("LLM_MODEL", ""),
    }


def build_agent(force_mock: bool = False) -> LLMAgent:
    cfg = current_llm_config()
    return LLMAgent(
        mock_mode=force_mock,
        api_key=cfg["api_key"] or None,
        base_url=cfg["base_url"] or None,
        model_name=cfg["model"] or None,
    )


def parse_report_compat(
    parser: ReportParser,
    ocr_lines: List[str],
    agent: LLMAgent,
    use_llm_parse: bool,
) -> Dict[str, Any]:
    """Use newer LLM-assisted parsing when the checked-out branch provides it."""
    parse_with_llm = getattr(parser, "parse_with_llm", None)
    if use_llm_parse and not agent.mock_mode and callable(parse_with_llm):
        return parse_with_llm(ocr_lines, llm_agent=agent)
    return parser.parse(ocr_lines)


def get_advice_compat(
    agent: LLMAgent,
    indicator_name: str,
    value: Any,
    ref_range: str,
    detailed: bool,
) -> Dict[str, Any]:
    """Pass optional arguments only when supported by this branch's API."""
    parameters = inspect.signature(agent.get_advice).parameters
    kwargs = {"detailed": detailed} if "detailed" in parameters else {}
    return agent.get_advice(indicator_name, value, ref_range, **kwargs)


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def status_badge(status: str, label: Optional[str] = None) -> None:
    normalized = "abnormal" if status == "abnormal" else "normal"
    st.markdown(
        f'<span class="status-pill status-{normalized}">{label or status}</span>',
        unsafe_allow_html=True,
    )


def report_summary(db: HealthDatabase) -> Dict[str, Any]:
    employees = db.get_all_employees()
    total_reports = 0
    total_abnormal = 0
    abnormal_items: Dict[str, Dict[str, Any]] = {}

    for employee in employees:
        for record in db.get_history(employee["id"]):
            total_reports += 1
            indicators = record.get("report_data", {}).get("indicators", {})
            for name, info in indicators.items():
                if info.get("status") == "abnormal":
                    total_abnormal += 1
                    item = abnormal_items.setdefault(
                        name, {"count": 0, "employees": set()}
                    )
                    item["count"] += 1
                    item["employees"].add(employee["name"])

    return {
        "employees": employees,
        "total_reports": total_reports,
        "total_abnormal": total_abnormal,
        "abnormal_items": abnormal_items,
    }


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## E-Health Agent")
        st.caption("体检报告智能解读工作台")
        st.divider()
        page = st.radio(
            "工作区",
            [
                "总览",
                "员工档案",
                "报告导入",
                "趋势分析",
                "LLM 解读",
                "模拟数据",
                "设置",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        cfg = current_llm_config()
        if cfg["api_key"]:
            st.success("LLM API 已配置")
        else:
            st.info("当前使用 Mock / 本地自动探测")
        st.caption(f"数据库: {DB_PATH.name}")
        return page


def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">E-Health Intelligence</div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview() -> None:
    render_hero("健康档案，一眼看清", "从 OCR 识别到趋势预警，把分散的体检信息整理成可行动的健康线索。")
    db = get_db()
    try:
        summary = report_summary(db)
        employees = summary["employees"]
        if not employees:
            st.info("数据库还没有员工或体检报告。可以从“模拟数据”开始，或导入一份报告。")
            return

        latest_abnormal = 0
        for employee in employees:
            latest = db.get_latest_report(employee["id"])
            if latest:
                latest_abnormal += sum(
                    1
                    for info in latest["report_data"].get("indicators", {}).values()
                    if info.get("status") == "abnormal"
                )

        cols = st.columns(4)
        cols[0].metric("员工", len(employees))
        cols[1].metric("体检报告", summary["total_reports"])
        cols[2].metric("异常记录", summary["total_abnormal"])
        cols[3].metric("最新异常", latest_abnormal)

        st.subheader("员工健康快照")
        cards = st.columns(min(3, max(1, len(employees))))
        for index, employee in enumerate(employees):
            latest = db.get_latest_report(employee["id"])
            indicators = latest["report_data"].get("indicators", {}) if latest else {}
            abnormal = {
                name: info
                for name, info in indicators.items()
                if info.get("status") == "abnormal"
            }
            with cards[index % len(cards)]:
                state = "异常待关注" if abnormal else "指标正常"
                state_class = "abnormal" if abnormal else "normal"
                st.markdown(
                    f"""
                    <div class="card">
                      <div class="card-label">{employee['gender']} · ID {employee['id']}</div>
                      <h3>{employee['name']}</h3>
                      <span class="status-pill status-{state_class}">{state}</span>
                      <p class="section-note">
                        最新报告：{latest['report_date'] if latest else '暂无'} ·
                        {len(indicators)} 项指标
                      </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if abnormal:
                    for name, info in list(abnormal.items())[:3]:
                        st.caption(
                            f"⚠ {name}: {info.get('value', '?')} {info.get('unit', '')}"
                        )

        if summary["abnormal_items"]:
            st.subheader("异常指标排行")
            ranking = sorted(
                summary["abnormal_items"].items(),
                key=lambda item: item[1]["count"],
                reverse=True,
            )
            st.dataframe(
                [
                    {
                        "指标": name,
                        "异常次数": item["count"],
                        "涉及员工": ", ".join(sorted(item["employees"])),
                    }
                    for name, item in ranking
                ],
                use_container_width=True,
                hide_index=True,
            )
    finally:
        close_db(db)


def employee_selector(db: HealthDatabase, key: str) -> Optional[Dict[str, Any]]:
    employees = db.get_all_employees()
    if not employees:
        st.info("暂无员工数据。")
        return None
    labels = {
        f"{employee['name']} · {employee['gender']} · ID {employee['id']}": employee
        for employee in employees
    }
    selected = st.selectbox("选择员工", list(labels), key=key)
    return labels[selected]


def render_employee_page() -> None:
    render_hero("员工档案", "查看员工列表、最新报告、异常指标和完整体检历史。")
    db = get_db()
    try:
        employees = db.get_all_employees()
        if not employees:
            st.info("暂无员工数据。")
            return

        rows = []
        for employee in employees:
            history = db.get_history(employee["id"])
            latest = history[-1] if history else None
            abnormal = (
                sum(
                    1
                    for info in latest["report_data"].get("indicators", {}).values()
                    if info.get("status") == "abnormal"
                )
                if latest
                else 0
            )
            rows.append(
                {
                    "ID": employee["id"],
                    "姓名": employee["name"],
                    "性别": employee["gender"],
                    "出生年份": employee.get("birth_year") or "-",
                    "报告数": len(history),
                    "最新日期": latest["report_date"] if latest else "-",
                    "最新异常": abnormal,
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.subheader("员工详情")
        employee = employee_selector(db, "employee_detail")
        if not employee:
            return
        history = db.get_history(employee["id"])
        st.markdown(
            f"### {employee['name']}  \n{employee['gender']} · "
            f"出生年份：{employee.get('birth_year') or '未记录'} · "
            f"{len(history)} 份报告"
        )

        if not history:
            st.info("该员工暂无体检报告。")
            return

        for index, record in enumerate(reversed(history)):
            data = record["report_data"]
            indicators = data.get("indicators", {})
            abnormal = {
                name: info
                for name, info in indicators.items()
                if info.get("status") == "abnormal"
            }
            label = (
                f"{record['report_date']} · {len(indicators)} 项指标 · "
                f"{len(abnormal)} 项异常"
            )
            with st.expander(label, expanded=index == 0):
                st.write(
                    f"姓名：{data.get('name') or employee['name']} | "
                    f"性别：{data.get('gender') or employee['gender']} | "
                    f"年龄：{data.get('age') or '未记录'}"
                )
                table = []
                for name, info in indicators.items():
                    table.append(
                        {
                            "指标": name,
                            "结果": info.get("value"),
                            "单位": info.get("unit", ""),
                            "状态": info.get("status", "unknown"),
                            "参考范围": info.get("ref_range", ""),
                        }
                    )
                st.dataframe(table, use_container_width=True, hide_index=True)
                if abnormal:
                    st.markdown("**趋势与预警**")
                    for name in abnormal:
                        trend = db.check_trend_warning(employee["id"], name)
                        if trend["trend"] != "insufficient":
                            message = trend.get("message", "")
                            st.warning(
                                f"{name}: {trend['trend']} · "
                                f"{'预警：' + message if trend['warning'] else '暂无预警'}"
                            )
    finally:
        close_db(db)


def uploaded_to_temp(uploaded_file: Any) -> str:
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(uploaded_file.getbuffer())
        return handle.name


def process_report(
    uploaded_file: Any,
    use_llm_parse: bool = False,
    force_mock: bool = False,
) -> Dict[str, Any]:
    temp_path = uploaded_to_temp(uploaded_file)
    try:
        engine = OCREngine(use_gpu=False)
        parser = ReportParser()
        ocr_lines = engine.extract_text(temp_path)
        agent = build_agent(force_mock=force_mock)
        report = parse_report_compat(parser, ocr_lines, agent, use_llm_parse)
        report["_ocr_lines"] = ocr_lines
        report["_parse_source"] = (
            "llm"
            if use_llm_parse
            and not agent.mock_mode
            and hasattr(parser, "parse_with_llm")
            else "regex"
        )
        return report
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def save_report(report: Dict[str, Any]) -> int:
    db = get_db()
    try:
        name = report.get("name") or "未知员工"
        gender = report.get("gender") or "未知"
        employee_id = db.get_or_create_employee(name, gender)
        clean_report = {
            key: value
            for key, value in report.items()
            if not key.startswith("_")
        }
        return db.save_report(employee_id, clean_report)
    finally:
        close_db(db)


def render_report_result(report: Dict[str, Any], show_raw_ocr: bool = True) -> None:
    indicators = report.get("indicators", {})
    abnormal = {
        name: info
        for name, info in indicators.items()
        if info.get("status") == "abnormal"
    }
    st.success(
        f"解析完成：{report.get('name') or '未知员工'} · "
        f"{len(indicators)} 项指标 · {len(abnormal)} 项异常"
    )
    cols = st.columns(4)
    cols[0].metric("姓名", report.get("name") or "未识别")
    cols[1].metric("性别", report.get("gender") or "未识别")
    cols[2].metric("年龄", report.get("age") or "未识别")
    cols[3].metric("报告日期", report.get("report_date") or "未识别")

    table = [
        {
            "指标": name,
            "结果": info.get("value"),
            "单位": info.get("unit", ""),
            "状态": info.get("status", "unknown"),
            "异常方向": info.get("abnormal_type") or "-",
            "参考范围": info.get("ref_range") or "-",
        }
        for name, info in indicators.items()
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)
    if abnormal:
        st.warning("发现异常指标：" + "、".join(abnormal))
    if show_raw_ocr:
        with st.expander("查看 OCR 原始文本"):
            st.code("\n".join(report.get("_ocr_lines", [])), language="text")


def render_import_page() -> None:
    render_hero("报告导入", "上传单份图片或 PDF，完成 OCR、结构化解析、异常标记并写入 SQLite。")
    tabs = st.tabs(["单份导入", "批量导入", "解析测试"])

    with tabs[0]:
        uploaded = st.file_uploader(
            "上传体检报告",
            type=SUPPORTED_EXTENSIONS,
            key="single_report",
        )
        use_llm_parse = st.checkbox(
            "使用 LLM 辅助补全解析（后端不可用时自动回退正则）",
            value=False,
        )
        if uploaded and st.button("开始 OCR 与解析", type="primary"):
            with st.spinner("正在进行 OCR 和报告解析..."):
                try:
                    report = process_report(uploaded, use_llm_parse=use_llm_parse)
                    st.session_state["last_report"] = report
                except Exception as exc:
                    st.error(f"处理失败：{exc}")

        report = st.session_state.get("last_report")
        if report:
            render_report_result(report)
            if st.button("保存到数据库", key="save_single_report"):
                try:
                    record_id = save_report(report)
                    st.success(f"已保存报告，记录 ID：{record_id}")
                except Exception as exc:
                    st.error(f"保存失败：{exc}")

    with tabs[1]:
        batch = st.file_uploader(
            "上传多份图片或 PDF",
            type=SUPPORTED_EXTENSIONS,
            accept_multiple_files=True,
            key="batch_reports",
        )
        if batch:
            st.caption(f"已选择 {len(batch)} 个文件")
            st.dataframe(
                [{"文件": file.name, "大小": f"{file.size / 1024:.1f} KB"} for file in batch],
                use_container_width=True,
                hide_index=True,
            )
        if batch and st.button("开始批量导入", type="primary"):
            progress = st.progress(0)
            results = []
            for index, uploaded in enumerate(batch, 1):
                try:
                    report = process_report(uploaded)
                    record_id = save_report(report)
                    abnormal_count = sum(
                        1
                        for info in report.get("indicators", {}).values()
                        if info.get("status") == "abnormal"
                    )
                    results.append(
                        {
                            "文件": uploaded.name,
                            "状态": "成功",
                            "员工": report.get("name") or "未知",
                            "异常指标": abnormal_count,
                            "记录 ID": record_id,
                        }
                    )
                except Exception as exc:
                    results.append(
                        {"文件": uploaded.name, "状态": f"失败：{exc}"}
                    )
                progress.progress(index / len(batch))
            st.dataframe(results, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.caption("使用项目内置 Mock OCR 文本验证解析器，不需要上传文件或连接模型。")
        if st.button("运行 Mock 解析"):
            parser = ReportParser()
            report = parser.parse(get_mock_ocr_text())
            report["_ocr_lines"] = get_mock_ocr_text()
            st.session_state["last_parse_test"] = report
        if st.session_state.get("last_parse_test"):
            render_report_result(st.session_state["last_parse_test"])


def collect_trends(db: HealthDatabase) -> List[Dict[str, Any]]:
    rows = []
    for employee in db.get_all_employees():
        latest = db.get_latest_report(employee["id"])
        if not latest:
            continue
        for indicator_name in latest["report_data"].get("indicators", {}):
            trend = db.check_trend_warning(employee["id"], indicator_name)
            if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                rows.append(
                    {
                        "employee": employee,
                        "indicator": indicator_name,
                        "trend": trend,
                    }
                )
    return rows


def render_trends_page() -> None:
    render_hero("趋势分析", "把连续体检记录串起来，识别上升、下降、波动和边界预警。")
    db = get_db()
    try:
        rows = collect_trends(db)
        if not rows:
            st.info("趋势数据不足。每位员工至少需要两份包含相同指标的报告。")
            return

        options = [
            f"{row['employee']['name']} · {row['indicator']}" for row in rows
        ]
        selected = st.selectbox("选择趋势", options)
        row = rows[options.index(selected)]
        trend = row["trend"]
        cols = st.columns(4)
        cols[0].metric("趋势", trend["trend"])
        cols[1].metric("最新值", trend["values"][-1])
        cols[2].metric("历史点数", len(trend["values"]))
        cols[3].metric("预警", "是" if trend["warning"] else "否")
        if trend["warning"]:
            st.warning(trend["message"])
        else:
            st.success("当前趋势未触发预警。")

        chart_rows = pd.DataFrame(
            {
                "日期": trend["dates"],
                row["indicator"]: trend["values"],
            }
        ).set_index("日期")
        st.line_chart(chart_rows)
        st.dataframe(
            [
                {"日期": date, "数值": value}
                for date, value in zip(trend["dates"], trend["values"])
            ],
            use_container_width=True,
            hide_index=True,
        )
    finally:
        close_db(db)


def abnormal_options(db: HealthDatabase) -> List[Dict[str, Any]]:
    options = []
    for employee in db.get_all_employees():
        latest = db.get_latest_report(employee["id"])
        if not latest:
            continue
        for name, info in latest["report_data"].get("indicators", {}).items():
            if info.get("status") == "abnormal":
                options.append(
                    {"employee": employee, "name": name, "info": info}
                )
    return options


def render_advice(advice: Dict[str, Any], detailed: bool) -> None:
    source = advice.get("source", "unknown")
    st.caption(f"来源：{source}")
    st.markdown(f"**概述**  \n{advice.get('summary', '暂无')}")
    if advice.get("risk_level"):
        st.markdown(f"**风险等级：** {advice['risk_level']}")
    if detailed and advice.get("interpretation"):
        st.markdown(f"**解读**  \n{advice['interpretation']}")
    if detailed and advice.get("possible_causes"):
        st.markdown("**可能原因**")
        for item in advice["possible_causes"]:
            st.markdown(f"- {item}")
    if advice.get("advice"):
        st.markdown("**建议**")
        for item in advice["advice"]:
            st.markdown(f"- {item}")
    if detailed and advice.get("lifestyle"):
        st.markdown("**生活方式**")
        for item in advice["lifestyle"]:
            st.markdown(f"- {item}")
    if detailed and advice.get("follow_up"):
        st.markdown(f"**复查建议：** {advice['follow_up']}")
    if detailed and advice.get("urgency"):
        st.markdown(f"**就医建议：** {advice['urgency']}")
    if advice.get("knowledge_ref"):
        st.info(f"知识库引用：{advice['knowledge_ref']}")


def render_llm_page() -> None:
    render_hero("LLM 指标解读", "只对异常指标调用解读能力，并保留 Mock 回退，方便离线演示和测试。")
    db = get_db()
    try:
        options = abnormal_options(db)
        if not options:
            st.info("当前没有最新异常指标可供解读。")
            return

        labels = [
            f"{item['employee']['name']} · {item['name']} · "
            f"{item['info'].get('value')} {item['info'].get('unit', '')}"
            for item in options
        ]
        selected = st.selectbox("选择异常指标", labels)
        item = options[labels.index(selected)]
        detailed = st.toggle("详细模式", value=False)
        st.markdown(
            f"**{item['name']}** · {item['employee']['name']} · "
            f"参考范围：{item['info'].get('ref_range') or '未知'}"
        )
        if st.button("生成健康解读", type="primary"):
            with st.spinner("正在生成解读..."):
                agent = build_agent()
                advice = get_advice_compat(
                    agent,
                    item["name"],
                    item["info"].get("value", 0),
                    item["info"].get("ref_range", ""),
                    detailed,
                )
                st.session_state["last_advice"] = advice
        if st.session_state.get("last_advice"):
            render_advice(st.session_state["last_advice"], detailed)
    finally:
        close_db(db)


def render_mock_page() -> None:
    render_hero("模拟数据", "一键导入 5 位员工、3 年历史报告，用于体验趋势预警和健康概览。")
    db = get_db()
    try:
        count = len(db.get_all_employees())
        st.metric("当前员工数", count)
        st.warning("重复导入会追加同一批报告。建议在需要干净演示时先重置数据库。")
        if st.button("导入模拟数据", type="primary"):
            with st.spinner("正在写入模拟数据..."):
                init_mock_database(db)
            st.success("模拟数据导入完成。")
            st.rerun()
    finally:
        close_db(db)


def render_settings_page() -> None:
    render_hero("设置", "配置 OpenAI 兼容 API、LM Studio 或让系统自动回退到 Mock 模式。")
    cfg = current_llm_config()
    with st.form("llm_settings"):
        api_key = st.text_input(
            "API Key",
            value=cfg["api_key"],
            type="password",
            help="仅写入当前 Streamlit 进程环境，不会写入项目文件。",
        )
        base_url = st.text_input(
            "Base URL",
            value=cfg["base_url"],
            placeholder="https://api.openai.com/v1 或 http://localhost:1234/v1",
        )
        model = st.text_input("Model", value=cfg["model"])
        submitted = st.form_submit_button("应用设置", type="primary")
    if submitted:
        os.environ["OPENAI_API_KEY"] = api_key.strip()
        os.environ["LLM_BASE_URL"] = base_url.strip()
        os.environ["LLM_MODEL"] = model.strip()
        st.success("设置已应用到当前 Streamlit 进程。")

    if st.button("测试连接"):
        with st.spinner("正在测试后端连接..."):
            agent = build_agent()
        if agent.mock_mode:
            st.warning("后端不可用，当前会使用 Mock 模式。")
        else:
            st.success(f"连接成功：{agent.backend} · {agent.base_url} · {agent.model_name}")

    st.subheader("当前状态")
    active = current_llm_config()
    st.dataframe(
        [
            {
                "项目": "API Key",
                "状态": f"已设置（{active['api_key'][:8]}...）"
                if active["api_key"]
                else "未设置",
            },
            {"项目": "Base URL", "状态": active["base_url"] or "自动选择"},
            {"项目": "Model", "状态": active["model"] or "默认"},
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_reset_action() -> None:
    with st.sidebar:
        st.divider()
        st.markdown("### 数据维护")
        st.caption("删除数据库后，下一次访问会自动重建空表。")
        if st.button("清空全部数据", type="secondary"):
            st.session_state["confirm_reset"] = True
        if st.session_state.get("confirm_reset"):
            st.warning("此操作会删除所有员工和体检记录。")
            if st.button("确认删除", type="primary"):
                if DB_PATH.exists():
                    DB_PATH.unlink()
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(DB_PATH) + suffix)
                    if sidecar.exists():
                        sidecar.unlink()
                st.session_state["confirm_reset"] = False
                st.success("数据库已清空。")
                st.rerun()


def main() -> None:
    inject_styles()
    page = render_sidebar()
    render_reset_action()

    if page == "总览":
        render_overview()
    elif page == "员工档案":
        render_employee_page()
    elif page == "报告导入":
        render_import_page()
    elif page == "趋势分析":
        render_trends_page()
    elif page == "LLM 解读":
        render_llm_page()
    elif page == "模拟数据":
        render_mock_page()
    elif page == "设置":
        render_settings_page()


if __name__ == "__main__":
    main()
