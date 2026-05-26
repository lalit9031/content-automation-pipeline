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
class LongFormScene:
    title: str
    on_screen_text: str
    narration: str
    duration_seconds: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongFormScene":
        duration = data.get("duration_seconds")
        if not isinstance(duration, int) or not 8 <= duration <= 20:
            raise ValueError("long-form scene duration_seconds must be between 8 and 20")
        return cls(
            title=_required_text(data, "title"),
            on_screen_text=_required_text(data, "on_screen_text"),
            narration=_required_text(data, "narration"),
            duration_seconds=duration,
        )


@dataclass(frozen=True)
class LongFormVideoScript:
    title: str
    scenes: list[LongFormScene]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongFormVideoScript":
        raw_scenes = data.get("scenes", [])
        if not isinstance(raw_scenes, list) or not raw_scenes:
            raise ValueError("long-form video scenes must be a non-empty list")
        return cls(
            title=_required_text(data, "title"),
            scenes=[LongFormScene.from_dict(scene) for scene in raw_scenes],
        )

    @property
    def duration_seconds(self) -> int:
        return sum(scene.duration_seconds for scene in self.scenes)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InfographicPanel:
    title: str
    points: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InfographicPanel":
        points = data.get("points", [])
        if not isinstance(points, list) or not points:
            raise ValueError("infographic panel points must be a non-empty list")
        return cls(
            title=_required_text(data, "title"),
            points=[str(point).strip() for point in points if str(point).strip()],
        )


@dataclass(frozen=True)
class LinkedInInfographic:
    headline: str
    subtitle: str
    left_panel: InfographicPanel
    right_panel: InfographicPanel
    takeaway_title: str
    takeaway_points: list[str]
    workflow: list[str]
    discussion_prompt: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinkedInInfographic":
        takeaway_points = data.get("takeaway_points", [])
        workflow = data.get("workflow", [])
        if not isinstance(takeaway_points, list) or not takeaway_points:
            raise ValueError("linkedin_infographic.takeaway_points must be a non-empty list")
        if not isinstance(workflow, list) or not workflow:
            raise ValueError("linkedin_infographic.workflow must be a non-empty list")
        return cls(
            headline=_required_text(data, "headline"),
            subtitle=_required_text(data, "subtitle"),
            left_panel=InfographicPanel.from_dict(data.get("left_panel", {})),
            right_panel=InfographicPanel.from_dict(data.get("right_panel", {})),
            takeaway_title=_required_text(data, "takeaway_title"),
            takeaway_points=[
                str(point).strip() for point in takeaway_points if str(point).strip()
            ],
            workflow=[str(step).strip() for step in workflow if str(step).strip()],
            discussion_prompt=_required_text(data, "discussion_prompt"),
        )


@dataclass(frozen=True)
class ContentPackage:
    date: str
    topic: str
    image_prompt: str
    linkedin_infographic: LinkedInInfographic
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
            linkedin_infographic=LinkedInInfographic.from_dict(
                data.get("linkedin_infographic", {})
            ),
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
