from __future__ import annotations

import json
from datetime import date
from typing import Protocol

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage


class PromptProvider(Protocol):
    def generate(self, day: str) -> ContentPackage: ...


class MockPromptProvider:
    def generate(self, day: str) -> ContentPackage:
        return ContentPackage.from_dict(
            {
                "date": day,
                "topic": "How small teams can use AI workflows responsibly",
                "image_prompt": (
                    "A creator planning an AI-assisted content workflow on a clean "
                    "dashboard, warm daylight, professional photography, no text"
                ),
                "video_script": {
                    "hook": "AI workflows save time only when the guardrails are clear.",
                    "points": [
                        "Start with one repeatable task",
                        "Review claims before publishing",
                        "Measure useful engagement, not volume",
                    ],
                    "cta": "Follow for practical AI workflow ideas.",
                },
                "linkedin_caption": (
                    "A content pipeline should amplify judgment, not remove it. "
                    "Start small, review facts, then automate the repeatable parts."
                ),
                "hashtags": ["#AI", "#ContentStrategy", "#Automation"],
                "seo_title": "Build a Responsible AI Content Workflow",
                "seo_description": (
                    "A practical approach to using AI workflows for consistent "
                    "content while preserving accuracy and review."
                ),
            }
        )


class AnthropicPromptProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key or not settings.anthropic_model:
            raise ValueError("ANTHROPIC_API_KEY and ANTHROPIC_MODEL are required")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def generate(self, day: str) -> ContentPackage:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1600,
            system=(
                "You are a content strategist. Output only valid JSON. Create an "
                "accurate daily content package for LinkedIn, YouTube and Instagram. "
                "Do not invent statistics or describe a topic as trending without "
                "evidence supplied in the prompt."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Date: {day}. Produce keys: date, topic, image_prompt, "
                        "video_script with hook, points and cta, linkedin_caption, "
                        "hashtags, seo_title, seo_description. Choose a useful topic "
                        "in AI, technology, productivity, or entrepreneurship."
                    ),
                }
            ],
        )
        return ContentPackage.from_dict(json.loads(message.content[0].text))


def prompt_provider(settings: Settings) -> PromptProvider:
    if settings.prompt_provider == "mock":
        return MockPromptProvider()
    if settings.prompt_provider == "anthropic":
        return AnthropicPromptProvider(settings)
    raise ValueError(f"Unsupported PROMPT_PROVIDER: {settings.prompt_provider}")


def today_iso() -> str:
    return date.today().isoformat()
