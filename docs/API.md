# API 清单与契约

所有业务接口位于 `/api/v1`，当前有 28 个路径。交互式 schema 以 `/docs` 的 OpenAPI 为准。

## 会话与 Agent

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | durable 状态完整性摘要 |
| POST | `/sessions` | 创建 user 隔离会话 |
| GET | `/sessions/{session_id}` | 会话、轮数、摘要 generation、预约槽位 |
| POST | `/sessions/{session_id}/close` | 关闭会话；AutoDream 只统计关闭会话 |
| GET | `/sessions/{session_id}/messages` | 权威消息历史 |
| POST | `/chat` | 非流式统一 Agent 服务 |
| POST | `/chat/stream` | 标准 SSE 统一 Agent 服务 |
| POST | `/consultations` | 咨询兼容入口，仍走同一 Orchestrator |

### SSE 事件

```text
run.started
progress
handoff
tool.started
tool.finished
text.delta
citation
run.completed | run.failed
```

每个事件含序号、Trace、Invocation、Session 与时间戳。`run.completed` 是展示终态，权威终态仍在 SQLite。服务不输出模型 chain-of-thought。

## 预约与工程师

| 方法 | 路径 | 风险/幂等 |
|---|---|---|
| POST | `/appointments/drafts` | 只更新 session 槽位，不创建预约 |
| POST | `/appointments/confirm` | 中风险；显式确认；必需 idempotency key |
| GET | `/appointments` | 按 user/status 查询 |
| GET | `/appointments/{id}` | user scope |
| POST | `/appointments/{id}/cancel` | 中风险；确认 + expected version |
| POST | `/availability/search` | 只读技能/排班/区域/时间约束匹配 |
| GET | `/engineers` | 只读工程师目录 |
| POST | `/engineers` | 高风险，supervisor/admin |
| POST | `/engineers/{id}/shifts` | 高风险，supervisor/admin |

预约确认示例：

```json
{
  "user_id": "customer-001",
  "session_id": "<uuid>",
  "engineer_id": "<uuid>",
  "idempotency_key": "web-20260826-0001",
  "slots": {
    "service_type": "onsite_repair",
    "issue_category": "network",
    "start_time": "2026-08-27 14:00",
    "duration_minutes": 120,
    "required_skills": ["network"],
    "location": "北京",
    "confirmation": true
  }
}
```

相同幂等键返回原 Appointment；不同幂等键但重叠工程师资源槽返回 `409 appointment_time_conflict`。

## 行为、Memory 与 AutoDream

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/behavior/events` | 以 idempotency key 记录行为 |
| GET | `/behavior/users/{user_id}/profile` | 偏好、置信度、证据数、冲突分 |
| GET | `/memory/users/{user_id}/recall` | 加权 Top-K Recall |
| POST | `/memory/autodream/run` | supervisor/admin；默认遵守 5 session/24h |

`force=true` 只允许管理角色用于运维回放；仍需抢占锁和遵守 checkpoint 幂等。

## 知识 MCP

| 方法 | 路径 | 映射 Tool |
|---|---|---|
| POST | `/knowledge/query` | `query_knowledge_hub` |
| GET | `/knowledge/collections` | `list_collections` |
| GET | `/knowledge/documents/{id}/summary` | `get_document_summary` |

Query 响应包含 `context`、结构化 `citations`、`candidate_count`、`rank_changes`、`source` 与 `degraded`。

## 观测与评估

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/handoffs/{id}` | support+ |
| GET | `/traces/{id}` | support+ |
| GET | `/audit` | supervisor/admin |
| POST | `/evaluations/run` | supervisor/admin |
| GET | `/evaluations/failures` | supervisor/admin |

## 认证约定

本地演示默认 `AUTH_REQUIRED=false`。开启后：

```http
Authorization: Bearer <LOCAL_API_TOKEN>
X-Actor-Id: customer-001
X-Role: customer|support|supervisor|admin
X-Confirm-Token: confirmed
```

这些 header 是本地参考实现。生产中角色与确认票据必须由受信网关/JWT claims 注入，不能相信浏览器任意填写 `X-Role`。

