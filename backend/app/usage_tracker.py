"""Self-tracked count of Sungrow API calls made — Sungrow doesn't expose a
"calls remaining" endpoint, so this is our own counter against the free
tier's documented limits (2000/hour, 100000/month), persisted to a small
JSON file so it survives restarts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HOURLY_LIMIT = 2000
MONTHLY_LIMIT = 100_000


class UsageTracker:
    def __init__(self, path: Path):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"hour_key": None, "hour_count": 0, "month_key": None, "month_count": 0}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data), encoding="utf-8")

    def record_call(self) -> None:
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%d-%H")
        month_key = now.strftime("%Y-%m")
        if self._data.get("hour_key") != hour_key:
            self._data["hour_key"] = hour_key
            self._data["hour_count"] = 0
        if self._data.get("month_key") != month_key:
            self._data["month_key"] = month_key
            self._data["month_count"] = 0
        self._data["hour_count"] += 1
        self._data["month_count"] += 1
        self._save()

    def snapshot(self) -> dict:
        return {
            "hour_used": self._data.get("hour_count", 0),
            "hour_limit": HOURLY_LIMIT,
            "month_used": self._data.get("month_count", 0),
            "month_limit": MONTHLY_LIMIT,
        }
