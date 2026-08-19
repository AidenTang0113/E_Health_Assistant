from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志：INFO写入文件，WARNING以上才在控制台显示
# 控制台不显示 INFO 级别日志（如"数据库就绪"等），避免干扰 CLI 界面
logger = logging.getLogger("e_health")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()

# 文件日志：INFO 及以上，完整记录
_file_handler = logging.FileHandler(
    str(PROJECT_ROOT / "data" / "app.log"), encoding="utf-8"
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logger.addHandler(_file_handler)

# 控制台日志：仅 WARNING 及以上（ERROR 用红色）
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.WARNING)
_console_handler.setFormatter(
    logging.Formatter("[%(levelname)s] %(message)s")
)
logger.addHandler(_console_handler)

# 子模块 logger 跟随根配置
for _name in ["core.ocr_engine", "core.parser", "core.database",
              "core.llm_agent", "core.config_manager", "core.user_database",
              "utils.mock_data"]:
    _sub = logging.getLogger(_name)
    _sub.handlers.clear()
    _sub.setLevel(logging.INFO)
    _sub.propagate = True  # 传播到 root logger

# root logger 也设为 WARNING（拦截其他库的 INFO 噪音）
logging.getLogger().setLevel(logging.WARNING)


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
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 50)
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


# ======================================================================
#  总体查看
# ======================================================================

def func_global_view() -> None:
    """总体查看子菜单。"""
    while True:
        print_header("总体查看")
        print("  +---- 总体查看 ----+")
        print("  | 1. 全员概览       |")
        print("  | 2. 全员趋势       |")
        print("  | 3. 异常指标解读   |")
        print("  | 0. 返回           |")
        print("  +-------------------+")
        sub = _input("\n  请选择 [0-3]: ")
        if sub == "1":
            func_overview()
        elif sub == "2":
            func_trend_analysis()
        elif sub == "3":
            func_llm_interpret()
        elif sub == "0":
            return
        else:
            print("  [!] 无效选择")
            _pause()


# ======================================================================
#  个人查看
# ======================================================================

def _select_employee(db) -> dict | None:
    """显示员工列表并让用户选择，返回选中的员工字典或 None。"""
    employees = db.get_all_employees()
    if not employees:
        print("  无员工数据")
        return None
    print("  选择员工:")
    for i, emp in enumerate(employees, 1):
        history = db.get_history(emp["id"])
        print(f"    {i}. {emp['name']} ({emp['gender']}, {len(history)}份报告)")
    print(f"    0. 返回")
    choice = _input("\n  请选择: ")
    if not choice or choice == "0":
        return None
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(employees):
            print("  [!] 无效选择")
            return None
    except ValueError:
        print("  [!] 请输入数字")
        return None
    return employees[idx]


def func_personal_view(current_user: dict) -> None:
    """个人查看：选员工后进入子菜单。"""
    role = current_user.get("role", "employee")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()

    # 员工角色跳过选择，直接用自己
    if role == "employee":
        employee_id = current_user.get("employee_id")
        if not employee_id:
            print("  当前账号未关联员工档案")
            db.close()
            _pause()
            return
        employee = db.get_employee(employee_id)
        if not employee:
            print("  未找到员工档案")
            db.close()
            _pause()
            return
    else:
        # HR/经理选择员工
        employee = _select_employee(db)
        if not employee:
            db.close()
            return

    emp_id = employee["id"]
    emp_name = employee["name"]

    while True:
        history = db.get_history(emp_id)
        latest_date = history[-1]["report_date"] if history else "无"
        report_count = len(history)

        print_header(f"个人查看 - {emp_name}")
        print(f"  员工: {emp_name} ({employee['gender']})  ID: {emp_id}")
        if employee.get("birth_year"):
            print(f"  出生年份: {employee['birth_year']}")
        print(f"  报告数: {report_count}  最新: {latest_date}")
        print()
        print("  +---- 个人查看 ----+")
        print("  | 1. 个人档案       |")
        print("  | 2. 个人趋势       |")
        print("  | 3. 指标解读       |")
        print("  | 4. 账号设置       |")
        print("  | 0. 返回           |")
        print("  +-------------------+")
        sub = _input("\n  请选择 [0-4]: ")

        if sub == "1":
            _personal_profile(db, emp_id, employee)
        elif sub == "2":
            _personal_trend(db, emp_id, emp_name)
        elif sub == "3":
            _personal_llm(db, emp_id, emp_name, history)
        elif sub == "4":
            _personal_account(employee, current_user, role)
        elif sub == "0":
            db.close()
            return
        else:
            print("  [!] 无效选择")
            _pause()


