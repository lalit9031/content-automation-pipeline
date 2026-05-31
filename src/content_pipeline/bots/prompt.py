from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from dataclasses import replace
from datetime import date
from typing import Protocol

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage, LongFormVideoScript
from content_pipeline.openai_usage import log_openai_usage


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

CINEMATIC_IMAGE_STYLE = (
    "Create a vibrant, cinematic 3D supporting illustration with rounded shapes, "
    "soft volumetric lighting, pastel purple and cyan highlights, floating modular "
    "cards, clean modern tech surfaces, subtle sparkles, and strong depth. "
    "Keep it readable and polished, with no text, logos, or watermarks."
)

THUMBNAIL_IMAGE_STYLE = (
    "Create a high-contrast YouTube thumbnail with a bold hero subject, readable "
    "negative space for headline text, saturated lighting, sharp focal depth, "
    "cinematic composition, and no logos, watermarks, or tiny unreadable details."
)

STORYBOARD_STYLE_BASE = (
    "Use the same vibrant, cinematic 3D visual language across the entire sequence: "
    "premium animation, rounded shapes, soft glow, vibrant color contrast, smooth "
    "depth, and a clean scene composition suitable for a polished explainer video."
)


@dataclass(frozen=True)
class ImageStylePack:
    topic: str
    topic_prompt: str
    storyboard_prompts: list[dict[str, str]]
    thumbnail_prompt: str
    notes: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class PromptProvider(Protocol):
    def generate(self, day: str, avoid_topics: list[str] | None = None) -> ContentPackage: ...


def build_cinematic_image_prompt(topic: str, subject: str = "", audience: str = "professional audiences") -> str:
    focus = f" about {subject}" if subject else ""
    return (
        f"A vivid supporting illustration for {topic}{focus}, optimized for {audience}. "
        f"{CINEMATIC_IMAGE_STYLE} "
        "Design it like a premium hero image with generous negative space for overlays."
    )


def build_thumbnail_prompt(topic: str, subject: str = "", audience: str = "YouTube viewers") -> str:
    focus = f" featuring {subject}" if subject else ""
    return (
        f"A striking thumbnail concept for {topic}{focus}, designed for {audience}. "
        f"{THUMBNAIL_IMAGE_STYLE} "
        "Make the message obvious at a glance and leave a safe area for any later text overlay."
    )


def build_storyboard_prompts(
    topic: str,
    *,
    scene_count: int = 35,
) -> list[dict[str, str]]:
    scene_templates = [
        "Intro: a vibrant opening frame introducing {topic} with glowing modular elements and a cinematic tech atmosphere.",
        "Traditional setup: a grounded pre-AI workspace showing the old way of handling {topic}.",
        "Core idea: a clean abstract visual that explains the heart of {topic}.",
        "Challenge: a visually obvious bottleneck or messy process blocking {topic}.",
        "AI enters: a friendly assistant or system starting to help with {topic}.",
        "Transformation: old manual work dissolves into a cleaner modern workflow for {topic}.",
        "Speed: fast, elegant motion showing how {topic} moves quicker with assistance.",
        "Analytics: floating charts and dashboard cards summarizing {topic} insights.",
        "Collaboration: a team working together around a glowing shared table for {topic}.",
        "Assistant ecosystem: a small helper drone or bot supporting {topic} tasks.",
        "Predictive view: a future timeline forecasting the next steps in {topic}.",
        "Roadblocks removed: a barrier breaks apart to reveal progress in {topic}.",
        "Continuous improvement: an infinity loop or cycle representing better {topic}.",
        "Resource optimization: a balanced, polished visual showing smarter use of time and energy in {topic}.",
        "Quality control: a scanner or inspection beam checking the quality of {topic}.",
        "Midpoint recap: split-screen comparison of manual vs modern {topic}.",
        "Human partnership: a human and assistant high-five while improving {topic}.",
        "Agility: flowing motion and flexible shapes adapting to new {topic} demands.",
        "Data streams: glowing particles flowing into an organized structure for {topic}.",
        "Strategic architecture: a blueprint becoming a stable system for {topic}.",
        "Scale: a global or large-scale map showing {topic} growing confidently.",
        "Cloud layer: secure cloud-style infrastructure supporting {topic}.",
        "Real-time tracking: a live progress display for {topic}.",
        "Waste removal: clutter or noise swept away from the {topic} workspace.",
        "Frameworks: modular blocks stacking into a scalable {topic} system.",
        "Security: a shield or vault protecting the {topic} workflow.",
        "Feedback loop: a circular reflection or ripple effect improving {topic}.",
        "Success moment: a summit or peak shot showing {topic} mastered.",
        "Next generation: a seed or spark becoming the next evolution of {topic}.",
        "Peak optimization: a perfectly tuned engine room for {topic}.",
        "Summary: a wide polished overview that brings all {topic} ideas together.",
        "Call to action: a clean final frame leaving space for a title or CTA about {topic}.",
        "Outro card: a polished engagement frame for suggestions or next steps on {topic}.",
        "Social follow-up: floating engagement icons themed around {topic}.",
        "Final end card: a premium outro scene with bold subscribe/like/bell energy for {topic}.",
    ]
    prompts: list[dict[str, str]] = []
    for index in range(scene_count):
        template = scene_templates[index % len(scene_templates)]
        prompts.append(
            {
                "scene_number": index + 1,
                "segment": f"Scene {index + 1:02d}",
                "prompt": (
                    template.replace("{topic}", topic)
                    + f" {STORYBOARD_STYLE_BASE}"
                ),
            }
        )
    return prompts


