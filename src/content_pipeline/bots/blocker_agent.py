from __future__ import annotations

import json
import traceback
from html import escape
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BLOCKER_JOURNAL_FILENAME = "blocker_journal.json"


@dataclass(frozen=True)
class BlockerEntry:
    id: str
    created_at: str
    updated_at: str
    status: str
    command: str
    component: str
    issue: str
    solution: str = ""
    severity: str = "medium"
    tags: list[str] = field(default_factory=list)
    error_type: str = ""
    traceback_excerpt: str = ""
    source: str = "auto"
    source_title: str = ""
    source_url: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def blocker_journal_path(output_dir: Path) -> Path:
    return output_dir / BLOCKER_JOURNAL_FILENAME


def load_blocker_journal(output_dir: Path) -> dict[str, Any]:
    path = blocker_journal_path(output_dir)
    if not path.exists():
        return {"version": 1, "entries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "entries": []}
    data.setdefault("version", 1)
    data.setdefault("entries", [])
    return data


def record_blocker(
    output_dir: Path,
    *,
    command: str,
    issue: str,
    solution: str = "",
    component: str = "",
    severity: str = "medium",
    tags: list[str] | None = None,
    error: Exception | None = None,
    source: str = "manual",
    source_title: str = "",
    source_url: str = "",
    notes: str = "",
) -> Path:
    journal = load_blocker_journal(output_dir)
    entries = [entry for entry in journal.get("entries", []) if isinstance(entry, dict)]
    now = datetime.now(timezone.utc).isoformat()
    entry = BlockerEntry(
        id=_entry_id(command, issue, now),
        created_at=now,
        updated_at=now,
        status="open" if not solution else "resolved",
        command=command.strip(),
        component=component.strip(),
        issue=issue.strip(),
        solution=solution.strip(),
        severity=severity.strip().lower() or "medium",
        tags=[tag.strip() for tag in (tags or []) if tag.strip()],
        error_type=error.__class__.__name__ if error else "",
        traceback_excerpt=_traceback_excerpt(error) if error else "",
        source=source,
        source_title=source_title.strip(),
        source_url=source_url.strip(),
        notes=notes.strip(),
    )
    entries.append(entry.as_dict())
    payload = {"version": 1, "entries": entries}
    path = blocker_journal_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def resolve_blocker(output_dir: Path, blocker_id: str, solution: str) -> Path:
    journal = load_blocker_journal(output_dir)
    entries = [entry for entry in journal.get("entries", []) if isinstance(entry, dict)]
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    for entry in entries:
        if entry.get("id") == blocker_id:
            entry["solution"] = solution.strip()
            entry["status"] = "resolved"
            entry["updated_at"] = now
            updated = True
    if not updated:
        raise ValueError(f"Unknown blocker id: {blocker_id}")
    path = blocker_journal_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "entries": entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def blocker_status(output_dir: Path) -> dict[str, Any]:
    journal = load_blocker_journal(output_dir)
    entries = [entry for entry in journal.get("entries", []) if isinstance(entry, dict)]
    open_entries = [entry for entry in entries if entry.get("status") != "resolved"]
    resolved_entries = [entry for entry in entries if entry.get("status") == "resolved"]
    recent_open = open_entries[-5:]
    recent_resolved = resolved_entries[-5:]
    lessons = [
        {
            "id": entry.get("id", ""),
            "issue": entry.get("issue", ""),
            "solution": entry.get("solution", ""),
            "command": entry.get("command", ""),
            "severity": entry.get("severity", "medium"),
            "tags": entry.get("tags", []),
            "status": entry.get("status", "open"),
            "source_title": entry.get("source_title", ""),
            "source_url": entry.get("source_url", ""),
        }
        for entry in recent_open
    ]
    resolved_lessons = [
        {
            "id": entry.get("id", ""),
            "issue": entry.get("issue", ""),
            "solution": entry.get("solution", ""),
            "command": entry.get("command", ""),
            "severity": entry.get("severity", "medium"),
            "tags": entry.get("tags", []),
            "status": entry.get("status", "resolved"),
            "source_title": entry.get("source_title", ""),
            "source_url": entry.get("source_url", ""),
            "notes": entry.get("notes", ""),
        }
        for entry in recent_resolved
    ]
    suggestions = suggest_blocker_fixes(output_dir, limit=5)
    return {
        "journal_path": str(blocker_journal_path(output_dir)),
        "total_entries": len(entries),
        "open_count": len(open_entries),
        "resolved_count": len(resolved_entries),
        "recent_open": lessons,
        "recent_resolved": resolved_lessons,
        "suggestions": suggestions,
    }


def blocker_status_html(output_dir: Path) -> str:
    status = blocker_status(output_dir)
    rows: list[str] = []
    for entry in status["recent_open"]:
        severity = f" <em>({escape(str(entry['severity']))})</em>" if entry.get("severity") else ""
        solution = f" - {escape(str(entry['solution']))}" if entry.get("solution") else ""
        command = escape(str(entry.get("command") or "unknown"))
        issue = escape(str(entry.get("issue") or ""))
        source = ""
        if entry.get("source_title") or entry.get("source_url"):
            source_bits = []
            if entry.get("source_title"):
                source_bits.append(escape(str(entry["source_title"])))
            if entry.get("source_url"):
                source_bits.append(escape(str(entry["source_url"])))
            source = f" <span style=\"color:#94a3b8;\">[{ ' | '.join(source_bits) }]</span>"
        rows.append(f"<li><strong>{command}</strong>: {issue}{severity}{solution}{source}</li>")
    rows_html = "".join(rows)
    if not rows_html:
        rows_html = "<li>No open blockers recorded.</li>"
    suggestions = status.get("suggestions", [])
    suggestion_html = ""
    if suggestions:
        suggestion_items = []
        for suggestion in suggestions[:3]:
            source_note = (
                f" from {escape(str(suggestion.get('source_title')))}"
                if suggestion.get("source_title")
                else ""
            )
            suggestion_items.append(
                "<li>"
                f"<strong>{escape(str(suggestion.get('solution') or ''))}</strong>"
                f"<span style=\"color:#94a3b8;\">"
                f" matched {escape(str(suggestion.get('match_score') or 0))} keywords"
                f"{source_note}"
                "</span>"
                "</li>"
            )
        suggestion_html = (
            '<div style="margin-top:14px;font-size:13px;">'
            '<div style="font-weight:700;color:#fca5a5;margin-bottom:6px;">Suggested prior fixes</div>'
            f"<ul style=\"margin:0;padding-left:18px;color:#cbd5e1;\">{''.join(suggestion_items)}</ul>"
            "</div>"
        )
    return f"""<section style="background:#111827;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
    <div>
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#fca5a5;font-weight:800;">Blocker learning agent</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px;">{status['open_count']} open / {status['resolved_count']} resolved</div>
    </div>
    <div style="font-size:12px;color:#94a3b8;text-align:right;">Journal: {status['journal_path']}</div>
  </div>
  <ul style="margin:14px 0 0;padding-left:18px;color:#cbd5e1;">{rows_html}</ul>
  {suggestion_html}
</section>"""


def log_exception(
    output_dir: Path,
    *,
    command: str,
    exc: Exception,
    component: str = "",
) -> Path:
    return record_blocker(
        output_dir,
        command=command,
        issue=str(exc),
        component=component or "cli",
        severity="high",
        tags=[exc.__class__.__name__.lower(), "auto-captured"],
        error=exc,
        source="auto",
    )


def suggest_blocker_fixes(output_dir: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    journal = load_blocker_journal(output_dir)
    entries = [entry for entry in journal.get("entries", []) if isinstance(entry, dict)]
    resolved = [entry for entry in entries if entry.get("status") == "resolved" and entry.get("solution")]
    suggestions: list[dict[str, Any]] = []
    for entry in resolved:
        score = _solution_match_score(entry)
        if score <= 0:
            continue
        suggestions.append(
            {
                "id": entry.get("id", ""),
                "issue": entry.get("issue", ""),
                "solution": entry.get("solution", ""),
                "command": entry.get("command", ""),
                "severity": entry.get("severity", "medium"),
                "source_title": entry.get("source_title", ""),
                "source_url": entry.get("source_url", ""),
                "match_score": score,
            }
        )
    suggestions.sort(key=lambda item: (item["match_score"], item.get("severity") == "high"), reverse=True)
    return suggestions[:limit]


def absorb_blocker_solution(
    output_dir: Path,
    *,
    issue: str,
    solution: str,
    command: str = "",
    component: str = "",
    source_title: str = "",
    source_url: str = "",
    notes: str = "",
    severity: str = "low",
    tags: list[str] | None = None,
) -> Path:
    return record_blocker(
        output_dir,
        command=command or "blocker-learn",
        issue=issue,
        solution=solution,
        component=component,
        severity=severity,
        tags=tags or [],
        source="manual",
        source_title=source_title,
        source_url=source_url,
        notes=notes,
    )


def _entry_id(command: str, issue: str, created_at: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in f"{command}-{issue}").strip("-").lower()
    return f"{slug[:40] or 'blocker'}-{created_at[:19].replace(':', '').replace('-', '').replace('T', '')}"


def _traceback_excerpt(error: Exception | None) -> str:
    if error is None:
        return ""
    return "".join(traceback.format_exception_only(error.__class__, error)).strip()


def _solution_match_score(entry: dict[str, Any]) -> int:
    haystack = " ".join(
        str(entry.get(field, ""))
        for field in ("issue", "solution", "command", "component", "notes", "source_title")
    ).lower()
    score = 0
    for token in ("error", "limit", "rate", "quota", "429", "fallback", "retry", "auth", "billing", "timeout"):
        if token in haystack:
            score += 1
    return score
