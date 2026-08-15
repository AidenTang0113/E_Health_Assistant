"""
E-Health Agent 正式版 CLI
运行后进入交互式菜单界面，支持体检报告全流程管理。
LLM 配置通过界面设置，持久化存储，下次启动自动加载。

用法:
    python cli.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e_health")


# ======================================================================
#  配置管理
# ======================================================================

def _load_config() -> dict:
    """加载持久化配置"""
    from core.config_manager import load_config
    return load_config()


def _save_config(config: dict) -> bool:
    """保存配置到文件"""
    from core.config_manager import save_config as _save
    return _save(config)


def _get_llm_agent():
    """根据当前配置获取 LLM Agent 实例"""
    from core.llm_agent import LLMAgent
    from core.config_manager import get_llm_config

    llm_cfg = get_llm_config()

    return LLMAgent(
        base_url=llm_cfg["base_url"] or None,
        api_key=llm_cfg["api_key"] or None,
        model_name=llm_cfg["model"] or None,
    )


# ======================================================================
#  工具函数
# ======================================================================

def print_header(title: str) -> None:
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _pause() -> None:
    _input("\n  按回车键继续...")


def _confirm(prompt: str) -> bool:
    return _input(f"  {prompt} (y/n): ").lower() == "y"


def _get_db():
    from core.database import HealthDatabase
    return HealthDatabase(str(PROJECT_ROOT / "data" / "health.db"))


def _get_user_db():
    from core.user_database import UserDatabase
    return UserDatabase(str(PROJECT_ROOT / "data" / "users.db"))


def _db_exists() -> bool:
    return (PROJECT_ROOT / "data" / "health.db").exists()


def _sync_employee_account(employee: dict, employee_id: int) -> None:
    user_db = _get_user_db()
    account, _ = user_db.ensure_employee_account(employee, employee_id=employee_id)
    user_db.close()
    logger.debug(
        "员工账号已同步: %s (%s)",
        account.get("employee_name"),
        account.get("username"),
    )


def _sync_all_employee_accounts() -> int:
    if not _db_exists():
        return 0
    db = _get_db()
    try:
        employees = db.get_all_employees()
        if not employees:
            return 0
        user_db = _get_user_db()
        try:
            synced = user_db.sync_employees(employees)
        finally:
            user_db.close()
        return sum(1 for _, password in synced if password)
    finally:
        db.close()


def func_auth_prompt() -> dict | None:
    print_header("员工账号")
    user_db = _get_user_db()
    try:
        while True:
            username = _input("  用户名: ")
            password = _input("  密码: ")
            user = user_db.authenticate(username, password)
            if user:
                print(f"  [OK] 登录成功: {user['employee_name']} ({user['username']})")
                _pause()
                return user
            print("  [!] 登录失败")
            _pause()
    finally:
        user_db.close()


def _show_status() -> bool:
    """显示数据库和 LLM 状态"""
    from core.config_manager import get_status_text

    # 数据库状态
    if not _db_exists():
        db_status = "未创建"
        has_data = False
    else:
        db = _get_db()
        employees = db.get_all_employees()
        if not employees:
            db_status = "空"
            has_data = False
        else:
            total = sum(len(db.get_history(e["id"])) for e in employees)
            db_status = f"{len(employees)} 名员工, {total} 份报告"
            has_data = True
        db.close()

    print(f"  数据库: {db_status}")
    print(f"  LLM: {get_status_text()}")
    return has_data


# ======================================================================
#  核心功能
# ======================================================================

def func_overview() -> None:
    print_header("系统总览")

    if not _db_exists():
        print("  数据库不存在，请先导入数据")
        _pause()
        return

    db = _get_db()
    employees = db.get_all_employees()
    if not employees:
        print("  数据库为空，请先导入数据")
        db.close()
        _pause()
        return

    total_reports = 0
    total_abnormal = 0
    all_abnormal_items = {}

    for emp in employees:
        history = db.get_history(emp["id"])
        total_reports += len(history)
        for record in history:
            indicators = record["report_data"].get("indicators", {})
            for name, info in indicators.items():
                if info.get("status") == "abnormal":
                    total_abnormal += 1
                    if name not in all_abnormal_items:
                        all_abnormal_items[name] = {"count": 0, "employees": set()}
                    all_abnormal_items[name]["count"] += 1
                    all_abnormal_items[name]["employees"].add(emp["name"])

    print()
    print("  +--- 总览 ---+")
    print(f"  | 员工数: {len(employees)}")
    print(f"  | 报告数: {total_reports}")
    print(f"  | 异常记录: {total_abnormal} 条")
    print(f"  | 异常指标类型: {len(all_abnormal_items)} 种")

    print()
    print("  +--- 员工列表 ---+")
    print(f"  {'ID':>4}  {'姓名':<8} {'性别':<4} {'报告数':>4}  {'最新体检日期':<12}")
    print(f"  {'----':>4}  {'--------':<8} {'----':<4} {'----':>4}  {'------------':<12}")
    for emp in employees:
        history = db.get_history(emp["id"])
        latest = history[-1]["report_date"] if history else "-"
        print(f"  {emp['id']:>4}  {emp['name']:<8} {emp['gender']:<4} {len(history):>4}  {latest:<12}")

    print()
    print("  +--- 健康摘要 ---+")
    for emp in employees:
        history = db.get_history(emp["id"])
        if not history:
            continue
        latest = history[-1]
        indicators = latest["report_data"].get("indicators", {})
        abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}
        icon = "[OK]" if not abnormal else "[!]"
        print(f"\n  {icon} {emp['name']} ({emp['gender']}) - {latest['report_date']}")
        print(f"      指标: {len(indicators)} 项, 异常: {len(abnormal)} 项, 历史报告: {len(history)} 份")
        if abnormal:
            for name, info in abnormal.items():
                val = info.get("value", "?")
                unit = info.get("unit", "")
                atype = info.get("abnormal_type", "?")
                ref = info.get("ref_range", "?")
                print(f"      [!] {name}: {val} {unit} ({atype}, 参考: {ref})")
                trend = db.check_trend_warning(emp["id"], name)
                if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                    vals_str = " -> ".join(str(v) for v in trend["values"])
                    print(f"          趋势: {trend['trend']} ({vals_str})")
                    if trend["warning"]:
                        print(f"          预警: {trend['message']}")
        else:
            print(f"      所有指标正常")

    if all_abnormal_items:
        print()
        print("  +--- 异常指标排行 ---+")
        sorted_items = sorted(all_abnormal_items.items(), key=lambda x: x[1]["count"], reverse=True)
        print(f"  {'指标':<14} {'次数':>4}  {'涉及员工':<20}")
        print(f"  {'------------':<14} {'----':>4}  {'--------------------':<20}")
        for name, data in sorted_items:
            emps = ", ".join(sorted(data["employees"]))
            print(f"  {name:<14} {data['count']:>4}  {emps:<20}")

    db.close()
    _pause()


def func_employee_list() -> None:
    print_header("员工列表")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    employees = db.get_all_employees()
    if not employees:
        print("  无员工数据")
        db.close()
        _pause()
        return

    print(f"  {'ID':>4}  {'姓名':<8} {'性别':<4} {'出生年份':>6}  {'报告数':>4}  {'最新体检日期':<12}")
    print(f"  {'----':>4}  {'--------':<8} {'----':<4} {'------':>6}  {'----':>4}  {'------------':<12}")
    for emp in employees:
        history = db.get_history(emp["id"])
        latest = history[-1]["report_date"] if history else "-"
        birth = emp.get("birth_year") or "-"
        print(f"  {emp['id']:>4}  {emp['name']:<8} {emp['gender']:<4} {str(birth):>6}  {len(history):>4}  {latest:<12}")

    db.close()
    _pause()


def func_employee_detail() -> None:
    print_header("查询员工详情")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    employees = db.get_all_employees()
    if not employees:
        print("  无员工数据")
        db.close()
        _pause()
        return

    print("  选择员工:")
    for i, emp in enumerate(employees, 1):
        history = db.get_history(emp["id"])
        print(f"    {i}. {emp['name']} ({emp['gender']}, {len(history)}份报告)")
    print(f"    0. 返回")

    choice = _input("\n  请选择: ")
    if not choice or choice == "0":
        db.close()
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(employees):
            print("  [!] 无效选择")
            db.close()
            _pause()
            return
    except ValueError:
        print("  [!] 请输入数字")
        db.close()
        _pause()
        return

    emp = employees[idx]
    history = db.get_history(emp["id"])

    print(f"\n  {'=' * 46}")
    print(f"  员工: {emp['name']} ({emp['gender']})  ID: {emp['id']}")
    if emp.get("birth_year"):
        print(f"  出生年份: {emp['birth_year']}")
    print(f"  报告数: {len(history)}")
    print(f"  {'=' * 46}")

    for i, record in enumerate(history, 1):
        indicators = record["report_data"].get("indicators", {})
        abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}
        icon = "[!]" if abnormal else "[OK]"
        print(f"\n  [{i}] {record['report_date']}  {icon}  {len(indicators)}项指标, {len(abnormal)}项异常")

        if i == len(history):
            print("  -- 最新报告 --")
            for name, info in indicators.items():
                val = info.get("value", "?")
                unit = info.get("unit", "")
                status = info.get("status", "?")
                ref = info.get("ref_range", "")
                tag = "[!]" if status == "abnormal" else "   "
                print(f"    {tag} {name}: {val} {unit}  (参考: {ref})")
                trend = db.check_trend_warning(emp["id"], name)
                if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                    vals_str = " -> ".join(str(v) for v in trend["values"])
                    print(f"        趋势: {trend['trend']} ({vals_str})")
                    if trend["warning"]:
                        print(f"        [!] {trend['message']}")
        else:
            for name, info in abnormal.items():
                val = info.get("value", "?")
                unit = info.get("unit", "")
                print(f"    [!] {name}: {val} {unit}")

    db.close()
    _pause()


def func_add_report() -> None:
    print_header("添加体检报告")
    print("  1. 从图片文件导入 (OCR)")
    print("  2. 从 PDF 文件导入 (OCR)")
    print("  3. 批量导入目录")
    print("  0. 返回")

    choice = _input("\n  请选择: ")

    if choice == "1":
        _import_single_file(is_pdf=False)
    elif choice == "2":
        _import_single_file(is_pdf=True)
    elif choice == "3":
        _import_batch()
    _pause()


def _import_single_file(is_pdf: bool = False) -> None:
    label = "PDF" if is_pdf else "图片"
    path = _input(f"  请输入{label}路径: ")
    if not path:
        return

    p = Path(path)
    if not p.exists():
        print(f"  [!] 文件不存在: {path}")
        return

    print(f"\n  正在处理: {p.name}")

    try:
        from core.ocr_engine import OCREngine
        from core.parser import ReportParser

        print("  [1/5] OCR 识别中...")
        engine = OCREngine()
        if is_pdf:
            ocr_lines = engine.extract_text_from_pdf(str(p))
        else:
            ocr_lines = engine.extract_text_from_image(str(p))
        print(f"        识别到 {len(ocr_lines)} 行")

        print("  [2/5] 解析报告中...")
        parser = ReportParser()
        agent = _get_llm_agent()
        if not agent.mock_mode:
            report_data = parser.parse_with_llm(ocr_lines, llm_agent=agent)
            print(f"        解析方式: {report_data.get('_parse_source', 'regex')}")
        else:
            report_data = parser.parse(ocr_lines)
            print("        解析方式: regex")

        name = report_data.get("name", "未知")
        gender = report_data.get("gender", "男")
        indicators = report_data.get("indicators", {})
        abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}
        print(f"        姓名: {name}, 指标: {len(indicators)} 项, 异常: {len(abnormal)} 项")

        print("  [3/5] 存储到数据库...")
        db = _get_db()
        emp_id = db.get_or_create_employee(name, gender)
        record_id = db.save_report(emp_id, report_data)
        _sync_employee_account({"name": name, "gender": gender}, emp_id)
        print(f"        员工ID={emp_id}, 记录ID={record_id}")

        print("  [4/5] 趋势分析...")
        for ind_name in indicators:
            trend = db.check_trend_warning(emp_id, ind_name)
            if trend["trend"] != "insufficient":
                msg = f"        {ind_name}: 趋势={trend['trend']}"
                if trend["warning"]:
                    msg += f" [!] {trend['message']}"
                print(msg)

        if abnormal and not agent.mock_mode:
            print(f"  [5/5] LLM 解读异常指标...")
            for ind_name, ind_info in abnormal.items():
                advice = agent.get_advice(
                    ind_name, ind_info["value"],
                    ind_info.get("ref_range", ""),
                )
                print(f"        [{ind_name}] {advice.get('summary', '?')}")
        elif abnormal and agent.mock_mode:
            print("  [5/5] LLM 未配置，跳过解读")
        else:
            print("  [5/5] 无异常指标")

        db.close()
        print(f"\n  [OK] 导入完成: {name}")

    except Exception as e:
        logger.error(f"导入失败: {e}", exc_info=True)
        print(f"  [!] 导入失败: {e}")


def _import_batch() -> None:
    d = _input("  请输入目录路径: ")
    if not d:
        return

    p = Path(d)
    if not p.is_dir():
        print(f"  [!] 目录不存在: {d}")
        return

    supported_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".pdf"}
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in supported_exts)

    if not files:
        print(f"  [!] 目录中无支持的文件 ({', '.join(sorted(supported_exts))})")
        return

    print(f"\n  发现 {len(files)} 个文件:")
    for f in files:
        print(f"    - {f.name}")

    if not _confirm(f"  确认导入这 {len(files)} 个文件?"):
        print("  已取消")
        return

    try:
        from core.ocr_engine import OCREngine
        from core.parser import ReportParser

        engine = OCREngine()
        parser = ReportParser()
        db = _get_db()
        agent = _get_llm_agent()

        success = 0
        failed = 0

        for idx, file_path in enumerate(files, 1):
            print(f"\n  [{idx}/{len(files)}] {file_path.name}")

            try:
                if file_path.suffix.lower() == ".pdf":
                    ocr_lines = engine.extract_text_from_pdf(str(file_path))
                else:
                    ocr_lines = engine.extract_text_from_image(str(file_path))
                print(f"    OCR: {len(ocr_lines)} 行")

                if not agent.mock_mode:
                    report_data = parser.parse_with_llm(ocr_lines, llm_agent=agent)
                else:
                    report_data = parser.parse(ocr_lines)

                name = report_data.get("name", "未知")
                gender = report_data.get("gender", "男")
                indicators = report_data.get("indicators", {})
                abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}

                emp_id = db.get_or_create_employee(name, gender)
                record_id = db.save_report(emp_id, report_data)
                _sync_employee_account({"name": name, "gender": gender}, emp_id)
                print(f"    -> {name}, {len(indicators)}项指标, {len(abnormal)}项异常, 记录ID={record_id}")

                for ind_name, ind_info in abnormal.items():
                    trend = db.check_trend_warning(emp_id, ind_name)
                    if trend["trend"] != "insufficient":
                        tag = "[!]" if trend["warning"] else "   "
                        print(f"    {tag} {ind_name}: {ind_info['value']} {ind_info.get('unit', '')} 趋势={trend['trend']}")

                if abnormal and not agent.mock_mode:
                    for ind_name, ind_info in abnormal.items():
                        advice = agent.get_advice(
                            ind_name, ind_info["value"],
                            f"{ind_info.get('ref_range', '')} {ind_info.get('unit', '')}",
                        )
                        print(f"    [{ind_name}] {advice.get('summary', '?')}")

                success += 1
            except Exception as e:
                print(f"    [!] 处理失败: {e}")
                failed += 1

        db.close()
        print(f"\n  [OK] 批量导入完成: 成功 {success}, 失败 {failed}")

    except Exception as e:
        logger.error(f"批量导入失败: {e}", exc_info=True)
        print(f"  [!] 批量导入失败: {e}")


def func_llm_interpret() -> None:
    print_header("LLM 指标解读")

    print("  解读模式:")
    print("    1. 简略模式")
    print("    2. 详细模式")
    mode = _input("\n  请选择 (默认1): ")
    detailed = (mode == "2")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    employees = db.get_all_employees()
    if not employees:
        print("  无员工数据")
        db.close()
        _pause()
        return

    all_abnormal = {}
    for emp in employees:
        history = db.get_history(emp["id"])
        if history:
            latest = history[-1]
            indicators = latest["report_data"].get("indicators", {})
            for name, info in indicators.items():
                if info.get("status") == "abnormal":
                    if name not in all_abnormal:
                        all_abnormal[name] = []
                    all_abnormal[name].append((emp["name"], info))

    if not all_abnormal:
        print("  所有指标均正常，无需解读")
        db.close()
        _pause()
        return

    print(f"\n  异常指标 ({len(all_abnormal)} 种):")
    items = list(all_abnormal.items())
    for i, (name, entries) in enumerate(items, 1):
        emps = ", ".join(set(e[0] for e in entries))
        print(f"    {i}. {name} - 涉及: {emps}")
    print(f"    0. 返回")

    choice = _input("\n  请选择要解读的指标: ")
    if not choice or choice == "0":
        db.close()
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(items):
            print("  [!] 无效选择")
            db.close()
            _pause()
            return
    except ValueError:
        print("  [!] 请输入数字")
        db.close()
        _pause()
        return

    ind_name, entries = items[idx]
    emp_name, ind_info = entries[0]

    print(f"\n  正在解读: {ind_name}")
    print(f"  员工: {emp_name}, 值: {ind_info.get('value')} {ind_info.get('unit', '')}")
    print(f"  参考范围: {ind_info.get('ref_range', '未知')}")
    print(f"  模式: {'详细' if detailed else '简略'}")
    print()

    agent = _get_llm_agent()
    advice = agent.get_advice(
        ind_name,
        ind_info.get("value", 0),
        ind_info.get("ref_range", ""),
        detailed=detailed,
    )

    print(f"  来源: {advice.get('source', '?')}")
    print(f"  概述: {advice.get('summary', '?')}")
    print(f"  风险: {advice.get('risk_level', '?')}")

    if detailed:
        interp = advice.get("interpretation", "")
        if interp:
            print(f"\n  解读: {interp}")
        causes = advice.get("possible_causes", [])
        if causes:
            print("\n  可能原因:")
            for i, c in enumerate(causes, 1):
                print(f"    {i}. {c}")

    print("\n  建议:")
    for i, item in enumerate(advice.get("advice", []), 1):
        print(f"    {i}. {item}")

    if detailed:
        lifestyle = advice.get("lifestyle", [])
        if lifestyle:
            print("\n  生活方式:")
            for i, item in enumerate(lifestyle, 1):
                print(f"    {i}. {item}")
        follow = advice.get("follow_up", "")
        if follow:
            print(f"\n  复查建议: {follow}")
        urgency = advice.get("urgency", "")
        if urgency:
            print(f"  就医建议: {urgency}")

    print(f"\n  知识引用: {advice.get('knowledge_ref', '无')}")

    db.close()
    _pause()


def func_trend_analysis() -> None:
    print_header("趋势分析")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    employees = db.get_all_employees()
    if not employees:
        print("  无员工数据")
        db.close()
        _pause()
        return

    found_any = False
    for emp in employees:
        history = db.get_history(emp["id"])
        if len(history) < 2:
            continue
        latest_indicators = history[-1]["report_data"].get("indicators", {})
        for ind_name in latest_indicators:
            trend = db.check_trend_warning(emp["id"], ind_name)
            if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                if not found_any:
                    found_any = True
                vals_str = " -> ".join(str(v) for v in trend["values"])
                tag = "[!]" if trend["warning"] else "   "
                print(f"  {tag} {emp['name']} - {ind_name}")
                print(f"        值: {vals_str}")
                print(f"        趋势: {trend['trend']}")
                if trend["warning"]:
                    print(f"        预警: {trend['message']}")
                print()

    if not found_any:
        print("  无趋势数据 (需要每位员工至少 2 份报告)")

    db.close()
    _pause()


def func_import_mock() -> None:
    print_header("导入模拟数据")
    print("  将生成 5 名员工 x 3 年的模拟体检数据")
    print()

    if not _confirm("  确认导入?"):
        print("  已取消")
        _pause()
        return

    try:
        from core.database import HealthDatabase
        from utils.mock_data import init_mock_database

        db = HealthDatabase(str(PROJECT_ROOT / "data" / "health_test.db"))
        init_mock_database(db)
        employees = db.get_all_employees()
        print(f"\n  [OK] 导入完成: {len(employees)} 名员工")
        for emp in employees:
            history = db.get_history(emp["id"])
            print(f"    {emp['name']} ({emp['gender']}): {len(history)} 份报告")
        db.close()
    except Exception as e:
        logger.error(f"导入失败: {e}", exc_info=True)
        print(f"  [!] 导入失败: {e}")

    _pause()


def func_reset() -> None:
    print_header("清空数据库")

    if not _db_exists():
        print("  数据库不存在，无需清空")
        _pause()
        return

    import sqlite3
    db_path = PROJECT_ROOT / "data" / "health.db"
    conn = sqlite3.connect(str(db_path))
    emp_count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    rec_count = conn.execute("SELECT COUNT(*) FROM health_records").fetchone()[0]
    conn.close()

    if emp_count == 0 and rec_count == 0:
        print("  数据库已为空")
        _pause()
        return

    print(f"  当前数据: {emp_count} 名员工, {rec_count} 条记录")
    if not _confirm("  确认清空所有数据?"):
        print("  已取消")
        _pause()
        return

    db_path.unlink()
    print("  [OK] 报告数据库已清空，员工账号已保留")
    _pause()


def func_settings() -> None:
    """设置 — LLM 模式选择 + 持久化配置"""
    print_header("设置")

    config = _load_config()

    while True:
        mode_text = "第三方 API" if config["mode"] == "api" else "本地模型"

        print(f"\n  当前模式: {mode_text}")
        print(f"  ----------------------------------------")

        if config["mode"] == "api":
            key_display = "已设置 (" + config["api_key"][:8] + "...)" if config["api_key"] else "未设置"
            print(f"  API Key:  {key_display}")
            print(f"  Base URL: {config['base_url'] or '未设置'}")
            print(f"  Model:    {config['model'] or '未设置'}")
        else:
            print(f"  本地地址:  {config['local_url']}")
            print(f"  模型名称:  {config['model'] or '未指定'}")

        print(f"  ----------------------------------------")
        print()
        print("  1. 切换为: 第三方 API 模式")
        print("  2. 切换为: 本地模型模式 (LM Studio)")
        if config["mode"] == "api":
            print("  3. 设置 API Key")
            print("  4. 设置 Base URL")
            print("  5. 设置 Model")
            print("  6. 测试连接")
        else:
            print("  3. 设置本地地址")
            print("  4. 设置模型名称")
            print("  5. 测试连接")
        print("  0. 返回")

        choice = _input("\n  请选择: ")

        if choice == "1":
            config["mode"] = "api"
            _save_config(config)
            print("  [OK] 已切换为第三方 API 模式")

        elif choice == "2":
            config["mode"] = "local"
            _save_config(config)
            print("  [OK] 已切换为本地模型模式")
            if not config["model"]:
                config["model"] = "qwen2.5-7b-instruct"
                _save_config(config)
                print(f"  [OK] 默认模型: {config['model']}")

        elif choice == "3" and config["mode"] == "api":
            key = _input("  API Key: ")
            if key:
                config["api_key"] = key
                if _save_config(config):
                    print("  [OK] API Key 已加密保存")
                else:
                    print("  [!] 保存失败")

        elif choice == "3" and config["mode"] == "local":
            url = _input(f"  本地地址 (默认 {config['local_url']}): ")
            if url:
                config["local_url"] = url
                _save_config(config)
                print("  [OK] 本地地址已保存")

        elif choice == "4" and config["mode"] == "api":
            url = _input("  Base URL (如 https://api.openai.com/v1): ")
            if url:
                config["base_url"] = url
                _save_config(config)
                print("  [OK] Base URL 已保存")

        elif choice == "4" and config["mode"] == "local":
            m = _input(f"  模型名称 (默认 {config.get('model', 'qwen2.5-7b-instruct')}): ")
            if m:
                config["model"] = m
                _save_config(config)
                print("  [OK] 模型名称已保存")

        elif choice == "5" and config["mode"] == "api":
            m = _input("  Model (如 gpt-4o-mini): ")
            if m:
                config["model"] = m
                _save_config(config)
                print("  [OK] Model 已保存")

        elif (choice == "6" and config["mode"] == "api") or \
             (choice == "5" and config["mode"] == "local"):
            _test_llm_connection(config)

        elif choice == "0":
            break

        _pause()


def _test_llm_connection(config: dict) -> None:
    """测试 LLM 连接"""
    print()
    print("  正在测试连接...")

    try:
        from core.llm_agent import LLMAgent

        if config["mode"] == "api":
            agent = LLMAgent(
                base_url=config["base_url"] or None,
                api_key=config["api_key"] or None,
                model_name=config["model"] or None,
            )
        else:
            agent = LLMAgent(
                base_url=config["local_url"],
                api_key=None,
                model_name=config["model"] or "qwen2.5-7b-instruct",
            )

        if agent.mock_mode:
            print("  [!] 连接失败 — 回退到 Mock 模式")
            print("  请检查:")
            if config["mode"] == "api":
                print("    - API Key 和 Base URL 是否正确")
                print("    - 网络是否可达")
            else:
                print("    - LM Studio 是否已启动")
                print(f"    - 是否已加载模型")
                print(f"    - 地址是否正确: {config['local_url']}")
        else:
            backend = getattr(agent, "backend", "unknown")
            print(f"  [OK] 连接成功!")
            print(f"  后端: {backend}")
            print(f"  模型: {agent.model_name or '默认'}")

            # 快速测试
            print("  正在发送测试请求...")
            advice = agent.get_advice("空腹血糖", 6.5, "3.9-6.1 mmol/L")
            summary = advice.get("summary", "")
            if summary:
                print(f"  [OK] 测试响应: {summary[:60]}...")

    except Exception as e:
        print(f"  [!] 测试失败: {e}")


def func_account_management() -> None:
    print_header("员工账号管理")

    user_db = _get_user_db()
    try:
        synced_count = _sync_all_employee_accounts()
        if synced_count:
            print(f"  [OK] 已同步 {synced_count} 个新账号")

        users = user_db.list_users()
        if not users:
            print("  暂无员工账号")
        else:
            print(f"  {'用户名':<18} {'员工':<10} {'性别':<4} {'状态':<6} {'最近登录':<19}")
            print(f"  {'------':<18} {'----':<10} {'----':<4} {'----':<6} {'--------':<19}")
            for user in users:
                last_login = user.get("last_login_at") or "-"
                status = "启用" if user.get("is_active") else "停用"
                print(
                    f"  {user['username']:<18} {user['employee_name']:<10} {user['gender']:<4} "
                    f"{status:<6} {last_login:<19}"
                )

        print()
        print("  1. 重置账号密码")
        print("  2. 重新同步员工账号")
        print("  3. 登录")
        print("  0. 返回")

        choice = _input("\n  请选择: ")
        if choice == "1":
            username = _input("  用户名: ")
            password = user_db.reset_password(username)
            if password is None:
                print("  [!] 未找到该账号")
            else:
                print(f"  [OK] 密码已重置，初始密码: {password}")
        elif choice == "2":
            synced = _sync_all_employee_accounts()
            print(f"  [OK] 已同步 {synced} 个账号")
        elif choice == "3":
            user = func_auth_prompt()
            if user:
                print(f"  当前登录: {user['employee_name']}")
    finally:
        user_db.close()

    _pause()


# ======================================================================
#  主菜单
# ======================================================================

def main():
    current_user = None
    if _db_exists():
        _sync_all_employee_accounts()
    current_user = func_auth_prompt()

    while True:
        print("\n" + "=" * 50)
        print("  E-Health Agent  体检报告智能解读系统")
        if current_user:
            print(f"  当前登录: {current_user['employee_name']} ({current_user['username']})")
        print("=" * 50)

        _show_status()

        print()
        print("  +---- 功能菜单 ----+")
        print("  | 1. 系统总览       |")
        print("  | 2. 员工列表       |")
        print("  | 3. 查询员工详情   |")
        print("  | 4. 添加报告       |")
        print("  | 5. LLM 指标解读   |")
        print("  | 6. 趋势分析       |")
        print("  | 7. 导入模拟数据   |")
        print("  | 8. 清空数据库     |")
        print("  | 9. 设置           |")
        print("  | 10. 员工账号      |")
        print("  | 0. 退出           |")
        print("  +------------------+")

        choice = _input("\n  请选择 [0-10]: ")

        if choice == "1":
            func_overview()
        elif choice == "2":
            func_employee_list()
        elif choice == "3":
            func_employee_detail()
        elif choice == "4":
            func_add_report()
        elif choice == "5":
            func_llm_interpret()
        elif choice == "6":
            func_trend_analysis()
        elif choice == "7":
            func_import_mock()
        elif choice == "8":
            func_reset()
        elif choice == "9":
            func_settings()
        elif choice == "10":
            func_account_management()
        elif choice == "0":
            print("\n  再见!")
            break
        else:
            print("  [!] 无效选择，请输入 0-10")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  已退出")
        sys.exit(0)
