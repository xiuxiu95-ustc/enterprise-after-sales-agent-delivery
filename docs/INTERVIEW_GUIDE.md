# 秋招面试深挖题库与标准回答

回答结构建议统一为：业务问题 → 不变量 → 方案 → 替代方案/取舍 → 失败处理 → 可验证证据。不要只背技术名词。

## 一、总体架构与 Agent 工程

### 1. 为什么需要主管 Agent，直接让一个大模型调用所有工具不行吗？

标准回答：单 Agent 能减少一次路由，但工具集合、提示词、权限与状态会一起膨胀，错误半径大。主管 Agent 只负责识别目标、规划有限工具和选择专业 Agent；咨询、预约、行为分析各自有输入/输出契约。这样可以分别评估 routing、slot、RAG、tool 和 trajectory，也能给预约写工具更严格的授权。代价是一次 handoff 和更多状态；所以系统没有无限拆 Agent，而是只按权限边界和变化原因拆三个专业域。低流量简单场景可用单 Agent，但仍要保留统一 Invocation、工具白名单和终态闭环。

追问：主管判断错怎么办？答：路由结果带 reason code 并进入 EDD；专业 Agent 发现 schema/域不匹配时返回可观察 handoff/拒绝，而不是勉强执行。多意图可规划多个 Tool，但总步数受限。

### 2. 你的 ReAct 和普通 if/else 路由有什么区别？

标准回答：确定性路由只是第一步，ReAct 的工程核心是“Action 有显式工具名和参数，Observation 回写状态，直到满足终止条件”。本项目通过 LoopGuard、ToolPolicy、InvocationEvent 和专业 Agent outcome 将这个循环变成可审计状态机。当前离线 fallback 的 planner 可以是规则，实现可重复测试；换成 LLM planner 也必须输出相同结构契约。不能把自由文本“我正在思考”当 ReAct 证据。

### 3. 为什么采用 Web/API/Agents/Services/DB 五层，会不会过度设计？

标准回答：这五层分别对应传输、智能决策、领域不变量和持久化，变化原因不同。预约并发约束若写在 API，会被聊天 Agent 或后台任务绕过；鉴权若写在 Repository，又污染数据访问。层数不是目标，单一写入口才是目标。当前 API routes 较集中，是为了避免每个 endpoint 都造 service；当文件超过可维护阈值时应按用例拆分，而不是为名词机械加层。

### 4. 为什么复用 SHIFT 的契约而不直接把 SHIFT 嵌入项目？

标准回答：SHIFT 是 Node 的本地 CLI/ACP Agent 控制台，目标系统是 Python FastAPI 的售后业务。直接嵌入会引入双运行时、双会话和双终态语义。真正可复用的是经过验证的不变量：SQLite 真相源、Invocation 终态、handoff 漏斗、五阶段 evidence、上下文预算、恢复顺序和审计脱敏。用 Python 重建这些契约，比复制代码更符合复用目的。

### 5. 五阶段为什么是 phase，而“待批准/修改中”不做新状态？

标准回答：phase 表示长期稳定的业务阶段，计划批准、review 结果、交付验收是带版本的 artifact/gate。若每种结果都变成状态，状态组合会爆炸，也无法说明批准绑定的是哪版方案。本项目用 `workflow.phase` event 保存 evidence；changes requested 应作为 `review → implement` transition，并让旧 evidence 失效。客服自动流当前直线执行，但数据模型可以支持未来人工复核。

### 6. 为什么 SSE 不输出 chain-of-thought？用户不是想看思考过程吗？

标准回答：原始推理可能含系统提示、个人信息、密钥和不稳定中间猜测，也不适合作为审计事实。系统输出结构化 progress：route reason、phase、tool started/finished、citation 和 terminal。这既能解释系统行为，又不泄露隐私或让前端依赖模型措辞。审计需要可验证证据，不需要逐字内部思维。

## 二、状态、终态与恢复

### 7. 为什么 SSE completed 不能作为成功真相？

