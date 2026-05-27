from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from content_pipeline.bots.linkedin import (
    assert_publish_allowed,
    authorize_linkedin,
    publish_linkedin_image,
    published_post_receipt,
    record_published_post,
)
from content_pipeline.bots.audio import generate_hindi_voice_samples
from content_pipeline.bots.image import image_provider
from content_pipeline.bots.krishna_agents import (
    ImagePlan,
    bal_krishna_image_plan,
    generate_planned_images,
    initialize_agent_workspace,
    write_image_plan,
)
from content_pipeline.bots.motion import (
    MotionPlan,
    assemble_motion_preview,
    bal_krishna_environment_validation_plan,
    bal_krishna_validation_plan,
    generate_motion_clips,
    write_motion_plan,
)
from content_pipeline.bots.policy import PublicationDeclarations, review_publication
from content_pipeline.bots.prompt import generate_long_form_video_script
from content_pipeline.bots.video import render_landscape_preview, render_long_form_preview
from content_pipeline.bots.youtube import authorize_youtube, upload_youtube_video
from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.pipeline import run_linkedin_mvp
from content_pipeline.storage import LocalDailyStorage


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
    agent_init_parser = subparsers.add_parser(
        "krishna-agents-init", help="Create separate-agent workflow manifests and safe source rules."
    )
    agent_init_parser.add_argument("--destination", type=Path, default=Path("output"))
    image_plan_parser = subparsers.add_parser(
        "krishna-image-plan", help="Write the Image Agent validation shot plan."
    )
    image_plan_parser.add_argument("--destination", type=Path, default=Path("output"))
    image_generate_parser = subparsers.add_parser(
        "krishna-image-generate", help="Generate Image Agent assets from an approved plan."
    )
    image_generate_parser.add_argument("--plan", type=Path, required=True)
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
    subparsers.add_parser("youtube-auth", help="Authorize YouTube upload access and store a local token.")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing .env and output/.",
    )
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    settings = Settings.from_environment(project_dir)
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
        for path in generate_hindi_voice_samples(settings, destination):
            print(path)
        return 0
    if args.command == "krishna-image-plan":
        destination = args.destination
        if not destination.is_absolute():
            destination = project_dir / destination
        print(f"Image validation plan generated: {write_image_plan(bal_krishna_image_plan(), destination)}")
        return 0
    if args.command == "krishna-image-generate":
        plan_path = args.plan if args.plan.is_absolute() else project_dir / args.plan
        plan = ImagePlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
        for path in generate_planned_images(plan, image_provider(settings), settings.output_dir):
            print(path)
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
    if args.command == "youtube-upload":
        video = args.video if args.video.is_absolute() else project_dir / args.video
        description = args.description_file if args.description_file.is_absolute() else project_dir / args.description_file
        report_path = args.policy_report if args.policy_report.is_absolute() else project_dir / args.policy_report
        report = json.loads(report_path.read_text(encoding="utf-8"))
        video_id = upload_youtube_video(
            video,
            args.title,
            description.read_text(encoding="utf-8"),
            report,
            settings,
            args.privacy,
        )
        print(f"YouTube video uploaded as {args.privacy}: {video_id}")
        return 0
    if args.command == "youtube-auth":
        print(f"YouTube token stored locally: {authorize_youtube(settings)}")
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
