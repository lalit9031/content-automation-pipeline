"""Science Story Agent — generates 30-minute cinematic science discovery stories.

Architecture
------------
    Topic input (or auto-generate)
            │
            ▼
    Phase 1: Chapter Outline (structure + narrative arc)
            │
            ▼
    Phase 2: Scene Generation (detailed per-chapter scenes)
            │
            ▼
    ScienceStoryScript → Science Video Agent

Each scene contains:
    - Hindi narration text (narration_hi)
    - Hindi on-screen text (on_screen_text_hi)
    - English visual prompt for cinematic image generation
    - Duration in seconds
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.models import ScienceScene, ScienceStoryScript
from content_pipeline.openai_usage import log_openai_usage

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  CONSTANTS
# ---------------------------------------------------------------------------

TARGET_DURATION_SECONDS = 1800  # 30 minutes
MIN_SCENES = 60
MAX_SCENES = 90
MIN_DURATION_SECONDS = 28 * 60  # 28 min
MAX_DURATION_SECONDS = 32 * 60  # 32 min

SCIENCE_EDITORIAL_STYLE = """You are an award-winning science storyteller and documentary writer.
You create immersive, cinematic science discovery stories that make complex
scientific ideas accessible and thrilling for a general YouTube audience.

Your stories follow this narrative formula:
1. Hook the viewer with a compelling mystery or question
2. Introduce the key scientific figures and their discoveries
3. Build tension by showing competing theories and failed attempts
4. Reveal the breakthrough moment with dramatic weight
5. Explain the impact — how this changed science and our world
6. Leave the viewer with a thought-provoking closing perspective

Write in a rich, vivid style suitable for high-quality cinematic narration.
Use analogies and concrete images to explain abstract concepts.
Every scene must feel like a mini-revelation.

The narration (narration_hi) must be in Hindi — clear, natural, slightly formal
but engaging Hindi. Think of a National Geographic documentary narrator.
Use correct Hindi scientific terminology where possible.

The on-screen text (on_screen_text_hi) is also in Hindi — short, punchy,
readable in 3-5 seconds. Like documentary title cards.

