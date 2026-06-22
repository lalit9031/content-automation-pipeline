from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_pipeline.bots.linkedin import publish_linkedin_custom_image
from content_pipeline.bots.linkedin_video import render_linkedin_post_from_video_details
from content_pipeline.bots.youtube import get_my_video_details, list_my_uploaded_videos
from content_pipeline.config import Settings


STATE_FILE = "state/youtube_public_sync.json"


@dataclass(frozen=True)
class PublicVideoSyncItem:
    video_id: str
    title: str
    privacy_status: str
    youtube_url: str
    linkedin_post_id: str = ""
    linked_at: str = ""
    telegram_sent_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_sync_state(project_dir: Path) -> dict[str, Any]:
    path = project_dir / STATE_FILE
    if not path.exists():
        return {"processed_video_ids": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"processed_video_ids": []}
    data.setdefault("processed_video_ids", [])
    return data


def save_sync_state(project_dir: Path, state: dict[str, Any]) -> Path:
    path = project_dir / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def sync_public_youtube_uploads(
    settings: Settings,
    project_dir: Path,
) -> list[PublicVideoSyncItem]:
    state_path = project_dir / STATE_FILE
    state = load_sync_state(project_dir)
    processed = set(state.get("processed_video_ids", []))
    uploaded = list_my_uploaded_videos(settings, max_results=50)
    video_ids = [item["video_id"] for item in uploaded if item.get("video_id")]
    details = {item["video_id"]: item for item in get_my_video_details(settings, video_ids)}

    results: list[PublicVideoSyncItem] = []
    for uploaded_item in uploaded:
        video_id = uploaded_item["video_id"]
        if video_id in processed:
            continue
        detail = details.get(video_id)
        if not detail:
            continue
        if detail.get("privacy_status") != "public":
            continue

        youtube_url = f"https://youtu.be/{video_id}"
        image_path = project_dir / "state" / "linkedin_cards" / f"{video_id}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_path = render_linkedin_post_from_video_details(
            title=detail["title"],
            description=detail.get("description", ""),
            youtube_url=youtube_url,
            hashtags=[tag if str(tag).startswith("#") else f"#{tag}" for tag in detail.get("tags", [])],
            output_path=image_path,
        )

        caption = _compose_linkedin_caption(
            title=detail["title"],
            description=detail.get("description", ""),
            youtube_url=youtube_url,
            tags=detail.get("tags", []),
        )
        linkedin_post_id = publish_linkedin_custom_image(
            settings=settings,
            image_path=rendered_path,
            caption=caption,
            media_title=detail["title"],
        )
        processed.add(video_id)
        results.append(
            PublicVideoSyncItem(
                video_id=video_id,
                title=detail["title"],
                privacy_status=detail["privacy_status"],
                youtube_url=youtube_url,
                linkedin_post_id=linkedin_post_id,
                linked_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    if results:
        state["processed_video_ids"] = sorted(processed)
        state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
        state["results"] = [item.as_dict() for item in results]
        save_sync_state(project_dir, state)
    return results


def _compose_linkedin_caption(title: str, description: str, youtube_url: str, tags: list[str]) -> str:
    tag_text = " ".join(tag if str(tag).startswith("#") else f"#{tag}" for tag in tags[:8])
    body = description.strip().replace("\n", "\n")
    pieces = [
        title.strip(),
        body,
        f"Watch the full video: {youtube_url}",
        tag_text,
    ]
    return "\n\n".join(part for part in pieces if part)
