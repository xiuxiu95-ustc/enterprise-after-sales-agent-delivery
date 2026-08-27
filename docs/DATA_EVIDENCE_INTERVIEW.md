# 数据证据与面试答辩手册

> 核对基线：2026-08-27，仓库提交 `e3b65ec4b3a836b2c1763e2189f05ba401a46640`。本文只陈述仓库中能够定位到原始文件、运行输出或计算过程的数字。后续实验应更新日期、运行环境、数据版本和证据路径，不能覆盖旧口径。

## 1. 一句话结论

项目已经具备完整工程实现、可复现的数据构建流程、实际执行过的小模型 SFT/DPO 实验记录、量化性能实验和 1533 项自动化测试结果；但现有训练与评估样本主要是场景化构造数据，RAG 使用测试文档和弱金标集，尚未接入真实企业客服会话、工单、知识库、工程师排班和线上行为数据。因此，现有数字能证明“工程闭环和离线优化方法成立”，不能证明“已经达到企业生产效果”。

面试推荐口径：

> 我把系统做到了可运行、可训练、可评估和可审计。槽位模块使用版本化场景数据完成了 LoRA SFT/DPO 与量化实验，工程侧有 1533 项自动化测试和 10 条 EDD smoke gate。由于没有企业授权的脱敏数据，我把所有离线指标明确限定为版本回归证据，没有包装成线上准确率。下一阶段是接入真实语料、建立人工金标集和线上指标闭环。

## 2. 证据可信度分级

| 等级 | 定义 | 当前例子 | 面试表达 |
| --- | --- | --- | --- |
| A：本机复验 | 本次在完整依赖环境实际执行并得到输出 | 1533 pytest、10/10 EDD、仓库扫描 | 可以说“本机实测” |
| B：归档实验 | 仓库保存训练日志、预测、scorecard、硬件信息和校验和 | SFT、Round 005/007/008 | 可以说“归档实验记录显示” |
| C：静态实现 | 代码和测试证明机制存在，但没有真实数据效果测量 | RAG 双路召回、AutoDream、并发约束 | 只能说“已实现并通过契约测试” |
| D：容量估算 | 由公式和假设推导，不是压测结果 | 10 万 DAU 容量模型、2 秒预算 | 必须说“估算/目标” |

任何指标回答都应同时带上五个限定：`数据版本 + 样本量 + 环境 + 指标定义 + 是否生产数据`。

## 3. 数据资产总账

### 3.1 槽位抽取数据

| 数据资产 | 数量 | 用途 | 真实性与限制 |
| --- | ---: | --- | --- |
| `raw/v0.1` | 500 | 第一版原始场景样本 | 构造数据 |
| `raw/v0.2` | 795 | Round 001 | 479 条 v0.1 去重回放 + 316 条定向样本 |
| `raw/v0.3` | 1165 union | Round 002 | 共享核心与大小模型专项样本 |
| `raw/v0.4` | 1405 union | Round 003 | 增加字段边界、日期和工具结果回归样本 |
| `raw/v0.5` | 1425 union | Round 004 最终定向数据 | 不代表真实用户分布 |
| v0.5 small train/val | 1048 / 117 | Qwen3-0.6B SFT | 合计 1165，约 90/10 切分 |
| v0.5 large train/val | 1210 / 135 | Qwen3-1.7B SFT | 合计 1345，约 90/10 切分 |
| DPO train/val v0.1 | 135 / 15 | 偏好优化 | chosen/rejected 由规则与扰动构造，不是用户投票 |
| 主评估集 `eval-v0.2` | 51 | 固定离线比较 | 36 Final、15 Tool Call；28 多轮、23 单轮 |
| 独立 holdout `eval-v0.3` | 24 | Round 004 后盲测 | 12 Final、12 Tool Call；6 多轮、18 单轮 |

覆盖场景：缺失信息追问、时间归一化、能力等级、指定工程师、可用/不可用/不存在/无匹配、偏好继承与修改、多轮状态更新、工具调用、确认、拒绝、暂缓和 handoff。

不能代表：真实用户语言分布、方言/ASR 噪声、产品长尾、跨地区策略差异、真实客服误操作、真实排班变化、线上攻击分布和长期用户行为。

### 3.2 数据来源与限制

训练数据由场景规格、结构化生成器和人工构造形成，再通过 schema、工具协议和业务断言校验；失败切片会生成定向回归样本，并渲染为 SFT ShareGPT 或 DPO chosen/rejected 格式。

仓库没有数据采集授权、企业来源标识、脱敏流水、标注员一致性记录或线上时间窗口，因此不能称为“真实企业数据”。数据中还存在领域迁移后不够自然的偏好短语，说明它适合验证协议与状态机，但不适合直接估计生产泛化能力。

### 3.3 数据治理证据

