#!/usr/bin/env python3
"""Prompt Engineering for PMs — Educational Video Generator

Generates a full-length management educational video about why project managers
must master prompt engineering, with custom-designed slides, professional motion
graphics, smooth crossfade transitions, and SRT subtitles.

Usage:
    python scripts/prompt_engineering_video.py

Requires: ffmpeg, cairosvg, openai
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import Path


WIDTH = 1280
HEIGHT = 720
OUTPUT_DIR = Path("output/prompt_engineering_video")
FPS = 30
TRANSITION_DUR = 0.4  # Crossfade duration between slides


@dataclass(frozen=True)
class PESlide:
    text_on_screen: str
    duration: int
    narration: str
    slide_type: str


# ── Slide Definitions ──────────────────────────────────────────────────────
# Based on the presentation "Why PMs Must Master Prompt Engineering"

SLIDES = [
    PESlide(
        text_on_screen=(
            "Prompt Engineering:\nThe PM's Superpower\n\n"
            "Why mastering prompts is your\nmost important skill in 2026"
        ),
        duration=18,
        narration=(
            "Welcome. Prompt engineering is the single most important skill "
            "for project managers in the age of AI. It's not about writing questions. "
            "It's about designing inputs that produce predictable, reliable, "
            "and actionable outputs from AI systems. This video will show you why "
            "this matters and how to master it."
        ),
        slide_type="title",
    ),
    PESlide(
        text_on_screen=(
            "The Cost of Vague Prompts\n\n"
            "Vague Prompt:\n"
            "\"Summarize the meeting\"\n"
            "→ Generic, often useless output\n\n"
            "Precise Prompt:\n"
            "\"Extract 3 key decisions, 2 open questions,\n"
            "and 4 action items with owners from this\n"
            "sprint retrospective transcript\"\n"
            "→ Actionable, structured output"
        ),
        duration=55,
        narration=(
            "The difference between a vague prompt and a precise prompt is the difference "
            "between wasting thirty minutes and saving three hours. When you ask AI to "
            "\"summarize the meeting,\" you get generic paragraphs that still require you to "
            "extract the real information. But when you specify exactly what you need — "
            "three key decisions, two open questions, four action items with owners — "
            "the AI delivers structured output you can immediately use. "
            "Vague prompts cost organizations time, clarity, and trust. "
            "Precise prompts build confidence and velocity."
        ),
        slide_type="comparison",
    ),
    PESlide(
        text_on_screen=(
            "The ROI of Prompt Engineering\n\n"
            "Before: Copy-paste status reports\n"
            "→ Hours spent formatting updates\n\n"
            "After: \"Generate a weekly RAID log\n"
            "from Slack+Jira, flag blockers over\n"
            "48 hours, draft stakeholder email\n"
            "in 3 tones\"\n"
            "→ Minutes to review and approve"
        ),
        duration=50,
        narration=(
            "Let's talk about real return on investment. Before prompt engineering, a PM "
            "spends hours copying data from Jira, formatting status reports, writing "
            "stakeholder emails, and chasing updates. After mastering prompts, that same PM "
            "generates a comprehensive RAID log from Slack and Jira in seconds, flags "
            "blockers that have been open for more than 48 hours, and drafts a stakeholder "
            "email in three different tones — formal, friendly, or urgent. "
            "The PM's role shifts from data entry to decision intelligence. "
            "That is the ROI. Not automation for its own sake, but freeing human judgment "
            "to focus on what matters."
        ),
        slide_type="comparison",
    ),
    PESlide(
        text_on_screen=(
            "The Prompt Engineering Flow\n\n"
            "Plan  →  Draft  →  Test  →  Refine  →  Deploy\n\n"
            "Treat prompts like requirements:\n"
            "1. Define the output format\n"
            "2. Provide the context\n"
            "3. Set constraints and examples\n"
            "4. Iterate based on results\n"
            "5. Version-control what works"
        ),
        duration=52,
        narration=(
            "Prompt engineering follows the same cycle as project management itself. "
            "First, Plan: define what output you need, what format it should take, and "
            "what constraints apply. Second, Draft: write your prompt with role, context, "
            "and specificity. Third, Test: run the prompt and review the output critically. "
            "Fourth, Refine: adjust wording, add examples, tighten instructions. "
            "And Fifth, Deploy: save the working prompt to your library for reuse. "
            "Treat prompts like requirements documents. Define the output format upfront, "
            "provide relevant context, set clear constraints, and give examples. "
            "Then iterate based on what the AI returns. Version-control the prompts "
            "that work so your whole team benefits."
        ),
        slide_type="roadmap",
    ),
    PESlide(
        text_on_screen=(
            "Core Prompting Principles\n\n"
            "Role:      \"You are a senior PMO consultant\"\n"
            "Context:   \"We use Scrum with 2-week sprints\"\n"
            "Specificity: \"List exactly 3 risks\"\n"
            "Iterate:   \"Make it more concise\" → Refine\n\n"
            "You are not guessing.\nYou are engineering an input."
        ),
        duration=50,
        narration=(
            "Four core principles will transform how you prompt. "
            "First, Role: tell the AI who it is. \"You are a senior PMO consultant "
            "with fifteen years of delivery experience.\" This frames the entire response. "
            "Second, Context: provide the environment. \"We use Scrum with two-week sprints, "
            "our team has eight members, our main risk is vendor dependency.\" "
            "Third, Specificity: be exact. \"List exactly three risks ranked by impact.\" "
            "Not \"list some risks\" — specific numbers produce specific outputs. "
            "Fourth, Iterate: treat the first response as a draft. \"Make it more concise,\" "
            "\"Add owner names,\" \"Format as a table.\" Each refinement improves the output. "
            "You are not guessing. You are engineering an input for a predictable output."
        ),
        slide_type="principles",
    ),
    PESlide(
        text_on_screen=(
            "From Tracking to Orchestration\n\n"
            "Before:\n"
            "\"PM, what's the status?\"\n"
            "→ Copy-paste a report\n\n"
            "After:\n"
            "\"Generate weekly RAID log from\n"
            "Slack+Jira, flag blockers over 48h,\n"
            "draft stakeholder email in 3 tones\"\n"
            "→ Orchestrate, don't administrate"
        ),
        duration=48,
        narration=(
            "This is the biggest mindset shift for modern PMs. Move from tracking to "
            "orchestration. Before prompt engineering, your day is reactive. Someone asks "
            "\"what's the status?\" and you copy-paste from one tool to another. "
            "After prompt engineering, you orchestrate. You design prompts that pull "
            "information from multiple sources, synthesize it, and produce polished output. "
            "Your job becomes: design the prompt, review the output, make the decision. "
            "Not collect the data, format the data, and send the data. "
            "This is sophisticated algorithmic orchestration, and it's the new baseline "
            "for high-performing project managers."
        ),
        slide_type="dashboard",
    ),
    PESlide(
        text_on_screen=(
            "AI Generates. You Govern.\n\n"
            "Judgment:     Prioritize trade-offs AI can't value\n"
            "Alignment:    Translate business goals to prompts\n"
            "Accountability: Own outcomes, ethics, and trust\n\n"
            "We remain the essential human layer\n"
            "between ambiguous demands and precise outputs"
        ),
        duration=52,
        narration=(
            "Never forget: AI generates, but you govern. Three responsibilities stay with "
            "you as the human leader. First, Judgment: AI can list options, but it cannot "
            "navigate organizational politics, weigh stakeholder relationships, or make "
            "ethical trade-offs. That is your job. Second, Alignment: you translate "
            "business goals into precise prompts. The AI does not know your stakeholders, "
            "your risks, or your deadlines unless you tell it. Third, Accountability: "
            "when the output is wrong — and it will be sometimes — you own the outcome. "
            "You review every AI-generated deliverable before it leaves your desk. "
            "You stay accountable for ethics, data privacy, and trust. "
            "We remain the essential human layer between ambiguous demands and precise outputs."
        ),
        slide_type="governance",
    ),
    PESlide(
        text_on_screen=(
            "Survive & Thrive: 30-Day Plan\n\n"
            "Week 1 — Learn:\n"
            "Master 10 prompt patterns\n"
            "(role, chain-of-thought, few-shot)\n\n"
            "Week 2 — Build:\n"
            "Create a shared prompt library\n\n"
            "Week 3 — Practice:\n"
            "Treat AI as intern: brief, review, iterate\n\n"
            "Week 4 — Lead:\n"
            "Teach one colleague. Scale the skill."
        ),
        duration=55,
        narration=(
            "Here is your thirty-day plan to survive and thrive. "
            "Week one: Learn. Master ten fundamental prompt patterns — role prompting, "
            "chain-of-thought, few-shot learning, format constraints, persona injection, "
            "step-by-step instructions, example-driven prompts, negative constraints, "
            "iterative refinement, and multi-turn orchestration. Spend thirty minutes "
            "per day practicing each one with real PM scenarios. "
            "Week two: Build. Create a shared prompt library for your team. Save prompts "
            "that work for status reporting, risk discovery, meeting actions, backlog "
            "refinement, and stakeholder updates. "
            "Week three: Practice. Treat AI as your intern. Brief it clearly, review its "
            "output critically, and iterate until the quality meets your standard. "
            "Week four: Lead. Teach one colleague what you have learned. "
            "Scaling the skill across your team multiplies your impact. "
            "Master prompts, or be managed by those who do."
        ),
        slide_type="roadmap",
    ),
]

TOTAL_DURATION = sum(s.duration for s in SLIDES)


# ── Motion Profiles ────────────────────────────────────────────────────────

MOTION_PROFILES: dict[str, dict[str, str | float]] = {
    "title": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0035,1.045))",
        "desc": "Slow cinematic zoom in",
    },
    "comparison": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.002,1.03))",
        "x": "iw/2-(iw/zoom/2) - 6*sin(on/150)",
        "desc": "Gentle horizontal reveal pan",
    },
    "roadmap": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0018,1.025))",
        "x": "iw/2-(iw/zoom/2)+5*sin(on/160)",
        "desc": "Gentle pan across timeline",
    },
    "principles": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0028,1.04))",
        "desc": "Slow zoom emphasizing principles",
    },
    "dashboard": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.003,1.04))",
        "desc": "Slow zoom emphasizing data",
    },
    "governance": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0015,1.02))",
        "desc": "Ultra subtle micro-motion",
    },
    "closing": {
        "z": "if(lte(zoom,1.0),1.03,max(zoom-0.002,1.0))",
        "desc": "Cinematic zoom out for finale",
    },
}


# ── SVG Generation ─────────────────────────────────────────────────────────

def _wrap(text: str, width: int) -> list[str]:
    lines = []
    for line in text.split("\n"):
        if not line:
            lines.append("")
        else:
            wrapped = textwrap.wrap(line, width=width) or [""]
            lines.extend(wrapped)
    return lines


def _svg_background() -> str:
    return """\
  <defs>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M40 0H0V40" fill="none" stroke="#1e3a5f" stroke-width="1" opacity="0.35"/>
    </pattern>
    <radialGradient id="glow" cx="50%" cy="45%" r="65%">
      <stop offset="0%" stop-color="#1e40af" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#0f172a" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="accentBar" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="50%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#f59e0b"/>
    </linearGradient>
    <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
      <stop offset="60%" stop-color="#000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.3"/>
    </radialGradient>
    <pattern id="dots" width="120" height="120" patternUnits="userSpaceOnUse">
      <circle cx="20" cy="20" r="1" fill="#f59e0b" opacity="0.12"/>
      <circle cx="70" cy="50" r="1.2" fill="#3b82f6" opacity="0.10"/>
      <circle cx="30" cy="90" r="0.8" fill="#22c55e" opacity="0.08"/>
      <circle cx="100" cy="30" r="1" fill="#a855f7" opacity="0.10"/>
      <circle cx="90" cy="100" r="0.6" fill="#f59e0b" opacity="0.08"/>
    </pattern>
  </defs>
  <rect width="1280" height="720" fill="#0f172a"/>
  <rect width="1280" height="720" fill="url(#grid)"/>
  <rect width="1280" height="720" fill="url(#dots)"/>
  <rect width="1280" height="720" fill="url(#glow)"/>
  <rect width="1280" height="720" fill="url(#vignette)"/>
  <rect x="0" y="0" width="1280" height="5" fill="url(#accentBar)"/>"""


def _bottom_bar(seconds: int, total: int) -> str:
    progress = int((seconds / total) * 1128)
    return f"""\
  <rect x="76" y="680" width="1128" height="4" rx="2" fill="#1e293b"/>
  <rect x="76" y="680" width="{progress}" height="4" rx="2" fill="#f59e0b"/>
  <text x="76" y="710" font-family="Arial, sans-serif" font-size="13" font-weight="500" fill="#64748b" letter-spacing="1">PROMPT ENGINEERING FOR PMS</text>
  <text x="1204" y="710" text-anchor="end" font-family="Arial, sans-serif" font-size="13" font-weight="500" fill="#64748b">{seconds:02d}s / {total:02d}s</text>"""


def _pill(text: str, x: int, y: int, width: int = 200, centered: bool = False) -> str:
    left = x - width / 2 if centered else x
    text_x = x if centered else left + width / 2
    return f"""\
  <rect x="{left}" y="{y}" width="{width}" height="34" rx="17" fill="#1e3a5f" stroke="#3b82f6" stroke-width="1.5"/>
  <text x="{text_x}" y="{y + 22}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#93c5fd" letter-spacing="1.5">{escape(text)}</text>"""


def _section_divider(x: int, y: int, width: int) -> str:
    return f"""\
  <line x1="{x}" y1="{y}" x2="{x + width}" y2="{y}" stroke="#334155" stroke-width="1"/>
  <line x1="{x}" y1="{y + 1}" x2="{x + width}" y2="{y + 1}" stroke="#1e293b" stroke-width="1"/>"""


def _floating_dots(count: int, cx: int, cy: int, radius: int) -> str:
    import math
    dots = ""
    for i in range(count):
        angle = 2 * math.pi * i / count
        dx = cx + int(radius * math.cos(angle))
        dy = cy + int(radius * math.sin(angle))
        colors = ["#f59e0b", "#3b82f6", "#22c55e", "#a855f7", "#f97316"]
        dots += f"""\
  <circle cx="{dx}" cy="{dy}" r="3" fill="{colors[i % len(colors)]}" opacity="0.2"/>"""
    return dots


def _text_block(
    lines: list[str], x: int, y: int, font_size: int,
    line_height: int, color: str = "#f8fafc", anchor: str = "start",
    weight: str = "400",
) -> str:
    return "\n".join(
        f'  <text x="{x}" y="{y + i * line_height}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{font_size}" '
        f'font-weight="{weight}" fill="{color}">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )


# ── Slide Renderers ────────────────────────────────────────────────────────

def _title_slide(slide: PESlide, seconds: int, total: int) -> str:
    lines = slide.text_on_screen.split("\n\n", 1)
    title = lines[0].strip() if lines else ""
    subtitle = lines[1].strip() if len(lines) > 1 else ""
    title_lines = title.split("\n") if title else [""]
    sub_lines = subtitle.split("\n") if subtitle else [""]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_floating_dots(8, 640, 360, 250)}
  <rect x="480" y="120" width="320" height="280" rx="28" fill="#1e3a5f" stroke="#3b82f6" stroke-width="2" opacity="0.10"/>
  <rect x="520" y="140" width="240" height="200" rx="20" fill="#1e3a5f" stroke="#f59e0b" stroke-width="2" opacity="0.06"/>
  {_pill("MANAGEMENT EDUCATION", 640, 70, 260, centered=True)}
  {_text_block(title_lines, 640, 170, 52, 62, "#f8fafc", "middle", "700")}
  {_text_block(sub_lines, 640, 380, 22, 34, "#94a3b8", "middle", "400")}
  <circle cx="640" cy="540" r="80" fill="none" stroke="#f59e0b" stroke-width="1.5" opacity="0.10"/>
  <circle cx="640" cy="540" r="50" fill="none" stroke="#3b82f6" stroke-width="1.5" opacity="0.15"/>
  {_bottom_bar(seconds, total)}
</svg>"""