def build_image_style_pack(
    topic: str,
    *,
    subject: str = "",
    audience: str = "professional audiences",
    scene_count: int = 35,
) -> ImageStylePack:
    return ImageStylePack(
        topic=topic,
        topic_prompt=build_cinematic_image_prompt(topic, subject, audience),
        storyboard_prompts=build_storyboard_prompts(topic, scene_count=scene_count),
        thumbnail_prompt=build_thumbnail_prompt(topic, subject, audience="YouTube viewers"),
        notes=[
            "Keep text out of the image prompt itself.",
            "Use one style pack per topic and swap only the topic/subject.",
            "Keep the storyboard sequence consistent with the same palette and depth cues.",
            "Always keep the finished image with no text, logos, or watermarks.",
        ],
    )


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
    log_openai_usage(
        response,
        label="OpenAI long-form script usage",
        context_window_tokens=128000,
        prompt_rate_per_1m=0.75,
        completion_rate_per_1m=4.50,
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
    def generate(self, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
        avoid = {topic.lower().strip() for topic in avoid_topics or []}
        if "definition of done vs acceptance criteria in agile delivery" in avoid:
            return ContentPackage.from_dict(
                {
                    "date": day,
                    "topic": "Sprint planning questions that reduce rework",
                    "image_prompt": build_cinematic_image_prompt(
                        "Sprint planning questions that reduce rework",
                        "an Agile team reviewing a planning checklist",
                        "Agile delivery teams",
                    ),
                    "linkedin_infographic": {
                        "headline": "Plan the work, then protect the plan",
                        "subtitle": "Sprint planning questions that reduce rework",
                        "left_panel": {
                            "title": "Before planning",
                            "points": [
                                "Clarify the outcome first",
                                "Check dependencies early",
                                "Agree on the real capacity",
                            ],
                        },
                        "right_panel": {
                            "title": "During planning",
                            "points": [
                                "Split stories until they are testable",
                                "Confirm acceptance criteria",
                                "Surface risks before the sprint starts",
                            ],
                        },
                        "takeaway_title": "Better planning makes delivery calmer",
                        "takeaway_points": [
                            "Short, precise questions prevent hidden work",
                            "Planning should reduce confusion, not create it",
                        ],
                        "workflow": ["Prepare", "Plan", "Confirm", "Commit"],
                        "discussion_prompt": "What question saves your team the most time?",
                    },
                    "video_script": {
                        "hook": "What is the one question that saves a sprint?",
                        "points": [
                            "Start with the outcome, not the task list",
                            "Check dependencies before you estimate",
                            "Make the acceptance path visible to everyone",
                        ],
                        "cta": "Which question do you always ask in sprint planning?",
                    },
                    "linkedin_caption": (
                        "Sprint planning is easier when the team asks the right questions.\n\n"
                        "A good planning session clarifies the outcome, surfaces dependencies, "
                        "and keeps the sprint goal realistic before anyone commits.\n\n"
                        "Try this next time: start with the outcome, check capacity honestly, "
                        "and make sure the acceptance path is visible to everyone.\n\n"
                        "What question helps your team avoid rework?"
                    ),
                    "hashtags": [
                        "#ProjectManagement",
                        "#ScrumMaster",
                        "#AgileDelivery",
                        "#SprintPlanning",
                        "#QualityAssurance",
                        "#TeamWork",
                    ],
                    "seo_title": "Sprint planning questions that reduce rework",
                    "seo_description": (
                        "A practical Agile post showing how better sprint-planning questions reduce rework."
                    ),
                }
            )
        return ContentPackage.from_dict(
            {
                "date": day,
                "topic": "Definition of Done vs Acceptance Criteria in Agile delivery",
                "image_prompt": build_cinematic_image_prompt(
                    "Definition of Done vs Acceptance Criteria in Agile delivery",
                    "an Agile team reviewing a quality checklist",
                    "Agile delivery teams",
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

    def generate(self, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
        avoid_text = _avoid_topics_text(avoid_topics)
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
                f"{avoid_text}"
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
        log_openai_usage(
            response,
            label="OpenAI daily package usage",
            context_window_tokens=128000,
            prompt_rate_per_1m=0.75,
            completion_rate_per_1m=4.50,
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

    def generate(self, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
        avoid_text = _avoid_topics_text(avoid_topics)
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
                        f"{avoid_text}"
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


def _avoid_topics_text(avoid_topics: list[str] | None) -> str:
    if not avoid_topics:
        return ""
    joined = "; ".join(topic for topic in avoid_topics[:12] if topic)
    return f"\nAvoid these previously used topics and close variations: {joined}"


def today_iso() -> str:
    return date.today().isoformat()