| 机制 | 已有证据 | 解释 |
| --- | --- | --- |
| 数据注册表 | `data/dataset-registry.yaml` | 记录 role、status、parent、路径和首次使用轮次 |
| 不可变版本 | v0.1 到 v0.5 独立目录 | 新数据新版本，不覆盖旧版本 |
| 固定随机种子 | v0.5 seed `20260821` | 支持切分复现 |
| 文件校验和 | manifests 与 `test.sha256` | 防止静默修改 |
| 去重记录 | v0.2 删除 21 条 v0.1 重复 | 有数量证据 |
| 主评估集隔离 | `eval_exact_input_overlap = 0` | 只证明精确输入零重合，不证明语义零泄漏 |
| holdout 隔离 | `holdout_in_training = false` | 24 条盲测未进入 v0.5 训练视图 |
| 契约校验 | `dataset_contract.json` | 校验字段、History、Tool Call、Reply Type 和 assertions |

追问“如何防泄漏”时要补充：当前没有用户级、时间级、产品级 Group Split，也没有 embedding/MinHash 语义近重复检测。这是下一版真实数据治理需要补齐的部分。

## 4. 评分体系

### 4.1 指标定义

51 条固定评估集包含：

- `protocol`：JSON 可解析、精确字段集合、字段类型、Final/Tool Call 协议；
- `task_correctness`：结构化槽位、状态、工具名称/参数及回复的业务正确性。

Final 样本：

```text
task_correctness = 0.70 * structured_score + 0.30 * reply_score
```

Tool Call 样本：

```text
task_correctness = mean(action, tool_name, arguments)
```

单条 `effective_pass`：

```text
protocol_pass == true AND task_correctness >= 0.95
```

偏好语义先做归一化、高置信别名和否定门控，其余使用 `BAAI/bge-small-zh-v1.5` 余弦相似度，阈值 `0.70`，多偏好做一对一匹配后计算 precision、recall、F1。评分不调用外部 LLM Judge。

小模型即使语义接近，只要输出不可解析或 Tool Call 参数不满足契约，系统也无法安全执行，所以协议正确是硬门槛。

### 4.2 局限

- 51 + 24 的样本量小，置信区间较宽；
- 固定集合经过多轮错误分析，存在对主集过拟合风险；
- Reply 语义评分不等价于真实满意度；
- 没有标注员间一致性、难例双审或仲裁数据；
- 没有按用户、产品、地区或时间做分层统计。

## 5. 模型优化证据

### 5.1 M0 基线

| 模型 | Protocol | Task correctness | Effective pass | 平均延迟 | P95 | 吞吐 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3-0.6B | 39.2% | 37.7% | 2/51 | 3676.67 ms | 4810.59 ms | 21.98 tok/s |
| Qwen3-1.7B | 72.5% | 64.7% | 6/51 | 6568.75 ms | 9774.28 ms | 12.88 tok/s |
| Qwen3-4B-Instruct-2507 | 82.4% | 67.6% | 25/51 | 10007.51 ms | 14098.73 ms | 9.69 tok/s |
| GPT-5.6-sol | 100% | 98.8% | 51/51 | 3450.37 ms | 5097.71 ms | 36.08 tok/s |

前三个模型为本地 llama.cpp 记录；GPT 为远程 API，网络、硬件和推理栈不同，延迟不能直接横向归因于模型本身。

### 5.2 第一阶段 SFT 与 DPO

| 模型 | Protocol | Task correctness | Effective pass |
| --- | ---: | ---: | ---: |
| Qwen3-0.6B Base | 39.2% | 37.7% | 2/51 |
| Qwen3-0.6B SFT | 82.4% | 77.3% | 24/51 |
| Qwen3-1.7B Base | 72.5% | 64.7% | 6/51 |
| Qwen3-1.7B SFT | 88.2% | 92.1% | 29/51 |

同一评分口径下，0.6B 的 effective pass 从 3.9% 提升到 47.1%，1.7B 从 11.8% 提升到 56.9%。这支持“SFT 改善结构协议和任务适配”，不能外推为线上准确率。

| DPO 运行 | Effective pass | 相对 SFT parent |
| --- | ---: | ---: |
| 0.6B SFT | 24/51 | 基准 |
| 0.6B DPO beta=0.1 | 22/51 | -2 |
| 0.6B DPO beta=0.3 | 22/51 | -2 |
| 1.7B SFT | 29/51 | 基准 |
| 1.7B DPO beta=0.1 | 29/51 | 0 |
| 1.7B DPO beta=0.3 | 27/51 | -2 |

结论不是“DPO 一定无效”，而是当前 150 条构造偏好对和当前错误类型不足以带来收益。很多错误是 schema、工具证据和状态约束问题，继续做 DPO 的边际收益不如定向 SFT 与确定性校验。

### 5.3 Phase 06 多轮 SFT

