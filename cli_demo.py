"""
E-Health Agent CLI
  - 无参数运行: 进入交互式菜单界面
  - 带 --test 参数: 执行原有测试流程

用法:
    python cli_demo.py                          # 交互式菜单
    python cli_demo.py --test ocr --image report.jpg   # 测试模式
    python cli_demo.py --test parse
    python cli_demo.py --test database
    python cli_demo.py --test llm
    python cli_demo.py --test full
    python cli_demo.py --test full --image report.jpg
    python cli_demo.py --test batch --batch-dir ./reports
    python cli_demo.py --test status
    python cli_demo.py --test reset
"""

from __future__ import annotations

import argparse
import json
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
logger = logging.getLogger("cli_demo")


def print_section(title: str) -> None:
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_json(data, indent: int = 2) -> None:
    """格式化打印 JSON"""
    print(json.dumps(data, ensure_ascii=False, indent=indent))


# ======================================================================
#  测试函数
# ======================================================================


def test_ocr(image_path: str = None, pdf_path: str = None) -> None:
    """测试 OCR 文字提取"""
    print_section("OCR 文字提取测试")

    from core.ocr_engine import OCREngine

    engine = OCREngine(use_gpu=False)

    if image_path:
        print(f"输入图片: {image_path}")
        lines = engine.extract_text_from_image(image_path)
    elif pdf_path:
        print(f"输入PDF: {pdf_path}")
        lines = engine.extract_text_from_pdf(pdf_path)
    else:
        print("[!] 未指定图片或PDF文件，跳过 OCR 测试")
        print("  用法: python cli_demo.py --test ocr --image <path>")
        return

    print(f"\n提取到 {len(lines)} 行文字:")
    print("-" * 40)
    for i, line in enumerate(lines, 1):
        print(f"  {i:3d}. {line}")


def test_parse(use_mock: bool = True, image_path: str = None) -> None:
    """测试报告解析"""
    print_section("报告解析测试")

    from core.parser import ReportParser
    from utils.mock_data import get_mock_ocr_text

    parser = ReportParser()

    if image_path:
        # 从真实图片 OCR 后解析
        from core.ocr_engine import OCREngine

        engine = OCREngine()
        ocr_lines = engine.extract_text_from_image(image_path)
    else:
        # 使用模拟 OCR 文本
        print("使用模拟 OCR 文本进行解析测试")
        ocr_lines = get_mock_ocr_text()

    # 纠错演示
    print("\n--- OCR 纠错演示 ---")
    test_text = "总旦红素 17.2 直接旦红素 5.0 白旦白 45"
    corrected = parser.correct_text(test_text)
    print(f"  原始: {test_text}")
    print(f"  纠正: {corrected}")

    # 解析
    print("\n--- 解析结果 ---")
    result = parser.parse(ocr_lines)
    print_json(result)

    # 异常指标汇总
    abnormal = {
        k: v
        for k, v in result.get("indicators", {}).items()
        if v.get("status") == "abnormal"
    }
    print(f"\n异常指标: {len(abnormal)} 项")
    for name, info in abnormal.items():
        print(
            f"  [!] {name}: {info['value']} {info['unit']} "
            f"({info.get('abnormal_type', '?')}, 参考: {info.get('ref_range', '?')})"
        )


