from __future__ import annotations

import json
import hashlib
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

from content_pipeline.bots.audio import VOICE_VARIANTS
from content_pipeline.bots.image import ImageProvider, ImageVariant
from content_pipeline.config import Settings


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


def write_voice_selection(output_dir: Path, sample_filename: str) -> Path:
    variants = {filename: voice for filename, voice, _ in VOICE_VARIANTS}
    if sample_filename not in variants:
        raise ValueError(f"Unknown Krishna voice sample: {sample_filename}")
    path = output_dir / WORKFLOW_ID / "voice_selection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    selection = {
        "workflow_id": WORKFLOW_ID,
        "selected_sample": sample_filename,
        "voice": variants[sample_filename],
        "model": "gpt-4o-mini-tts",
        "selection_status": "creator_approved",
        "selected_on": date.today().isoformat(),
        "language": "Hindi",
        "pronunciation_terms": ["यशोदा", "गोकुल", "कान्हा"],
        "disclosure_required": "Narration is AI-generated.",
        "voice_source_mode": "built_in_ai_voice",
    }
    path.write_text(json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def record_character_design_approval(
    output_dir: Path,
    kanha_image: Path,
    yashoda_image: Path,
) -> Path:
    for label, path in (("KANHA_V1", kanha_image), ("YASHODA_V1", yashoda_image)):
        if not path.exists():
            raise FileNotFoundError(f"{label} approval image is missing: {path}")
    approval = {
        "workflow_id": WORKFLOW_ID,
        "identity_version": "v1",
        "approved_on": date.today().isoformat(),
        "approval_status": "creator_approved_for_private_motion_validation",
        "approval_scope": (
            "Original fictional character design only. No real-person likeness permission "
            "is asserted and no public upload is approved."
        ),
        "characters": {
            "KANHA_V1": {
                "file": str(kanha_image),
                "sha256": hashlib.sha256(kanha_image.read_bytes()).hexdigest(),
            },
            "YASHODA_V1": {
                "file": str(yashoda_image),
                "sha256": hashlib.sha256(yashoda_image.read_bytes()).hexdigest(),
            },
        },
        "next_gate": (
            "Generate an HTTPS-hosted fictional KANHA_V1 still through a configured "
            "character-motion provider, then approve that precise hosted still before rendering motion."
        ),
    }
    path = output_dir / WORKFLOW_ID / "character_design_approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    return path


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


def bal_krishna_character_design_plan() -> ImagePlan:
    common = (
        "Original stylized 3D Indian children's story illustration, vertical 9:16, "
        "bright warm Gokul palette, rounded gentle expressions, child-safe devotional "
        "mood. Entirely fictional design; no resemblance to any uploaded or real person. "
        "Do not imitate any named animation studio or copyrighted cartoon character. "
        "No text, logo or watermark. "
    )
    return ImagePlan(
        project_id="bal_krishna_character_identity_validation",
        provider_mode="fictional_character_design_stills_only",
        shots=[
            ImageShot(
                id="kanha_v1_identity",
                purpose="Approved reference still for Kanha's consistent design",
                output_basename="images/kanha_v1_identity",
                prompt=(
                    f"{common} Character identity portrait for KANHA_V1: fictional toddler "
                    "Kanha with soft blue-toned skin, large warm brown eyes, short curly "
                    "dark hair, one small peacock feather, yellow dhoti with red waistband, "
                    "tiny gold anklets and a shy playful smile. Full body standing safely "
                    "in a sunny courtyard; butter pot visible in the background."
                ),
            ),
            ImageShot(
                id="yashoda_v1_identity",
                purpose="Approved reference still for Yashoda's consistent design",
                output_basename="images/yashoda_v1_identity",
                prompt=(
                    f"{common} Character identity portrait for YASHODA_V1: fictional "
                    "mother Yashoda with a kind oval face, dark hair in a low bun with "
                    "jasmine flowers, small red bindi, orange sari with magenta border "
                    "and simple gold bangles. Full body standing in the same sunny Gokul "
                    "courtyard, smiling gently."
                ),
            ),
        ],
        rules=[
            "Identity images are fictional visual designs, not transformations of family photographs.",
            "A human must approve KANHA_V1 and YASHODA_V1 before any character-motion provider test.",
            "Do not send these human-like character references to Sora while its current restrictions block such uploads.",
        ],
    )


def character_motion_validation_protocol() -> dict[str, Any]:
    return {
        "workflow_id": WORKFLOW_ID,
        "identity_version": "v1",
        "characters": {
            "KANHA_V1": [
                "soft blue-toned skin",
                "short curly dark hair",
                "one small peacock feather",
                "yellow dhoti with red waistband",
                "tiny gold anklets",
            ],
            "YASHODA_V1": [
                "kind oval face",
                "dark hair in a low bun with jasmine flowers",
                "small red bindi",
                "orange sari with magenta border",
                "simple gold bangles",
            ],
        },
        "provider_gate": {
            "openai_sora_character_motion": "blocked_for_this_route",
            "reason": (
                "Current Sora restrictions reject real people, input images with human faces, "
                "and human-likeness character uploads by default."
            ),
            "allowed_sora_validation": "Environment motion without people or faces.",
            "next_character_route": (
                "Evaluate Luma Dream Machine image-to-video with approved fictional character "
                "stills; its documented policy does not prohibit gentle fictional child-story "
                "animation, subject to moderation and private human review."
            ),
            "not_selected_runway_characters": (
                "Runway's published Additional Character & Game Worlds Policies prohibit "
                "characters intended to engage users under 18."
            ),
            "candidate_source": "https://docs.lumalabs.ai/docs/api",
            "candidate_policy_source": "https://luma.ai/content-policy",
            "runway_policy_source": "https://help.runwayml.com/hc/en-us/articles/17944787368595-Runway-s-Usage-Policy",
        },
        "planned_character_test_clips": [
            {
                "id": "kanha_sees_butter_pot",
                "length_seconds": "5",
                "required_motion": [
                    "Kanha looks from camera area toward the hanging pot.",
                    "Kanha blinks once and forms a playful smile.",
                    "Peacock feather, tree leaves and garlands move gently.",
                ],
            },
            {
                "id": "yashoda_hugs_kanha",
                "length_seconds": "5",
                "required_motion": [
                    "Yashoda bends gently and embraces Kanha.",
                    "Kanha smiles and relaxes into the hug.",
                    "Sari edge, leaves and sun rays move naturally.",
                ],
            },
        ],
        "human_review_checklist": [
            "Character face and costume remain recognizably the approved identity throughout the clip.",
            "Hands, eyes, clothing and accessories do not visibly deform.",
            "Motion is smooth and matches the described action.",
            "Scene is gentle and suitable for young children.",
            "There is no resemblance to an identifiable real child or adult.",
            "No copyrighted visual property, music, logo or watermark appears.",
        ],
        "approval_status": "awaiting_character_stills_and_supported_video_provider",
    }


def write_character_validation_pack(output_dir: Path) -> list[Path]:
    image_plan_path = write_image_plan(bal_krishna_character_design_plan(), output_dir)
    path = output_dir / WORKFLOW_ID / "character_motion_validation_protocol.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(character_motion_validation_protocol(), indent=2) + "\n",
        encoding="utf-8",
    )
    return [image_plan_path, path]


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
    return [manifest_path, voice_policy_path, image_plan_path, *write_character_validation_pack(output_dir)]


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


