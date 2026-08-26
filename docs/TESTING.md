# 测试矩阵与验证结果

验证环境：Windows、Python 3.12，按 `requirements-integrated.txt` 安装根服务与两个内置组件。以下数字来自本次实际命令输出，不包含仅收集、未执行或依赖外部服务的用例。

| 层级 | 命令 | 结果 |
| --- | --- | --- |
| 根服务 Unit/Integration/E2E | 仓库根目录 `python -m pytest -q` | 25 passed |
| 槽位算法与后训练组件 | `packages/slot_extractor` 下 `python -m pytest -q` | 290 passed, 1 deselected |
| RAG 纯单元 | `packages/modular_rag_mcp` 下 `python -m pytest tests/unit -q` | 1205 passed, 1 skipped |
| MCP stdio 与进程级 E2E | 同目录运行 `tests/integration/test_mcp_server.py tests/e2e/test_mcp_client.py` | 13 passed |
| EDD 业务门禁 | 根目录 `python -m evaluation.runner --fail-on-gate` | 10/10 passed |
| 仓库集成/旧领域扫描 | 根目录 `python scripts/verify_repository.py` | passed |

pytest 实际通过合计 1533 项。RAG 仓库其余 Azure/OpenAI/Ollama、真实 Chroma 数据、视觉模型和慢速集成用例需要对应服务、凭据或语料；槽位组件的本地 llama-server 用例由 `local_backend` 标记隔离。CI 和报告必须把这些用例记为“环境未提供”，不能记成通过。

MCP 进程测试覆盖标准初始化屏障、3 个 Tool 的 schema/list、查询调用、集合枚举、缺失文档、未知 Tool、同会话多次调用与结构化错误。Windows 下 Chroma 原生扩展在 stdio worker 启动前预载，测试仅给初始化阶段 90 秒冷启动预算，普通 Tool 使用各自较短超时。

已知非功能性提醒：当前 Starlette TestClient 会报告一条 `httpx` 迁移弃用警告，不影响断言；应在框架升级窗口迁移到官方建议的新测试客户端。生产门禁还需补充脱敏企业标注集、50/100/200 并发压测、外部依赖故障注入和至少 24 小时稳定性运行。
