#!/usr/bin/env python3
"""How AI Understands Language — Educational Video Generator

Generates a short educational video explaining how large language models work,
with custom-designed SVG slides, Ken Burns motion, OpenAI TTS narration,
procedural background music, crossfade transitions, and SRT subtitles.

Output saved to output/New/
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
OUTPUT_DIR = Path("output/New")
FPS = 30
TRANSITION_DUR = 0.4


@dataclass(frozen=True)
class AISlide:
    text_on_screen: str
    duration: int
    narration: str
    slide_type: str


# ── Slide Definitions ──────────────────────────────────────────────────────

SLIDES = [
    AISlide(
        text_on_screen=(
            "How AI Understands Language\n\n"
            "A simple guide to how Large Language\n"
            "Models actually work"
        ),
        duration=14,
        narration=(
            "How does AI understand language? It doesn't — not the way we do. "
            "But it can predict words, patterns, and meaning with surprising accuracy. "
            "Let's break down how Large Language Models actually work, without the jargon."
        ),
        slide_type="title",
    ),
    AISlide(
        text_on_screen=(
            "Words Become Numbers\n\n"
            "\"The cat sat on the mat\"\n"
            "→ [45, 892, 671, 23, 45, 312]\n\n"
            "Tokenization: every word becomes\n"
            "a numeric ID the model can process"
        ),
        duration=16,
        narration=(
            "First, the model converts words into numbers. This is called tokenization. "
            "Every word gets a unique numeric ID. The word 'the' might be 45, "
            "'cat' might be 892, and so on. "
            "These numbers are all the model sees — it has no concept of what a cat is. "
            "It only knows that 892 often appears near 671, which is 'sat'. "
            "This numeric transformation is the foundation of everything."
        ),
        slide_type="concept",
    ),
    AISlide(
        text_on_screen=(
            "Patterns, Not Understanding\n\n"
            "The model learns:\n"
            "• Which words appear together\n"
            "• In what order they usually go\n"
            "• Which words are similar in meaning\n\n"
            "It's a pattern-matching engine,\n"
            "not a thinking machine"
        ),
        duration=18,
        narration=(
            "Here is the key insight: LLMs do not understand language. "
            "They are pattern-matching engines trained on enormous amounts of text. "
            "The model learns which words tend to appear together, "
            "in what order they usually go, and which words are interchangeable. "
            "When you ask a question, the model predicts the most probable response "
            "based on all the patterns it has seen in its training data. "
            "That is why it can write essays, code, and poetry — "
            "but it can also make confident-sounding mistakes."
        ),
        slide_type="principles",
    ),
    AISlide(
        text_on_screen=(
            "Training: Billions of Words\n\n"
            "GPT-4 trained on:\n"
            "• ~13 trillion tokens of text\n"
            "• Books, articles, code, websites\n"
            "• Months of GPU compute\n\n"
            "Scale is what makes it work"
        ),
        duration=16,
        narration=(
            "Training these models requires staggering scale. "
            "GPT-4 was trained on roughly 13 trillion tokens — "
            "that is trillions of words from books, articles, code, and websites. "
            "The training runs for months on thousands of specialized GPUs. "
            "During training, the model makes a prediction, checks if it was right, "
            "and adjusts billions of internal parameters to be slightly more accurate next time. "
            "This process repeats trillions of times. Scale is what makes the magic work."
        ),
        slide_type="stats",
    ),
    AISlide(
        text_on_screen=(
            "You Guide the AI\n\n"
            "Better prompts = Better results\n\n"
            "Prompt design:\n"
            "• Be specific, not vague\n"
            "• Give examples (few-shot)\n"
            "• Tell it the role to play\n"
            "• Iterate and refine"
        ),
        duration=16,
        narration=(
            "Here is where you come in. The quality of what you get from an AI "
            "depends entirely on the quality of what you give it. "
            "Be specific — instead of 'write an email', say 'write a professional follow-up email "
            "to a client who hasn't responded in three days'. Give examples of the output you want. "
            "Tell the AI what role to play — 'you are a senior software architect'. "
            "And iterate. Treat the first response as a draft, then refine your prompt. "
            "The AI generates. You guide. That partnership is where the real power lives."
        ),
        slide_type="principles",
    ),
    AISlide(
        text_on_screen=(
            "Summary\n\n"
            "• Words → Numbers (tokenization)\n"
            "• Patterns → Predictions (training)\n"
            "• You → The guide (prompting)\n\n"
            "AI doesn't understand.\n"
            "But it can be incredibly useful."
        ),
        duration=14,
        narration=(
            "So to summarize: AI turns words into numbers through tokenization, "
            "learns patterns from billions of examples during training, "
            "and generates responses by predicting what comes next. "
            "It does not understand language the way humans do — "
            "but it can be incredibly useful when guided well. "
            "The more you understand how it works, the better you can use it. "
            "Thanks for watching, and keep exploring."
        ),
        slide_type="closing",
    ),
]

TOTAL_DURATION = sum(s.duration for s in SLIDES)


# ── Motion Profiles ────────────────────────────────────────────────────────

MOTION_PROFILES: dict[str, dict[str, str | float]] = {
    "title": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0035,1.045))",
        "desc": "Slow cinematic zoom in",
    },
    "concept": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0025,1.035))",
        "x": "iw/2-(iw/zoom/2)+6*sin(on/140)",
        "desc": "Zoom with gentle horizontal sway",
    },
    "principles": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0028,1.04))",
        "desc": "Slow zoom emphasizing key points",
    },
    "stats": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.003,1.04))",
        "desc": "Slow zoom emphasizing data",
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
      <path d="M40 0H0V40" fill="none" stroke="#2d1b69" stroke-width="1" opacity="0.35"/>
    </pattern>
    <radialGradient id="glow" cx="50%" cy="45%" r="65%">
      <stop offset="0%" stop-color="#7c3aed" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#0f172a" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="accentBar" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#8b5cf6"/>
      <stop offset="50%" stop-color="#06b6d4"/>
      <stop offset="100%" stop-color="#8b5cf6"/>
    </linearGradient>
    <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
      <stop offset="60%" stop-color="#000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.3"/>
    </radialGradient>
    <pattern id="dots" width="120" height="120" patternUnits="userSpaceOnUse">
      <circle cx="20" cy="20" r="1" fill="#8b5cf6" opacity="0.15"/>
      <circle cx="70" cy="50" r="1.2" fill="#06b6d4" opacity="0.12"/>
      <circle cx="30" cy="90" r="0.8" fill="#22d3ee" opacity="0.10"/>
      <circle cx="100" cy="30" r="1" fill="#a78bfa" opacity="0.12"/>
      <circle cx="90" cy="100" r="0.6" fill="#8b5cf6" opacity="0.10"/>
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
  <rect x="76" y="680" width="{progress}" height="4" rx="2" fill="#8b5cf6"/>
  <text x="76" y="710" font-family="Arial, sans-serif" font-size="13" font-weight="500" fill="#64748b" letter-spacing="1">HOW AI UNDERSTANDS LANGUAGE</text>
  <text x="1204" y="710" text-anchor="end" font-family="Arial, sans-serif" font-size="13" font-weight="500" fill="#64748b">{seconds:02d}s / {total:02d}s</text>"""


