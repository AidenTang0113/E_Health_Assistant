# E-Health Agent — AI 健康档案解读

> 黑客松项目：基于 PaddleOCR + LLM + RAG 的本地化健康档案智能解读系统
>
> 从体检报告图片/PDF 中提取数据，结构化解析并与参考范围比对，对异常指标调用 LLM 生成专业解读建议，同时支持历史趋势预警。

---

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12）
- Windows / macOS / Linux
- PaddleOCR 首次运行需联网下载模型（约 10MB，后续离线可用）

### 安装

```powershell
# 1. 进入项目目录
cd e_health_agent

# 2. 创建虚拟环境（推荐用 PyCharm 自带 venv）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt
```

> **注意**：`paddlepaddle` 在 Windows 上建议安装 3.2.2 版本（3.3.1 有 oneDNN 兼容 bug）。
> ```powershell
> pip install paddlepaddle==3.2.2
> ```

### 5 分钟体验

```powershell
# 使用模拟数据跑通完整流程（无需图片、无需 LLM）
python cli_demo.py --test full --mock

# 查看系统状态
python cli_demo.py --test status
```

---

## CLI 命令一览

| 命令 | 说明 |
|------|------|
| `--test ocr` | 测试 OCR 文字提取（需 `--image` 或 `--pdf`） |
| `--test parse` | 测试报告解析（可用 `--image` 或模拟数据） |
| `--test database` | 测试数据库操作（自动导入 5 员工×3 年模拟数据） |
| `--test llm` | 测试 LLM 智能解读（自动检测 LM Studio / API） |
| `--test full` | 完整流程：OCR → 解析 → 存储 → 趋势 → LLM |
| `--test batch` | 批量导入目录下所有图片/PDF（需 `--batch-dir`） |
| `--test status` | 查看系统状态：员工、报告、异常指标、趋势 |
| `--test reset` | 清空数据库所有数据 |

### 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--image` | 图片路径 | `--image report.jpg` |
| `--pdf` | PDF 路径 | `--pdf report.pdf` |
| `--batch-dir` | 批量导入目录 | `--batch-dir ./reports` |
| `--api-key` | OpenAI 兼容 API Key | `--api-key sk-xxx` |
| `--base-url` | 自定义 API 地址 | `--base-url https://deepkey.top/v1` |
| `--model` | 模型名称 | `--model gpt-5.4-mini` |
| `--mock` | 强制 Mock 模式 | `--mock` |

### 典型用法

```powershell
# OCR 识别单张图片
python cli_demo.py --test ocr --image sample_report.png

# 批量导入 + AI 解读
python cli_demo.py --test batch --batch-dir batch_test \
  --api-key sk-xxx --base-url https://deepkey.top/v1 --model gpt-5.4-mini

# 查看整体状态
python cli_demo.py --test status

# 清空数据库重来
python cli_demo.py --test reset

# 纯 Mock 模式（不依赖任何外部 API）
python cli_demo.py --test full --mock
```

### LLM 后端优先级

```
1. --api-key 提供 → OpenAI 兼容 API（如 deepkey.top）
2. LM Studio 本地运行 → http://localhost:1234/v1
3. 以上都不可用 → Mock 模式（内置预设建议）
```

也可通过环境变量配置：

```powershell
$env:OPENAI_API_KEY = "sk-xxx"
$env:LLM_BASE_URL = "https://deepkey.top/v1"
$env:LLM_MODEL = "gpt-5.4-mini"
```

---

## 项目结构

```
e_health_agent/
├── core/                        # 核心算法层（禁止导入 UI 库）
│   ├── __init__.py
│   ├── ocr_engine.py            # PaddleOCR 封装（图片 + PDF 文字提取）
│   ├── parser.py                # 报告解析 + OCR 纠错 + 异常检测
│   ├── database.py              # SQLite 存储 + 历史趋势预警
│   └── llm_agent.py             # LLM 解读 + RAG 知识库 + Mock 模式
├── utils/
│   ├── __init__.py
│   └── mock_data.py             # 5 员工 × 3 年模拟数据
├── assets/
│   └── knowledge_base.txt       # RAG 知识库（20+ 指标医学详解）
├── data/                        # SQLite 数据库（运行时生成）
├── batch_test/                  # 批量导入测试用示例图片
│   ├── report_1_张三.png
│   ├── report_2_李四.png
│   └── report_3_王五.png
├── cli_demo.py                  # CLI 入口
├── requirements.txt             # Python 依赖
└── PROJECT.md                   # 本文档
```

---

## 核心模块详解

### 1. ocr_engine.py — OCR 文字提取

