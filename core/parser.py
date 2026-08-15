"""
体检报告解析模块 — OCR 文本纠错 + 结构化解析 + 异常检测
包含 CORRECTION_MAP（OCR 常见错别字映射）和 REFERENCE_RANGES（指标参考范围）
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
#  OCR 纠错映射表
#  覆盖体检报告中常见的 OCR 识别错误
# ======================================================================

CORRECTION_MAP: Dict[str, str] = {
    # 胆红素类
    "总旦红素": "总胆红素",
    "直接旦红素": "直接胆红素",
    "间接旦红素": "间接胆红素",
    "总胆红案": "总胆红素",
    "直胆红案": "直接胆红素",
    # 蛋白类
    "总旦白": "总蛋白",
    "白旦白": "白蛋白",
    "球旦白": "球蛋白",
    "白/球旦白比": "白/球蛋白比",
    "糖化血红旦白": "糖化血红蛋白",
    # 肝功能
    "谷丙转氨酶": "谷丙转氨酶",  # 正确，保留
    "谷草转氨酶": "谷草转氨酶",  # 正确，保留
    "谷丙转氨酶 ALT": "谷丙转氨酶",
    "谷草转氨酶 AST": "谷草转氨酶",
    "r-谷氨酰转肽酶": "γ-谷氨酰转肽酶",
    "r谷氨酰转肽酶": "γ-谷氨酰转肽酶",
    "GGT": "γ-谷氨酰转肽酶",
    # 血糖
    "空腹血粮": "空腹血糖",
    "空腹血糟": "空腹血糖",
    "葡萄糟": "葡萄糖",
    # 血脂
    "甘油三酯": "甘油三酯",  # 正确，保留
    "甘油三脂": "甘油三酯",  # 常见误写
    "总胆固酵": "总胆固醇",
    "低密度脂旦白": "低密度脂蛋白",
    "高密度脂旦白": "高密度脂蛋白",
    # 肾功能
    "肌酥": "肌酐",
    "尿素氮": "尿素氮",  # 正确，保留
    "尿酸": "尿酸",  # 正确，保留
    # 血常规
    "白细胞计数": "白细胞计数",  # 正确，保留
    "红细饱": "红细胞",
    "红细脑计数": "红细胞计数",
    "血红旦白": "血红蛋白",
    "血小板计数": "血小板计数",  # 正确，保留
    # 其他
    "甲胎旦白": "甲胎蛋白",
    "癌胚抗原": "癌胚抗原",  # 正确，保留
    "C反应旦白": "C反应蛋白",
    "超敏C反应旦白": "超敏C反应蛋白",
}


# ======================================================================
#  指标参考范围
#  格式: { 指标名: {"unit": 单位, "low": 下限, "high": 上限, "desc": 描述} }
#  low/high 为 None 表示该方向无界限
# ======================================================================

REFERENCE_RANGES: Dict[str, Dict[str, Any]] = {
    # 肝功能
    "谷丙转氨酶": {
        "unit": "U/L",
        "low": 0,
        "high": 40,
        "desc": "反映肝细胞损伤程度",
    },
    "谷草转氨酶": {
        "unit": "U/L",
        "low": 0,
        "high": 40,
        "desc": "反映肝细胞损伤及心肌损伤",
    },
    "总胆红素": {
        "unit": "μmol/L",
        "low": 3.4,
        "high": 17.1,
        "desc": "反映胆汁代谢及肝功能",
    },
    "直接胆红素": {
        "unit": "μmol/L",
        "low": 0,
        "high": 6.8,
        "desc": "反映胆道排泄功能",
    },
    "间接胆红素": {
        "unit": "μmol/L",
        "low": 1.7,
        "high": 12.2,
        "desc": "反映红细胞破坏及肝脏代谢",
    },
    "总蛋白": {
        "unit": "g/L",
        "low": 60,
        "high": 80,
        "desc": "反映肝脏合成功能及营养状态",
    },
    "白蛋白": {
        "unit": "g/L",
        "low": 35,
        "high": 55,
        "desc": "反映肝脏合成功能及营养状态",
    },
    "球蛋白": {
        "unit": "g/L",
        "low": 20,
        "high": 40,
        "desc": "反映免疫功能",
    },
    "γ-谷氨酰转肽酶": {
        "unit": "U/L",
        "low": 0,
        "high": 50,
        "desc": "反映胆道梗阻及肝损伤",
    },
    # 血糖
    "空腹血糖": {
        "unit": "mmol/L",
        "low": 3.9,
        "high": 6.1,
        "desc": "反映基础胰岛素分泌功能",
    },
    "糖化血红蛋白": {
        "unit": "%",
        "low": 4.0,
        "high": 6.0,
        "desc": "反映近2-3个月平均血糖水平",
    },
    # 血脂
    "总胆固醇": {
        "unit": "mmol/L",
        "low": 0,
        "high": 5.2,
        "desc": "心血管疾病风险指标",
    },
    "甘油三酯": {
        "unit": "mmol/L",
        "low": 0,
        "high": 1.7,
        "desc": "反映脂质代谢及心血管风险",
    },
    "低密度脂蛋白": {
        "unit": "mmol/L",
        "low": 0,
        "high": 3.4,
        "desc": "'坏胆固醇'，升高增加心血管风险",
    },
    "高密度脂蛋白": {
        "unit": "mmol/L",
        "low": 1.0,
        "high": None,
        "desc": "'好胆固醇'，偏低增加心血管风险",
    },
    # 肾功能
    "肌酐": {
        "unit": "μmol/L",
        "low": 44,
        "high": 133,
        "desc": "反映肾小球滤过功能",
    },
    "尿素氮": {
        "unit": "mmol/L",
        "low": 2.9,
        "high": 8.2,
        "desc": "反映肾脏排泄功能",
    },
    "尿酸": {
        "unit": "μmol/L",
        "low": 149,
        "high": 416,
        "desc": "嘌呤代谢产物，升高与痛风相关",
    },
    # 血常规
    "白细胞计数": {
        "unit": "10^9/L",
        "low": 3.5,
        "high": 9.5,
        "desc": "反映免疫系统功能",
    },
    "红细胞计数": {
        "unit": "10^12/L",
        "low": 3.8,
        "high": 5.1,
        "desc": "反映贫血及携氧能力",
    },
    "血红蛋白": {
        "unit": "g/L",
        "low": 115,
        "high": 150,
        "desc": "反映贫血程度",
    },
    "血小板计数": {
        "unit": "10^9/L",
        "low": 125,
        "high": 350,
        "desc": "反映凝血功能",
    },
    # 肿瘤标志物
    "甲胎蛋白": {
        "unit": "ng/mL",
        "low": 0,
        "high": 7.0,
        "desc": "肝癌筛查指标",
    },
    "癌胚抗原": {
        "unit": "ng/mL",
        "low": 0,
        "high": 5.0,
        "desc": "广谱肿瘤标志物",
    },
    # 炎症
    "C反应蛋白": {
        "unit": "mg/L",
        "low": 0,
        "high": 10.0,
        "desc": "反映急性炎症",
    },
    "超敏C反应蛋白": {
        "unit": "mg/L",
        "low": 0,
        "high": 3.0,
        "desc": "心血管炎症风险指标",
    },
}


# ======================================================================
#  解析器
# ======================================================================


class ReportParser:
    """
    体检报告解析器
    1. 对 OCR 文本进行纠错
    2. 结构化提取报告信息
    3. 根据参考范围判断指标异常状态
    """

    def __init__(
        self,
        correction_map: Optional[Dict[str, str]] = None,
        reference_ranges: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.correction_map = correction_map or CORRECTION_MAP
        self.reference_ranges = reference_ranges or REFERENCE_RANGES

        # 编译指标名正则（用于从文本中匹配指标）
        self._indicator_patterns = self._build_indicator_patterns()

    def _build_indicator_patterns(self) -> List[tuple]:
        """构建指标匹配正则列表，返回 [(compiled_regex, indicator_name), ...]"""
        patterns = []
        for name in self.reference_ranges.keys():
            # 转义特殊字符，构建灵活匹配模式
            escaped = re.escape(name)
            # 允许指标名中间有空格或全角空格
            flexible = escaped.replace(r"\ ", r"[\s\u3000]*")
            patterns.append((re.compile(flexible), name))

        # 额外添加一些别名
        aliases = {
            "ALT": "谷丙转氨酶",
            "AST": "谷草转氨酶",
            "TBIL": "总胆红素",
            "DBIL": "直接胆红素",
            "FBG": "空腹血糖",
            "HbA1c": "糖化血红蛋白",
            "TC": "总胆固醇",
            "TG": "甘油三酯",
            "LDL": "低密度脂蛋白",
            "HDL": "高密度脂蛋白",
            "Cr": "肌酐",
            "BUN": "尿素氮",
            "UA": "尿酸",
            "WBC": "白细胞计数",
            "RBC": "红细胞计数",
            "Hb": "血红蛋白",
            "PLT": "血小板计数",
            "AFP": "甲胎蛋白",
            "CEA": "癌胚抗原",
            "CRP": "C反应蛋白",
            "hs-CRP": "超敏C反应蛋白",
        }
        for alias, canonical in aliases.items():
            patterns.append((re.compile(re.escape(alias)), canonical))

        return patterns

    # ------------------------------------------------------------------
    #  文本纠错
    # ------------------------------------------------------------------

    def correct_text(self, text: str) -> str:
        """
        对 OCR 识别文本进行纠错

        Args:
            text: 原始 OCR 文本

        Returns:
            纠错后的文本
        """
        corrected = text
        for wrong, right in self.correction_map.items():
            if wrong in corrected:
                corrected = corrected.replace(wrong, right)
        return corrected

    # ------------------------------------------------------------------
    #  结构化解析
    # ------------------------------------------------------------------

    def parse(self, ocr_results: List[str]) -> Dict[str, Any]:
        """
        将 OCR 文本行列表解析为结构化报告数据

        Args:
            ocr_results: OCR 提取的文本行列表

        Returns:
            结构化报告字典:
            {
                "name": "张三",
                "gender": "男",
                "age": 35,
                "report_date": "2024-06-15",
                "indicators": {
                    "空腹血糖": {"value": 6.5, "unit": "mmol/L", "status": "abnormal"},
                    ...
                }
            }
        """
        # 先对全文纠错
        corrected_lines = [self.correct_text(line) for line in ocr_results]
        full_text = "\n".join(corrected_lines)

        result: Dict[str, Any] = {
            "name": None,
            "gender": None,
            "age": None,
            "report_date": None,
            "indicators": {},
        }

        # 提取基本信息
        result["name"] = self._extract_name(corrected_lines)
        result["gender"] = self._extract_gender(corrected_lines)
        result["age"] = self._extract_age(corrected_lines)
        result["report_date"] = self._extract_date(corrected_lines)

        # 提取指标
        indicators = self._extract_indicators(corrected_lines)
        result["indicators"] = indicators

        logger.info(
            f"解析完成: {result['name']}, {result['gender']}, "
            f"{result['age']}岁, {len(indicators)} 项指标"
        )
        return result

    def _extract_name(self, lines: List[str]) -> Optional[str]:
        """提取姓名"""
        for line in lines:
            # 匹配 "姓名：张三" 或 "姓名:张三"
            m = re.search(r"姓\s*名[\s:：]+([\u4e00-\u9fa5]{2,4})", line)
            if m:
                return m.group(1)
            # 匹配 "张三" 单独一行（较短中文行）
            if (
                len(line) <= 4
                and 2 <= len(line) <= 4
                and re.match(r"^[\u4e00-\u9fa5]+$", line)
                and not any(
                    kw in line for kw in ["报告", "体检", "检查", "医院", "健康"]
                )
            ):
                return line
        return None

    def _extract_gender(self, lines: List[str]) -> Optional[str]:
        """提取性别"""
        for line in lines:
            m = re.search(r"性\s*别[\s:：]+([男女])", line)
            if m:
                return m.group(1)
            # 也可能在姓名行附近
            if "男" in line and "性别" not in line:
                # 避免误匹配如"男科"
                if re.search(r"(?<![科])男(?![科])", line):
                    return "男"
            if "女" in line and "性别" not in line:
                if re.search(r"(?<![科])女(?![科])", line):
                    return "女"
        return None

    def _extract_age(self, lines: List[str]) -> Optional[int]:
        """提取年龄"""
        for line in lines:
            m = re.search(r"年\s*龄[\s:：]+(\d{1,3})", line)
            if m:
                age = int(m.group(1))
                if 0 < age < 150:
                    return age
            # "35岁" 独立出现
            m = re.search(r"(?<!\d)(\d{1,3})\s*岁", line)
            if m:
                age = int(m.group(1))
                if 0 < age < 150:
                    return age
        return None

    def _extract_date(self, lines: List[str]) -> Optional[str]:
        """提取报告日期，统一输出 YYYY-MM-DD 格式"""
        for line in lines:
            # 匹配 "2024-06-15" / "2024/06/15" / "2024年06月15日"
            m = re.search(
                r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", line
            )
            if m:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{year:04d}-{month:02d}-{day:02d}"

            # 匹配 "报告日期：2024.06.15"
            m = re.search(
                r"(\d{4})\.(\d{1,2})\.(\d{1,2})", line
            )
            if m:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    def _extract_indicators(self, lines: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        从文本行中提取指标名、数值、单位

        策略: 遍历每行，用正则匹配指标名，然后在同行或下一行寻找数值
        """
        indicators: Dict[str, Dict[str, Any]] = {}

        for i, line in enumerate(lines):
            for pattern, canonical_name in self._indicator_patterns:
                if canonical_name in indicators:
                    continue  # 已提取过该指标
                if not pattern.search(line):
                    continue

                # 在当前行和下一行搜索数值
                search_lines = line
                if i + 1 < len(lines):
                    search_lines += " " + lines[i + 1]

                value, unit = self._extract_value_and_unit(
                    search_lines, canonical_name
                )
                if value is not None:
                    # 检查异常状态
                    status_info = self.check_abnormal(canonical_name, value)
                    indicators[canonical_name] = {
                        "value": value,
                        "unit": unit
                        or self.reference_ranges.get(canonical_name, {}).get(
                            "unit", ""
                        ),
                        "status": status_info["status"],
                        "abnormal_type": status_info.get("abnormal_type"),
                        "ref_range": status_info.get("ref_range"),
                    }
                    break  # 匹配到当前行一个指标即可

        return indicators

    def _extract_value_and_unit(
        self, text: str, indicator_name: str
    ) -> tuple:
        """从文本中提取指标数值和单位"""
        # 构建正则: 指标名后面（可能有冒号、空格）跟着一个数字
        escaped_name = re.escape(indicator_name)
        # 数值可能有小数点，可能有负号
        # 单位可能是常见的医学单位
        unit_pattern = (
            r"(mmol/L|μmol/L|umol/L|g/L|U/L|mg/L|ng/mL|"
            r"mg/dL|10\^9/L|10\^12/L|10\^9|10\^12|%|IU/L|"
            r"mmol|μmol|umol|pg|mL|fL|%)"
        )

        # 尝试多种匹配模式
        patterns = [
            # "指标名 6.5 mmol/L"
            rf"{escaped_name}\s*[:：]?\s*(\d+\.?\d*)\s*{unit_pattern}?",
            # "指标名 6.5"
            rf"{escaped_name}\s*[:：]?\s*(\d+\.?\d*)",
        ]

        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    value = float(m.group(1))
                    unit = ""
                    if m.lastindex and m.lastindex >= 2:
                        unit = m.group(2) or ""
                    return value, unit
                except (ValueError, IndexError):
                    continue

        return None, None

    # ------------------------------------------------------------------
    #  异常检测
    # ------------------------------------------------------------------

    def check_abnormal(
        self, indicator_name: str, value: float
    ) -> Dict[str, Any]:
        """
        根据参考范围判断指标值是否异常

        Args:
            indicator_name: 指标名称
            value: 指标数值

        Returns:
            {
                "status": "normal" | "abnormal_high" | "abnormal_low" | "unknown",
                "abnormal_type": "high" | "low" | None,
                "ref_range": "3.9-6.1 mmol/L" | None,
            }
        """
        ref = self.reference_ranges.get(indicator_name)

        if not ref:
            return {
                "status": "unknown",
                "abnormal_type": None,
                "ref_range": None,
            }

        low = ref["low"]
        high = ref["high"]
        unit = ref["unit"]

        ref_str = ""
        if low is not None and high is not None:
            ref_str = f"{low}-{high} {unit}"
        elif low is not None:
            ref_str = f">={low} {unit}"
        elif high is not None:
            ref_str = f"<={high} {unit}"

        if low is not None and value < low:
            return {
                "status": "abnormal",
                "abnormal_type": "low",
                "ref_range": ref_str,
            }
        if high is not None and value > high:
            return {
                "status": "abnormal",
                "abnormal_type": "high",
                "ref_range": ref_str,
            }
        return {
            "status": "normal",
            "abnormal_type": None,
            "ref_range": ref_str,
        }