def _pill(text: str, x: int, y: int, width: int = 200, centered: bool = False) -> str:
    left = x - width / 2 if centered else x
    text_x = x if centered else left + width / 2
    return f"""\
  <rect x="{left}" y="{y}" width="{width}" height="34" rx="17" fill="#2d1b69" stroke="#8b5cf6" stroke-width="1.5"/>
  <text x="{text_x}" y="{y + 22}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#a78bfa" letter-spacing="1.5">{escape(text)}</text>"""


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
        colors = ["#8b5cf6", "#06b6d4", "#22d3ee", "#a78bfa", "#c084fc"]
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

def _title_slide(slide: AISlide, seconds: int, total: int) -> str:
    lines = slide.text_on_screen.split("\n\n", 1)
    title = lines[0].strip() if lines else ""
    subtitle = lines[1].strip() if len(lines) > 1 else ""
    title_lines = title.split("\n") if title else [""]
    sub_lines = subtitle.split("\n") if subtitle else [""]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_floating_dots(10, 640, 360, 280)}
  <rect x="480" y="110" width="320" height="300" rx="28" fill="#2d1b69" stroke="#8b5cf6" stroke-width="2" opacity="0.12"/>
  <rect x="520" y="130" width="240" height="220" rx="20" fill="#2d1b69" stroke="#06b6d4" stroke-width="2" opacity="0.08"/>
  <circle cx="640" cy="520" r="120" fill="none" stroke="#8b5cf6" stroke-width="1.5" opacity="0.12"/>
  <circle cx="640" cy="520" r="80" fill="none" stroke="#06b6d4" stroke-width="1.5" opacity="0.15"/>
  <circle cx="640" cy="520" r="40" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.12"/>
  {_pill("AI EXPLAINED", 640, 70, 190, centered=True)}
  {_text_block(title_lines, 640, 170, 48, 58, "#f8fafc", "middle", "700")}
  {_text_block(sub_lines, 640, 370, 22, 34, "#94a3b8", "middle", "400")}
  {_bottom_bar(seconds, total)}
