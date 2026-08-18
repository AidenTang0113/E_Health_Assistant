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


def func_my_profile(current_user: dict) -> None:
    """员工查看自己的档案及账号设置。"""
    username = current_user["username"]
    user_db = _get_user_db()

    while True:
        print_header("我的档案")
        print(f"  用户名: {username}")
        print(f"  姓名: {current_user.get('employee_name', '-')}")
        print(f"  角色: {current_user.get('role', '-')}")
        birth = current_user.get("birth_year")
        print(f"  出生年份: {birth if birth else '-'}")

        print()
        print("  +--- 我的菜单 ---+")
        print("  | 1. 查看健康档案  |")
        print("  | 2. 账号设置      |")
        print("  | 0. 返回          |")
        print("  +-----------------+")
        choice = _input("\n  请选择 [0-2]: ")

        # ---- 1. 查看健康档案 ----
        if choice == "1":
            _my_health_profile(current_user)

        # ---- 2. 账号设置 ----
        elif choice == "2":
            _my_account_settings(username, current_user)

        elif choice == "0":
            break
        else:
            print("  [!] 无效选择，请输入 0-2")

    user_db.close()


def _my_health_profile(current_user: dict) -> None:
    """查看健康档案。"""
    employee_id = current_user.get("employee_id")
    if not employee_id:
        print("  当前账号未关联员工档案")
        _pause()
        return

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    employee = db.get_employee(employee_id)
    if not employee:
        print("  未找到员工档案")
        db.close()
        _pause()
        return

    history = db.get_history(employee_id)
    print(f"\n  员工: {employee['name']} ({employee['gender']})  ID: {employee['id']}")
    if employee.get("birth_year"):
        print(f"  出生年份: {employee['birth_year']}")
    print(f"  报告数: {len(history)}")

    if not history:
        print("  暂无体检报告")
        db.close()
        _pause()
        return

    latest = history[-1]
    indicators = latest["report_data"].get("indicators", {})
    abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}

    print(f"\n  最新报告: {latest['report_date']}")
    print(f"  指标: {len(indicators)} 项, 异常: {len(abnormal)} 项")
    for name, info in abnormal.items():
        print(f"    [!] {name}: {info.get('value', '?')} {info.get('unit', '')}")

    db.close()
    _pause()


def _my_account_settings(username: str, current_user: dict) -> None:
    """员工修改自己的账号信息。"""
    print_header("账号设置")
    print("  1. 修改用户名")
    print("  2. 修改密码")
    print("  3. 修改出生年份")
    print("  0. 返回")

    choice = _input("\n  请选择 [0-3]: ")
    user_db = _get_user_db()
    try:
        if choice == "1":
            new_name = _input("  新用户名: ").strip()
            if not new_name:
                print("  [!] 用户名不能为空")
            else:
                ok, msg = user_db.update_user_profile(username, new_username=new_name)
                print(f"  {'[OK]' if ok else '[!]'} {msg}")
                if ok:
                    current_user["username"] = new_name
                    username = new_name

        elif choice == "2":
            old_pw = _input("  旧密码: ")
            new_pw = _input("  新密码: ")
            if not new_pw:
                print("  [!] 新密码不能为空")
            else:
                ok, msg = user_db.update_user_profile(
                    username, old_password=old_pw, new_password=new_pw
                )
                print(f"  {'[OK]' if ok else '[!]'} {msg}")

        elif choice == "3":
            by_str = _input("  出生年份 (直接回车跳过): ").strip()
            if by_str:
                try:
                    birth_year = int(by_str)
                    ok, msg = user_db.update_user_profile(username, birth_year=birth_year)
                    print(f"  {'[OK]' if ok else '[!]'} {msg}")
                    if ok:
                        current_user["birth_year"] = birth_year
                except ValueError:
                    print("  [!] 请输入有效年份")
            else:
                print("  已跳过")

        elif choice == "0":
            return
        else:
            print("  [!] 无效选择")
    finally:
        user_db.close()

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


