"""
模拟数据生成模块 — 5个员工 × 3年体检数据
用于开发和测试阶段，无需真实报告即可验证全部功能
部分指标呈逐年上升趋势，用于测试趋势预警
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ======================================================================
#  5个员工的模拟数据（2022-2024，连续3年）
#  设计要点:
#  - 张三：血糖逐年上升（趋势预警测试）
#  - 李四：肝功能指标偏高且持续（异常监测测试）
#  - 王五：基本正常（对照组）
#  - 赵六：血脂异常 + 尿酸高（多指标异常测试）
#  - 陈七：贫血指标偏低 + 逐年下降（下降趋势测试）
# ======================================================================

MOCK_EMPLOYEES: List[Dict[str, Any]] = [
    {"name": "张三", "gender": "男", "birth_year": 1985},
    {"name": "李四", "gender": "男", "birth_year": 1978},
    {"name": "王五", "gender": "女", "birth_year": 1990},
    {"name": "赵六", "gender": "男", "birth_year": 1982},
    {"name": "陈七", "gender": "女", "birth_year": 1995},
]


def _make_indicator(value: float, unit: str, status: str, abnormal_type: str = None, ref_range: str = "") -> Dict[str, Any]:
    """快捷构建指标字典"""
    return {
        "value": value,
        "unit": unit,
        "status": status,
        "abnormal_type": abnormal_type,
        "ref_range": ref_range,
    }


# ======================================================================
#  各年度体检报告数据
# ======================================================================

def get_mock_reports() -> Dict[str, List[Dict[str, Any]]]:
    """
    获取所有员工的模拟体检报告（3年）

    Returns:
        {员工姓名: [2022年报告, 2023年报告, 2024年报告], ...}
    """
    return {
        # ====================================================================
        #  张三：空腹血糖逐年上升（5.2 → 5.8 → 6.5），2024年异常
        # ====================================================================
        "张三": [
            {
                "name": "张三", "gender": "男", "age": 37, "report_date": "2022-06-15",
                "indicators": {
                    "空腹血糖": _make_indicator(5.2, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(25, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(4.5, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(1.2, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "肌酐": _make_indicator(82, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "尿酸": _make_indicator(350, "μmol/L", "normal", None, "149-416 μmol/L"),
                    "血红蛋白": _make_indicator(145, "g/L", "normal", None, "115-150 g/L"),
                    "白细胞计数": _make_indicator(6.5, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                },
            },
            {
                "name": "张三", "gender": "男", "age": 38, "report_date": "2023-06-20",
                "indicators": {
                    "空腹血糖": _make_indicator(5.8, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(28, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(4.8, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(1.5, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "肌酐": _make_indicator(85, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "尿酸": _make_indicator(370, "μmol/L", "normal", None, "149-416 μmol/L"),
                    "血红蛋白": _make_indicator(143, "g/L", "normal", None, "115-150 g/L"),
                    "白细胞计数": _make_indicator(6.8, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                },
            },
            {
                "name": "张三", "gender": "男", "age": 39, "report_date": "2024-06-15",
                "indicators": {
                    "空腹血糖": _make_indicator(6.5, "mmol/L", "abnormal", "high", "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(32, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(5.0, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(1.6, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "肌酐": _make_indicator(88, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "尿酸": _make_indicator(390, "μmol/L", "normal", None, "149-416 μmol/L"),
                    "血红蛋白": _make_indicator(142, "g/L", "normal", None, "115-150 g/L"),
                    "白细胞计数": _make_indicator(7.0, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                },
            },
        ],
        # ====================================================================
        #  李四：谷丙转氨酶持续偏高（55 → 62 → 68）
        # ====================================================================
        "李四": [
            {
                "name": "李四", "gender": "男", "age": 44, "report_date": "2022-05-10",
                "indicators": {
                    "空腹血糖": _make_indicator(5.5, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(55, "U/L", "abnormal", "high", "0-40 U/L"),
                    "谷草转氨酶": _make_indicator(42, "U/L", "abnormal", "high", "0-40 U/L"),
                    "总胆红素": _make_indicator(15.2, "μmol/L", "normal", None, "3.4-17.1 μmol/L"),
                    "甘油三酯": _make_indicator(2.1, "mmol/L", "abnormal", "high", "0-1.7 mmol/L"),
                    "肌酐": _make_indicator(95, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "尿酸": _make_indicator(420, "μmol/L", "abnormal", "high", "149-416 μmol/L"),
                    "血红蛋白": _make_indicator(148, "g/L", "normal", None, "115-150 g/L"),
                },
            },
            {
                "name": "李四", "gender": "男", "age": 45, "report_date": "2023-05-18",
                "indicators": {
                    "空腹血糖": _make_indicator(5.7, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(62, "U/L", "abnormal", "high", "0-40 U/L"),
                    "谷草转氨酶": _make_indicator(45, "U/L", "abnormal", "high", "0-40 U/L"),
                    "总胆红素": _make_indicator(16.0, "μmol/L", "normal", None, "3.4-17.1 μmol/L"),
                    "甘油三酯": _make_indicator(2.3, "mmol/L", "abnormal", "high", "0-1.7 mmol/L"),
                    "肌酐": _make_indicator(98, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "尿酸": _make_indicator(425, "μmol/L", "abnormal", "high", "149-416 μmol/L"),
                    "血红蛋白": _make_indicator(147, "g/L", "normal", None, "115-150 g/L"),
                },
            },
            {
                "name": "李四", "gender": "男", "age": 46, "report_date": "2024-05-15",
                "indicators": {
                    "空腹血糖": _make_indicator(5.9, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(68, "U/L", "abnormal", "high", "0-40 U/L"),
                    "谷草转氨酶": _make_indicator(48, "U/L", "abnormal", "high", "0-40 U/L"),
                    "总胆红素": _make_indicator(16.8, "μmol/L", "normal", None, "3.4-17.1 μmol/L"),
                    "甘油三酯": _make_indicator(2.5, "mmol/L", "abnormal", "high", "0-1.7 mmol/L"),
                    "肌酐": _make_indicator(100, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "尿酸": _make_indicator(430, "μmol/L", "abnormal", "high", "149-416 μmol/L"),
                    "血红蛋白": _make_indicator(146, "g/L", "normal", None, "115-150 g/L"),
                },
            },
        ],
        # ====================================================================
        #  王五：基本正常（对照组）
        # ====================================================================
        "王五": [
            {
                "name": "王五", "gender": "女", "age": 32, "report_date": "2022-07-01",
                "indicators": {
                    "空腹血糖": _make_indicator(4.8, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(18, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(3.8, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(0.9, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "高密度脂蛋白": _make_indicator(1.5, "mmol/L", "normal", None, ">=1.0 mmol/L"),
                    "肌酐": _make_indicator(62, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "血红蛋白": _make_indicator(128, "g/L", "normal", None, "115-150 g/L"),
                    "白细胞计数": _make_indicator(5.8, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                },
            },
            {
                "name": "王五", "gender": "女", "age": 33, "report_date": "2023-07-05",
                "indicators": {
                    "空腹血糖": _make_indicator(4.9, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(20, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(3.9, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(1.0, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "高密度脂蛋白": _make_indicator(1.6, "mmol/L", "normal", None, ">=1.0 mmol/L"),
                    "肌酐": _make_indicator(64, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "血红蛋白": _make_indicator(130, "g/L", "normal", None, "115-150 g/L"),
                    "白细胞计数": _make_indicator(6.0, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                },
            },
            {
                "name": "王五", "gender": "女", "age": 34, "report_date": "2024-07-01",
                "indicators": {
                    "空腹血糖": _make_indicator(5.0, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(22, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(4.0, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(1.1, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "高密度脂蛋白": _make_indicator(1.55, "mmol/L", "normal", None, ">=1.0 mmol/L"),
                    "肌酐": _make_indicator(66, "μmol/L", "normal", None, "44-133 μmol/L"),
                    "血红蛋白": _make_indicator(132, "g/L", "normal", None, "115-150 g/L"),
                    "白细胞计数": _make_indicator(6.2, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                },
            },
        ],
        # ====================================================================
        #  赵六：血脂异常 + 尿酸高
        # ====================================================================
        "赵六": [
            {
                "name": "赵六", "gender": "男", "age": 40, "report_date": "2022-08-10",
                "indicators": {
                    "空腹血糖": _make_indicator(5.6, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(35, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(5.8, "mmol/L", "abnormal", "high", "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(2.8, "mmol/L", "abnormal", "high", "0-1.7 mmol/L"),
                    "低密度脂蛋白": _make_indicator(3.8, "mmol/L", "abnormal", "high", "0-3.4 mmol/L"),
                    "高密度脂蛋白": _make_indicator(0.9, "mmol/L", "abnormal", "low", ">=1.0 mmol/L"),
                    "尿酸": _make_indicator(450, "μmol/L", "abnormal", "high", "149-416 μmol/L"),
                    "肌酐": _make_indicator(90, "μmol/L", "normal", None, "44-133 μmol/L"),
                },
            },
            {
                "name": "赵六", "gender": "男", "age": 41, "report_date": "2023-08-15",
                "indicators": {
                    "空腹血糖": _make_indicator(5.8, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(38, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(6.0, "mmol/L", "abnormal", "high", "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(3.0, "mmol/L", "abnormal", "high", "0-1.7 mmol/L"),
                    "低密度脂蛋白": _make_indicator(4.0, "mmol/L", "abnormal", "high", "0-3.4 mmol/L"),
                    "高密度脂蛋白": _make_indicator(0.88, "mmol/L", "abnormal", "low", ">=1.0 mmol/L"),
                    "尿酸": _make_indicator(465, "μmol/L", "abnormal", "high", "149-416 μmol/L"),
                    "肌酐": _make_indicator(92, "μmol/L", "normal", None, "44-133 μmol/L"),
                },
            },
            {
                "name": "赵六", "gender": "男", "age": 42, "report_date": "2024-08-10",
                "indicators": {
                    "空腹血糖": _make_indicator(6.0, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(40, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(6.2, "mmol/L", "abnormal", "high", "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(3.2, "mmol/L", "abnormal", "high", "0-1.7 mmol/L"),
                    "低密度脂蛋白": _make_indicator(4.2, "mmol/L", "abnormal", "high", "0-3.4 mmol/L"),
                    "高密度脂蛋白": _make_indicator(0.85, "mmol/L", "abnormal", "low", ">=1.0 mmol/L"),
                    "尿酸": _make_indicator(480, "μmol/L", "abnormal", "high", "149-416 μmol/L"),
                    "肌酐": _make_indicator(95, "μmol/L", "normal", None, "44-133 μmol/L"),
                },
            },
        ],
        # ====================================================================
        #  陈七：血红蛋白逐年下降（125 → 118 → 110），2024年贫血
        # ====================================================================
        "陈七": [
            {
                "name": "陈七", "gender": "女", "age": 27, "report_date": "2022-09-01",
                "indicators": {
                    "空腹血糖": _make_indicator(4.5, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(15, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(3.5, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(0.8, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "血红蛋白": _make_indicator(125, "g/L", "normal", None, "115-150 g/L"),
                    "红细胞计数": _make_indicator(4.2, "10^12/L", "normal", None, "3.8-5.1 10^12/L"),
                    "白细胞计数": _make_indicator(5.5, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                    "肌酐": _make_indicator(58, "μmol/L", "normal", None, "44-133 μmol/L"),
                },
            },
            {
                "name": "陈七", "gender": "女", "age": 28, "report_date": "2023-09-05",
                "indicators": {
                    "空腹血糖": _make_indicator(4.6, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(16, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(3.6, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(0.9, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "血红蛋白": _make_indicator(118, "g/L", "normal", None, "115-150 g/L"),
                    "红细胞计数": _make_indicator(4.0, "10^12/L", "normal", None, "3.8-5.1 10^12/L"),
                    "白细胞计数": _make_indicator(5.6, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                    "肌酐": _make_indicator(60, "μmol/L", "normal", None, "44-133 μmol/L"),
                },
            },
            {
                "name": "陈七", "gender": "女", "age": 29, "report_date": "2024-09-01",
                "indicators": {
                    "空腹血糖": _make_indicator(4.7, "mmol/L", "normal", None, "3.9-6.1 mmol/L"),
                    "谷丙转氨酶": _make_indicator(17, "U/L", "normal", None, "0-40 U/L"),
                    "总胆固醇": _make_indicator(3.7, "mmol/L", "normal", None, "0-5.2 mmol/L"),
                    "甘油三酯": _make_indicator(0.9, "mmol/L", "normal", None, "0-1.7 mmol/L"),
                    "血红蛋白": _make_indicator(110, "g/L", "abnormal", "low", "115-150 g/L"),
                    "红细胞计数": _make_indicator(3.7, "10^12/L", "abnormal", "low", "3.8-5.1 10^12/L"),
                    "白细胞计数": _make_indicator(5.7, "10^9/L", "normal", None, "3.5-9.5 10^9/L"),
                    "肌酐": _make_indicator(62, "μmol/L", "normal", None, "44-133 μmol/L"),
                },
            },
        ],
    }


def init_mock_database(db) -> None:
    """
    将模拟数据导入数据库

    Args:
        db: HealthDatabase 实例
    """
    reports = get_mock_reports()

    for emp_info in MOCK_EMPLOYEES:
        name = emp_info["name"]
        gender = emp_info["gender"]
        birth_year = emp_info["birth_year"]

        # 创建员工
        emp_id = db.get_or_create_employee(name, gender, birth_year)

        # 导入3年报告
        for report in reports.get(name, []):
            db.save_report(emp_id, report)

        logger.info(f"模拟数据导入: {name} (ID={emp_id}), {len(reports.get(name, []))} 份报告")

    logger.info(
        f"模拟数据导入完成: {len(MOCK_EMPLOYEES)} 名员工, "
        f"共 {sum(len(v) for v in reports.values())} 份报告"
    )


def get_mock_ocr_text() -> List[str]:
    """
    生成模拟 OCR 文本行（用于测试 parser，无需真实图片）

    Returns:
        模拟体检报告的 OCR 文本行列表
    """
    return [
        "健康体检报告",
        "姓名：张三    性别：男    年龄：39岁",
        "报告日期：2024-06-15",
        "",
        "检验项目          结果      单位       参考范围",
        "空腹血糖          6.5      mmol/L     3.9-6.1",
        "谷丙转氨酶        32       U/L        0-40",
        "总胆固醇          5.0      mmol/L     0-5.2",
        "甘油三酯          1.6      mmol/L     0-1.7",
        "肌酐              88       μmol/L     44-133",
        "尿酸              390      μmol/L     149-416",
        "血红蛋白          142      g/L        115-150",
        "白细胞计数        7.0      10^9/L     3.5-9.5",
    ]
