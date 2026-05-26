from __future__ import annotations

from dataclasses import dataclass

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


@dataclass(frozen=True)
class PublishReceipt:
    platform: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "status": self.status,
            "message": self.message,
        }


def prepare_linkedin_post(
    package: ContentPackage,
    image_file: str,
    settings: Settings,
    storage: LocalDailyStorage,
) -> PublishReceipt:
    if settings.publish_linkedin:
        raise NotImplementedError(
            "Live LinkedIn publishing is intentionally gated until organization "
            "access and the image upload/post approval flow are configured."
        )
    post = {
        "caption": package.linkedin_caption,
        "hashtags": package.hashtags,
        "image_file": image_file,
    }
    storage.write_json(package.date, "publish/linkedin_payload.json", post)
    receipt = PublishReceipt(
        platform="linkedin",
        status="prepared",
        message="Payload prepared locally; public posting is disabled.",
    )
    storage.write_json(package.date, "publish/linkedin_receipt.json", receipt.as_dict())
    return receipt
