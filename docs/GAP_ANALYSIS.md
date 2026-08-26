# 仓库盘点、差距与迁移映射

## 1. 盘点结论

### 原目标仓库

`D:\smart-appointment-ai-agent-master` 有 78 个源码/文档文件，目录上已经分为 Web、API、Agents、Services、DB，但核心语义仍是售后服务门店：

- `Engineer` 只有姓名、性别、力度/倾向，不能表达企业工程师技能、区域、员工编号和排班容量。
- 预约状态保存在进程对象与全局 `busy_periods_dict`，预约表本身没有可靠持久化、幂等键、版本或并发约束。
- 分类 Agent 是一次路由器，不是有步数预算、工具白名单和终态证据的 ReAct 主管 Agent。
- 流式接口输出自定义字符串标签，没有标准 SSE event/id/data，也没有持久化 Invocation/Trace 终态。
- user behavior 有表，但短期上下文、长期 Memory、Recall 排序、冲突治理和 AutoDream 均未形成闭环。
- README 声明兼容 MCP/流式/多 Agent，但数据库真相源、handoff 单次消费、审计和评估门禁未实现。
- 4 个测试文件仍验证售后服务、性别和工程师字段；本机基线因未安装 pytest 无法运行。
- 目标目录不是 Git 仓库，无法原地使用 worktree 或依靠 Git 回滚。

### SHIFT

`D:\SHIFT-master` 是 Node.js 本地多 Agent 控制台。可复用价值主要在可靠性契约：

- SQLite 唯一在线真相源；SSE/JSONL/内存状态不能仲裁业务成功。
- Invocation 必须写 started 和 completed/failed/aborted 终态。
- handoff 的 accepted、enqueued、started、completed 分开；重复和已完成不混入成功率。
- `discuss → implement → review → deliver → done` 是稳定 phase，变更请求是 transition，不扩张状态。
- context 在调用前投影，保留输出预算；达到软阈值后 seal/summary，接近物理上限才紧急停止。
- Trace/审计只保存允许字段，生命周期事实与派生 span/link 分离。
- 启动顺序先收口 active Invocation，再处理 pending Handoff，最后收口 active Trace。

SHIFT 的 Node Provider、CLI 进程监督和前端不能直接搬到 FastAPI 业务系统，因此本项目实现同等契约的 Python 版本。

### 槽位抽取组件

`packages/slot_extractor` 已纳入单仓库并提供：

- `Backend.generate(messages, GenerationParams)` 统一推理接口；
- mock、llama-server、OpenAI Responses 后端工厂；
- JSON schema 约束输出、工具 loop、结构化评估。

集成时已把训练 schema、prompt、工具循环、评估断言和夹具改为工程师能力等级、问题类别与技能偏好。在线预约仍由 `SlotExtractorAdapter` 提供企业 schema 和业务状态机；未配置模型时启用确定性规则降级以保证测试可运行。

### RAG MCP 组件

`packages/modular_rag_mcp` 已纳入单仓库，实现 BM25 + Dense、RRF、Cross-Encoder/LLM rerank、Trace 和三个 MCP Tool。`RagGateway` 通过同进程或 MCP stdio 适配：

- `query_knowledge_hub`
- `list_collections`
- `get_document_summary`

本地降级检索只用于开发；完整质量以集成组件的标注集评估为准。

## 2. 差距闭环矩阵

| 目标 | 原状态 | 新实现 | 关键路径 |
|---|---|---|---|
| 主管 ReAct | 一次分类转发 | 规划、白名单、步数/重复签名 guard、专业 Agent dispatch | `agents/supervisor.py`, `services/orchestrator.py` |
| 五阶段流 | 无持久 phase/gate | 五 phase + 每阶段必需证据 + durable event | `services/workflow.py` |
| SSE | 自定义 token 字符串 | 标准 event/id/data，含工具、handoff、引用和终态 | `api/routes.py`, `services/orchestrator.py` |
| Invocation/历史 | 仅 chat history | session/message/invocation/event/trace 全持久化 | `db/models.py`, `db/repositories.py` |
| handoff | 进程内直接调用 | dedupe、原子 claim、唯一 target Invocation、状态漏斗 | `Handoff`, `HandoffRepository` |
| 上下文窗口 | Agent 实例局部 history | 最近 10 轮、预约槽位、60% 滚动摘要 | `services/context.py` |
| 长期 Memory | 行为与偏好计数 | 咨询/预约/偏好 Memory、加权 Top-5 Recall | `services/memory.py` |
| AutoDream | 定时推荐脚本 | 5 个关闭会话 + 24h、锁、checkpoint、去重、冲突降权 | `services/autodream.py` |
| 企业预约 | 工程师性别/力度 | 工程师技能/区域/排班/专长向量替代 | `services/appointment.py` |
| 并发一致性 | 先查后写内存 busy | 30 分钟资源槽唯一约束 + 事务 + 幂等键 + version | `AppointmentReservation` |
| RAG | 目标仓库自建 FAISS | 3 Tool MCP adapter；本地仅降级 | `services/rag.py` |
| 槽位 | 售后服务 prompt/schema | 复用推理 Backend，企业 JSON schema 和规则 fallback | `services/slot_extraction.py` |
| 权限/安全 | CORS `*`、无授权 | 角色权限、确认、参数限制、工具白名单、回环监听、脱敏 | `services/security.py`, `config/settings.py` |
| Trace/审计 | 普通日志 | duration/token/candidates/rank/steps/span + 审计 allowlist | `Trace`, `TraceSpan`, `AuditLog` |
| EDD | 4 个旧业务测试文件 | 分层 cases、失败回归表、CI 阈值门禁 | `evaluation/`, `tests/`, `.github/workflows/ci.yml` |
| API | 功能分散且字段旧 | 28 个 `/api/v1` 路径 | `api/routes.py` |

## 3. 未直接复用项

- SHIFT 的 Git worktree manager 未进入在线售后主链路。原因：目标目录本身不是 Git 仓库，业务 Agent 不具备文件编辑工具，把 worktree 加入运行时只会制造无效复杂度。原目录在交付时做完整目录备份；未来若增加“生成/执行客户脚本”的高风险 Agent，必须先初始化 Git，再按 session 创建 worktree 并让文件写工具只访问该目录。
- SHIFT 的多 Provider CLI 调度没有复制。企业客服的专业 Agent 当前是同进程领域 Agent，模型推理通过明确 adapter 注入。若未来接多模型，应保持现有 Invocation/Handoff 单一入口，不另开一条运行路径。
- 不用未经验证的测试数量包装质量。本次交付在干净 Python 3.12 环境实际执行 1533 项 pytest（根服务 25、槽位 290、RAG 单元 1205、MCP 进程级 13）和 10 个 EDD case；真实外部模型/向量库用例单独列为环境依赖。数量仍不是覆盖证据，真实 RAG 标注集、模型回归集和压测样本需要业务数据持续扩充。
