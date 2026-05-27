from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings


@dataclass(frozen=True)
class MotionClip:
    id: str
    title: str
    duration_seconds: int
    prompt: str
    output_file: str


@dataclass(frozen=True)
class MotionPlan:
    project_id: str
    title: str
    provider: str
    model: str
    size: str
    clips: list[MotionClip]
    provider_rules: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "provider": self.provider,
            "model": self.model,
            "size": self.size,
            "clips": [asdict(clip) for clip in self.clips],
            "provider_rules": self.provider_rules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MotionPlan":
        return cls(
            project_id=data["project_id"],
            title=data["title"],
            provider=data["provider"],
            model=data["model"],
            size=data["size"],
            clips=[MotionClip(**clip) for clip in data["clips"]],
            provider_rules=list(data["provider_rules"]),
        )


def bal_krishna_validation_plan(model: str = "sora-2") -> MotionPlan:
    character = (
        "An original stylized 3D animated fictional toddler Kanha, gentle blue-toned skin, "
        "curly dark hair, a tiny peacock feather and yellow dhoti. This is an imaginary "
        "storybook character, not a real child and not based on an identifiable person. "
    )
    look = (
        "Original premium bright Indian family-animation look, colorful Gokul courtyard, "
        "rounded expressive features, devotional warmth, child-safe joyful mood. "
        "Do not imitate any film studio or copyrighted cartoon. No text, logo or watermark. "
    )
    return MotionPlan(
        project_id="bal_krishna_motion_validation",
        title="Kanha Ki Nanhi Leela - Motion Validation",
        provider="openai_sora",
        model=model,
        size="720x1280",
        clips=[
            MotionClip(
                id="kanha_notices_butter",
                title="Kanha notices the butter pot",
                duration_seconds=8,
                output_file="clips/scene_01_kanha_notices_butter.mp4",
                prompt=(
                    f"{character}{look} Vertical medium shot: Kanha stands safely on the "
                    "courtyard floor and looks up at a decorated hanging butter pot. He "
                    "blinks, turns his gaze toward the pot and forms a mischievous gentle "
                    "smile. His peacock feather sways softly; marigold garlands flutter, "
                    "tree leaves move in a light breeze and small clouds drift slowly. "
                    "Camera makes a very gentle push-in. No climbing, no falling, no danger."
                ),
            ),
            MotionClip(
                id="yashoda_hugs_kanha",
                title="Yashoda hugs Kanha",
                duration_seconds=8,
                output_file="clips/scene_02_yashoda_hugs_kanha.mp4",
                prompt=(
                    f"{character}{look} Vertical warm closing shot: a fictional animated "
                    "mother Yashoda in an orange and pink sari kneels in the courtyard and "
                    "gently hugs smiling Kanha. Kanha closes his eyes happily. Sun rays "
                    "glow through moving tree leaves, flower petals drift lightly, a calf "
                    "stands peacefully in the background. Tender natural movement only; "
                    "no real-person likeness and no frightening action."
                ),
            ),
        ],
        provider_rules=[
            "Sora video input must be prompt-only for these scenes; do not upload family photos or face-reference images.",
            "Sora output must remain suitable for audiences under 18.",
            "Do not request copyrighted characters, copyrighted music, real people or copied studio styles.",
            "Vertex Veo is not selected for these child-character clips because the installed SDK permits person generation only as dont_allow or allow_adult.",
        ],
    )