def _comparison_slide(slide: PESlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 52)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("CONTRAST", 640, 45, 150, centered=True)}
  {_text_block([title], 640, 105, 28, 36, "#f8fafc", "middle", "700")}
  {_section_divider(100, 150, 1080)}
  {_text_block(body_lines, 100, 170, 22, 34, "#cbd5e1", "start", "400")}
  {_bottom_bar(seconds, total)}
</svg>"""


def _roadmap_slide(slide: PESlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 56)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("WORKFLOW", 640, 45, 150, centered=True)}
  {_text_block([title], 640, 105, 28, 36, "#f8fafc", "middle", "700")}
  {_section_divider(100, 150, 1080)}
  {_text_block(body_lines, 100, 170, 22, 34, "#cbd5e1", "start", "400")}
  {_bottom_bar(seconds, total)}
</svg>"""


def _principles_slide(slide: PESlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 58)

    principle_cards = """\
  <g transform="translate(80, 155)">
    <rect x="0" y="0" width="260" height="90" rx="14" fill="#1e3a5f" stroke="#3b82f6" stroke-width="1.5" opacity="0.9"/>
    <text x="20" y="30" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#93c5fd" letter-spacing="1">ROLE</text>
    <text x="20" y="60" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">You are a senior</text>
    <text x="20" y="82" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">PMO consultant</text>
  </g>
  <g transform="translate(360, 155)">
    <rect x="0" y="0" width="260" height="90" rx="14" fill="#1e1e0f" stroke="#f59e0b" stroke-width="1.5" opacity="0.9"/>
    <text x="20" y="30" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#fcd34d" letter-spacing="1">CONTEXT</text>
    <text x="20" y="60" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">We use Scrum with</text>
    <text x="20" y="82" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">2-week sprints</text>
  </g>
  <g transform="translate(640, 155)">
    <rect x="0" y="0" width="280" height="90" rx="14" fill="#0f1e12" stroke="#22c55e" stroke-width="1.5" opacity="0.9"/>
    <text x="20" y="30" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#4ade80" letter-spacing="1">SPECIFICITY</text>
    <text x="20" y="60" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">List exactly 3 risks</text>
    <text x="20" y="82" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">ranked by impact</text>
  </g>
  <g transform="translate(940, 155)">
    <rect x="0" y="0" width="260" height="90" rx="14" fill="#1e0f2e" stroke="#a855f7" stroke-width="1.5" opacity="0.9"/>
    <text x="20" y="30" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#c084fc" letter-spacing="1">ITERATE</text>
    <text x="20" y="60" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">Make it more</text>
    <text x="20" y="82" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">concise → Refine</text>
  </g>"""

    footer = """\
  <g transform="translate(340, 560)">
    <rect x="0" y="0" width="600" height="48" rx="24" fill="#1e3a5f" opacity="0.5"/>
    <text x="300" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" fill="#93c5fd" font-weight="600">You are not guessing. You are engineering an input.</text>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("PRINCIPLES", 640, 40, 160, centered=True)}
  {_text_block([title], 640, 100, 28, 36, "#f8fafc", "middle", "700")}
  {principle_cards}
  {_section_divider(100, 280, 1080)}
  {_text_block(_wrap(slide.narration, 60), 100, 305, 19, 30, "#cbd5e1", "start", "400")}
  {footer}
  {_bottom_bar(seconds, total)}
</svg>"""