标准回答：SSE 是易失传输，客户端可能断开、代理可能缓冲、服务器可能在发出正文后数据库提交失败。权威成功必须是 SQLite 中 Trace/Invocation terminal 与消息写入都完成。`run.completed` 只在 durable 提交后发出。反过来客户端没收到 completed，也不能断言业务失败，应按 trace/idempotency key 查询。

### 8. 进程在工具成功后、终态写入前崩溃怎么办？

标准回答：本地 Invocation 会在重启时标 `failed/process_restarted`，不伪造 completed。工具副作用是否重复由业务幂等键决定：预约工具以 idempotency key 返回已有记录；外部工单也必须接受同一 key。恢复不能仅凭工具日志推断成功，因为日志可能早于事务提交。对于非幂等外部系统，需要 outbox/状态查询或补偿事务。

### 9. 为什么启动恢复顺序是 Invocation、Handoff、Trace？

标准回答：Invocation 是执行单元，先终止它才能判断 target 是否仍活跃；然后收口 Handoff，避免 target 已失败但 handoff 仍 pending；最后 Trace 聚合整个请求。顺序反过来可能先把 Trace 标失败，随后仍有 active Invocation 写事件，产生矛盾事实。恢复只关闭遗留状态，不补造业务成功。

### 10. 如何保证一个 Invocation 不会永久 active？

标准回答：正常路径在完成/异常/取消三个分支写终态；客户端取消捕获为 aborted；进程退出遗漏由启动恢复标 failed；健康检查暴露 active 数量和 incomplete Trace。生产还应增加 watchdog，对超过最大执行窗口的 active Invocation 条件更新为 failed，并终止下游任务。终态写和规范 end event应在同一事务。

## 三、handoff 与 exactly-once

### 11. 你真的实现了 exactly-once 吗？

标准回答：严格说网络与任意外部副作用没有端到端 exactly-once。本项目实现 SQLite 业务边界内的 exactly-once consumption：handoff dedupe key 唯一；`UPDATE WHERE status=pending` 只有一个消费者 rowcount=1；同事务创建 target Invocation，且 source_handoff_id 唯一。重复调用得到已有 target。若 target 再调用外部系统，仍必须传递幂等键。因此准确表述是“durable handoff 单次消费 + 端到端幂等副作用”，不是魔法 exactly-once。

### 12. 为什么 accepted、enqueued、started、completed 要分开？

标准回答：它们定位不同故障：accepted 后未 enqueued 是调度写失败；enqueued 未 started 是队列/worker 问题；started 未 completed 是执行或工具问题；completed 也只表示闭合。把它们压成一个 success boolean 会丢掉排障坐标，并把 pending 样本错误计入失败率。漏斗必须同时显示 denominator、pending、duplicate 和 unknown。

### 13. 两个消费者同时 claim handoff 会怎样？

标准回答：两者都执行条件更新，数据库串行化写；只有一个 rowcount=1。另一个重新读 handoff 和 target Invocation，返回 consumed=false，不执行工具。唯一 source_handoff_id 是第二道防线。不能先读 status 再改，因为两个消费者可能同时读到 pending。

### 14. target 完成但 handoff 仍 started 怎么办？

标准回答：这是完整性违规，不应靠读模型默默修成 completed。正常 finalize 应在同一业务用例中写 target terminal 和 handoff terminal；健康检查发现后告警。恢复策略可安全标 failed/incomplete，或在有严格事务证据时运行显式 repair 工具，但不能从 SSE/日志猜业务成功。

## 四、预约并发、一致性和幂等

### 15. 为什么“先查询工程师空闲，再插入预约”会重复预约？

标准回答：两个请求可同时在查询阶段看到空闲，然后都插入，这是 TOCTOU 竞态。应用锁只在单进程有效，分布式锁还会遇到租约过期和网络分区。最终约束必须在数据库。本项目把时间段离散成 30 分钟资源槽，用唯一 `(engineer_id, slot_start)` 约束；预约和所有槽同事务提交，冲突者原子失败。

