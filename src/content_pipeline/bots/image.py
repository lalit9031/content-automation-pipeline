from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Protocol

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


@dataclass(frozen=True)
class ImageVariant:
    aspect_ratio: str
    width: int
    height: int
    filename: str


VARIANTS = [
    ImageVariant("1:1", 1080, 1080, "images/image_square"),
    ImageVariant("16:9", 1280, 720, "images/image_landscape"),
    ImageVariant("9:16", 1080, 1920, "images/image_portrait"),
]


class ImageProvider(Protocol):
    extension: str

    def create(self, prompt: str, variant: ImageVariant) -> bytes: ...


class MockImageProvider:
    extension = ".svg"

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        title = escape(prompt[:105])
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{variant.width}" height="{variant.height}" viewBox="0 0 {variant.width} {variant.height}">
  <defs>
    <linearGradient id="bg" x2="1" y2="1">
      <stop stop-color="#111827"/>
      <stop offset="1" stop-color="#2563eb"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <text x="8%" y="45%" fill="#ffffff" font-family="Arial, sans-serif" font-size="{max(30, variant.width // 25)}" font-weight="bold">IMAGE BOT PLACEHOLDER</text>
  <text x="8%" y="52%" fill="#bfdbfe" font-family="Arial, sans-serif" font-size="{max(18, variant.width // 45)}">{escape(variant.aspect_ratio)} variant</text>
  <text x="8%" y="61%" fill="#e5e7eb" font-family="Arial, sans-serif" font-size="{max(14, variant.width // 62)}">{title}</text>
</svg>
"""
        return svg.encode("utf-8")


class ImagenProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        if not settings.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID is required for IMAGE_PROVIDER=imagen")
        try:
            from google import genai
            from google.genai.types import GenerateImagesConfig
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.generate_images_config = GenerateImagesConfig
        self.client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        self.model = settings.imagen_model

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        config = self.generate_images_config(
            number_of_images=1,
            aspect_ratio=variant.aspect_ratio,
            output_mime_type="image/png",
        )
        response = self.client.models.generate_images(
            model=self.model,
            prompt=prompt,
            config=config,
        )
        return response.generated_images[0].image.image_bytes


def image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider == "mock":
        return MockImageProvider()
    if settings.image_provider == "imagen":
        return ImagenProvider(settings)
    raise ValueError(f"Unsupported IMAGE_PROVIDER: {settings.image_provider}")


def generate_images(
    package: ContentPackage,
    provider: ImageProvider,
    storage: LocalDailyStorage,
) -> list[str]:
    files: list[str] = []
    for variant in VARIANTS:
        filename = variant.filename + provider.extension
        storage.write_bytes(package.date, filename, provider.create(package.image_prompt, variant))
        files.append(filename)
    return files
