# Modular RAG MCP Server

企业知识检索组件，提供文档摄取、Dense + BM25 双路召回、RRF 融合、可选 Cross-Encoder/LLM 精排、引用生成、查询/摄取 Trace、评估面板和 MCP stdio 服务。

## MCP Tools

- `query_knowledge_hub`：返回答案上下文、引用、候选数量和排序信息。
- `list_collections`：列出知识集合及统计信息。
- `get_document_summary`：按文档标识返回摘要与元数据。

`main.py` 直接启动 `src.mcp_server.server` 的正式协议处理器，stdout 只用于 JSON-RPC，日志写入 stderr。主服务既可通过 stdio 调用，也可在同进程中复用查询工具。

## 单独安装与测试

```powershell
pip install -e ".[dev]"
pytest
python main.py
```

生产运行前请在 `config/settings.yaml` 配置 embedding、向量库、精排器和企业知识集合。运行产生的向量库、BM25 索引、缓存、日志和 trace 不进入版本库。