def func_reset() -> None:
    print_header("清空数据库")

    if not _db_exists():
        print("  数据库不存在，无需清空")
        _pause()
        return

    import sqlite3
    db_path = PROJECT_ROOT / "data" / "health.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    emp_count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    rec_count = conn.execute("SELECT COUNT(*) FROM health_records").fetchone()[0]

    if emp_count == 0 and rec_count == 0:
        print("  数据库已为空")
        conn.close()
        _pause()
        return

    print(f"  当前数据: {emp_count} 名员工, {rec_count} 条记录")
    if not _confirm("  确认清空所有数据?"):
        print("  已取消")
        conn.close()
        _pause()
        return

    conn.execute("DELETE FROM health_records")
    conn.execute("DELETE FROM employees")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('employees', 'health_records')")
    conn.commit()
    conn.close()
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
            print("  7. 清空数据库")
        else:
            print("  3. 设置本地地址")
            print("  4. 设置模型名称")
            print("  5. 测试连接")
            print("  6. 清空数据库")
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

        elif (choice == "7" and config["mode"] == "api") or \
             (choice == "6" and config["mode"] == "local"):
            func_reset()

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


def func_manager_management(user_db) -> None:
    while True:
        print_header("经理管理")
        managers = user_db.list_users_by_role("manager")
        if managers:
            print("  当前经理:")
            for manager in managers:
                print(f"    - {manager['employee_name']} ({manager['username']})")
        else:
            print("  当前没有经理账号")

        print()
        print("  1. 添加经理")
        print("  2. 移除经理")
        print("  0. 返回")
        choice = _input("\n  请选择: ")

        if choice == "0":
            return
        if choice == "1":
            name = _input("  姓名: ")
            try:
                promoted = user_db.promote_employee_to_manager(name)
                if promoted:
                    print(
                        f"  [OK] 已将员工提升为经理: "
                        f"{promoted['employee_name']} ({promoted['username']})"
                    )
                else:
                    username = _input("  用户名: ")
                    password = _input("  密码: ")
                    user, _ = user_db.create_manager_account(name, username, password)
                    print(f"  [OK] 已创建经理账号: {user['username']}")
            except Exception as exc:
                print(f"  [!] 添加失败: {exc}")
            _pause()
        elif choice == "2":
            name = _input("  经理姓名: ")
            removed = user_db.demote_manager_by_name(name)
            if removed:
                print(f"  [OK] 已移除经理权限: {removed['employee_name']}")
            else:
                print("  [!] 未找到该经理")
            _pause()
        else:
            print("  [!] 无效选择")