def generate_luma_character_identities(
    plan: ImagePlan,
    settings: Settings,
    output_dir: Path,
    session: requests.Session | None = None,
) -> list[dict[str, str]]:
    if plan.provider_mode != "fictional_character_design_stills_only":
        raise ValueError("Luma identity generation requires the fictional character identity plan.")
    if not settings.luma_api_key:
        raise ValueError("LUMAAI_API_KEY is required to generate fictional character identity stills.")
    client = session or requests.Session()
    endpoint = "https://api.lumalabs.ai/dream-machine/v1/generations/image"
    generation_endpoint = "https://api.lumalabs.ai/dream-machine/v1/generations"
    headers = {
        "Authorization": f"Bearer {settings.luma_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    project_dir = output_dir / plan.project_id
    results: list[dict[str, str]] = []
    for shot in plan.shots:
        response = client.post(
            endpoint,
            headers=headers,
            json={"prompt": shot.prompt, "model": settings.luma_image_model, "aspect_ratio": "9:16"},
            timeout=60,
        )
        response.raise_for_status()
        generation_id = response.json()["id"]
        while True:
            status = client.get(
                f"{generation_endpoint}/{generation_id}",
                headers=headers,
                timeout=60,
            )
            status.raise_for_status()
            generation = status.json()
            state = generation.get("state")
            if state == "completed":
                break
            if state == "failed":
                raise RuntimeError(
                    f"Luma identity generation failed for {shot.id}: "
                    f"{generation.get('failure_reason', 'unknown error')}"
                )
            print(f"Waiting for Luma identity still {shot.id}: {state}")
            time.sleep(3)
        image_url = generation.get("assets", {}).get("image")
        if not image_url:
            raise RuntimeError(f"Luma identity generation completed without an image URL for {shot.id}.")
        asset = client.get(image_url, timeout=120)
        asset.raise_for_status()
        path = project_dir / f"{shot.output_basename}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(asset.content)
        results.append(
            {
                "status": "awaiting_creator_approval",
                "identity_id": shot.id,
                "generation_id": generation_id,
                "file": str(path),
                "source_url": image_url,
            }
        )
    receipt = project_dir / "identity_generation_receipt.json"
    receipt.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results