def test_database() -> None:
    """测试数据库功能"""
    print_section("数据库功能测试")

    from core.database import HealthDatabase
    from utils.mock_data import init_mock_database, MOCK_EMPLOYEES

    db_path = PROJECT_ROOT / "data" / "health_test.db"
    db = HealthDatabase(str(db_path))

    # 导入模拟数据
    print("\n--- 导入模拟数据 ---")
    init_mock_database(db)

    # 查询所有员工
    print("\n--- 员工列表 ---")
    employees = db.get_all_employees()
    for emp in employees:
        print(f"  ID={emp['id']}, {emp['name']}({emp['gender']}), 出生年份={emp.get('birth_year')}")

    # 查询张三的历史
    print("\n--- 张三的体检历史 ---")
    zhang_san = employees[0]
    history = db.get_history(zhang_san["id"])
    for record in history:
        indicators = record["report_data"].get("indicators", {})
        abnormal_count = sum(
            1 for v in indicators.values() if v.get("status") == "abnormal"
        )
        print(
            f"  {record['report_date']}: {len(indicators)} 项指标, "
            f"{abnormal_count} 项异常"
        )

    # 趋势预警测试
    print("\n--- 趋势预警测试 ---")
    test_cases = [
        (zhang_san["id"], "空腹血糖", "张三-空腹血糖（预期: 上升趋势）"),
        (employees[1]["id"], "谷丙转氨酶", "李四-谷丙转氨酶（预期: 持续异常+上升）"),
        (employees[3]["id"], "尿酸", "赵六-尿酸（预期: 持续异常+上升）"),
        (employees[4]["id"], "血红蛋白", "陈七-血红蛋白（预期: 下降趋势）"),
    ]

    for emp_id, indicator, desc in test_cases:
        print(f"\n  [{desc}]")
        trend = db.check_trend_warning(emp_id, indicator)
        print(f"    历史值: {trend['values']}")
        print(f"    检测日期: {trend['dates']}")
        print(f"    趋势: {trend['trend']}")
        print(f"    预警: {trend['warning']}")
        print(f"    信息: {trend['message']}")

    db.close()
    print(f"\n数据库文件: {db_path}")


def test_llm(detailed: bool = False) -> None:
    """测试 LLM 智能解读"""
    print_section(f"LLM 智能解读测试 ({'详细' if detailed else '简略'}模式)")

    from core.llm_agent import LLMAgent

    # 初始化（自动检测后端: OpenAI API > LM Studio > Mock）
    agent = LLMAgent(
        base_url=os.environ.get("LLM_BASE_URL"),
        mock_mode=False,
        api_key=os.environ.get("OPENAI_API_KEY"),
        model_name=os.environ.get("LLM_MODEL"),
    )
    print(f"模式: {'Mock' if agent.mock_mode else 'LLM'}")

    # 测试用例
    test_cases = [
        ("空腹血糖", 6.5, "3.9-6.1 mmol/L"),
        ("谷丙转氨酶", 68, "0-40 U/L"),
        ("甘油三酯", 3.2, "0-1.7 mmol/L"),
        ("尿酸", 480, "149-416 μmol/L"),
        ("血红蛋白", 110, "115-150 g/L"),
    ]

    for indicator, value, ref in test_cases:
        print(f"\n--- {indicator}: {value} (参考: {ref}) ---")
        advice = agent.get_advice(indicator, value, ref, detailed=detailed)
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
                for i, c in enumerate(causes, 1):
                    print(f"    {i}. {c}")
        print(f"  建议:")
        for i, item in enumerate(advice.get("advice", []), 1):
            print(f"    {i}. {item}")
        if detailed:
            lifestyle = advice.get("lifestyle", [])
            if lifestyle:
                print("  生活方式:")
                for i, item in enumerate(lifestyle, 1):
                    print(f"    {i}. {item}")
            follow = advice.get("follow_up", "")
            if follow:
                print(f"  复查建议: {follow}")
            urgency = advice.get("urgency", "")
            if urgency:
                print(f"  就医建议: {urgency}")
        print(f"  知识引用: {advice.get('knowledge_ref', '无')}")


