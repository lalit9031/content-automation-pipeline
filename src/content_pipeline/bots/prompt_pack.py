from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile


@dataclass(frozen=True)
class PromptSlide:
    slide_number: int
    title: str
    slide_type: str
    on_screen_text: str
    image_prompt: str
    speaker_notes: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromptPack:
    topic: str
    day: str
    slug: str
    full_title: str
    short_title: str
    full_slides: list[PromptSlide]
    short_slides: list[PromptSlide]

    def as_dict(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "day": self.day,
            "slug": self.slug,
            "full_title": self.full_title,
            "short_title": self.short_title,
            "full_slides": [slide.as_dict() for slide in self.full_slides],
            "short_slides": [slide.as_dict() for slide in self.short_slides],
        }


def create_prompt_pack(
    topic: str,
    day: str | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    day = day or date.today().isoformat()
    output_dir = output_dir or Path("output")
    slug = _slugify(topic)
    root = output_dir / "prompt_packs" / day / slug
    root.mkdir(parents=True, exist_ok=True)

    pack = _prompt_pack(topic=topic, day=day, slug=slug)
    manifest_path = root / "prompt_pack.json"
    manifest_path.write_text(json.dumps(pack.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    full_doc = root / f"{slug}_youtube_full_video.docx"
    short_doc = root / f"{slug}_shorts.docx"
    _write_docx(
        full_doc,
        title=f"{topic} - YouTube Full Video Prompt Pack",
        subtitle="Manual-first image brief for full video slides",
        slides=pack.full_slides,
        topic=topic,
        day=day,
        slug=slug,
    )
    _write_docx(
        short_doc,
        title=f"{topic} - Shorts Prompt Pack",
        subtitle="Manual-first image brief for shorts",
        slides=pack.short_slides,
        topic=topic,
        day=day,
        slug=slug,
    )

    prompt_md = root / "prompt_pack.md"
    prompt_md.write_text(_prompt_markdown(pack), encoding="utf-8")
    return [manifest_path, full_doc, short_doc, prompt_md]


def prompt_pack_documents(topic: str, day: str | None = None, output_dir: Path | None = None) -> list[Path]:
    return create_prompt_pack(topic, day=day, output_dir=output_dir)


def _prompt_pack(topic: str, day: str, slug: str) -> PromptPack:
    full_slides = [
        PromptSlide(
            1,
            "Title Slide",
            "motion_video",
            f"Why Project Managers Must Master Prompt Engineering to Survive the AI Revolution",
            _hero_prompt(topic),
            "Open with a cinematic control room and the core thesis. Make the AI presence feel larger than the PM.",
        ),
        PromptSlide(
            2,
            "Old vs New PM",
            "static_image",
            "Old PM vs New PM",
            _comparison_prompt(topic),
            "Split-screen comparison: task chasing versus algorithmic orchestration.",
        ),
        PromptSlide(
            3,
            "Strategy Gap",
            "motion_video",
            "Strategy ≠ Execution",
            _bridge_prompt(topic),
            "Show the gap between strategy and execution, then bridge it with prompt engineering.",
        ),
        PromptSlide(
            4,
            "Junior LLM",
            "static_image",
            "Treat the LLM like a junior teammate",
            _junior_prompt(topic),
            "Make the model feel literal-minded, brilliant, and dependent on clear instruction.",
        ),
        PromptSlide(
            5,
            "Prompt Skill",
            "motion_video",
            "Prompt engineering is a PM core skill",
            _skill_prompt(topic),
            "Use typed text and simple motion to show bad prompt versus good prompt.",
        ),
        PromptSlide(
            6,
            "Orchestration",
            "static_image",
            "Task tracking -> algorithmic orchestration",
            _orchestration_prompt(topic),
            "Use a structured diagram showing stakeholder demand, PM prompt, and AI output.",
        ),
        PromptSlide(
            7,
            "Human Layer",
            "motion_video",
            "AI prepares, humans decide",
            _human_layer_prompt(topic),
            "Emphasize judgment, empathy, and final sign-off as the essential human layer.",
        ),
        PromptSlide(
            8,
            "CTA",
            "static_image",
            "Master prompting. Stay irreplaceable.",
            _cta_prompt(topic),
            "Close with a 30-day challenge and a clear call to action.",
        ),
    ]
    short_slides = [
        PromptSlide(
            1,
            "Hook",
            "motion_video",
            "Prompt engineering will change how PMs work",
            _short_hook_prompt(topic),
            "Open strong with one idea: PMs who can brief AI will move faster.",
        ),
        PromptSlide(
            2,
            "Gap",
            "static_image",
            "High-level strategy, low-level execution",
            _short_gap_prompt(topic),
            "Show the gap with a bridge or connector graphic.",
        ),
        PromptSlide(
            3,
            "LLM",
            "static_image",
            "LLMs are literal teammates",
            _short_llm_prompt(topic),
            "A junior teammate metaphor works well here.",
        ),
        PromptSlide(
            4,
            "Prompt",
            "motion_video",
            "Bad prompt vs good prompt",
            _short_prompt_prompt(topic),
            "Show a weak prompt transforming into a structured prompt.",
        ),
        PromptSlide(
            5,
            "CTA",
            "static_image",
            "Start prompting today",
            _short_cta_prompt(topic),
            "End with a simple action challenge.",
        ),
    ]
    return PromptPack(
        topic=topic,
        day=day,
        slug=slug,
        full_title=f"{topic} - YouTube Full Video Prompt Pack",
        short_title=f"{topic} - Shorts Prompt Pack",
        full_slides=full_slides,
        short_slides=short_slides,
    )


def _hero_prompt(topic: str) -> str:
    return (
        "Hero scene, bold YouTube learning-video cover image, premium presentation design, dark cinematic background, "
        "ultra high contrast, strong focal subject, dramatic volumetric lighting, futuristic AI atmosphere. "
        f"Topic: {topic}. "
        'Renderer-only headline: "WHY PROJECT MANAGERS MUST MASTER PROMPT ENGINEERING". '
        'Renderer-only hook: "From task tracker to algorithmic orchestrator". '
        "Visualize a confident project manager facing a giant AI hologram, with glowing data streams, a command center, "
        "and symbolic metaphors for strategy, execution, and AI orchestration. "
        "Large clean typography-safe space on the left, hero visual on the right. "
        "No logos, no watermark, no readable UI, no clutter."
    )


def _comparison_prompt(topic: str) -> str:
    return (
        "Premium split-screen educational image, dark cinematic background, high contrast, executive training style. "
        f"Topic: {topic}. "
        'Renderer-only headline: "OLD PM VS NEW PM". '
        'Renderer-only hook: "Task tracking, chasing updates, manual synthesis vs algorithmic orchestration". '
        "Left side: stressed PM with sticky notes and red flags. Right side: calm PM talking to an AI avatar. "
        "Make the contrast obvious and polished. No logos, no watermark, no readable UI."
    )


def _bridge_prompt(topic: str) -> str:
    return (
        "Motion-friendly abstract illustration, futuristic strategy-to-execution bridge, dark blue and orange lighting. "
        f"Topic: {topic}. "
        'Renderer-only headline: "STRATEGY ≠ EXECUTION". '
        'Renderer-only hook: "Prompt engineering closes the gap". '
        "Show high-level strategy floating above granular execution, then a glowing bridge icon connecting them. "
        "Use abstract clouds, ticket cards, and a prompt symbol. Clean, cinematic, presentation-ready."
    )


def _junior_prompt(topic: str) -> str:
    return (
        "Premium metaphor image, a brilliant but literal-minded junior AI teammate, dark cinematic lighting, glassy glow. "
        f"Topic: {topic}. "
        'Renderer-only headline: "YOUR MOST JUNIOR TEAM MEMBER". '
        'Renderer-only hook: "Treat the LLM like a literal-minded intern". '
        "Show a robot or hologram with a junior-intern badge, holding a manual, with visible symbols for no context inference, "
        "no assumption correction, and garbage-in-garbage-out. No logos, no watermark, no clutter."
    )


def _skill_prompt(topic: str) -> str:
    return (
        "Kinetic typography frame, dark cinematic background, subtle AI glow, editorial learning-video style. "
        f"Topic: {topic}. "
        'Renderer-only headline: "PROMPT ENGINEERING IS A PM CORE SKILL". '
        'Renderer-only hook: "Clarity under pressure is the new advantage". '
        "Show bad prompt vs good prompt as large clean text panels, with a typing cursor, structured output cards, and a transformation arrow."
    )


def _orchestration_prompt(topic: str) -> str:
    return (
        "Structured diagram slide, premium enterprise learning style, dark background, cyan and orange accents. "
        f"Topic: {topic}. "
        'Renderer-only headline: "TASK TRACKING -> ALGORITHMIC ORCHESTRATION". '
        'Renderer-only hook: "Stakeholder demand -> PM prompt -> AI output". '
        "Show three columns: vague stakeholder demand, structured PM prompt, granular AI output. Keep it clean, readable, and diagram-like."
    )


def _human_layer_prompt(topic: str) -> str:
    return (
        "Motion-style cinematic shield scene, glowing human layer filtering stakeholder chaos into clean prompts, dark futuristic atmosphere. "
        f"Topic: {topic}. "
        'Renderer-only headline: "THE HUMAN LAYER". '
        'Renderer-only hook: "AI prepares. Humans decide." '
        "Show a shield, validation gate, and subtle political/strategic reality cues. Keep it premium, high contrast, and minimal."
    )


def _cta_prompt(topic: str) -> str:
    return (
        "Final course engagement slide, premium executive learning design, dark blue grid background, orange and white typography, clean spacious composition. "
        f"Topic: {topic}. "
        'Renderer-only headline: "MASTER PROMPTING. STAY IRREPLACEABLE." '
        'Renderer-only hook: "Start a 30-day prompt challenge". '
        "Show checklist icons, a like icon, a subscribe icon, and a notification bell icon. Calm, clean, and confident."
    )


def _short_hook_prompt(topic: str) -> str:
    return (
        "Hero scene, bold learning-video thumbnail, premium presentation design, dark cinematic background, AI atmosphere. "
        f"Topic: {topic}. "
        'Renderer-only headline: "PROMPT ENGINEERING CHANGES PM WORK". '
        'Renderer-only hook: "The PM AI question". '
        "One PM standing in front of a giant AI presence, high contrast, blue and orange glow."
    )


def _short_gap_prompt(topic: str) -> str:
    return (
        "Split diagram, strategy to execution bridge, dark futuristic learning slide. "
        f"Topic: {topic}. "
        'Renderer-only headline: "STRATEGY TO EXECUTION". '
        'Renderer-only hook: "Bridging ambiguity". '
        "Show a gap, then a prompt bridge linking strategy and action."
    )


def _short_llm_prompt(topic: str) -> str:
    return (
        "Metaphor slide, junior AI teammate, dark cinematic learning design. "
        f"Topic: {topic}. "
        'Renderer-only headline: "THE LLM IS LITERAL". '
        'Renderer-only hook: "Write clearly, get better outputs". '
        "Use a robot intern or AI assistant visual with simple symbolic badges."
    )


def _short_prompt_prompt(topic: str) -> str:
    return (
        "Typing effect slide, good prompt vs bad prompt, modern educational thumbnail style. "
        f"Topic: {topic}. "
        'Renderer-only headline: "BAD PROMPT -> GOOD PROMPT". '
        'Renderer-only hook: "Structure beats vague asks". '
        "Show a messy prompt transforming into a structured one with role, format, constraints, and examples."
    )


def _short_cta_prompt(topic: str) -> str:
    return (
        "Clean CTA slide, dark grid background, executive learning style. "
        f"Topic: {topic}. "
        'Renderer-only headline: "START TODAY". '
        'Renderer-only hook: "One prompt, one workflow". '
        "Show a checklist and a confident closing message."
    )


def _prompt_markdown(pack: PromptPack) -> str:
    lines = [
        f"# {pack.topic}",
        "",
        f"- Date: {pack.day}",
        f"- Folder: {pack.slug}",
        "",
        "## Full Video Slides",
    ]
    lines.extend(_slide_markdown(pack.full_slides))
    lines.append("")
    lines.append("## Shorts Slides")
    lines.extend(_slide_markdown(pack.short_slides))
    return "\n".join(lines).strip() + "\n"


def _slide_markdown(slides: Iterable[PromptSlide]) -> list[str]:
    rows: list[str] = []
    for slide in slides:
        rows.extend(
            [
                f"### Slide {slide.slide_number}: {slide.title}",
                f"- Type: {slide.slide_type}",
                f"- On-screen text: {slide.on_screen_text}",
                f"- Speaker notes: {slide.speaker_notes}",
                "",
                "Prompt:",
                slide.image_prompt,
                "",
            ]
        )
    return rows


def _write_docx(
    path: Path,
    *,
    title: str,
    subtitle: str,
    slides: list[PromptSlide],
    topic: str,
    day: str,
    slug: str,
) -> None:
    document_xml = _build_document_xml(title, subtitle, slides, topic=topic, day=day, slug=slug)
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>
"""
    core_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:dcmitype="http://purl.org/dc/dcmitype/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Prompt Pack</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-05-29T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-05-29T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)


def _build_document_xml(
    title: str,
    subtitle: str,
    slides: list[PromptSlide],
    *,
    topic: str,
    day: str,
    slug: str,
) -> str:
    blocks = [
        _paragraph(title),
        _paragraph(subtitle),
        _paragraph(f"Topic: {topic}"),
        _paragraph(f"Date: {day}"),
        _paragraph(f"Folder: {slug}"),
        _paragraph(""),
    ]
    blocks.extend(_slide_blocks(slides))
    body = "".join(blocks)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"""


def _slide_blocks(slides: list[PromptSlide]) -> list[str]:
    blocks: list[str] = []
    for slide in slides:
        blocks.extend(
            [
                _paragraph(f"Slide {slide.slide_number}: {slide.title}"),
                _paragraph(f"Type: {slide.slide_type}"),
                _paragraph(f"On-screen text: {slide.on_screen_text}"),
                _paragraph(f"Speaker notes: {slide.speaker_notes}"),
                _paragraph("Prompt:"),
                _paragraph(slide.image_prompt),
                _paragraph(""),
            ]
        )
    return blocks


def _paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{_xml_escape(text)}</w:t></w:r></w:p>"


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:72] or "prompt-pack"