def _personal_profile(db, emp_id: int, employee: dict) -> None:
    """个人档案：历史报告 + 最新指标。"""
    history = db.get_history(emp_id)
    if not history:
        print("  暂无体检报告")
        _pause()
        return

    print(f"\n  报告数: {len(history)}")
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
                trend = db.check_trend_warning(emp_id, name)
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
    _pause()


def _personal_trend(db, emp_id: int, emp_name: str) -> None:
    """个人趋势：该员工各项指标历史变化。"""
    history = db.get_history(emp_id)
    if len(history) < 2:
        print("  历史报告不足2份，无法分析趋势")
        _pause()
        return

    found = False
    latest_indicators = history[-1]["report_data"].get("indicators", {})
    for ind_name in latest_indicators:
        trend = db.check_trend_warning(emp_id, ind_name)
        if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
            found = True
            vals_str = " -> ".join(str(v) for v in trend["values"])
            tag = "[!]" if trend["warning"] else "   "
            print(f"  {tag} {ind_name}")
            print(f"        值: {vals_str}")
            print(f"        趋势: {trend['trend']}")
            if trend["warning"]:
                print(f"        预警: {trend['message']}")
            print()
    if not found:
        print("  无趋势数据")
    _pause()


def _personal_llm(db, emp_id: int, emp_name: str, history: list) -> None:
    """个人指标解读：选该员工的某项指标做 LLM 解读。"""
    if not history:
        print("  暂无体检报告")
        _pause()
        return

    latest = history[-1]
    indicators = latest["report_data"].get("indicators", {})
    if not indicators:
        print("  最新报告无指标数据")
        _pause()
        return

    # 列出所有指标（不限于异常）
    print("  解读模式: 1.简略  2.详细")
    mode = _input("\n  请选择 (默认1): ")
    detailed = (mode == "2")

    print(f"\n  指标列表:")
    items = list(indicators.items())
    for i, (name, info) in enumerate(items, 1):
        val = info.get("value", "?")
        unit = info.get("unit", "")
        status = info.get("status", "?")
        tag = "[!]" if status == "abnormal" else "   "
        print(f"    {i}. {tag} {name}: {val} {unit}")
    print(f"    0. 返回")

    choice = _input("\n  请选择要解读的指标: ")
    if not choice or choice == "0":
        return
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(items):
            print("  [!] 无效选择")
            _pause()
            return
    except ValueError:
        print("  [!] 请输入数字")
        _pause()
        return

    ind_name, ind_info = items[idx]
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
    _pause()


