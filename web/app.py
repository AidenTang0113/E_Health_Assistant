"""
E-Health Agent — Streamlit Web 版入口

启动方式:
    streamlit run web/app.py

功能:
    - 保留 CLI 版全部业务逻辑（复用 core/ 模块）
    - 三角色权限：HR / 经理 / 员工
    - OCR 识别体检报告（图片/PDF）
    - LLM 智能解读（API / 本地 / Mock 三模式）
    - 历史趋势预警
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

from web.state import init_session_state, is_logged_in


# ──────────────────────────── 配色体系 ────────────────────────────
THEME_CSS = """
<style>
/* ====== CSS 变量：明/暗双套 ====== */
:root {
    --eh-primary: #0891b2;
    --eh-primary-dark: #0e7490;
    --eh-primary-light: #67e8f9;
    --eh-bg: #f8fafc;
    --eh-card-bg: #ffffff;
    --eh-border: #e2e8f0;
    --eh-text: #1e293b;
    --eh-text-muted: #64748b;
    --eh-normal: #10b981;
    --eh-normal-bg: #d1fae5;
    --eh-abnormal-high: #f59e0b;
    --eh-abnormal-high-bg: #fef3c7;
    --eh-abnormal-low: #6366f1;
    --eh-abnormal-low-bg: #e0e7ff;
    --eh-danger: #ef4444;
    --eh-danger-bg: #fee2e2;
    --eh-sidebar-bg: #ffffff;
    --eh-sidebar-border: #e2e8f0;
}

[data-testid="stAppViewContainer"][data-theme="dark"], .stApp[data-theme="dark"] {
    --eh-primary: #22d3ee;
    --eh-primary-dark: #0891b2;
    --eh-primary-light: #a5f3fc;
    --eh-bg: #0f172a;
    --eh-card-bg: #1e293b;
    --eh-border: #334155;
    --eh-text: #f1f5f9;
    --eh-text-muted: #94a3b8;
    --eh-normal: #34d399;
    --eh-normal-bg: #064e3b;
    --eh-abnormal-high: #fbbf24;
    --eh-abnormal-high-bg: #78350f;
    --eh-abnormal-low: #818cf8;
    --eh-abnormal-low-bg: #312e81;
    --eh-danger: #f87171;
    --eh-danger-bg: #7f1d1d;
    --eh-sidebar-bg: #1e293b;
    --eh-sidebar-border: #334155;
}

/* ====== 全局布局 ====== */
.stApp {
    background-color: var(--eh-bg);
    color: var(--eh-text);
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

/* ====== 卡片容器 ====== */
.stCard, .stContainer > div {
    background-color: var(--eh-card-bg);
    border: 1px solid var(--eh-border);
    border-radius: 0.75rem;
    padding: 1rem;
}

/* ====== 标题 ====== */
h1, .stTitle {
    color: var(--eh-primary-dark);
    font-weight: 700;
}

h2, h3, .stHeader {
    color: var(--eh-text);
    font-weight: 600;
}

/* ====== 侧边栏 ====== */
section[data-testid="stSidebar"] {
    background-color: var(--eh-sidebar-bg);
    border-right: 1px solid var(--eh-sidebar-border);
}

/* ====== 按钮主色 ====== */
.stButton > button[kind="primary"],
.stButton > button[data-kind="primary"] {
    background-color: var(--eh-primary);
    border-color: var(--eh-primary);
    color: white;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-kind="primary"]:hover {
    background-color: var(--eh-primary-dark);
    border-color: var(--eh-primary-dark);
}

/* ====== Metric 卡片 ====== */
[data-testid="stMetric"] {
    background-color: var(--eh-card-bg);
    border: 1px solid var(--eh-border);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
}
[data-testid="stMetricLabel"] {
    color: var(--eh-text-muted);
    font-size: 0.8rem;
}
[data-testid="stMetricValue"] {
    color: var(--eh-primary-dark);
    font-weight: 700;
}

/* ====== 数据表格 ====== */
.stDataFrame {
    font-size: 0.85rem;
}
.stDataFrame table {
    border-radius: 0.5rem;
    overflow: hidden;
}
.stDataFrame thead th {
    background-color: var(--eh-primary);
    color: white;
    font-weight: 600;
}

/* ====== Expander ====== */
details.stExpander {
    border: 1px solid var(--eh-border);
    border-radius: 0.5rem;
    background-color: var(--eh-card-bg);
}
details.stExpander > summary {
    color: var(--eh-text);
    font-weight: 500;
}

/* ====== Tabs ====== */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    border-bottom: 2px solid var(--eh-border);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 0.5rem 0.5rem 0 0;
    padding: 0.5rem 1rem;
    color: var(--eh-text-muted);
    background-color: transparent;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: var(--eh-primary-dark);
    background-color: var(--eh-card-bg);
    border-bottom: 3px solid var(--eh-primary);
    font-weight: 600;
}

/* ====== 状态语义色 ====== */
/* 正常 — 柔和绿 */
.stSuccess, div[data-testid="stAlertContent"] {
    border-radius: 0.5rem;
}
.stSuccess > div {
    background-color: var(--eh-normal-bg) !important;
    border-color: var(--eh-normal) !important;
}

/* 警告 — 琥珀橙 */
.stWarning > div {
    background-color: var(--eh-abnormal-high-bg) !important;
    border-color: var(--eh-abnormal-high) !important;
}

/* 错误/危险 — 珊瑚红 */
.stError > div {
    background-color: var(--eh-danger-bg) !important;
    border-color: var(--eh-danger) !important;
}

/* 信息 — 医疗蓝 */
.stInfo > div {
    background-color: #e0f2fe !important;
    border-color: var(--eh-primary) !important;
}

/* ====== 表单输入框 ====== */
.stTextInput > div > input,
.stTextArea > div > textarea {
    border-color: var(--eh-border);
    border-radius: 0.375rem;
}
.stTextInput > div > input:focus,
.stTextArea > div > textarea:focus {
    border-color: var(--eh-primary);
    box-shadow: 0 0 0 2px rgba(8, 145, 178, 0.2);
}

/* =====| 登录页 |===== */
.login-header {
    text-align: center;
    padding: 2rem 0 1rem;
}
.login-header h1 {
    font-size: 2.2rem;
    color: var(--eh-primary);
    margin-bottom: 0.3rem;
}
.login-header p {
    color: var(--eh-text-muted);
    font-size: 0.95rem;
}

/* ====== 进度条 ====== */
.stProgress > div > div {
    background-color: var(--eh-primary);
}

/* ====== Spinner ====== */
.stSpinner > div {
    border-top-color: var(--eh-primary);
}

/* ====== 分割线 ====== */
hr, .stDivider {
    border-color: var(--eh-border);
}

/* =====| 暗色模式微调 |===== */
.stApp[data-theme="dark"] .stInfo > div {
    background-color: #082f49 !important;
}
.stApp[data-theme="dark"] .stSuccess > div {
    background-color: var(--eh-normal-bg) !important;
}
.stApp[data-theme="dark"] .stWarning > div {
    background-color: var(--eh-abnormal-high-bg) !important;
}
.stApp[data-theme="dark"] .stError > div {
    background-color: var(--eh-danger-bg) !important;
}
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title="E-Health Agent",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 注入医疗专业配色体系
    st.markdown(THEME_CSS, unsafe_allow_html=True)

    init_session_state()

    if not is_logged_in():
        from web.views.login import render_login
        render_login()
    else:
        from web.layout import render_layout
        render_layout()


if __name__ == "__main__":
    main()