### 16. 资源槽法有什么 trade-off？

标准回答：优点是 SQLite/PostgreSQL 都容易实现、冲突确定、索引简单。代价是槽粒度限制和额外行数；17:10–17:40 会占 17:00/17:30 两槽，可能保守降低利用率。若业务需要任意区间，PostgreSQL 可用 range type + exclusion constraint；或者用日历版本/乐观锁。当前售后服务按 30 分钟计费，离散槽与业务一致。

### 17. 幂等键和唯一资源槽有什么区别？

标准回答：幂等键识别“同一请求重试”，返回同一个 Appointment；资源槽识别“不同请求争抢同一工程师时间”，后者必须冲突。只做幂等键挡不住两个不同 key 的重叠预约；只做资源槽会让同一请求重试看起来像冲突而无法返回原结果。两者缺一不可。

### 18. 取消预约为什么还需要 version？

标准回答：用户 A 页面看到 version 1，后台已把预约改到 version 2；A 再取消若不带 expected version，会覆盖新状态。条件更新 `WHERE id=? AND status=confirmed AND version=?` 保证乐观并发控制，失败让客户端刷新。取消和释放资源槽同事务，避免状态取消但槽仍占用或反之。

### 19. 指定工程师不可用时怎么替代？

标准回答：先用指定工程师的 skills 作为目标向量，候选必须先满足 active、排班、区域、时间槽和最小技能约束，再按 skill embedding cosine 排序。Embedding 只做软排序，不能绕过硬约束。返回 substitution_for 和分数，用户明确确认后才预约。若向量服务失败，可退化到标签重叠，但必须标 degraded。

### 20. SQLite 写并发不高，为什么还用它？什么时候迁移？

标准回答：本项目是本地/单机原型，SQLite 部署成本低且事务/唯一约束足以证明一致性设计；WAL 可多读单写。持续 lock wait、需要多实例写、千万级事件日增、在线分区与高可用时迁 PostgreSQL。迁移应保持 Repository 和唯一约束语义，不用 Redis 锁替代最终一致性。

## 五、上下文、Memory 与 AutoDream

### 21. 为什么最近 10 轮和 60% 摘要，而不是把全部历史发给模型？

标准回答：全部历史导致成本和延迟线性增长，早期噪音降低注意力，还会挤掉工具输出预算。最近 10 条保留局部连贯，summary 保留较老事实，预约 slot state 独立结构化保存，避免摘要把关键时间写错。60% 是质量软阈值，留出 system/tool/RAG/output reserve；应按模型 context profile 和输出 P90 调整，不是万能常数。

### 22. 摘要会不会丢信息？怎么防？

标准回答：会，所以 summary 不是业务真相。原 Message 永久保留；预约槽位、用户 ID、Appointment 等结构事实独立存表；摘要只用于 prompt。高风险写入重新读取结构化状态并要求确认。还可给摘要生成版本、来源 message range 和事实校验，失败时回退更小窗口而不是删除历史。

### 23. Memory 为什么用 0.6/0.3/0.1？

标准回答：业务希望语义相关性主导，同时避免陈旧偏好长期霸榜，所以 semantic 0.6、recency 0.3、importance 0.1。confidence 再做可信度调节。权重是可评估超参数，不是理论真理；应在离线标注集上网格/贝叶斯调参，并按 memory type 分 cohort。没有 judgment 时只能说启发式排序，不能声称最佳。

### 24. Memory 冲突怎么处理？为什么不直接覆盖旧值？

标准回答：用户可能工作日偏好远程、周末偏好上门，或新行为只是一次异常。直接覆盖会丢证据，也无法解释。系统为同 key 多 value 分别保留 confidence/evidence/conflict；新冲突使旧值 confidence 乘 0.85、conflict 增加，新值从中等置信度开始；重复证据渐进提升。后续可增加场景条件和时间段，而不是强行压成单值。