</svg>"""


def _concept_slide(slide: AISlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 58)

    # Code block visual
    code_visual = """\
  <g transform="translate(780, 160)">
    <rect x="0" y="0" width="440" height="260" rx="14" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
    <rect x="0" y="0" width="440" height="40" rx="14" fill="#2d1b69"/>
    <rect x="0" y="22" width="440" height="18" fill="#2d1b69"/>
    <circle cx="20" cy="20" r="6" fill="#ef4444"/>
    <circle cx="42" cy="20" r="6" fill="#f59e0b"/>
    <circle cx="64" cy="20" r="6" fill="#22c55e"/>
    <text x="20" y="75" font-family="Arial, sans-serif" font-size="25" font-weight="600" fill="#22d3ee">tokens</text>
    <text x="20" y="115" font-family="Arial, sans-serif" font-size="22" fill="#94a3b8">Input:  "The cat sat on the mat"</text>
    <line x1="20" y1="130" x2="420" y2="130" stroke="#334155" stroke-width="1"/>
    <text x="20" y="165" font-family="Arial, sans-serif" font-size="22" fill="#22c55e">[45, 892, 671, 23, 45, 312]</text>
    <line x1="20" y1="180" x2="420" y2="180" stroke="#334155" stroke-width="1"/>
    <text x="20" y="215" font-family="Arial, sans-serif" font-size="22" fill="#a78bfa">IDs → Model processes → Output</text>
    <line x1="20" y1="230" x2="420" y2="230" stroke="#334155" stroke-width="1"/>
    <text x="20" y="260" font-family="Arial, sans-serif" font-size="18" fill="#64748b">Tokenization transforms text to numbers</text>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("TOKENIZATION", 640, 40, 190, centered=True)}
  {_text_block([title], 640, 100, 28, 36, "#f8fafc", "middle", "700")}
  {_section_divider(80, 145, 600)}
  {_text_block(body_lines, 80, 170, 18, 28, "#cbd5e1", "start", "400")}
  {code_visual}
  {_bottom_bar(seconds, total)}
</svg>"""


def _principles_slide(slide: AISlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 62)

    # Cards for key concepts
    cards = """\
  <g transform="translate(80, 430)">
    <rect x="0" y="0" width="360" height="210" rx="16" fill="#1e293b" stroke="#8b5cf6" stroke-width="1.5"/>
    <rect x="0" y="0" width="360" height="6" rx="16" fill="#8b5cf6" opacity="0.7"/>
    <text x="180" y="45" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#a78bfa" letter-spacing="1">PATTERN MATCHER</text>
    <line x1="20" y1="60" x2="340" y2="60" stroke="#334155" stroke-width="0.5"/>
    <text x="180" y="95" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Learns which words appear</text>
    <text x="180" y="120" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">together and in what order</text>
    <text x="180" y="155" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">No understanding, only probability</text>
  </g>
  <g transform="translate(460, 430)">
    <rect x="0" y="0" width="360" height="210" rx="16" fill="#1e293b" stroke="#06b6d4" stroke-width="1.5"/>
    <rect x="0" y="0" width="360" height="6" rx="16" fill="#06b6d4" opacity="0.7"/>
    <text x="180" y="45" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#22d3ee" letter-spacing="1">CONTEXT ENGINE</text>
    <line x1="20" y1="60" x2="340" y2="60" stroke="#334155" stroke-width="0.5"/>
    <text x="180" y="95" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Uses surrounding words to</text>
    <text x="180" y="120" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">predict the next token</text>
    <text x="180" y="155" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">Context window = memory</text>
  </g>
  <g transform="translate(840, 430)">
    <rect x="0" y="0" width="360" height="210" rx="16" fill="#1e293b" stroke="#22d3ee" stroke-width="1.5"/>
    <rect x="0" y="0" width="360" height="6" rx="16" fill="#22d3ee" opacity="0.7"/>
    <text x="180" y="45" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#67e8f9" letter-spacing="1">SCALE MATTERS</text>
    <line x1="20" y1="60" x2="340" y2="60" stroke="#334155" stroke-width="0.5"/>
    <text x="180" y="95" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">Trillions of training examples</text>
    <text x="180" y="120" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">create emergent capabilities</text>
    <text x="180" y="155" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">More data = better predictions</text>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("HOW IT WORKS", 640, 35, 190, centered=True)}
  {_text_block([title], 640, 95, 30, 38, "#f8fafc", "middle", "700")}
  {_section_divider(100, 140, 1080)}
  {_text_block(body_lines[:3], 100, 165, 19, 30, "#cbd5e1", "start", "400")}
  {cards}
  {_bottom_bar(seconds, total)}