def test_full(image_path: str = None, mock: bool = False, detailed: bool = False) -> None:
    """完整流程测试: OCR -> 解析 -> 存储 -> 趋势分析 -> LLM解读"""
    print_section("E-Health Agent 完整流程测试")

    # Step 1: OCR
    print("\n>>> Step 1: OCR 文字提取")
    from core.ocr_engine import OCREngine
    from core.parser import ReportParser
    from core.database import HealthDatabase
    from core.llm_agent import LLMAgent
    from utils.mock_data import init_mock_database

    ocr_lines = None
    if image_path:
        engine = OCREngine()
        try:
            ocr_lines = engine.extract_text_from_image(image_path)
            print(f"  OCR 完成: {len(ocr_lines)} 行")
        except Exception as e:
            print(f"  OCR 失败: {e}")
            print("  回退到模拟数据...")
            ocr_lines = None

    if ocr_lines is None:
        from utils.mock_data import get_mock_ocr_text

        ocr_lines = get_mock_ocr_text()
        print(f"  使用模拟 OCR 数据: {len(ocr_lines)} 行")

    # Step 2: 解析（正则 + LLM 辅助）
    print("\n>>> Step 2: 报告解析")
    parser = ReportParser()

    # 初始化 LLM agent 用于辅助解析
    agent_for_parse = LLMAgent(mock_mode=mock)
    if not agent_for_parse.mock_mode:
        report_data = parser.parse_with_llm(ocr_lines, llm_agent=agent_for_parse)
        print(f"  解析方式: {report_data.get('_parse_source', 'regex')}")
    else:
        report_data = parser.parse(ocr_lines)
        print("  解析方式: regex (Mock模式)")

    if detailed:
        print("  解读模式: 详细")

    print(f"  姓名: {report_data.get('name')}")
    print(f"  性别: {report_data.get('gender')}")
    print(f"  年龄: {report_data.get('age')}")
    print(f"  日期: {report_data.get('report_date')}")
    print(f"  指标数: {len(report_data.get('indicators', {}))}")

    abnormal = {
        k: v
        for k, v in report_data.get("indicators", {}).items()
        if v.get("status") == "abnormal"
    }
    print(f"  异常数: {len(abnormal)}")

    # Step 3: 数据库存储
    print("\n>>> Step 3: 数据库存储")
    db_path = PROJECT_ROOT / "data" / "health.db"
    db = HealthDatabase(str(db_path))

    # 先导入历史数据用于趋势对比
    print("  导入历史模拟数据...")
    init_mock_database(db)

    # 保存当前报告
    name = report_data.get("name", "未知")
    gender = report_data.get("gender", "男")
    emp_id = db.get_or_create_employee(name, gender)
    record_id = db.save_report(emp_id, report_data)
    print(f"  员工: {name} (ID={emp_id})")
    print(f"  记录: ID={record_id}")

    # Step 4: 趋势分析
    print("\n>>> Step 4: 趋势分析")
    for indicator_name in report_data.get("indicators", {}):
        trend = db.check_trend_warning(emp_id, indicator_name)
        if trend["trend"] != "insufficient":
            print(
                f"  {indicator_name}: 值={trend['values'][-1]}, "
                f"趋势={trend['trend']}, "
                f"预警={trend['warning'] or '无'}"
            )
            if trend["warning"]:
                print(f"    -> {trend['message']}")

    # Step 5: LLM 解读
    print("\n>>> Step 5: LLM 智能解读")
    agent = LLMAgent(
        mock_mode=False,
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL"),
        model_name=os.environ.get("LLM_MODEL"),
    )
    print(f"  模式: {'Mock' if agent.mock_mode else 'LLM'}")

    # 只解读异常指标
    for name, info in abnormal.items():
        print(f"\n  [{name}: {info['value']} {info['unit']}]")
        advice = agent.get_advice(
            name, info["value"], info.get("ref_range", ""), detailed=detailed
        )
        print(f"    概述: {advice.get('summary', '?')}")
        print(f"    风险: {advice.get('risk_level', '?')}")
        if detailed:
            interp = advice.get("interpretation", "")
            if interp:
                print(f"    解读: {interp}")
            causes = advice.get("possible_causes", [])
            if causes:
                print("    可能原因:")
                for i, c in enumerate(causes, 1):
                    print(f"      {i}. {c}")
        print("    建议:")
        for i, item in enumerate(advice.get("advice", []), 1):
            print(f"      {i}. {item}")
        if detailed:
            lifestyle = advice.get("lifestyle", [])
            if lifestyle:
                print("    生活方式:")
                for i, item in enumerate(lifestyle, 1):
                    print(f"      {i}. {item}")
            follow = advice.get("follow_up", "")
            if follow:
                print(f"    复查建议: {follow}")
            urgency = advice.get("urgency", "")
            if urgency:
                print(f"    就医建议: {urgency}")

    emp_count = len(db.get_all_employees())
    db.close()

    # 总结
    print_section("测试完成")
    print(f"  数据库: {db_path}")
    print(f"  员工数: {emp_count}")
    print(f"  异常指标: {len(abnormal)} 项")
    print(f"  LLM 模式: {'Mock' if agent.mock_mode else 'LLM'}")