基于 PaddleOCR，支持图片（jpg/png/bmp/tiff）和 PDF 两种输入。

| 方法 | 说明 |
|------|------|
| `extract_text_from_image(image_path)` | 从图片提取文字，返回行文本列表 |
| `extract_text_from_pdf(pdf_path)` | 从 PDF 逐页提取文字，返回行文本列表 |

**技术要点**：
- 自动检测 PaddleOCR 2.x / 3.x API 版本，兼容不同参数
- 首次运行自动下载 PP-OCRv6 模型并缓存到 `~/.paddlex/official_models/`
- OCR 失败时不抛异常，返回空列表，由上层处理

### 2. parser.py — 报告解析与异常检测

| 组件 | 说明 |
|------|------|
| `CORRECTION_MAP` | OCR 纠错映射表（40+ 条，如 "总旦红素→总胆红素"） |
| `REFERENCE_RANGES` | 25+ 项指标参考范围表 |
| `ReportParser.correct_text()` | 对 OCR 文本逐行纠错 |
| `ReportParser.parse()` | 正则提取姓名/性别/年龄/日期/指标，返回结构化字典 |
| `ReportParser.check_abnormal()` | 对比参考范围标记正常/异常 |

**解析输出格式**：

```json
{
  "name": "张三",
  "gender": "男",
  "age": "35",
  "report_date": "2025-01-10",
  "indicators": {
    "空腹血糖": {"value": 5.8, "unit": "mmol/L", "status": "normal", "ref_range": "3.9-6.1"},
    "谷丙转氨酶": {"value": 42, "unit": "U/L", "status": "abnormal", "abnormal_type": "high", "ref_range": "0-40"}
  }
}
```

### 3. database.py — 数据存储与趋势预警

SQLite 两张表：

```
employees:  id | name | gender | birth_year | created_at
health_records: id | employee_id | report_date | report_data(JSON) | created_at
```

| 方法 | 说明 |
|------|------|
| `get_or_create_employee()` | 按姓名+性别查找或创建员工 |
| `save_report()` | 保存体检报告（JSON 存储） |
| `get_history()` | 获取员工所有历史报告 |
| `get_all_employees()` | 获取全部员工列表 |
| `check_trend_warning()` | 分析指标趋势（rising/falling/fluctuating），触发预警 |

**趋势预警逻辑**：取最近 3+ 次同指标值，判断单调递增/递减，若连续上升或下降且最新值超出参考范围，则生成预警消息。

### 4. llm_agent.py — LLM 智能解读

| 方法 | 说明 |
|------|------|
| `load_knowledge_base()` | 加载 `assets/knowledge_base.txt` |
| `search_knowledge(query)` | 关键词匹配检索相关段落（RAG） |
| `build_prompt()` | 构建包含指标值 + 知识库原文的 Prompt |
| `get_advice()` | 调用 LLM 获取解读建议 |
| `get_mock_advice()` | Mock 模式预设建议（无需 LLM） |

**三种后端自动切换**：
- 有 `api_key` → OpenAI 兼容 API（deepkey.top / OpenAI / 其他）
- 无 `api_key` + LM Studio 可达 → `http://localhost:1234/v1`
- 以上都不可用 → Mock 模式（内置 10+ 指标的预设建议）

**Prompt 设计**：仅对异常指标调用 LLM，Prompt 中包含指标名、当前值、参考范围、历史趋势，并要求引用知识库原文出处。

### 5. mock_data.py — 模拟数据

5 个员工 × 3 年（2022-2024）模拟体检数据，用于开发和测试：

| 员工 | 设计意图 |
|------|---------|
| 张三 | 空腹血糖逐年上升（趋势预警测试） |
| 李四 | 肝功能指标持续偏高（异常监测测试） |
| 王五 | 基本正常（对照组） |
| 赵六 | 尿酸持续上升 + 血脂异常（多指标趋势） |
| 陈七 | 血红蛋白持续下降（下降趋势测试） |

---

## 数据流程

```
体检报告图片/PDF
      │
      ▼
 ① OCR 提取 ──→ PaddleOCR 识别文字 → 纠错映射表修正
      │
      ▼
 ② 报告解析 ──→ 正则提取指标 → 对比参考范围标记异常
      │                                           │
      ▼                                           ▼
 ③ 数据存储 ──→ SQLite 入库              ④ 趋势分析
      │                                           │
      └────────── 仅异常指标 ──────────→ ⑤ LLM 解读
                                                    │
                                    RAG 检索知识库 → Prompt → LLM
                                                    │
                                                    ▼
                                            解读建议 + 风险等级
```

---