def _personal_account(employee: dict, current_user: dict, role: str) -> None:
    """账号设置：按角色显示不同操作。"""
    emp_name = employee["name"]
    emp_id = employee["id"]

    # 查找该员工对应的用户账号
    user_db = _get_user_db()
    users = user_db.list_users()
    target_user = None
    for u in users:
        if u.get("employee_id") == emp_id:
            target_user = u
            break

    while True:
        print_header(f"账号设置 - {emp_name}")
        if target_user:
            print(f"  用户名: {target_user['username']}")
            print(f"  角色: {target_user.get('role', '-')}")
            status = "启用" if target_user.get("is_active") else "停用"
            print(f"  状态: {status}")
            last = target_user.get("last_login_at") or "-"
            print(f"  最近登录: {last}")
        else:
            print(f"  该员工尚未创建账号")

        print()
        print("  +---- 账号设置 ----+")
        # 员工只能改自己的基本信息
        if role == "employee":
            print("  | 1. 修改用户名     |")
            print("  | 2. 修改密码       |")
            print("  | 0. 返回           |")
            print("  +-------------------+")
            sub = _input("\n  请选择 [0-2]: ")
            if sub == "1":
                _do_change_username(target_user, current_user, user_db)
            elif sub == "2":
                _do_change_password(target_user, user_db)
            elif sub == "0":
                user_db.close()
                return
            else:
                print("  [!] 无效选择")
            _pause()
        else:
            # HR/经理 可用的操作
            print("  | 1. 修改用户名     |")
            print("  | 2. 修改密码       |")
            print("  | 3. 重置密码       |")
            if role == "HR":
                print("  | 4. 停用/启用账号  |")
                print("  | 5. 角色管理       |")
                print("  | 6. 删除该员工     |")
            print("  | 0. 返回           |")
            print("  +-------------------+")
            max_choice = "6" if role == "HR" else "3"
            sub = _input(f"\n  请选择 [0-{max_choice}]: ")
            operator = current_user.get("username", "system")

            if sub == "1":
                _do_change_username(target_user, current_user, user_db)
            elif sub == "2":
                _do_change_password(target_user, user_db)
            elif sub == "3":
                _do_reset_password(target_user, user_db, operator)
            elif sub == "4" and role == "HR":
                _do_toggle_active(target_user, user_db, operator)
            elif sub == "5" and role == "HR":
                _do_role_management(target_user, user_db, operator)
            elif sub == "6" and role == "HR":
                _do_delete_employee(target_user, employee, user_db, operator)
                if not target_user:  # 已删除
                    user_db.close()
                    return
            elif sub == "0":
                user_db.close()
                return
            else:
                print("  [!] 无效选择")
            _pause()

            # 刷新 target_user
            if target_user:
                target_user = user_db.get_user(target_user["username"])


def _do_change_username(target_user, current_user, user_db) -> None:
    """修改用户名。"""
    if not target_user:
        print("  [!] 该员工无账号")
        return
    old_name = target_user["username"]
    new_name = _input("  新用户名: ").strip()
    if not new_name:
        print("  [!] 用户名不能为空")
        return
    ok, msg = user_db.update_user_profile(old_name, new_username=new_name)
    print(f"  {'[OK]' if ok else '[!]'} {msg}")
    if ok and current_user.get("username") == old_name:
        current_user["username"] = new_name


def _do_change_password(target_user, user_db) -> None:
    """修改密码（需验证旧密码）。"""
    if not target_user:
        print("  [!] 该员工无账号")
        return
    username = target_user["username"]
    old_pw = _input("  旧密码: ")
    new_pw = _input("  新密码: ")
    if not new_pw:
        print("  [!] 新密码不能为空")
        return
    ok, msg = user_db.update_user_profile(
        username, old_password=old_pw, new_password=new_pw
    )
    print(f"  {'[OK]' if ok else '[!]'} {msg}")


def _do_reset_password(target_user, user_db, operator: str) -> None:
    """重置密码（HR/经理操作，不需旧密码）。"""
    if not target_user:
        print("  [!] 该员工无账号")
        return
    username = target_user["username"]
    if not _confirm(f"  确认重置 {target_user['employee_name']} 的密码?"):
        print("  已取消")
        return
    password = user_db.reset_password(username, operator=operator)
    if password is None:
        print("  [!] 重置失败")
    else:
        print(f"  [OK] 密码已重置，初始密码: {password}")


def _do_toggle_active(target_user, user_db, operator: str) -> None:
    """停用/启用账号。"""
    if not target_user:
        print("  [!] 该员工无账号")
        return
    username = target_user["username"]
    is_active = target_user.get("is_active", 1)
    if is_active:
        if not _confirm(f"  确认停用 {target_user['employee_name']}? (档案保留)"):
            print("  已取消")
            return
        if user_db.deactivate_user(username, operator=operator):
            print("  [OK] 账号已停用")
        else:
            print("  [!] 停用失败")
    else:
        if user_db.reactivate_user(username, operator=operator):
            print("  [OK] 账号已启用")
        else:
            print("  [!] 启用失败")


