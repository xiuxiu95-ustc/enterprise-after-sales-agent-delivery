"""Executable entry point for the vendored RAG MCP stdio server."""

import sys

from src.mcp_server.server import main as run_mcp_server


def main() -> int:
    """Start the real MCP protocol server; stdout stays JSON-RPC only."""
    return run_mcp_server()


if __name__ == "__main__":
    sys.exit(main())