| 轮次 | 数据版本 | 0.6B | 1.7B | 主要结论 |
| --- | --- | ---: | ---: | --- |
| Round 001 | sft-v0.2 | 33/51 | 34/51 | 组合数据对 0.6B 有效 |
| Round 002 | sft-v0.3 | 36/51 | 34/51 | 0.6B 提升但出现回归 |
| Round 003 | sft-v0.4 | 37/51 | 38/51 | 1.7B 协议 51/51，仍有历史回归 |
| Round 004/005 | 0.6B v0.5 / 1.7B v0.4 | 40/51 | 39/51 | 0.6B 最终轮与 1.7B 上轮候选统一复评，只差 1 条 |

最终统一复评：

| 候选 | 主集 | 24 条 holdout | Protocol 主集 | Task correctness 主集 | P95 主集 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `r004-qwen3-0.6b-sft` | 40/51（78.4%） | 21/24（87.5%） | 92.2% | 93.9% | 7571.58 ms |
| `r003-qwen3-1.7b-sft` | 39/51（76.5%） | 21/24（87.5%） | 100% | 95.5% | 12879.71 ms |

1.7B 在协议和平均任务分上更高，0.6B 的严格通过数略高且速度更好。差异只有一条，不能宣称存在统计显著性。

### 5.4 训练配置与运行记录

Round 004 0.6B：Qwen3-0.6B、LoRA SFT、rank 16、alpha 32、dropout 0.05、target all、cutoff 2048、学习率 `1e-4`、cosine、warmup 0.1、3 epochs、micro batch 2、gradient accumulation 8、bf16、seed `20260821`。

| 运行 | Train loss | Runtime | Samples/s |
| --- | ---: | ---: | ---: |
| r001 0.6B | 0.1185 | 436.95 s | 4.909 |
| r001 1.7B | 0.1455 | 732.31 s | 2.929 |
| r002 0.6B | 0.0942 | 585.78 s | 4.998 |
| r002 1.7B | 0.1175 | 979.27 s | 2.990 |
| r003 0.6B | 0.0857 | 675.26 s | 5.056 |
| r003 1.7B | 0.1069 | 1140.37 s | 2.994 |

Round 003 归档环境：RTX 4090、CUDA 12.6；时间戳从 `2026-08-21T14:49:59+08:00` 到 `15:21:38+08:00`。这只证明该次归档环境。Train loss 下降不能单独证明泛化提升，模型决策仍依赖冻结评估、holdout 和逐样本回归。

## 6. 量化、推理与 Prompt 证据

### 6.1 Q8 与 Q4

Round 007：Windows、本地 CPU、8 线程、关闭 Prompt Cache；8 条不同长度请求，每条重复 3 次，另有一次预热；输入约 1324–1680 tokens。

| 中位数指标 | Q8_0 | Q4_K_M | Q4 相对 Q8 |
| --- | ---: | ---: | ---: |
| 模型体积 | 609.8 MiB | 378.3 MiB | -38.0% |
| Prefill | 8286.6 ms | 5035.8 ms | -39.2% |
| Prefill 速度 | 168.8 tok/s | 274.9 tok/s | +62.9% |
| TTFT | 8808.4 ms | 5583.1 ms | -36.6% |
| Decode | 3143.6 ms | 2644.1 ms | -15.9% |
| Decode 速度 | 30.31 tok/s | 32.15 tok/s | +6.1% |
| 端到端 | 11952.7 ms | 8318.0 ms | -30.4% |
| 峰值 RSS | 1156.4 MiB | 1129.5 MiB | -2.3% |

质量复评：Q8 为 61/75，Q4 为 59/75。Q4 损失 2 条，所以默认选择 Q8 质量版，Q4 作为低延迟选项。主要瓶颈是长结构化 Prompt 的 Prefill，而不是 Decode。

### 6.2 Prompt Cache 与压缩 Prompt

| 配置 | 输入 tokens | Prefill | TTFT | 端到端 | holdout 通过 |
| --- | ---: | ---: | ---: | ---: | ---: |
| full-cold | 1337 | 4807.6 ms | 5349.7 ms | 7378.8 ms | 17/24 |
| full-cache | 1337 | 1053.3 ms | 1565.4 ms | 3725.4 ms | 17/24 |
| compact-cold | 605 | 2282.2 ms | 2843.8 ms | 4471.3 ms | 5/24 |
| compact-cache | 605 | 676.5 ms | 1197.1 ms | 2902.4 ms | 5/24 |

完整 Prompt 使用缓存后端到端中位延迟降低约 49.5%，质量在该实验中不变；暴力压缩 Prompt 使 holdout 从 17/24 降到 5/24。正确方向是可控前缀缓存、状态结构化和分阶段 Prompt，而不是删除关键约束。

## 7. 模型产物交付边界

仓库有 8 个 `adapter_model.safetensors` 路径，但当前克隆内容是 136 字节 Git LFS pointer，不是完整二进制权重。最终两个指针：

| Adapter | 对象大小 | SHA-256 OID |
| --- | ---: | --- |
| `r004-qwen3-0.6b-sft` | 38.55 MiB | `b9bd49...89dc59` |
| `r003-qwen3-1.7b-sft` | 66.55 MiB | `0002c9...36b89` |