The visual_prompt must be in English — detailed cinematic prompts for
AI image generation. Include lighting, composition, mood, and era/style.
"""

# ---------------------------------------------------------------------------
#  PHASE 1: CHAPTER OUTLINE
# ---------------------------------------------------------------------------

# Pre-defined science story templates for auto-generation
SCIENCE_STORY_TEMPLATES = [
    {
        "topic": "The Discovery of Penicillin",
        "tagline": "How a forgotten moldy petri dish changed medicine forever",
        "hook": "साल 1928 की बात है। एक गंदी प्रयोगशाला में, एक वैज्ञानिक की अनदेखी ने दुनिया को बचा लिया।",
        "chapters": [
            "The Accidental Laboratory",
            "The Mysterious Mold",
            "The Failed Experiments",
            "The First Human Trial",
            "War and Mass Production",
            "The Antibiotic Revolution",
            "The Coming Crisis",
        ],
    },
    {
        "topic": "The Double Helix: Unraveling DNA",
        "tagline": "The race to discover the secret of life itself",
        "hook": "जीवन का रहस्य — एक अणु में छिपा था। तीन वैज्ञानिकों ने इसे खोजने की होड़ लगाई।",
        "chapters": [
            "The Secret of Heredity",
            "The Rival Laboratories",
            "Photo 51 — The Clue",
            "Building the Model",
            "The Discovery",
            "The Nobel Prize Controversy",
            "The Genetic Age Begins",
        ],
    },
    {
        "topic": "The Theory of Relativity",
        "tagline": "How Einstein rewrote the laws of the universe",
        "hook": "एक क्लर्क ने, बिना किसी प्रयोगशाला के, ब्रह्मांड के नियम बदल दिए। यह कहानी है आइंस्टीन की।",
        "chapters": [
            "The Patent Office Dreamer",
            "Chasing Light",
            "Special Relativity",
            "Space and Time Bend",
            "The Eclipse That Proved It",
            "Black Holes and Time Travel",
            "The Unfinished Dream",
        ],
    },
    {
        "topic": "The CRISPR Revolution",
        "tagline": "Editing the code of life — humanity's greatest power and responsibility",
        "hook": "हम अपने जीन बदल सकते हैं। यह विज्ञान कथा नहीं है — यह CRISPR है।",
        "chapters": [
            "The Bacterial Defense System",
            "The Accidental Discovery",
            "The Gene-Editing Breakthrough",
            "The Race for the Patent",
            "Healing the Incurable",
            "Designer Babies",
            "The Future of Evolution",
        ],
    },
    {
        "topic": "The Big Bang and the Origin of the Universe",
        "tagline": "From nothing to everything — the cosmic origin story",
        "hook": "क्या होगा अगर मैं कहूँ कि पूरा ब्रह्मांड एक बिंदु से शुरू हुआ? यह सबसे बड़ी कहानी है।",
        "chapters": [
            "The Expanding Universe",
            "The Primeval Atom",
            "Cosmic Microwave Background",
            "The First Three Minutes",
            "Birth of Stars and Galaxies",
            "Dark Matter and Dark Energy",
            "The Fate of the Cosmos",
        ],
    },
    {
        "topic": "The Discovery of Electricity and Magnetism",
        "tagline": "The invisible force that powers our modern world",
        "hook": "बिजली के बिना हमारी दुनिया की कल्पना करना मुश्किल है। लेकिन क्या आप जानते हैं इसकी खोज कैसे हुई?",
        "chapters": [
            "The Amber Mystery",
            "The Leyden Jar",
            "Franklin's Kite",
            "Volta's Battery",
            "Faraday's Electromagnetism",
            "Maxwell's Equations",
            "Edison vs Tesla",
        ],
    },
    {
        "topic": "The Quantum Revolution",
        "tagline": "When reality becomes stranger than science fiction",
        "hook": "जब वैज्ञानिकों ने परमाणु के अंदर झांका, तो उन्होंने पाया कि वहाँ के नियम हमारी समझ से परे हैं।",
        "chapters": [
            "The Ultraviolet Catastrophe",
            "Planck's Quantum",
            "The Bohr Atom",
            "Schrödinger's Cat",
            "The Copenhagen Interpretation",
            "Quantum Entanglement",
            "The Quantum Future",
        ],
    },
]

# ---------------------------------------------------------------------------
#  SCHEMA DEFINITIONS
# ---------------------------------------------------------------------------

CHAPTER_OUTLINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "topic", "tagline", "hook", "chapters"],
    "properties": {
        "title": {"type": "string"},
        "topic": {"type": "string"},
        "tagline": {"type": "string"},
        "hook": {
            "type": "string",
            "description": "Opening hook in Hindi, 2-3 sentences maximum, compelling and cinematic.",
        },
        "chapters": {
            "type": "array",
            "minItems": 5,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "description",
                    "narrative_arc",
                    "key_concepts",
                    "estimated_scenes",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "What this chapter covers, in English.",
                    },
                    "narrative_arc": {
                        "type": "string",
                        "description": "The emotional/narrative journey of this chapter (e.g., mystery → discovery → awe).",
                    },
                    "key_concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 5,
                    },
                    "estimated_scenes": {
                        "type": "integer",
                        "minimum": 8,
                        "maximum": 15,
                        "description": "Number of scenes planned for this chapter.",
                    },
                },
            },
        },
    },
}

CHAPTER_SCENES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["chapter_title", "scenes"],
    "properties": {
        "chapter_title": {"type": "string"},
        "scenes": {
            "type": "array",
            "minItems": 8,
            "maxItems": 15,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "narration_hi",
                    "on_screen_text_hi",
                    "visual_prompt",
                    "duration_seconds",
                ],
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short English title for this scene.",
                    },
                    "narration_hi": {
                        "type": "string",
                        "description": "Hindi narration for this scene. Natural, documentary-style Hindi.",
                    },
                    "on_screen_text_hi": {
                        "type": "string",
                        "maxLength": 100,
                        "description": "Hindi on-screen text, short and readable like a title card.",
                    },
                    "visual_prompt": {
                        "type": "string",
                        "description": "Detailed cinematic English prompt for AI image generation. Include era, lighting, mood, composition, style.",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "minimum": 15,
                        "maximum": 40,
                        "description": "Duration of this scene in seconds. Target ~25s for most scenes.",
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
#  CORE FUNCTIONS
# ---------------------------------------------------------------------------

def generate_science_story_script(
    settings: Settings,
    topic: str = "",
    target_minutes: int = 30,
) -> ScienceStoryScript:
    """Generate a complete 30-minute science discovery story script.

    This is a two-phase process:
        1. Generate the chapter outline (structure, narrative arc)
        2. Generate detailed scenes for each chapter

    Args:
        settings: Pipeline settings (requires OPENAI_API_KEY).
        topic: Optional science topic. Auto-selects if empty.
        target_minutes: Target duration in minutes (default 30).

    Returns:
        A complete ScienceStoryScript with scenes.

    Raises:
        ValueError: If OpenAI is not configured or generation fails.
    """
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for science story generation.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc

    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.openai_model

    # --- Phase 1: Generate chapter outline ---
    outline = _generate_chapter_outline(client, model, topic, target_minutes)

    # --- Phase 2: Generate scenes for each chapter ---
    all_scenes: list[ScienceScene] = []
    for chapter_index, chapter in enumerate(outline["chapters"]):
        log.info(
            "Generating scenes for chapter %d/%d: %s",
            chapter_index + 1,
            len(outline["chapters"]),
            chapter["title"],
        )
        chapter_scenes = _generate_chapter_scenes(
            client,
            model,
            outline,
            chapter,
            chapter_index,
            len(outline["chapters"]),
            _duration_budget_for_chapter(
                scenes_so_far=all_scenes,
                target_seconds=TARGET_DURATION_SECONDS,
                remaining_chapters=len(outline["chapters"]) - chapter_index - 1,
                estimated_scenes=chapter.get("estimated_scenes", 10),
            ),
        )
        all_scenes.extend(chapter_scenes)

    # --- Assemble the final script ---
    script = ScienceStoryScript(
        title=outline["title"],
        topic=outline["topic"],
        tagline=outline["tagline"],
        chapters=[c["title"] for c in outline["chapters"]],
        scenes=all_scenes,
    )

    _validate_script_duration(script)
    log.info(
        "Generated science story: %s | %d scenes | %.1f minutes",
        script.title,
        len(script.scenes),
        script.duration_minutes,
    )
    return script


def _generate_chapter_outline(
    client: Any,
    model: str,
    topic: str,
    target_minutes: int,
) -> dict[str, Any]:
    """Phase 1: Generate the high-level chapter outline for the story."""
    template_info = _find_template(topic)

    if not topic:
        topic_text = "Choose one of the most compelling science discovery stories from the templates below, or invent a fresh one."
    else:
        topic_text = f"Create a science story about: {topic}"

    input_text = (
        f"{topic_text}\n\n"
        f"Target duration: {target_minutes} minutes.\n"
        f"Number of chapters: 5 to 8.\n"
        f"Each chapter should have 8 to 15 scenes.\n"
        f"Each scene should be 15-40 seconds long.\n\n"
    )

    if template_info and not topic:
        template_lines = "\n".join(f"- {t['topic']}: {t['tagline']}" for t in SCIENCE_STORY_TEMPLATES)
        input_text += (
            f"Available template topics:\n"
            f"{template_lines}\n\n"
            f"Or create a fresh topic not listed above.\n"
        )
    elif template_info:
        input_text += (
            f"Related template:\n"
            f"- {template_info['topic']}: {template_info['tagline']}\n"
            f"- Hook: {template_info['hook']}\n"
            f"- Sample chapters: {', '.join(template_info['chapters'])}\n\n"
            f"Use this as inspiration but create a unique, expanded narrative.\n"
        )

    response = client.responses.create(
        model=model,
        instructions=(
            f"{SCIENCE_EDITORIAL_STYLE}\n\n"
            "Generate a chapter outline for a cinematic science documentary. "
            "Each chapter must have a clear narrative arc (e.g., mystery → tension → discovery → awe). "
            "Include key scientific concepts for each chapter."
        ),
        input=input_text,
        text={
            "format": {
                "type": "json_schema",
                "name": "science_story_chapter_outline",
                "strict": True,
                "schema": CHAPTER_OUTLINE_SCHEMA,
            }
        },
    )

    log_openai_usage(
        response,
        label="Science story outline generation",
        context_window_tokens=128000,
        prompt_rate_per_1m=0.75,
        completion_rate_per_1m=4.50,
    )

    outline = json.loads(response.output_text)

    # Validate structure
    chapters = outline.get("chapters", [])
    if not 5 <= len(chapters) <= 8:
        raise ValueError(
            f"Expected 5-8 chapters, got {len(chapters)}. Retrying may fix this."
        )

    return outline


def _generate_chapter_scenes(
    client: Any,
    model: str,
    outline: dict[str, Any],
    chapter: dict[str, Any],
    chapter_index: int,
    total_chapters: int,
    chapter_duration_budget: int,
) -> list[ScienceScene]:
    """Phase 2: Generate detailed scenes for a single chapter."""
    target_scenes = chapter.get("estimated_scenes", 10)
    scene_duration = max(15, min(40, chapter_duration_budget // max(target_scenes, 1)))

    context = (
        f"Story title: {outline['title']}\n"
        f"Topic: {outline['topic']}\n"
        f"Tagline: {outline['tagline']}\n"
        f"Chapter {chapter_index + 1} of {total_chapters}: {chapter['title']}\n"
        f"Description: {chapter['description']}\n"
        f"Narrative arc: {chapter['narrative_arc']}\n"
        f"Key concepts: {', '.join(chapter.get('key_concepts', []))}\n"
        f"Previous chapters: {', '.join(c['title'] for c in outline['chapters'][:chapter_index]) or 'None (this is the first chapter)'}\n\n"
        f"Target scene count: ~{target_scenes} scenes.\n"
        f"Scene duration: ~{scene_duration} seconds each.\n"
        f"Chapter total budget: ~{chapter_duration_budget} seconds.\n\n"
        "IMPORTANT:\n"
        "- narration_hi must be in Hindi (natural documentary-style Hindi)\n"
        "- on_screen_text_hi must be in Hindi (short, readable title cards)\n"
        "- visual_prompt must be in English (detailed cinematic prompts)\n"
        "- Each scene should advance the narrative — no filler scenes\n"
        "- Vary scene durations for rhythm: some dramatic 15s reveals, some detailed 35s explanations\n"
    )

    response = client.responses.create(
        model=model,
        instructions=(
            f"{SCIENCE_EDITORIAL_STYLE}\n\n"
            f"You are writing scenes for Chapter {chapter_index + 1}: {chapter['title']}.\n"
            f"This chapter's narrative arc: {chapter['narrative_arc']}.\n"
            "Create rich, visual scenes that build this chapter's story arc. "
            "Each scene must feel like a mini-revelation. "
            "Ensure the Hindi narration flows naturally from scene to scene."
        ),
        input=context,
        text={
            "format": {
                "type": "json_schema",
                "name": "science_story_chapter_scenes",
                "strict": True,
                "schema": CHAPTER_SCENES_SCHEMA,
            }
        },
    )

    log_openai_usage(
        response,
        label=f"Science story scenes: Chapter {chapter_index + 1}",
        context_window_tokens=128000,
        prompt_rate_per_1m=0.75,
        completion_rate_per_1m=4.50,
    )

    data = json.loads(response.output_text)
    scenes_data = data.get("scenes", [])

    return [
        ScienceScene(
            chapter=chapter["title"],
            chapter_index=chapter_index,
            scene_index=scene_index,
            title=s["title"],
            narration_hi=s["narration_hi"],
            on_screen_text_hi=s["on_screen_text_hi"],
            visual_prompt=s["visual_prompt"],
            duration_seconds=s["duration_seconds"],
        )
        for scene_index, s in enumerate(scenes_data)
    ]


# ---------------------------------------------------------------------------
#  HELPERS
# ---------------------------------------------------------------------------

def _find_template(topic: str) -> dict[str, Any] | None:
    """Find a matching template for the given topic (case-insensitive partial match)."""
    if not topic:
        return None
    topic_lower = topic.lower()
    for template in SCIENCE_STORY_TEMPLATES:
        if topic_lower in template["topic"].lower():
            return template
        for keyword in template["topic"].lower().split():
            if keyword in topic_lower and len(keyword) > 4:
                return template
    return None


def _duration_budget_for_chapter(
    scenes_so_far: list[ScienceScene],
    target_seconds: int,
    remaining_chapters: int,
    estimated_scenes: int,
) -> int:
    """Calculate a fair duration budget for the next chapter."""
    used = sum(s.duration_seconds for s in scenes_so_far)
    remaining = target_seconds - used
    if remaining_chapters <= 0:
        return max(120, remaining)
    # Distribute remaining time proportionally
    return max(120, remaining // (remaining_chapters + 1))


def _validate_script_duration(script: ScienceStoryScript) -> None:
    """Validate the total script duration is within acceptable bounds."""
    total = script.duration_seconds
    if total < MIN_DURATION_SECONDS:
        log.warning(
            "Science story '%s' is only %.1f minutes (min %.1f). Consider regenerating.",
            script.title,
            total / 60,
            MIN_DURATION_SECONDS / 60,
        )
    if total > MAX_DURATION_SECONDS:
        log.warning(
            "Science story '%s' is %.1f minutes (max %.1f). Some scenes may be trimmed.",
            script.title,
            total / 60,
            MAX_DURATION_SECONDS / 60,
        )


def list_available_topics() -> list[str]:
    """Return available science story template topics."""
    return [t["topic"] for t in SCIENCE_STORY_TEMPLATES]


def save_script_to_disk(script: ScienceStoryScript, output_dir: str) -> dict[str, str]:
    """Save the generated script to disk as JSON and Markdown."""
    from pathlib import Path

    root = Path(output_dir) / "science_stories" / script.topic.replace(" ", "_").lower()[:48]
    root.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = root / "script.json"
    json_path.write_text(
        json.dumps(script.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Markdown summary
    md_lines = [
        f"# {script.title}",
        "",
        f"**Topic:** {script.topic}",
        f"**Tagline:** {script.tagline}",
        f"**Duration:** {script.duration_seconds}s ({script.duration_minutes:.1f} min)",
        f"**Scenes:** {len(script.scenes)}",
        "",
        "## Chapters",
        "",
    ]
    for i, chapter in enumerate(script.chapters):
        chapter_scenes = script.scenes_for_chapter(i)
        chapter_duration = sum(s.duration_seconds for s in chapter_scenes)
        md_lines.extend(
            [
                f"### {i + 1}. {chapter} ({len(chapter_scenes)} scenes, {chapter_duration}s)",
                "",
            ]
        )
        for scene in chapter_scenes:
            md_lines.extend(
                [
                    f"**{scene.scene_index + 1}. {scene.title}** ({scene.duration_seconds}s)",
                    "",
                    f"> {scene.narration_hi}",
                    "",
                    f"*On screen:* {scene.on_screen_text_hi}",
                    "",
                ]
            )

    md_path = root / "script.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "workspace": str(root),
    }
