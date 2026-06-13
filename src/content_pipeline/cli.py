from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from content_pipeline.bots.linkedin import (
    assert_publish_allowed,
    authorize_linkedin,
    publish_linkedin_image,
    published_post_receipt,
    record_published_post,
)
from content_pipeline.bots.science_story_agent import (
    generate_science_story_script,
    list_available_topics,
    save_script_to_disk,
)
from content_pipeline.bots.science_video_agent import (
    create_science_video,
    create_science_video_workspace,
    generate_scene_images,
    generate_narration_audio,
    assemble_scene_clips,
    assemble_final_video,
)
from content_pipeline.bots.audio import (
    audio_status,
    generate_hindi_voice_samples,
    render_voice_status_html,
    render_audio_status_html,
    voice_status,
)
from content_pipeline.bots.blocker_agent import (
    absorb_blocker_solution,
    blocker_status,
    blocker_status_html,
    log_exception,
    record_blocker,
    resolve_blocker,
    suggest_blocker_fixes,
)
from content_pipeline.bots.image import (
    VARIANTS,
    gemini_image_package_plan,
    gemini_image_status,
    image_provider,
)
from content_pipeline.bots.krishna_agents import (
    ImagePlan,
    assert_character_design_approved,
    bal_krishna_character_design_plan,
    bal_krishna_image_plan,
    generate_luma_character_identities,
    generate_planned_images,
    initialize_agent_workspace,
    record_character_design_approval,
    write_character_validation_pack,
    write_image_plan,
    write_voice_selection,
)
from content_pipeline.bots.motion import (
    MotionPlan,
    assemble_motion_preview,
    bal_krishna_environment_validation_plan,
    bal_krishna_luma_kanha_validation_plan,
    bal_krishna_local_kanha_validation_plan,
    bal_krishna_validation_plan,
    generate_motion_clips,
    write_motion_plan,
)
from content_pipeline.bots.policy import PublicationDeclarations, review_publication
from content_pipeline.bots.pm_video_agents import create_daily_pm_video_batch
from content_pipeline.bots.prompt import build_image_style_pack, generate_long_form_video_script
from content_pipeline.bots.pm_slide_router import build_slide_plan
from content_pipeline.bots.pm_template_agent import write_pm_template_agent_examples
from content_pipeline.bots.pm_video_templates import (
    list_pm_video_templates,
    write_template_examples,
    write_template_gallery,
)
from content_pipeline.bots.video_engine import (
    VideoCompilation,
    assemble_compilation,
    assemble_episode,
    assert_shorts_publish_allowed,
    create_clip_plan,
    create_compilation_workspace,
    create_episode_workspace,
    generate_auto_2_5d_clips,
    record_shorts_publish,
    shorts_publish_metadata,
)
from content_pipeline.bots.instagram import (
    authorize_instagram,
    instagram_publish_reel,
    record_instagram_publish,
)
from content_pipeline.bots.gemini_video import (
    gemini_config_status,
    generate_missing_gemini_clips,
    write_gemini_dry_run,
    write_gemini_budget_report,
)
from content_pipeline.bots.prompt import generate_long_form_video_script
from content_pipeline.bots.prompt_pack import create_prompt_pack
from content_pipeline.bots.krishna_studio import (
    assemble_manual_episode,
    butter_heist_short_episode,
    create_daily_video_workspace,
)
from content_pipeline.bots.story_studio import (
    assemble_story_episode,
    create_story_episode,
    create_story_workspace,
    serve_story_studio,
)
from content_pipeline.bots.video import render_landscape_preview, render_long_form_preview
from content_pipeline.bots.telegram import (
    compose_video_created_message,
    compose_youtube_upload_message,
    send_telegram_document,
    send_telegram_message,
)
from content_pipeline.bots.youtube import (
    authorize_youtube,
    review_youtube_upload_readiness,
    upload_youtube_video,
)
from content_pipeline.bots.youtube_audit import (
    audit_youtube_channels,
    render_youtube_audit_markdown,
    run_weekly_youtube_review,
    write_youtube_audit_report,
)
from content_pipeline.bots.project_brain import (
    build_project_brain_report,
    render_project_brain_markdown,
    run_project_brain_daemon,
)
from content_pipeline.bots.youtube_sync import sync_public_youtube_uploads
from content_pipeline.config import Settings
from content_pipeline.content_history import record_history_entry
from content_pipeline.models import ContentPackage, ScienceStoryScript, VideoEpisode
from content_pipeline.pipeline import run_linkedin_mvp
from content_pipeline.storage import LocalDailyStorage