完整 base、合并 F16 和 GGUF 权重没有提交。仓库保存配置、指针、训练日志、预测、scorecard、生成脚本和校验信息。

准确口径：实验结果可审计、部分可复现；从全新 clone 恢复完整权重仍缺可用对象存储和自动下载凭据，不能说“一键全量复现”。

## 8. RAG 数据与算法证据

### 8.1 已实现能力

- 文档摄取和解析；
- Dense + BM25 双路召回；
- RRF 融合；
- 可选 Cross-Encoder/LLM rerank；
- query/ingestion Trace；
- citations、候选数和排名变化；
- 3 个 MCP Tool 与标准 stdio 生命周期；
- 自定义评估与 Ragas 适配代码。

这些属于“功能与评估框架已实现”，不是检索质量结论。

### 8.2 当前数据事实

- `golden_test_set.json` 只有 5 个示例问题；
- 5 条的 `expected_chunk_ids` 和 `expected_sources` 都为空；
- 测试语料明确位于 `tests/fixtures/sample_documents`；
- 多份 PDF 由仓库脚本生成；
- 没有企业产品手册、保修条款、SLA、故障案例或工单语料；
- 没有持久化真实 Chroma/BM25 索引、查询日志或 RAG benchmark 报告。

因此当前不能声称 Recall@5、MRR、nDCG、RRF 增益、Cross-Encoder 增益或引用正确率达到某个数。根 EDD 的 RAG case 只检查 `candidate_count >= 1`；这证明链路返回候选，不等于相关性，也不能冒充 Recall。

面试标准回答：

> RAG 目前最强的证据是组件级和进程级测试，不是质量指标。因为没有带 graded relevance 的企业金标集，我没有用“有返回结果”替代 Recall。下一步会让业务专家建立 0/1/2/3 级 query-document 相关性，报告 Recall@5、MRR、nDCG@5、citation validity，并对 BM25、Dense、RRF 和 rerank 做消融。

## 9. 工程测试证据

### 9.1 实际运行结果

| 测试组 | 实际结果 | 主要证明对象 |
| --- | ---: | --- |
| 根服务 Unit/Integration/E2E | 25 passed | Agent、状态、预约、Memory、API、安全 |
| 槽位组件 | 290 passed，1 deselected | 数据、schema、评估、训练配置、工具循环 |
| RAG unit | 1205 passed，1 skipped | 组件合同、错误路径、评估和 Trace |
| MCP stdio/进程 E2E | 13 passed | 初始化、Tool list/call、结构化错误 |
| pytest 合计 | 1533 passed | 参数化后的实际测试 outcome |
| 仓库集成扫描 | passed | 目录、适配路径和旧领域关键词 |

源码中的 test 函数数与 pytest outcome 不相等，因为参数化会把一个函数展开成多个 case。面试说“1533 项测试通过”比“1533 个测试函数”准确。

### 9.2 根系统重点不变量

- 最近 10 条上下文和滚动摘要；
- Memory 按语义 0.6、时效 0.3、重要度 0.1 召回 Top-5；
- 工具白名单和关键操作确认；
- 预约状态机非法跳转；
- 幂等键重复确认返回同一预约；
- 同工程师时间重叠冲突；
- AutoDream 5 次会话/24 小时阈值、checkpoint、锁和冲突降权；
- Agent loop 的重复签名和最大步数；
- handoff 只消费一次；
- 重启后关闭遗留 active 事实行；
- 五阶段流程的版本化证据门禁；
- SSE 终态事件和知识引用；
- 高风险 API 对 customer 拒绝访问。

这些证明确定性业务不变量，不证明线上成功率或高并发容量。

### 9.3 尚无证据

- Azure/OpenAI/Ollama 真实服务；
- 企业语料上的完整 RAG E2E；
- 从新 clone 恢复并运行完整本地模型；
- 50/100/200 并发压测；
- 24 小时稳定性；
- 网络抖动、429、下游超时和断路器故障注入；
- 多实例数据库竞争和 PostgreSQL 生产部署；
- 浏览器真实用户行为与满意度。

## 10. EDD 业务门禁

`evaluation/cases.json` 当前有 10 条：

| 层 | 数量 | 内容 |
| --- | ---: | --- |
| routing | 3 | 咨询、预约、画像 |
| slot | 2 | 槽位完整、确认 |
| rag | 1 | 至少返回一个候选 |
| tool | 1 | 工具白名单 |
| trajectory | 1 | 最大步骤 |
| safety | 2 | 注入和无确认写入 |

2026-08-27 本机复验：

- 10/10 passed；
- task success rate 100%；
- safety pass rate 100%；
- P95 `18.074 ms`；
- task success、安全、P95、最大步数四项 gate 全部通过。

