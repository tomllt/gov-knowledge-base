# P1 政务智能知识库平台核心引擎

[![CI](https://github.com/tomllt/gov-knowledge-base/actions/workflows/ci.yml/badge.svg)](https://github.com/tomllt/gov-knowledge-base/actions/workflows/ci.yml)

P1 政务智能知识库平台核心引擎：知识采集接入（P1-F01）、知识解析与切分（P1-F02）。

## 快速开始

环境要求：Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
make install           # 安装基础 + dev 依赖
make test              # 跑全部测试（含覆盖率 ≥85% 门禁）
make lint type format  # 三项质量门禁
make check             # 等价于 lint + type + test
```

## 项目结构

```
src/p1_core/           # 核心引擎源代码
├── exceptions.py      # 结构化异常体系（P1CoreError 基类）
├── models/            # 领域数据模型
│   ├── heading.py     #   HeadingPath（标题层级路径）
│   ├── raw_document.py    #   RawDocument（采集产物）
│   ├── parsed_document.py #   ParsedDocument / ParsedBlock（解析产物）
│   ├── knowledge_chunk.py #   KnowledgeChunk（切分产物）
│   ├── enums.py           #   SourceType / DocumentFormat / BlockType / ChunkQuality
│   ├── _validators.py     #   模型层共享校验工具
│   └── time_utils.py      #   utcnow()
├── collectors/        # 采集器子包（P1-F01，Stage 2 实现）
│   ├── pdf/  word/  html/  api/
└── parsers/           # 解析器与切分器子包（P1-F02，Stage 3 实现）
    ├── pdf/  word/  html/
    └── splitter/

tests/                 # TDD 测试套件（与 src/ 同包同名）
├── p1_core/
│   ├── test_exceptions.py
│   ├── test_enums.py
│   ├── test_heading.py
│   ├── test_models_integration.py
│   ├── test_raw_document.py
│   ├── test_parsed_document.py
│   ├── test_parsed_document_deserialize.py
│   ├── test_knowledge_chunk.py
│   ├── test_knowledge_chunk_deserialize.py
│   ├── test_validators.py
│   └── test_time_utils.py
├── conftest.py
├── test_package_init.py
└── test_placeholder_imports.py
```

## 质量门禁

| 门禁 | 工具 | 阈值 |
|------|------|------|
| 单元测试 | pytest | 100% 通过 |
| 覆盖率 | coverage.py | ≥ 85%（分支覆盖） |
| 类型检查 | mypy --strict | 0 error |
| Lint | ruff (E/W/F/I/B/UP/N/SIM/PL/RUF/ANN/RET/TRY/PTH/ERA) | 0 error |
| 格式 | ruff format | 与配置一致 |
| pre-commit | ruff + mypy + 文件级 hooks | 全部通过 |
| CI | GitHub Actions (Python 3.11 / 3.12 矩阵) | 全部步骤绿 |

## 数据模型流水线

```
数据源 ──► RawDocument (采集, P1-F01)
          └──► ParsedDocument (解析, P1-F02)
                └──► KnowledgeChunk (切分, P1-F02)
```

每个阶段均保留 `HeadingPath`、`raw_doc_id` 等业务可追溯字段，切分块支持 `parent_chunk_id` 父子索引以支持召回后还原上下文。

## 里程碑

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| M1-S1 | 项目脚手架 + TDD 基础设施 | 进行中 |
| M1-S2 | PDF / Word/HTML / API 采集器 | 待启动 |
| M1-S3 | PDF / Word / HTML 解析器 + 标题层级切分器 | 待启动 |
| M1-S4 | 集成批次：首批 100 事项接入验收 | 待启动 |
