# 性能与容量估算

## 估算模型

设日活用户 `U`，每用户日均会话 `S`，每会话平均轮数 `T`，每轮平均 Agent 步数 `A`：

```text
daily_turns = U * S * T
daily_invocations ~= daily_turns * (1 root + 1 specialist)
daily_events ~= daily_turns * (phase/tool/terminal events, approximately 12 + 2A)
```

示例：10 万 DAU、0.3 会话/人/日、6 轮/会话、4 工具步：

- 18 万 turn/日，平均约 2.1 turn/s；10 倍峰值约 21 turn/s。
- 36 万 Invocation/日。
- 约 360 万 InvocationEvent/日（按 20/turn）。
- 如果结构事件平均 0.8 KB，仅事件约 2.9 GB/日；必须限制 payload、分区/归档，而不是无限留在单个 SQLite。

## 延迟预算

建议在线 P95 预算：

| 阶段 | P95 预算 |
|---|---:|
| API 校验 + SQLite started | 50 ms |
| 路由与上下文 | 80 ms |
| Memory Recall | 50 ms |
| RAG hybrid + rerank | 800 ms |
| Slot LLM | 800 ms |
| 业务工具/排班 | 150 ms |
| 首字节编排开销 | 150 ms |
| 总体（不含长文本生成尾延迟） | 2 s 左右 |

真实模型与远程 RAG 需要独立测量 DNS、连接、TTFT、生成吞吐、429 和冷启动。本地 EDD 多次运行 P95 低于 15 ms，只证明规则与 SQLite 热路径。

## SQLite 容量边界

当前实现适合单机原型/中小流量：WAL 支持多读单写，资源槽唯一约束提供可靠一致性。出现以下信号时迁移 PostgreSQL：

- 持续写 QPS 超过单机可承受范围，busy/lock P95 上升；
- 需要多实例写、跨机故障切换、在线 schema migration；
- event/trace 日增达到千万级；
- 需要分区、物化视图或长周期在线分析。

迁移时保持 Repository 契约，使用数据库唯一约束与 `SELECT ... FOR UPDATE`/排他约束。不要用 Redis 锁替代数据库最终约束；锁过期或网络分区会重新打开重复写窗口。

## 扩容策略

1. 无状态 FastAPI 横向扩容；session/Invocation/预约事实进入共享 SQL 数据库。
2. RAG MCP 独立扩容，embedding/rerank 分开限流；collection 索引预热。
3. AutoDream 放到任务队列，按 user key 分区；数据库锁仍是最终所有权。
4. Trace span/指标异步投影到可观测存储，但 source tables 保持权威。
5. 对成功 payload 采样、错误/降级全量；生命周期事件全量。

## Token 容量

prompt 组成：system policy + summary + 最近 10 条 + slot state + Memory Top-5 + RAG context。每轮先估算 `current + prompt + output reserve`；60% 触发摘要是质量阈值，不是物理极限。应对不同模型维护 context profile 和输出 P90 reserve，避免固定字符截断破坏 JSON/tool schema。
