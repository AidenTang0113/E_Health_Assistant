"""
E-Health Agent CLI 测试入口
支持 --test ocr/parse/database/llm/full 参数

用法:
    python cli_demo.py --test ocr --image report.jpg
    python cli_demo.py --test parse
    python cli_demo.py --test database
    python cli_demo.py --test llm
    python cli_demo.py --test full
    python cli_demo.py --test full --image report.jpg
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


def test_llm() -> None:
    """测试 LLM 智能解读"""
    print_section("LLM 智能解读测试")

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
        advice = agent.get_advice(indicator, value, ref)
        print(f"  来源: {advice.get('source', '?')}")
        print(f"  概述: {advice.get('summary', '?')}")
        print(f"  风险: {advice.get('risk_level', '?')}")
        print(f"  建议:")
        for i, item in enumerate(advice.get("advice", []), 1):
            print(f"    {i}. {item}")
        print(f"  知识引用: {advice.get('knowledge_ref', '无')}")


def test_full(image_path: str = None) -> None:
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

    # Step 2: 解析
    print("\n>>> Step 2: 报告解析")
    parser = ReportParser()
    report_data = parser.parse(ocr_lines)
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
        advice = agent.get_advice(name, info["value"], info.get("ref_range", ""))
        print(f"    概述: {advice.get('summary', '?')}")
        print(f"    风险: {advice.get('risk_level', '?')}")
        for i, item in enumerate(advice.get("advice", []), 1):
            print(f"      {i}. {item}")

    emp_count = len(db.get_all_employees())
    db.close()

    # 总结
    print_section("测试完成")
    print(f"  数据库: {db_path}")
    print(f"  员工数: {emp_count}")
    print(f"  异常指标: {len(abnormal)} 项")
    print(f"  LLM 模式: {'Mock' if agent.mock_mode else 'LLM'}")



def test_batch(batch_dir: str = None, api_key: str = None, base_url: str = None, model: str = None) -> None:
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
    from utils.mock_data import init_mock_database

    engine = OCREngine()
    parser = ReportParser()
    db_path = PROJECT_ROOT / "data" / "health.db"
    db = HealthDatabase(str(db_path))

    # 首次运行导入历史模拟数据作为趋势对比基准
    if len(db.get_all_employees()) == 0:
        print("\n首次运行，导入历史模拟数据...")
        init_mock_database(db)

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

            # Step 2: 解析
            print("  [2] 解析报告中...")
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
                    print("  [5] LLM 解读异常指标...")
                    for ind_name, ind_info in abnormal.items():
                        advice = agent.get_advice(
                            ind_name, ind_info["value"],
                            f"{ind_info.get('ref_range', '')} {ind_info.get('unit', '')}"
                        )
                        print(f"      [{ind_name}] {advice.get('summary', '?')}")
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

使用 OpenAI API 测试:
  set OPENAI_API_KEY=sk-xxx
  python cli_demo.py --test llm

  或直接传入:
  python cli_demo.py --test llm --api-key sk-xxx
        """,
    )
    parser.add_argument(
        "--test",
        choices=["ocr", "parse", "database", "llm", "full", "batch"],
        default="full",
        help="测试模块 (默认: full)",
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

    args = parser.parse_args()

    # 将命令行参数同步到环境变量，供 LLMAgent 读取
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["LLM_BASE_URL"] = args.base_url
    if args.model:
        os.environ["LLM_MODEL"] = args.model

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

    try:
        if args.test == "ocr":
            test_ocr(image_path=args.image, pdf_path=args.pdf)
        elif args.test == "parse":
            test_parse(use_mock=args.mock, image_path=args.image)
        elif args.test == "database":
            test_database()
        elif args.test == "llm":
            test_llm()
        elif args.test == "full":
            test_full(image_path=args.image)
        elif args.test == "batch":
            test_batch(
                batch_dir=args.batch_dir,
                api_key=args.api_key,
                base_url=args.base_url,
                model=args.model,
            )
    except KeyboardInterrupt:
        print("\n\n[!] 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
