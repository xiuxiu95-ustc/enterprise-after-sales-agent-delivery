from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings


@dataclass
class AppointmentSlots:
    service_type: Optional[str] = None
    issue_category: Optional[str] = None
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    engineer_name: Optional[str] = None
    required_skills: List[str] = field(default_factory=list)
    location: Optional[str] = None
    contact: Optional[str] = None
    confirmation: bool = False
    missing_info: List[str] = field(default_factory=list)
    source: str = "rule_fallback"

    def merged(self, previous: Dict[str, Any]) -> "AppointmentSlots":
        current = asdict(self)
        for key, value in previous.items():
            if key not in current:
                continue
            if current[key] in (None, [], "") and value not in (None, [], ""):
                current[key] = value
        current["confirmation"] = bool(self.confirmation)
        current["missing_info"] = []
        return AppointmentSlots(**current)

    def finalize_missing(self) -> "AppointmentSlots":
        required = ["service_type", "issue_category", "start_time", "duration_minutes"]
        self.missing_info = [name for name in required if not getattr(self, name)]
        if self.service_type != "remote_support" and not self.location:
            self.missing_info.append("location")
        return self


@dataclass(frozen=True)
class BackendGenerationParams:
    """Structural equivalent of slot_extractor.inference.base.GenerationParams."""

    temperature: float = 0.0
    max_tokens: int = 400
    response_schema: Optional[Dict[str, Any]] = None
    response_schema_name: str = "enterprise_appointment_slots"


ENTERPRISE_SLOT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "service_type": {"type": ["string", "null"]},
        "issue_category": {"type": ["string", "null"]},
        "start_time": {"type": ["string", "null"], "description": "YYYY-MM-DD HH:MM"},
        "duration_minutes": {"type": ["integer", "null"]},
        "engineer_name": {"type": ["string", "null"]},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "location": {"type": ["string", "null"]},
        "contact": {"type": ["string", "null"]},
        "confirmation": {"type": "boolean"},
    },
    "required": [
        "service_type", "issue_category", "start_time", "duration_minutes",
        "engineer_name", "required_skills", "location", "contact", "confirmation"
    ],
    "additionalProperties": False,
}


class SlotExtractorAdapter:
    """Adapts post-training-slot-extractor's Backend.generate to enterprise slots."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = self._load_backend()

    def _load_backend(self) -> Optional[Any]:
        if not self.settings.slot_backend_config:
            return None
        repo = Path(self.settings.slot_extractor_repo)
        src = repo / "src"
        config = Path(self.settings.slot_backend_config).expanduser()
        if not config.is_absolute():
            config = repo / config
        if not src.exists() or not config.exists():
            raise RuntimeError("slot_extractor_adapter_configuration_missing")
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from slot_extractor.inference.factory import build_backend_from_config

        return build_backend_from_config(config)

    def extract(
        self,
        user_input: str,
        previous: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> AppointmentSlots:
        now = now or datetime.now()
        if self.backend is None:
            current = self._rule_extract(user_input, now)
        else:
            current = self._backend_extract(user_input, previous or {}, now)
        return current.merged(previous or {}).finalize_missing()

    def _backend_extract(self, user_input: str, previous: Dict[str, Any], now: datetime) -> AppointmentSlots:
        prompt = (
            "你是企业售后预约槽位抽取器。只输出符合 JSON Schema 的对象，不生成解释。"
            "不得把客户未确认的信息当成确认；相对时间以 current_time 为准。"
        )
        messages = [
            {
                "role": "system",
                "content": f"{prompt}\ncurrent_time={now:%Y-%m-%d %H:%M}\nstate={json.dumps(previous, ensure_ascii=False)}",
            },
            {"role": "user", "content": user_input},
        ]
        result = self.backend.generate(
            messages,
            BackendGenerationParams(
                temperature=0.0,
                max_tokens=400,
                response_schema=ENTERPRISE_SLOT_SCHEMA,
                response_schema_name="enterprise_appointment_slots",
            ),
        )
        data = json.loads(result.text)
        data["source"] = "post_training_backend_adapter"
        return AppointmentSlots(**data)

    @staticmethod
    def _rule_extract(text: str, now: datetime) -> AppointmentSlots:
        service_map = {
            "上门": "onsite_repair", "维修": "onsite_repair", "远程": "remote_support",
            "安装": "installation", "保养": "maintenance", "巡检": "inspection",
            "退换": "return_exchange",
        }
        service_type = next((value for key, value in service_map.items() if key in text), None)
        issue_map = {
            "网络": ("network", ["network"]), "路由器": ("network", ["network"]),
            "软件": ("software", ["software"]), "系统": ("software", ["software"]),
            "硬件": ("hardware", ["hardware"]), "不开机": ("hardware", ["hardware"]),
            "空调": ("hvac", ["hvac"]), "冰箱": ("appliance", ["appliance"]),
            "打印机": ("printer", ["printer"]), "安装": ("installation", ["installation"]),
        }
        issue_category, skills = next(
            ((value[0], value[1]) for key, value in issue_map.items() if key in text),
            (None, []),
        )
        duration = None
        duration_match = re.search(r"(\d+(?:\.\d+)?)\s*(小时|分钟)", text)
        if duration_match:
            amount = float(duration_match.group(1))
            duration = int(amount * 60 if duration_match.group(2) == "小时" else amount)
        start_time = None
        iso = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(\d{1,2})[:点](\d{1,2})?", text)
        if iso:
            start_time = f"{int(iso.group(1)):04d}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d} {int(iso.group(4)):02d}:{int(iso.group(5) or 0):02d}"
        else:
            relative = re.search(r"(今天|明天|后天).{0,8}?(上午|下午|晚上)?\s*(\d{1,2})[点:](\d{1,2})?", text)
            if relative:
                offset = {"今天": 0, "明天": 1, "后天": 2}[relative.group(1)]
                hour = int(relative.group(3))
                if relative.group(2) in {"下午", "晚上"} and hour < 12:
                    hour += 12
                target = now + timedelta(days=offset)
                start_time = target.replace(hour=hour, minute=int(relative.group(4) or 0), second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
        engineer = None
        engineer_match = re.search(r"(?:指定|找|要)([\u4e00-\u9fffA-Za-z]{2,12})(?:工程师|师傅)", text)
        if engineer_match:
            engineer = engineer_match.group(1)
        location = None
        location_match = re.search(r"(?:地址|地点|到)(?:是|：|:)?\s*([^，。；;]{2,40})", text)
        if location_match:
            location = location_match.group(1).strip()
        contact = None
        phone_match = re.search(r"1[3-9]\d{9}", text)
        if phone_match:
            contact = phone_match.group(0)
        negated_confirmation = bool(re.search(r"不需要确认|不要确认|无需确认|尚未确认|不确认", text))
        confirmation = not negated_confirmation and bool(
            re.search(r"确认预约|确认$|同意|就这样|可以预约|帮我下单", text)
        )
        return AppointmentSlots(
            service_type=service_type,
            issue_category=issue_category,
            start_time=start_time,
            duration_minutes=duration,
            engineer_name=engineer,
            required_skills=skills,
            location=location,
            contact=contact,
            confirmation=confirmation,
        )
