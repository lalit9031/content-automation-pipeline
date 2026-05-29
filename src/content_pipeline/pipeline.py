from __future__ import annotations

from dataclasses import asdict

from content_pipeline.bots.image import generate_images, image_provider
from content_pipeline.bots.infographic import render_linkedin_infographic
from content_pipeline.bots.linkedin import prepare_linkedin_post
from content_pipeline.bots.prompt import prompt_provider
from content_pipeline.config import Settings
from content_pipeline.content_history import ContentHistory, record_history_entry
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


def run_linkedin_mvp(day: str, settings: Settings) -> dict[str, object]:
    storage = LocalDailyStorage(settings.output_dir)
    history = ContentHistory.load(settings.output_dir)
    package = prompt_provider(settings).generate(day, avoid_topics=history.recent_topics())
    prompt_path = storage.write_json(day, "prompt.json", package.as_dict())
    image_files = generate_images(
        package,
        image_provider(settings),
        storage,
        max_dimension=settings.image_max_dimension,
        max_bytes=settings.image_max_bytes,
    )
    linkedin_image = render_linkedin_infographic(package, storage)
    receipt = prepare_linkedin_post(package, linkedin_image, settings, storage)
    history_path = record_history_entry(
        settings.output_dir,
        date=day,
        kind="linkedin_post",
        topic=package.topic,
        title=package.seo_title,
        platform="linkedin",
        reference=package.seo_title,
        url=settings.youtube_channel_url,
        source="run_linkedin_mvp",
    )
    provider_mode = (
        "mock"
        if settings.prompt_provider == "mock" and settings.image_provider == "mock"
        else "live"
    )
    artifacts: dict[str, object] = {
        "prompt": str(prompt_path),
        "images": image_files,
        "linkedin_image": linkedin_image,
        "linkedin": "publish/linkedin_payload.json",
    }

    # Optional: render a video via Canva Autofill + Export.
    video_rel = _render_video(package, settings, storage, day)
    if video_rel:
        artifacts["canva_video"] = video_rel

    result = {
        "date": day,
        "mode": provider_mode,
        "providers": {
            "prompt": settings.prompt_provider,
            "supporting_images": settings.image_provider,
            "linkedin_infographic": "template",
        },
        "topic": package.topic,
        "history": str(history_path),
        "artifacts": artifacts,
        "publishing": asdict(receipt),
        "next_stages": ["video_bot", "merge_bot", "youtube", "shorts", "instagram"],
    }
    storage.write_json(day, "run_manifest.json", result)
    return result


def _render_video(
    package: ContentPackage,
    settings: Settings,
    storage: LocalDailyStorage,
    day: str,
) -> str | None:
    """Render a video via Canva if credentials and a brand template are configured."""
    if not (
        settings.canva_brand_template_id
        and settings.canva_client_id
        and settings.canva_client_secret
        and settings.canva_refresh_token
    ):
        return None
    from content_pipeline.bots.canva import render_canva_video

    return render_canva_video(package, settings, storage)