</svg>"""


def _stats_slide(slide: AISlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 56)

    # Stats bars
    stats_bars = """\
  <g transform="translate(720, 160)">
    <text x="20" y="35" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Training Data</text>
    <rect x="20" y="50" width="500" height="28" rx="14" fill="#334155"/>
    <rect x="20" y="50" width="480" height="28" rx="14" fill="#8b5cf6"/>
    <text x="510" y="70" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#a78bfa" font-weight="700">13 trillion tokens</text>

    <text x="20" y="120" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Model Parameters</text>
    <rect x="20" y="135" width="500" height="28" rx="14" fill="#334155"/>
    <rect x="20" y="135" width="440" height="28" rx="14" fill="#06b6d4"/>
    <text x="510" y="155" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#22d3ee" font-weight="700">~1.8 trillion</text>

    <text x="20" y="205" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Training Duration</text>
    <rect x="20" y="220" width="500" height="28" rx="14" fill="#334155"/>
    <rect x="20" y="220" width="380" height="28" rx="14" fill="#22d3ee"/>
    <text x="510" y="240" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#67e8f9" font-weight="700">Months on GPUs</text>

    <text x="20" y="290" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Context Window</text>
    <rect x="20" y="305" width="500" height="28" rx="14" fill="#334155"/>
    <rect x="20" y="305" width="260" height="28" rx="14" fill="#a78bfa"/>
    <text x="510" y="325" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#c084fc" font-weight="700">Up to 128K tokens</text>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("SCALE", 640, 40, 130, centered=True)}
  {_text_block([title], 640, 100, 28, 36, "#f8fafc", "middle", "700")}
  {_section_divider(80, 145, 550)}
  {_text_block(body_lines, 80, 170, 18, 28, "#cbd5e1", "start", "400")}
  {stats_bars}
  {_bottom_bar(seconds, total)}
</svg>"""


def _closing_slide(slide: AISlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    body = parts[1] if len(parts) > 1 else ""
    title_lines = title.split("\n") if title else [""]
    body_lines = body.split("\n") if body else [""]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_floating_dots(12, 640, 360, 300)}
  {_pill("RECAP", 640, 60, 120, centered=True)}
  {_text_block(title_lines, 640, 140, 36, 44, "#f8fafc", "middle", "700")}
  {_section_divider(200, 195, 880)}
  {_text_block(body_lines, 640, 230, 22, 36, "#cbd5e1", "middle", "400")}
  <!-- Key takeaway box -->
  <g transform="translate(340, 420)">
    <rect x="0" y="0" width="600" height="100" rx="24" fill="#2d1b69" stroke="#8b5cf6" stroke-width="2" opacity="0.9"/>
    <text x="300" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#a78bfa">AI doesn't understand.</text>
    <text x="300" y="78" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#22d3ee">But it can be incredibly useful.</text>
  </g>
  <g transform="translate(440, 560)">
    <rect x="0" y="0" width="400" height="48" rx="24" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
    <text x="200" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#64748b">Words → Patterns → Predictions → You guide</text>
  </g>
  {_bottom_bar(seconds, total)}
</svg>"""


# ── Render Dispatch ────────────────────────────────────────────────────────

