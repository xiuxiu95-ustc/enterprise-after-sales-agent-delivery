import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from .models import AvailabilityWindow, Engineer


@dataclass(frozen=True)
class FixtureStore:
    version: str
    date: str
    _engineers: tuple[Engineer, ...]
    fixture_hash: str

    @classmethod
    def from_yaml(cls, path: Path, target_date: date | None = None) -> "FixtureStore":
        raw = path.read_bytes()
        payload = yaml.safe_load(raw)
        parsed_windows = [
            datetime.strptime(item[key], "%Y-%m-%d %H:%M")
            for row in payload["engineers"]
            for item in row["availability"]
            for key in ("start", "end")
        ]
        if not parsed_windows:
            raise ValueError("fixture must contain availability windows")
        date_shift = (
            timedelta(days=(target_date - min(parsed_windows).date()).days)
            if target_date is not None
            else timedelta()
        )
        engineers = []
        names = set()
        for row in payload["engineers"]:
            if row["name"] in names:
                raise ValueError("duplicate engineer name")
            names.add(row["name"])
            windows = tuple(
                AvailabilityWindow(
                    datetime.strptime(item["start"], "%Y-%m-%d %H:%M") + date_shift,
                    datetime.strptime(item["end"], "%Y-%m-%d %H:%M") + date_shift,
                )
                for item in row["availability"]
            )
            ordered = sorted(windows, key=lambda window: window.start)
            if any(
                left.end > right.start for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("overlapping availability windows")
            engineers.append(
                Engineer(row["name"], row["level"], tuple(row["specialties"]), windows)
            )
        return cls(
            payload["version"],
            (target_date or datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()).isoformat(),
            tuple(engineers),
            hashlib.sha256(raw).hexdigest(),
        )

    def engineers(self) -> tuple[Engineer, ...]:
        return self._engineers