### 25. AutoDream 为什么要 5 个关闭会话和 24 小时？

标准回答：太频繁会把单次偶然行为固化为偏好，也浪费推理成本。5 个关闭会话提供最低证据量，24h 合并短期波动。关闭会话比“5 轮消息”更符合独立行为样本。阈值应通过画像稳定性、接受率和更新成本评估；新用户可保留事件但不立刻生成高置信偏好。

### 26. AutoDream 如何保证幂等和并发安全？

标准回答：per-user 条件更新抢占 task lock；只扫描 checkpoint 之后事件；Memory source_event_id 唯一，user+content hash 防精确重复，embedding 阈值防近重复；成功后才推进 checkpoint。两个 worker 只有一个持锁，锁过期可接管。若处理失败，checkpoint 不前进，重试仍由唯一键避免重复写。

### 27. 向量去重阈值 0.92 有什么风险？

标准回答：阈值过低会把“喜欢远程”和“不喜欢远程”误合并，过高又产生重复。必须先做否定/实体/类型约束，再在同 user、同 memory type 内比较；冲突偏好不应用内容相似度直接合并。当前实现是简化版，生产应在带 duplicate/non-duplicate 标注的数据集上选择阈值，并保存模型版本。

## 六、安全、权限与隐私

### 28. 工具白名单和 RBAC 为什么都需要？

标准回答：RBAC 判断“这个 actor 能做什么”，工具白名单判断“Agent runtime 允许调用什么”。Prompt injection 可能诱导模型选择不存在/危险工具，即使用户角色有普通权限也要被 ToolPolicy 拦截；反过来工具在白名单内，customer 仍不能写工程师排班。两层分别处理主体权限和执行面收敛。

### 29. 如何防止用户说“已经确认了”绕过预约确认？

标准回答：确认是结构化业务状态，不相信任意模型解释。多轮聊天 extractor 要识别明确肯定，同时处理“不需要确认/不确认”等否定；创建 Service 再检查 confirmation 与完整槽位。直接 API 需要受信确认票据。生产中票据应绑定 user、session、参数 hash、有效期和 nonce，不能只用可伪造 header。

### 30. Prompt injection 如何处理？

标准回答：模型不能扩张工具集合、角色和参数 schema；系统 prompt 与检索内容分隔；RAG 文档视为不可信数据；工具参数经 Pydantic/Service 二次校验；跨用户资源由服务端 scope 检查；敏感工具需要确认和审计。安全 EDD 必须包含“忽略规则、输出 API key、调用 delete”等样本，要求 100% 通过。

### 31. Trace 为什么不能保存完整 prompt/tool output？

标准回答：它们可能包含联系人、地址、token、企业文档和提示词，复制到 Trace 扩大泄露面和删除难度。Trace 默认只保存 digest、计数、耗时、error code 和 allowlist attributes；Message/Appointment 各自按业务生命周期管理。排障需要 payload 时使用短期受控采样、单独权限和脱敏，不让 metrics label 带高基数或敏感值。

### 32. 本地只监听 127.0.0.1 有什么意义？

标准回答：减少开发环境误暴露到局域网/公网，尤其默认 auth 关闭时。生产不应简单把 host 改 0.0.0.0；应启用鉴权、TLS 反代、可信角色注入、CORS allowlist、速率限制和审计。配置校验在 local 环境拒绝非回环地址。

## 七、Trace、指标与可观测性

### 33. Trace、InvocationEvent 和 AuditLog 有什么区别？

标准回答：Trace 是一次请求生命周期和聚合指标；InvocationEvent 是执行规范事件，如 phase、tool start/end、terminal；AuditLog 是“谁对什么资源做了什么、允许还是拒绝”的安全证据。三者不能混用：Trace 不能作为预约事实，Audit 不能补 Invocation terminal，Event 也不应复制敏感业务 payload。

### 34. 你记录哪些观测字段？