def render_slide(slide: AISlide, seconds: int, total: int) -> bytes:
    renderers = {
        "title": _title_slide,
        "concept": _concept_slide,
        "principles": _principles_slide,
        "stats": _stats_slide,
        "closing": _closing_slide,
    }
    renderer = renderers.get(slide.slide_type)
    if not renderer:
        renderer = _concept_slide
    svg = renderer(slide, seconds, total)
    return svg.encode("utf-8")


# ── SRT Generation ─────────────────────────────────────────────────────────

def _timestamp(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d},000"


def generate_srt(slides: list[AISlide], video_duration: int) -> str:
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

def generate_narration(slides: list[AISlide], output_dir: Path) -> Path:
    """Generate narration using OpenAI TTS. Falls back to espeak-ng or macOS say."""
    full_script = " ".join(slide.narration for slide in slides)
    audio_path = output_dir / "narration.mp3"

    # Try OpenAI first
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            from openai import OpenAI
            print("  Generating narration via OpenAI TTS...")
            client = OpenAI(api_key=api_key)
            result = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="echo",
                input=full_script,
                instructions=(
                    "Speak in a warm, clear, friendly voice. Like a knowledgeable educator "
                    "explaining a fascinating concept to a curious beginner. "
                    "Enthusiastic but not rushed. Clear and conversational. "
                    "Sound excited about how AI works without being dramatic."
                ),
            )
            audio_path.write_bytes(result.read())
            print(f"  Narration saved: {audio_path}")
            return audio_path
        except Exception as e:
            print(f"  OpenAI TTS failed ({e}). Falling back to local TTS...")

    # Fallback: local TTS
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
        "No TTS engine available. Install espeak-ng (brew install espeak-ng) "
        "or set OPENAI_API_KEY in your environment."
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

    # Gentle chord tones (D minor - more contemplative)
    for freq, vol, name in [
        (146.83, 0.025, "tone_d"),     # D3
        (174.61, 0.018, "tone_f"),     # F3
        (220.00, 0.018, "tone_a"),     # A3
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
         "-i", str(temp_dir / "tone_d.wav"),
         "-i", str(temp_dir / "tone_f.wav"),
         "-i", str(temp_dir / "tone_a.wav"),
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
    profile = MOTION_PROFILES.get(slide_type, MOTION_PROFILES["concept"])
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


def assemble_video(slides: list[AISlide], output_dir: Path) -> Path:
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
        profile_name = slide.slide_type if slide.slide_type in MOTION_PROFILES else "concept"
        profile = MOTION_PROFILES.get(profile_name, MOTION_PROFILES["concept"])
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
        temp_mp4 = output_dir / "ai_video_no_audio.mp4"
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

        temp_mp4 = output_dir / "ai_video_no_audio.mp4"
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
    output_mp4 = output_dir / "how_ai_understands_language.mp4"
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
    srt_path = output_dir / "how_ai_understands_language.srt"
    srt_path.write_text(generate_srt(slides, int(actual_video_dur)), encoding="utf-8")

    return output_mp4


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  How AI Understands Language - Educational Video")
    print("  Motion graphics + crossfade transitions + ambient audio")
    print("=" * 60)
    print(f"\nSlides: {len(SLIDES)}")
    actual_dur = TOTAL_DURATION - (len(SLIDES) - 1) * TRANSITION_DUR
    print(f"Total duration: {TOTAL_DURATION}s → {actual_dur:.1f}s (with {TRANSITION_DUR}s crossfades)")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    for s in SLIDES:
        profile = MOTION_PROFILES.get(s.slide_type, MOTION_PROFILES["concept"])
        print(f"  [{s.slide_type:12s}] {s.duration:2d}s  {profile['desc']}")

    print()
    output_mp4 = assemble_video(SLIDES, OUTPUT_DIR)

    srt_path = OUTPUT_DIR / "how_ai_understands_language.srt"
    print(f"\n✓ Video generated: {output_mp4}")
    print(f"✓ Subtitles: {srt_path}")
    final_dur = TOTAL_DURATION - (len(SLIDES) - 1) * TRANSITION_DUR
    print(f"✓ Video duration: {final_dur:.1f}s ({int(final_dur // 60)}m {int(final_dur % 60)}s)")
    print(f"✓ File size: {output_mp4.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
