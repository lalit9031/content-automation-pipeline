from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from content_pipeline.bots.linkedin import authorize_linkedin, publish_linkedin_image
from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.pipeline import run_linkedin_mvp


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily content automation pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Generate the daily content package.")
    run_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    auth_parser = subparsers.add_parser("linkedin-auth", help="Authorize your LinkedIn profile.")
    post_parser = subparsers.add_parser("linkedin-post", help="Preview or publish an image post.")
    post_parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    post_parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually publish to LinkedIn; without this flag only a preview is printed.",
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
    package = ContentPackage.from_dict(
        json.loads((daily / "prompt.json").read_text(encoding="utf-8"))
    )
    image_path = daily / "images" / "linkedin_infographic.png"
    if not args.publish:
        print(f"Preview only: {image_path}")
        print(" ".join([package.linkedin_caption, *package.hashtags]))
        print("Run again with --publish only after reviewing this post.")
        return 0
    post_id = publish_linkedin_image(package, image_path, settings)
    print(f"LinkedIn post published: {post_id}")
    return 0
