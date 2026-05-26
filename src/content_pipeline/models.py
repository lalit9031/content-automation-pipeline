from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class VideoScript:
    hook: str
    points: list[str]
    cta: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoScript":
        points = data.get("points", [])
        if not isinstance(points, list) or not points:
            raise ValueError("video_script.points must be a non-empty list")
        return cls(
            hook=_required_text(data, "hook"),
            points=[str(point).strip() for point in points if str(point).strip()],
            cta=_required_text(data, "cta"),
        )


@dataclass(frozen=True)
class ContentPackage:
    date: str
    topic: str
    image_prompt: str
    video_script: VideoScript
    linkedin_caption: str
    hashtags: list[str]
    seo_title: str
    seo_description: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentPackage":
        package_date = _required_text(data, "date")
        date.fromisoformat(package_date)
        hashtags = data.get("hashtags", [])
        if not isinstance(hashtags, list) or not hashtags:
            raise ValueError("hashtags must be a non-empty list")
        return cls(
            date=package_date,
            topic=_required_text(data, "topic"),
            image_prompt=_required_text(data, "image_prompt"),
            video_script=VideoScript.from_dict(data.get("video_script", {})),
            linkedin_caption=_required_text(data, "linkedin_caption"),
            hashtags=[str(tag).strip() for tag in hashtags if str(tag).strip()],
            seo_title=_required_text(data, "seo_title"),
            seo_description=_required_text(data, "seo_description"),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
