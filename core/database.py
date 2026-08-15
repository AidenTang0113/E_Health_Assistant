"""
健康档案数据库模块 — SQLite 存储 + 趋势预警
表结构: employees (员工) + health_records (体检记录)
"""

from __future__ import annotations

import json
import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthDatabase:
    """
    健康档案数据库管理器
    提供员工管理、报告存储、历史查询、趋势预警功能
    """

    def __init__(self, db_path: str = "data/health.db"):
        """
        初始化数据库连接

        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（单例）"""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_db(self) -> None:
        """创建表结构（如不存在）"""
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                gender      TEXT NOT NULL,
                birth_year  INTEGER,
                created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS health_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                report_date TEXT,
                report_data TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_records_emp_date
                ON health_records(employee_id, report_date);
            """
        )
        conn.commit()
        logger.info(f"数据库就绪: {self.db_path}")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """将 sqlite3.Row 转为字典"""
        return {key: row[key] for key in row.keys()}

    # ------------------------------------------------------------------
    #  员工管理
    # ------------------------------------------------------------------

    def get_or_create_employee(
        self, name: str, gender: str, birth_year: Optional[int] = None
    ) -> int:
        """
        查找或创建员工记录

        Args:
            name: 姓名
            gender: 性别（"男" / "女"）
            birth_year: 出生年份

        Returns:
            员工 ID
        """
        conn = self._get_conn()

        # 先查找
        cursor = conn.execute(
            "SELECT id FROM employees WHERE name = ? AND gender = ?",
            (name, gender),
        )
        row = cursor.fetchone()
        if row:
            # 如果提供了 birth_year 且数据库中为空，则更新
            if birth_year is not None:
                conn.execute(
                    "UPDATE employees SET birth_year = ? WHERE id = ? AND birth_year IS NULL",
                    (birth_year, row["id"]),
                )
                conn.commit()
            return row["id"]

        # 创建
        cursor = conn.execute(
            "INSERT INTO employees (name, gender, birth_year) VALUES (?, ?, ?)",
            (name, gender, birth_year),
        )
        conn.commit()
        emp_id = cursor.lastrowid
        logger.info(f"创建员工: {name}({gender}), ID={emp_id}")
        return emp_id

    def get_all_employees(self) -> List[Dict[str, Any]]:
        """
        获取所有员工列表

        Returns:
            员工字典列表: [{"id":1, "name":"张三", "gender":"男", "birth_year":1985, ...}, ...]
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, name, gender, birth_year, created_at FROM employees ORDER BY id"
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_employee(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """获取单个员工信息"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, name, gender, birth_year, created_at FROM employees WHERE id = ?",
            (employee_id,),
        )
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    #  报告存储
    # ------------------------------------------------------------------

    def save_report(
        self, employee_id: int, report_data: Dict[str, Any]
    ) -> int:
        """
        保存体检报告到数据库

        Args:
            employee_id: 员工 ID
            report_data: 解析后的报告数据字典

        Returns:
            记录 ID
        """
        conn = self._get_conn()

        report_date = report_data.get("report_date") or datetime.now().strftime(
            "%Y-%m-%d"
        )
        report_json = json.dumps(report_data, ensure_ascii=False)

        cursor = conn.execute(
            "INSERT INTO health_records (employee_id, report_date, report_data) "
            "VALUES (?, ?, ?)",
            (employee_id, report_date, report_json),
        )
        conn.commit()
        record_id = cursor.lastrowid
        logger.info(
            f"保存报告: 员工ID={employee_id}, 日期={report_date}, 记录ID={record_id}"
        )
        return record_id

    # ------------------------------------------------------------------
    #  历史查询
    # ------------------------------------------------------------------

    def get_history(self, employee_id: int) -> List[Dict[str, Any]]:
        """
        获取员工所有体检历史记录

        Args:
            employee_id: 员工 ID

        Returns:
            历史记录列表（按日期排序）:
            [{"id":1, "employee_id":1, "report_date":"2024-06-15",
              "report_data": {...}, "created_at":"..."}, ...]
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, employee_id, report_date, report_data, created_at "
            "FROM health_records WHERE employee_id = ? ORDER BY report_date ASC",
            (employee_id,),
        )
        records = []
        for row in cursor.fetchall():
            record = self._row_to_dict(row)
            # 反序列化 report_data
            try:
                record["report_data"] = json.loads(record["report_data"])
            except (json.JSONDecodeError, TypeError):
                pass
            records.append(record)
        return records

    def get_latest_report(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """获取员工最近一次体检报告"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, employee_id, report_date, report_data, created_at "
            "FROM health_records WHERE employee_id = ? "
            "ORDER BY report_date DESC LIMIT 1",
            (employee_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        record = self._row_to_dict(row)
        try:
            record["report_data"] = json.loads(record["report_data"])
        except (json.JSONDecodeError, TypeError):
            pass
        return record

    # ------------------------------------------------------------------
    #  趋势预警
    # ------------------------------------------------------------------

    def check_trend_warning(
        self, employee_id: int, indicator_name: str
    ) -> Dict[str, Any]:
        """
        检查指定员工的某项指标趋势，判断是否需要预警

        分析逻辑:
        - 取最近 3 次报告的该指标值
        - 连续上升或下降 → 趋势预警
        - 接近参考范围边界（在阈值内）→ 边界预警
        - 已经异常 → 异常预警

        Args:
            employee_id: 员工 ID
            indicator_name: 指标名称

        Returns:
            {
                "indicator": "空腹血糖",
                "values": [5.2, 5.8, 6.5],
                "dates": ["2022-06-15", "2023-06-20", "2024-06-15"],
                "trend": "rising" | "falling" | "stable" | "insufficient",
                "warning": "trend_rising" | "trend_falling" | "boundary" | "abnormal" | None,
                "message": "空腹血糖连续3年上升，已超出正常范围",
            }
        """
        history = self.get_history(employee_id)

        # 收集该指标的所有历史值
        values: List[float] = []
        dates: List[str] = []

        for record in history:
            report_data = record.get("report_data", {})
            indicators = report_data.get("indicators", {})
            if indicator_name in indicators:
                ind = indicators[indicator_name]
                val = ind.get("value")
                if val is not None:
                    values.append(val)
                    dates.append(record.get("report_date", ""))

        if len(values) < 2:
            return {
                "indicator": indicator_name,
                "values": values,
                "dates": dates,
                "trend": "insufficient",
                "warning": None,
                "message": "历史数据不足，无法分析趋势",
            }

        # 计算趋势
        trend = self._analyze_trend(values)

        # 判断预警类型
        warning = None
        message_parts = []

        # 获取参考范围
        from core.parser import REFERENCE_RANGES

        ref = REFERENCE_RANGES.get(indicator_name, {})
        low = ref.get("low")
        high = ref.get("high")
        unit = ref.get("unit", "")
        ref_str = ""
        if low is not None and high is not None:
            ref_str = f"{low}-{high} {unit}"
        elif high is not None:
            ref_str = f"<={high} {unit}"
        elif low is not None:
            ref_str = f">={low} {unit}"

        latest_val = values[-1]

        # 异常预警（最新值已超出范围）
        if low is not None and latest_val < low:
            warning = "abnormal"
            message_parts.append(
                f"{indicator_name}最新值 {latest_val} {unit} 低于参考范围 {ref_str}"
            )
        elif high is not None and latest_val > high:
            warning = "abnormal"
            message_parts.append(
                f"{indicator_name}最新值 {latest_val} {unit} 高于参考范围 {ref_str}"
            )

        # 趋势预警（连续上升或下降）
        if trend == "rising" and len(values) >= 3:
            if warning != "abnormal":
                warning = "trend_rising"
            message_parts.append(
                f"{indicator_name}连续{len(values)}次检测呈上升趋势"
            )
        elif trend == "falling" and len(values) >= 3:
            if warning != "abnormal":
                warning = "trend_falling"
            message_parts.append(
                f"{indicator_name}连续{len(values)}次检测呈下降趋势"
            )

        # 边界预警（接近但未超出正常范围）
        if warning is None and low is not None and high is not None:
            range_span = high - low
            threshold = range_span * 0.1  # 10% 边界
            if latest_val > high - threshold:
                warning = "boundary"
                message_parts.append(
                    f"{indicator_name}最新值 {latest_val} {unit} "
                    f"接近参考范围上限 {high} {unit}"
                )
            elif latest_val < low + threshold:
                warning = "boundary"
                message_parts.append(
                    f"{indicator_name}最新值 {latest_val} {unit} "
                    f"接近参考范围下限 {low} {unit}"
                )

        return {
            "indicator": indicator_name,
            "values": values,
            "dates": dates,
            "trend": trend,
            "warning": warning,
            "message": "；".join(message_parts) if message_parts else "指标趋势正常",
        }

    @staticmethod
    def _analyze_trend(values: List[float]) -> str:
        """
        分析数值序列的趋势

        Returns:
            "rising" | "falling" | "stable" | "fluctuating"
        """
        if len(values) < 2:
            return "insufficient"

        # 检查是否单调递增/递减（允许1次波动）
        rising_count = 0
        falling_count = 0
        for i in range(1, len(values)):
            if values[i] > values[i - 1]:
                rising_count += 1
            elif values[i] < values[i - 1]:
                falling_count += 1

        n = len(values) - 1
        if rising_count == n:
            return "rising"
        if falling_count == n:
            return "falling"

        # 允许1次波动
        if rising_count >= n - 1 and falling_count <= 1:
            return "rising"
        if falling_count >= n - 1 and rising_count <= 1:
            return "falling"

        # 变化幅度很小
        avg = sum(values) / len(values)
        if avg > 0:
            max_dev = max(abs(v - avg) for v in values) / avg
            if max_dev < 0.05:  # 5%以内
                return "stable"

        return "fluctuating"

    # ------------------------------------------------------------------
    #  关闭
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭")

    def __del__(self):
        self.close()
