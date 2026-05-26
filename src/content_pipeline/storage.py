from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LocalDailyStorage:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def daily_path(self, day: str, *parts: str) -> Path:
        path = self.output_dir / "daily" / day
        for part in parts:
            path = path / part
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, day: str, filename: str, value: Any) -> Path:
        path = self.daily_path(day, filename)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def read_json(self, day: str, filename: str) -> Any | None:
        path = self.output_dir / "daily" / day / filename
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, day: str, filename: str, value: str) -> Path:
        path = self.daily_path(day, filename)
        path.write_text(value, encoding="utf-8")
        return path

    def write_bytes(self, day: str, filename: str, value: bytes) -> Path:
        path = self.daily_path(day, filename)
        path.write_bytes(value)
        return path
