# EDD 评估体系与 CI 门禁

EDD 在本项目中指 Evaluation-Driven Development：先定义可判断的业务样本、指标语义和阈值，再让实现与失败回归集共同演进。它不是“pytest 通过”的同义词。

## 分层

| 层 | 判断对象 | 主要指标 | 当前例子 |
|---|---|---|---|
| routing | 主管选择意图/Agent | accuracy、unsafe route | 咨询、预约、画像 |
| slot | 槽位抽取与合并 | field F1、missing accuracy、confirmation precision | 企业服务/问题/时间/时长/地址 |
| rag | 知识检索 | labeled Recall@K、MRR、nDCG、citation validity | 保修/SLA |
| tool | 工具选择与参数 | whitelist pass、schema validity、tool success | 禁止 delete_database |
| trajectory | 整条 Agent 轨迹 | task success、max steps、loop rate、P95、token | 工具数不超过 6 |
| safety | 越权/注入/敏感操作 | 必须 100% 通过 | 无确认不写预约 |

本地 `evaluation/cases.json` 是小型 smoke gate。严格 RAG 指标需要在 RAG 仓库维护带 graded relevance 的业务数据集，不能用“返回了 1 条”冒充 Recall。

## 门禁

当前默认阈值：

```json
{
  "task_success_rate": 0.85,
  "safety_pass_rate": 1.0,
  "p95_ms": 2500,
  "max_agent_steps": 6
}
```

CI 顺序：

1. compileall：阻断语法/导入期错误。
2. Unit/Integration/E2E：钉住状态、事务和 API 可观察行为。
3. EvaluationRunner：计算分层样本和门禁。
4. 任一 gate false 则 CI 失败。

## 失败回归集

失败 case 写入 `evaluation_failures`：case ID、layer、input digest、expected、actual、Trace ID、首次/最近时间和 occurrences。只保存 digest 与结构值，不复制敏感 query。重复失败更新 occurrences，不制造多个语义相同样本。

线上失败进入离线回归集的流程：

```text
Trace failure/error code
  -> 人工脱敏与归因
  -> 给出 expected/judgment
  -> 加入 versioned cases
  -> 重现失败
  -> 修复
  -> CI 持续门禁
```

## 指标语义

- `Invocation.completed`：执行闭合，不代表 task success。
- RAG `candidate_count>0`：hit，不代表 Recall/正确。
- `handoff.completed`：target 终止，不代表预约成功。
- 安全率的分母只包含成熟、合格的安全样本；pending/unknown 不应当作成功。
- P95 必须同时给样本量、硬件、外部依赖模式。当前多次运行 P95 低于 15 ms，是本地规则/SQLite smoke，不代表真实模型/RAG P95。

## 扩充路线

1. 将真实客服日志脱敏后按产品/地区/意图分层抽样。
2. 槽位评估增加 field-level precision/recall、跨轮状态保留和否定确认。
3. RAG 导入 graded relevance，计算 Recall@5、MRR、nDCG@5 和 scope leakage。
4. Tool 增加下游超时、429、重复回调和参数污染。
5. Trajectory 增加多意图、handoff 修复、模型空输出、client disconnect。
6. Safety 加入 prompt injection、跨用户 IDOR、重复扣费/预约、日志泄密和权限提升。
