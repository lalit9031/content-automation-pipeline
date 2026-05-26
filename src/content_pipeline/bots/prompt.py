from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import Protocol

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage, LongFormVideoScript


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
    "supplied evidence. The linkedin_infographic content is rendered by a controlled "
    "portrait template with a headline, two panels, a takeaway, workflow, and "
    "discussion footer; keep every item brief and readable. The image_prompt is "
    "only for a supporting illustration and must contain no text, logos, or "
    "watermarks."
)


class PromptProvider(Protocol):
    def generate(self, day: str) -> ContentPackage: ...


def generate_long_form_video_script(
    package: ContentPackage, settings: Settings, target_minutes: int = 4
) -> LongFormVideoScript:
    """Generate a narrated 3-5 minute video outline for an existing package."""
    if not 3 <= target_minutes <= 5:
        raise ValueError("Long-form video target must be between 3 and 5 minutes.")
    if not settings.openai_api_key or not settings.openai_model:
        raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc

    minimum_seconds = 180
    maximum_seconds = 300
    response = OpenAI(api_key=settings.openai_api_key).responses.create(
        model=settings.openai_model,
        instructions=(
            f"{EDITORIAL_STYLE} Write a narrated YouTube explainer. The finished video "
            f"should target approximately {target_minutes} minutes and must run "
            f"between {minimum_seconds} and {maximum_seconds} seconds. "
            "Use practical, original teaching language and do not invent evidence."
        ),
        input=(
            "Expand this existing daily topic into a long-form video script. Each scene "
            "must have short readable on-screen copy and separate natural narration. "
            "Use 14 to 20 scenes. Keep on_screen_text under 90 characters and narration "
            "roughly appropriate for its duration at a calm speaking pace. Include an "
            "opening hook, problem explanation, step-by-step guidance, concrete example, "
            "mistakes to avoid, recap, and closing question.\n\n"
            f"Existing package:\n{json.dumps(package.as_dict(), indent=2)}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "long_form_video_script",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "scenes"],
                    "properties": {
                        "title": {"type": "string"},
                        "scenes": {
                            "type": "array",
                            "minItems": 14,
                            "maxItems": 20,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "title",
                                    "on_screen_text",
                                    "narration",
                                    "duration_seconds",
                                ],
                                "properties": {
                                    "title": {"type": "string"},
                                    "on_screen_text": {"type": "string"},
                                    "narration": {"type": "string"},
                                    "duration_seconds": {
                                        "type": "integer",
                                        "minimum": 8,
                                        "maximum": 20,
                                    },
                                },
                            },
                        },
                    },
                },
            }
        },
    )
    script = LongFormVideoScript.from_dict(json.loads(response.output_text))
    return _fit_long_form_duration(script, minimum_seconds, maximum_seconds)


def _fit_long_form_duration(
    script: LongFormVideoScript, minimum_seconds: int, maximum_seconds: int
) -> LongFormVideoScript:
    """Adjust scene holds slightly when generated timing falls outside bounds."""
    scenes = list(script.scenes)
    while sum(scene.duration_seconds for scene in scenes) > maximum_seconds:
        for index in range(len(scenes) - 1, -1, -1):
            if scenes[index].duration_seconds > 8:
                scenes[index] = replace(
                    scenes[index],
                    duration_seconds=scenes[index].duration_seconds - 1,
                )
                break
        else:
            raise ValueError("Generated long-form script cannot be shortened to 5 minutes.")
    while sum(scene.duration_seconds for scene in scenes) < minimum_seconds:
        for index in range(len(scenes)):
            if scenes[index].duration_seconds < 20:
                scenes[index] = replace(
                    scenes[index],
                    duration_seconds=scenes[index].duration_seconds + 1,
                )
                break
        else:
            raise ValueError("Generated long-form script cannot be extended to 3 minutes.")
    return replace(script, scenes=scenes)


class MockPromptProvider:
    def generate(self, day: str) -> ContentPackage:
        return ContentPackage.from_dict(
            {
                "date": day,
                "topic": "Definition of Done vs Acceptance Criteria in Agile delivery",
                "image_prompt": (
                    "Clean supporting illustration of an Agile team reviewing a "
                    "quality checklist, modern flat editorial style, no text."
                ),
                "linkedin_infographic": {
                    "headline": "Built the right thing vs built the thing right?",
                    "subtitle": "Acceptance Criteria (AC) vs Definition of Done (DoD)",
                    "left_panel": {
                        "title": "Acceptance Criteria",
                        "points": [
                            "Specific to one feature or story",
                            "Defines what the user must be able to do",
                            "Example: user can log in with Google",
                        ],
                    },
                    "right_panel": {
                        "title": "Definition of Done",
                        "points": [
                            "Quality standard for every story",
                            "Covers tests, review and documentation",
                            "Example: tested, secure and deployable",
                        ],
                    },
                    "takeaway_title": "Use both before calling work complete",
                    "takeaway_points": [
                        "AC checks whether we built the right outcome",
                        "DoD checks whether we built it responsibly",
                    ],
                    "workflow": ["Refine", "Build", "Test", "Review", "Done"],
                    "discussion_prompt": "What is one check your team never skips?",
                },
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
                "The image_prompt is only for a supporting illustration with no text. "
                "The linkedin_infographic field drives a deterministic template: keep "
                "the headline under 58 characters, subtitle under 70 characters, "
                "each panel to 3 concise points under 65 characters, takeaway to 2 "
                "points under 70 characters, workflow to 4 or 5 labels of no more "
                "than 2 words each (for example: Discover, Refine, Build, Review, "
                "Done), and discussion_prompt under 70 characters."
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
                            "linkedin_infographic",
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
                            "linkedin_infographic": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "headline",
                                    "subtitle",
                                    "left_panel",
                                    "right_panel",
                                    "takeaway_title",
                                    "takeaway_points",
                                    "workflow",
                                    "discussion_prompt",
                                ],
                                "properties": {
                                    "headline": {"type": "string"},
                                    "subtitle": {"type": "string"},
                                    "left_panel": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["title", "points"],
                                        "properties": {
                                            "title": {"type": "string"},
                                            "points": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "minItems": 1,
                                            },
                                        },
                                    },
                                    "right_panel": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["title", "points"],
                                        "properties": {
                                            "title": {"type": "string"},
                                            "points": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "minItems": 1,
                                            },
                                        },
                                    },
                                    "takeaway_title": {"type": "string"},
                                    "takeaway_points": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 1,
                                    },
                                    "workflow": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 1,
                                    },
                                    "discussion_prompt": {"type": "string"},
                                },
                            },
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
                        "linkedin_infographic with headline, subtitle, left_panel "
                        "(title/points), right_panel (title/points), takeaway_title, "
                        "takeaway_points, workflow and discussion_prompt, "
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
