from __future__ import annotations

import json
import os
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
    "Style: Premium 3D character illustration with warm, expressive characters, friendly and approachable. "
    "Shapes and curves are beautifully rounded, smooth modern tech surfaces with tactile glassmorphism textures. "
    "Features a software developer or project manager sitting at a sleek minimalist glass desk, looking with an inspired smile at a floating, semi-transparent holographic UI dashboard in front of them showing glowing colorful charts and flowchart nodes. "
    "Includes a friendly little robotic AI assistant with glowing yellow eyes floating nearby. "
    "Color Palette: Soft pastel purple and cyan highlights, subtle orange/gold glow, deep blue-grey background studio environment. "
    "Lighting: Soft volumetric studio lighting, gentle depth of field, subtle glowing particles, dramatic contrast. "
    "Absolutely no large readable text inside the image. Reserve a clean typography-safe area for text overlays. "
    "Include clean high-tech interface dashboard backgrounds, flawless vector icons, clean background elements, sharp focus, masterpiece, 8k resolution, and absolutely no gibberish text, no distorted symbols."
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

CONTENT_PACKAGE_JSON_SCHEMA = """
Return strict JSON only with this schema:
{
  "date": "YYYY-MM-DD",
  "topic": "A fresh teaching topic",
  "image_prompt": "A supporting illustration prompt with no text, logos, or watermarks",
  "linkedin_infographic": {
    "headline": "headline under 58 characters",
    "subtitle": "subtitle under 70 characters",
    "left_panel": {
      "title": "panel title",
      "points": ["point 1", "point 2", "point 3"]
    },
    "right_panel": {
      "title": "panel title",
      "points": ["point 1", "point 2", "point 3"]
    },
    "takeaway_title": "short takeaway title",
    "takeaway_points": ["point 1", "point 2"],
    "workflow": ["Discover", "Refine", "Build", "Review", "Done"],
    "discussion_prompt": "short discussion prompt"
  },
  "video_script": {
    "hook": "hook line",
    "points": ["point 1", "point 2", "point 3"],
    "cta": "call to action"
  },
  "linkedin_caption": "detailed caption",
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "seo_title": "SEO title",
  "seo_description": "SEO description"
}
"""

LONG_FORM_JSON_SCHEMA = """
Return strict JSON only with this schema:
{
  "title": "A click-worthy long-form title",
  "scenes": [
    {
      "title": "scene title",
      "on_screen_text": "short on-screen copy",
      "narration": "natural narration",
      "duration_seconds": 8
    }
  ]
}
The scenes array must contain between 14 and 20 items.
Each duration_seconds must be between 8 and 20.
"""


def _first_non_empty(values: list[str] | tuple[str, ...], fallback: str = "") -> str:
    for value in values:
        if str(value).strip():
            return str(value).strip()
    return fallback.strip()


def _unique_non_empty(values: list[str] | tuple[str, ...], fallback: str = "") -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    fallback = fallback.strip()
    if not ordered and fallback:
        ordered.append(fallback)
    return ordered