def _do_role_management(target_user, user_db, operator: str) -> None:
    """角色管理：提升/降级。"""
    if not target_user:
        print("  [!] 该员工无账号")
        return
    current_role = target_user.get("role", "employee")
    print(f"  当前角色: {current_role}")
    if current_role == "employee":
        if _confirm("  确认提升为经理?"):
            result = user_db.promote_employee_to_manager(target_user["employee_name"])
            if result:
                print(f"  [OK] 已提升为经理")
            else:
                print("  [!] 提升失败")
    elif current_role == "manager":
        if _confirm("  确认降级为普通员工?"):
            result = user_db.demote_manager_by_name(target_user["employee_name"])
            if result:
                print(f"  [OK] 已降级为员工")
            else:
                print("  [!] 降级失败")
    else:
        print("  [!] 管理员角色不可更改")


def _do_delete_employee(target_user, employee, user_db, operator: str) -> None:
    """删除员工（连带档案可选）。"""
    emp_name = employee["name"]
    print(f"\n  删除 {emp_name}:")
    print("    1. 仅删除账号（保留健康档案）")
    print("    2. 删除账号 + 健康档案（不可逆）")
    print("    0. 取消")
    sub = _input("\n  请选择: ")
    if sub == "1":
        if not _confirm("  确认删除账号? 档案保留，此操作可逆（重新创建账号即可）"):
            print("  已取消")
            return
        if target_user and user_db.delete_user(
            target_user["username"], delete_records=False, operator=operator
        ):
            print("  [OK] 账号已删除，健康档案已保留")
        else:
            print("  [!] 删除失败")
    elif sub == "2":
        if not _confirm("  确认彻底删除账号及全部健康档案? 此操作不可逆!"):
            print("  已取消")
            return
        health_db = _get_db()
        try:
            if target_user and user_db.delete_user(
                target_user["username"], delete_records=True,
                health_db=health_db, operator=operator,
            ):
                print("  [OK] 账号及健康档案已彻底删除")
            else:
                print("  [!] 删除失败")
        finally:
            health_db.close()
    else:
        print("  已取消")


# ======================================================================
#  报告管理（复用原有函数）
# ======================================================================

# func_add_report 和 _import_batch 保持不变
# func_llm_interpret 保持不变（用于总体查看 > 异常指标解读）
# func_trend_analysis 保持不变（用于总体查看 > 全员趋势）
# func_overview 保持不变（用于总体查看 > 全员概览）


# ======================================================================
#  系统设置（精简）
# ======================================================================

def _self_account_settings(current_user: dict) -> None:
    """修改自己的账号信息（用户名/密码）。"""
    username = current_user.get("username", "")
    print_header("账号设置")
    print(f"  用户名: {username}")
    print(f"  姓名: {current_user.get('employee_name', '-')}")
    print(f"  角色: {current_user.get('role', '-')}")
    print()
    print("  1. 修改用户名")
    print("  2. 修改密码")
    print("  0. 返回")

    choice = _input("\n  请选择 [0-2]: ")
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
        elif choice == "0":
            return
        else:
            print("  [!] 无效选择")
    finally:
        user_db.close()
    _pause()


def func_settings_v2(current_user: dict) -> None:
    """精简后的系统设置：LLM配置 + 清空数据库 + 操作日志。"""
    role = current_user.get("role", "employee")

    while True:
        print_header("系统设置")
        config = _load_config()
        mode_text = "第三方 API" if config["mode"] == "api" else "本地模型"
        print(f"  LLM 模式: {mode_text}")
        if config["mode"] == "api":
            key_display = "已设置" if config["api_key"] else "未设置"
            print(f"  API Key: {key_display}")
            print(f"  Base URL: {config['base_url'] or '未设置'}")
            print(f"  Model: {config.get('api_model', '') or '未设置'}")
        else:
            print(f"  本地地址: {config['local_url']}")
            print(f"  模型名称: {config.get('local_model', '') or '未指定'}")

        print()
        print("  +---- 系统设置 ----+")
        print("  | 1. LLM 配置       |")
        if role == "HR":
            print("  | 2. 清空数据库     |")
            print("  | 3. 操作日志       |")
        print("  | 0. 返回           |")
        print("  +-------------------+")

        max_choice = "3" if role == "HR" else "1"
        sub = _input(f"\n  请选择 [0-{max_choice}]: ")

        if sub == "1":
            func_settings()  # 原有 LLM 配置函数
        elif sub == "2" and role == "HR":
            func_reset(current_user)
        elif sub == "3" and role == "HR":
            _show_audit_logs()
        elif sub == "0":
            return
        else:
            print("  [!] 无效选择")
        _pause()