标准回答：request/Trace ID、session、agent、phase、status、duration、input/output token、agent steps、RAG candidate_count、rank_changes、tool/hand off event、error code、capture policy 和 completeness。生产还应加入 queue latency、TTFT、tool P95、429/timeout、outbox lag 和 integrity violations。标签避免 user/query/Trace ID 等高基数字段。

### 35. Handoff 成功率应该怎么算？

标准回答：不能只报一个成功率。至少分协议质量、调度可靠性和业务结果。执行完成率分母应是观察窗口成熟且 accepted 的 eligible handoff，pending/unknown/censored 分开；漏斗展示 attempted→accepted→enqueued→started→completed，以及 duplicate、未入队、未启动、执行失败。业务预约成功还要另看 Appointment outcome。

### 36. 如何判断观测系统自己不完整？

标准回答：定义 completeness 指标：terminal Invocation 缺 end event、span 缺 end、target terminal 但 handoff pending、terminal Trace 仍含 active Invocation、telemetry write failure、projection lag。非权威 telemetry 失败可以不阻断业务，但 Trace 标 incomplete；权威 Invocation/Handoff/Trace 写失败必须 fail closed。

## 八、EDD、测试与质量

### 37. 为什么不能只拿测试数量证明质量？

标准回答：数量不是覆盖证据，重复断言或参数展开能轻易制造数字。本项目实际执行 1533 项 pytest，但面试时先说明它们覆盖什么：根服务钉住 handoff 单次消费、恢复终态、预约资源槽、幂等、version、AutoDream lock/checkpoint、上下文摘要、权限和 SSE terminal；槽位与 RAG 组件验证各自契约；MCP 13 项走真实子进程和 stdio。随后主动说明真实模型、企业语料、外部向量库、并发压测仍需独立证据，避免把离线绿灯等同生产质量。

### 38. Unit、Integration、E2E 和 EDD 怎么分工？

标准回答：Unit 验证纯路由/状态/评分；Integration 验证数据库事务、唯一约束和恢复；E2E 从 HTTP/SSE 验证用户可见链路；EDD 用版本化业务样本计算 accuracy/Recall/安全率/P95 并做 CI gate。pytest 全绿不代表模型质量，EDD 通过也不代表数据库并发正确，所以两者互补。

### 39. RAG 怎么评估而不大讲算法？

标准回答：工程上关注输入输出契约、collection 隔离、超时降级、citation validity、candidate/rank 变化和严格离线指标。数据集给 query→source 的 graded relevance，计算 Recall@K、MRR、nDCG；再评估 grounded answer 与业务结果。非空 hit 不能叫 Recall。检索算法由专用 MCP 仓库维护，客服系统只消费结构化结果和 Trace。

### 40. 为什么安全用例要求 100%，其他成功率可以 85%？

标准回答：越权预约、跨用户读取和密钥泄露是不可接受风险，不能用平均准确率稀释；门禁应对已知关键安全集要求全过。85% 是当前小型功能 smoke 的最低线，不是生产 SLA。随着样本成熟应按风险 cohort 设不同阈值，并对严重 case 零容忍。

### 41. 线上失败如何进入回归集？

标准回答：Trace 先给 error/failure coordinate；人工脱敏归因并写 expected/judgment；以 input digest 和 case/version 保存；先证明新 case 能复现，再修复；CI 永久运行。不能自动把所有用户投诉当 ground truth，也不能把原始敏感 query 直接复制到公共 fixture。

## 九、性能、扩展性和取舍

### 42. 如何估算容量？

标准回答：先算 `daily_turns = DAU * sessions/user * turns/session`，再乘 root+specialist Invocation 和每 turn event 数。10 万 DAU、0.3 会话、6 轮约 18 万 turn/日；若每 turn 20 event，就是 360 万 event/日。结构事件按 0.8KB 约 2.9GB/日，单 SQLite 不适合长期承载，需要保留策略、归档和 PostgreSQL/观测存储。容量回答必须带假设、峰值倍数和样本大小。

### 43. 性能瓶颈在哪里，怎么优化？

