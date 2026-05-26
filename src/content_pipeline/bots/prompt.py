from __future__ import annotations

import json
from datetime import date
from typing import Protocol

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage


EDITORIAL_STYLE = (
    "The creator is a senior project manager and Agile delivery leader. His "
    "LinkedIn posts teach project managers, Scrum Masters, product managers, "
    "business analysts, and software-delivery professionals. Prefer practical "
    "topics such as Definition of Done, acceptance criteria, sprint planning, "
    "stakeholder communication, risk, quality, AI in delivery, workflow design, "
    "or lessons from real delivery situations. Write in an educational LinkedIn "
    "style: begin with a short conversational hook or question; explain a common "
    "problem; break down a framework, comparison, or workflow with concrete "
    "examples; close with a thoughtful question inviting comments. Keep the "
    "caption useful and detailed, not promotional, and provide 6 to 10 relevant "
    "hashtags. Never invent statistics or claim a topic is trending without "
    "supplied evidence. The image must be a detailed professional LinkedIn "
    "infographic, portrait 4:5 composition, with a bold readable title at top, "
    "clearly separated colored panels, concise labels and bullets, process arrows "
    "or side-by-side comparison when appropriate, simple business/tech icons, "
    "clean white background with navy/blue/green/orange accents, and a discussion "
    "prompt footer. Avoid photographs, generic dashboards, logos, watermarks, "
    "tiny unreadable filler text, or decorative clutter."
)


class PromptProvider(Protocol):
    def generate(self, day: str) -> ContentPackage: ...


class MockPromptProvider:
    def generate(self, day: str) -> ContentPackage:
        return ContentPackage.from_dict(
            {
                "date": day,
                "topic": "Definition of Done vs Acceptance Criteria in Agile delivery",
                "image_prompt": (
                    "Professional LinkedIn infographic, portrait 4:5 layout. Header: "
                    "'BUILT THE RIGHT THING vs BUILT THE THING RIGHT?' Compare "
                    "Acceptance Criteria and Definition of Done in two colored "
                    "columns with checklist icons, one login-feature example, "
                    "delivery-quality summary, and discussion footer. Clean white "
                    "background, navy title, orange and green panels, readable text."
                ),
                "video_script": {
                    "hook": "Is a story done when it meets acceptance criteria?",
                    "points": [
                        "Acceptance criteria prove the requested outcome",
                        "Definition of Done proves delivery quality",
                        "Strong teams use both before calling work complete",
                    ],
                    "cta": "What is one item your Definition of Done never skips?",
                },
                "linkedin_caption": (
                    "Is it accepted, or is it actually done?\n\nAcceptance Criteria "
                    "checks whether a feature solves the user's need. Definition of "
                    "Done checks whether it is safe, tested, reviewed, and ready to "
                    "ship.\n\nFor a login feature:\n- AC: the user can log in with "
                    "the required account.\n- DoD: code reviewed, tests passed, "
                    "security checks completed, and documentation updated.\n\nTeams "
                    "avoid last-minute surprises when they use both. What is one "
                    "check your team never skips before calling work done?"
                ),
                "hashtags": [
                    "#ProjectManagement",
                    "#ScrumMaster",
                    "#AgileDelivery",
                    "#SoftwareDevelopment",
                    "#ProductManagement",
                    "#QualityAssurance",
                ],
                "seo_title": "Acceptance Criteria vs Definition of Done",
                "seo_description": (
                    "A practical Agile comparison showing how acceptance criteria "
                    "and Definition of Done support predictable delivery."
                ),
            }
        )


class OpenAIPromptProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key or not settings.openai_model:
            raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def generate(self, day: str) -> ContentPackage:
        response = self.client.responses.create(
            model=self.model,
            instructions=EDITORIAL_STYLE,
            input=(
                f"Date: {day}. Produce one fresh teaching topic and complete content "
                "package in the specified project-management and Agile-delivery style. "
                "The image prompt must be self-contained for an image model to create "
                "the infographic."
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "daily_content_package",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "date",
                            "topic",
                            "image_prompt",
                            "video_script",
                            "linkedin_caption",
                            "hashtags",
                            "seo_title",
                            "seo_description",
                        ],
                        "properties": {
                            "date": {"type": "string"},
                            "topic": {"type": "string"},
                            "image_prompt": {"type": "string"},
                            "video_script": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["hook", "points", "cta"],
                                "properties": {
                                    "hook": {"type": "string"},
                                    "points": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 1,
                                    },
                                    "cta": {"type": "string"},
                                },
                            },
                            "linkedin_caption": {"type": "string"},
                            "hashtags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                            },
                            "seo_title": {"type": "string"},
                            "seo_description": {"type": "string"},
                        },
                    },
                }
            },
        )
        return ContentPackage.from_dict(json.loads(response.output_text))


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
                f"Output only valid JSON. {EDITORIAL_STYLE}"
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Date: {day}. Produce keys: date, topic, image_prompt, "
                        "video_script with hook, points and cta, linkedin_caption, "
                        "hashtags, seo_title, seo_description. Choose a fresh useful "
                        "topic in the specified professional delivery niche."
                    ),
                }
            ],
        )
        return ContentPackage.from_dict(json.loads(message.content[0].text))


def prompt_provider(settings: Settings) -> PromptProvider:
    if settings.prompt_provider == "mock":
        return MockPromptProvider()
    if settings.prompt_provider == "openai":
        return OpenAIPromptProvider(settings)
    if settings.prompt_provider == "anthropic":
        return AnthropicPromptProvider(settings)
    raise ValueError(f"Unsupported PROMPT_PROVIDER: {settings.prompt_provider}")


def today_iso() -> str:
    return date.today().isoformat()