def _show_audit_logs() -> None:
    """查看操作审计日志。"""
    user_db = _get_user_db()
    try:
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
    finally:
        user_db.close()


# ======================================================================
#  报告管理（原有函数）
# ======================================================================

def func_add_report() -> None:
    """手动添加或 OCR 导入体检报告。"""
    print_header("添加报告")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    try:
        employees = db.get_all_employees()
        if not employees:
            print("  无员工数据，请先导入报告创建员工")
            _pause()
            return

        print("  选择员工:")
        for i, emp in enumerate(employees, 1):
            print(f"    {i}. {emp['name']} ({emp['gender']})")
        print(f"    0. 返回")

        choice = _input("\n  请选择: ")
        if not choice or choice == "0":
            return

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(employees):
                print("  [!] 无效选择")
                _pause()
                return
        except ValueError:
            print("  [!] 请输入数字")
            _pause()
            return

        emp = employees[idx]
        emp_id = emp["id"]

        print(f"\n  选中: {emp['name']} ({emp['gender']})")
        print("  导入方式: 1.OCR识别图片  2.OCR识别PDF  3.手动输入")
        method = _input("\n  请选择 [1-3]: ")

        if method in ("1", "2"):
            _import_single_file(is_pdf=(method == "2"))
        elif method == "3":
            print("\n  --- 手动输入 ---")
            report_date = _input("  报告日期 (YYYY-MM-DD): ")
            hospital = _input("  医院名称: ")
            print("  输入指标 (空行结束):")
            indicators = {}
            while True:
                name = _input("    指标名: ").strip()
                if not name:
                    break
                value_str = _input("    值: ").strip()
                unit = _input("    单位: ").strip()
                ref = _input("    参考范围: ").strip()
                try:
                    value = float(value_str)
                except ValueError:
                    value = value_str
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
            if not indicators:
                print("  [!] 未输入任何指标")
                _pause()
                return
            report_data = {
                "hospital": hospital,
                "indicators": indicators,
            }
            new_id = db.add_report(emp_id, report_date, report_data)
            print(f"\n  [OK] 已添加报告 ID: {new_id}")
        else:
            print("  [!] 无效选择")
    finally:
        db.close()
    _pause()


def _import_single_file(is_pdf: bool = False) -> None:
    """OCR 识别单个图片/PDF 文件并导入。"""
    from core.ocr_engine import OCREngine
    from core.parser import ReportParser

    file_label = "PDF" if is_pdf else "图片"
    file_path = _input(f"\n  请输入{file_label}路径: ").strip().strip('"').strip("'")
    if not file_path or not Path(file_path).exists():
        print(f"  [!] 文件不存在: {file_path}")
        return

    db = _get_db()
    try:
        employees = db.get_all_employees()
        if not employees:
            print("  无员工数据")
            return

        print("  选择员工:")
        for i, emp in enumerate(employees, 1):
            print(f"    {i}. {emp['name']} ({emp['gender']})")
        print(f"    0. 返回")
        choice = _input("\n  请选择: ")
        if not choice or choice == "0":
            return
        try:
            idx = int(choice) - 1
            emp = employees[idx]
        except (ValueError, IndexError):
            print("  [!] 无效选择")
            return

        print(f"\n  正在识别 {file_path} ...")
        ocr = OCREngine()
        texts = ocr.extract(file_path, is_pdf=is_pdf)
        if not texts or not any(t.strip() for t in texts):
            print("  [!] OCR 未识别到文本")
            return

        print(f"  [OK] 识别到 {len([t for t in texts if t.strip()])} 页文本")
        parser = ReportParser()
        report_data = parser.parse(texts)
        if not report_data.get("indicators"):
            print("  [!] 未能解析出指标数据")
            print("  原始文本:")
            for t in texts:
                print(t[:200])
            return

        print(f"  [OK] 解析到 {len(report_data['indicators'])} 项指标")
        report_date = report_data.get("report_date", "")
        if not report_date:
            report_date = _input("  报告日期 (YYYY-MM-DD): ").strip()
        hospital = report_data.get("hospital", "")
        if not hospital:
            hospital = _input("  医院名称: ").strip()
            report_data["hospital"] = hospital

        print(f"\n  日期: {report_date}")
        print(f"  医院: {hospital}")
        print(f"  指标数: {len(report_data['indicators'])}")
        abnormal = {k: v for k, v in report_data["indicators"].items() if v.get("status") == "abnormal"}
        if abnormal:
            print(f"  异常: {len(abnormal)} 项")
            for name, info in abnormal.items():
                print(f"    [!] {name}: {info.get('value')} {info.get('unit', '')}")

        if _confirm("\n  确认导入?"):
            new_id = db.add_report(emp["id"], report_date, report_data)
            print(f"  [OK] 导入成功，报告 ID: {new_id}")
        else:
            print("  已取消")
    finally:
        db.close()


