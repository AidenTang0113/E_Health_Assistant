"""报告管理：添加报告 + 批量导入。"""

from __future__ import annotations

import traceback
from pathlib import Path

import streamlit as st

from web.state import get_db, get_user_db, can_view_all, is_hr, PROJECT_ROOT


def render_reports() -> None:
    """报告管理页面。"""
    st.title("📁 报告管理")

    if not can_view_all():
        st.warning("您没有权限访问报告管理。")
        return

    tab1, tab2 = st.tabs(["📝 添加报告", "📦 批量导入"])

    with tab1:
        _render_add_report()
    with tab2:
        _render_batch_import()


def _render_add_report() -> None:
    db = get_db()
    employees = db.get_all_employees()

    if not employees:
        st.info("无员工数据，请先批量导入报告。")
        return

    # 选择员工
    emp_options = {f"{e['name']} ({e['gender']}, ID:{e['id']})": e for e in employees}
    selected_label = st.selectbox("选择员工", list(emp_options.keys()))
    emp = emp_options[selected_label]

    st.markdown(f"**选中**: {emp['name']} ({emp['gender']})")

    method = st.radio("导入方式", ["OCR 识别图片", "OCR 识别 PDF", "手动输入"], horizontal=True)

    if method == "OCR 识别图片":
        _ocr_import(emp, is_pdf=False)
    elif method == "OCR 识别 PDF":
        _ocr_import(emp, is_pdf=True)
    else:
        _manual_import(emp)


def _ocr_import(emp: dict, is_pdf: bool) -> None:
    file_label = "PDF" if is_pdf else "图片"
    accept_types = ["application/pdf"] if is_pdf else ["png", "jpg", "jpeg", "bmp"]

    uploaded = st.file_uploader(
        f"上传{file_label}文件",
        type=accept_types,
        key=f"upload_{'pdf' if is_pdf else 'img'}",
    )

    if uploaded is None:
        return

    # 保存临时文件
    tmp_path = PROJECT_ROOT / "data" / f"tmp_upload_{uploaded.name}"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "wb") as f:
        f.write(uploaded.getvalue())

    try:
        if st.button("🔍 开始 OCR 识别", type="primary"):
            with st.spinner("正在识别..."):
                from core.ocr_engine import OCREngine
                from core.parser import ReportParser

                ocr = OCREngine()
                texts = ocr.extract_text(str(tmp_path))

                if not texts or not any(t.strip() for t in texts):
                    st.error("OCR 未识别到文本")
                    return

                st.success(f"识别到 {len([t for t in texts if t.strip()])} 行文本")

                parser = ReportParser()
                report_data = parser.parse(texts)

                if not report_data.get("indicators"):
                    st.error("未能解析出指标数据")
                    st.text("原始文本:")
                    for t in texts:
                        st.text(t[:200])
                    return

                ind_count = len(report_data["indicators"])
                abnormal_count = sum(
                    1 for v in report_data["indicators"].values()
                    if v.get("status") == "abnormal"
                )
                st.success(f"解析到 {ind_count} 项指标, {abnormal_count} 项异常")

                # 显示解析结果
                _display_parsed_report(report_data)

                # 补充日期/医院
                report_date = report_data.get("report_date") or ""
                if not report_date:
                    report_date = st.text_input("报告日期 (YYYY-MM-DD)", "")
                    report_data["report_date"] = report_date

                hospital = report_data.get("hospital", "")
                if not hospital:
                    hospital = st.text_input("医院名称", "")
                    report_data["hospital"] = hospital

                if st.button("✅ 确认导入", type="primary"):
                    db = get_db()
                    new_id = db.save_report(emp["id"], report_data)
                    st.success(f"导入成功！报告 ID: {new_id}")

                    # 同步员工账号
                    _sync_employee_account(emp)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _manual_import(emp: dict) -> None:
    st.markdown("### 手动输入指标")

    report_date = st.text_input("报告日期 (YYYY-MM-DD)", "")
    hospital = st.text_input("医院名称", "")

    indicators = {}
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.caption("指标名")
    with col2:
        st.caption("值")
    with col3:
        st.caption("单位")
    with col4:
        st.caption("参考范围")

    # 动态行数，最多 30 项
    row_count = st.number_input("指标行数", min_value=1, max_value=30, value=5, step=1)

    for i in range(row_count):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            name = st.text_input(f"指标名 #{i+1}", key=f"ind_name_{i}", label_visibility="collapsed")
        with c2:
            val_str = st.text_input(f"值 #{i+1}", key=f"ind_val_{i}", label_visibility="collapsed")
        with c3:
            unit = st.text_input(f"单位 #{i+1}", key=f"ind_unit_{i}", label_visibility="collapsed")
        with c4:
            ref = st.text_input(f"参考范围 #{i+1}", key=f"ind_ref_{i}", label_visibility="collapsed")

        if name and val_str:
            try:
                value = float(val_str)
            except ValueError:
                value = val_str

            status = "normal"
            if ref and isinstance(value, (int, float)):
                parts = ref.replace("～", "-").replace("~", "-").split("-")
                if len(parts) == 2:
                    try:
                        lo, hi = float(parts[0]), float(parts[1])
                        if value < lo or value > hi:
                            status = "abnormal"
                    except ValueError:
                        pass

            indicators[name] = {
                "value": value,
                "unit": unit,
                "ref_range": ref,
                "status": status,
            }

    if st.button("✅ 提交报告", type="primary"):
        if not indicators:
            st.error("未输入任何指标")
            return
        if not report_date:
            st.error("请输入报告日期")
            return

        report_data = {
            "hospital": hospital,
            "report_date": report_date,
            "indicators": indicators,
        }

        db = get_db()
        new_id = db.save_report(emp["id"], report_data)
        st.success(f"报告已添加！ID: {new_id}")
        _sync_employee_account(emp)


