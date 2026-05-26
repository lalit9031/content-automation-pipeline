from __future__ import annotations

from dataclasses import asdict

from content_pipeline.bots.image import generate_images, image_provider
from content_pipeline.bots.linkedin import prepare_linkedin_post
from content_pipeline.bots.prompt import prompt_provider
from content_pipeline.config import Settings
from content_pipeline.storage import LocalDailyStorage


def run_linkedin_mvp(day: str, settings: Settings) -> dict[str, object]:
    storage = LocalDailyStorage(settings.output_dir)
    package = prompt_provider(settings).generate(day)
    prompt_path = storage.write_json(day, "prompt.json", package.as_dict())
    image_files = generate_images(package, image_provider(settings), storage)
    receipt = prepare_linkedin_post(package, image_files[0], settings, storage)
    result = {
        "date": day,
        "mode": settings.mode,
        "topic": package.topic,
        "artifacts": {
            "prompt": str(prompt_path),
            "images": image_files,
            "linkedin": "publish/linkedin_payload.json",
        },
        "publishing": asdict(receipt),
        "next_stages": ["video_bot", "merge_bot", "youtube", "shorts", "instagram"],
    }
    storage.write_json(day, "run_manifest.json", result)
    return result