def _import_batch() -> None:
    """批量导入指定目录下的所有报告图片/PDF。"""
    print_header("批量导入")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    dir_path = _input("\n  请输入目录路径: ").strip().strip('"').strip("'")
    if not dir_path or not Path(dir_path).is_dir():
        print(f"  [!] 目录不存在: {dir_path}")
        _pause()
        return

    from core.ocr_engine import OCREngine
    from core.parser import ReportParser

    supported = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.pdf"]
    files = []
    for pattern in supported:
        files.extend(Path(dir_path).glob(pattern))
    if not files:
        print(f"  [!] 未找到支持的文件")
        _pause()
        return

    print(f"  找到 {len(files)} 个文件")
    if not _confirm("  开始导入?"):
        _pause()
        return

    db = _get_db()
    ocr = OCREngine()
    parser = ReportParser()
    success, fail = 0, 0
    try:
        for i, f in enumerate(files, 1):
            print(f"\n  [{i}/{len(files)}] {f.name}")
            is_pdf = f.suffix.lower() == ".pdf"
            try:
                texts = ocr.extract(str(f), is_pdf=is_pdf)
                if not texts or not any(t.strip() for t in texts):
                    print("    [!] OCR 无文本")
                    fail += 1
                    continue
                report_data = parser.parse(texts)
                if not report_data.get("indicators"):
                    print("    [!] 解析无指标")
                    fail += 1
                    continue
                emp_name = report_data.get("employee_name", f.stem)
                emp = db.get_employee_by_name(emp_name)
                if not emp:
                    emp = db.add_employee(emp_name, gender="未知")
                report_date = report_data.get("report_date", "")
                if not report_date:
                    report_date = "未知"
                db.add_report(emp["id"], report_date, report_data)
                ind_count = len(report_data["indicators"])
                print(f"    [OK] {emp_name}: {ind_count} 项指标")
                success += 1
            except Exception as e:
                print(f"    [!] 失败: {e}")
                fail += 1
    finally:
        db.close()

    print(f"\n  导入完成: 成功 {success}, 失败 {fail}")
    _pause()


# ======================================================================
#  LLM 指标解读（原有函数）
# ======================================================================

