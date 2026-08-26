# 系统架构与数据模型

## 1. 设计目标与不变量

系统不是“几个 Agent 类互相调用”的演示，而是一条带权威状态、失败语义和审计坐标的业务执行链。必须长期守住：

1. SQLite 是在线事实真相源；SSE、日志、内存对象和 Trace 派生 span 不参与业务恢复。
2. 同一业务语义只有一个写入口：预约由 `AppointmentRepository.create_reserved`，handoff 由 `HandoffRepository`，行为由 `BehaviorRepository.record`，AutoDream 由 `AutoDreamService.run`。
3. Invocation 只能处于 `active` 或一个终态 `completed|failed|aborted`，不允许流输出结束但 durable 状态仍 active。
4. 预约未明确确认不得写入；写入必须同时通过授权、参数校验、幂等和资源槽冲突约束。
5. Agent 只能调用白名单工具；重复工具签名与超步数会终止 loop。
6. Trace 不保存 secret、完整联系人、原始工具 payload 或 chain-of-thought。

## 2. 五层边界

| 层 | 职责 | 禁止事项 |
|---|---|---|
| Web | 非技术用户界面 | 直接读数据库、推断业务终态 |
| API | 认证、参数 schema、HTTP/SSE、依赖装配 | 写领域状态机、自己实现幂等 |
| Agents | 主管规划、专业 Agent 答复、loop guard | 绕过工具策略或 Repository 写库 |
| Services | workflow、appointment、memory、AutoDream、RAG/slot adapter、安全、恢复 | 依赖 Web；建立第二真相源 |
| DB | SQLAlchemy 模型、事务、唯一约束、Repository | 依赖 Agent/API；把 JSONL 当恢复源 |

依赖方向严格向下；`app.create_app` 是 composition root。

## 3. 一次请求的时序

```text
Client             API             Supervisor          Specialist         SQLite/MCP
  | POST stream     |                    |                   |                 |
  |---------------->| validate actor     |                   |                 |
  |                 | persist message, Trace, Invocation started ------------>|
  |                 |------------------->| discuss route     |                 |
  |<-- progress ----|                    | persist phase evidence ------------>|
  |                 |                    | create/claim handoff -------------->|
  |<-- handoff -----|                    |------------------>|                 |
  |<-- tool.started |                    | whitelist/guard   |                 |
  |                 |                    |                   | RAG/slot/tool -->|
  |<-- tool.finished|                    |<------------------|                 |
  |                 |                    | review safety/evidence ------------>|
  |<-- text.delta --|                    | deliver           |                 |
  |                 | persist assistant + done + terminals ------------------>|
  |<-- completed ---|                    |                   |                 |
```

客户端中断会捕获取消信号并把 root Invocation/Trace 标成 `aborted`；未捕获异常标成 `failed`。进程崩溃时，下一次启动由 `RecoveryService` 收口遗留 active Invocation、pending/started Handoff 和 active Trace。

## 4. 五阶段协作流

```text
discuss -> implement -> review -> deliver -> done
```

- `discuss`：证据必须含 route 和 goal。
- `implement`：证据必须含实际/计划工具清单。
- `review`：证据必须含 validation 与 safety 结果。
- `deliver`：绑定 response digest，随后才向客户端发正文。
- `done`：绑定 Trace ID 和 terminal status。

新方案或上游证据变化应创建新 Invocation，不覆写旧证据。`changes_requested` 应记录为事件并回到 implement，而不是增加永久 phase；当前客服主链是单次自动 review，已为未来人工复核预留事件模型。

## 5. handoff exactly-once

“网络 exactly-once”通常不存在，本系统实现的是数据库作用域的业务 exactly-once：

1. `dedupe_key` 唯一，重复创建得到同一 Handoff。
2. 消费者执行 `UPDATE ... WHERE status='pending'`；只有 `rowcount=1` 的调用者取得所有权。
3. 同一事务创建 target Invocation；`Invocation.source_handoff_id` 也是唯一键。
4. 目标终态后 Handoff 才进入 `completed|failed`。
5. 重启发现 pending/started 会 fail closed，不伪造完成。

因此并发消费者最多一个获得权威 target Invocation。外部 Tool 若自身非幂等，仍需把 handoff/业务幂等键传给下游；数据库单次消费不能替外部系统保证副作用。

## 6. 会话、上下文与记忆

### 短期状态