def _render_batch_import() -> None:
    st.markdown("### 批量导入")
    st.caption("支持 png/jpg/jpeg/bmp/pdf 格式，文件命名约定: `员工姓名_日期.ext` 或 `员工姓名.ext`")

    uploaded_files = st.file_uploader(
        "选择多个文件",
        type=["png", "jpg", "jpeg", "bmp", "pdf"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        return

    st.info(f"已选择 {len(uploaded_files)} 个文件")

    # 显示文件列表
    file_names = [f.name for f in uploaded_files]
    st.write(", ".join(file_names))

    if st.button("🚀 开始批量导入", type="primary"):
        from core.ocr_engine import OCREngine
        from core.parser import ReportParser

        db = get_db()
        ocr = OCREngine()
        parser = ReportParser()
        success, fail = 0, 0
        results = []

        progress = st.progress(0, desc="准备导入...")

        for i, uploaded in enumerate(uploaded_files):
            progress.progress(i / len(uploaded_files), desc=f"处理 {uploaded.name}...")

            # 保存临时文件
            tmp_path = PROJECT_ROOT / "data" / f"tmp_batch_{uploaded.name}"
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                texts = ocr.extract_text(str(tmp_path))
                if not texts or not any(t.strip() for t in texts):
                    fail += 1
                    results.append((uploaded.name, "失败", "OCR 无文本"))
                    continue

                report_data = parser.parse(texts)
                if not report_data.get("indicators"):
                    fail += 1
                    results.append((uploaded.name, "失败", "解析无指标"))
                    continue

                # 确定员工
                emp_name = report_data.get("name") or Path(uploaded.name).stem.split("_")[0].strip()
                emp_gender = report_data.get("gender") or "未知"

                if not emp_name:
                    fail += 1
                    results.append((uploaded.name, "失败", "无法确定员工姓名"))
                    continue

                # 确定日期
                report_date = report_data.get("report_date") or ""
                if not report_date and "_" in Path(uploaded.name).stem:
                    parts = Path(uploaded.name).stem.split("_")
                    if len(parts) >= 2:
                        potential = parts[1].strip()
                        if len(potential) == 10 and potential.count("-") == 2:
                            report_date = potential
                if report_date:
                    report_data["report_date"] = report_date

                emp_id = db.get_or_create_employee(emp_name, emp_gender)
                emp = db.get_employee(emp_id)

                ind_count = len(report_data["indicators"])
                abnormal_count = sum(
                    1 for v in report_data["indicators"].values()
                    if v.get("status") == "abnormal"
                )

                db.save_report(emp_id, report_data)
                _sync_employee_account(emp)

                success += 1
                results.append((
                    uploaded.name,
                    "成功",
                    f"{emp['name']}({emp['gender']}): {ind_count}项, {abnormal_count}异常, {report_date or '未知'}"
                ))

            except Exception as e:
                fail += 1
                results.append((uploaded.name, "失败", str(e)))
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

        progress.progress(1.0, desc="导入完成")
        progress.empty()

        # 结果汇总
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        col1.metric("成功", success)
        col2.metric("失败", fail)
        col3.metric("总计", len(uploaded_files))

        import pandas as pd
        st.dataframe(
            pd.DataFrame(results, columns=["文件", "状态", "详情"]),
            use_container_width=True,
            hide_index=True,
        )

        if success > 0:
            st.success(f"批量导入完成: 成功 {success} 份, 失败 {fail} 份")


def _display_parsed_report(report_data: dict) -> None:
    """展示解析结果。"""
    import pandas as pd

    indicators = report_data.get("indicators", {})
    rows = []
    for name, info in indicators.items():
        status = info.get("status", "?")
        tag = "⚠️" if status == "abnormal" else "✅"
        rows.append({
            "": tag,
            "指标": name,
            "值": f"{info.get('value', '?')} {info.get('unit', '')}",
            "参考范围": info.get("ref_range", ""),
            "状态": status,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if report_data.get("name"):
        st.caption(f"姓名: {report_data['name']}")
    if report_data.get("gender"):
        st.caption(f"性别: {report_data['gender']}")
    if report_data.get("report_date"):
        st.caption(f"日期: {report_data['report_date']}")


def _sync_employee_account(employee: dict) -> None:
    """同步员工账号。"""
    try:
        user_db = get_user_db()
        user_db.ensure_employee_account(employee, employee_id=employee["id"])
    except Exception:
        pass  # 同步失败不影响主流程
