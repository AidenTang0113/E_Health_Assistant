"""UI 组件：面包屑 + 区块标题 + 趋势可视化（Plotly 折线图）。"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st


# ──────────────────────────── 通用组件 ────────────────────────────

def breadcrumb(*crumbs: str) -> None:
    """面包屑导航。

    用法:
        breadcrumb("首页", "总体查看", "全员概览")
    """
    if not crumbs:
        return

    items = []
    for i, c in enumerate(crumbs):
        if i < len(crumbs) - 1:
            items.append(f'<span class="eh-crumb">{c}</span>')
            items.append('<span class="eh-crumb-sep">/</span>')
        else:
            items.append(f'<span class="eh-crumb-current">{c}</span>')

    st.markdown(
        f'<div class="eh-breadcrumb">{" ".join(items)}</div>',
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str | None = None) -> None:
    """页面区块标题：替代 st.subheader，带更清晰的层级。

    用法:
        section_header("员工列表", "共 5 名员工")
    """
    if subtitle:
        st.markdown(
            f'<div class="eh-section-header">'
            f'<h3>{title}</h3>'
            f'<span class="eh-section-sub">{subtitle}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="eh-section-header"><h3>{title}</h3></div>',
            unsafe_allow_html=True,
        )


# ──────────────────────────── 趋势可视化 ────────────────────────────


# ── 语义色（与全局 CSS 对齐）──
_COLOR_PRIMARY = "#0891b2"
_COLOR_NORMAL = "#10b981"
_COLOR_NORMAL_BG = "rgba(16, 185, 129, 0.10)"
_COLOR_HIGH = "#f59e0b"
_COLOR_LOW = "#6366f1"
_COLOR_DANGER = "#ef4444"
_COLOR_GRID = "#e2e8f0"
_COLOR_TEXT = "#64748b"
_COLOR_AXIS = "#94a3b8"


def _parse_ref_range(ref_range: str) -> tuple[float | None, float | None]:
    """从参考范围字符串解析下限和上限。

    支持: "3.9-6.1", "3.9～6.1", "3.9~6.1", "< 5.2", "> 1.0"
    """
    if not ref_range:
        return None, None

    ref = ref_range.strip()

    # 处理 < / > 格式
    if ref.startswith("<") or ref.startswith("＜"):
        try:
            return None, float(ref.lstrip("<＜ ").strip())
        except ValueError:
            return None, None
    if ref.startswith(">") or ref.startswith("＞"):
        try:
            return float(ref.lstrip(">＞ ").strip()), None
        except ValueError:
            return None, None

    # 标准范围：low-high
    ref = ref.replace("～", "-").replace("~", "-")
    parts = ref.split("-")
    if len(parts) == 2:
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            return None, None

    return None, None


def render_trend_chart(
    indicator_name: str,
    dates: list[str],
    values: list[float],
    ref_range: str,
    unit: str = "",
    abnormal_flags: list[bool] | None = None,
    height: int = 360,
) -> None:
    """渲染单个指标的趋势折线图。

    Args:
        indicator_name: 指标名称（中文）
        dates: 日期列表 ["2022-06-01", "2023-06-01", ...]
        values: 数值列表 [5.2, 5.5, 5.8]
        ref_range: 参考范围字符串 "3.9-6.1"
        unit: 单位 "mmol/L"
        abnormal_flags: 每个点是否异常的标记
        height: 图表高度
    """
    if not dates or not values:
        st.info(f"暂无 {indicator_name} 的历史数据")
        return

    lo, hi = _parse_ref_range(ref_range)
    if abnormal_flags is None:
        abnormal_flags = [False] * len(values)

    fig = go.Figure()

    # ── 参考范围色带 ──
    if lo is not None and hi is not None:
        fig.add_hrect(
            y0=lo, y1=hi,
            fillcolor=_COLOR_NORMAL_BG,
            layer="below",
            line_width=0,
            annotation_text=f"正常范围 {lo}-{hi}",
            annotation_position="top left",
            annotation_font_size=10,
            annotation_font_color=_COLOR_NORMAL,
        )
    elif hi is not None:
        # 仅上限
        fig.add_hrect(
            y0=0, y1=hi,
            fillcolor=_COLOR_NORMAL_BG,
            layer="below",
            line_width=0,
        )
    elif lo is not None:
        # 仅下限
        fig.add_hrect(
            y0=lo, y1=max(values) * 1.2 if values else lo + 1,
            fillcolor=_COLOR_NORMAL_BG,
            layer="below",
            line_width=0,
        )

    # ── 参考范围边界线 ──
    if lo is not None:
        fig.add_hline(
            y=lo, line_dash="dash", line_color=_COLOR_NORMAL,
            line_width=1, opacity=0.5,
        )
    if hi is not None:
        fig.add_hline(
            y=hi, line_dash="dash", line_color=_COLOR_NORMAL,
            line_width=1, opacity=0.5,
        )

    # ── 正常数据点 ──
    normal_x = [dates[i] for i in range(len(dates)) if not abnormal_flags[i]]
    normal_y = [values[i] for i in range(len(dates)) if not abnormal_flags[i]]
    if normal_x:
        fig.add_trace(go.Scatter(
            x=normal_x, y=normal_y,
            mode="lines+markers",
            name="正常",
            line=dict(color=_COLOR_PRIMARY, width=2.5),
            marker=dict(size=8, color=_COLOR_PRIMARY),
            hovertemplate=(
                f"<b>{indicator_name}</b><br>"
                "日期: %{x}<br>"
                f"数值: %{{y}} {unit}<br>"
                "<extra></extra>"
            ),
            connectgaps=True,
        ))

    # ── 异常数据点 ──
    abnormal_x = [dates[i] for i in range(len(dates)) if abnormal_flags[i]]
    abnormal_y = [values[i] for i in range(len(dates)) if abnormal_flags[i]]
    if abnormal_x:
        fig.add_trace(go.Scatter(
            x=abnormal_x, y=abnormal_y,
            mode="markers",
            name="异常",
            marker=dict(
                size=11,
                color=_COLOR_DANGER,
                symbol="circle",
                line=dict(width=2, color="white"),
            ),
            hovertemplate=(
                f"<b>{indicator_name} ⚠️ 异常</b><br>"
                "日期: %{x}<br>"
                f"数值: %{{y}} {unit}<br>"
                f"参考范围: {ref_range}<br>"
                "<extra></extra>"
            ),
        ))

    # ── 连接线（穿过异常点）──
    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines",
        line=dict(color=_COLOR_PRIMARY, width=1.5, dash="dot"),
        showlegend=False,
        hoverinfo="skip",
        connectgaps=True,
    ))

    # ── 布局 ──
    title_text = f"{indicator_name}"
    if unit:
        title_text += f" ({unit})"

    y_range = None
    if values:
        y_min = min(values + ([lo] if lo else []))
        y_max = max(values + ([hi] if hi else []))
        padding = (y_max - y_min) * 0.15 if y_max > y_min else 1
        y_range = [y_min - padding, y_max + padding]

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14, color=_COLOR_TEXT)),
        xaxis=dict(
            title="",
            tickfont=dict(size=11, color=_COLOR_AXIS),
            gridcolor=_COLOR_GRID,
            showgrid=True,
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=11, color=_COLOR_AXIS),
            gridcolor=_COLOR_GRID,
            showgrid=True,
            range=y_range,
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, sans-serif", color=_COLOR_TEXT),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11),
        ),
        margin=dict(l=40, r=20, t=50, b=20),
        height=height,
        showlegend=True,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_multi_trend(
    indicators: dict[str, dict],
    dates: list[str],
    height: int = 300,
) -> None:
    """多指标小倍数图（small multiples）。

    Args:
        indicators: {指标名: {values: [...], ref_range: "...", unit: "...", abnormal_flags: [...]}}
        dates: 日期列表
        height: 每个子图高度
    """
    if not indicators:
        st.info("暂无可展示的趋势数据")
        return

    cols = st.columns(min(len(indicators), 3))
    items = list(indicators.items())

    for idx, (name, data) in enumerate(items):
        col_idx = idx % min(len(indicators), 3)
        with cols[col_idx]:
            render_trend_chart(
                indicator_name=name,
                dates=dates,
                values=data["values"],
                ref_range=data.get("ref_range", ""),
                unit=data.get("unit", ""),
                abnormal_flags=data.get("abnormal_flags"),
                height=height,
            )