def _extract_json_object(text: str) -> dict[str, object]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.lstrip("`")
        raw = raw.replace("json\n", "", 1).replace("JSON\n", "", 1)
        raw = raw.rstrip("`").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(raw[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Model response did not contain valid JSON.")


def _build_openai_client(api_key: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _build_openai_compatible_client(*, api_key: str, base_url: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url)


def _nvidia_text_model(settings: Settings) -> str:
    return _first_non_empty(
        [
            os.getenv("NVIDIA_TEXT_MODEL", ""),
            settings.nvidia_nim_model,
            "microsoft/phi-4-mini-instruct",
        ],
        "microsoft/phi-4-mini-instruct",
    )


def _openai_key_pool(settings: Settings) -> list[str]:
    return _unique_non_empty(list(settings.openai_api_keys), settings.openai_api_key)


def _gemini_key_pool(settings: Settings) -> list[str]:
    return _unique_non_empty(list(settings.gemini_api_keys), settings.gemini_api_key)


def _nvidia_key_pool(settings: Settings) -> list[str]:
    return _unique_non_empty(list(settings.nvidia_api_keys), settings.nvidia_api_key)


def _daily_package_prompt(day: str, avoid_topics: list[str] | None = None) -> str:
    avoid_text = _avoid_topics_text(avoid_topics)
    return (
        f"{EDITORIAL_STYLE}\n"
        f"Date: {day}. Produce one fresh teaching topic and complete content package in the "
        "specified project-management and Agile-delivery style. The image_prompt is only "
        "for a supporting illustration with no text. The linkedin_infographic field drives "
        "a deterministic template: keep the headline under 58 characters, subtitle under 70 "
        "characters, each panel to 3 concise points under 65 characters, takeaway to 2 "
        "points under 70 characters, workflow to 4 or 5 labels of no more than 2 words each "
        "(for example: Discover, Refine, Build, Review, Done), and discussion_prompt under 70 "
        f"characters.{avoid_text}\n\n{CONTENT_PACKAGE_JSON_SCHEMA}"
    )


def _long_form_prompt(package: ContentPackage, target_minutes: int) -> str:
    minimum_seconds = 180
    maximum_seconds = 300
    return (
        f"{EDITORIAL_STYLE} Write a narrated YouTube explainer. The finished video should "
        f"target approximately {target_minutes} minutes and must run between {minimum_seconds} "
        f"and {maximum_seconds} seconds. Use practical, original teaching language and do not "
        "invent evidence.\n\n"
        "Expand this existing daily topic into a long-form video script. Each scene must have "
        "short readable on-screen copy and separate natural narration. Use 14 to 20 scenes. "
        "Keep on_screen_text under 90 characters and narration roughly appropriate for its "
        "duration at a calm speaking pace. Include an opening hook, problem explanation, "
        "step-by-step guidance, concrete example, mistakes to avoid, recap, and closing "
        f"question.\n\nExisting package:\n{json.dumps(package.as_dict(), indent=2)}\n\n"
        f"{LONG_FORM_JSON_SCHEMA}"
    )


def _chat_json_completion(
    *,
    client,
    model: str,
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    extra_body: dict[str, object] | None = None,
) -> dict[str, object]:
    attempts: list[dict[str, object]] = [
        {"response_format": {"type": "json_object"}},
        {},
    ]
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            kwargs: dict[str, object] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": max_tokens,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "stream": False,
            }
            if extra_body:
                kwargs["extra_body"] = extra_body
            kwargs.update(attempt)
            completion = client.chat.completions.create(**kwargs)
            message = completion.choices[0].message
            content = str(getattr(message, "content", "") or "").strip()
            return _extract_json_object(content)
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("JSON completion failed.")


def _generate_package_with_openai(settings: Settings, *, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
    keys = _openai_key_pool(settings)
    if not keys:
        raise ValueError("OPENAI_API_KEY is required")
    last_error: Exception | None = None
    prompt = _daily_package_prompt(day, avoid_topics)
    for api_key in keys:
        try:
            response = _build_openai_client(api_key).responses.create(
                model=settings.openai_model,
                instructions=EDITORIAL_STYLE,
                input=prompt,
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
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI prompt generation failed.")


def _generate_package_with_nvidia(settings: Settings, *, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
    keys = _nvidia_key_pool(settings)
    if not keys:
        raise ValueError("NVIDIA_API_KEY is required")
    last_error: Exception | None = None
    prompt = _daily_package_prompt(day, avoid_topics)
    for api_key in keys:
        try:
            client = _build_openai_compatible_client(
                api_key=api_key,
                base_url="https://integrate.api.nvidia.com/v1",
            )
            payload = _chat_json_completion(
                client=client,
                model=_nvidia_text_model(settings),
                prompt=prompt,
                temperature=0.7,
                max_tokens=2048,
                extra_body={"thinking_budget": -1},
            )
            return ContentPackage.from_dict(payload)  # type: ignore[arg-type]
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("NVIDIA prompt generation failed.")


def _generate_package_with_gemini(settings: Settings, *, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
    keys = _gemini_key_pool(settings)
    if not keys:
        raise ValueError("GEMINI_API_KEY is required")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
    prompt = _daily_package_prompt(day, avoid_topics)
    last_error: Exception | None = None
    for api_key in keys:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            return ContentPackage.from_dict(_extract_json_object(response.text or ""))  # type: ignore[arg-type]
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("Gemini prompt generation failed.")


def _generate_package_with_local_llm(settings: Settings, *, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
    prompt = _daily_package_prompt(day, avoid_topics)
    client = _build_openai_compatible_client(api_key="local", base_url=settings.local_llm_url)
    payload = _chat_json_completion(
        client=client,
        model=settings.local_llm_model,
        prompt=prompt,
        temperature=0.7,
        max_tokens=2048,
    )
    return ContentPackage.from_dict(payload)  # type: ignore[arg-type]


def _generate_long_form_with_openai(
    settings: Settings,
    package: ContentPackage,
    target_minutes: int,
) -> LongFormVideoScript:
    keys = _openai_key_pool(settings)
    if not keys:
        raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required")
    prompt = _long_form_prompt(package, target_minutes)
    last_error: Exception | None = None
    minimum_seconds = 180
    maximum_seconds = 300
    for api_key in keys:
        try:
            response = _build_openai_client(api_key).responses.create(
                model=settings.openai_model,
                instructions=(
                    f"{EDITORIAL_STYLE} Write a narrated YouTube explainer. The finished video "
                    f"should target approximately {target_minutes} minutes and must run between "
                    f"{minimum_seconds} and {maximum_seconds} seconds. Use practical, original "
                    "teaching language and do not invent evidence."
                ),
                input=prompt,
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
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI long-form prompt generation failed.")


def _generate_long_form_with_nvidia(
    settings: Settings,
    package: ContentPackage,
    target_minutes: int,
) -> LongFormVideoScript:
    keys = _nvidia_key_pool(settings)
    if not keys:
        raise ValueError("NVIDIA_API_KEY is required")
    prompt = _long_form_prompt(package, target_minutes)
    last_error: Exception | None = None
    minimum_seconds = 180
    maximum_seconds = 300
    for api_key in keys:
        try:
            client = _build_openai_compatible_client(
                api_key=api_key,
                base_url="https://integrate.api.nvidia.com/v1",
            )
            payload = _chat_json_completion(
                client=client,
                model=_nvidia_text_model(settings),
                prompt=prompt,
                temperature=0.7,
                max_tokens=4096,
                extra_body={"thinking_budget": -1},
            )
            script = LongFormVideoScript.from_dict(payload)  # type: ignore[arg-type]
            return _fit_long_form_duration(script, minimum_seconds, maximum_seconds)
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("NVIDIA long-form prompt generation failed.")


def _generate_long_form_with_gemini(
    settings: Settings,
    package: ContentPackage,
    target_minutes: int,
) -> LongFormVideoScript:
    keys = _gemini_key_pool(settings)
    if not keys:
        raise ValueError("GEMINI_API_KEY is required")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
    prompt = _long_form_prompt(package, target_minutes)
    minimum_seconds = 180
    maximum_seconds = 300
    last_error: Exception | None = None
    for api_key in keys:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            script = LongFormVideoScript.from_dict(_extract_json_object(response.text or ""))  # type: ignore[arg-type]
            return _fit_long_form_duration(script, minimum_seconds, maximum_seconds)
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("Gemini long-form prompt generation failed.")


def _generate_long_form_with_local_llm(
    settings: Settings,
    package: ContentPackage,
    target_minutes: int,
) -> LongFormVideoScript:
    prompt = _long_form_prompt(package, target_minutes)
    client = _build_openai_compatible_client(api_key="local", base_url=settings.local_llm_url)
    payload = _chat_json_completion(
        client=client,
        model=settings.local_llm_model,
        prompt=prompt,
        temperature=0.7,
        max_tokens=4096,
    )
    minimum_seconds = 180
    maximum_seconds = 300
    script = LongFormVideoScript.from_dict(payload)  # type: ignore[arg-type]
    return _fit_long_form_duration(script, minimum_seconds, maximum_seconds)


@dataclass(frozen=True)
class ImageStylePack:
    topic: str
    topic_prompt: str
    storyboard_prompts: list[dict[str, str]]
    thumbnail_prompt: str
    notes: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_IMAGE_BRAND_REPLACEMENTS = (
    ("Jira", "project dashboard"),
    ("jira", "project dashboard"),
    ("Confluence", "project knowledge board"),
    ("confluence", "project knowledge board"),
    ("Trello", "task board"),
    ("trello", "task board"),
    ("Slack", "team chat workspace"),
    ("slack", "team chat workspace"),
    ("Asana", "project tracker"),
    ("asana", "project tracker"),
    ("Notion", "workspace page"),
    ("notion", "workspace page"),
)


def _sanitize_image_prompt_text(value: str) -> str:
    sanitized = value
    for source, replacement in _IMAGE_BRAND_REPLACEMENTS:
        sanitized = sanitized.replace(source, replacement)
    return sanitized


def sanitize_image_prompt_text(value: str) -> str:
    return _sanitize_image_prompt_text(value)


class PromptProvider(Protocol):
    def generate(self, day: str, avoid_topics: list[str] | None = None) -> ContentPackage: ...


def build_cinematic_image_prompt(
    topic: str,
    subject: str = "",
    audience: str = "professional audiences",
    style_name: str = "3D Claymation / Pixar",
) -> str:
    topic = _sanitize_image_prompt_text(topic)
    subject = _sanitize_image_prompt_text(subject)
    
    # Map ambiguous motor bike terms to motorcycle to avoid bicycle confusion
    for old_term in ["motor bike", "moter bike", "moterbike", "motorbike", "motor cycle"]:
        topic = topic.replace(old_term, "motorcycle").replace(old_term.capitalize(), "Motorcycle")
        subject = subject.replace(old_term, "motorcycle").replace(old_term.capitalize(), "Motorcycle")
        
    focus = f" about {subject}" if subject else ""
    
    if style_name == "None (Raw Prompt)":
        return f"{topic}{focus}".strip()

    if style_name == "Photorealistic":
        text_to_check = (topic + " " + subject).lower()
        is_nature = any(word in text_to_check for word in [
            "nature", "mountain", "river", "forest", "valleys", "waterfall", "landscape", "scenery", "sky", "desert", "sea", "ocean", "sunset", "sunrise",
            "tree", "trees", "road", "street", "path", "highway", "trail", "park", "garden", "field", "meadow", "grass", "outdoor", "outdoors"
        ])
        is_human = any(word in text_to_check for word in [
            "human", "person", "man", "woman", "girl", "boy", "vendor", "artist", "shepherd", "elder", "character", "face", "portrait"
        ])
        is_robot = any(word in text_to_check for word in [
            "robot", "robotic", "android", "cyborg", "machine", "mechanical", "automation", "drone", "cyberpunk"
        ])
        is_old = any(word in text_to_check for word in [
            "old", "vintage", "classic", "antique", "retro", "beetle car", "historical"
        ])
        is_new = any(word in text_to_check for word in [
            "new", "modern", "futuristic", "smart city", "skyscraper", "hologram", "holographic", "cyber", "neon"
        ])

        # Specific outdoor action/lifestyle shot condition (combination of human and nature/outdoor environment keywords)
        is_outdoor_action = is_human and (is_nature or any(word in text_to_check for word in [
            "road", "street", "path", "highway", "trail", "bike", "bicycle", "riding", "ride", "running", "walking", "park", "garden", "outdoor", "outdoors", "trees", "forest"
        ]))
        is_front_facing = any(phrase in text_to_check for phrase in ["towards us", "towards the camera", "coming towards", "facing the camera", "front view", "facing us"])

        if is_outdoor_action:
            is_motorcycle = "motorcycle" in text_to_check
            direction_detail = (
                "The subject's face is clearly visible looking forward, facing the camera directly, front of torso and body facing the viewer, "
                "with correct front-facing anatomy (arms and hands on the handlebars with chest and face facing us, not showing the back of the head or hair draped over the face). "
                if is_front_facing else ""
            )
            vehicle_detail = (
                "The vehicle is a real motorized motorcycle with an engine, fuel tank, and exhaust pipes, with absolutely no bicycle pedals or bicycle frames. "
                if is_motorcycle else ""
            )
            photorealistic_style = (
                f"Style: Professional outdoor lifestyle and action photograph, realistic natural lighting, "
                f"natural dappled sunlight filtering through the lush green leaves of realistic, organic trees, "
                f"lifelike tree bark textures and authentic organic foliage, shot on Sony Alpha 7 IV, 35mm lens, f/4 aperture to keep both the "
                f"subject and the beautiful surrounding landscape in sharp focus, Kodak Portra 400 film emulation for warm skin tones and natural colors, "
                f"micro-surface textures, {direction_detail}{vehicle_detail}clean composition, 8k resolution, "
                f"no text, no logos."
            )
        elif is_human:
            photorealistic_style = (
                "Style: High-fidelity close-up portrait photograph, soft dramatic Rembrandt studio lighting, "
                "gentle depth of field with beautiful background bokeh, shot on Sony Alpha 7R V with an 85mm prime portrait lens at f/1.4 aperture, "
                "sharp focus on eyes, realistic micro-surface skin textures with visible pores, soft subsurface scattering for skin realism, "
                "authentic facial expression, Kodak Portra 160 color science, rich color grading, masterclass portraiture, no text, no logos."
            )
        elif is_nature:
            photorealistic_style = (
                "Style: Breathtaking landscape photograph, shot on medium format Fujifilm GFX 100S, 24mm wide-angle lens, f/11 aperture for edge-to-edge sharpness, "
                "crisp focus, vibrant colors, golden hour morning light hitting misty valleys, nature documentary photography style, "
                "highly detailed textures of moss, rocks, water droplets, and foliage, natural light with realistic ray-traced shadows, "
                "clean composition, 8k resolution, no text, no logos."
            )
        elif is_robot:
            photorealistic_style = (
                "Style: High-end cinematic product shot, detailed mechanical joints, polished metal surfaces, "
                "soft reflections and glowing LED indicators, cyberpunk retro-futuristic design, moody atmospheric lighting "
                "with orange and cyan rim light, shot with 50mm macro lens at f/2.8, realistic material properties, brushed metal texture, "
                "subtle ambient occlusion, clean composition, 8k resolution, no text, no logos."
            )
        elif is_old:
            photorealistic_style = (
                "Style: Warm, nostalgic cinematic photograph, shot on vintage 35mm film camera, classic grain, "
                "Kodak Gold 200 film emulation, warm color grading (sepia and golden hues), soft focus around borders, gentle late-afternoon sunlight, "
                "authentic textures, nostalgic storytelling mood, classic masterpiece photography, no text, no logos."
            )
        elif is_new:
            photorealistic_style = (
                "Style: Sleek, futuristic wide-angle photograph, clean modern lines, minimalist architecture, "
                "glowing neon cyan and magenta lines, clean glass reflections and realistic light refraction, high-tech smart city aesthetic, crisp focus, "
                "shot on 24mm wide-angle lens, high-tech cinematic composition, 8k resolution, no text, no logos."
            )
        else:
            photorealistic_style = (
                "Style: High-end photorealistic landscape photograph, clean composition, crisp focus, natural lighting, "
                "shot on 35mm lens, masterpiece, 8k resolution, realistic textures and details, no text, no logos."
            )
        return f"A vivid photorealistic photograph of {topic}{focus}. {photorealistic_style} Design it like a premium hero image with generous negative space for overlays."

    if style_name == "Flat Vector":
        vector_style = (
            "Style: Clean flat vector illustration, minimalist design, elegant colors, clean paths, "
            "modern corporate design style, SVG vector aesthetic, flat color fills, no text, no logos."
        )
        return f"A clean flat vector illustration of {topic}{focus}. {vector_style} Design it like a premium hero image with generous negative space for overlays."

    if style_name == "Cinematic Anime":
        anime_style = (
            "Style: Cinematic anime digital illustration, hand-drawn detailing, soft atmospheric glow, "
            "beautiful anime scenery, vibrant colors, masterpiece, no text, no logos."
        )
        return f"A beautiful cinematic anime digital illustration of {topic}{focus}. {anime_style} Design it like a premium hero image with generous negative space for overlays."

    # Default to 3D Claymation / Pixar category-based behavior
    text_to_check = (topic + " " + subject).lower()
    is_kids = any(word in text_to_check for word in [
        "kids", "kid", "child", "baby", "cartoon", "nursery", "rhyme", 
        "toddler", "toy", "alphabet", "abcd"
    ])
    is_robot = any(word in text_to_check for word in [
        "robot", "robotic", "android", "cyborg", "machine", "mechanical", "automation", "drone", "cyberpunk"
    ])
    
    if is_kids:
        kids_style = (
            "Style: Premium 3D cute cartoon animation style with warm, expressive, friendly characters. "
            "Shapes and curves are beautifully rounded, with soft playful textures. "
            "Features happy children playing, learning, or interacting in a bright, colorful, and magical environment. "
            "Color Palette: Saturated, happy, and vibrant colors (bright yellow, sky blue, warm pastel highlights). "
            "Lighting: Bright cheerful volumetric lighting, gentle depth of field, sharp focus, masterpiece, 8k resolution. "
            "Absolutely no text inside the image. Reserve a clean typography-safe area for text overlays."
        )
        return (
            f"A vivid supporting illustration for {topic}{focus}, optimized for children and parents. "
            f"{kids_style} "
            "Design it like a premium hero image with generous negative space for overlays."
        )
        
    if is_robot:
        robot_style = (
            "Style: Playful and charming character illustration in a premium 3D claymation style. "
            "Beautifully rounded shapes, soft plasticine clay textures with subtle fingerprint details, "
            "bright cheerful volumetric studio lighting, colorful miniature diorama background, "
            "whimsical stop-motion animation aesthetic, 3D render, masterpiece, high details, no text, no logos."
        )
        return (
            f"A vivid supporting illustration of {topic}{focus} in claymation style. "
            f"{robot_style} "
            "Design it like a premium hero image with generous negative space for overlays."
        )
        
    is_agile_or_it = any(word in text_to_check for word in [
        "agile", "scrum", "jira", "sprint", "project manager", "project management", 
        "software", "developer", "delivery", "workflow", "confluence", "trello", "asana"
    ])
    
    if is_agile_or_it:
        return (
            f"A vivid supporting illustration for {topic}{focus}, optimized for {audience}. "
            f"{CINEMATIC_IMAGE_STYLE} "
            "Design it like a premium hero image with generous negative space for overlays."
        )
        
    is_cooking = any(word in text_to_check for word in ["cook", "kitchen", "chef", "food", "dish", "recipe"])
    if is_cooking:
        cooking_style = (
            "Style: Warm 3D claymation illustration style, friendly characters, organic shapes and textured surfaces. "
            "Features a friendly chef cooking or presenting food in a cozy, rustic kitchen. "
            "Color Palette: Rich cozy warm tones (terracotta, soft gold, warm greens and blues). "
            "Lighting: Natural warm lighting, cozy atmosphere, soft shadows, inviting depth of field. "
            "Absolutely no text inside the image. Reserve a clean typography-safe area for text overlays."
        )
        return (
            f"A vivid supporting illustration for {topic}{focus}, optimized for food lovers and chefs. "
            f"{cooking_style} "
            "Design it like a premium hero image with generous negative space for overlays."
        )
        
    general_style = (
        "Style: Warm 3D claymation illustration style, friendly characters, organic shapes and textured surfaces. "
        "Features a friendly character in a cozy, welcoming workspace or creative environment. "
        "Color Palette: Rich cozy warm tones (terracotta, soft gold, warm greens and blues). "
        "Lighting: Natural warm lighting, cozy atmosphere, soft shadows, inviting depth of field. "
        "Absolutely no text inside the image. Reserve a clean typography-safe area for text overlays."
    )
    return (
        f"A vivid supporting illustration for {topic}{focus}, optimized for general audiences. "
        f"{general_style} "
        "Design it like a premium hero image with generous negative space for overlays."
    )


def build_thumbnail_prompt(topic: str, subject: str = "", audience: str = "YouTube viewers") -> str:
    topic = _sanitize_image_prompt_text(topic)
    subject = _sanitize_image_prompt_text(subject)
    focus = f" featuring {subject}" if subject else ""
    return (
        f"A striking thumbnail concept for {topic}{focus}, designed for {audience}. "
        f"{THUMBNAIL_IMAGE_STYLE} "
        "Make the message obvious at a glance and leave a safe area for any later text overlay."
    )


STORYBOARD_STYLES = {
    "3D Claymation / Pixar": (
        "Use the same vibrant, cinematic 3D visual language across the entire sequence: "
        "premium animation, rounded shapes, soft glow, vibrant color contrast, smooth "
        "depth, and a clean scene composition suitable for a polished explainer video."
    ),
    "Photorealistic": (
        "Use a consistent, high-end photorealistic style across the entire sequence: "
        "clean composition, crisp focus, natural lighting, shot on 35mm lens, realistic textures and details, "
        "masterpiece, 8k resolution, suitable for a professional documentary look."
    ),
    "Flat Vector": (
        "Use a consistent, clean flat vector illustration style across the entire sequence: "
        "minimalist graphic design, elegant colors, clean paths, SVG vector aesthetic, flat color fills, "
        "suitable for a modern professional corporate presentation."
    ),
    "Cinematic Anime": (
        "Use a consistent, cinematic anime digital illustration style across the entire sequence: "
        "hand-drawn detailing, soft atmospheric glow, beautiful painted scenery, vibrant colors, "
        "masterpiece, suitable for a premium animated feature look."
    ),
    "None (Raw Prompt)": ""
}

def build_storyboard_prompts(
    topic: str,
    *,
    scene_count: int = 35,
    style_name: str = "3D Claymation / Pixar",
) -> list[dict[str, str]]:
    topic = _sanitize_image_prompt_text(topic)
    
    text_to_check = topic.lower()
    is_kids = any(word in text_to_check for word in ["kid", "child", "baby", "cartoon", "play", "school", "song", "rhyme", "nursery", "studying"])
    is_agile_or_it = any(word in text_to_check for word in [
        "agile", "scrum", "jira", "sprint", "project manager", "project management", 
        "software", "developer", "delivery", "workflow", "confluence", "trello", "asana"
    ])
    
    if is_kids:
        scene_templates = [
            "Intro: a vibrant opening frame introducing {topic} with bright happy colors and a friendly cartoon atmosphere.",
            "Story scene: happy characters exploring and learning about {topic}.",
            "Activity scene: fun and interactive play related to {topic}.",
            "Song theme: musical notes floating in the air while characters sing about {topic}.",
            "Magical moment: a beautiful, bright cartoon fantasy world of {topic}.",
            "Educational concept: a clear, friendly visual teaching the letters or numbers of {topic}.",
            "Dance scene: happy animals and kids dancing and enjoying {topic}.",
            "Celebration: a party with balloons, cake, and confetti themed around {topic}.",
            "Learning moment: characters happily discovering a secret about {topic}.",
            "Magical helper: a friendly little fairy or cute animal assisting with {topic}.",
            "Journey: characters walking along a colorful rainbow road related to {topic}.",
            "Friendly game: a simple, fun puzzle or game about {topic}.",
            "Nature scene: a beautiful garden or forest themed around {topic} with cute butterflies.",
            "Bedtime/Night: a calm, starry night sky with a smiling crescent moon themed around {topic}.",
            "Morning/Sunny day: a bright smiling sun shining over a playground for {topic}.",
            "Midpoint recap: split-screen showing different fun ways to play with {topic}.",
            "Human-animal friendship: a kid and a cute puppy high-five while learning {topic}.",
            "Playful learning: colorful toy blocks spelling out words for {topic}.",
            "Adventure: a small sailboat sailing on a beautiful sparkling blue lake for {topic}.",
            "Treehouse: a cozy wooden treehouse decorated with banners for {topic}.",
            "Fantasy sky: floating islands and cotton-candy clouds themed around {topic}.",
            "Underwater magic: friendly smiling fish and glowing coral reefs related to {topic}.",
            "Friendly monsters: cute, fuzzy, non-scary cartoon monsters playing with {topic}.",
            "Toybox: a giant overflowing box of colorful toys and plushies for {topic}.",
            "Art class: splatters of paint and colorful drawing boards themed around {topic}.",
            "Musical band: kids playing miniature instruments like drums and xylophone for {topic}.",
            "Happy ending: characters waving with bright smiles after mastering {topic}.",
            "Starlight: a cozy bedroom with glowing stars on the ceiling themed around {topic}.",
            "Picnic: a red-and-white checkered blanket with delicious fruits and juice for {topic}.",
            "Balloon ride: a giant colorful hot air balloon floating over a green valley for {topic}.",
            "Summary: a wide polished cartoon overview that brings all {topic} ideas together.",
            "Call to action: a clean final frame leaving space for a title or CTA about {topic}.",
            "Outro card: a polished engagement frame for suggestions or next steps on {topic}.",
            "Social follow-up: floating engagement icons themed around {topic}.",
            "Final end card: a premium outro scene with bold subscribe/like/bell energy for {topic}.",
        ]
    elif is_agile_or_it:
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
    else:
        scene_templates = [
            "Intro: a vibrant opening frame introducing {topic} with a clean, cinematic studio atmosphere.",
            "Traditional setup: a grounded, realistic scene showing the classic approach to {topic}.",
            "Core idea: a clean visual that explains the heart of {topic}.",
            "Challenge: a visually obvious problem or messy situation related to {topic}.",
            "Modern approach: a clean, elegant solution beginning to help with {topic}.",
            "Transformation: traditional methods dissolving into a cleaner modern workflow for {topic}.",
            "Efficiency: clean, precise layout showing how {topic} works smoother.",
            "Visual details: close-up shot highlighting the fine details and textures of {topic}.",
            "Collaboration: people working together in a beautifully designed setting for {topic}.",
            "Helper elements: neat, clean tools and assets supporting the main process of {topic}.",
            "Progression: a structured path showing the next steps in {topic}.",
            "Obstacles cleared: a messy situation being organized to reveal progress in {topic}.",
            "Ongoing process: a clean circular cycle representing continuous improvement of {topic}.",
            "Resource optimization: a balanced, polished visual showing smarter use of time in {topic}.",
            "Quality check: a detailed look verifying the final result of {topic}.",
            "Midpoint recap: split-screen comparison of different approaches to {topic}.",
            "Partnership: two elements or people collaborating successfully on {topic}.",
            "Flexibility: smooth flow and clean composition adapting to new demands for {topic}.",
            "Data and details: organized elements falling into a perfect structure for {topic}.",
            "Strategic setup: a solid design becoming a stable system for {topic}.",
            "Growth: a wide-scale view showing the impact of {topic} expanding.",
            "Support structure: secure, reliable foundation supporting the {topic} environment.",
            "Real-time progress: a clear, clean display showing live updates for {topic}.",
            "Clutter removed: clean and tidy space focused entirely on {topic}.",
            "Framework: modular pieces coming together into a scalable system for {topic}.",
            "Protection: a secure environment protecting the {topic} setup.",
            "Feedback: a clear cycle of reflection and refinement for {topic}.",
            "Success moment: a peak shot showing {topic} mastered and completed perfectly.",
            "Next generation: a spark or seed growing into the future of {topic}.",
            "Peak state: a perfectly optimized and clean environment for {topic}.",
            "Summary: a wide polished overview that brings all {topic} ideas together.",
            "Call to action: a clean final frame leaving space for a title or CTA about {topic}.",
            "Outro card: a polished engagement frame for suggestions or next steps on {topic}.",
            "Social follow-up: floating engagement icons themed around {topic}.",
            "Final end card: a premium outro scene with bold subscribe/like/bell energy for {topic}.",
        ]
    
    style_suffix = STORYBOARD_STYLES.get(style_name, STORYBOARD_STYLES["3D Claymation / Pixar"])
    prompts: list[dict[str, str]] = []
    for index in range(scene_count):
        template = scene_templates[index % len(scene_templates)]
        prompts.append(
            {
                "scene_number": index + 1,
                "segment": f"Scene {index + 1:02d}",
                "prompt": (
                    template.replace("{topic}", topic)
                    + (f" {style_suffix}" if style_suffix else "")
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
    style_name: str = "3D Claymation / Pixar",
) -> ImageStylePack:
    return ImageStylePack(
        topic=topic,
        topic_prompt=build_cinematic_image_prompt(topic, subject, audience, style_name=style_name),
        storyboard_prompts=build_storyboard_prompts(topic, scene_count=scene_count, style_name=style_name),
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
    for provider in ("openai", "nvidia", "gemini", "local"):
        try:
            if provider == "openai":
                return _generate_long_form_with_openai(settings, package, target_minutes)
            if provider == "nvidia":
                return _generate_long_form_with_nvidia(settings, package, target_minutes)
            if provider == "gemini":
                return _generate_long_form_with_gemini(settings, package, target_minutes)
            return _generate_long_form_with_local_llm(settings, package, target_minutes)
        except Exception:
            continue
    raise RuntimeError("Prompt generation failed across OpenAI, NVIDIA, Gemini, and Local LLM.")


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
        self.settings = settings

    def generate(self, day: str, avoid_topics: list[str] | None = None) -> ContentPackage:
        for provider in ("openai", "nvidia", "gemini", "local"):
            try:
                if provider == "openai":
                    return _generate_package_with_openai(self.settings, day=day, avoid_topics=avoid_topics)
                if provider == "nvidia":
                    return _generate_package_with_nvidia(self.settings, day=day, avoid_topics=avoid_topics)
                if provider == "gemini":
                    return _generate_package_with_gemini(self.settings, day=day, avoid_topics=avoid_topics)
                return _generate_package_with_local_llm(self.settings, day=day, avoid_topics=avoid_topics)
            except Exception:
                continue
        raise RuntimeError("Prompt generation failed across OpenAI, NVIDIA, Gemini, and Local LLM.")


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