def test_batch(batch_dir: str = None, api_key: str = None, base_url: str = None, model: str = None, detailed: bool = False) -> None:
    """批量导入: 扫描目录下所有图片/PDF，逐一 OCR -> 解析 -> 存储"""
    print_section("E-Health Agent 批量导入")

    if not batch_dir:
        print("[!] 未指定批量导入目录")
        print("  用法: python cli_demo.py --test batch --batch-dir <dir>")
        return

    batch_path = Path(batch_dir).resolve()
    if not batch_path.is_dir():
        print(f"[!] 目录不存在: {batch_path}")
        return

    # 扫描支持的文件
    supported_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".pdf"}
    files = sorted(
        f for f in batch_path.iterdir()
        if f.suffix.lower() in supported_exts
    )

    if not files:
        print(f"[!] 目录中无支持的文件: {batch_path}")
        print(f"  支持: {', '.join(sorted(supported_exts))}")
        return

    print(f"扫描目录: {batch_path}")
    print(f"发现文件: {len(files)} 个")
    for f in files:
        print(f"  - {f.name}")

    # 初始化各模块
    from core.ocr_engine import OCREngine
    from core.parser import ReportParser
    from core.database import HealthDatabase
    from core.llm_agent import LLMAgent

    engine = OCREngine()
    parser = ReportParser()
    db_path = PROJECT_ROOT / "data" / "health.db"
    db = HealthDatabase(str(db_path))

    agent = LLMAgent(
        mock_mode=False,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("LLM_BASE_URL"),
        model_name=model or os.environ.get("LLM_MODEL"),
    )

    success = 0
    failed = 0
    results = []

    for idx, file_path in enumerate(files, 1):
        print(f"\n{'='*60}")
        print(f"  [{idx}/{len(files)}] {file_path.name}")
        print(f"{'='*60}")

        try:
            # Step 1: OCR
            print("  [1] OCR 识别中...")
            if file_path.suffix.lower() == ".pdf":
                ocr_lines = engine.extract_text_from_pdf(str(file_path))
            else:
                ocr_lines = engine.extract_text_from_image(str(file_path))
            print(f"      识别到 {len(ocr_lines)} 行")

            # Step 2: 解析（正则 + LLM 辅助）
            print("  [2] 解析报告中...")
            if not agent.mock_mode:
                report_data = parser.parse_with_llm(ocr_lines, llm_agent=agent)
                src = report_data.get("_parse_source", "regex")
                print(f"      解析方式: {src}")
            else:
                report_data = parser.parse(ocr_lines)
            name = report_data.get("name", "未知")
            print(f"      姓名: {name}, 指标: {len(report_data.get('indicators', {}))} 项")

            # Step 3: 存储
            print("  [3] 存储到数据库...")
            gender = report_data.get("gender", "男")
            emp_id = db.get_or_create_employee(name, gender)
            record_id = db.save_report(emp_id, report_data)
            print(f"      员工ID={emp_id}, 记录ID={record_id}")

            # Step 4: 异常指标 + 趋势
            abnormal = {
                k: v for k, v in report_data.get("indicators", {}).items()
                if v.get("status") == "abnormal"
            }

            if abnormal:
                print(f"  [4] 异常指标: {len(abnormal)} 项")
                for ind_name, ind_info in abnormal.items():
                    trend = db.check_trend_warning(emp_id, ind_name)
                    trend_tag = f"趋势={trend['trend']}" if trend["trend"] != "insufficient" else "无历史对比"
                    print(f"      {ind_name}: {ind_info['value']} {ind_info['unit']} ({trend_tag})")

                # Step 5: LLM 解读（仅异常指标）
                if not agent.mock_mode:
                    print(f"  [5] LLM 解读异常指标 ({'详细' if detailed else '简略'})...")
                    for ind_name, ind_info in abnormal.items():
                        advice = agent.get_advice(
                            ind_name, ind_info["value"],
                            f"{ind_info.get('ref_range', '')} {ind_info.get('unit', '')}",
                            detailed=detailed,
                        )
                        print(f"      [{ind_name}] {advice.get('summary', '?')}")
                        if detailed:
                            risk = advice.get("risk_level", "")
                            if risk:
                                print(f"        风险等级: {risk}")
                            interp = advice.get("interpretation", "")
                            if interp:
                                print(f"        解读: {interp}")
                            for i, item in enumerate(advice.get("advice", []), 1):
                                print(f"        建议{i}: {item}")
                            for i, item in enumerate(advice.get("lifestyle", []), 1):
                                print(f"        生活方式{i}: {item}")
                            follow = advice.get("follow_up", "")
                            if follow:
                                print(f"        复查: {follow}")
                            urgency = advice.get("urgency", "")
                            if urgency:
                                print(f"        就医: {urgency}")
                else:
                    print("  [5] LLM Mock 模式，跳过真实解读")
            else:
                print("  [4] 无异常指标")

            success += 1
            results.append({"file": file_path.name, "status": "ok", "name": name, "abnormal": len(abnormal)})

        except Exception as e:
            print(f"  [!] 处理失败: {e}")
            failed += 1
            results.append({"file": file_path.name, "status": "failed", "error": str(e)})

    db.close()

    # 汇总
    print_section("批量导入完成")
    print(f"  总计: {len(files)} 个文件")
    print(f"  成功: {success}")
    print(f"  失败: {failed}")
    print(f"  数据库: {db_path}")
    print(f"  员工数: {len(db.get_all_employees()) if False else '(见上)'}")

    if failed > 0:
        print("\n  失败文件:")
        for r in results:
            if r["status"] == "failed":
                print(f"    - {r['file']}: {r['error']}")