门禁阈值是任务成功率 85%、安全 100%、P95 2500 ms、最大 6 步。必须主动解释：18.074 ms 是本地规则 fallback、SQLite 和小型测试语料热路径，不包含真实远程模型、真实 RAG 和业务下游，不能当作生产端到端 P95。

## 11. API、状态与运行数据

- `api/routes.py` 当前有 29 个 `/api/v1` 业务路由装饰器；
- 覆盖会话、Agent、SSE、咨询、预约、工程师、行为、Memory、AutoDream、知识、handoff、Trace、审计和评估；
- 仓库没有提交运行期 SQLite、生产 Trace、客服会话或行为日志；
- 工程师和排班来自 fixture，不是真实企业排班；
- AutoDream 阈值、锁、checkpoint 和冲突策略有测试，但没有真实用户画像效果数据；
- 预约并发有数据库约束和集成测试，但没有多进程/多机压力结果。

正确说法是“机制已实现并验证”，不能说“已经积累用户画像”或“已经承载某个并发量”。

## 12. 性能与容量：实测和估算分开

可以称为实测：槽位 scorecard 单机延迟、Round 007 Q8/Q4 CPU 流式 TTFT/吞吐/RSS、Round 008 cache 实验、本地 EDD P95。每组只能在对应硬件、模型、输入长度和样本量下解释。

文档中的 10 万 DAU 示例只是 sizing：

```text
100000 DAU * 0.3 session/day * 6 turns/session = 180000 turns/day
平均约 2.1 turn/s，假设 10 倍峰值约 21 turn/s
约 360000 invocation/day
若每 turn 20 个事件，则约 360 万事件/day
按 0.8 KB/event 约 2.9 GB/day
```

这不是系统已经压到 10 万 DAU；它用于推导事件 payload、归档/分区和从 SQLite 迁移 PostgreSQL 的时机。

## 13. 可说、谨慎说、不能说

### 13.1 可以直接说

- 项目有 29 个业务 API 路径；
- 本机实际通过 1533 项 pytest；
- 当前 10 条 EDD smoke case 全通过，安全样本 2/2；
- 数据有 v0.1–v0.5、固定 seed、manifest、checksum 和冻结 holdout；
- 执行过 LoRA SFT/DPO 并保存训练日志、预测和 scorecard；
- DPO 在当前构造偏好数据上没有超过 SFT；
- Q4 相对 Q8 明显降低 TTFT，但损失 2/75，所以默认 Q8；
- RAG 质量尚无可靠企业金标结果。

### 13.2 必须带限定说

- “槽位严格通过率 78.4%”：补充 `r004、51 条构造评估集、40/51、非线上数据`；
- “holdout 87.5%”：补充只有 24 条、21/24、统计不稳定；
- “P95 18 ms”：补充本地规则/SQLite smoke，不含远程模型；
- “1533 项测试”：证明工程行为，不证明业务准确率；
- “exact input overlap 为 0”：只排除精确重合，不排除语义近重复。

### 13.3 不能说

- 已在真实企业数据上训练或测试；
- 真实客服准确率、预约成功率或用户满意度是多少；
- RAG Recall@5、MRR、nDCG 已达到某个数；
- 已通过 100/200 并发或 24 小时稳定性测试；
- GitHub clone 后可以直接恢复全部模型权重；
- Q4 是无损量化；
- 10/10 EDD 等于生产系统 100% 成功率；
- 1533 项测试等于零缺陷。

## 14. 高频面试追问与标准回答

### Q1：你的数据是真实企业数据吗？

不是。当前是版本化场景构造数据，用于验证业务协议、状态更新、工具调用和训练链路。没有企业授权的脱敏会话、工单和知识库，所以我没有把离线分数解释成线上效果。

### Q2：那数据价值在哪里？

价值是把数据生产、校验、切分、训练、评估、失败归因和回归门禁串成闭环。它证明方法和工程基础已具备，真实数据接入后不必重写整套链路。

### Q3：为什么主评估集只有 51 条？

它是高密度协议集，强调业务边界而非分布估计，适合快速回归，不适合给出窄置信区间。后来增加 24 条训练前冻结 holdout，但规模仍小，因此下一步要建设分层真实金标集。

### Q4：反复看 51 条不会过拟合吗？

会，所以 Round 004 增加冻结 holdout，并停止继续围绕固定主集补数据。更彻底的方式是日常只看 train/dev，最终 test 在模型确定前保持盲态。

### Q5：如何证明没有数据泄漏？

manifest 记录主集精确输入 overlap 为 0，holdout_in_training 为 false，并用 SHA 和注册表冻结。但这只覆盖精确重合；生产版还要做语义近重复检测及 user/time/product group split。

### Q6：为什么 effective pass 阈值是 0.95？

Agent 工具调用是高约束任务，平均分可能掩盖一个关键字段错误。协议必须通过且任务分至少 0.95，避免错误参数、错误状态或虚假确认被平均掉。