- `ConversationSession.slot_state` 是当前预约草稿的权威快照，状态为 `collecting|awaiting_confirmation|confirmed`。
- prompt context 只取最近 10 条消息，同时注入历史 summary 和 slot state。
- `context_tokens` 用字符估算。达到 `context_window_tokens * 0.60` 且消息超过 10 条时，旧消息滚动摘要；原消息仍保留供审计，在线 prompt 不再重复注入。

### 长期 Recall

Memory 保存 source event、类型、内容 hash、embedding、置信度、重要度和发生时间。排序：

```text
raw = semantic * 0.6 + recency * 0.3 + importance * 0.1
score = raw * (0.7 + confidence * 0.3)
```

recency 使用 30 天指数衰减；返回 Top-5 并更新访问时间。开发环境使用稳定哈希向量，生产可把 embedding provider 适配到真实模型，但评分契约不变。

### AutoDream

触发条件是“自上次 checkpoint 后至少 5 个已关闭会话”且“距上次运行至少 24 小时”。流程：

1. 条件更新抢占 per-user lock，写 `lock_token/locked_until`。
2. 只读取 checkpoint 之后的 behavior event。
3. `source_event_id` 和 user+content_hash 唯一，防重放重复写。
4. embedding 相似度 >= 0.92 视为近重复，只提升已有置信度。
5. 同 key 不同 value 是冲突：旧值 confidence 乘 0.85、conflict_score 增加；新/重复证据按渐进公式提升目标置信度。
6. 成功后同时推进 event 与 closed-session checkpoint，释放锁；失败保留错误，checkpoint 不前进。

## 7. 预约状态与并发

```text
collecting -> awaiting_confirmation -> confirmed -> completed|cancelled|no_show
       |              |                    |
       +-> cancelled  +-> collecting       +-> cancelled
                      +-> expired
```

匹配先过滤：active、排班覆盖、区域、必需技能、时间槽未占用。若指定工程师可用则优先；不可用时用目标技能向量与候选工程师 skill embedding 的 cosine 排序，返回 `substitution_for`，仍需用户确认。

并发防护不采用“先查空闲再插入预约”的乐观假设。预约事务会为覆盖区间生成 30 分钟 `AppointmentReservation`，数据库唯一约束 `(engineer_id, slot_start)`。两个并发请求最多一个提交；另一个收到 `appointment_time_conflict`。同一请求重试由 `Appointment.idempotency_key` 返回原记录。取消使用 `expected_version` 条件更新，避免旧页面覆盖新状态，并在同一事务释放资源槽。

## 8. 外部能力适配

### SlotExtractorAdapter

配置后加载 `post-training-slot-extractor` 的 backend factory，复用模型推理、超时和生成参数；输入企业 JSON Schema。Adapter 输出转换成 `AppointmentSlots`，Service 不依赖某个模型 SDK。未配置时的规则 extractor 是可观察降级，`source=rule_fallback`。

### RagGateway

- `mcp`：以 stdio 启动专用 RAG Server 并调用 3 个 MCP Tool。
- `inprocess`：开发调试时直接调用其 Tool 类。
- `local`：测试用关键词降级，不复制 Dense/RRF/rerank。

生产配置外部模式失败会显式失败/拒答，不静默宣称知识可信。

## 9. 安全模型

- customer 只能访问自己的 session/appointment/memory；support 可读 Trace；supervisor/admin 才能操作工程师、AutoDream、审计和评估。
- 预约创建/取消必须显式 confirmation；直接 API 由 `X-Confirm-Token` 演示，生产应由网关签名确认票据替代。
- Pydantic 限制长度、枚举形状、时长和时间格式；Service 再检查未来时间、状态转换和版本。
- 工具白名单与 API 权限是两层控制，模型输出不能扩张权限。
- Audit 对 token/api_key/contact/phone/email 做字段级脱敏。
- local 模式只能绑定 loopback；CORS 使用显式 origin，不允许 `*`。

## 10. Trace 与审计

Trace 权威记录 request lifecycle：status、输入/输出 token、candidate_count、rank_changes、agent_steps、duration、error_code 和 completeness。InvocationEvent 记录 phase/tool/terminal 规范事件；TraceSpan 是可重建投影。AuditLog 记录 actor、action、resource、allow/deny、risk 和脱敏 payload。

必须区分：Invocation completed 只证明执行闭合，不等于回答正确；RAG hit 只证明返回非空，不等于严格 Recall；handoff completed 只证明目标 Invocation 终止，不等于业务预约成功。EDD 或人工 outcome 才能提供质量证据。

