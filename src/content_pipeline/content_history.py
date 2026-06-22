from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HISTORY_FILENAME = "content_history.json"


@dataclass(frozen=True)
class ContentHistoryEntry:
    date: str
    kind: str
    topic: str
    normalized_topic: str
    title: str = ""
    platform: str = ""
    reference: str = ""
    url: str = ""
    source: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContentHistory:
    entries: list[ContentHistoryEntry]

    @classmethod
    def load(cls, output_dir: Path) -> "ContentHistory":
        path = history_path(output_dir)
        if not path.exists():
            return cls(entries=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_entries = data.get("entries", []) if isinstance(data, dict) else []
        entries = [ContentHistoryEntry(**entry) for entry in raw_entries if isinstance(entry, dict)]
        return cls(entries=entries)

    def save(self, output_dir: Path) -> Path:
        path = history_path(output_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": [entry.as_dict() for entry in self.entries],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def topic_keys(self) -> set[str]:
        return {entry.normalized_topic for entry in self.entries if entry.normalized_topic}

    def recent_topics(self, limit: int = 12) -> list[str]:
        topics: list[str] = []
        for entry in reversed(self.entries):
            if entry.normalized_topic and entry.normalized_topic not in topics:
                topics.append(entry.normalized_topic)
            if len(topics) >= limit:
                break
        return list(reversed(topics))

    def add_entry(
        self,
        *,
        date: str,
        kind: str,
        topic: str,
        title: str = "",
        platform: str = "",
        reference: str = "",
        url: str = "",
        source: str = "",
    ) -> "ContentHistory":
        normalized_topic = normalize_topic(topic)
        entry = ContentHistoryEntry(
            date=date,
            kind=kind,
            topic=topic.strip(),
            normalized_topic=normalized_topic,
            title=title.strip(),
            platform=platform.strip(),
            reference=reference.strip(),
            url=url.strip(),
            source=source.strip(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return ContentHistory(entries=[*self.entries, entry])


def history_path(output_dir: Path) -> Path:
    return output_dir / HISTORY_FILENAME


def normalize_topic(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def record_history_entry(
    output_dir: Path,
    *,
    date: str,
    kind: str,
    topic: str,
    title: str = "",
    platform: str = "",
    reference: str = "",
    url: str = "",
    source: str = "",
) -> Path:
    history = ContentHistory.load(output_dir)
    history = history.add_entry(
        date=date,
        kind=kind,
        topic=topic,
        title=title,
        platform=platform,
        reference=reference,
        url=url,
        source=source,
    )
    return history.save(output_dir)


def select_unused_topics(candidates: list[str], used_topics: set[str]) -> list[str]:
    selected: list[str] = []
    seen = set(used_topics)
    for candidate in candidates:
        normalized = normalize_topic(candidate)
        if not normalized or _topic_seen(normalized, seen):
            continue
        selected.append(candidate)
        seen.add(normalized)
    return selected


def _topic_seen(candidate: str, used_topics: set[str]) -> bool:
    candidate_tokens = set(candidate.split())
    candidate_prefix = candidate.split()[:3]
    for used in used_topics:
        if candidate == used or candidate in used or used in candidate:
            return True
        if candidate_prefix and candidate_prefix == used.split()[:3]:
            return True
        used_tokens = set(used.split())
        shared = candidate_tokens & used_tokens
        if len(shared) >= 3 and len(shared) / max(1, min(len(candidate_tokens), len(used_tokens))) >= 0.55:
            return True
    return False