def test_status() -> None:
    """查看系统整体状态：数据库概览、员工健康汇总、异常指标统计"""
    print_section("E-Health Agent 系统状态")

    from core.database import HealthDatabase

    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  数据库不存在，请先导入数据")
        print(f"  预期路径: {db_path}")
        return

    db = HealthDatabase(str(db_path))
    employees = db.get_all_employees()

    if not employees:
        print("  数据库为空，无员工数据")
        print("  请先运行: python cli_demo.py --test batch --batch-dir <dir>")
        db.close()
        return

    # --- 1. 总览 ---
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
    print(f"  | 数据库: {db_path}")
    print(f"  | 员工数: {len(employees)}")
    print(f"  | 报告数: {total_reports}")
    print(f"  | 异常记录: {total_abnormal} 条")
    print(f"  | 异常指标类型: {len(all_abnormal_items)} 种")

    # --- 2. 员工列表 ---
    print()
    print("  +--- 员工列表 ---+")
    print(f"  {'ID':>4}  {'姓名':<8} {'性别':<4} {'报告数':>4}  {'最新体检日期':<12}")
    print(f"  {'----':>4}  {'--------':<8} {'----':<4} {'----':>4}  {'------------':<12}")
    for emp in employees:
        history = db.get_history(emp["id"])
        latest_date = history[-1]["report_date"] if history else "-"
        print(f"  {emp['id']:>4}  {emp['name']:<8} {emp['gender']:<4} {len(history):>4}  {latest_date:<12}")

    # --- 3. 每人健康摘要 ---
    print()
    print("  +--- 健康摘要 ---+")
    for emp in employees:
        history = db.get_history(emp["id"])
        if not history:
            print(f"  {emp['name']}: 无记录")
            continue

        latest = history[-1]
        indicators = latest["report_data"].get("indicators", {})
        abnormal = {k: v for k, v in indicators.items() if v.get("status") == "abnormal"}
        total = len(indicators)

        status_icon = "[*]" if not abnormal else "[!]"
        print(f"\n  {status_icon} {emp['name']} ({emp['gender']}) - {latest['report_date']}")
        print(f"      指标: {total} 项, 异常: {len(abnormal)} 项, 历史报告: {len(history)} 份")

        if abnormal:
            for name, info in abnormal.items():
                val = info.get("value", "?")
                unit = info.get("unit", "")
                atype = info.get("abnormal_type", "?")
                ref = info.get("ref_range", "?")
                print(f"      [!] {name}: {val} {unit} ({atype}, 参考: {ref})")

                # 趋势
                trend = db.check_trend_warning(emp["id"], name)
                if trend["trend"] != "insufficient" and len(trend["values"]) > 1:
                    vals_str = " -> ".join(str(v) for v in trend["values"])
                    print(f"          趋势: {trend['trend']} ({vals_str})")
                    if trend["warning"]:
                        print(f"          预警: {trend['message']}")
        else:
            print(f"      所有指标正常")

    # --- 4. 异常指标排行 ---
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
    print()
    print(f"  数据库连接已关闭")


