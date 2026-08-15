"""
LLM 智能解读模块 — 基于 LM Studio (OpenAI API 兼容) + RAG 知识库
支持自动检测 LM Studio 连接状态，未启动时切换 Mock 模式
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ======================================================================
#  Mock 预设建议数据
# ======================================================================

MOCK_ADVICE: Dict[str, Dict[str, Any]] = {
    "空腹血糖": {
        "high": {
            "summary": "空腹血糖偏高，提示可能存在糖代谢异常",
            "advice": [
                "控制碳水化合物摄入，减少精制糖和甜食",
                "增加膳食纤维摄入（全谷物、蔬菜）",
                "每周至少150分钟中等强度有氧运动",
                "建议复查糖化血红蛋白（HbA1c）以评估近3个月平均血糖",
                "如持续偏高，建议内分泌科就诊排除糖尿病",
            ],
            "knowledge_ref": "知识库: 空腹血糖≥6.1且<7.0为空腹血糖受损(IFG)，属糖尿病前期",
        },
        "low": {
            "summary": "空腹血糖偏低，可能存在低血糖倾向",
            "advice": [
                "规律进餐，避免长时间空腹",
                "随身携带含糖食品以备急需",
                "监测血糖变化，记录低血糖发作情况",
                "如频繁出现低血糖症状，建议内分泌科就诊",
            ],
            "knowledge_ref": "知识库: 空腹血糖<3.9为低血糖，需警惕胰岛素瘤等病因",
        },
    },
    "谷丙转氨酶": {
        "high": {
            "summary": "谷丙转氨酶升高，提示肝细胞可能存在损伤",
            "advice": [
                "避免饮酒及含酒精饮料",
                "慎用对肝脏有损害的药物，遵医嘱用药",
                "注意休息，避免熬夜和过度劳累",
                "建议复查肝炎病毒标志物（乙肝、丙肝）",
                "如持续升高，建议消化内科或肝病科就诊",
                "腹部B超检查排除脂肪肝",
            ],
            "knowledge_ref": "知识库: ALT>40U/L为升高，常见原因包括病毒性肝炎、脂肪肝、药物性肝损伤",
        },
    },
    "甘油三酯": {
        "high": {
            "summary": "甘油三酯升高，心血管疾病风险增加",
            "advice": [
                "减少高脂肪、高糖食物摄入",
                "避免饮酒（酒精显著升高甘油三酯）",
                "增加有氧运动（快走、游泳、骑车等）",
                "控制体重至正常范围（BMI 18.5-24）",
                "如伴随其他血脂异常，建议心内科就诊评估是否需药物治疗",
            ],
            "knowledge_ref": "知识库: 甘油三酯>1.7mmol/L为升高，与胰腺炎风险也相关",
        },
    },
    "总胆固醇": {
        "high": {
            "summary": "总胆固醇升高，心血管疾病风险增加",
            "advice": [
                "减少饱和脂肪摄入（动物内脏、肥肉、黄油等）",
                "增加不饱和脂肪摄入（深海鱼、坚果、橄榄油）",
                "规律有氧运动，每周至少3次",
                "建议检查低密度脂蛋白(LDL)水平以进一步评估风险",
                "如LDL同时升高，建议心内科就诊",
            ],
            "knowledge_ref": "知识库: 总胆固醇>5.2mmol/L为升高，是动脉粥样硬化的危险因素",
        },
    },
    "尿酸": {
        "high": {
            "summary": "尿酸升高，痛风及心血管疾病风险增加",
            "advice": [
                "限制高嘌呤食物（动物内脏、海鲜、浓肉汤）",
                "避免饮酒，尤其是啤酒",
                "每日饮水2000ml以上促进尿酸排泄",
                "控制体重，避免快速减重（可能诱发痛风）",
                "如出现关节红肿热痛，及时风湿免疫科就诊",
                "建议复查尿常规及肾功能",
            ],
            "knowledge_ref": "知识库: 尿酸>416μmol/L为高尿酸血症，痛风发作常累及第一跖趾关节",
        },
    },
    "血红蛋白": {
        "low": {
            "summary": "血红蛋白偏低，提示可能存在贫血",
            "advice": [
                "增加富含铁的食物摄入（红肉、动物肝脏、菠菜）",
                "配合维生素C促进铁吸收（柑橘、猕猴桃等）",
                "建议检查血清铁、铁蛋白以明确贫血类型",
                "女性需关注月经量是否过多",
                "如持续偏低，建议血液科就诊",
            ],
            "knowledge_ref": "知识库: 血红蛋白<115g/L(女)/<120g/L(男)为贫血，需进一步明确病因",
        },
    },
    "肌酐": {
        "high": {
            "summary": "肌酐升高，可能反映肾功能减退",
            "advice": [
                "控制血压和血糖在目标范围内",
                "避免使用肾毒性药物（如非甾体抗炎药）",
                "适量饮水，保持尿量充足",
                "建议检查尿常规、尿微量白蛋白及肾小球滤过率(eGFR)",
                "建议肾内科就诊进一步评估",
            ],
            "knowledge_ref": "知识库: 肌酐>133μmol/L提示肾功能受损，需结合eGFR综合评估",
        },
    },
}

# 默认建议（指标不在预设中时使用）
MOCK_DEFAULT_ADVICE = {
    "summary": "该指标存在异常，建议关注并进一步检查",
    "advice": [
        "建议携带完整体检报告咨询相关专科医生",
        "保持健康生活方式：均衡饮食、规律运动、充足睡眠",
        "定期复查该指标，关注变化趋势",
    ],
    "knowledge_ref": "知识库: 请参阅相关医学指南获取详细信息",
}


class LLMAgent:
    """
    LLM 智能解读代理
    通过 LM Studio (OpenAI API 兼容接口) 进行健康指标解读
    结合 RAG 知识库增强回答质量
    """

    def __init__(
        self,
        base_url: str = None,
        mock_mode: bool = False,
        knowledge_base_path: str = "assets/knowledge_base.txt",
        model_name: str = None,
        api_key: str = None,
    ):
        """
        初始化 LLM 代理

        支持三种后端（按优先级自动选择）:
        1. OpenAI API: 设置环境变量 OPENAI_API_KEY 或传入 api_key
        2. LM Studio: 本地 http://localhost:1234/v1
        3. Mock: 以上均不可用时自动回退

        Args:
            base_url: API 地址（默认自动选择: OpenAI 或 LM Studio）
            mock_mode: 是否强制使用 Mock 模式
            knowledge_base_path: RAG 知识库文件路径
            model_name: 模型名称（OpenAI 用 "gpt-4o-mini" 等）
            api_key: API key（不传则读环境变量 OPENAI_API_KEY）
        """
        self._knowledge_base: Optional[str] = None
        self._client = None
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

        # 自动判断后端类型
        if self._api_key and not base_url:
            # 有 API key → OpenAI 模式
            self.base_url = "https://api.openai.com/v1"
            self.model_name = model_name or "gpt-4o-mini"
            self.backend = "openai"
        elif self._api_key and base_url:
            # 有 API key + 自定义地址 → 兼容模式（如 Azure、代理等）
            self.base_url = base_url
            self.model_name = model_name or "gpt-4o-mini"
            self.backend = "openai"
        else:
            # 无 API key → LM Studio 模式
            self.base_url = base_url or "http://localhost:1234/v1"
            self.model_name = model_name or "local-model"
            self.backend = "lmstudio"

        self.knowledge_base_path = knowledge_base_path

        # 自动检测是否需要 Mock 模式
        if mock_mode:
            self.mock_mode = True
            logger.info("LLM 代理: 强制 Mock 模式")
        else:
            self.mock_mode = not self._check_backend()
            if self.mock_mode:
                if self.backend == "openai":
                    logger.warning("OpenAI API 未响应，自动切换 Mock 模式")
                else:
                    logger.warning(
                        f"LM Studio 未响应 ({self.base_url})，自动切换 Mock 模式"
                    )
            else:
                logger.info(
                    f"LLM 连接正常 ({self.backend}): "
                    f"{self.base_url}, model={self.model_name}"
                )
                self._init_client()

    # ------------------------------------------------------------------
    #  连接检测与客户端初始化
    # ------------------------------------------------------------------

    def _check_backend(self) -> bool:
        """
        检测 LLM 后端是否可用
        优先请求 /models 端点；若失败则发送一个轻量 chat 请求做实测
        使用标准库 urllib，不依赖 httpx
        """
        import json as _json
        import urllib.request
        import urllib.error

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # 第一步: 尝试 /models 接口
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models", headers=headers
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass

        # 第二步: 发送极简 chat 请求验证可用性
        try:
            chat_headers = {**headers, "Content-Type": "application/json"}
            body = _json.dumps({
                "model": self.model_name,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=body,
                headers=chat_headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status in (200, 201)
        except urllib.error.HTTPError as e:
            # 401/403 说明 key 有问题，但也说明服务在线
            logger.debug(f"chat 测试返回 HTTP {e.code}")
            return False
        except Exception:
            return False

    def _init_client(self) -> None:
        """初始化 OpenAI 兼容客户端"""
        try:
            from openai import OpenAI

            # LM Studio 不需要 API key，OpenAI 需要
            api_key = self._api_key or "not-needed"

            self._client = OpenAI(
                base_url=self.base_url,
                api_key=api_key,
            )
        except ImportError:
            logger.error("openai 库未安装，请执行: pip install openai")
            raise

    # ------------------------------------------------------------------
    #  RAG 知识库
    # ------------------------------------------------------------------

    def load_knowledge_base(self) -> str:
        """
        加载 RAG 知识库文件

        Returns:
            知识库全文内容
        """
        if self._knowledge_base is not None:
            return self._knowledge_base

        try:
            if os.path.isfile(self.knowledge_base_path):
                with open(
                    self.knowledge_base_path, "r", encoding="utf-8"
                ) as f:
                    self._knowledge_base = f.read()
                logger.info(
                    f"知识库已加载: {self.knowledge_base_path} "
                    f"({len(self._knowledge_base)} 字符)"
                )
            else:
                logger.warning(
                    f"知识库文件不存在: {self.knowledge_base_path}，使用空知识库"
                )
                self._knowledge_base = ""
        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            self._knowledge_base = ""

        return self._knowledge_base

    def search_knowledge(self, query: str) -> str:
        """
        在知识库中搜索与查询相关的内容（简易 RAG 实现）

        采用基于关键词的段落检索：
        1. 将知识库按段落分割
        2. 计算每个段落与查询的关键词匹配度
        3. 返回最相关的段落

        Args:
            query: 查询文本（如指标名称 + 异常类型）

        Returns:
            最相关的知识库段落文本
        """
        kb = self.load_knowledge_base()
        if not kb:
            return ""

        # 按双换行分割段落
        paragraphs = [p.strip() for p in kb.split("\n\n") if p.strip()]
        if not paragraphs:
            return ""

        # 提取查询关键词
        query_words = set(query.replace("：", " ").replace(":", " ").split())
        # 过滤过短的词
        query_words = {w for w in query_words if len(w) >= 2}

        if not query_words:
            return ""

        # 计算每个段落的匹配分数
        scored = []
        for i, para in enumerate(paragraphs):
            score = 0
            for word in query_words:
                if word in para:
                    score += 1
            if score > 0:
                scored.append((score, i, para))

        if not scored:
            return ""

        # 取前3个最相关段落
        scored.sort(key=lambda x: (-x[0], x[1]))
        relevant = [item[2] for item in scored[:3]]
        result = "\n\n---\n\n".join(relevant)
        logger.info(
            f"知识库检索: query='{query}', 匹配 {len(scored)} 段落, "
            f"返回 {len(relevant)} 段"
        )
        return result

    # ------------------------------------------------------------------
    #  Prompt 构建
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        indicator_name: str,
        value: float,
        ref_range: str,
        knowledge_context: str,
    ) -> str:
        """
        构建 LLM 解读 Prompt

        Args:
            indicator_name: 指标名称
            value: 指标值
            ref_range: 参考范围字符串
            knowledge_context: RAG 检索到的知识库上下文

        Returns:
            完整的 prompt 字符串
        """
        prompt = f"""你是一位专业的健康管理AI助手，请根据以下体检指标信息给出解读建议。

