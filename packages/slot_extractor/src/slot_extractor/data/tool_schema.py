from __future__ import annotations

import json

FIND_ENGINEERS = {
    "name": "find_engineers",
    "description": "按预约条件查询工程师",
    "parameters": {
        "type": "object",
        "properties": {
            "engineer_name": {"type": ["string", "null"]},
            "start_time": {"type": "string"},
            "duration_minutes": {"type": "integer"},
            "engineer_level_preference": {"type": ["string", "null"], "enum": ["standard", "expert", None]},
            "preferences": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "engineer_name",
            "start_time",
            "duration_minutes",
            "engineer_level_preference",
            "preferences",
        ],
    },
}
TOOL_SCHEMAS = {"find_engineers": FIND_ENGINEERS}


def render_tools(available_tools: list[str]) -> str:
    unknown = set(available_tools) - set(TOOL_SCHEMAS)
    if unknown:
        raise ValueError(f"unknown tools: {sorted(unknown)}")
    return json.dumps(
        [TOOL_SCHEMAS[name] for name in available_tools], ensure_ascii=False, separators=(",", ":")
    )