def _dashboard_slide(slide: PESlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    body = parts[1] if len(parts) > 1 else ""
    before_line = ""
    after_line = ""
    if "Before:" in body:
        before_section = body.split("After:")
        before_raw = before_section[0].replace("Before:", "").strip()
        after_raw = before_section[1].strip() if len(before_section) > 1 else ""
        before_line = before_raw.replace('"', '').replace('"', '').strip()
        after_line = after_raw.replace('"', '').replace('"', '').strip()

    dashboard = f"""\
  <g transform="translate(120, 170)">
    <rect x="0" y="0" width="500" height="360" rx="18" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
    <rect x="0" y="0" width="500" height="48" rx="18" fill="#450a0a"/>
    <rect x="0" y="30" width="500" height="18" fill="#450a0a"/>
    <text x="250" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#fca5a5" letter-spacing="2">BEFORE: TRACKING</text>
    <text x="30" y="90" font-family="Arial, sans-serif" font-size="14" fill="#ef4444">⚠</text>
    <text x="60" y="94" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">{escape(before_line[:80])}</text>
    <line x1="20" y1="110" x2="480" y2="110" stroke="#334155" stroke-width="0.5"/>
    <text x="30" y="150" font-family="Arial, sans-serif" font-size="14" fill="#ef4444">⚠</text>
    <text x="60" y="154" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Hours spent copying data, formatting reports</text>
    <line x1="20" y1="170" x2="480" y2="170" stroke="#334155" stroke-width="0.5"/>
    <text x="30" y="210" font-family="Arial, sans-serif" font-size="14" fill="#ef4444">⚠</text>
    <text x="60" y="214" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Reactive: respond to status requests manually</text>
    <line x1="20" y1="230" x2="480" y2="230" stroke="#334155" stroke-width="0.5"/>
    <text x="30" y="270" font-family="Arial, sans-serif" font-size="14" fill="#ef4444">⚠</text>
    <text x="60" y="274" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">No reusable prompt library or templates</text>
    <line x1="20" y1="290" x2="480" y2="290" stroke="#334155" stroke-width="0.5"/>
    <rect x="100" y="310" width="300" height="34" rx="17" fill="#ef4444" opacity="0.12"/>
    <text x="250" y="332" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#fca5a5">Reactive PM = administrative overload</text>
  </g>
  <g transform="translate(660, 170)">
    <rect x="0" y="0" width="500" height="360" rx="18" fill="#052e16" stroke="#22c55e" stroke-width="1.5"/>
    <rect x="0" y="0" width="500" height="48" rx="18" fill="#052e16"/>
    <rect x="0" y="30" width="500" height="18" fill="#052e16"/>
    <text x="250" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#4ade80" letter-spacing="2">AFTER: ORCHESTRATION</text>
    <text x="30" y="90" font-family="Arial, sans-serif" font-size="14" fill="#22c55e">✓</text>
    <text x="60" y="94" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">{escape(after_line[:80])}</text>
    <line x1="20" y1="110" x2="480" y2="110" stroke="#1a3a2a" stroke-width="0.5"/>
    <text x="30" y="150" font-family="Arial, sans-serif" font-size="14" fill="#22c55e">✓</text>
    <text x="60" y="154" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Minutes to review and approve AI-generated drafts</text>
    <line x1="20" y1="170" x2="480" y2="170" stroke="#1a3a2a" stroke-width="0.5"/>
    <text x="30" y="210" font-family="Arial, sans-serif" font-size="14" fill="#22c55e">✓</text>
    <text x="60" y="214" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Proactive: design prompts, review output, decide</text>
    <line x1="20" y1="230" x2="480" y2="230" stroke="#1a3a2a" stroke-width="0.5"/>
    <text x="30" y="270" font-family="Arial, sans-serif" font-size="14" fill="#22c55e">✓</text>
    <text x="60" y="274" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Shared prompt library scales across the team</text>
    <line x1="20" y1="290" x2="480" y2="290" stroke="#1a3a2a" stroke-width="0.5"/>
    <rect x="100" y="310" width="300" height="34" rx="17" fill="#22c55e" opacity="0.12"/>
    <text x="250" y="332" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#86efac">Orchestrating PM = decision intelligence</text>
  </g>
  <rect x="613" y="330" width="54" height="54" rx="27" fill="#f59e0b" opacity="0.12"/>
  <text x="640" y="364" text-anchor="middle" font-family="Arial, sans-serif" font-size="28" fill="#f59e0b" font-weight="700">→</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("TRANSFORMATION", 640, 40, 220, centered=True)}
  {_text_block([title], 640, 100, 26, 34, "#f8fafc", "middle", "700")}
  {dashboard}
  {_bottom_bar(seconds, total)}
</svg>"""


def _governance_slide(slide: PESlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 60)

    cards_data = [
        ("JUDGMENT", "Prioritize trade-offs\nAI can't value", "#3b82f6", "#1e3a5f"),
        ("ALIGNMENT", "Translate business goals\nto precise prompts", "#f59e0b", "#1e1e0f"),
        ("ACCOUNTABILITY", "Own outcomes,\nethics, and trust", "#22c55e", "#0f1e12"),
    ]

    cards_svg = ""
    for i, (label, desc, accent, bg) in enumerate(cards_data):
        cx = 100 + i * 400
        cards_svg += f"""\
  <g transform="translate({cx}, 225)">
    <rect x="0" y="0" width="340" height="160" rx="18" fill="{bg}" stroke="{accent}" stroke-width="1.5" opacity="0.9"/>
    <rect x="0" y="0" width="340" height="6" rx="18" fill="{accent}" opacity="0.7"/>
    <text x="170" y="45" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="{accent}" letter-spacing="2">{label}</text>
    <line x1="30" y1="62" x2="310" y2="62" stroke="{accent}" stroke-width="0.5" opacity="0.3"/>
    <text x="170" y="95" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#f8fafc">{escape(desc.split(chr(10))[0])}</text>
    <text x="170" y="125" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#f8fafc">{escape(desc.split(chr(10))[1] if chr(10) in desc else "")}</text>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("GOVERNANCE", 640, 40, 180, centered=True)}
  {_text_block([title], 640, 100, 30, 38, "#f8fafc", "middle", "700")}
  {cards_svg}
  {_section_divider(100, 430, 1080)}
  {_text_block(_wrap(slide.narration, 60), 100, 455, 18, 28, "#cbd5e1", "start", "400")}
  {_bottom_bar(seconds, total)}
</svg>"""


# ── Render Dispatch ────────────────────────────────────────────────────────

def render_slide(slide: PESlide, seconds: int, total: int) -> bytes:
    renderers = {
        "title": _title_slide,
        "comparison": _comparison_slide,
        "roadmap": _roadmap_slide,
        "principles": _principles_slide,
        "dashboard": _dashboard_slide,
        "governance": _governance_slide,
    }
    renderer = renderers.get(slide.slide_type)
    if not renderer:
        # Fallback to comparison-style layout
        renderer = _comparison_slide
    svg = renderer(slide, seconds, total)
    return svg.encode("utf-8")


# ── SRT Generation ─────────────────────────────────────────────────────────

def _timestamp(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d},000"


def generate_srt(slides: list[PESlide], video_duration: int) -> str:
    lines: list[str] = []
    start = 0
    for i, slide in enumerate(slides, start=1):
        end = min(start + slide.duration, video_duration)
        lines.extend([
            str(i),
            f"{_timestamp(start)} --> {_timestamp(end)}",
            slide.narration,
            "",
        ])
        start = end
    return "\n".join(lines)


# ── Audio Narration Generation ─────────────────────────────────────────────

def generate_narration(slides: list[PESlide], output_dir: Path) -> Path:
    """Generate narration using espeak-ng (local TTS). Falls back to macOS say."""
    full_script = " ".join(slide.narration for slide in slides)
    audio_path = output_dir / "narration.mp3"

    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    say_exec = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")

    if espeak:
        print("  Generating narration via espeak-ng...")
        wav_path = output_dir / "narration_temp.wav"
        subprocess.run(
            [espeak, "-s", "155", "-v", "en-us+f3", "-w", str(wav_path), full_script],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [ffmpeg, "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-q:a", "4", str(audio_path)],
            check=True, capture_output=True, text=True,
        )
        wav_path.unlink(missing_ok=True)
        print(f"  Narration saved: {audio_path}")
        return audio_path

    if say_exec:
        print("  Generating narration via macOS say...")
        aiff_path = output_dir / "narration_temp.aiff"
        subprocess.run(
            [say_exec, "-v", "Samantha", "-r", "180", "-o", str(aiff_path), full_script],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [ffmpeg, "-y", "-i", str(aiff_path), "-c:a", "libmp3lame", "-q:a", "4", str(audio_path)],
            check=True, capture_output=True, text=True,
        )
        aiff_path.unlink(missing_ok=True)
        print(f"  Narration saved: {audio_path}")
        return audio_path

    raise RuntimeError(
        "No TTS engine found. Install espeak-ng (brew install espeak-ng) "
        "or ensure OpenAI API key is set in .env"
    )


# ── Background Music Generation ─────────────────────────────────────────────

def generate_background_music(output_dir: Path, duration: float) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required for BGM generation.")

    temp_dir = output_dir / "bgm_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("  Generating ambient background music...")

    # Warm ambient pad (filtered pink noise)
    subprocess.run(
        [executable, "-y",
         "-f", "lavfi",
         "-i", f"anoisesrc=color=pink:duration={duration}:seed=42",
         "-af", "lowpass=f=350,volume=0.10",
         "-c:a", "pcm_s16le",
         str(temp_dir / "pad.wav")],
        check=True, capture_output=True, text=True,
    )

    # Gentle musical chord tones (C major)
    for freq, vol, name in [
        (130.81, 0.025, "tone_c"),
        (164.81, 0.018, "tone_e"),
        (196.00, 0.018, "tone_g"),
    ]:
        subprocess.run(
            [executable, "-y",
             "-f", "lavfi",
             "-i", f"aevalsrc=exprs={vol}*sin(2*PI*{freq}*t):d={duration}",
             "-c:a", "pcm_s16le",
             str(temp_dir / f"{name}.wav")],
            check=True, capture_output=True, text=True,
        )

    # Mix all layers with fade-in/out
    bgm_path = output_dir / "background_music.wav"
    subprocess.run(
        [executable, "-y",
         "-i", str(temp_dir / "pad.wav"),
         "-i", str(temp_dir / "tone_c.wav"),
         "-i", str(temp_dir / "tone_e.wav"),
         "-i", str(temp_dir / "tone_g.wav"),
         "-filter_complex",
         "[0:a][1:a][2:a][3:a]amix=inputs=4:duration=first:dropout_transition=2"
         ",afade=t=in:st=0:d=2,afade=t=out:st=" + str(max(0, duration - 2.5)) + ":d=2[out]",
         "-map", "[out]",
         "-c:a", "pcm_s16le",
         str(bgm_path)],
        check=True, capture_output=True, text=True,
    )

    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"  Background music saved: {bgm_path}")
    return bgm_path


