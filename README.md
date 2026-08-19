# E-Health Agent — AI健康档案解读

黑客松项目：基于 PaddleOCR + LM Studio + RAG 的本地化健康档案智能解读系统。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行完整测试（使用模拟数据，无需 LM Studio）
python cli_test.py --test full

# 测试各模块
python cli_test.py --test database
python cli_test.py --test llm
python cli_test.py --test parse

# 使用真实图片测试
python cli_test.py --test ocr --image path/to/report.jpg
python cli_test.py --test full --image path/to/report.jpg
```

## 项目结构

```
e_health_agent/
├── core/                    # 核心算法（禁止导入UI库）
│   ├── ocr_engine.py        # PaddleOCR 封装（图片+PDF）
│   ├── parser.py            # 报告解析 + OCR纠错 + 异常检测
│   ├── database.py          # SQLite 存储 + 趋势预警
│   └── llm_agent.py         # LLM解读 + RAG知识库 + Mock模式
├── utils/
│   └── mock_data.py         # 5员工×3年模拟数据
├── assets/
│   ├── knowledge_base.txt   # RAG知识库（20+指标详解）
│   └── sample_reports/
├── data/                    # 数据库文件
├── cli_demo.py              # CLI测试入口
├── requirements.txt
└── README.md
```

## 核心功能

| 模块 | 功能 | 技术方案 |
|------|------|---------|
| OCR提取 | 图片/PDF → 文字 | PaddleOCR + PyMuPDF |
| 报告解析 | 文字 → 结构化数据 | 正则匹配 + 纠错映射表 |
| 异常检测 | 对比参考范围 | 25+指标参考值库 |
| 数据存储 | 员工+体检记录 | SQLite |
| 趋势预警 | 多年数据对比 | 趋势分析算法 |
| LLM解读 | 指标→健康建议 | LM Studio + RAG |

## LM Studio 配置

1. 下载 [LM Studio](https://lmstudio.ai/)
2. 加载模型：推荐 `Qwen2.5-7B-Instruct-Q4_K_M.gguf`
3. 启动本地服务（默认端口 1234）
4. 未启动时自动切换 Mock 模式

## 约束

- 全部本地运行，不依赖云 API
- `core/` 目录不导入任何 UI 库
- Python 3.10+
