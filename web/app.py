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


def main() -> None:
    st.set_page_config(
        page_title="E-Health Agent",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 全局样式
    st.markdown(
        """
        <style>
        /* 紧凑布局 */
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        /* 表格字体 */
        .stDataFrame {
            font-size: 0.85rem;
        }
        /* 侧边栏 */
        .stSidebar > div:first-child {
            padding-top: 1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    init_session_state()

    if not is_logged_in():
        from web.pages.login import render_login
        render_login()
    else:
        from web.layout import render_layout
        render_layout()


if __name__ == "__main__":
    main()