### Q7：为什么结构 70%、回复 30%？

工具执行首先依赖结构化状态，错误时间、工程师或确认会直接产生业务风险，因此权重更高；回复仍影响用户理解，所以保留 30%。比例来自当前风险假设，真实阶段应按错误成本校准。

### Q8：为什么不用 LLM-as-Judge？

核心协议可确定性判断，避免 Judge 漂移、成本和不可复现。自然语言使用固定 embedding、否定门控和语义动作。开放式回答可增加 Judge，但应先和人工金标校准并固定版本。

### Q9：SFT 到底提升了什么？

0.6B 协议从 39.2% 到 82.4%，任务分从 37.7% 到 77.3%；1.7B 任务分从 64.7% 到 92.1%。主要改善严格 JSON、字段边界、工具调用和多轮状态，不代表通用语言能力提升。

### Q10：为什么 DPO 没提升？

偏好对只有 150 条且由规则构造，主要错误又是硬协议和状态约束。DPO 对 0.6B 少 2 条通过，对 1.7B 最好持平，所以停止投入，回到定向 SFT 和系统约束。

### Q11：为什么保留 0.6B 和 1.7B 两个候选？

统一复评中 0.6B 是 40/51，1.7B 是 39/51，holdout 都是 21/24。差异不足以证明谁显著更强；0.6B 成本和延迟好，1.7B 协议和平均任务分高，应按部署目标选择。

### Q12：为什么默认 Q8 而不是更快的 Q4？

Q4 将 TTFT 降低 36.6%、端到端降低 30.4%，但从 61/75 降至 59/75，不是无损。默认优先业务质量选 Q8，Q4 只在能接受稳定回归的低延迟环境启用。

### Q13：为什么 Prefill 是瓶颈？

输入包含系统策略、JSON schema、状态和工具规则，约 1.3k–1.7k tokens。Q4 对 Prefill 提升 62.9%，对 Decode 只提升 6.1%，端到端收益主要来自 Prefill，因此优先做前缀缓存和约束外置。

### Q14：Prompt 压缩为什么失败？

输入从约 1337 降至 605 tokens 后延迟改善，但 holdout 从 17/24 降至 5/24，说明删除了小模型依赖的显式约束。正确方向是公共前缀缓存、状态结构化和分阶段 Prompt。

### Q15：训练 loss 下降说明模型更好吗？

不能。它只说明训练目标拟合增强。是否更好要看冻结评估、holdout、协议错误和逐样本回归；项目里也出现过 loss 下降但历史样本回归。

### Q16：RAG 效果怎么样？

目前不能给可靠质量数字。只有 5 条示例 query，且 expected chunk/source 为空。现在能证明摄取、召回、融合、重排接口、Trace 和 MCP 生命周期工作，不能证明企业语料 Recall 或 nDCG。

### Q17：为什么 candidate_count>0 不是 Recall？

Recall 的分母是标注相关文档，必须知道 ground truth。返回任意候选只说明链路非空，候选可能完全无关。

### Q18：如何建设 RAG 金标集？

从脱敏日志按产品、意图、频次和零结果分层抽样；专家对 query-document 标 0–3 相关性；双人标注加仲裁；按时间和产品切分；报告 Recall@K、MRR、nDCG、citation validity、零结果率和 scope leakage。

### Q19：如何证明 RRF 和 rerank 有用？

固定语料、query、候选预算和 embedding 版本，做 BM25-only、Dense-only、RRF、RRF+rerank 消融；同时报告质量、P95、候选数和成本。

### Q20：1533 项测试意味着什么？

意味着大量确定性合同和错误路径被自动回归，包含参数化 case；不意味着 1533 个测试函数，也不意味着业务准确率或零缺陷。

### Q21：EDD 10/10 为什么不是线上 100%？

分母只有 10 条人工 smoke case，且部分走规则 fallback。它只表示当前 CI gate 通过。线上成功率需要真实会话分母、业务结果定义和置信区间。

### Q22：为什么本地 P95 只有 18 ms？

它不含真实 LLM、远程 RAG 和业务系统，仅测规则、SQLite 和小数据热路径。真实 P95 要拆 DNS、连接、TTFT、生成、检索、工具和排队。

### Q23：预约并发有真实压测吗？

没有。当前证据是数据库约束、重叠检查、幂等键和集成测试。多进程、多实例和 PostgreSQL 下的冲突率、锁等待与吞吐需要压测。

### Q24：怎么防止重复预约？

请求级使用 idempotency key 返回原结果；资源级用数据库冲突约束保护工程师时间槽；事务内重查并提交。应用锁只能优化竞争，数据库约束是最终防线。

### Q25：Memory 有真实效果数据吗？

没有。当前证明最近 10 条、Top-5 加权召回、摘要触发、偏好置信度和冲突降权机制，但没有个性化带来的满意度或任务成功率提升。

### Q26：AutoDream 如何评估？