def test_reset() -> None:
    """清空数据库所有数据"""
    print_section("清空数据库")

    import sqlite3

    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  数据库不存在，无需清空")
        return

    # 先统计要删的数据
    conn = sqlite3.connect(str(db_path))
    emp_count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    rec_count = conn.execute("SELECT COUNT(*) FROM health_records").fetchone()[0]
    conn.close()

    if emp_count == 0 and rec_count == 0:
        print("  数据库已为空，无需清空")
        return

    print(f"  当前数据: {emp_count} 名员工, {rec_count} 条记录")
    print(f"  数据库路径: {db_path}")
    print()
    print("  正在清空...")

    # 直接删除数据库文件，下次运行自动重建
    db_path.unlink()

    print("  [OK] 数据库已清空")
    print()
    print("  提示: 下次运行 batch/full/database 时会自动创建新数据库")


# ======================================================================
#  交互式菜单
# ======================================================================


def _get_llm_agent(detailed: bool = False):
    """获取 LLM Agent 实例（自动检测后端）"""
    from core.llm_agent import LLMAgent

    agent = LLMAgent(
        base_url=os.environ.get("LLM_BASE_URL"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        model_name=os.environ.get("LLM_MODEL"),
    )
    return agent


def _input(prompt: str) -> str:
    """安全 input，处理 Ctrl+C"""
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _pause():
    """暂停，等待用户按回车"""
    _input("\n  按回车键继续...")


def _print_header(title: str):
    """打印菜单页头"""
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def _show_db_status() -> bool:
    """显示数据库状态，返回是否有数据"""
    from core.database import HealthDatabase

    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  [!] 数据库不存在")
        return False

    db = HealthDatabase(str(db_path))
    employees = db.get_all_employees()
    if not employees:
        db.close()
        print("  [!] 数据库为空")
        return False

    total_reports = sum(len(db.get_history(e["id"])) for e in employees)
    print(f"  数据库: {len(employees)} 名员工, {total_reports} 份报告")
    db.close()
    return True


# ----------------------------------------------------------------------
#  菜单页面
# ----------------------------------------------------------------------

def menu_overview():
    """1. 系统总览"""
    _print_header("系统总览")
    if not _show_db_status():
        print("  请先导入数据 (菜单 > 添加报告)")
        _pause()
        return
    print()
    test_status()
    _pause()


def menu_employee_list():
    """2. 员工列表"""
    from core.database import HealthDatabase

    _print_header("员工列表")
    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  [!] 数据库不存在")
        _pause()
        return

    db = HealthDatabase(str(db_path))
    employees = db.get_all_employees()
    if not employees:
        print("  [!] 无员工数据")
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


def menu_employee_detail():
    """3. 查询员工详情"""
    from core.database import HealthDatabase

    _print_header("查询员工详情")
    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  [!] 数据库不存在")
        _pause()
        return

    db = HealthDatabase(str(db_path))
    employees = db.get_all_employees()
    if not employees:
        print("  [!] 无员工数据")
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
        status_icon = "[!]" if abnormal else "[OK]"
        print(f"\n  [{i}] {record['report_date']}  {status_icon}  {len(indicators)}项指标, {len(abnormal)}项异常")

        if i == len(history):
            print("  -- 最新报告 --")
            for name, info in indicators.items():
                val = info.get("value", "?")
                unit = info.get("unit", "")
                status = info.get("status", "?")
                ref = info.get("ref_range", "")
                tag = "[!]" if status == "abnormal" else "   "
                print(f"    {tag} {name}: {val} {unit}  (参考: {ref})")

                # 趋势
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


def menu_add_report():
    """4. 添加报告"""
    _print_header("添加体检报告")
    print("  1. 从图片文件导入 (OCR)")
    print("  2. 从 PDF 文件导入 (OCR)")
    print("  3. 批量导入目录")
    print("  0. 返回")

    choice = _input("\n  请选择: ")
    if choice == "1":
        path = _input("  请输入图片路径: ")
        if not path:
            return
        p = Path(path)
        if not p.exists():
            print(f"  [!] 文件不存在: {path}")
            _pause()
            return
        print(f"\n  正在处理: {p.name}")
        test_full(image_path=str(p), mock=False, detailed=False)
    elif choice == "2":
        path = _input("  请输入 PDF 路径: ")
        if not path:
            return
        p = Path(path)
        if not p.exists():
            print(f"  [!] 文件不存在: {path}")
            _pause()
            return
        print(f"\n  正在处理: {p.name}")
        test_ocr(pdf_path=str(p))
    elif choice == "3":
        d = _input("  请输入目录路径: ")
        if not d:
            return
        p = Path(d)
        if not p.is_dir():
            print(f"  [!] 目录不存在: {d}")
            _pause()
            return
        test_batch(
            batch_dir=str(p),
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("LLM_BASE_URL"),
            model=os.environ.get("LLM_MODEL"),
            detailed=False,
        )
    _pause()


def menu_llm_query():
    """5. LLM 指标解读"""
    from core.database import HealthDatabase

    _print_header("LLM 指标解读")

    # 选择模式
    print("  解读模式:")
    print("    1. 简略模式")
    print("    2. 详细模式")
    mode = _input("\n  请选择 (默认1): ")
    detailed = (mode == "2")

    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  [!] 数据库不存在")
        _pause()
        return

    db = HealthDatabase(str(db_path))
    employees = db.get_all_employees()
    if not employees:
        print("  [!] 无员工数据")
        db.close()
        _pause()
        return

    # 收集所有异常指标
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


def menu_trend_analysis():
    """6. 趋势分析"""
    from core.database import HealthDatabase

    _print_header("趋势分析")
    db_path = PROJECT_ROOT / "data" / "health.db"
    if not db_path.exists():
        print("  [!] 数据库不存在")
        _pause()
        return

    db = HealthDatabase(str(db_path))
    employees = db.get_all_employees()
    if not employees:
        print("  [!] 无员工数据")
        db.close()
        _pause()
        return

    found_any = False
    for emp in employees:
        history = db.get_history(emp["id"])
        if len(history) < 2:
            continue

        # 收集该员工所有指标的趋势
        warnings = []
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


def menu_import_mock():
    """7. 导入模拟数据"""
    _print_header("导入模拟数据")
    print("  将生成 5 名员工 x 3 年的模拟体检数据")
    print("  用于测试趋势分析和数据库功能")
    print()
    confirm = _input("  确认导入? (y/n): ")
    if confirm.lower() != "y":
        print("  已取消")
        _pause()
        return

    test_database()
    _pause()


def menu_reset():
    """8. 清空数据库"""
    _print_header("清空数据库")
    confirm = _input("  确认清空所有数据? (y/n): ")
    if confirm.lower() != "y":
        print("  已取消")
        _pause()
        return
    test_reset()
    _pause()


def menu_settings():
    """9. 设置"""
    _print_header("设置")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "")

    print("  当前配置:")
    print(f"    API Key: {'已设置 (' + api_key[:8] + '...)' if api_key else '未设置'}")
    print(f"    Base URL: {base_url or '未设置'}")
    print(f"    Model: {model or '未设置'}")
    print()
    print("  1. 设置 API Key")
    print("  2. 设置 Base URL")
    print("  3. 设置 Model")
    print("  4. 一键设置 (DeepKey)")
    print("  0. 返回")

    choice = _input("\n  请选择: ")
    if choice == "1":
        key = _input("  API Key: ")
        if key:
            os.environ["OPENAI_API_KEY"] = key
            print("  [OK] API Key 已设置")
    elif choice == "2":
        url = _input("  Base URL: ")
        if url:
            os.environ["LLM_BASE_URL"] = url
            print("  [OK] Base URL 已设置")
    elif choice == "3":
        m = _input("  Model: ")
        if m:
            os.environ["LLM_MODEL"] = m
            print("  [OK] Model 已设置")
    elif choice == "4":
        os.environ["OPENAI_API_KEY"] = "sk-HC5mpYjdOT6MxPgN6so24Zppw4u3RQLtVafLqfFAuvlqlJHe"
        os.environ["LLM_BASE_URL"] = "https://deepkey.top/v1"
        os.environ["LLM_MODEL"] = "gpt-5.4-mini"
        print("  [OK] DeepKey 配置已设置")
    _pause()