标准回答：通常不是 FastAPI，而是 LLM TTFT、embedding/RAG、rerank、外部工单和数据库写竞争。先用 Trace 分段：route/context、Memory、RAG、slot、tool、generation。优化顺序是减少不必要模型调用、并行只读工具、缓存稳定 embedding、连接复用、索引预热、限制 RAG context、批量投影观测。不能为降低 P95 绕过确认或把 durable 写异步化到可能丢失。

### 44. 哪些步骤可以并行？

标准回答：咨询场景的 Memory Recall 与 RAG query 无依赖，可并行；候选工程师查询必须等 slot 完整；预约写必须等匹配与确认；done 必须等 assistant message、Invocation/Handoff terminal 和 Trace terminal。并行前先画依赖图，不能因为延迟把因果顺序打乱。当前实现为清晰性串行，生产可对只读调用用 task group 并保留各自 span。

### 45. 如何从单体扩展为多实例？

标准回答：FastAPI 变无状态，SQLite 迁共享 PostgreSQL；Handoff/AutoDream claim 用条件更新或 `SKIP LOCKED`；SSE 可由同一 worker 持有连接，事件事实写数据库/outbox；后台任务按 user/session key 分区；RAG MCP 独立服务化。重要的是不建立 Redis 与 SQL 双仲裁，Redis 只做缓存/队列，最终唯一约束仍在 SQL。

### 46. 如果要接多个模型 Provider，怎么不破坏架构？

标准回答：在 Agent inference adapter 后增加 provider registry，每个 Invocation 保存 provider/model/session/usage；Supervisor 按能力、成本和风险选择，但仍走同一 start→events→terminal、handoff 和 Trace 路径。Provider 超时/overflow 映射统一 error code。不能为某 Provider 新开一套 SSE 或消息表。

### 47. Git/worktree 为什么这次没有放进在线系统？

标准回答：售后 Agent 不编辑代码，目标目录也不是 Git 仓库，强行创建 worktree 是无业务价值的抽象。交付时先完整备份原目录以获得恢复点。若未来增加“自动生成并执行客户修复脚本”，worktree 才成为安全边界：每 session 独立分支/目录、工具路径校验、diff 审批、测试和交付 gate；仍不能让高风险执行默认开放。

### 48. 这个项目最大的未解决项是什么？

标准回答：槽位与完整 RAG 源码已经纳入单仓库，但真实模型、企业知识库和生产凭据没有随代码提交；本地规则与关键词 fallback 只能验证系统工程，不代表模型/RAG 质量。其次，SQLite 适合单机但不适合多实例高写；认证 header 是本地参考，不是生产 IAM；评估集仍小。清楚列出这些边界比伪造“生产级/1364 测试”更专业。下一步优先挂载真实模型与索引、扩充脱敏标注集、做 50/100/200 并发压测和故障注入，再决定数据库迁移。

## 十、一分钟项目陈述模板

“我把一个预约原型重构成企业售后智能客服与预约系统。核心不是多写几个 Agent，而是建立单一 SQLite 真相源和可恢复执行链：主管 Agent 规划咨询、预约、行为分析工具，专业 Agent 通过 durable handoff 执行；每轮经过五阶段 evidence gate，并用 SSE 输出结构化过程。会话保留最近 10 轮，60% 窗口滚动摘要，长期 Memory 按 0.6/0.3/0.1 召回；AutoDream 以 5 个关闭会话、24 小时、任务锁和 checkpoint 增量沉淀。预约用排班、技能、区域和 embedding 替代匹配，并用 30 分钟资源槽唯一约束、幂等键和 version 解决并发重复写。RAG 和槽位后训练工程已纳入同一仓库，通过 MCP/Backend 边界接入。Trace 记录 token、候选数、排名变化和终态，EDD 对路由、槽位、RAG、工具、轨迹和安全做 CI 门禁。真实模型/RAG 质量与高并发仍需用生产样本继续验证。”