当前测试阈值、24 小时间隔、锁、checkpoint、去重和冲突降权。真实评估应报告偏好 precision、错误写入率、冲突恢复率、过期率及下游推荐增益。

### Q27：模型权重为什么不在仓库？

大模型制品不适合普通 Git。仓库保留指针、OID、大小、配置和实验记录，生产应使用模型注册表或对象存储。当前缺口是没有可公开恢复对象的凭据和自动下载链路。

### Q28：实验可复现到什么程度？

数据版本、seed、配置、日志、环境清单、预测、scorecard 和部分哈希都在；但完整 base/adapter/GGUF payload 和外部凭据不在，因此是“结果可审计、部分可复现”。

### Q29：如何处理统计显著性？

51 条上相差一条不能宣称显著。真实评估应扩大样本，报告 bootstrap 置信区间或配对检验，并按场景切片；模型选择还要结合错误成本。

### Q30：如何从合成数据迁移到真实数据？

保留合成集做协议回归；真实数据经授权、脱敏、会话级切分和双人标注后建立 train/dev/test；先只评估，再分析分布差异，最后逐步混合训练，并分别报告 synthetic 和 real 指标。

### Q31：真实数据最担心什么？

PII 泄露、标注漂移、同一用户跨集合泄漏、热门产品支配总分、日志只保留成功请求造成选择偏差，以及客服历史回答本身含错。

### Q32：如何构建失败回归集？

从 Trace 抽取失败，先脱敏和人工归因，再补 expected/judgment；保留 trace ID 和输入 digest；修复前先复现；加入版本化 cases 后进入 CI。线上失败不能未经审核直接训练。

### Q33：指标冲突怎么选？

先按风险设硬门槛，例如安全和协议；再在合格候选中比较任务质量、延迟和成本。Q8/Q4 就是典型：Q4 更快，但质量回归让默认版本选择 Q8。

### Q34：容量估算和压测有什么区别？

容量估算用业务假设推导存储和 QPS，用于发现架构边界；压测在明确硬件、数据和依赖下测吞吐、P95、错误率和资源。项目当前有前者，没有完整后者。

### Q35：最诚实的项目评价是什么？

这是一个证据意识较强的企业 Agent 工程原型：算法训练和工程测试确实执行过，但生产数据闭环尚未完成。最大价值是架构、不变量、评估框架以及对指标边界的诚实控制。

## 15. 三种面试陈述长度

### 30 秒

> 项目实现了企业售后咨询、预约、知识检索和用户记忆的统一 Agent 服务。工程上有 29 个 API、SSE、handoff、幂等预约、AutoDream 和 Trace，实际通过 1533 项测试。算法侧用版本化构造数据完成 Qwen3 0.6B/1.7B 的 LoRA SFT/DPO 和量化实验，最终 0.6B 在 51 条主集上 40/51、24 条 holdout 上 21/24。由于不是企业真实数据，我只把这些数字当离线回归证据，RAG 质量也明确留待真实金标集验证。

### 2 分钟

> 我把项目拆成 Web/API/Agents/Services/DB 五层，主管 Agent 通过 ReAct 调度咨询、预约、行为分析和 RAG 工具。会话保存最近 10 条与滚动摘要，长期记忆按语义、时效和重要度召回 Top-5；预约通过显式确认、幂等键和数据库冲突约束防重复写；handoff、Invocation、事件和 Trace 都持久化。
>
> 数据侧维护 v0.1 到 v0.5，最终 union 1425 条，主评估 51 条，另有训练前冻结的 24 条 holdout。0.6B Base 严格通过 2/51，第一阶段 SFT 后 24/51，后续定向 SFT 最终 40/51，holdout 21/24。DPO 没有超过 SFT，所以没有为了技术名词继续堆 DPO。量化实验中 Q4 比 Q8 的 TTFT 快 36.6%，但少通过 2/75，因此默认 Q8。
>
> 这些都是场景构造数据，不是线上客服数据。RAG 虽实现 Dense、BM25、RRF 和 rerank，但当前金标只有 5 条且没有相关文档 ID，所以不能虚报 Recall。现阶段成果是工程与离线评估闭环，下一阶段才是真实数据和线上效果闭环。

### 5 分钟展开顺序

1. 业务目标与为什么需要主管 Agent；
2. 五层架构和状态权威存储；
3. 数据版本、51 主集、24 holdout 与泄漏控制；
4. Base → SFT → DPO → 多轮 SFT 的决策证据；
5. Q8/Q4、Prompt Cache 与质量/延迟 trade-off；
6. 预约并发、handoff、Memory、AutoDream 不变量；
7. 1533 项测试和 10 条 EDD 的证明边界；
8. 主动说明真实数据、RAG 金标和负载测试缺口；
9. 给出真实数据接入与生产验证计划。

## 16. 下一阶段真实数据方案

以下是目标，不是当前成果。

### 16.1 数据源与治理

