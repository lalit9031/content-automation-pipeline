from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass
from html import escape
from io import BytesIO
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
        title = escape(
            _prompt_field(prompt, "Renderer-only headline")
            or _prompt_field(prompt, "Main headline text")
            or _prompt_topic(prompt)
            or "THE PM AI QUESTION"
        )
        hook = escape(
            _prompt_field(prompt, "Renderer-only hook")
            or _prompt_field(prompt, "Opening hook text")
            or "Practical PM AI playbook"
        )
        concepts = _prompt_concepts(prompt)
        concept_rows = "\n".join(
            f"""    <g transform="translate(0 {index * 82})">
      <rect x="0" y="0" width="310" height="62" rx="22" fill="#111827" fill-opacity="0.76" stroke="{color}" stroke-width="2"/>
      <circle cx="34" cy="31" r="11" fill="{color}"/>
      <text x="58" y="39" fill="#f8fafc" font-family="Arial, sans-serif" font-size="24" font-weight="800">{escape(label)}</text>
    </g>"""
            for index, (label, color) in enumerate(zip(concepts, ("#38bdf8", "#f59e0b", "#a3e635")))
        )
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{variant.width}" height="{variant.height}" viewBox="0 0 {variant.width} {variant.height}">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop stop-color="#030712"/>
      <stop offset="0.52" stop-color="#07152f"/>
      <stop offset="1" stop-color="#301308"/>
    </linearGradient>
    <radialGradient id="aiGlow" cx="73%" cy="42%" r="35%">
      <stop stop-color="#38bdf8" stop-opacity="0.9"/>
      <stop offset="0.36" stop-color="#0ea5e9" stop-opacity="0.34"/>
      <stop offset="1" stop-color="#020617" stop-opacity="0"/>
    </linearGradient>
    <filter id="shadow"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000000" flood-opacity="0.45"/></filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#aiGlow)"/>
  <path d="M0 610 C250 500 430 700 670 590 C900 485 1040 540 1280 435" stroke="#38bdf8" stroke-opacity="0.32" stroke-width="8" fill="none"/>
  <path d="M0 650 C250 555 450 730 700 625 C930 528 1100 605 1280 485" stroke="#f59e0b" stroke-opacity="0.42" stroke-width="7" fill="none"/>
  <g opacity="0.15" stroke="#94a3b8" stroke-width="1">
    {"".join(f'<line x1="{x}" y1="0" x2="{x}" y2="{variant.height}"/>' for x in range(0, variant.width + 1, 64))}
    {"".join(f'<line x1="0" y1="{y}" x2="{variant.width}" y2="{y}"/>' for y in range(0, variant.height + 1, 64))}
  </g>
  <g transform="translate(70 58)">
    <rect width="285" height="46" rx="23" fill="#f59e0b" filter="url(#shadow)"/>
    <text x="28" y="31" fill="#111827" font-family="Arial, sans-serif" font-size="24" font-weight="900">LEARN WITH LALIT</text>
    <rect x="330" width="190" height="46" rx="23" fill="#111827" stroke="#a855f7" stroke-width="2"/>
    <text x="360" y="31" fill="#ffffff" font-family="Arial, sans-serif" font-size="23" font-weight="900">AI FOR PMS</text>
  </g>
  <g transform="translate(70 170)" filter="url(#shadow)">
    <text x="0" y="0" fill="#ffffff" font-family="Arial, sans-serif" font-size="{max(46, variant.width // 14)}" font-weight="900">{title}</text>
    <text x="2" y="76" fill="#93c5fd" font-family="Arial, sans-serif" font-size="{max(34, variant.width // 22)}" font-weight="900">{hook}</text>
  </g>
  <g transform="translate(78 370)">
    <rect x="0" y="0" width="570" height="170" rx="34" fill="#0f172a" fill-opacity="0.74" stroke="#38bdf8" stroke-width="2"/>
    <text x="38" y="58" fill="#e5e7eb" font-family="Arial, sans-serif" font-size="28" font-weight="800">Local renderer baseline</text>
    <text x="38" y="100" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="23">Clean text, deterministic layout,</text>
    <text x="38" y="134" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="23">no API cost, less cinematic realism.</text>
  </g>
  <g transform="translate(780 190)" filter="url(#shadow)">
    <circle cx="210" cy="155" r="142" fill="#020617" stroke="#38bdf8" stroke-width="3"/>
    <path d="M115 155 C145 72 275 74 307 155 C280 245 148 244 115 155Z" fill="none" stroke="#38bdf8" stroke-width="8"/>
    <circle cx="210" cy="155" r="42" fill="#38bdf8" fill-opacity="0.2" stroke="#93c5fd" stroke-width="5"/>
    <path d="M210 30 L210 0 M210 310 L210 280 M65 155 L25 155 M395 155 L355 155" stroke="#93c5fd" stroke-width="5"/>
  </g>
  <g transform="translate(820 472)">
{concept_rows}
  </g>
  <text x="70" y="{variant.height - 48}" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="22" font-weight="800">PMP • SCRUM • AGILE • SAFE • JIRA • COPILOT • PMO</text>
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


class GeminiImageProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for IMAGE_PROVIDER=gemini")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.clients = [genai.Client(api_key=key) for key in (settings.gemini_api_keys or (settings.gemini_api_key,))]
        self.model = settings.gemini_image_model

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        last_error: Exception | None = None
        for client in self.clients:
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=(
                        f"Create a polished, high-contrast presentation image for a {variant.aspect_ratio} canvas. "
                        f"Use this creative brief: {prompt}"
                    ),
                )
                image_bytes = _response_image_bytes(response)
                if image_bytes is None:
                    raise RuntimeError("Gemini image generation did not return an image asset.")
                return image_bytes
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Gemini image generation failed for all configured keys: {last_error}")


class OpenAIImageProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for IMAGE_PROVIDER=openai")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.clients = [OpenAI(api_key=key) for key in (settings.openai_api_keys or (settings.openai_api_key,))]
        self.model = settings.openai_image_model

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        last_error: Exception | None = None
        for client in self.clients:
            try:
                result = client.images.generate(
                    model=self.model,
                    prompt=prompt,
                    size=_openai_size_for(variant),
                    quality="low",
                )
                image_base64 = result.data[0].b64_json
                if not image_base64:
                    raise RuntimeError("OpenAI image generation did not return an image asset.")
                return base64.b64decode(image_base64)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"OpenAI image generation failed for all configured keys: {last_error}")


def image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider == "mock":
        return MockImageProvider()
    if settings.image_provider == "imagen":
        return ImagenProvider(settings)
    if settings.image_provider == "gemini":
        return GeminiImageProvider(settings)
    if settings.image_provider in {"openai", "chatgpt", "gpt-image"}:
        return OpenAIImageProvider(settings)
    raise ValueError(f"Unsupported IMAGE_PROVIDER: {settings.image_provider}")


def generate_images(
    package: ContentPackage,
    provider: ImageProvider,
    storage: LocalDailyStorage,
    *,
    max_dimension: int = 2048,
    max_bytes: int = 5 * 1024 * 1024,
) -> list[str]:
    files: list[str] = []
    for variant in VARIANTS:
        filename = variant.filename + provider.extension
        image_bytes = provider.create(package.image_prompt, variant)
        _assert_image_limits(image_bytes, provider.extension, filename, max_dimension, max_bytes)
        storage.write_bytes(package.date, filename, image_bytes)
        files.append(filename)
    return files


def _assert_image_limits(
    image_bytes: bytes,
    extension: str,
    filename: str,
    max_dimension: int,
    max_bytes: int,
) -> None:
    if len(image_bytes) > max_bytes:
        raise ValueError(
            f"Generated image {filename} exceeds the {max_bytes} byte limit. "
            "Ask the agent to simplify the composition or reduce detail."
        )
    if extension.lower() != ".png":
        return
    width, height = _png_dimensions(image_bytes)
    if width > max_dimension or height > max_dimension:
        raise ValueError(
            f"Generated image {filename} is {width}x{height}, which exceeds the "
            f"{max_dimension}px limit. Regenerate a smaller asset."
        )


def _png_dimensions(image_bytes: bytes) -> tuple[int, int]:
    if len(image_bytes) < 24 or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG image bytes were not valid.")
    if image_bytes[12:16] != b"IHDR":
        raise ValueError("PNG image bytes are missing IHDR metadata.")
    width = struct.unpack(">I", image_bytes[16:20])[0]
    height = struct.unpack(">I", image_bytes[20:24])[0]
    return width, height


def _response_image_bytes(response: object) -> bytes | None:
    candidates = []
    parts = getattr(response, "parts", None)
    if parts:
        candidates.extend(parts)
    responses = getattr(response, "candidates", None)
    if responses:
        for candidate in responses:
            content = getattr(candidate, "content", None)
            if content is not None:
                candidate_parts = getattr(content, "parts", None)
                if candidate_parts:
                    candidates.extend(candidate_parts)
    for part in candidates:
        inline_data = getattr(part, "inline_data", None)
        if inline_data is not None:
            data = getattr(inline_data, "data", None)
            if data:
                return bytes(data)
        as_image = getattr(part, "as_image", None)
        if callable(as_image):
            image = as_image()
            if image is not None:
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue()
    return None


def _openai_size_for(variant: ImageVariant) -> str:
    if variant.aspect_ratio == "16:9":
        return "1536x1024"
    if variant.aspect_ratio == "9:16":
        return "1024x1536"
    return "1024x1024"


def _prompt_field(prompt: str, field: str) -> str:
    pattern = rf'{re.escape(field)}:\s*"?([^"\n]+)"?'
    match = re.search(pattern, prompt, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _prompt_topic(prompt: str) -> str:
    match = re.search(r"Topic:\s*([^\n]+)", prompt, flags=re.IGNORECASE)
    return match.group(1).strip().upper() if match else ""


def _prompt_concepts(prompt: str) -> list[str]:
    known = [
        "Cycle Time",
        "Escaped Defects",
        "Delivery Confidence",
        "Risk Visibility",
        "Flow Faster",
        "Review Human",
    ]
    found = [concept for concept in known if concept.lower() in prompt.lower()]
    return (found + ["Risk Visible", "Flow Faster", "Review Human"])[:3]