# ----------------------------------------------------------------------
#  主菜单循环
# ----------------------------------------------------------------------

def interactive_menu(args):
    """交互式菜单主循环"""
    # 如果命令行传了 api-key/base-url/model，同步到环境变量
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["LLM_BASE_URL"] = args.base_url
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    while True:
        print("\n" + "=" * 50)
        print("  E-Health Agent  体检报告智能解读系统")
        print("=" * 50)

        # 显示数据库状态
        db_ok = _show_db_status()

        # LLM 状态
        api_key = os.environ.get("OPENAI_API_KEY", "")
        llm_status = "已配置" if api_key else "未配置 (Mock)"

        print(f"  LLM: {llm_status}")
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
        print("  | 0. 退出           |")
        print("  +------------------+")

        choice = _input("\n  请选择 [0-9]: ")

        if choice == "1":
            menu_overview()
        elif choice == "2":
            menu_employee_list()
        elif choice == "3":
            menu_employee_detail()
        elif choice == "4":
            menu_add_report()
        elif choice == "5":
            menu_llm_query()
        elif choice == "6":
            menu_trend_analysis()
        elif choice == "7":
            menu_import_mock()
        elif choice == "8":
            menu_reset()
        elif choice == "9":
            menu_settings()
        elif choice == "0":
            print("\n  再见!")
            break
        else:
            print("  [!] 无效选择，请输入 0-9")
            _pause()


