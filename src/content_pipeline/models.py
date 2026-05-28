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



@dataclass(frozen=True)
class VideoClip:
    """A single 5-8 second video segment."""
    id: str
    title: str
    duration_seconds: int
    narration: str
    on_screen_text: str
    visual_mode: str  # "2_5d_image" or "motion_video"
    prompt: str
    source_type: str  # "auto_2_5d" or "manual"
    expected_file: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoClip":
        duration = data.get("duration_seconds", 0)
        if not 3 <= duration <= 15:
            raise ValueError(f"clip duration_seconds must be between 3 and 15, got {duration}")
        if data.get("visual_mode") not in ("2_5d_image", "motion_video"):
            raise ValueError('visual_mode must be "2_5d_image" or "motion_video"')
        if data.get("source_type") not in ("auto_2_5d", "manual"):
            raise ValueError('source_type must be "auto_2_5d" or "manual"')
        return cls(
            id=_required_text(data, "id"),
            title=_required_text(data, "title"),
            duration_seconds=duration,
            narration=data.get("narration", ""),
            on_screen_text=data.get("on_screen_text", ""),
            visual_mode=data["visual_mode"],
            prompt=_required_text(data, "prompt"),
            source_type=data["source_type"],
            expected_file=_required_text(data, "expected_file"),
        )


@dataclass(frozen=True)
class VideoEpisode:
    """A 2-3 minute collection of clips with narration and metadata."""
    episode_id: str
    title: str
    description: str
    aspect: str  # "shorts" or "landscape"
    width: int
    height: int
    clips: list[VideoClip]
    youtube_title: str
    youtube_description: str
    hashtags: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoEpisode":
        aspect = data.get("aspect", "shorts")
        if aspect not in ("shorts", "landscape"):
            raise ValueError('aspect must be "shorts" or "landscape"')
        width, height = (720, 1280) if aspect == "shorts" else (1280, 720)
        raw_clips = data.get("clips", [])
        if not isinstance(raw_clips, list) or not raw_clips:
            raise ValueError("clips must be a non-empty list")
        return cls(
            episode_id=_required_text(data, "episode_id"),
            title=_required_text(data, "title"),
            description=_required_text(data, "description"),
            aspect=aspect,
            width=int(data.get("width", width)),
            height=int(data.get("height", height)),
            clips=[VideoClip.from_dict(clip) for clip in raw_clips],
            youtube_title=_required_text(data, "youtube_title"),
            youtube_description=_required_text(data, "youtube_description"),
            hashtags=[str(tag).strip() for tag in data.get("hashtags", []) if str(tag).strip()],
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def duration_seconds(self) -> int:
        return sum(clip.duration_seconds for clip in self.clips)


@dataclass(frozen=True)
class VideoCompilation:
    """A 20-30 minute video combining multiple episodes."""
    compilation_id: str
    title: str
    description: str
    episode_ids: list[str]
    transition_duration_seconds: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoCompilation":
        episode_ids = data.get("episode_ids", [])
        if not isinstance(episode_ids, list) or not episode_ids:
            raise ValueError("episode_ids must be a non-empty list")
        return cls(
            compilation_id=_required_text(data, "compilation_id"),
            title=_required_text(data, "title"),
            description=_required_text(data, "description"),
            episode_ids=[str(eid) for eid in episode_ids],
            transition_duration_seconds=max(
                1, int(data.get("transition_duration_seconds", 2))
            ),
        )

    @property
    def estimated_duration_seconds(self) -> int:
        """Rough estimate of transition overhead only; episode durations are unknown at this level."""
        if len(self.episode_ids) < 2:
            return 0
        return (len(self.episode_ids) - 1) * self.transition_duration_seconds

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