def bal_krishna_environment_validation_plan(model: str = "sora-2") -> MotionPlan:
    look = (
        "Original premium bright 3D Indian family-animation setting, vibrant decorated "
        "Gokul courtyard, warm morning sunlight, rounded clay architecture, devotional "
        "joy. No people, no faces, no human likeness, no copyrighted characters, no "
        "copyrighted music, no studio imitation, no text, logo or watermark. "
    )
    return MotionPlan(
        project_id="bal_krishna_environment_motion_validation",
        title="Kanha Ki Nanhi Leela - Environment Motion Validation",
        provider="openai_sora",
        model=model,
        size="720x1280",
        clips=[
            MotionClip(
                id="gokul_butter_pot_breeze",
                title="Gokul butter pot and morning breeze",
                duration_seconds=8,
                output_file="clips/scene_01_gokul_butter_pot_breeze.mp4",
                prompt=(
                    f"{look} Vertical wide shot of an empty cheerful Gokul courtyard. "
                    "A decorated clay butter pot hangs securely from a flower-covered "
                    "rope and sways only slightly in a gentle breeze. Marigold garlands "
                    "flutter, leafy tree branches move softly and small white clouds drift "
                    "through the blue sky. Camera slowly pushes forward. Everything calm "
                    "and safe."
                ),
            ),
            MotionClip(
                id="butter_feather_warm_close",
                title="Butter pot and peacock feather closing mood",
                duration_seconds=8,
                output_file="clips/scene_02_butter_feather_close.mp4",
                prompt=(
                    f"{look} Vertical close-up of a decorated clay butter pot resting on "
                    "a clean colorful rangoli cloth. A single peacock feather lies beside "
                    "it and moves gently in the breeze. Soft golden sunbeams shift through "
                    "tree leaves, a few flower petals drift slowly, and the camera glides "
                    "very slightly closer. Peaceful emotional closing mood."
                ),
            ),
        ],
        provider_rules=[
            "This provider-validation plan contains no people or faces.",
            "The requested Kanha and Yashoda character-motion plan is retained separately and must not be rendered after a moderation rejection without a supported provider path.",
            "Do not upload family photos or face-reference images to Sora.",
            "Do not request copyrighted characters, copyrighted music, real people or copied studio styles.",
        ],
    )


def write_motion_plan(plan: MotionPlan, output_dir: Path) -> Path:
    path = output_dir / plan.project_id / "motion_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.as_dict(), indent=2) + "\n", encoding="utf-8")
    return path


class SoraMotionProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for MOTION_PROVIDER=openai_sora")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.client = OpenAI(api_key=settings.openai_api_key)

    def create_clip(self, clip: MotionClip, plan: MotionPlan, destination: Path) -> dict[str, str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"Starting Sora clip: {clip.id} ({clip.duration_seconds}s, {plan.size})")
        video = self.client.videos.create(
            model=plan.model,
            prompt=clip.prompt,
            seconds=str(clip.duration_seconds),
            size=plan.size,
        )
        while video.status in ("queued", "in_progress"):
            print(f"Waiting for {clip.id}: {video.status}")
            time.sleep(10)
            video = self.client.videos.retrieve(video.id)
        if video.status != "completed":
            message = getattr(getattr(video, "error", None), "message", video.status)
            raise RuntimeError(f"Sora video generation failed for {clip.id}: {message}")
        content = self.client.videos.download_content(video.id, variant="video")
        content.write_to_file(destination)
        print(f"Completed Sora clip: {destination}")
        return {"clip_id": clip.id, "video_id": video.id, "file": str(destination)}


def generate_motion_clips(plan: MotionPlan, settings: Settings, output_dir: Path) -> list[dict[str, str]]:
    if settings.motion_provider != "openai_sora":
        raise ValueError("Set MOTION_PROVIDER=openai_sora to generate real motion clips.")
    provider = SoraMotionProvider(settings)
    project_dir = output_dir / plan.project_id
    results = []
    for clip in plan.clips:
        try:
            result = provider.create_clip(clip, plan, project_dir / clip.output_file)
            results.append({"status": "completed", **result})
        except RuntimeError as exc:
            results.append({"status": "failed", "clip_id": clip.id, "error": str(exc)})
            receipt_path = project_dir / "generation_receipt.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            raise
    receipt_path = project_dir / "generation_receipt.json"
    receipt_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def assemble_motion_preview(plan: MotionPlan, output_dir: Path) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to assemble generated motion clips.")
    project_dir = output_dir / plan.project_id
    clip_paths = [project_dir / clip.output_file for clip in plan.clips]
    missing = [str(path) for path in clip_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Generated motion clips are missing: {', '.join(missing)}")
    output_path = project_dir / "video" / "motion_validation_preview.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path = output_path.parent / "motion_clips.txt"
    concat_path.write_text(
        "\n".join(f"file '{path}'" for path in clip_paths) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-vf",
            "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path