def func_llm_interpret() -> None:
    """选择异常指标进行 LLM 解读。"""
    print_header("异常指标解读")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    try:
        employees = db.get_all_employees()
        if not employees:
            print("  无员工数据")
            _pause()
            return

        # 汇总所有异常指标
        all_abnormal = {}
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
            print("  所有指标均正常，无需解读")
            _pause()
            return

        print("  异常指标:")
        items = list(all_abnormal.items())
        for i, (name, records) in enumerate(items, 1):
            print(f"    {i}. {name} ({len(records)}人)")
        print(f"    0. 返回")

        choice = _input("\n  请选择要解读的指标: ")
        if not choice or choice == "0":
            return
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(items):
                print("  [!] 无效选择")
                _pause()
                return
        except ValueError:
            print("  [!] 请输入数字")
            _pause()
            return

        ind_name, records = items[idx]
        print(f"\n  解读: {ind_name}")
        print("  解读模式: 1.简略  2.详细")
        mode = _input("\n  请选择 (默认1): ")
        detailed = (mode == "2")

        agent = _get_llm_agent()
        for emp_name, info, report_date in records:
            print(f"\n  --- {emp_name} ({report_date}) ---")
            print(f"  值: {info.get('value')} {info.get('unit', '')}")
            print(f"  参考范围: {info.get('ref_range', '未知')}")
            advice = agent.get_advice(
                ind_name,
                info.get("value", 0),
                info.get("ref_range", ""),
                detailed=detailed,
            )
            print(f"  来源: {advice.get('source', '?')}")
            print(f"  概述: {advice.get('summary', '?')}")
            print(f"  风险: {advice.get('risk_level', '?')}")
            if detailed:
                interp = advice.get("interpretation", "")
                if interp:
                    print(f"  解读: {interp}")
                causes = advice.get("possible_causes", [])
                if causes:
                    print("  可能原因:")
                    for j, c in enumerate(causes, 1):
                        print(f"    {j}. {c}")
            print("  建议:")
            for j, item in enumerate(advice.get("advice", []), 1):
                print(f"    {j}. {item}")
            if detailed:
                lifestyle = advice.get("lifestyle", [])
                if lifestyle:
                    print("  生活方式:")
                    for j, item in enumerate(lifestyle, 1):
                        print(f"    {j}. {item}")
                follow = advice.get("follow_up", "")
                if follow:
                    print(f"  复查: {follow}")
                urgency = advice.get("urgency", "")
                if urgency:
                    print(f"  就医: {urgency}")
            print(f"  知识引用: {advice.get('knowledge_ref', '无')}")
    finally:
        db.close()
    _pause()


# ======================================================================
#  趋势分析（原有函数）
# ======================================================================

def func_trend_analysis() -> None:
    """全员指标趋势分析。"""
    print_header("全员趋势")

    if not _db_exists():
        print("  数据库不存在")
        _pause()
        return

    db = _get_db()
    try:
        employees = db.get_all_employees()
        if not employees:
            print("  无员工数据")
            _pause()
            return

        found = False
        for emp in employees:
            history = db.get_history(emp["id"])
            if len(history) < 2:
                continue
            latest_indicators = history[-1]["report_data"].get("indicators", {})
            for ind_name in latest_indicators:
                trend = db.check_trend_warning(emp["id"], ind_name)
                if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                    if not found:
                        found = True
                    vals_str = " -> ".join(str(v) for v in trend["values"])
                    tag = "[!]" if trend["warning"] else "   "
                    print(f"  {tag} {emp['name']} - {ind_name}")
                    print(f"        值: {vals_str}")
                    print(f"        趋势: {trend['trend']}")
                    if trend["warning"]:
                        print(f"        预警: {trend['message']}")
                    print()
        if not found:
            print("  无趋势数据")
    finally:
        db.close()
    _pause()


# ======================================================================
#  数据库清空（原有函数）
# ======================================================================

def func_reset(current_user: dict) -> None:
    """清空数据库（仅 HR，需密码验证）。"""
    print_header("清空数据库")
    print("  [!] 此操作将删除所有员工和报告数据!")
    print("  [!] 此操作不可逆!")

    # HR 密码验证
    user_db = _get_user_db()
    try:
        username = current_user.get("username", "")
        password = _input("\n  请输入您的密码以验证身份: ").strip()
        if not user_db.authenticate(username, password):
            print("  [!] 密码错误，操作已取消")
            _pause()
            return
    finally:
        user_db.close()

    if not _confirm("\n  确认清空?"):
        print("  已取消")
        _pause()
        return
    confirm_text = _input("  输入 'YES' 确认: ").strip()
    if confirm_text != "YES":
        print("  已取消")
        _pause()
        return
    db = _get_db()
    try:
        db.reset_database()
        print("  [OK] 数据库已清空")
    finally:
        db.close()
    _pause()


# ======================================================================
#  LLM 配置（原有函数）
# ======================================================================