# ======================================================================
#  主入口
# ======================================================================


def main():
    parser = argparse.ArgumentParser(
        description="E-Health Agent CLI 测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli_demo.py --test ocr --image report.jpg
  python cli_demo.py --test parse
  python cli_demo.py --test database
  python cli_demo.py --test llm
  python cli_demo.py --test full
  python cli_demo.py --test full --image report.jpg
  python cli_demo.py --test full --mock
  python cli_demo.py --test batch --batch-dir ./reports
  python cli_demo.py --test status
  python cli_demo.py --test reset

使用 OpenAI API 测试:
  set OPENAI_API_KEY=sk-xxx
  python cli_demo.py --test llm

  或直接传入:
  python cli_demo.py --test llm --api-key sk-xxx
        """,
    )
    parser.add_argument(
        "--test",
        choices=["ocr", "parse", "database", "llm", "full", "batch", "status", "reset"],
        default=None,
        help="测试模块 (不指定则进入交互式菜单)",
    )
    parser.add_argument("--image", type=str, help="图片文件路径")
    parser.add_argument("--pdf", type=str, help="PDF文件路径")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="强制使用 Mock 模式（不依赖 LM Studio）",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenAI API Key（也可通过环境变量 OPENAI_API_KEY 设置）",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="自定义 API 地址（默认: OpenAI 或 LM Studio）",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="模型名称（OpenAI: gpt-4o-mini, gpt-4o 等）",
    )
    parser.add_argument(
        "--batch-dir",
        type=str,
        default=None,
        help="批量导入目录路径（扫描目录下所有图片和PDF）",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        default=False,
        help="LLM 详细解读模式（含解读/原因/生活方式/复查建议）",
    )

    args = parser.parse_args()

    # 将命令行参数同步到环境变量，供 LLMAgent 读取
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["LLM_BASE_URL"] = args.base_url
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    # 无 --test 参数时进入交互式菜单
    if args.test is None:
        interactive_menu(args)
        return

    # 以下为原有测试流程
    print("\n" + "[*]" * 30)
    print("  E-Health Agent 核心算法测试")
    print("[*]" * 30)
    print(f"  测试模块: {args.test}")
    print(f"  图片: {args.image or '无'}")
    print(f"  PDF: {args.pdf or '无'}")
    print(f"  Mock: {args.mock}")
    print(f"  API Key: {'已设置' if args.api_key or os.environ.get('OPENAI_API_KEY') else '无'}")
    print(f"  Base URL: {args.base_url or '自动选择'}")
    if args.batch_dir:
        print(f"  批量目录: {args.batch_dir}")
    if args.detailed:
        print("  解读模式: 详细")

    try:
        if args.test == "ocr":
            test_ocr(image_path=args.image, pdf_path=args.pdf)
        elif args.test == "parse":
            test_parse(use_mock=args.mock, image_path=args.image)
        elif args.test == "database":
            test_database()
        elif args.test == "llm":
            test_llm(detailed=args.detailed)
        elif args.test == "full":
            test_full(image_path=args.image, mock=args.mock, detailed=args.detailed)
        elif args.test == "batch":
            test_batch(
                batch_dir=args.batch_dir,
                api_key=args.api_key,
                base_url=args.base_url,
                model=args.model,
                detailed=args.detailed,
            )
        elif args.test == "status":
            test_status()
        elif args.test == "reset":
            test_reset()
    except KeyboardInterrupt:
        print("\n\n[!] 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