## 体检指标
- 指标名称: {indicator_name}
- 检测值: {value}
- 参考范围: {ref_range}

## 知识库参考
{knowledge_context if knowledge_context else '（无相关知识库内容）'}

## 输出要求
请严格按以下 JSON 格式输出（不要输出其他内容）:
```json
{{
  "summary": "一句话概述该指标的异常情况",
  "risk_level": "低风险|中风险|高风险",
  "advice": ["建议1", "建议2", "建议3"],
  "knowledge_ref": "引用知识库中的原文出处"
}}
```

## 注意事项
1. 建议要具体、可操作，不要空泛
2. 引用知识库原文时注明出处
3. 不要给出确诊结论，建议进一步就医检查
4. 保持专业、客观、关怀的语气
"""
        return prompt

    # ------------------------------------------------------------------
    #  获取建议（主入口）
    # ------------------------------------------------------------------

    def get_advice(
        self, indicator_name: str, value: float, ref_range: str = ""
    ) -> Dict[str, Any]:
        """
        获取指标的健康建议

        Args:
            indicator_name: 指标名称
            value: 指标值
            ref_range: 参考范围字符串（可选）

        Returns:
            {
                "summary": str,
                "risk_level": str,
                "advice": List[str],
                "knowledge_ref": str,
                "source": "llm" | "mock",
            }
        """
        if self.mock_mode:
            return self.get_mock_advice(indicator_name, value)

        try:
            # RAG 检索知识库
            query = f"{indicator_name} 异常"
            knowledge_context = self.search_knowledge(query)

            # 构建 Prompt
            prompt = self.build_prompt(
                indicator_name, value, ref_range, knowledge_context
            )

            # 调用 LLM
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的健康管理AI助手，"
                        "擅长解读体检报告并给出科学的健康建议。"
                        "请始终用中文回答，并严格按照要求的JSON格式输出。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
            )

            raw_output = response.choices[0].message.content.strip()

            # 解析 JSON（尝试提取 JSON 块）
            result = self._parse_llm_output(raw_output)
            result["source"] = "llm"
            logger.info(
                f"LLM 解读完成: {indicator_name}={value}, "
                f"风险等级={result.get('risk_level', '未知')}"
            )
            return result

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}，回退到 Mock 模式")
            result = self.get_mock_advice(indicator_name, value)
            result["source"] = "mock_fallback"
            result["error"] = str(e)
            return result

    # ------------------------------------------------------------------
    #  Mock 模式
    # ------------------------------------------------------------------

    def get_mock_advice(
        self, indicator_name: str, value: float
    ) -> Dict[str, Any]:
        """
        返回预设的 Mock 建议（LM Studio 未启动时使用）

        Args:
            indicator_name: 指标名称
            value: 指标值

        Returns:
            预设建议字典
        """
        from core.parser import REFERENCE_RANGES

        ref = REFERENCE_RANGES.get(indicator_name, {})
        low = ref.get("low")
        high = ref.get("high")

        # 判断异常方向
        abnormal_type = None
        if low is not None and value < low:
            abnormal_type = "low"
        elif high is not None and value > high:
            abnormal_type = "high"

        # 查找预设建议
        mock_entry = MOCK_ADVICE.get(indicator_name, {})
        advice_data = mock_entry.get(abnormal_type, MOCK_DEFAULT_ADVICE)

        result = {
            "summary": advice_data["summary"],
            "risk_level": "中风险" if abnormal_type else "正常",
            "advice": advice_data["advice"],
            "knowledge_ref": advice_data["knowledge_ref"],
            "source": "mock",
        }

        logger.info(
            f"Mock 建议: {indicator_name}={value} "
            f"(type={abnormal_type}, risk={result['risk_level']})"
        )
        return result

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_llm_output(raw: str) -> Dict[str, Any]:
        """
        解析 LLM 输出，提取 JSON 内容

        支持:
        - 纯 JSON 输出
        - ```json ... ``` 代码块
        - 包含额外文字的输出（提取最长的 JSON 块）
        """
        import re

        # 尝试直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        for block in json_blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

        # 尝试提取裸 JSON 对象
        json_matches = re.findall(r"\{[^{}]*\}", raw, re.DOTALL)
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # 解析失败，返回原始文本
        logger.warning(f"LLM 输出 JSON 解析失败，返回原始文本")
        return {
            "summary": "解读结果解析失败",
            "risk_level": "未知",
            "advice": [raw[:200] + "..." if len(raw) > 200 else raw],
            "knowledge_ref": "",
        }