def _send_telegram_if_configured(message: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    send_telegram_message(bot_token, chat_id, message)


def _send_telegram_document_if_configured(document_path: Path, caption: str = "") -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    send_telegram_document(bot_token, chat_id, document_path, caption=caption)


def _write_pm_image_provider_comparison(settings: Settings, plan: object, day: str) -> dict[str, object]:
    variant = next(variant for variant in VARIANTS if variant.aspect_ratio == "16:9")
    slide = plan.slides[0]
    root = settings.output_dir / "pm_image_provider_compare" / day
    root.mkdir(parents=True, exist_ok=True)
    prompt_path = root / "prompt.md"
    prompt_path.write_text(slide.image_prompt, encoding="utf-8")

    provider_configs = [
        ("local", "mock", "No API local SVG renderer"),
        ("gemini", "gemini", f"Gemini image model: {settings.gemini_image_model}"),
        ("openai", "openai", f"OpenAI image model: {settings.openai_image_model}"),
    ]
    results: list[dict[str, str]] = []
    for label, provider_name, description in provider_configs:
        output = root / f"{label}_cover"
        try:
            if provider_name == "gemini" and not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not configured.")
            if provider_name == "openai" and not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not configured.")
            provider = image_provider(replace(settings, image_provider=provider_name))
            image_bytes = provider.create(slide.image_prompt, variant)
            image_path = output.with_suffix(provider.extension)
            image_path.write_bytes(image_bytes)
            results.append(
                {
                    "provider": label,
                    "status": "created",
                    "description": description,
                    "path": str(image_path),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "provider": label,
                    "status": "failed",
                    "description": description,
                    "error": str(exc),
                }
            )

    html_path = root / "comparison.html"
    cards = "\n".join(_comparison_card(result, root) for result in results)
    html_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PM Image Provider Comparison</title>
  <style>
    body {{ margin: 0; background: #060914; color: #f8fafc; font-family: Avenir Next, Helvetica, Arial, sans-serif; }}
    main {{ padding: 28px; max-width: 1420px; margin: auto; }}
    h1 {{ font-size: 34px; margin: 0 0 10px; }}
    .prompt {{ white-space: pre-wrap; background: #111827; border: 1px solid #334155; border-radius: 18px; padding: 18px; color: #cbd5e1; max-height: 300px; overflow: auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 22px; margin-top: 24px; }}
    .card {{ background: #0f172a; border: 1px solid #334155; border-radius: 20px; padding: 16px; box-shadow: 0 18px 60px rgba(0,0,0,.35); }}
    .card img {{ width: 100%; border-radius: 14px; display: block; background: #020617; }}
    .status {{ color: #93c5fd; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; font-size: 12px; }}
    .error {{ color: #fecaca; }}
    a {{ color: #7dd3fc; }}
  </style>
</head>
<body>
<main>
  <h1>PM Image Provider Comparison</h1>
  <p>Same cinematic prompt, three routes: local fallback, Gemini, and ChatGPT/OpenAI.</p>
  <section class="grid">{cards}</section>
  <h2>Prompt</h2>
  <div class="prompt">{slide.image_prompt}</div>
</main>
</body>
</html>
""",
        encoding="utf-8",
    )
    manifest = {
        "topic": plan.topic,
        "date": day,
        "prompt": str(prompt_path),
        "html": str(html_path),
        "results": results,
    }
    (root / "comparison_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def _comparison_card(result: dict[str, str], root: Path) -> str:
    if result.get("status") == "created" and result.get("path"):
        image_path = Path(result["path"])
        rel = image_path.relative_to(root)
        media = f'<a href="{rel}"><img src="{rel}" alt="{result["provider"]} output" /></a>'
    else:
        media = f'<p class="error">{result.get("error", "No output created.")}</p>'
    return f"""<article class="card">
  <p class="status">{result["provider"]} · {result["status"]}</p>
  <h2>{result["description"]}</h2>
  {media}
</article>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily content automation pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Generate the daily content package.")
    run_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    video_parser = subparsers.add_parser("video-preview", help="Render a landscape video preview.")
    video_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    long_video_parser = subparsers.add_parser(
        "long-video-preview", help="Generate and render a 3-5 minute landscape video preview."
    )
    long_video_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    long_video_parser.add_argument(
        "--minutes", type=int, choices=(3, 4, 5), default=4, help="Target video length."
    )
    auth_parser = subparsers.add_parser("linkedin-auth", help="Authorize your LinkedIn profile.")
    post_parser = subparsers.add_parser("linkedin-post", help="Preview or publish an image post.")
    post_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    post_parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually publish to LinkedIn; without this flag only a preview is printed.",
    )
    post_parser.add_argument(
        "--force-republish",
        action="store_true",
        help="Publish even when a recorded LinkedIn post already exists for this date.",
    )
    record_parser = subparsers.add_parser(
        "linkedin-record",
        help="Record an already published LinkedIn post ID for duplicate protection.",
    )
    record_parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD.")
    record_parser.add_argument("--post-id", required=True, help="Published LinkedIn URN.")
    voice_parser = subparsers.add_parser(
        "krishna-voice-samples", help="Generate three Hindi narrator pronunciation samples."
    )
    voice_parser.add_argument(
        "--destination",
        type=Path,
        default=Path("output/bal_krishna_motion_validation/audio_samples"),
    )
    voice_parser.add_argument(
        "--engine",
        choices=("edge",),
        default="edge",
        help="Use the free Edge TTS Indian voice samples.",
    )
    voice_select_parser = subparsers.add_parser(
        "krishna-voice-select", help="Record the creator-approved Hindi narration voice."
    )
    voice_select_parser.add_argument(
        "--sample",
        required=True,
        choices=(
            "sample_01_prabhat_neural.mp3",
            "sample_02_neerja_neural.mp3",
            "sample_03_swara_neural.mp3",
        ),
    )
    voice_select_parser.add_argument("--destination", type=Path, default=Path("output"))
    agent_init_parser = subparsers.add_parser(
        "krishna-agents-init", help="Create separate-agent workflow manifests and safe source rules."
    )
    agent_init_parser.add_argument("--destination", type=Path, default=Path("output"))
    image_plan_parser = subparsers.add_parser(
        "krishna-image-plan", help="Write the Image Agent validation shot plan."
    )
    image_plan_parser.add_argument("--destination", type=Path, default=Path("output"))
    image_plan_parser.add_argument(
        "--mode",
        choices=("environment", "characters"),
        default="environment",
        help="Generate environment still prompts or fictional character identity still prompts.",
    )
    image_generate_parser = subparsers.add_parser(
        "krishna-image-generate", help="Generate Image Agent assets from an approved plan."
    )
    image_generate_parser.add_argument("--plan", type=Path, required=True)
    character_parser = subparsers.add_parser(
        "krishna-character-validation-init",
        help="Write the fictional character identity plan and motion review protocol.",
    )
    character_parser.add_argument("--destination", type=Path, default=Path("output"))
    approval_parser = subparsers.add_parser(
        "krishna-character-approve",
        help="Record creator approval of the fictional Kanha and Yashoda concept previews.",
    )
    approval_parser.add_argument("--kanha-image", type=Path, required=True)
    approval_parser.add_argument("--yashoda-image", type=Path, required=True)
    approval_parser.add_argument("--destination", type=Path, default=Path("output"))
    luma_identities_parser = subparsers.add_parser(
        "krishna-luma-identity-generate",
        help="Generate fictional Kanha and Yashoda identity stills for creator review.",
    )
    luma_identities_parser.add_argument(
        "--plan",
        type=Path,
        default=Path("output/bal_krishna_character_identity_validation/image_plan.json"),
    )
    luma_motion_parser = subparsers.add_parser(
        "krishna-luma-kanha-motion-plan",
        help="Write a private Kanha image-to-video motion test after identity approval.",
    )
    luma_motion_parser.add_argument("--approved-image-url", required=True)
    luma_motion_parser.add_argument(
        "--confirm-identity-approved",
        action="store_true",
        help="Confirm the supplied URL is the reviewed fictional KANHA_V1 still.",
    )
    luma_motion_parser.add_argument("--destination", type=Path, default=Path("output"))
    local_motion_parser = subparsers.add_parser(
        "krishna-local-kanha-motion-plan",
        help="Write a no-subscription local 2.5D Kanha motion test from the approved design.",
    )
    local_motion_parser.add_argument(
        "--approved-image",
        type=Path,
        default=Path("output/bal_krishna_character_identity_validation/images/kanha_v1_concept_preview.png"),
    )
    local_motion_parser.add_argument(
        "--approval-receipt",
        type=Path,
        default=Path("output/kanha_ki_nanhi_leela/character_design_approval.json"),
    )
    local_motion_parser.add_argument("--destination", type=Path, default=Path("output"))
    motion_plan_parser = subparsers.add_parser(
        "krishna-motion-plan", help="Write the two-clip Sora motion validation plan."
    )
    motion_plan_parser.add_argument(
        "--destination", type=Path, default=Path("output")
    )
    motion_plan_parser.add_argument(
        "--mode",
        choices=("environment", "characters"),
        default="environment",
        help="Render-safe environment validation is default; characters documents the desired shots.",
    )
    motion_generate_parser = subparsers.add_parser(
        "krishna-motion-generate", help="Generate the planned real-motion validation clips."
    )
    motion_generate_parser.add_argument("--plan", type=Path, required=True)
    motion_assemble_parser = subparsers.add_parser(
        "krishna-motion-assemble", help="Assemble generated motion clips into one preview."
    )
    motion_assemble_parser.add_argument("--plan", type=Path, required=True)
    manual_ui_parser = subparsers.add_parser(
        "krishna-daily-video-ui",
        help="Create a daily manual OpenArt/Meta AI episode dashboard and clip inbox.",
    )
    manual_ui_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    manual_ui_parser.add_argument(
        "--aspect",
        choices=("shorts", "landscape"),
        default="shorts",
        help="Create mobile Shorts prompts or landscape YouTube prompts.",
    )
    manual_ui_parser.add_argument("--destination", type=Path, default=Path("output"))
    manual_assemble_parser = subparsers.add_parser(
        "krishna-manual-video-assemble",
        help="Assemble downloaded OpenArt/Meta AI scene clips from an episode workspace.",
    )
    manual_assemble_parser.add_argument("--workspace", type=Path, required=True)
    # --- Science Discovery Story commands ---
    science_story_parser = subparsers.add_parser(
        "science-story-generate",
        help="Generate a 30-minute science discovery story script from a topic.",
    )
    science_story_parser.add_argument("--topic", default="", help="Science topic. Leave empty for auto-selection.")
    science_story_parser.add_argument(
        "--minutes", type=int, default=30, help="Target video duration in minutes."
    )
    science_story_parser.add_argument(
        "--save", action="store_true", help="Save script to output directory."
    )
    subparsers.add_parser(
        "science-story-topics",
        help="List available science story template topics.",
    )
    science_video_parser = subparsers.add_parser(
        "science-video-create",
        help="Full pipeline: generate script, create workspace, images, audio, and assemble video.",
    )
    science_video_parser.add_argument(
        "--topic", default="", help="Science topic. Leave empty for auto-selection."
    )
    science_video_parser.add_argument(
        "--minutes", type=int, default=30, help="Target video duration in minutes."
    )
    science_video_parser.add_argument(
        "--tts-voice",
        default="en-IN-PrabhatNeural",
        help="Edge TTS voice name for narration.",
    )
    science_video_parser.add_argument(
        "--skip-images", action="store_true", help="Skip AI image generation (use gradient placeholders)."
    )
    science_video_parser.add_argument(
        "--skip-audio", action="store_true", help="Skip TTS audio generation (use silence)."
    )
    science_video_parser.add_argument(
        "--skip-assembly", action="store_true", help="Skip final video assembly."
    )
    science_workspace_parser = subparsers.add_parser(
        "science-video-workspace",
        help="Create a workspace from an existing script (images + audio + assembly steps separately).",
    )
    science_workspace_parser.add_argument("--topic", default="", help="Science topic.")
    science_workspace_parser.add_argument(
        "--minutes", type=int, default=30, help="Target video duration."
    )
    science_workspace_parser.add_argument(
        "--workspace", type=Path, default=None,
        help="Existing workspace path (skip script generation).",
    )
    science_workspace_parser.add_argument(
        "--generate-images", action="store_true", help="Generate scene images."
    )
    science_workspace_parser.add_argument(
        "--generate-audio", action="store_true", help="Generate narration audio."
    )
    science_workspace_parser.add_argument(
        "--assemble-clips", action="store_true", help="Assemble individual scene clips."
    )
    science_workspace_parser.add_argument(
        "--assemble-final", action="store_true", help="Assemble final video from clips."
    )

    story_parser = subparsers.add_parser(
        "story-studio-create",
        help="Create a general kid/adult story dashboard, prompts and clip inbox.",
    )
    story_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    story_parser.add_argument("--audience", choices=("kid", "adult"), default="kid")
    story_parser.add_argument("--idea", default="", help="Optional story idea. Omit for an auto-created story.")
    story_parser.add_argument(
        "--aspect",
        choices=("shorts", "landscape"),
        default="shorts",
        help="Create mobile Shorts prompts or landscape YouTube prompts.",
    )
    story_parser.add_argument("--destination", type=Path, default=Path("output"))
    story_assemble_parser = subparsers.add_parser(
        "story-studio-assemble",
        help="Assemble downloaded OpenArt/Meta AI clips from a Story Studio workspace.",
    )
    story_assemble_parser.add_argument("--workspace", type=Path, required=True)
    story_gemini_parser = subparsers.add_parser(
        "story-studio-gemini-generate",
        help="Generate missing Story Studio scene clips with Gemini/Veo, or write a dry-run request file.",
    )
    story_gemini_parser.add_argument("--workspace", type=Path, required=True)
    story_gemini_parser.add_argument("--limit", type=int, default=None, help="Maximum new clips to generate.")
    story_gemini_parser.add_argument("--dry-run", action="store_true", help="Only write gemini_video_requests.json.")
    story_budget_parser = subparsers.add_parser(
        "story-studio-budget-report",
        help="Write Gemini/Veo budget report for a Story Studio workspace.",
    )
    story_budget_parser.add_argument("--workspace", type=Path, required=True)
    story_serve_parser = subparsers.add_parser(
        "story-studio-serve",
        help="Serve a Story Studio dashboard locally with character media uploads enabled.",
    )
    story_serve_parser.add_argument("--workspace", type=Path, required=True)
    story_serve_parser.add_argument("--host", default="127.0.0.1")
    story_serve_parser.add_argument("--port", type=int, default=8765)
    subparsers.add_parser("gemini-config-check", help="Check Gemini/Veo API configuration without generating video.")
    subparsers.add_parser(
        "gemini-image-status",
        help="Show Gemini image-key cooldowns and when the next request is allowed.",
    )
    subparsers.add_parser(
        "gemini-image-plan",
        help="Estimate how many full image packages can be generated before failing.",
    )
    voice_status_parser = subparsers.add_parser(
        "voice-status",
        help="Show the current voice provider, selected voice, and daily bundle state.",
    )
    voice_status_parser.add_argument("--day", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    voice_status_parser.add_argument("--html", action="store_true", help="Render a small HTML widget.")
    audio_status_parser = subparsers.add_parser(
        "audio-status",
        help="Summarize the daily voice bundle plus science and PM audio manifests.",
    )
    audio_status_parser.add_argument("--day", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    audio_status_parser.add_argument("--html", action="store_true", help="Render a small HTML widget.")
    image_style_pack_parser = subparsers.add_parser(
        "image-style-pack",
        help="Generate a reusable prompt pack with one topic prompt, storyboard prompts, and thumbnail prompt.",
    )
    image_style_pack_parser.add_argument("--topic", required=True, help="Primary topic to build the pack around.")
    image_style_pack_parser.add_argument("--subject", default="", help="Optional scene subject to steer visuals.")
    image_style_pack_parser.add_argument(
        "--audience",
        default="professional audiences",
        help="Target audience for the main topic prompt.",
    )
    image_style_pack_parser.add_argument(
        "--scene-count",
        type=int,
        default=35,
        help="How many storyboard prompts to generate.",
    )
    image_style_pack_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON pack instead of printing it.",
    )
    blocker_status_parser = subparsers.add_parser(
        "blocker-status",
        help="Show blocker journal summary and recent open items.",
    )
    blocker_status_parser.add_argument("--html", action="store_true", help="Render a small HTML widget.")
    blocker_log_parser = subparsers.add_parser(
        "blocker-log",
        help="Record a blocker and the fix you discovered later.",
    )
    blocker_log_parser.add_argument("--stage", default="", help="Command or stage that hit the blocker.")
    blocker_log_parser.add_argument("--issue", required=True, help="Short blocker description.")
    blocker_log_parser.add_argument("--solution", default="", help="What fixed it, if known.")
    blocker_log_parser.add_argument("--component", default="", help="Optional component name.")
    blocker_log_parser.add_argument("--severity", default="medium", help="low, medium, or high.")
    blocker_log_parser.add_argument("--tag", action="append", default=[], help="Optional tag; repeatable.")
    blocker_log_parser.add_argument("--source-title", default="", help="Where the solution came from.")
    blocker_log_parser.add_argument("--source-url", default="", help="Link to the source of the fix.")
    blocker_log_parser.add_argument("--notes", default="", help="Extra implementation notes.")
    blocker_learn_parser = subparsers.add_parser(
        "blocker-learn",
        help="Record a fix from any source as a reusable blocker lesson.",
    )
    blocker_learn_parser.add_argument("--issue", required=True, help="What problem was solved.")
    blocker_learn_parser.add_argument("--solution", required=True, help="What fixed it.")
    blocker_learn_parser.add_argument("--stage", default="", help="Optional command or stage name.")
    blocker_learn_parser.add_argument("--component", default="", help="Optional component name.")
    blocker_learn_parser.add_argument("--severity", default="low", help="low, medium, or high.")
    blocker_learn_parser.add_argument("--tag", action="append", default=[], help="Optional tag; repeatable.")
    blocker_learn_parser.add_argument("--source-title", default="", help="Where the solution came from.")
    blocker_learn_parser.add_argument("--source-url", default="", help="Link to the source of the fix.")
    blocker_learn_parser.add_argument("--notes", default="", help="Extra implementation notes.")
    blocker_suggest_parser = subparsers.add_parser(
        "blocker-suggest",
        help="Suggest previous fixes that look similar to a new blocker.",
    )
    blocker_suggest_parser.add_argument("--limit", type=int, default=5, help="Maximum suggestions to show.")
    blocker_resolve_parser = subparsers.add_parser(
        "blocker-resolve",
        help="Mark an existing blocker as resolved with a solution note.",
    )
    blocker_resolve_parser.add_argument("--id", required=True, help="Blocker id from blocker-status.")
    blocker_resolve_parser.add_argument("--solution", required=True, help="What fixed the blocker.")
    policy_parser = subparsers.add_parser(
        "youtube-policy-check", help="Create the required publication approval report."
    )
    policy_parser.add_argument("--title", required=True)
    policy_parser.add_argument("--video", type=Path, required=True)
    policy_parser.add_argument("--confirm-rights", action="store_true")
    policy_parser.add_argument("--confirm-disclosures", action="store_true")
    policy_parser.add_argument("--confirm-fictional-likenesses", action="store_true")
    policy_parser.add_argument("--confirm-made-for-kids", action="store_true")
    policy_parser.add_argument("--confirm-no-face-input", action="store_true")
    policy_parser.add_argument("--human-approved", action="store_true")
    upload_check_parser = subparsers.add_parser(
        "youtube-upload-preflight",
        help="Run the YouTube upload readiness test before publishing.",
    )
    upload_check_parser.add_argument("--video", type=Path, required=True)
    upload_check_parser.add_argument("--title", required=True)
    upload_check_parser.add_argument("--description-file", type=Path, required=True)
    upload_check_parser.add_argument("--policy-report", type=Path, required=True)
    upload_parser = subparsers.add_parser(
        "youtube-upload", help="Upload a policy-approved video to YouTube."
    )
    upload_parser.add_argument("--video", type=Path, required=True)
    upload_parser.add_argument("--title", required=True)
    upload_parser.add_argument("--description-file", type=Path, required=True)
    upload_parser.add_argument("--policy-report", type=Path, required=True)
    upload_parser.add_argument(
        "--privacy", choices=("private", "unlisted", "public"), default="private"
    )
    clip_plan_parser = subparsers.add_parser(
        "video-clip-plan",
        help="Generate a structured clip plan (VideoEpisode) from a topic.",
    )
    clip_plan_parser.add_argument("--topic", required=True)
    clip_plan_parser.add_argument("--audience", choices=("kid", "adult"), default="adult")
    clip_plan_parser.add_argument("--aspect", choices=("shorts", "landscape"), default="shorts")
    clip_plan_parser.add_argument("--date", default=date.today().isoformat())
    clip_plan_parser.add_argument("--target-duration", type=int, default=150)

    pm_daily_parser = subparsers.add_parser(
        "pm-daily-videos",
        help="Create daily PM/AI Shorts and YouTube video workspaces.",
    )
    pm_daily_parser.add_argument("--date", default=date.today().isoformat())
    pm_daily_parser.add_argument("--shorts-count", type=int, default=2)
    pm_daily_parser.add_argument("--youtube-count", type=int, default=2)
    pm_daily_parser.add_argument(
        "--template-mode",
        choices=("random", "course"),
        default="random",
        help="Use random visual templates for topic videos or a fixed course layout.",
    )
    pm_daily_parser.add_argument(
        "--no-render",
        action="store_true",
        help="Create scripts, subtitles and metadata without rendering MP4 previews.",
    )
    pm_daily_parser.add_argument("--tts-voice", default="en-IN-PrabhatNeural")
    pm_daily_parser.add_argument(
        "--voice-sample",
        type=Path,
        help="Store a creator voice sample with each PM video workspace for reference.",
    )
    pm_daily_parser.add_argument(
        "--voiceover-file",
        type=Path,
        help="Use a complete creator-recorded narration file instead of generated TTS.",
    )
    pm_daily_parser.add_argument(
        "--preview-without-audio",
        action="store_true",
        help="Render a review copy with silent narration if Edge TTS cannot be reached.",
    )
    pm_plan_parser = subparsers.add_parser(
        "pm-slide-plan",
        help="Preview the slide-agent split and template families before rendering a PM video.",
    )
    pm_plan_parser.add_argument("--topic", required=True)
    pm_plan_parser.add_argument("--date", default=date.today().isoformat())
    pm_plan_parser.add_argument("--aspect", choices=("shorts", "landscape"), default="landscape")
    pm_plan_parser.add_argument(
        "--template-mode",
        choices=("random", "course"),
        default="random",
        help="Use random visual templates for topic videos or a fixed course layout.",
    )
    pm_plan_parser.add_argument(
        "--slides",
        type=int,
        default=None,
        help="Override the default slide count for the chosen aspect.",
    )
    compare_parser = subparsers.add_parser(
        "pm-image-provider-compare",
        help="Generate the same PM cover prompt with local, Gemini, and OpenAI image providers.",
    )
    compare_parser.add_argument("--topic", required=True)
    compare_parser.add_argument("--date", default=date.today().isoformat())
    compare_parser.add_argument(
        "--template-mode",
        choices=("random", "course"),
        default="random",
        help="Template mode used for prompt planning.",
    )
    prompt_pack_parser = subparsers.add_parser(
        "pm-prompt-pack",
        help="Create a manual prompt pack for shorts and full video and optionally send it to Telegram.",
    )
    prompt_pack_parser.add_argument("--topic", required=True)
    prompt_pack_parser.add_argument("--date", default=date.today().isoformat())
    prompt_pack_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override the output directory for the prompt pack.",
    )
    prompt_pack_parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Write the docs locally only and skip Telegram delivery.",
    )
    subparsers.add_parser(
        "pm-video-templates",
        help="Write a gallery preview of the PM video template catalog.",
    )
    template_examples_parser = subparsers.add_parser(
        "pm-template-examples",
        help="Render five short template example videos and a single HTML preview page.",
    )
    template_examples_parser.add_argument(
        "--seconds",
        type=int,
        default=4,
        choices=(3, 4, 5),
        help="Length for each example preview in seconds.",
    )
    template_agent_parser = subparsers.add_parser(
        "pm-template-agent",
        help="Generate a richer five-pack of workflow, architecture, and dashboard template concepts.",
    )
    template_agent_parser.add_argument("--topic", default="Project Management AI")
    template_agent_parser.add_argument(
        "--seconds",
        type=int,
        default=4,
        choices=(3, 4, 5),
        help="Length for each concept preview in seconds.",
    )
    ep_create_parser = subparsers.add_parser(
        "video-episode-create",
        help="Create episode workspace and generate auto 2.5D clips from a topic plan.",
    )
    ep_create_parser.add_argument("--topic", required=True)
    ep_create_parser.add_argument("--audience", choices=("kid", "adult"), default="adult")
    ep_create_parser.add_argument("--aspect", choices=("shorts", "landscape"), default="shorts")
    ep_create_parser.add_argument("--date", default=date.today().isoformat())
    ep_create_parser.add_argument("--target-duration", type=int, default=150)

    ep_assemble_parser = subparsers.add_parser(
        "video-episode-assemble",
        help="Assemble an episode from its workspace (auto + manual clips) into a final MP4.",
    )
    ep_assemble_parser.add_argument("--workspace", type=Path, required=True)

    comp_parser = subparsers.add_parser(
        "video-compilation-create",
        help="Create a compilation manifest referencing multiple episode IDs.",
    )
    comp_parser.add_argument("--title", required=True)
    comp_parser.add_argument("--description", required=True)
    comp_parser.add_argument("--episode-ids", required=True, help="Comma-separated list of episode IDs.")
    comp_parser.add_argument("--compilation-id", default="", help="Optional custom ID.")
    comp_parser.add_argument("--transition-duration", type=int, default=2)

    comp_assemble_parser = subparsers.add_parser(
        "video-compilation-assemble",
        help="Stitch compiled episodes into a final long-form video.",
    )
    comp_assemble_parser.add_argument("--manifest", type=Path, required=True, help="Path to compilation.json manifest.")

    shorts_parser = subparsers.add_parser(
        "shorts-publish",
        help="Publish an assembled episode as YouTube Shorts / Instagram Reels.",
    )
    shorts_parser.add_argument("--workspace", type=Path, required=True, help="Episode workspace directory.")
    shorts_parser.add_argument(
        "--platform",
        choices=("youtube", "instagram", "all"),
        default="youtube",
        help="Target platform(s) for publishing.",
    )
    shorts_parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default="private",
        help="YouTube privacy setting (only used for youtube/platform).",
    )
    shorts_parser.add_argument(
        "--video-host-url",
        default="",
        help="Public URL where the video is hosted (required for Instagram Reels).",
    )
    shorts_parser.add_argument(
        "--policy-report",
        type=Path,
        default=None,
        help="Path to the YouTube policy report (required for YouTube Shorts).",
    )
    shorts_parser.add_argument(
        "--date",
        default="",
        help="Content date in YYYY-MM-DD format (for Instagram receipt path). "
        "Defaults to the first 10 chars of the episode ID.",
    )
    shorts_parser.add_argument(
        "--force-republish",
        action="store_true",
        help="Publish even if a receipt already exists for this episode.",
    )

    instagram_auth_parser = subparsers.add_parser(
        "instagram-auth",
        help="Authorize Instagram Reels publishing via the Facebook Graph API.",
    )

    subparsers.add_parser("youtube-auth", help="Authorize YouTube upload access and store a local token.")
    sync_parser = subparsers.add_parser(
        "youtube-public-sync",
        help="Scan YouTube uploads and auto-post LinkedIn + Telegram updates for public videos.",
    )
    sync_parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("state"),
        help="Directory for processed video state.",
    )
    audit_parser = subparsers.add_parser(
        "youtube-audit",
        help="Diagnose all configured YouTube channels and generate trend + fix guidance.",
    )
    audit_parser.add_argument(
        "--region-code",
        default="IN",
        help="Region code used when fetching public trending videos.",
    )
    audit_parser.add_argument(
        "--max-videos",
        type=int,
        default=15,
        help="How many recent uploads to inspect per channel.",
    )
    audit_parser.add_argument(
        "--related-topic-limit",
        type=int,
        default=3,
        help="How many top recent uploads to turn into related search queries.",
    )
    audit_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory for the audit files.",
    )
    audit_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Terminal output format.",
    )
    weekly_parser = subparsers.add_parser(
        "youtube-weekly-audit",
        help="Run the weekly YouTube audit, rewrite metadata suggestions, and notify Telegram.",
    )
    weekly_parser.add_argument(
        "--region-code",
        default="IN",
        help="Region code used when fetching public trending videos.",
    )
    weekly_parser.add_argument("--max-videos", type=int, default=15, help="Recent uploads to inspect per channel.")
    weekly_parser.add_argument(
        "--related-topic-limit",
        type=int,
        default=3,
        help="How many recent titles to turn into related searches.",
    )
    weekly_parser.add_argument(
        "--trending-limit",
        type=int,
        default=15,
        help="How many public trending videos to inspect.",
    )
    weekly_parser.add_argument(
        "--update-limit",
        type=int,
        default=2,
        help="How many videos per channel to rewrite/update.",
    )
    weekly_parser.add_argument(
        "--rewrite-provider",
        choices=("auto", "nvidia", "gemini", "openai", "local"),
        default="auto",
        help="Metadata rewrite provider order for the weekly audit.",
    )
    weekly_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the Gemini-recommended title/tag changes back to YouTube.",
    )
    weekly_parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Skip Telegram notifications even if credentials are configured.",
    )
    weekly_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory for the weekly report.",
    )
    weekly_parser.add_argument(
        "--telegram-bot-token",
        default="",
        help="Telegram bot token for notifications.",
    )
    weekly_parser.add_argument(
        "--telegram-chat-id",
        default="",
        help="Telegram chat ID for notifications.",
    )
    brain_parser = subparsers.add_parser(
        "project-brain",
        help="Run the project-wide quality brain and write a scored report.",
    )
    brain_parser.add_argument(
        "--refresh-web",
        action="store_true",
        help="Refresh YouTube trend signals before scoring.",
    )
    brain_parser.add_argument(
        "--trend-region",
        default="IN",
        help="Region code used when refreshing web trend signals.",
    )
    brain_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory for the brain report.",
    )
    brain_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Terminal output format.",
    )
    brain_daemon_parser = subparsers.add_parser(
        "project-brain-daemon",
        help="Continuously refresh the project brain on a schedule.",
    )
    brain_daemon_parser.add_argument(
        "--refresh-web",
        action="store_true",
        help="Refresh YouTube trend signals before each scoring pass.",
    )
    brain_daemon_parser.add_argument(
        "--trend-region",
        default="IN",
        help="Region code used when refreshing web trend signals.",
    )
    brain_daemon_parser.add_argument(
        "--interval-minutes",
        type=int,
        default=360,
        help="How often the daemon should refresh the brain report.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing .env and output/.",
    )
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    settings = Settings.from_environment(project_dir)

    # --- Science Discovery Story commands ---
    if args.command == "science-story-topics":
        topics = list_available_topics()
        print("Available science story topics:")
        for t in topics:
            print(f"  - {t}")
        print("\nOr provide any science topic of your choice via --topic.")
        return 0

    if args.command == "science-story-generate":
        topic = args.topic.strip()
        if not topic:
            topics = list_available_topics()
            print("Available topics: " + ", ".join(topics))
            print("\nProvide --topic or leave empty for auto-selection.")
            topic = ""
        script = generate_science_story_script(
            settings, topic=topic, target_minutes=args.minutes
        )
        print(f"Title: {script.title}")
        print(f"Topic: {script.topic}")
        print(f"Duration: {script.duration_seconds}s ({script.duration_minutes:.1f} minutes)")
        print(f"Scenes: {len(script.scenes)}")
        print(f"Chapters: {len(script.chapters)}")
        for i, chapter in enumerate(script.chapters):
            chapter_scenes = script.scenes_for_chapter(i)
            chapter_duration = sum(s.duration_seconds for s in chapter_scenes)
            print(f"  Chapter {i + 1}: {chapter} ({len(chapter_scenes)} scenes, {chapter_duration}s)")
        if args.save:
            paths = save_script_to_disk(script, str(settings.output_dir))
            print(f"\nScript saved:")
            for key, path in paths.items():
                print(f"  {key}: {path}")
        return 0

    if args.command == "science-video-create":
        workspace_dir = create_science_video(
            settings,
            topic=args.topic.strip() or "",
            target_minutes=args.minutes,
            tts_voice=args.tts_voice,
            skip_images=args.skip_images,
            skip_audio=args.skip_audio,
            skip_assembly=args.skip_assembly,
        )
        print(f"\nScience video workspace: {workspace_dir}")
        print(f"  Storyboard: {workspace_dir / 'ui' / 'storyboard.html'}")
        print(f"  Scene manifest: {workspace_dir / 'scene_manifest.json'}")
        final_video = workspace_dir / "video" / "final_video.mp4"
        if final_video.exists():
            print(f"  Final video: {final_video}")
        return 0

    if args.command == "science-video-workspace":
        from content_pipeline.bots.image import image_provider

        if args.workspace:
            ws_path = args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
            script = ScienceStoryScript.from_dict(
                json.loads((ws_path / "script.json").read_text(encoding="utf-8"))
            )
            workspace_dir = ws_path
        else:
            script = generate_science_story_script(
                settings, topic=args.topic.strip() or "", target_minutes=args.minutes
            )
            workspace_dir = create_science_video_workspace(settings.output_dir, script)
            print(f"Workspace created: {workspace_dir}")

        if args.generate_images:
            provider = image_provider(settings)
            print(f"Generating {len(script.scenes)} scene images...")
            generate_scene_images(
                workspace_dir,
                script,
                provider,
                request_delay_seconds=settings.image_request_delay_seconds,
            )
        if args.generate_audio:
            print(f"Generating {len(script.scenes)} narration audio files...")
            generate_narration_audio(workspace_dir, script, settings, voice=settings.indian_tts_voice)
        if args.assemble_clips:
            print("Assembling scene clips...")
            assemble_scene_clips(workspace_dir, script)
        if args.assemble_final:
            print("Assembling final video...")
            path = assemble_final_video(workspace_dir, script)
            print(f"Final video: {path}")
        return 0

    if args.command == "krishna-agents-init":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        for path in initialize_agent_workspace(destination):
            print(path)
        return 0
    if args.command == "krishna-voice-samples":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        for path in generate_hindi_voice_samples(settings, destination, engine=args.engine):
            print(path)
        return 0
    if args.command == "krishna-voice-select":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        print(f"Selected narration voice recorded: {write_voice_selection(destination, args.sample)}")
        return 0
    if args.command == "krishna-image-plan":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        plan = bal_krishna_image_plan() if args.mode == "environment" else bal_krishna_character_design_plan()
        print(f"Image validation plan generated: {write_image_plan(plan, destination)}")
        return 0
    if args.command == "krishna-image-generate":
        plan_path = args.plan if args.plan.is_absolute() else project_dir / args.plan
        plan = ImagePlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
        for path in generate_planned_images(
            plan,
            image_provider(settings),
            settings.output_dir,
            request_delay_seconds=settings.image_request_delay_seconds,
        ):
            print(path)
        return 0
    if args.command == "krishna-character-validation-init":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        for path in write_character_validation_pack(destination):
            print(path)
        return 0
    if args.command == "krishna-character-approve":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        kanha_image = args.kanha_image if args.kanha_image.is_absolute() else project_dir / args.kanha_image
        yashoda_image = (
            args.yashoda_image if args.yashoda_image.is_absolute() else project_dir / args.yashoda_image
        )
        print(
            "Character design approval recorded: "
            f"{record_character_design_approval(destination, kanha_image, yashoda_image)}"
        )
        return 0
    if args.command == "krishna-luma-identity-generate":
        plan_path = args.plan if args.plan.is_absolute() else project_dir / args.plan
        plan = ImagePlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
        generated = generate_luma_character_identities(plan, settings, settings.output_dir)
        print(json.dumps(generated, indent=2))
        return 0
    if args.command == "krishna-luma-kanha-motion-plan":
        if not args.confirm_identity_approved:
            raise ValueError(
                "Review the fictional KANHA_V1 still first, then rerun with --confirm-identity-approved."
            )
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        plan = bal_krishna_luma_kanha_validation_plan(args.approved_image_url, settings.luma_video_model)
        print(f"Motion validation plan generated: {write_motion_plan(plan, destination)}")
        return 0
    if args.command == "krishna-local-kanha-motion-plan":
        image_path = args.approved_image if args.approved_image.is_absolute() else project_dir / args.approved_image
        receipt_path = (
            args.approval_receipt
            if args.approval_receipt.is_absolute()
            else project_dir / args.approval_receipt
        )
        assert_character_design_approved(receipt_path, "KANHA_V1", image_path)
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        plan = bal_krishna_local_kanha_validation_plan(str(image_path))
        print(f"Motion validation plan generated: {write_motion_plan(plan, destination)}")
        return 0
    if args.command == "krishna-motion-plan":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        plan = (
            bal_krishna_environment_validation_plan(settings.motion_model)
            if args.mode == "environment"
            else bal_krishna_validation_plan(settings.motion_model)
        )
        path = write_motion_plan(plan, destination)
        print(f"Motion validation plan generated: {path}")
        return 0
    if args.command in {"krishna-motion-generate", "krishna-motion-assemble"}:
        plan_path = args.plan if args.plan.is_absolute() else project_dir / args.plan
        plan = MotionPlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
        if args.command == "krishna-motion-generate":
            generated = generate_motion_clips(plan, settings, settings.output_dir)
            print(json.dumps(generated, indent=2))
        else:
            print(f"Motion preview generated: {assemble_motion_preview(plan, settings.output_dir)}")
        return 0
    if args.command == "krishna-daily-video-ui":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        episode = butter_heist_short_episode(args.date, aspect=args.aspect)
        written = create_daily_video_workspace(destination, episode)
        for path in written:
            print(path)
        print(f"Open the dashboard file in your browser: {written[-1]}")
        return 0
    if args.command == "krishna-manual-video-assemble":
        workspace = args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        print(f"Manual video assembled: {assemble_manual_episode(workspace)}")
        return 0
    if args.command == "story-studio-create":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        episode = create_story_episode(
            args.audience,
            idea=args.idea or None,
            episode_date=args.date,
            aspect=args.aspect,
        )
        written = create_story_workspace(destination, episode)
        for path in written:
            print(path)
        print(f"Open the dashboard file in your browser: {written[-1]}")
        return 0
    if args.command == "story-studio-assemble":
        workspace = args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        print(f"Story video assembled: {assemble_story_episode(workspace)}")
        return 0
    if args.command == "story-studio-gemini-generate":
        workspace = args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        if args.dry_run:
            print(f"Gemini request file written: {write_gemini_dry_run(workspace)}")
            return 0
        print(json.dumps(generate_missing_gemini_clips(workspace, settings, args.limit), indent=2))
        return 0
    if args.command == "story-studio-budget-report":
        workspace = args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        print(f"Gemini budget report written: {write_gemini_budget_report(workspace, settings)}")
        return 0
    if args.command == "story-studio-serve":
        workspace = args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        serve_story_studio(workspace, host=args.host, port=args.port)
        return 0
    if args.command == "gemini-config-check":
        print(json.dumps(gemini_config_status(settings), indent=2))
        return 0
    if args.command == "gemini-image-status":
        print(json.dumps(gemini_image_status(settings), indent=2))
        return 0
    if args.command == "gemini-image-plan":
        print(json.dumps(gemini_image_package_plan(settings), indent=2))
        return 0
    if args.command == "voice-status":
        status = voice_status(settings.output_dir, settings, day=args.day)
        if args.html:
            print(render_voice_status_html(status))
        else:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0
    if args.command == "audio-status":
        status = audio_status(settings.output_dir, settings, day=args.day)
        if args.html:
            print(render_audio_status_html(status))
        else:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0
    if args.command == "image-style-pack":
        pack = build_image_style_pack(
            args.topic,
            subject=args.subject,
            audience=args.audience,
            scene_count=args.scene_count,
        )
        payload = json.dumps(pack.as_dict(), indent=2, ensure_ascii=False)
        if args.output:
            output_path = args.output if args.output.is_absolute() else project_dir / args.output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload + "\n", encoding="utf-8")
            print(output_path)
        else:
            print(payload)
        return 0
    if args.command == "blocker-status":
        if args.html:
            print(blocker_status_html(settings.output_dir))
        else:
            print(json.dumps(blocker_status(settings.output_dir), indent=2, ensure_ascii=False))
        return 0
    if args.command == "blocker-log":
        path = record_blocker(
            settings.output_dir,
            command=args.stage,
            issue=args.issue,
            solution=args.solution,
            component=args.component,
            severity=args.severity,
            tags=args.tag,
            source_title=args.source_title,
            source_url=args.source_url,
            notes=args.notes,
        )
        print(path)
        return 0
    if args.command == "blocker-learn":
        path = absorb_blocker_solution(
            settings.output_dir,
            issue=args.issue,
            solution=args.solution,
            command=args.stage,
            component=args.component,
            severity=args.severity,
            tags=args.tag,
            source_title=args.source_title,
            source_url=args.source_url,
            notes=args.notes,
        )
        print(path)
        return 0
    if args.command == "blocker-suggest":
        print(json.dumps(suggest_blocker_fixes(settings.output_dir, limit=args.limit), indent=2, ensure_ascii=False))
        return 0
    if args.command == "blocker-resolve":
        path = resolve_blocker(settings.output_dir, args.id, args.solution)
        print(path)
        return 0
    if args.command == "youtube-policy-check":
        video = args.video if args.video.is_absolute() else project_dir / args.video
        report = review_publication(
            args.title,
            str(video),
            PublicationDeclarations(
                original_or_licensed_story=args.confirm_rights,
                original_or_licensed_music=args.confirm_rights,
                ai_audio_disclosed=args.confirm_disclosures,
                ai_visuals_disclosed=args.confirm_disclosures,
                fictional_or_consented_likenesses=args.confirm_fictional_likenesses,
                no_face_reference_supplied_to_video_api=args.confirm_no_face_input,
                made_for_kids_selected=args.confirm_made_for_kids,
                no_copyrighted_characters_or_style_copy=args.confirm_rights,
                human_final_review=args.human_approved,
            ),
        )
        report_path = video.parent / "youtube_policy_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"Policy report: {report_path}")
        return 0 if report["status"] == "approved_for_upload" else 2
    if args.command == "youtube-upload-preflight":
        video = args.video if args.video.is_absolute() else project_dir / args.video
        description = args.description_file if args.description_file.is_absolute() else project_dir / args.description_file
        report_path = args.policy_report if args.policy_report.is_absolute() else project_dir / args.policy_report
        report = review_youtube_upload_readiness(
            title=args.title,
            video_path=video,
            description_text=description.read_text(encoding="utf-8"),
            policy_report=json.loads(report_path.read_text(encoding="utf-8")),
            thumbnail_path=description.parent / "thumbnail" / "thumbnail.svg",
        )
        preflight_path = video.parent / "youtube_upload_preflight.json"
        preflight_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"Preflight report: {preflight_path}")
        return 0 if report["status"] == "approved_for_upload" else 2
    if args.command == "youtube-upload":
        video = args.video if args.video.is_absolute() else project_dir / args.video
        description = args.description_file if args.description_file.is_absolute() else project_dir / args.description_file
        report_path = args.policy_report if args.policy_report.is_absolute() else project_dir / args.policy_report
        policy_report = json.loads(report_path.read_text(encoding="utf-8"))
        preflight = review_youtube_upload_readiness(
            title=args.title,
            video_path=video,
            description_text=description.read_text(encoding="utf-8"),
            policy_report=policy_report,
            thumbnail_path=description.parent / "thumbnail" / "thumbnail.svg",
        )
        preflight_path = video.parent / "youtube_upload_preflight.json"
        preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
        if preflight["status"] != "approved_for_upload" or preflight["blockers"]:
            raise RuntimeError(
                "YouTube upload blocked by preflight checks: "
                + ", ".join(preflight.get("blockers", []))
            )
        video_id = upload_youtube_video(
            video,
            args.title,
            description.read_text(encoding="utf-8"),
            policy_report,
            settings,
            args.privacy,
        )
        _send_telegram_if_configured(
            compose_youtube_upload_message(
                title=args.title,
                youtube_url=f"https://youtu.be/{video_id}",
                privacy_status=args.privacy,
                thumbnail_path=str(description.parent / "thumbnail" / "thumbnail.svg"),
            )
        )
        record_history_entry(
            settings.output_dir,
            date=date.today().isoformat(),
            kind="youtube_upload",
            topic=args.title,
            title=args.title,
            platform="youtube",
            reference=video_id,
            url=f"https://youtu.be/{video_id}",
            source="youtube-upload",
        )
        print(f"YouTube video uploaded as {args.privacy}: {video_id}")
        return 0
    if args.command == "video-clip-plan":
        episode = create_clip_plan(
            topic=args.topic,
            audience=args.audience,
            aspect=args.aspect,
            episode_date=args.date,
            target_duration_seconds=args.target_duration,
        )
        print(json.dumps(episode.as_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "pm-video-templates":
        gallery_path = write_template_gallery(settings.output_dir, list_pm_video_templates())
        print(gallery_path)
        for template in list_pm_video_templates()[:8]:
            print(f"{template.template_id}: {template.style_line}")
        print(f"Template count: {len(list_pm_video_templates())}")
        return 0
    if args.command == "pm-template-examples":
        examples_path = write_template_examples(settings.output_dir, list_pm_video_templates(), args.seconds)
        print(examples_path)
        return 0
    if args.command == "pm-template-agent":
        agent_path = write_pm_template_agent_examples(settings.output_dir, topic=args.topic, seconds=args.seconds)
        print(agent_path)
        return 0

    if args.command == "pm-slide-plan":
        default_slides = 10 if args.aspect == "shorts" else 35
        slide_count = args.slides or default_slides
        max_dimension = 1920 if args.aspect == "shorts" else 2048
        plan = build_slide_plan(
            topic=args.topic,
            day=args.date,
            aspect=args.aspect,
            total_slides=slide_count,
            template_mode=args.template_mode,
            max_dimension=max_dimension,
            max_bytes=settings.image_max_bytes,
            openai_key_count=max(1, len(settings.openai_api_keys)),
            gemini_key_count=max(1, len(settings.gemini_api_keys)),
        )
        print(json.dumps(plan.as_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "pm-image-provider-compare":
        plan = build_slide_plan(
            topic=args.topic,
            day=args.date,
            aspect="landscape",
            total_slides=35,
            template_mode=args.template_mode,
            max_dimension=settings.image_max_dimension,
            max_bytes=settings.image_max_bytes,
            openai_key_count=max(1, len(settings.openai_api_keys)),
            gemini_key_count=max(1, len(settings.gemini_api_keys)),
        )
        comparison = _write_pm_image_provider_comparison(settings, plan, args.date)
        print(json.dumps(comparison, indent=2, ensure_ascii=False))
        return 0

    if args.command == "pm-prompt-pack":
        output_dir = args.output_dir or settings.output_dir
        paths = create_prompt_pack(args.topic, day=args.date, output_dir=output_dir)
        for path in paths:
            print(path)
        if not args.no_telegram:
            caption = (
                "Prompt pack ready.\n"
                f"Topic: {args.topic}\n"
                f"Date: {args.date}\n"
                "Use the attached docx files to create the manual images for shorts and full video."
            )
            for path in paths:
                if path.suffix == ".docx":
                    _send_telegram_document_if_configured(path, caption=caption)
                    caption = "Prompt pack document attached."
        return 0

    if args.command == "pm-daily-videos":
        scene_image_provider = None
        if settings.image_provider != "mock":
            try:
                scene_image_provider = image_provider(settings)
            except Exception as exc:
                print(f"WARNING: scene image provider unavailable; using local templates only: {exc}")
        paths = create_daily_pm_video_batch(
            settings.output_dir,
            args.date,
            shorts_count=args.shorts_count,
            youtube_count=args.youtube_count,
            render_videos=not args.no_render,
            template_mode=args.template_mode,
            openai_api_key="",
            tts_voice=args.tts_voice,
            voice_sample_path=args.voice_sample,
            voiceover_file=args.voiceover_file,
            youtube_channel_url=settings.youtube_channel_url,
            openai_key_count=max(1, len(settings.openai_api_keys)),
            gemini_key_count=max(1, len(settings.gemini_api_keys)),
            preview_without_audio=args.preview_without_audio,
            scene_image_provider=scene_image_provider,
            request_delay_seconds=settings.image_request_delay_seconds,
        )
        for path in paths:
            print(path)
        manifest_path = settings.output_dir / "pm_video_agents" / args.date / "daily_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for episode in manifest.get("episodes", []):
            _send_telegram_if_configured(
                compose_video_created_message(
                    date=args.date,
                    title=str(episode.get("title", "")),
                    episode_folder=str(episode.get("workspace", "")),
                    manifest_path=str(manifest_path),
                    thumbnail_path=str(episode.get("thumbnail", "")),
                )
            )
        print(
            "Daily PM video batch ready: "
            f"{manifest_path}"
        )
        return 0

    if args.command == "video-episode-create":
        episode = create_clip_plan(
            topic=args.topic,
            audience=args.audience,
            aspect=args.aspect,
            episode_date=args.date,
            target_duration_seconds=args.target_duration,
        )
        written = create_episode_workspace(settings.output_dir, episode)
        for path in written:
            print(path)
        provider = image_provider(settings)
        auto_clips = generate_auto_2_5d_clips(episode, provider, settings.output_dir)
        for path in auto_clips:
            print(path)
        print(f"Episode workspace ready at: {settings.output_dir / 'video_episodes' / episode.episode_id}")
        return 0

    if args.command == "video-episode-assemble":
        workspace = (
            args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        )
        print(f"Episode assembled: {assemble_episode(workspace)}")
        return 0

    if args.command == "video-compilation-create":
        episode_ids = [eid.strip() for eid in args.episode_ids.split(",") if eid.strip()]
        if not episode_ids:
            raise ValueError("At least one episode ID is required.")
        compilation = VideoCompilation(
            compilation_id=args.compilation_id or f"compilation_{date.today().isoformat()}",
            title=args.title,
            description=args.description,
            episode_ids=episode_ids,
            transition_duration_seconds=args.transition_duration,
        )
        manifest_path = create_compilation_workspace(settings.output_dir, compilation)
        print(f"Compilation manifest created: {manifest_path}")
        return 0

    if args.command == "video-compilation-assemble":
        manifest_path = (
            args.manifest if args.manifest.is_absolute() else project_dir / args.manifest
        )
        compilation = VideoCompilation.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        # Find episode directories under output_dir / video_episodes / <episode_id>
        episode_dirs = [
            settings.output_dir / "video_episodes" / eid
            for eid in compilation.episode_ids
        ]
        for ep_dir in episode_dirs:
            if not ep_dir.is_dir():
                raise FileNotFoundError(
                    f"Episode directory not found: {ep_dir}. "
                    "Create the episode first with video-episode-create."
                )
        output_path = assemble_compilation(
            settings.output_dir, compilation, episode_dirs
        )
        print(f"Compilation assembled: {output_path}")
        return 0

    if args.command == "shorts-publish":
        workspace = (
            args.workspace if args.workspace.is_absolute() else project_dir / args.workspace
        )
        episode = VideoEpisode.from_dict(
            json.loads((workspace / "episode.json").read_text(encoding="utf-8"))
        )
        if episode.aspect != "shorts":
            raise ValueError(
                f"Episode '{episode.episode_id}' has aspect '{episode.aspect}'. "
                "Only shorts (9:16) episodes can be published to Shorts/Reels."
            )

        video_path = workspace / "video" / "episode_review.mp4"
        if not video_path.exists():
            raise FileNotFoundError(
                f"Assembled video not found at {video_path}. "
                "Run video-episode-assemble first."
            )

        platforms = ["youtube", "instagram"] if args.platform == "all" else [args.platform]

        for platform in platforms:
            assert_shorts_publish_allowed(
                settings.output_dir,
                episode.episode_id,
                platform,
                force=args.force_republish,
            )

            meta = shorts_publish_metadata(episode, platform=platform, video_path=video_path)

            if platform == "youtube":
                if not args.policy_report:
                    raise ValueError(
                        "--policy-report is required for YouTube Shorts publishing. "
                        "Run youtube-policy-check first."
                    )
                report_path = (
                    args.policy_report
                    if args.policy_report.is_absolute()
                    else project_dir / args.policy_report
                )
                report = json.loads(report_path.read_text(encoding="utf-8"))
                video_id = upload_youtube_video(
                    video_path,
                    meta.title,
                    meta.description,
                    report,
                    settings,
                    args.privacy,
                )
                record_shorts_publish(
                    settings.output_dir,
                    episode.episode_id,
                    "youtube",
                    video_id,
                )
                _send_telegram_if_configured(
                    compose_youtube_upload_message(
                        title=meta.title,
                        youtube_url=f"https://youtu.be/{video_id}",
                        privacy_status=args.privacy,
                        thumbnail_path=str(workspace / "thumbnail" / "thumbnail.svg"),
                    )
                )
                record_history_entry(
                    settings.output_dir,
                    date=episode.episode_id[:10],
                    kind="youtube_publish",
                    topic=episode.title,
                    title=meta.title,
                    platform="youtube",
                    reference=video_id,
                    url=f"https://youtu.be/{video_id}",
                    source="shorts-publish",
                )
                print(f"YouTube Short published: {video_id}")

            elif platform == "instagram":
                if not args.video_host_url:
                    raise ValueError(
                        "--video-host-url is required for Instagram Reels publishing. "
                        "Upload the video to a public URL first."
                    )
                media_id = instagram_publish_reel(
                    video_path,
                    meta.description,
                    args.video_host_url,
                    settings,
                )
                publish_day = args.date or episode.episode_id[:10]
                record_instagram_publish(
                    settings.output_dir,
                    episode.episode_id,
                    publish_day,
                    media_id,
                )
                print(f"Instagram Reel published: {media_id}")

        return 0

    if args.command == "instagram-auth":
        result = authorize_instagram(settings, project_dir / ".env")
        print(f"Instagram authorized: user_id={result['instagram_user_id']}")
        return 0

    if args.command == "youtube-auth":
        print(f"YouTube token stored locally: {authorize_youtube(settings)}")
        return 0
    if args.command == "youtube-public-sync":
        state_dir = args.state_dir if args.state_dir.is_absolute() else project_dir / args.state_dir
        results = sync_public_youtube_uploads(settings, state_dir)
        print(json.dumps([result.as_dict() for result in results], indent=2, ensure_ascii=False))
        return 0
    if args.command == "youtube-audit":
        report = audit_youtube_channels(
            settings,
            project_dir,
            region_code=args.region_code,
            max_videos=args.max_videos,
            related_topic_limit=args.related_topic_limit,
        )
        output_dir = args.output_dir if args.output_dir else settings.output_dir / "youtube_audits"
        if not output_dir.is_absolute():
            output_dir = project_dir / output_dir
        paths = write_youtube_audit_report(report, output_dir)
        print(f"Audit report written: {paths['markdown']}")
        print(f"Audit JSON written: {paths['json']}")
        if args.format == "json":
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_youtube_audit_markdown(report))
        return 0
    if args.command == "youtube-weekly-audit":
        output_dir = args.output_dir if args.output_dir else settings.output_dir / "youtube_audits"
        if not output_dir.is_absolute():
            output_dir = project_dir / output_dir
        report = run_weekly_youtube_review(
            settings,
            project_dir,
            region_code=args.region_code,
            max_videos=args.max_videos,
            related_topic_limit=args.related_topic_limit,
            trending_limit=args.trending_limit,
            update_limit=args.update_limit,
            rewrite_provider=args.rewrite_provider,
            apply_updates=args.apply,
            notify_telegram=not args.no_telegram,
            telegram_bot_token=args.telegram_bot_token,
            telegram_chat_id=args.telegram_chat_id,
            output_dir=output_dir,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    if args.command == "project-brain":
        output_dir = args.output_dir if args.output_dir else settings.output_dir
        if not output_dir.is_absolute():
            output_dir = project_dir / output_dir
        report = build_project_brain_report(
            settings,
            refresh_web=args.refresh_web,
            trend_region=args.trend_region,
            output_dir=output_dir,
        )
        print(f"Brain JSON written: {report.report_path}")
        print(f"Brain markdown written: {report.markdown_path}")
        if args.format == "json":
            print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        else:
            print(render_project_brain_markdown(report))
        return 0
    if args.command == "project-brain-daemon":
        run_project_brain_daemon(
            settings,
            refresh_web=args.refresh_web,
            trend_region=args.trend_region,
            interval_minutes=args.interval_minutes,
        )
        return 0
    if args.command == "linkedin-auth":
        member_urn = authorize_linkedin(settings, project_dir / ".env")
        print(f"LinkedIn authorized for {member_urn}. Token stored in local .env.")
        return 0
    date.fromisoformat(args.date)
    if args.command == "run":
        result = run_linkedin_mvp(args.date, settings)
        print(json.dumps(result, indent=2))
        return 0
    daily = settings.output_dir / "daily" / args.date
    storage = LocalDailyStorage(settings.output_dir)
    package = ContentPackage.from_dict(
        json.loads((daily / "prompt.json").read_text(encoding="utf-8"))
    )
    if args.command == "video-preview":
        video_file = render_landscape_preview(package, storage)
        print(f"Landscape video preview generated: {settings.output_dir / 'daily' / args.date / video_file}")
        print(
            "Subtitle track generated: "
            f"{settings.output_dir / 'daily' / args.date / 'video/landscape_preview_16x9.srt'}"
        )
        return 0
    if args.command == "long-video-preview":
        script = generate_long_form_video_script(package, settings, args.minutes)
        storage.write_json(args.date, "video/longform_script.json", script.as_dict())
        video_file = render_long_form_preview(script, args.date, storage)
        print(
            f"Long-form video preview generated: "
            f"{settings.output_dir / 'daily' / args.date / video_file}"
        )
        print(
            "Subtitle track generated: "
            f"{settings.output_dir / 'daily' / args.date / 'video/longform_preview_16x9.srt'}"
        )
        print(f"Planned duration: {script.duration_seconds} seconds")
        return 0
    image_path = daily / "images" / "linkedin_infographic.png"
    if args.command == "linkedin-record":
        receipt = record_published_post(
            package,
            "images/linkedin_infographic.png",
            args.post_id,
            storage,
        )
        print(json.dumps(receipt, indent=2))
        return 0
    prior_post = published_post_receipt(storage, args.date)
    if not args.publish:
        if prior_post:
            print(f"Already published: {prior_post['post_id']}")
        print(f"Preview only: {image_path}")
        print(" ".join([package.linkedin_caption, *package.hashtags]))
        print("Run again with --publish only after reviewing this post.")
        return 0
    assert_publish_allowed(prior_post, args.force_republish)
    post_id = publish_linkedin_image(package, image_path, settings)
    record_published_post(package, "images/linkedin_infographic.png", post_id, storage)
    print(f"LinkedIn post published: {post_id}")
    return 0