- 脱敏客服会话、工单和产品知识文档；
- 工程师技能、地区、班次、请假和历史服务结果；
- 预约创建/取消/改约、用户确认、转人工、投诉和满意度事件；
- 明确授权和目的限定，删除姓名、电话、地址、序列号等 PII；
- 以 conversation/user 为单位去重和切分，增加时间外推 test；
- 双人标注 + 仲裁，记录指南版本和一致性；
- 每次导出记录 lineage、hash、schema version 和 retention policy。

### 16.2 建议首期规模

这些是建议值，不是已有数据：

- 5,000–20,000 条脱敏会话用于分布分析；
- 1,000–3,000 条高质量槽位/轨迹标注用于独立评估；
- 300–1,000 条 RAG query，每条带 graded relevance；
- 至少 200 条安全/越权/注入用例；
- 50/100/200 并发三档压测和 24 小时 soak test。

### 16.3 应报告的生产指标

| 层 | 离线指标 | 线上指标 |
| --- | --- | --- |
| Routing | macro-F1、unsafe route | 转人工率、错路由率 |
| Slot | field P/R/F1、exact match、confirmation precision | 补问轮数、预约修改率 |
| RAG | Recall@5、MRR、nDCG@5、citation validity | 零结果率、引用纠错率 |
| Tool | selection accuracy、argument validity | success、timeout、retry |
| Trajectory | task success、loop rate、steps、token | 一次解决率、处理时长 |
| Appointment | conflict/idempotency pass | 重复预约率、冲突率、成功率 |
| Memory | preference precision、conflict rate | 个性化采纳率、错误画像投诉 |
| Safety | attack pass、IDOR pass | 越权事件、敏感信息泄露 |
| Performance | P50/P95/P99、throughput、error rate | SLO、可用性、成本/会话 |

## 17. 面试前核验清单

- [ ] 明确说“构造数据”，不说“真实企业数据”；
- [ ] 每个百分比能还原成分子/分母；
- [ ] 区分主集 51、holdout 24 和 EDD 10；
- [ ] 区分 pytest、EDD、模型评估和 RAG 评估；
- [ ] 能解释 effective pass 的 0.95 门槛；
- [ ] 能解释为什么停止 DPO；
- [ ] 能解释 Q8/Q4 的质量与延迟取舍；
- [ ] 主动说明 RAG 没有可靠 Recall；
- [ ] 主动说明 P95 18 ms 不含真实模型；
- [ ] 主动说明权重文件目前只是 LFS 指针；
- [ ] 不把容量模型说成压测结果；
- [ ] 准备真实数据接入与标注方案。

## 18. 证据路径索引

| 证据 | 仓库路径 |
| --- | --- |
| 数据注册表 | `packages/slot_extractor/data/dataset-registry.yaml` |
| 主评估卡 | `packages/slot_extractor/data/eval/DATASET_CARD.md` |
| 51 条评估集 | `packages/slot_extractor/data/eval/test.jsonl` |
| 24 条 holdout | `packages/slot_extractor/data/eval/phase06_holdout_v0.3.jsonl` |
| v0.5 manifest | `packages/slot_extractor/data/processed/v0.5/manifest.json` |
| M0 基线 | `packages/slot_extractor/reports/baseline-m0/comparison.json` |
| SFT 比较 | `packages/slot_extractor/reports/m1-sft/README.md` |
| DPO 比较 | `packages/slot_extractor/reports/m2-dpo/README.md` |
| Phase 06 汇总 | `packages/slot_extractor/experiments/phase06/summary/phase06-summary.md` |
| 最终候选复评 | `packages/slot_extractor/experiments/phase06/round-005/results/llamacpp` |
| 量化最终分析 | `packages/slot_extractor/experiments/phase06/round-007/reports/final-analysis.md` |
| Q8/Q4 benchmark | `packages/slot_extractor/experiments/phase06/round-007/local-final/benchmark.json` |
| Prompt/cache | `packages/slot_extractor/experiments/phase06/round-008/results/round008-results.json` |
| RAG golden set | `packages/modular_rag_mcp/tests/fixtures/golden_test_set.json` |
| RAG sample docs | `packages/modular_rag_mcp/tests/fixtures/sample_documents/README.md` |
| EDD 用例 | `evaluation/cases.json` |
| 测试结果 | `docs/TESTING.md` |
| API 证据 | `api/routes.py`、`docs/API.md` |
| 容量估算 | `docs/CAPACITY.md` |

## 19. 最终答辩原则

最有说服力的不是把数字说大，而是能回答：数字来自哪里、分母是什么、为什么这样评、失败了什么、为什么停止某条优化路线，以及现有证据不能证明什么。

当前最真实的亮点是：SFT 有明显离线收益、DPO 失败被如实保留、Q4 的质量回归阻止了“只追求速度”的错误决策、RAG 没有金标就不虚报 Recall、工程测试与生产效果被明确区分。这种证据边界本身就是企业 Agent 的重要工程能力。
