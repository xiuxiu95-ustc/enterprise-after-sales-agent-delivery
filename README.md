# 企业售后智能客服与预约 Agent 系统

这是一个可直接克隆的 Python 单仓库。主服务、企业槽位抽取/后训练工具链、模块化 RAG MCP Server 均在同一版本边界内，不依赖本机其他源码目录。

## 核心能力

- 主管 Agent 以 ReAct 方式规划并调用咨询、预约、行为分析、知识检索和记忆工具。
- `discuss → implement → review → deliver → done` 五阶段持久化工作流，每次迁移都有证据门禁。
- FastAPI + SSE 推送运行、handoff、工具、引用、文本和终态事件。
- SQLite 持久化 session、message、invocation、event、handoff、Trace、Memory、预约、行为、审计和回归失败样本。
- 最近 10 轮 + session 槽位构成短期状态；窗口达到 60% 时滚动摘要；长期 Recall 按语义 0.6、时效 0.3、重要度 0.1 召回 Top-5。
- AutoDream 在 5 个已关闭会话且间隔 24 小时后增量运行，具备去重、冲突降权、置信度更新、任务锁和 checkpoint 幂等。
- 预约状态机结合排班、技能、区域和约束匹配；指定工程师不可用时按专长向量推荐替代候选。
- 30 分钟资源槽唯一约束、请求幂等键和版本号共同处理并发预约、重试与取消竞争。
- 权限分级、参数校验、工具白名单、显式确认、字段脱敏、本地回环监听和完整审计。
- EDD 对路由、槽位、RAG、工具调用、Agent 轨迹和安全用例分层评分，并在 CI 中执行门禁。

## 单仓库结构

```text
.
├── web/                 # 服务台页面
├── api/                 # FastAPI schema、依赖与 28 个 API 路径
├── agents/              # 主管 Agent、专业 Agent、handoff 合同
├── services/            # 编排、工作流、预约、记忆、RAG、安全、恢复
├── db/                  # SQLAlchemy 模型与 Repository Pattern
├── evaluation/          # EDD case、评分器、失败回归写入
├── packages/
│   ├── slot_extractor/  # 后训练、评估、量化、推理和工具循环
│   └── modular_rag_mcp/ # 摄取、双路召回、RRF、精排、3 个 MCP Tool
├── tests/               # Unit / Integration / E2E
└── docs/                # 架构、API、容量、运行、面试深挖
```

主服务通过 `SlotExtractorAdapter` 加载 `packages/slot_extractor/src`，通过 `RagGateway` 以进程内或 MCP stdio 方式加载 `packages/modular_rag_mcp`。默认路径按仓库根目录解析，因此换机器或换盘符无需修改源码。

## 快速启动

要求 Python 3.12+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app:app --host 127.0.0.1 --port 8001
```

访问：

- 服务台：`http://127.0.0.1:8001/`
- OpenAPI：`http://127.0.0.1:8001/docs`
- 健康检查：`http://127.0.0.1:8001/api/v1/health`

`RAG_MODE=local` 是无外部模型的确定性开发降级。启用完整 RAG 能力时安装集成依赖并选择 `mcp` 或 `inprocess`：

```powershell
pip install -r requirements-integrated.txt
```

```env
SLOT_EXTRACTOR_REPO=packages/slot_extractor
SLOT_EXTRACTOR_BACKEND_CONFIG=configs/inference/your-backend.yaml
RAG_MODE=mcp
RAG_MCP_REPO=packages/modular_rag_mcp
RAG_COLLECTION=enterprise_after_sales
```

槽位 backend 配置路径相对 `packages/slot_extractor` 解析。RAG MCP 的 `main.py` 启动真实 stdio 协议服务，三个工具分别是 `query_knowledge_hub`、`list_collections`、`get_document_summary`。

## 验证

```powershell
python -m compileall -q agents api config db services evaluation scripts app.py
python scripts/verify_repository.py
pytest
python -m evaluation.runner --fail-on-gate
```

仓库验证脚本会检查两个集成组件、内部默认路径、关键入口以及旧领域术语，CI 使用同一检查避免回归。

本次干净 Python 3.12 环境验证基线为：根服务 25 项、槽位组件 290 项、RAG 单元 1205 项、MCP stdio/进程级 E2E 13 项，共 1533 项 pytest 通过；另有 10/10 EDD case 通过。真实 Azure/OpenAI/Ollama、外部 Chroma 数据和本地 llama-server 用例不伪装为离线通过，边界与复现命令见测试报告。

## 文档

- [集成边界与产物清单](packages/README.md)
- [盘点与差距分析](docs/GAP_ANALYSIS.md)
- [系统架构与数据模型](docs/ARCHITECTURE.md)
- [API 清单](docs/API.md)
- [EDD 与 CI 门禁](docs/EDD.md)
- [测试矩阵与验证结果](docs/TESTING.md)
- [故障处理与运行手册](docs/RUNBOOK.md)
- [性能和容量估算](docs/CAPACITY.md)
- [秋招面试深挖题库与标准回答](docs/INTERVIEW_GUIDE.md)

生产部署前必须替换演示鉴权、配置企业知识库与模型凭据，并完成真实标注集评估、并发压测和故障注入。
