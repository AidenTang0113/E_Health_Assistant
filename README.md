# E-Health Agent — AI 体检报告智能解读系统

基于 PaddleOCR + LLM + RAG 的本地化健康档案管理与智能解读系统。从体检报告图片/PDF 中提取数据，结构化解析并与医学参考范围比对，对异常指标调用 LLM 生成专业解读建议，支持历史趋势预警。

支持 **HR / 经理 / 员工** 三角色权限管理，适用于企业健康管理场景。

---

## 目录

- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [系统架构与原理](#系统架构与原理)
- [核心模块详解](#核心模块详解)
- [角色与权限](#角色与权限)
- [CLI 菜单结构](#cli-菜单结构)
- [数据流程](#数据流程)
- [项目结构](#项目结构)
- [运行环境](#运行环境)
- [已知问题与注意事项](#已知问题与注意事项)
- [后续规划](#后续规划)

---

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12）
- Windows / macOS / Linux
- PaddleOCR 首次运行需联网下载模型（约 10MB，后续离线可用）

### 安装

```powershell
# 1. 克隆仓库
git clone https://github.com/AidenTang0113/E_Health_Assistant.git
cd E_Health_Assistant

# 2. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate      # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt
```

> **PaddlePaddle 版本**：3.3.1 有 oneDNN 兼容 bug（`ConvertPirAttribute2RuntimeAttribute` 报错），已锁定 3.2.2。如自动安装失败，手动执行：
> ```powershell
> pip install paddlepaddle==3.2.2 -i https://mirrors.aliyun.com/pypi/simple/
> ```

### 首次启动

```powershell
python cli.py
```

系统会自动初始化：
1. 创建 `data/health.db`（体检数据库）
2. 创建 `data/users.db`（用户数据库），并生成默认 admin 账号
3. 生成 `data/config.json`（LLM 配置，默认 Mock 模式）

**默认管理员账号**：用户名 `admin`，密码 `123456`（首次登录后请立即修改）

### 5 分钟体验

启动后用 admin 账号登录，依次操作：
1. **报告管理 → 批量导入**：选择 `assets/sample_reports/` 目录，导入 5 份示例体检报告
2. **总体查看 → 全员概览**：查看全员健康摘要
3. **总体查看 → 异常指标解读**：对异常指标进行 LLM 解读（Mock 模式下也能看到预设建议）
4. **个人查看**：选择员工查看个人档案、趋势分析

---

## 配置说明

### LLM 配置

通过 **系统设置 → LLM 配置** 菜单配置，或直接编辑 `data/config.json`。

支持两种模式：

| 模式 | 适用场景 | 配置项 |
|------|---------|--------|
| 第三方 API | 使用 OpenAI 兼容 API 服务 | `api_key`、`base_url`、`api_model` |
| 本地模型 | 使用 LM Studio 本地推理 | `local_url`、`local_model` |

**第三方 API 配置示例**：

```json
{
  "mode": "api",
  "api_key": "sk-your-api-key",
  "base_url": "https://api.openai.com/v1",
  "api_model": "gpt-4o-mini"
}
```

**本地模型配置示例**：

```json
{
  "mode": "local",
  "local_url": "http://localhost:1234/v1",
  "local_model": "qwen2.5-7b-instruct"
}
```

> 模型名称按模式独立存储：切换 API/本地模式时，各自使用对应的模型名，互不干扰。
> 旧配置中的 `model` 字段会自动迁移为 `api_model`。

### LM Studio 配置（本地模式）

1. 安装 [LM Studio](https://lmstudio.ai/)
2. 下载推荐模型：`Qwen2.5-7B-Instruct-Q4_K_M.gguf`（约 4.7GB）
3. 启动 Local Server，端口默认 1234
4. 在系统设置中将模式切为"本地模型"

### API Key 加密

Windows 环境下，API Key 使用 DPAPI（Windows Data Protection API）加密存储，绑定当前用户账户。`pywin32` 依赖提供加密支持。

### 后端自动检测优先级

```
1. 有 api_key + 自定义 base_url（非 localhost）→ OpenAI 兼容 API 模式
2. 有 api_key + 无 base_url → OpenAI 官方 API 模式
3. 无 api_key + localhost → LM Studio 本地模式
4. 以上都不可用 → Mock 模式（内置预设建议）
```

---

## 系统架构与原理

### 整体架构

```
┌─────────────────────────────────────────────┐
│                  CLI 界面层                   │
│                 (cli.py)                      │
│  ┌──────────┬──────────┬──────────────────┐  │
│  │ 总体查看  │ 个人查看  │  报告管理/设置   │  │
│  └─────┬────┴─────┬────┴────────┬─────────┘  │
├────────┼──────────┼─────────────┼────────────┤
│        ▼          ▼             ▼            │
│  ┌──────────────────────────────────────┐    │
│  │            核心算法层 (core/)          │    │
│  │  ┌─────────┐ ┌────────┐ ┌──────────┐  │    │
│  │  │OCR Engine│ │ Parser │ │Database  │  │    │
│  │  └────┬────┘ └───┬────┘ └────┬─────┘  │    │
│  │       │          │           │         │    │
│  │  ┌────▼──────────▼───────────▼──────┐  │    │
│  │  │         LLMAgent + RAG            │  │    │
│  │  └──────────────────────────────────┘  │    │
│  └──────────────────────────────────────┘    │
│        ▼                                      │
│  ┌──────────────────────────────────────┐    │
│  │          数据层 (data/)               │    │
│  │  health.db │ users.db │ config.json  │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

### OCR 提取原理

基于 PaddleOCR，支持图片（jpg/png/bmp/tiff）和 PDF 两种输入：

1. **图片**：直接调用 PaddleOCR 推理，返回行文本列表
2. **PDF**：通过 PyMuPDF 逐页渲染为图片，再走图片 OCR 流程
3. **纠错**：OCR 结果经过 `CORRECTION_MAP`（40+ 条映射）修正常见误识别，如"总旦红素→总胆红素"
4. **容错**：OCR 失败时返回空列表，不抛异常，由上层处理

### 报告解析原理

采用 **正则解析 + LLM 辅助** 融合策略：

1. **正则解析**（快速免费）：从 OCR 文本中用正则提取姓名、性别、年龄、日期、指标名/数值/单位
2. **LLM 辅助**（可选）：正则解析后，用 LLM 补全遗漏的指标和非数值结果
3. **冲突处理**：两者都提取到的指标，优先信任正则结果；正则遗漏的用 LLM 补充
4. **异常检测**：对比 `REFERENCE_RANGES`（25+ 项指标参考值表），标记 normal/abnormal 及方向（high/low）

解析输出格式：

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

### LLM 解读原理

采用 **RAG（检索增强生成）** 架构：

1. **知识库加载**：读取 `assets/knowledge_base.txt`（20+ 指标医学详解）
2. **检索**：`search_knowledge(query)` 按关键词匹配相关段落，取前 3 段
3. **Prompt 构建**：包含指标名、当前值、参考范围、历史趋势、知识库原文
4. **调用**：`chat.completions.create`（temperature 0.3，简略 1024 tokens / 详细 2048 tokens）
5. **解析**：`_parse_llm_output` 支持纯 JSON、```json``` 代码块、含额外文字的输出
6. **降级**：LLM 不可用时自动回退 Mock 模式，返回预设建议

**Prompt 输出格式**（详细模式）：

```json
{
  "summary": "一句话总结",
  "risk_level": "低风险/中风险/高风险",
  "interpretation": "指标含义解读",
  "possible_causes": ["原因1", "原因2"],
  "advice": ["建议1", "建议2"],
  "lifestyle": ["生活方式建议"],
  "follow_up": "随访建议",
  "knowledge_ref": "知识库引用出处",
  "urgency": "routine/attention/urgent"
}
```

### 趋势预警逻辑

取员工最近 3+ 次体检中同一指标的值，判断：
- **单调递增**（rising）：连续上升，且最新值超出参考范围上限 → 预警
- **单调递减**（falling）：连续下降，且最新值低于参考范围下限 → 预警
- **波动**（fluctuating）：值在参考范围内但有较大波动 → 提示

---

## 核心模块详解

### ocr_engine.py — OCR 文字提取

| 方法 | 说明 |
|------|------|
| `extract_text_from_image(image_path)` | 从图片提取文字，返回行文本列表 |
| `extract_text_from_pdf(pdf_path)` | 从 PDF 逐页提取文字 |

- 自动检测 PaddleOCR 2.x / 3.x API 版本
- 首次运行自动下载 PP-OCRv6 模型并缓存

### parser.py — 报告解析与异常检测

| 组件 | 说明 |
|------|------|
| `CORRECTION_MAP` | OCR 纠错映射表（40+ 条） |
| `REFERENCE_RANGES` | 25+ 项指标参考范围表 |
| `ReportParser.correct_text()` | 对 OCR 文本逐行纠错 |
| `ReportParser.parse()` | 正则提取结构化数据 |
| `ReportParser.check_abnormal()` | 对比参考范围标记异常 |

### database.py — 体检数据存储

SQLite 两张表：

```sql
employees:  id | name | gender | birth_year | created_at
health_records: id | employee_id | report_date | report_data(JSON) | created_at
```

| 方法 | 说明 |
|------|------|
| `get_or_create_employee()` | 按姓名+性别查找或创建员工 |
| `save_report()` | 保存体检报告（JSON 存储） |
| `get_history()` | 获取员工所有历史报告 |
| `check_trend_warning()` | 分析指标趋势，触发预警 |

### user_database.py — 用户管理与认证

SQLite 表：

```sql
users: id | username | employee_key | employee_name | gender | role | is_active | password_hash | created_at
user_audit_log: id | action | target | operator | detail | timestamp
```

认证：`pbkdf2_sha256`，210000 次迭代。

| 方法 | 说明 |
|------|------|
| `authenticate()` | 用户名+密码验证 |
| `ensure_employee_account()` | 为员工创建关联账号 |
| `sync_employees()` | 从 health.db 同步员工到 users.db |
| `update_user_profile()` | 修改用户名/密码 |
| `reset_password()` | 重置密码（需 operator 审计） |
| `deactivate_user()` / `reactivate_user()` | 停用/启用账号 |
| `delete_user()` | 删除账号（支持软删除/硬删除） |
| `promote_employee_to_manager()` | 提升为经理 |
| `list_audit_logs()` | 查看操作日志 |

**删除策略**：

| 场景 | 策略 | 档案 |
|------|------|------|
| 员工离职 | 软删除（`is_active=0`） | 保留 |
| 账号误建 | 硬删除用户记录 | 保留 |
| 删除个人信息 | 硬删除用户+连带删档案 | 二次确认 |
| 系统重置 | 硬删除所有用户 | 不动 |

### config_manager.py — 配置管理

| 方法 | 说明 |
|------|------|
| `load_config()` | 加载 `data/config.json`，自动迁移旧字段 |
| `save_config()` | 保存配置（API Key 加密存储） |
| `get_llm_config()` | 按当前模式返回完整 LLM 配置 |
| `get_status_text()` | 返回 LLM 状态摘要文本 |

- Windows 下 API Key 使用 DPAPI 加密
- `api_model` / `local_model` 分离存储，切换模式不串用

### llm_agent.py — LLM 智能解读

| 方法 | 说明 |
|------|------|
| `load_knowledge_base()` | 加载知识库文件 |
| `search_knowledge(query)` | 关键词检索相关段落（RAG） |
| `build_prompt()` | 构建包含指标+知识库的 Prompt |
| `get_advice()` | 调用 LLM 获取解读建议 |
| `get_mock_advice()` | Mock 模式预设建议 |
| `parse_report_with_llm()` | LLM 辅助解析 OCR 文本 |

---

## 角色与权限

| 功能 | HR | 经理 | 员工 |
|------|:---:|:---:|:---:|
| 全员概览 | ✅ | ✅ | ❌ |
| 全员趋势分析 | ✅ | ✅ | ❌ |
| 异常指标解读 | ✅ | ✅ | ❌ |
| 查看个人档案 | ✅ | ✅ | ✅（仅自己） |
| 个人趋势 | ✅ | ✅ | ✅（仅自己） |
| 个人指标解读 | ✅ | ✅ | ✅（仅自己） |
| 添加/批量导入报告 | ✅ | ✅ | ❌ |
| 账号设置 | ✅ | ✅ | ✅（仅自己） |
| LLM 配置 | ✅ | ❌ | ❌ |
| 清空数据库 | ✅ | ❌ | ❌ |
| 操作日志 | ✅ | ❌ | ❌ |
| 退出登录 | ✅ | ✅ | ✅ |

员工登录后直接进入个人查看，不显示主菜单。

---

## CLI 菜单结构

```
登录界面
  ├── admin / HR 账号 → 主菜单
  │     ├── 1. 总体查看
  │     │     ├── 1. 全员概览
  │     │     ├── 2. 全员趋势
  │     │     ├── 3. 异常指标解读
  │     │     └── 0. 返回
  │     ├── 2. 个人查看（选择员工）
  │     │     ├── 1. 个人档案
  │     │     ├── 2. 个人趋势
  │     │     ├── 3. 指标解读
  │     │     ├── 4. 账号设置
  │     │     └── 0. 返回 / 切换账号
  │     ├── 3. 报告管理
  │     │     ├── 1. 添加报告
  │     │     ├── 2. 批量导入
  │     │     └── 0. 返回
  │     ├── 4. 账号设置
  │     ├── 5. 系统设置
  │     │     ├── LLM 配置
  │     │     ├── 清空数据库（HR）
  │     │     └── 操作日志（HR）
  │     ├── 6. 退出登录 → 回到登录界面
  │     └── 0. 退出程序
  │
  └── 员工账号 → 个人查看（直接进入，无主菜单）
        ├── 1. 个人档案
        ├── 2. 个人趋势
        ├── 3. 指标解读
        ├── 4. 账号设置
        └── 0. 切换账号 → 回到登录界面
```

每次菜单循环自动清屏，模拟真实 CLI 体验。

---

## 数据流程

```
体检报告图片/PDF
      │
      ▼
 ① OCR 提取 ──→ PaddleOCR 识别文字 → 纠错映射表修正
      │
      ▼
 ② 报告解析 ──→ 正则提取指标 → LLM 辅助补全 → 对比参考范围标记异常
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

## 项目结构

```
e_health_agent/
├── core/                        # 核心算法层（禁止导入 UI 库）
│   ├── __init__.py
│   ├── ocr_engine.py            # PaddleOCR 封装（图片 + PDF）
│   ├── parser.py                # 报告解析 + OCR 纠错 + 异常检测
│   ├── database.py              # SQLite 体检数据存储 + 趋势预警
│   ├── user_database.py         # 用户管理 + 认证 + 审计日志
│   ├── llm_agent.py             # LLM 解读 + RAG 知识库 + Mock 模式
│   └── config_manager.py        # 配置管理 + API Key 加密
├── utils/
│   ├── __init__.py
│   └── mock_data.py             # 5 员工 × 3 年模拟数据
├── assets/
│   ├── knowledge_base.txt       # RAG 知识库（20+ 指标医学详解）
│   └── sample_reports/          # 5 份示例体检报告图片
├── data/                        # 运行时数据（已 gitignore）
│   ├── health.db                # 体检数据库
│   ├── users.db                 # 用户数据库
│   ├── config.json              # LLM 配置
│   └── app.log                  # 运行日志
├── cli.py                       # CLI 入口（~1560 行）
├── requirements.txt             # Python 依赖
├── .gitignore
└── README.md                    # 本文档
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
| pywin32 | — | Windows DPAPI 加密（仅 Windows） |
| SQLite | 内置 | 无需额外安装 |

### 依赖安装（国内镜像加速）

```powershell
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

---

## 已知问题与注意事项

1. **PaddlePaddle 3.3.1 oneDNN bug**：`ConvertPirAttribute2RuntimeAttribute` 报错，降级到 3.2.2 解决
2. **Windows 控制台编码**：日志中使用纯文本 `[ERROR]` 前缀，不使用 ANSI 颜色
3. **首次 OCR 较慢**：PaddleOCR 模型加载约 3-5 秒，后续请求正常
4. **PaddleOCR 模型下载**：首次运行需联网，国内网络可能需要配置代理或镜像源
5. **PDF OCR**：通过 PyMuPDF 逐页渲染为图片再 OCR，大文件可能较慢
6. **数据安全**：`data/` 目录已加入 `.gitignore`，不会上传到 GitHub；API Key 使用 DPAPI 加密存储

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
| 解析 | 正则表达式 + 纠错映射表 + LLM 辅助 |
| 存储 | SQLite (Python 内置 sqlite3) |
| LLM | OpenAI 兼容 API / LM Studio / Mock |
| RAG | 本地文本知识库 + 关键词检索 |
| 认证 | pbkdf2_sha256 (210000 次迭代) |
| 加密 | Windows DPAPI (API Key 保护) |
| CLI | argparse |
| GUI (计划) | PySide6 |

---

## 更新日志

### 2026-08-19：企业级用户管理 + CLI 重构

- **用户管理重构**：审计日志、软删除/硬删除策略、admin 保护（按 `employee_key` 查找）
- **CLI 菜单重构**：HR/经理/员工三角色菜单，新增退出登录/切换账号
- **LLM 后端修复**：三段式判断逻辑，支持无 API Key 的 OpenAI 兼容模式
- **模型名分离**：`api_model` / `local_model` 独立存储，切换模式不串用
- **清屏优化**：每次菜单循环自动清屏
- **HR 改密修复**：`_ensure_admin_account` 不再覆盖已修改的密码

### 2026-08-15：LLM 辅助解析

新增正则+LLM 融合解析策略，LLM 补全正则遗漏的指标。测试结果：纯正则 10/10 指标，LLM 辅助 10/10，耗时 ~8s。

---

*最后更新：2026-08-19*