def func_settings() -> None:
    """LLM 配置管理。"""
    config = _load_config()

    while True:
        print_header("LLM 配置")
        mode_text = "第三方 API" if config["mode"] == "api" else "本地模型"
        print(f"  当前模式: {mode_text}")
        if config["mode"] == "api":
            key_display = "已设置" if config["api_key"] else "未设置"
            print(f"  API Key: {key_display}")
            print(f"  Base URL: {config['base_url'] or '未设置'}")
            print(f"  Model: {config.get('api_model', '') or '未设置'}")
        else:
            print(f"  本地地址: {config['local_url']}")
            print(f"  模型名称: {config.get('local_model', '') or '未指定'}")

        print()
        print("  1. 切换模式 (API/本地)")
        print("  2. 配置 API")
        print("  3. 配置本地模型")
        print("  4. 测试连接")
        print("  0. 返回")

        choice = _input("\n  请选择 [0-4]: ")
        if choice == "1":
            config["mode"] = "local" if config["mode"] == "api" else "api"
            _save_config(config)
            print(f"  [OK] 已切换到 {'本地模型' if config['mode'] == 'local' else 'API'} 模式")
        elif choice == "2":
            config["api_key"] = _input("  API Key (直接回车跳过): ").strip() or config.get("api_key", "")
            config["base_url"] = _input("  Base URL (直接回车跳过): ").strip() or config.get("base_url", "")
            config["api_model"] = _input("  模型名称 (直接回车跳过): ").strip() or config.get("api_model", "")
            _save_config(config)
            print("  [OK] API 配置已保存")
        elif choice == "3":
            config["local_url"] = _input("  本地服务地址: ").strip() or config.get("local_url", "")
            config["local_model"] = _input("  模型名称 (直接回车跳过): ").strip() or config.get("local_model", "")
            _save_config(config)
            print("  [OK] 本地配置已保存")
        elif choice == "4":
            _test_llm_connection(config)
        elif choice == "0":
            return
        else:
            print("  [!] 无效选择")
        _pause()


def _test_llm_connection(config: dict) -> None:
    """测试 LLM 连接。"""
    print("\n  正在测试连接...")
    try:
        agent = _get_llm_agent()
        advice = agent.get_advice("血糖", 6.5, "3.9-6.1", detailed=False)
        if advice and advice.get("summary"):
            print("  [OK] 连接成功")
            print(f"  测试结果: {advice.get('summary', '?')[:80]}")
        else:
            print("  [!] 连接成功但返回空结果")
    except Exception as e:
        print(f"  [!] 测试失败: {e}")


# ======================================================================
#  主菜单
# ======================================================================

def main():
    if _db_exists():
        _sync_all_employee_accounts()

    while True:
        current_user = func_auth_prompt()
        if not current_user:
            return
        role = current_user.get("role", "employee")

        # 员工角色默认直接进入个人查看
        if role == "employee":
            func_personal_view(current_user)
            continue  # 退出个人查看后回到登录

        result = _main_loop(current_user, role)
        if result == "switch":
            continue
        break


def _main_loop(current_user: dict, role: str):
    """HR/经理主菜单循环，返回 'switch' 切换账号，否则退出程序"""
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 50)
        print("  E-Health Agent  体检报告智能解读系统")
        print(
            f"  当前登录: {current_user['employee_name']} "
            f"({current_user['username']}) [{role}]"
        )
        print("=" * 50)

        _show_status()

        print()
        print("  +------ 主菜单 ------+")
        print("  | 1. 总体查看        |")
        print("  | 2. 个人查看        |")
        print("  | 3. 报告管理        |")
        print("  | 4. 账号设置        |")
        print("  | 5. 系统设置        |")
        print("  | 6. 退出登录        |")
        print("  | 0. 退出            |")
        print("  +--------------------+")

        choice = _input("\n  请选择 [0-6]: ")

        if choice == "1":
            func_global_view()

        elif choice == "2":
            func_personal_view(current_user)

        elif choice == "3":
            print()
            print("  +---- 报告管理 ----+")
            print("  | 1. 添加报告       |")
            print("  | 2. 批量导入       |")
            print("  | 0. 返回           |")
            print("  +-------------------+")
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

        elif choice == "4":
            _self_account_settings(current_user)

        elif choice == "5":
            func_settings_v2(current_user)

        elif choice == "6":
            print("\n  正在退出当前账号...")
            return "switch"

        elif choice == "0":
            print("\n  再见!")
            break

        else:
            print("  [!] 无效选择，请输入 0-6")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  已退出")
        sys.exit(0)

