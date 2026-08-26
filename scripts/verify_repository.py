from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {
    ".cfg", ".css", ".env", ".example", ".html", ".ini", ".js", ".json",
    ".jsonl", ".lock", ".md", ".py", ".toml", ".txt", ".yaml", ".yml",
}
DISALLOWED = (
    "按" + "摩",
    "推" + "拿",
    "技" + "师",
    "mass" + "age",
    "mass" + "eur",
    "thera" + "pist",
    "tech" + "nician",
)
REQUIRED_PATHS = (
    "packages/slot_extractor/src/slot_extractor/inference/factory.py",
    "packages/slot_extractor/INTEGRATION_MANIFEST.md",
    "packages/modular_rag_mcp/src/mcp_server/server.py",
    "packages/modular_rag_mcp/src/mcp_server/tools/query_knowledge_hub.py",
    "packages/modular_rag_mcp/src/mcp_server/tools/list_collections.py",
    "packages/modular_rag_mcp/src/mcp_server/tools/get_document_summary.py",
)


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore"


def verify() -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required component path: {relative}")

    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        lowered_path = relative.as_posix().casefold()
        for term in DISALLOWED:
            if term.casefold() in lowered_path:
                errors.append(f"disallowed legacy term in path: {relative}")
        if not path.is_file() or not _is_text(path):
            continue
        try:
            content = path.read_text(encoding="utf-8").casefold()
        except UnicodeDecodeError:
            continue
        for term in DISALLOWED:
            if term.casefold() in content:
                errors.append(f"disallowed legacy term in file: {relative}")
                break
    return errors


def main() -> int:
    errors = verify()
    if errors:
        print("\n".join(errors))
        return 1
    print("repository integration verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
