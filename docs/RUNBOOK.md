# 运行手册与故障场景

## 启动前检查

- local 模式只监听 `127.0.0.1`；非本地部署必须由网关终止 TLS。
- `AUTH_REQUIRED=true` 时不能使用默认 token。
- SQLite 目录可写，WAL、foreign key 与 busy timeout 已启用。
- `RAG_MODE=mcp` 时确认目标仓库、配置、embedding/vector store 和 collection 可用。
- 配置外部 slot backend 时先单独运行该仓库的 backend smoke。

## 健康检查

`GET /api/v1/health` 重点看：

- `active_invocations`：短时存在正常；长时不下降说明 terminal closure 失败。
- `orphan_handoffs`：非 0 即 degraded，需要看 source/target Invocation。
- `incomplete_traces`：历史失败可存在，但窗口突增需告警。

## 常见故障

### SSE 有正文但没有 completed

1. 查询 Trace/Invocation durable 状态，不以浏览器为准。
2. 若客户端断开，应为 aborted；若仍 active，重启恢复会标 failed。
3. 检查 `invocation.ended` 事件是否存在；缺失属于完整性故障。
4. 不要人工补 completed；先定位事务失败，再重放原幂等请求。

### handoff pending/started 卡住

检查 target Invocation：

- 无 target：claim 后创建 Invocation 的事务失败，应 fail closed。
- target active：Agent/Tool 卡住，按超时策略终止 target 与 handoff。
- target terminal 但 handoff 非 terminal：finalize 写失败，属于完整性违规；不可从 SSE 猜成功。

### 重复预约或时间冲突

- 同一幂等键：应返回原 Appointment，不新增资源槽。
- 不同键重叠：应收到唯一约束映射的 `appointment_time_conflict`。
- 若外部工单系统也写入，必须把本项目 idempotency key 传递下去；否则本地 exactly-once 不能覆盖外部副作用。
- SQLite 高写竞争频繁出现 busy 时，先缩短事务和增加重试抖动；再评估迁移 PostgreSQL，不要加进程锁作为第二真相源。

### AutoDream 重复/不运行

- `not_due/minimum_closed_sessions`：确认 session 是否真正 close，而不是只有 completed turn。
- `not_due/minimum_interval`：查看 last_run_at。
- `locked`：检查 locked_until；过期锁可由下一任务原子抢占。
- 重复 Memory：核对 source_event_id、content hash 和近重复阈值。
- checkpoint 只在成功后推进；失败时不要手工跳过事件。

### RAG 无结果或超时

- 查询 source/degraded 字段；local fallback 不等于生产 RAG。
- 检查 collection、embedding provider、BM25 index、vector store 和 reranker。
- Agent 应拒答或声明降级，不允许凭模型常识补造企业政策。
- Trace 查看 candidate_count 和 rank_changes；真实 query 文本默认不进 Trace。

### 上下文膨胀

- 查看 session.context_tokens、summary_generation 和最近消息数。
- 达 60% 后应只注入 summary + 最近 10 条 + slot state。
- summary 不能替代预约权威槽位；槽位永远单独结构化注入。
- 如果模型输出预算变大，应降低 summary threshold 或增加 reserve，而不是等 provider overflow。

### Agent loop

- `repeated_tool_signature`：同工具同参数重复，通常是工具结果未写回状态或 planner 未识别终止条件。
- `max_agent_steps_exceeded`：默认 6 步，先分析轨迹，不盲目调大。
- 工具失败必须转成结构化 observation；空 observation 会诱发重复调用。

## 备份与恢复

SQLite 使用 WAL 时，热备份必须使用 SQLite backup API 或在一致性检查点后复制 DB/WAL/SHM，不能只复制 `.db`。恢复演练应验证：

1. foreign key integrity；
2. terminal Invocation 存在 end event；
3. target terminal 不对应 pending handoff；
4. confirmed Appointment 的资源槽完整；
5. AutoDream checkpoint 指向存在的 event。

## 数据保留与隐私

- Message/Appointment/Memory 属于业务数据，按用户删除与法规策略处理。
- Trace/Audit 只保存结构字段并配置独立保留期。
- 任何导出再次执行 allowlist/redaction；脱敏失败时拒绝导出。
- 不把 API key、Authorization、联系人或完整工具输出写入 metrics label。