def func_account_management(current_user: dict | None = None) -> None:
    """员工账号管理：增删改查 + 软删除/硬删除 + 审计日志。"""
    operator = current_user["username"] if current_user else "system"

    while True:
        print_header("员工账号管理")

        user_db = _get_user_db()
        try:
            users = user_db.list_users()
            if not users:
                print("  暂无员工账号")
            else:
                print(f"  {'用户名':<18} {'角色':<8} {'员工':<10} {'状态':<6} {'最近登录':<19}")
                print(f"  {'------':<18} {'----':<8} {'----':<10} {'----':<6} {'--------':<19}")
                for user in users:
                    last_login = user.get("last_login_at") or "-"
                    status = "启用" if user.get("is_active") else "停用"
                    print(
                        f"  {user['username']:<18} {user.get('role', 'employee'):<8} "
                        f"{user['employee_name']:<10} {status:<6} {last_login:<19}"
                    )

            print()
            print("  +---- 账号管理 ----+")
            print("  | 1. 重置密码       |")
            print("  | 2. 停用账号       |")
            print("  | 3. 启用账号       |")
            print("  | 4. 硬删除用户     |")
            print("  | 5. 清空所有员工   |")
            print("  | 6. 重新同步账号   |")
            print("  | 7. 经理管理       |")
            print("  | 8. 操作日志       |")
            print("  | 0. 返回           |")
            print("  +-------------------+")

            choice = _input("\n  请选择 [0-8]: ")
            if choice == "0":
                return

            # ---- 1. 重置密码 ----
            elif choice == "1":
                username = _input("  用户名: ").strip()
                password = user_db.reset_password(username, operator=operator)
                if password is None:
                    print("  [!] 未找到该账号")
                else:
                    print(f"  [OK] 密码已重置，初始密码: {password}")

            # ---- 2. 停用账号（软删除） ----
            elif choice == "2":
                username = _input("  用户名: ").strip()
                if not _confirm("  确认停用该账号? (账号将无法登录，档案保留)"):
                    print("  已取消")
                elif user_db.deactivate_user(username, operator=operator):
                    print("  [OK] 账号已停用，健康档案已保留")
                else:
                    print("  [!] 停用失败（账号不存在/已是停用状态/管理员不可停用）")

            # ---- 3. 启用账号 ----
            elif choice == "3":
                username = _input("  用户名: ").strip()
                if user_db.reactivate_user(username, operator=operator):
                    print("  [OK] 账号已启用")
                else:
                    print("  [!] 启用失败（账号不存在/已启用）")

            # ---- 4. 硬删除用户 ----
            elif choice == "4":
                username = _input("  用户名: ").strip()
                user = user_db.get_user(username)
                if not user:
                    print("  [!] 未找到该账号")
                elif user.get("role") == "HR":
                    print("  [!] 管理员账号不可删除")
                else:
                    print(f"  用户: {user['employee_name']} ({username})")
                    print(f"  角色: {user.get('role', '-')}")
                    print()
                    print("  删除选项:")
                    print("    1. 仅删除账号（保留健康档案）")
                    print("    2. 删除账号 + 健康档案")
                    print("    0. 取消")
                    sub = _input("\n  请选择: ")
                    if sub == "1":
                        if not _confirm("  确认硬删除账号? 此操作不可逆!"):
                            print("  已取消")
                        elif user_db.delete_user(username, delete_records=False, operator=operator):
                            print("  [OK] 账号已删除，健康档案已保留")
                        else:
                            print("  [!] 删除失败")
                    elif sub == "2":
                        if not _confirm("  确认删除账号及全部健康档案? 此操作不可逆!"):
                            print("  已取消")
                        else:
                            health_db = _get_db()
                            try:
                                if user_db.delete_user(
                                    username, delete_records=True,
                                    health_db=health_db, operator=operator,
                                ):
                                    print("  [OK] 账号及健康档案已彻底删除")
                                else:
                                    print("  [!] 删除失败")
                            finally:
                                health_db.close()
                    else:
                        print("  已取消")

            # ---- 5. 清空所有员工用户 ----
            elif choice == "5":
                if not _confirm("  确认清空所有员工用户? 管理员账号保留"):
                    print("  已取消")
                else:
                    removed = user_db.delete_all_users(keep_admin=True)
                    user_db._log_action("delete_all_users", "all_employees", operator)
                    print(f"  [OK] 已删除 {removed} 个员工用户")

            # ---- 6. 重新同步员工账号 ----
            elif choice == "6":
                synced = _sync_all_employee_accounts()
                print(f"  [OK] 已同步 {synced} 个账号")

            # ---- 7. 经理管理 ----
            elif choice == "7":
                func_manager_management(user_db)

            # ---- 8. 操作日志 ----
            elif choice == "8":
                logs = user_db.list_audit_logs(limit=30)
                if not logs:
                    print("  暂无操作记录")
                else:
                    print(f"  {'时间':<19} {'操作':<18} {'目标':<16} {'操作人':<10}")
                    print(f"  {'----':<19} {'------':<18} {'------':<16} {'------':<10}")
                    for log in logs:
                        print(
                            f"  {log['created_at']:<19} {log['action']:<18} "
                            f"{log['target']:<16} {log['operator']:<10}"
                        )
                        if log.get("detail"):
                            print(f"    └ {log['detail']}")
            else:
                print("  [!] 无效选择")
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
    role = current_user.get("role") if current_user else None

    while True:
        print("\n" + "=" * 50)
        print("  E-Health Agent  体检报告智能解读系统")
        if current_user:
            print(
                f"  当前登录: {current_user['employee_name']} "
                f"({current_user['username']}) [{role}]"
            )
        print("=" * 50)

        _show_status()

        # 统一主菜单：HR 与经理结构相同，权限通过子菜单区分
        print()
        print("  +---- 主菜单 ----+")
        print("  | 1. 总览          |")
        print("  | 2. 员工管理      |")
        print("  | 3. 报告管理      |")
        print("  | 4. 健康分析      |")
        print("  | 5. 系统设置      |")
        print("  | 0. 退出          |")
        print("  +-----------------+")

        choice = _input("\n  请选择 [0-5]: ")

        # ---- 1. 总览 ----
        if choice == "1":
            func_overview()

        # ---- 2. 员工管理 ----
        elif choice == "2":
            print()
            print("  +---- 员工管理 ----+")
            print("  | 1. 员工列表      |")
            print("  | 2. 查询详情      |")
            print("  | 0. 返回          |")
            print("  +------------------+")
            sub = _input("\n  请选择 [0-2]: ")
            if sub == "1":
                func_employee_list()
            elif sub == "2":
                func_employee_detail()
            elif sub == "0":
                pass
            else:
                print("  [!] 无效选择")
            _pause()

        # ---- 3. 报告管理 ----
        elif choice == "3":
            print()
            print("  +---- 报告管理 ----+")
            print("  | 1. 添加报告      |")
            print("  | 2. 批量导入      |")
            print("  | 0. 返回          |")
            print("  +------------------+")
            sub = _input("\n  请选择 [0-2]: ")
            if sub == "1":
                func_add_report()
            elif sub == "2":
                _import_batch()
            elif sub == "0":
                pass
            else:
                print("  [!] 无效选择")
            _pause()

        # ---- 4. 健康分析 ----
        elif choice == "4":
            print()
            print("  +---- 健康分析 ----+")
            print("  | 1. 指标解读      |")
            print("  | 2. 趋势分析      |")
            print("  | 0. 返回          |")
            print("  +------------------+")
            sub = _input("\n  请选择 [0-2]: ")
            if sub == "1":
                func_llm_interpret()
            elif sub == "2":
                func_trend_analysis()
            elif sub == "0":
                pass
            else:
                print("  [!] 无效选择")
            _pause()

        # ---- 5. 系统设置 ----
        elif choice == "5":
            # 员工只能看自己的档案
            if role == "employee":
                func_my_profile(current_user)
            else:
                print()
                print("  +---- 系统设置 ----+")
                print("  | 1. LLM 配置      |")
                print("  | 2. 员工账号      |")
                if role == "HR":
                    print("  | 3. 经理管理      |")
                    print("  | 4. 清空数据库    |")
                    print("  | 0. 返回          |")
                    print("  +------------------+")
                    sub = _input("\n  请选择 [0-4]: ")
                    if sub == "1":
                        func_settings()
                    elif sub == "2":
                        func_account_management(current_user)
                    elif sub == "3":
                        user_db = _get_user_db()
                        try:
                            func_manager_management(user_db)
                        finally:
                            user_db.close()
                    elif sub == "4":
                        func_reset()
                    elif sub == "0":
                        pass
                    else:
                        print("  [!] 无效选择")
                else:
                    print("  | 0. 返回          |")
                    print("  +------------------+")
                    sub = _input("\n  请选择 [0-2]: ")
                    if sub == "1":
                        func_settings()
                    elif sub == "2":
                        func_account_management(current_user)
                    elif sub == "0":
                        pass
                    else:
                        print("  [!] 无效选择")
            _pause()

        elif choice == "0":
            print("\n  再见!")
            break

        else:
            print("  [!] 无效选择，请输入 0-5")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  已退出")
        sys.exit(0)
