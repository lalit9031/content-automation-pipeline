from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from content_pipeline.bots.image import ImageProvider, ImageVariant


WORKFLOW_ID = "kanha_ki_nanhi_leela"
WORKFLOW_VERSION = "1.0"


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    responsibility: str
    inputs: list[str]
    outputs: list[str]
    approval_before_next_step: str


@dataclass(frozen=True)
class ImageShot:
    id: str
    purpose: str
    prompt: str
    output_basename: str


@dataclass(frozen=True)
class ImagePlan:
    project_id: str
    provider_mode: str
    shots: list[ImageShot]
    rules: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "provider_mode": self.provider_mode,
            "shots": [asdict(shot) for shot in self.shots],
            "rules": self.rules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImagePlan":
        return cls(
            project_id=data["project_id"],
            provider_mode=data["provider_mode"],
            shots=[ImageShot(**shot) for shot in data["shots"]],
            rules=list(data["rules"]),
        )


def agent_registry() -> list[AgentDefinition]:
    return [
        AgentDefinition(
            id="story_agent",
            responsibility="Create age-appropriate Hindi story scripts, morals and metadata.",
            inputs=["episode theme", "age suitability rules"],
            outputs=["script", "scene brief", "title and description"],
            approval_before_next_step="Story is gentle, original and suitable for young children.",
        ),
        AgentDefinition(
            id="voice_agent",
            responsibility="Generate Hindi narrator samples and approved narration audio.",
            inputs=["approved script", "pronunciation glossary", "approved voice source"],
            outputs=["voice samples", "narration audio", "AI voice disclosure text"],
            approval_before_next_step="Creator chooses voice; any custom voice has explicit recorded consent.",
        ),
        AgentDefinition(
            id="image_agent",
            responsibility="Create original storyboard, thumbnail and setting images.",
            inputs=["approved scene brief", "visual rules"],
            outputs=["image_plan.json", "approved still assets"],
            approval_before_next_step="No copied studio style, copyrighted character or identifiable real face.",
        ),
        AgentDefinition(
            id="motion_video_agent",
            responsibility="Generate short real-motion clips for approved scenes.",
            inputs=["motion_plan.json", "provider restrictions"],
            outputs=["individual MP4 clips", "generation receipt"],
            approval_before_next_step="Failed or blocked character renders are not bypassed.",
        ),
        AgentDefinition(
            id="assembly_agent",
            responsibility="Combine approved motion clips, narration, captions and licensed audio.",
            inputs=["approved clips", "narration", "subtitles", "licensed audio only"],
            outputs=["final review MP4", "subtitle files"],
            approval_before_next_step="Human views the final render before compliance approval.",
        ),
        AgentDefinition(
            id="copyright_policy_agent",
            responsibility="Check rights, disclosures, child safety and YouTube policy status.",
            inputs=["final MP4", "metadata", "rights declarations"],
            outputs=["youtube_policy_report.json", "SHA-256 approval fingerprint"],
            approval_before_next_step="Every check passes; report is current and matches final MP4.",
        ),
        AgentDefinition(
            id="youtube_publish_agent",
            responsibility="Upload only an approved final MP4 to YouTube.",
            inputs=["passed policy report", "approved MP4", "YouTube OAuth"],
            outputs=["private or unlisted YouTube video ID"],
            approval_before_next_step="Public publication remains a separate deliberate decision.",
        ),
    ]


def voice_source_policy() -> dict[str, Any]:
    return {
        "default_mode": "built_in_ai_voice",
        "currently_allowed": [
            "OpenAI built-in voices with AI-generated voice disclosure.",
            "The creator's own voice with explicit consent recorded.",
            "A hired narrator voice only with written permission and voice-model consent recorded.",
        ],
        "not_accepted_for_voice_cloning": [
            "Celebrity, actor, public figure or devotional singer recordings.",
            "Audio downloaded from YouTube, reels, films, TV or podcasts.",
            "A voice described only as free, royalty-free or open-source without the speaker's consent to synthetic voice creation.",
        ],
        "later_custom_voice_requirements": [
            "Provider eligibility for custom voices.",
            "A provider-required consent recording by the same speaker.",
            "A clean sample recording by that speaker.",
            "AI voice disclosure in audience-facing metadata.",
        ],
        "reason": "Copyright or an open license for audio does not by itself grant permission to create a synthetic likeness of the speaker's voice.",
        "source": "https://developers.openai.com/api/docs/guides/text-to-speech#custom-voices",
    }


def bal_krishna_image_plan() -> ImagePlan:
    common = (
        "Original bright premium 3D Indian family-animation setting, vertical 9:16, "
        "warm Gokul village sunlight, vibrant rangoli and marigold decorations. "
        "No copyrighted cartoon character, no copied film-studio style, no real-person "
        "likeness, no text, logo or watermark. "
    )
    return ImagePlan(
        project_id="bal_krishna_image_validation",
        provider_mode="safe_environment_assets",
        shots=[
            ImageShot(
                id="gokul_courtyard",
                purpose="Opening setting and possible thumbnail background",
                output_basename="images/scene_01_gokul_courtyard",
                prompt=(
                    f"{common} Empty joyful Gokul courtyard at sunrise, decorated clay "
                    "butter pot hanging safely from a flower-covered rope, leafy tree "
                    "above, white clouds and a colorful rangoli below."
                ),
            ),
            ImageShot(
                id="butter_feather_close",
                purpose="Closing setting frame for emotional transition",
                output_basename="images/scene_02_butter_feather_close",
                prompt=(
                    f"{common} Close-up of a painted clay butter pot resting on a clean "
                    "rangoli cloth, fresh butter visible at the rim, a peacock feather "
                    "beside it and soft golden sunbeams from above."
                ),
            ),
        ],
        rules=[
            "Use environment-only validation assets while character motion remains provider-blocked.",
            "Do not use uploaded baby or mother photographs as generation inputs.",
            "Character artwork must remain fictional and must be approved separately before public distribution.",
        ],
    )


def initialize_agent_workspace(output_dir: Path) -> list[Path]:
    root = output_dir / WORKFLOW_ID
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "workflow_id": WORKFLOW_ID,
        "version": WORKFLOW_VERSION,
        "agent_order": [asdict(agent) for agent in agent_registry()],
        "handoff_rule": "Each agent consumes only approved artifacts from the prior stage.",
        "publication_rule": "No public upload without a passed policy report and explicit creator approval.",
    }
    manifest_path = root / "agent_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    voice_policy_path = root / "voice_source_policy.json"
    voice_policy_path.write_text(json.dumps(voice_source_policy(), indent=2) + "\n", encoding="utf-8")
    image_plan_path = write_image_plan(bal_krishna_image_plan(), output_dir)
    return [manifest_path, voice_policy_path, image_plan_path]


def write_image_plan(plan: ImagePlan, output_dir: Path) -> Path:
    path = output_dir / plan.project_id / "image_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.as_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def generate_planned_images(
    plan: ImagePlan,
    provider: ImageProvider,
    output_dir: Path,
) -> list[Path]:
    root = output_dir / plan.project_id
    variant = ImageVariant("9:16", 1080, 1920, "unused")
    outputs: list[Path] = []
    for shot in plan.shots:
        path = root / f"{shot.output_basename}{provider.extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(provider.create(shot.prompt, variant))
        outputs.append(path)
    return outputs