# ── Duration Helpers ───────────────────────────────────────────────────────

def _get_audio_duration(audio_path: Path) -> float:
    probe = shutil.which("ffprobe") or "ffprobe"
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


# ── Video Assembly ─────────────────────────────────────────────────────────

def _build_motion_filter(slide_type: str, frames: int, slide_duration: int) -> str:
    profile = MOTION_PROFILES.get(slide_type, MOTION_PROFILES["comparison"])
    z_expr = profile.get("z", "1.0")
    x_expr = profile.get("x", "iw/2-(iw/zoom/2)")
    y_expr = profile.get("y", "ih/2-(ih/zoom/2)")

    fade_out = max(0, slide_duration - 0.4)
    return (
        f"scale=1280:720,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s=1280x720:fps={FPS},"
        f"fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={fade_out}:d=0.5,"
        f"format=yuv420p"
    )


def assemble_video(slides: list[PESlide], output_dir: Path) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required. Install with: brew install ffmpeg")

    output_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    import cairosvg

    total_duration = sum(s.duration for s in slides)

    # ── Step 1: Render all slides to PNGs and generate clip MP4s ──
    clip_paths: list[Path] = []
    running = 0
    for i, slide in enumerate(slides, start=1):
        profile_name = slide.slide_type if slide.slide_type in MOTION_PROFILES else "comparison"
        profile = MOTION_PROFILES.get(profile_name, MOTION_PROFILES["comparison"])
        print(f"  Rendering slide {i}/{len(slides)} ({slide.duration}s) [{profile['desc']}]...")
        svg_bytes = render_slide(slide, running + slide.duration, total_duration)
        png_path = scenes_dir / f"slide_{i:02d}.png"
        cairosvg.svg2png(
            bytestring=svg_bytes,
            output_width=WIDTH,
            output_height=HEIGHT,
            write_to=str(png_path),
        )

        clip_path = clips_dir / f"slide_{i:02d}.mp4"
        frames = slide.duration * FPS
        motion_filter = _build_motion_filter(profile_name, frames, slide.duration)

        subprocess.run(
            [executable, "-y",
             "-loop", "1",
             "-i", str(png_path),
             "-vf", motion_filter,
             "-t", str(slide.duration),
             "-an",
             "-c:v", "libx264",
             "-pix_fmt", "yuv420p",
             "-movflags", "+faststart",
             "-crf", "22",
             str(clip_path)],
            check=True, capture_output=True, text=True,
        )
        clip_paths.append(clip_path)
        running += slide.duration

    # ── Step 2: Concatenate with crossfade transitions ──
    num_clips = len(clip_paths)

    if num_clips == 1:
        temp_mp4 = output_dir / "pe_video_no_audio.mp4"
        clip_paths[0].rename(temp_mp4)
    else:
        print(f"  Crossfading {num_clips} clips with {TRANSITION_DUR}s transitions...")

        filter_parts = []
        for i in range(num_clips):
            filter_parts.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]")

        cumulative = 0.0
        prev_label = "v0"
        for i in range(1, num_clips):
            offset = cumulative + slides[i - 1].duration - TRANSITION_DUR
            cur_label = f"xf{i}"
            filter_parts.append(
                f"[{prev_label}][v{i}]xfade=transition=fade:"
                f"duration={TRANSITION_DUR}:offset={offset:.1f}[{cur_label}]"
            )
            cumulative += slides[i - 1].duration - TRANSITION_DUR
            prev_label = cur_label

        filter_chain = ";".join(filter_parts)

        temp_mp4 = output_dir / "pe_video_no_audio.mp4"
        cmd = [executable, "-y"]
        for clip in clip_paths:
            cmd.extend(["-i", str(clip)])
        cmd.extend([
            "-filter_complex", filter_chain,
            "-map", f"[{prev_label}]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "22",
            "-movflags", "+faststart",
            str(temp_mp4),
        ])
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    # ── Step 3: Compute actual video duration after transitions ──
    actual_video_dur = total_duration - (num_clips - 1) * TRANSITION_DUR
    print(f"  Video duration: {total_duration}s - {(num_clips - 1) * TRANSITION_DUR}s transitions = {actual_video_dur:.1f}s")

    # ── Step 4: Generate narration audio ──
    audio_path = generate_narration(slides, output_dir)

    # ── Step 5: Generate background music ──
    bgm_path = generate_background_music(output_dir, total_duration)

    # ── Step 6: Mix narration with background music ──
    print("  Mixing narration with background music...")
    audio_mixed = output_dir / "audio_mixed.wav"
    subprocess.run(
        [executable, "-y",
         "-i", str(audio_path),
         "-i", str(bgm_path),
         "-filter_complex",
         "[1:a]volume=0.18[bgm];"
         "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[mixed]",
         "-map", "[mixed]",
         "-c:a", "pcm_s16le",
         str(audio_mixed)],
        check=True, capture_output=True, text=True,
    )

    # ── Step 7: Speed/sync audio to match video duration ──
    mixed_dur = _get_audio_duration(audio_mixed)
    if abs(mixed_dur - actual_video_dur) > 0.5:
        print(f"  Mixed audio ({mixed_dur:.1f}s) != video ({actual_video_dur:.1f}s). Adjusting speed...")
        audio_final = output_dir / "audio_final.m4a"
        speed = mixed_dur / actual_video_dur if actual_video_dur > 0 else 1.0
        speed = max(0.5, min(3.0, speed))
        print(f"  Audio speed factor: {speed:.2f}x")
        subprocess.run(
            [executable, "-y",
             "-i", str(audio_mixed),
             "-af", f"atempo={speed},apad,atrim=duration={actual_video_dur}",
             "-c:a", "aac",
             "-b:a", "192k",
             str(audio_final)],
            check=True, capture_output=True, text=True,
        )
        audio_mixed.unlink(missing_ok=True)
        audio_mixed = audio_final
    else:
        print(f"  Audio duration matches video ({mixed_dur:.1f}s). No speed adjustment needed.")
        audio_final = output_dir / "audio_final.m4a"
        subprocess.run(
            [executable, "-y",
             "-i", str(audio_mixed),
             "-c:a", "aac",
             "-b:a", "192k",
             str(audio_final)],
            check=True, capture_output=True, text=True,
        )
        audio_mixed.unlink(missing_ok=True)
        audio_mixed = audio_final

    # ── Step 8: Merge audio with video ──
    output_mp4 = output_dir / "prompt_engineering_for_pms.mp4"
    print("  Merging final audio with video...")
    subprocess.run(
        [executable, "-y",
         "-i", str(temp_mp4),
         "-i", str(audio_mixed),
         "-c:v", "copy",
         "-c:a", "aac",
         "-b:a", "192k",
         "-map", "0:v:0",
         "-map", "1:a:0",
         "-movflags", "+faststart",
         str(output_mp4)],
        check=True, capture_output=True, text=True,
    )

    # Cleanup temp files
    audio_mixed.unlink(missing_ok=True)
    bgm_path.unlink(missing_ok=True)
    temp_mp4.unlink(missing_ok=True)

    # Generate SRT subtitles
    srt_path = output_dir / "prompt_engineering_for_pms.srt"
    srt_path.write_text(generate_srt(slides, int(actual_video_dur)), encoding="utf-8")

    return output_mp4


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  Prompt Engineering for PMs - Educational Video Generator")
    print("  Motion graphics + crossfade transitions + ambient audio")
    print("=" * 60)
    print(f"\nSlides: {len(SLIDES)}")
    actual_dur = TOTAL_DURATION - (len(SLIDES) - 1) * TRANSITION_DUR
    print(f"Total duration: {TOTAL_DURATION}s → {actual_dur:.1f}s (with {TRANSITION_DUR}s crossfades)")
    minutes = int(actual_dur // 60)
    seconds = int(actual_dur % 60)
    print(f"Target: {minutes}m {seconds}s — exceeding the 5-minute minimum ✓")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    for s in SLIDES:
        profile = MOTION_PROFILES.get(s.slide_type, MOTION_PROFILES["comparison"])
        print(f"  [{s.slide_type:12s}] {s.duration:2d}s  {profile['desc']}")

    print()
    output_mp4 = assemble_video(SLIDES, OUTPUT_DIR)

    srt_path = OUTPUT_DIR / "prompt_engineering_for_pms.srt"
    print(f"\n✓ Video generated: {output_mp4}")
    print(f"✓ Subtitles: {srt_path}")
    actual_dur = TOTAL_DURATION - (len(SLIDES) - 1) * TRANSITION_DUR
    print(f"✓ Video duration: {actual_dur:.1f}s ({int(actual_dur // 60)}m {int(actual_dur % 60)}s)")
    print(f"✓ File size: {output_mp4.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
