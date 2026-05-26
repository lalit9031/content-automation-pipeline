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
from content_pipeline.bots.video import render_landscape_preview
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
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing .env and output/.",
    )
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    settings = Settings.from_environment(project_dir)
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