## 运行环境

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 推荐 3.12 |
| PaddlePaddle | 3.2.2 | 避免 3.3.1 的 oneDNN bug |
| PaddleOCR | 3.x | 自动检测 API 版本 |
| PyMuPDF | 1.23+ | PDF 处理 |
| openai | 1.12+ | LLM 客户端（OpenAI 兼容接口） |
| SQLite | 内置 | 无需额外安装 |

### LM Studio 配置（可选，本地 LLM）

1. 安装 [LM Studio](https://lmstudio.ai/)
2. 下载推荐模型：`Qwen2.5-7B-Instruct-Q4_K_M.gguf`（约 4.7GB）
3. 启动 Local Server，端口默认 1234
4. 项目会自动检测连接，未启动则回退 Mock 模式

---

## 测试验证

```powershell
# 全模块测试（venv 激活后）
python cli_demo.py --test ocr --image batch_test/report_1_张三.png   # OCR ✅
python cli_demo.py --test parse                                       # 解析 ✅
python cli_demo.py --test database                                    # 数据库 ✅
python cli_demo.py --test llm --mock                                  # LLM Mock ✅
python cli_demo.py --test full --mock                                 # 完整流程 ✅

# 带 AI 解读测试
python cli_demo.py --test llm \
  --api-key sk-xxx --base-url https://deepkey.top/v1 --model gpt-5.4-mini

# 批量导入测试
python cli_demo.py --test batch --batch-dir batch_test \
  --api-key sk-xxx --base-url https://deepkey.top/v1 --model gpt-5.4-mini

# 查看状态
python cli_demo.py --test status
```

---

## 已知问题与注意事项

1. **PaddlePaddle 3.3.1 oneDNN bug**：`ConvertPirAttribute2RuntimeAttribute` 报错，降级到 3.2.2 解决
2. **Windows 控制台 GBK 编码**：cli_demo.py 中已移除 emoji，使用 ASCII 标记替代
3. **首次 OCR 较慢**：PaddleOCR 模型加载约 3-5 秒，后续请求正常
4. **网络问题**：PaddleOCR 模型下载需要联网，国内网络可能需要配置代理或镜像源
5. **PDF OCR**：通过 PyMuPDF 逐页渲染为图片再 OCR，大文件可能较慢

---

## 后续规划

- [ ] PySide6 桌面 GUI（图形界面，`core/` 保持 UI 无关）
- [ ] 多报告类型适配（不同医院报告格式差异）
- [ ] 知识库扩充（更多指标、用药建议）
- [ ] 导出 PDF 报告
- [ ] Web 版部署

---

## 技术栈

| 层 | 技术 |
|----|------|
| OCR | PaddleOCR 3.x + PaddlePaddle 3.2.2 |
| PDF | PyMuPDF (fitz) |
| 解析 | 正则表达式 + 纠错映射表 |
| 存储 | SQLite (Python 内置 sqlite3) |
| LLM | OpenAI 兼容 API / LM Studio / Mock |
| RAG | 本地文本知识库 + 关键词检索 |
| CLI | argparse |
| GUI (计划) | PySide6 |

---

*最后更新：2026-08-15*

---

## 更新日志

### 2026-08-15：LLM 辅助解析

新增 `parser.parse_with_llm()` 和 `llm_agent.parse_report_with_llm()`，实现正则+LLM 融合解析：

- **策略**：先正则解析（快速免费），再用 LLM 补全正则遗漏的指标
- **冲突处理**：两者都提取到的指标，优先信任正则结果；正则遗漏的用 LLM 补充
- **基本信息**：正则提取失败时（如姓名/性别/日期），用 LLM 结果补全
- **Mock 模式**：LLM 不可用时自动跳过，纯正则解析

**测试结果**（表格分列格式报告，指标名与数值在不同列）：

| 对比项 | 纯正则 | LLM 独立 | 正则+LLM 融合 |
|--------|--------|----------|---------------|
| 指标数 | 10/10 | 10/10 | 10/10 |
| 姓名 | OK | OK | OK |
| 异常标记 | 7 异常 | 7 异常 | 7 异常 |
| 耗时 | <0.1s | ~8s | ~8s |
| API 调用 | 0 | 1 | 1 |

结论：当前正则解析器对该格式已足够鲁棒（PaddleOCR 将表格分列识别为逐行文本，"看下一行"逻辑命中）。LLM 辅助的价值主要在于：
1. 正则完全无法提取的极端格式（竖排、图文混排）
2. 不在 REFERENCE_RANGES 表中的指标
3. 非数值结果（阴性/阳性/比值）
4. 基本信息提取失败的补充
