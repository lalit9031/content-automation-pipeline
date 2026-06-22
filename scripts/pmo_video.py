#!/usr/bin/env python3
"""PMO Educational Video Generator

Generates a management educational video about PMO (Project Management Office)
with custom-designed slides, professional motion graphics, smooth crossfade
transitions, and SRT subtitles.

Usage:
    python scripts/pmo_video.py

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
OUTPUT_DIR = Path("output/pmo_video")
FPS = 30
TRANSITION_DUR = 0.4  # Crossfade duration between slides


@dataclass(frozen=True)
class PMOSlide:
    text_on_screen: str
    duration: int
    narration: str
    slide_type: str  # matches keys in MOTION_PROFILES


# ── Slide Definitions ──────────────────────────────────────────────────────

SLIDES = [
    PMOSlide(
        text_on_screen=(
            "PMO\nProject Management Office\n"
            "Driving project success with structure and control"
        ),
        duration=12,
        narration=(
            "PMO stands for Project Management Office. It's the central hub that helps "
            "organizations manage projects in a structured and successful way. "
            "Think of it as the air traffic control for all your projects."
        ),
        slide_type="title",
    ),
    PMOSlide(
        text_on_screen=(
            "What is PMO?\n\n"
            "A PMO is a team that supports\nproject planning, tracking, and delivery."
        ),
        duration=28,
        narration=(
            "A PMO is a dedicated team that provides guidance, standards, and support to "
            "project teams across the organization. It makes sure every project follows "
            "the right process and stays on track. For example, imagine a software company "
            "building a new mobile app. The PMO ensures the design, development, and "
            "testing teams all use the same planning tools, report progress consistently, "
            "and resolve issues before they escalate."
        ),
        slide_type="definition",
    ),
    PMOSlide(
        text_on_screen=(
            "Key Responsibilities\n\n"
            "•  Project planning\n"
            "•  Risk tracking\n"
            "•  Status reporting\n"
            "•  Resource management\n"
            "•  Governance"
        ),
        duration=38,
        narration=(
            "The PMO handles five critical responsibilities. First, project planning: "
            "creating realistic schedules and allocating resources. For instance, a PMO "
            "might use Gantt charts to map every phase of a product launch. Second, risk "
            "tracking: identifying potential issues early, like a supplier delay that could "
            "impact your timeline. Third, status reporting: giving leadership clear, honest "
            "updates on project health. Fourth, resource management: ensuring the right "
            "people are working on the right projects. And fifth, governance: making sure "
            "every project follows company policies and industry regulations."
        ),
        slide_type="list",
    ),
    PMOSlide(
        text_on_screen=(
            "Why PMO is Important\n\n"
            "✓  Visibility\n"
            "✓  Control\n"
            "✓  Delivery quality\n"
            "✓  Decision-making"
        ),
        duration=26,
        narration=(
            "Without a PMO, projects often face frequent delays, unclear ownership where "
            "nobody knows who's responsible, and poor communication between teams. "
            "This leads to chaotic, over-budget outcomes. But with a PMO, leadership gets "
            "full visibility into every project, maintains control through standardized "
            "processes, delivers higher quality results, and makes better data-driven "
            "decisions. The result is on-time, on-budget delivery with happy stakeholders."
        ),
        slide_type="comparison",
    ),
    PMOSlide(
        text_on_screen=(
            "PMO in Action\n\n"
            "Timeline  |  Budget  |  Risks  |  Issues  |  Progress"
        ),
        duration=32,
        narration=(
            "A PMO uses a project dashboard to track five key metrics. Timeline: are we "
            "on schedule? Budget: are we spending as planned? Risks: what could go wrong? "
            "Issues: what problems have come up? And progress: how much is complete? "
            "Each metric gets a color status. Green means good, yellow means watch closely, "
            "and red means urgent action is needed. For example, if a project's budget "
            "runs ten percent over, it shows yellow as a warning before it becomes critical."
        ),
        slide_type="dashboard",
    ),
    PMOSlide(
        text_on_screen=(
            "PMO Maturity Levels\n\n"
            "Supportive"
        ),
        duration=35,
        narration=(
            "PMO maturity typically follows three progressive levels. "
            "Level one is Supportive: the PMO provides templates, best practices, "
            "training, and lessons learned. It acts as a consultant to project teams. "
            "Level two is Controlling: the PMO requires compliance with project "
            "management standards, conducts regular audits, and enforces processes "
            "across all projects. Level three is Directive: the PMO directly manages "
            "projects and assigns project managers to deliver results. Most organizations "
            "start at Supportive and progress through these levels as their project "
            "management capability matures over time."
        ),
        slide_type="maturity",
    ),
    PMOSlide(
        text_on_screen=(
            "PMO Success Metrics\n\n"
            "On-time delivery"
        ),
        duration=32,
        narration=(
            "How do you measure PMO success? "
            "The five key metrics are: on-time delivery, the percentage of projects "
            "completed by their original deadline; budget adherence, how well projects "
            "stay within their approved budget; stakeholder satisfaction, measured through "
            "surveys and feedback after each project; risk mitigation, how effectively "
            "risks are identified and resolved before they become issues; and resource "
            "utilization, ensuring team members are assigned to the right projects "
            "without being over-allocated. A mature PMO tracks all five metrics and "
            "uses them to drive continuous improvement across the organization."
        ),
        slide_type="metrics",
    ),
    PMOSlide(
        text_on_screen=(
            "How PMO Helps the Team\n\n"
            "1. Provides standard processes\n"
            "2. Offers coaching and mentoring\n"
            "3. Cross-project visibility\n"
            "4. Removes roadblocks\n"
            "5. Data-driven insights"
        ),
        duration=38,
        narration=(
            "How exactly does a PMO help the team? First, it provides standard processes and "
            "templates so every project starts on solid ground instead of reinventing the wheel. "
            "Second, it offers coaching and mentoring to project managers who are new or "
            "need guidance. Third, it gives cross-project visibility, so if one project has "
            "a bottleneck, another team can help. Fourth, the PMO actively removes roadblocks "
            "by escalating issues to leadership and resolving dependencies between teams. "
            "And fifth, it provides data-driven insights through dashboards and reports, "
            "so teams always know where they stand and can make informed decisions."
        ),
        slide_type="benefits",
    ),
    PMOSlide(
        text_on_screen=(
            "Tools PMOs Use\n\n"
            "\U0001f527  Jira \u2014 Issue & sprint tracking\n"
            "\U0001f527  Microsoft Project \u2014 Gantt & scheduling\n"
            "\U0001f527  Smartsheet \u2014 Collaborative planning\n"
            "\U0001f527  Confluence \u2014 Documentation & wikis\n"
            "\U0001f527  Tableau / Power BI \u2014 Dashboards & analytics"
        ),
        duration=30,
        narration=(
            "PMOs rely on a suite of powerful tools to keep projects organized. Jira is the "
            "go-to for issue tracking and sprint management in agile teams. Microsoft Project "
            "provides detailed Gantt charts and scheduling for complex timelines. Smartsheet "
            "offers a collaborative spreadsheet-style planning surface that works across "
            "departments. Confluence serves as the central documentation hub for project wikis, "
            "meeting notes, and process guides. And tools like Tableau or Power BI transform "
            "project data into visual dashboards that give leadership real-time status at a glance."
        ),
        slide_type="tools",
    ),
    PMOSlide(
        text_on_screen=(
            "Common PMO Challenges\n\n"
            "Resistance to Change"
        ),
        duration=40,
        narration=(
            "PMOs often face five common challenges and each has a practical solution. "
            "First, resistance to change: teams are used to working independently. "
            "The solution is to demonstrate quick wins early, like showing how a simple "
            "template saves hours of planning time. Second, lack of executive sponsorship: "
            "without leadership backing, the PMO struggles to enforce standards. "
            "The solution is to build a compelling business case using metrics that show "
            "how the PMO saves money and reduces risk. Third, too much bureaucracy: "
            "if processes feel heavy, teams will bypass them. The solution is to right-size "
            "processes to the organization's needs, keeping things lean and practical. "
            "Fourth, inadequate resources: PMOs are often understaffed. The solution is "
            "to prioritize high-impact projects and automate repetitive reporting tasks. "
            "And fifth, an unclear mandate: without a defined charter, nobody knows what "
            "the PMO is supposed to do. The solution is to clearly define the PMO charter, "
            "scope, and success criteria from day one."
        ),
        slide_type="challenges",
    ),
    PMOSlide(
        text_on_screen=(
            "PMO Implementation Roadmap\n\n"
            "Step 1: Assess Current State\n"
            "Step 2: Define PMO Charter\n"
            "Step 3: Choose Maturity Level\n"
            "Step 4: Establish Processes & Tools\n"
            "Step 5: Build the Team\n"
            "Step 6: Launch & Iterate"
        ),
        duration=50,
        narration=(
            "Setting up a PMO follows a proven six-step roadmap. "
            "Step one: assess your current state. Evaluate your organization's project management "
            "maturity, identify gaps, and understand what your teams need most. "
            "Step two: define the PMO charter. Clearly document the PMO's mission, scope, authority, "
            "and success criteria. Get executive sponsorship before moving forward. "
            "Step three: choose your target maturity level. Decide whether to start with a supportive, "
            "controlling, or directive model based on your organization's culture. "
            "Step four: establish processes and tools. Select your project management methodology, "
            "define standard templates, and choose the right tool stack. "
            "Step five: build the team. Hire or assign the right people, define roles, "
            "and provide thorough training on the new processes. "
            "Step six: launch and iterate. Start with a pilot project, gather feedback, "
            "measure success metrics, and continuously improve. "
            "Remember, a PMO is not built in a single day. It evolves and matures over time "
            "through continuous iteration and learning."
        ),
        slide_type="roadmap",
    ),
    PMOSlide(
        text_on_screen=(
            "PM  vs  PMO  vs  SM  vs  Program Manager"
        ),
        duration=50,
        narration=(
            "It's important to understand how these four roles differ. A Project Manager, or PM, "
            "is a single person responsible for the day-to-day management of one specific project. "
            "The PMO is a team or department that sets standards and supports multiple projects "
            "across the organization. A Scrum Master is an agile coach who facilitates the team "
            "process, removes impediments, and protects the team from distractions. A Program "
            "Manager oversees a group of related projects, called a program, ensuring they "
            "collectively deliver a larger business outcome. In short, the PM manages one project, "
            "the PMO supports many, the Scrum Master coaches the agile team, and the Program "
            "Manager coordinates multiple related projects toward a shared strategic goal."
        ),
        slide_type="roles_table",
    ),
    PMOSlide(
        text_on_screen=(
            "PMO = Better Planning\n+ Better Control\n+ Better Results"
        ),
        duration=26,
        narration=(
            "In summary, a PMO helps organizations deliver projects on time, with better "
            "quality and better results. It brings structure, clarity, and accountability "
            "to every project. Whether you're building a skyscraper, launching a new "
            "product, or implementing new software, a PMO gives you the best chance of "
            "success. Remember: PMO equals better planning, plus better control, plus "
            "better results."
        ),
        slide_type="closing",
    ),
]

TOTAL_DURATION = sum(s.duration for s in SLIDES)


# ── Motion Profiles ────────────────────────────────────────────────────────
# Each slide type gets a different camera motion for visual variety.
# zoompan expressions: z=zoom, x=pan-x, y=pan-y

MOTION_PROFILES: dict[str, dict[str, str | float]] = {
    "title": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0035,1.045))",
        "desc": "Slow cinematic zoom in",
    },
    "definition": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0025,1.035))",
        "x": "iw/2-(iw/zoom/2)+8*sin(on/120)",
        "y": "ih/2-(ih/zoom/2)",
        "desc": "Subtle zoom + gentle horizontal sway",
    },
    "list": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0018,1.03))",
        "y": "ih/2-(ih/zoom/2) + 4*sin(on/90)",
        "desc": "Subtle zoom + vertical float",
    },
    "comparison": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.002,1.03))",
        "x": "iw/2-(iw/zoom/2) - 6*sin(on/150)",
        "desc": "Gentle horizontal reveal pan",
    },
    "dashboard": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0032,1.04))",
        "desc": "Slow zoom emphasizing data",
    },
    "benefits": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0015,1.02))",
        "desc": "Ultra subtle micro-motion",
    },
    "tools": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.002,1.03))",
        "desc": "Subtle zoom across tool cards",
    },
    "maturity": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0012,1.02))",
        "desc": "Very subtle, focused on structure",
    },
    "metrics": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.003,1.04))",
        "x": "iw/2-(iw/zoom/2)+5*sin(on/180)",
        "desc": "Data reveal with gentle sway",
    },
    "roles_table": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.001,1.015))",
        "desc": "Ultra subtle for table readability",
    },
    "challenges": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0022,1.03))",
        "x": "iw/2-(iw/zoom/2)+4*sin(on/140)",
        "desc": "Subtle zoom + gentle sway for challenge/reveal",
    },
    "roadmap": {
        "z": "if(lte(zoom,1.0),1.0,min(zoom+0.0018,1.025))",
        "x": "iw/2-(iw/zoom/2)+5*sin(on/160)",
        "desc": "Gentle pan across timeline roadmap",
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
    <!-- Floating dot pattern for depth -->
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
  <text x="76" y="710" font-family="Arial, sans-serif" font-size="13" font-weight="500" fill="#64748b" letter-spacing="1">PMO \u2014 PROJECT MANAGEMENT OFFICE</text>
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

def _title_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    lines = slide.text_on_screen.split("\n")
    title_lines = [lines[0]] if lines else ["PMO"]
    subtitle_lines = lines[1:3] if len(lines) >= 3 else [""]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_floating_dots(8, 640, 360, 250)}
  <!-- Large letter blocks -->
  <rect x="520" y="160" width="240" height="220" rx="28" fill="#1e3a5f" stroke="#3b82f6" stroke-width="2" opacity="0.12"/>
  <rect x="560" y="180" width="160" height="140" rx="20" fill="#1e3a5f" stroke="#f59e0b" stroke-width="2" opacity="0.08"/>
  {_pill("MANAGEMENT EDUCATION", 640, 85, 260, centered=True)}
  {_text_block(title_lines, 640, 200, 72, 78, "#f8fafc", "middle", "700")}
  {_text_block(subtitle_lines, 640, 360, 24, 40, "#94a3b8", "middle", "400")}
  <!-- Decorative rings -->
  <circle cx="640" cy="510" r="100" fill="none" stroke="#f59e0b" stroke-width="1.5" opacity="0.12"/>
  <circle cx="640" cy="510" r="70" fill="none" stroke="#3b82f6" stroke-width="1.5" opacity="0.18"/>
  <circle cx="640" cy="510" r="40" fill="none" stroke="#22c55e" stroke-width="1" opacity="0.12"/>
  {_bottom_bar(seconds, total)}
</svg>"""


def _definition_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    body = parts[1] if len(parts) > 1 else ""
    body_lines = _wrap(body, 34)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("KEY CONCEPT", 640, 70, 170, centered=True)}
  {_text_block([title], 640, 135, 40, 48, "#f8fafc", "middle", "700")}
  {_section_divider(120, 190, 1040)}
  {_text_block(body_lines, 120, 230, 24, 38, "#cbd5e1", "start", "400")}
  <!-- Team/dashboard visual panel -->
  <g transform="translate(780, 120)">
    <rect x="0" y="60" width="400" height="340" rx="18" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
    <rect x="0" y="60" width="400" height="40" rx="18" fill="#1e3a5f"/>
    <rect x="0" y="82" width="400" height="18" fill="#1e3a5f"/>
    <text x="20" y="88" font-family="Arial, sans-serif" font-size="13" font-weight="600" fill="#64748b" letter-spacing="1">PROJECT DASHBOARD \u2014 TEAM OVERVIEW</text>
    <!-- Progress bars with labels -->
    <text x="20" y="125" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8">Planning \u2014 78%</text>
    <rect x="20" y="133" width="360" height="8" rx="4" fill="#334155"/>
    <rect x="20" y="133" width="281" height="8" rx="4" fill="#22c55e"/>
    <text x="20" y="162" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8">Development \u2014 62%</text>
    <rect x="20" y="170" width="360" height="8" rx="4" fill="#334155"/>
    <rect x="20" y="170" width="223" height="8" rx="4" fill="#3b82f6"/>
    <text x="20" y="199" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8">Testing \u2014 45%</text>
    <rect x="20" y="207" width="360" height="8" rx="4" fill="#334155"/>
    <rect x="20" y="207" width="162" height="8" rx="4" fill="#f59e0b"/>
    <text x="20" y="236" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8">Deployment \u2014 30%</text>
    <rect x="20" y="244" width="360" height="8" rx="4" fill="#334155"/>
    <rect x="20" y="244" width="108" height="8" rx="4" fill="#ef4444"/>
    <!-- Team section -->
    <line x1="20" y1="270" x2="380" y2="270" stroke="#334155" stroke-width="1"/>
    <text x="20" y="295" font-family="Arial, sans-serif" font-size="12" font-weight="600" fill="#64748b" letter-spacing="1">TEAM MEMBERS (6)</text>
    <circle cx="30" cy="330" r="20" fill="#334155"/>
    <circle cx="85" cy="330" r="20" fill="#334155"/>
    <circle cx="140" cy="330" r="20" fill="#334155"/>
    <circle cx="195" cy="330" r="20" fill="#334155"/>
    <circle cx="250" cy="330" r="20" fill="#334155"/>
    <circle cx="305" cy="330" r="20" fill="#334155"/>
    <text x="30" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">PM</text>
    <text x="85" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">Dev</text>
    <text x="140" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">QA</text>
    <text x="195" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">UX</text>
    <text x="250" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">Ops</text>
    <text x="305" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">PO</text>
  </g>
  {_bottom_bar(seconds, total)}
</svg>"""


def _list_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    items_raw = parts[1] if len(parts) > 1 else ""
    items = [line.strip() for line in items_raw.split("\n") if line.strip()]

    # Enhanced icon row
    icons_data = [
        ("\U0001f4cb", "PLAN", "#3b82f6", "#1e3a5f"),
        ("\u26a0\ufe0f", "RISK", "#f59e0b", "#1e1e0f"),
        ("\U0001f4ca", "REPORT", "#22c55e", "#0f1e12"),
        ("\U0001f465", "PEOPLE", "#a855f7", "#1e0f2e"),
        ("\u2696\ufe0f", "GOVERN", "#f97316", "#1e140e"),
    ]
    icons_svg = ""
    for idx, (icon, label, accent, bg) in enumerate(icons_data):
        ix = 80 + idx * 240
        icons_svg += f"""\
    <g transform="translate({ix}, 430)">
      <rect x="0" y="0" width="200" height="90" rx="16" fill="{bg}" stroke="{accent}" stroke-width="1.5" opacity="0.9"/>
      <rect x="0" y="0" width="200" height="5" rx="16" fill="{accent}" opacity="0.6"/>
      <text x="28" y="40" text-anchor="middle" font-size="22" fill="{accent}">{icon}</text>
      <text x="28" y="68" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="700" fill="{accent}" opacity="0.8" letter-spacing="1.5">{label}</text>
      <!-- Subtle glow dot -->
      <circle cx="172" cy="18" r="3" fill="{accent}" opacity="0.3"/>
    </g>"""

    list_lines = []
    for item in items:
        clean = item.replace("\u2022 ", "").strip()
        list_lines.append(f"\u25b8  {clean}")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("RESPONSIBILITIES", 640, 65, 200, centered=True)}
  {_text_block([title], 640, 125, 36, 44, "#f8fafc", "middle", "700")}
  {_section_divider(200, 170, 880)}
  {_text_block(list_lines, 200, 195, 24, 46, "#cbd5e1", "start", "400")}
  {icons_svg}
  {_bottom_bar(seconds, total)}
</svg>"""


def _comparison_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    before_panel = """\
  <rect x="70" y="220" width="530" height="380" rx="18" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
  <rect x="70" y="220" width="530" height="54" rx="18" fill="#450a0a"/>
  <rect x="70" y="256" width="530" height="18" fill="#450a0a"/>
  <text x="335" y="256" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#fca5a5" letter-spacing="2">\u2606  WITHOUT PMO  \u2606</text>
  <!-- Items -->
  <text x="120" y="320" font-family="Arial, sans-serif" font-size="20" fill="#ef4444">\u2717</text>
  <text x="155" y="324" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">Frequent delays and missed deadlines</text>
  <line x1="120" y1="338" x2="540" y2="338" stroke="#334155" stroke-width="0.5"/>
  <text x="120" y="378" font-family="Arial, sans-serif" font-size="20" fill="#ef4444">\u2717</text>
  <text x="155" y="382" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">Unclear ownership and responsibilities</text>
  <line x1="120" y1="396" x2="540" y2="396" stroke="#334155" stroke-width="0.5"/>
  <text x="120" y="436" font-family="Arial, sans-serif" font-size="20" fill="#ef4444">\u2717</text>
  <text x="155" y="440" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">Poor communication across teams</text>
  <line x1="120" y1="454" x2="540" y2="454" stroke="#334155" stroke-width="0.5"/>
  <rect x="145" y="500" width="380" height="54" rx="27" fill="#ef4444" opacity="0.12"/>
  <text x="335" y="534" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" fill="#fca5a5" font-weight="600">\u2757  Over-budget, delayed, low quality</text>"""

    after_panel = """\
  <rect x="680" y="220" width="530" height="380" rx="18" fill="#0f2a1e" stroke="#22c55e" stroke-width="1.5"/>
  <rect x="680" y="220" width="530" height="54" rx="18" fill="#052e16"/>
  <rect x="680" y="256" width="530" height="18" fill="#052e16"/>
  <text x="945" y="256" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#4ade80" letter-spacing="2">\u2606  WITH PMO  \u2606</text>
  <!-- Items -->
  <text x="730" y="320" font-family="Arial, sans-serif" font-size="20" fill="#22c55e">\u2713</text>
  <text x="765" y="324" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">Better visibility and transparency</text>
  <line x1="730" y1="338" x2="1150" y2="338" stroke="#1a3a2a" stroke-width="0.5"/>
  <text x="730" y="378" font-family="Arial, sans-serif" font-size="20" fill="#22c55e">\u2713</text>
  <text x="765" y="382" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">Full control and accountability</text>
  <line x1="730" y1="396" x2="1150" y2="396" stroke="#1a3a2a" stroke-width="0.5"/>
  <text x="730" y="436" font-family="Arial, sans-serif" font-size="20" fill="#22c55e">\u2713</text>
  <text x="765" y="440" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">Higher quality delivery</text>
  <line x1="730" y1="454" x2="1150" y2="454" stroke="#1a3a2a" stroke-width="0.5"/>
  <rect x="745" y="500" width="380" height="54" rx="27" fill="#22c55e" opacity="0.12"/>
  <text x="935" y="534" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" fill="#86efac" font-weight="600">\u2705  On-time, on-budget, quality delivered</text>"""

    arrow = """\
  <rect x="614" y="375" width="52" height="52" rx="26" fill="#f59e0b" opacity="0.12"/>
  <text x="640" y="408" text-anchor="middle" font-family="Arial, sans-serif" font-size="24" fill="#f59e0b" font-weight="700">\u2192</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("BEFORE vs AFTER", 640, 50, 220, centered=True)}
  {_text_block([title], 640, 110, 28, 36, "#f8fafc", "middle", "700")}
  <text x="640" y="142" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">How PMO transforms project outcomes</text>
  {before_panel}
  {arrow}
  {after_panel}
  {_bottom_bar(seconds, total)}
</svg>"""


def _dashboard_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    subtitle = parts[1] if len(parts) > 1 else ""
    sub_lines = _wrap(subtitle, 50) if subtitle else [""]

    dashboard = """\
  <rect x="160" y="240" width="960" height="400" rx="22" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
  <!-- Header -->
  <rect x="160" y="240" width="960" height="48" rx="22" fill="#1e3a5f"/>
  <rect x="160" y="270" width="960" height="18" fill="#1e3a5f"/>
  <text x="200" y="272" font-family="Arial, sans-serif" font-size="14" font-weight="600" fill="#64748b" letter-spacing="1">PROJECT STATUS DASHBOARD</text>
  <circle cx="1070" cy="264" r="6" fill="#22c55e"/>
  <text x="1085" y="268" font-family="Arial, sans-serif" font-size="11" fill="#64748b">LIVE</text>
  <!-- Rows -->
  <text x="200" y="325" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Timeline</text>
  <rect x="380" y="310" width="680" height="20" rx="10" fill="#334155"/>
  <rect x="380" y="310" width="530" height="20" rx="10" fill="#22c55e"/>
  <text x="1080" y="326" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#22c55e" font-weight="700">ON TRACK</text>
  <text x="200" y="375" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Budget</text>
  <rect x="380" y="360" width="680" height="20" rx="10" fill="#334155"/>
  <rect x="380" y="360" width="440" height="20" rx="10" fill="#f59e0b"/>
  <text x="1080" y="376" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#f59e0b" font-weight="700">AT RISK</text>
  <text x="200" y="425" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Risks</text>
  <rect x="380" y="410" width="680" height="20" rx="10" fill="#334155"/>
  <rect x="380" y="410" width="600" height="20" rx="10" fill="#22c55e"/>
  <text x="1080" y="426" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#22c55e" font-weight="700">MANAGED</text>
  <text x="200" y="475" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Issues</text>
  <rect x="380" y="460" width="680" height="20" rx="10" fill="#334155"/>
  <rect x="380" y="460" width="320" height="20" rx="10" fill="#ef4444"/>
  <text x="1080" y="476" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#ef4444" font-weight="700">CRITICAL</text>
  <text x="200" y="525" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#94a3b8">Progress</text>
  <rect x="380" y="510" width="680" height="20" rx="10" fill="#334155"/>
  <rect x="380" y="510" width="460" height="20" rx="10" fill="#3b82f6"/>
  <text x="1080" y="526" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#3b82f6" font-weight="700">68% DONE</text>
  <!-- Legend -->
  <rect x="380" y="555" width="320" height="30" rx="8" fill="#0f172a"/>
  <circle cx="400" cy="570" r="5" fill="#22c55e"/>
  <text x="415" y="574" font-family="Arial, sans-serif" font-size="11" fill="#94a3b8">Green = Good</text>
  <circle cx="490" cy="570" r="5" fill="#f59e0b"/>
  <text x="505" y="574" font-family="Arial, sans-serif" font-size="11" fill="#94a3b8">Yellow = Watch</text>
  <circle cx="580" cy="570" r="5" fill="#ef4444"/>
  <text x="595" y="574" font-family="Arial, sans-serif" font-size="11" fill="#94a3b8">Red = Action needed</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("TRACKING", 640, 65, 150, centered=True)}
  {_text_block([title], 640, 120, 30, 38, "#f8fafc", "middle", "700")}
  {_text_block(sub_lines, 640, 165, 20, 30, "#94a3b8", "middle", "400")}
  {dashboard}
  {_bottom_bar(seconds, total)}
</svg>"""


def _benefits_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    benefit_details = [
        ("01", "STANDARD PROCESSES", "Repeatable templates, consistent methods\u2026", "#3b82f6"),
        ("02", "COACHING & MENTORING", "Guidance for new PMs, skill-building\u2026", "#22c55e"),
        ("03", "CROSS-PROJECT VIEW", "Spot bottlenecks, share resources\u2026", "#f59e0b"),
        ("04", "REMOVES ROADBLOCKS", "Escalates issues, resolves dependencies\u2026", "#a855f7"),
        ("05", "DATA-DRIVEN INSIGHTS", "Real-time dashboards, trend analysis\u2026", "#ef4444"),
    ]

    benefit_cards = ""
    for idx, (num, label, desc, accent) in enumerate(benefit_details):
        col = idx % 3
        row = idx // 3
        cx = 100 + col * 400
        cy = 210 + row * 220
        cw = 360
        ch = 190

        benefit_cards += f"""\
    <g transform="translate({cx}, {cy})">
      <rect x="0" y="0" width="{cw}" height="{ch}" rx="16" fill="#1e293b" stroke="{accent}" stroke-width="1.5" opacity="0.85"/>
      <rect x="0" y="0" width="{cw}" height="6" rx="16" fill="{accent}" opacity="0.7"/>
      <text x="16" y="46" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="{accent}" letter-spacing="1">{num}</text>
      <text x="52" y="46" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#f8fafc">{escape(label)}</text>
      <line x1="16" y1="62" x2="{cw - 16}" y2="62" stroke="{accent}" stroke-width="0.5" opacity="0.3"/>
      <text x="16" y="90" font-family="Arial, sans-serif" font-size="13" fill="#94a3b8">{escape(desc[:42])}</text>
      <text x="16" y="112" font-family="Arial, sans-serif" font-size="13" fill="#94a3b8">{escape(desc[42:84])}</text>
      <!-- Accent corner -->
      <rect x="{cw - 24}" y="{ch - 24}" width="24" height="24" rx="0" fill="{accent}" opacity="0.08"/>
      <rect x="{cw - 24}" y="{ch - 2}" width="24" height="2" rx="0" fill="{accent}" opacity="0.2"/>
    </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("TEAM BENEFITS", 640, 60, 210, centered=True)}
  {_text_block([title], 640, 115, 30, 38, "#f8fafc", "middle", "700")}
  {_section_divider(200, 160, 880)}
{benefit_cards}
  {_bottom_bar(seconds, total)}
</svg>"""


def _tools_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    body = parts[1] if len(parts) > 1 else ""
    items = [line.strip() for line in body.split("\n") if line.strip()]

    tool_icons = {
        "Jira": {"icon": "\U0001f4cb", "color": "#3b82f6"},
        "Microsoft Project": {"icon": "\U0001f4c5", "color": "#22c55e"},
        "Smartsheet": {"icon": "\U0001f4ca", "color": "#f59e0b"},
        "Confluence": {"icon": "\U0001f4dd", "color": "#a855f7"},
        "Tableau / Power BI": {"icon": "\U0001f4c8", "color": "#ef4444"},
    }

    tool_cards = ""
    for idx, item in enumerate(items):
        clean = item.replace("\U0001f527  ", "").strip()
        if "\u2014" in clean:
            tool_name, tool_desc = clean.split("\u2014", 1)
            tool_name = tool_name.strip()
            tool_desc = tool_desc.strip()
        else:
            tool_name = clean
            tool_desc = ""

        info = tool_icons.get(tool_name, {"icon": "\U0001f527", "color": "#64748b"})

        row = idx // 3
        col = idx % 3
        cx = 90 + col * 395
        cy = 210 + row * 230
        cw = 350
        ch = 190

        tool_cards += f"""\
    <g transform="translate({cx}, {cy})">
      <rect x="0" y="0" width="{cw}" height="{ch}" rx="18" fill="#1e293b" stroke="{info["color"]}" stroke-width="1.5" opacity="0.85"/>
      <rect x="0" y="0" width="{cw}" height="16" rx="18" fill="{info["color"]}" opacity="0.5"/>
      <rect x="0" y="10" width="{cw}" height="6" fill="{info["color"]}" opacity="0.5"/>
      <text x="{cw / 2}" y="70" text-anchor="middle" font-size="38" fill="{info["color"]}">{info["icon"]}</text>
      <text x="{cw / 2}" y="115" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#f8fafc">{escape(tool_name)}</text>
      <text x="{cw / 2}" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8">{escape(tool_desc[:48])}</text>
      <!-- Hover-like glow -->
      <circle cx="{cw / 2}" cy="55" r="25" fill="{info["color"]}" opacity="0.06"/>
    </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("PMO TOOLKIT", 640, 55, 190, centered=True)}
  {_text_block([title], 640, 105, 30, 38, "#f8fafc", "middle", "700")}
  <text x="640" y="140" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">Essential software used by PMOs worldwide</text>
{tool_cards}
  {_bottom_bar(seconds, total)}
</svg>"""


def _roles_table_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    title = slide.text_on_screen.strip()

    table_header = """\
  <rect x="60" y="180" width="1160" height="440" rx="16" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
  <!-- Table header -->
  <rect x="60" y="180" width="1160" height="52" rx="16" fill="#1e3a5f"/>
  <rect x="60" y="214" width="1160" height="18" fill="#1e3a5f"/>
  <text x="170" y="214" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#f59e0b" letter-spacing="1">ROLE</text>
  <line x1="280" y1="180" x2="280" y2="620" stroke="#334155" stroke-width="1"/>
  <text x="430" y="214" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#f59e0b" letter-spacing="1">FOCUS</text>
  <line x1="580" y1="180" x2="580" y2="620" stroke="#334155" stroke-width="1"/>
  <text x="730" y="214" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#f59e0b" letter-spacing="1">SCOPE</text>
  <line x1="880" y1="180" x2="880" y2="620" stroke="#334155" stroke-width="1"/>
  <text x="1080" y="214" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#f59e0b" letter-spacing="1">KEY RESPONSIBILITY</text>"""

    hl_colors = ["#3b82f6", "#f59e0b", "#22c55e", "#a855f7"]
    rows_data = [
        ("PM", "Execution", "Single project", "Day-to-day planning, tracking, delivery"),
        ("PMO", "Standardization", "Multiple projects across org", "Set standards, govern, support teams"),
        ("SM", "Agile Coaching", "Single agile team", "Facilitate Scrum, remove impediments"),
        ("Program Mgr", "Strategic Alignment", "Group of related projects", "Coordinate toward a shared goal"),
    ]

    table_rows = ""
    for i, (role, focus, scope, responsibility) in enumerate(rows_data):
        ry = 248 + i * 88
        bg = "#0f172a" if i % 2 == 0 else "#1e293b"
        hl = hl_colors[i]

        table_rows += f"""\
  <rect x="61" y="{ry}" width="219" height="88" fill="{bg}"/>
  <rect x="61" y="{ry + 20}" width="4" height="48" rx="2" fill="{hl}"/>
  <text x="170" y="{ry + 54}" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#f8fafc">{escape(role)}</text>
  <text x="430" y="{ry + 54}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#cbd5e1">{escape(focus)}</text>
  <text x="730" y="{ry + 54}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#94a3b8">{escape(scope)}</text>
  <text x="1080" y="{ry + 54}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">{escape(responsibility[:42])}</text>
  <line x1="60" y1="{ry + 88}" x2="1220" y2="{ry + 88}" stroke="#334155" stroke-width="0.5"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("ROLES COMPARISON", 640, 45, 250, centered=True)}
  {_text_block([title], 640, 105, 26, 34, "#f8fafc", "middle", "700")}
  <text x="640" y="138" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">Understanding the difference between project roles</text>
{table_header}
{table_rows}
  <rect x="200" y="640" width="880" height="46" rx="23" fill="#1e3a5f" opacity="0.5"/>
  <text x="640" y="668" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#94a3b8">\u2139\ufe0f  PM manages one project \u00b7 PMO supports many \u00b7 SM coaches the team \u00b7 Program Mgr aligns the program</text>
  {_bottom_bar(seconds, total)}
</svg>"""


def _maturity_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    level_data = [
        ("Level 1", "Supportive", "Advisory / Consultant role", "#22c55e",
         ["Provides templates & best practices", "Training & mentoring teams", "Shares lessons learned", "Low authority, high influence"]),
        ("Level 2", "Controlling", "Governance / Oversight role", "#3b82f6",
         ["Enforces compliance & standards", "Conducts regular audits", "Monitors performance", "Moderate authority"]),
        ("Level 3", "Directive", "Management / Ownership role", "#f59e0b",
         ["Directly manages projects", "Assigns project managers", "Owns portfolio outcomes", "High authority & accountability"]),
    ]

    cards = ""
    stairs_svg = ""
    for i, (lvl, name, subtitle, accent, chars) in enumerate(level_data):
        cx = 100 + i * 400
        cy = 180 + (2 - i) * 55
        bw = 360
        bh = 420

        # Connection arrow between levels
        if i < len(level_data) - 1:
            next_cx = 100 + (i + 1) * 400
            next_cy = 180 + (2 - (i + 1)) * 55
            ax1 = cx + bw
            ay1 = cy + bh // 2
            ax2 = next_cx
            ay2 = next_cy + bh // 2
            stairs_svg += f"""\
    <line x1="{ax1}" y1="{ay1}" x2="{ax2 - 10}" y2="{ay2}" stroke="{accent}" stroke-width="3" stroke-dasharray="8,4" opacity="0.4"/>
    <polygon points="{ax2 - 10},{ay2 - 6} {ax2},{ay2} {ax2 - 10},{ay2 + 6}" fill="{accent}" opacity="0.4"/>"""

        cards += f"""\
    <g transform="translate({cx}, {cy})">
      <rect x="0" y="0" width="{bw}" height="{bh}" rx="20" fill="#0f172a" stroke="{accent}" stroke-width="2" opacity="0.9"/>
      <rect x="0" y="0" width="{bw}" height="64" rx="20" fill="{accent}" opacity="0.12"/>
      <rect x="0" y="34" width="{bw}" height="30" fill="{accent}" opacity="0.12"/>
      <circle cx="{bw // 2}" cy="32" r="20" fill="{accent}" opacity="0.2"/>
      <text x="{bw // 2}" y="37" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="{accent}">{escape(lvl)}</text>
      <text x="{bw // 2}" y="90" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="{accent}">{escape(name)}</text>
      <text x="{bw // 2}" y="115" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8" letter-spacing="1">{escape(subtitle)}</text>
      <line x1="30" y1="132" x2="{bw - 30}" y2="132" stroke="{accent}" stroke-width="1" opacity="0.25"/>
      <!-- Maturity bar -->
      <rect x="40" y="150" width="{bw - 80}" height="8" rx="4" fill="{accent}" opacity="0.15"/>
      <rect x="40" y="150" width="{int((bw - 80) * (i + 1) / 3)}" height="8" rx="4" fill="{accent}"/>
      <text x="{bw // 2}" y="180" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b" letter-spacing="1">MATURITY LEVEL {i + 1}/3</text>"""

        for ci, ch in enumerate(chars):
            cards += f"""\
      <line x1="30" y1="{200 + ci * 32}" x2="{bw - 30}" y2="{200 + ci * 32}" stroke="#334155" stroke-width="0.5" opacity="0.5"/>
      <circle cx="40" cy="{194 + ci * 32}" r="3" fill="{accent}" opacity="0.6"/>
      <text x="52" y="{198 + ci * 32}" font-family="Arial, sans-serif" font-size="13" fill="#94a3b8">{escape(ch)}</text>"""

        cards += f"""\
    </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("MATURITY MODEL", 640, 45, 220, centered=True)}
  {_text_block([title], 640, 100, 30, 38, "#f8fafc", "middle", "700")}
  <text x="640" y="133" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">PMOs evolve through three maturity levels over time</text>
{stairs_svg}
{cards}
  {_bottom_bar(seconds, total)}
</svg>"""


def _metrics_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    metric_data = [
        ("On-Time\nDelivery", "92%", "#22c55e", "Projects completed by deadline"),
        ("Budget\nAdherence", "87%", "#3b82f6", "Within approved budget"),
        ("Stakeholder\nSatisfaction", "4.2/5", "#a855f7", "Post-project survey score"),
        ("Risk\nMitigation", "78%", "#f59e0b", "Risks resolved before impact"),
        ("Resource\nUtilization", "85%", "#ef4444", "Team allocation efficiency"),
    ]

    metric_cards = ""
    for idx, (label, value, color, desc) in enumerate(metric_data):
        row = idx // 3
        col = idx % 3
        if row == 0:
            cx = 70 + col * 400
            cy = 200
        else:
            cx = 230 + col * 400
            cy = 480
        cw = 360
        ch = 210

        label_lines = label.split("\n")

        metric_cards += f"""\
    <g transform="translate({cx}, {cy})">
      <rect x="0" y="0" width="{cw}" height="{ch}" rx="18" fill="#1e293b" stroke="{color}" stroke-width="1.5" opacity="0.85"/>
      <rect x="0" y="0" width="{cw}" height="6" rx="18" fill="{color}"/>
      <text x="{cw // 2}" y="80" text-anchor="middle" font-family="Arial, sans-serif" font-size="44" font-weight="700" fill="{color}">{value}</text>"""

        for li, ll in enumerate(label_lines):
            metric_cards += f"""\
      <text x="{cw // 2}" y="{120 + li * 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="600" fill="#f8fafc">{escape(ll)}</text>"""

        metric_cards += f"""\
      <text x="{cw // 2}" y="{180}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">{escape(desc)}</text>
      <circle cx="{cw - 20}" cy="20" r="4" fill="{color}" opacity="0.3"/>
    </g>"""

    trend = """\
    <rect x="380" y="440" width="520" height="36" rx="18" fill="#1e3a5f" opacity="0.5"/>
    <text x="640" y="464" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#93c5fd">\U0001f4c8  All metrics tracked quarterly — trending upward year over year</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("KPI DASHBOARD", 640, 45, 210, centered=True)}
  {_text_block([title], 640, 100, 30, 38, "#f8fafc", "middle", "700")}
  <text x="640" y="133" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">Five key performance indicators that measure PMO effectiveness</text>
{metric_cards}
{trend}
  {_bottom_bar(seconds, total)}
</svg>"""


def _challenges_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    challenge_data = [
        ("\U0001f6ab", "Resistance to Change", "Teams avoid new processes", "\u2705", "Show quick wins early", "#ef4444", "#22c55e"),
        ("\U0001f465", "Lack of Sponsorship", "No executive backing", "\u2705", "Build business case with metrics", "#f59e0b", "#3b82f6"),
        ("\U0001f4dc", "Too Much Bureaucracy", "Heavy processes slow teams", "\u2705", "Right-size processes to org needs", "#a855f7", "#22c55e"),
        ("\U0001f4b0", "Inadequate Resources", "Understaffed and overworked", "\u2705", "Prioritize high-impact projects", "#f97316", "#3b82f6"),
        ("\U0001f50d", "Unclear Mandate", "Nobody knows PMO's purpose", "\u2705", "Define charter and scope from day one", "#ef4444", "#22c55e"),
    ]

    cards = ""
    for idx, (icon, challenge, desc, check, solution, problem_color, sol_color) in enumerate(challenge_data):
        col = idx % 3
        row = idx // 3
        cx = 80 + col * 400
        cy = 195 + row * 235
        cw = 380
        ch = 210

        # Split card: problem left, solution right
        left_w = cw // 2 - 4
        right_w = cw // 2 - 4

        cards += f"""\
    <g transform="translate({cx}, {cy})">
      <!-- Card shadow -->
      <rect x="2" y="2" width="{cw}" height="{ch}" rx="16" fill="#000" opacity="0.3"/>
      <!-- Problem side (left) -->
      <rect x="0" y="0" width="{left_w}" height="{ch}" rx="16" fill="#1a0a0a" stroke="{problem_color}" stroke-width="1.5"/>
      <rect x="0" y="0" width="{left_w}" height="6" rx="16" fill="{problem_color}"/>
      <rect x="0" y="4" width="{left_w}" height="2" fill="{problem_color}"/>
      <text x="{left_w // 2}" y="42" text-anchor="middle" font-size="22">{icon}</text>
      <text x="{left_w // 2}" y="75" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="{problem_color}">{escape(challenge)}</text>
      <text x="{left_w // 2}" y="100" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#fca5a5" opacity="0.7">{escape(desc)}</text>
      <!-- Separator line -->
      <line x1="{left_w}" y1="10" x2="{left_w}" y2="{ch - 10}" stroke="{problem_color}" stroke-width="1" stroke-dasharray="3,3" opacity="0.3"/>
      <!-- Arrow -->
      <text x="{left_w + 8}" y="{ch // 2 + 6}" text-anchor="middle" font-size="14" fill="{sol_color}" opacity="0.6">\u27a1</text>
      <!-- Solution side (right) -->
      <rect x="{left_w + 16}" y="0" width="{right_w - 16}" height="{ch}" rx="16" fill="#0a1a0f" stroke="{sol_color}" stroke-width="1.5"/>
      <rect x="{left_w + 16}" y="0" width="{right_w - 16}" height="6" rx="16" fill="{sol_color}"/>
      <rect x="{left_w + 16}" y="4" width="{right_w - 16}" height="2" fill="{sol_color}"/>
      <text x="{left_w + 16 + (right_w - 16) // 2}" y="42" text-anchor="middle" font-size="22">{check}</text>
      <text x="{left_w + 16 + (right_w - 16) // 2}" y="75" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="600" fill="{sol_color}">SOLUTION</text>
      <text x="{left_w + 16 + (right_w - 16) // 2}" y="100" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#86efac" opacity="0.8">{escape(solution)}</text>
    </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_pill("OBSTACLES & SOLUTIONS", 640, 45, 260, centered=True)}
  {_text_block([title], 640, 100, 30, 38, "#f8fafc", "middle", "700")}
  <text x="640" y="133" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">Every PMO faces obstacles \u2014 but each has a practical solution</text>
  {_section_divider(200, 160, 880)}
{cards}
  {_bottom_bar(seconds, total)}
</svg>"""


def _roadmap_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    parts = slide.text_on_screen.split("\n\n", 1)
    title = parts[0] if len(parts) > 0 else ""

    steps = [
        ("01", "Assess Current State", "Evaluate PM maturity, identify gaps and team needs", "#3b82f6"),
        ("02", "Define PMO Charter", "Document mission, scope, authority and success criteria", "#22c55e"),
        ("03", "Choose Maturity Level", "Select supportive, controlling or directive model", "#f59e0b"),
        ("04", "Establish Processes", "Define methodology, templates and choose tool stack", "#a855f7"),
        ("05", "Build the Team", "Hire, assign roles and provide thorough training", "#f97316"),
        ("06", "Launch & Iterate", "Pilot, gather feedback, measure and continuously improve", "#ef4444"),
    ]

    timeline_x = 640
    cards_svg = ""

    for i, (num, step_title, desc, color) in enumerate(steps):
        if i < 3:
            card_x = 100
            text_x = card_x + 20
            connector_start = card_x + 360
            connector_end = timeline_x - 16
        else:
            card_x = timeline_x + 26
            text_x = card_x + 20
            connector_start = timeline_x + 16
            connector_end = card_x

        cy = 170 + (i % 3) * 120

        cards_svg += f"""\
    <g>
      <line x1="{connector_start}" y1="{cy + 25}" x2="{connector_end}" y2="{cy + 25}" stroke="{color}" stroke-width="2" opacity="0.35"/>
      <circle cx="{timeline_x}" cy="{cy + 25}" r="16" fill="#0f172a" stroke="{color}" stroke-width="2.5"/>
      <circle cx="{timeline_x}" cy="{cy + 25}" r="12" fill="{color}" opacity="0.12"/>
      <text x="{timeline_x}" y="{cy + 31}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="{color}">{num}</text>
      <rect x="{card_x}" y="{cy}" width="370" height="80" rx="14" fill="#1e293b" stroke="{color}" stroke-width="1.5" opacity="0.85"/>
      <rect x="{card_x}" y="{cy}" width="370" height="5" rx="14" fill="{color}" opacity="0.7"/>
      <rect x="{card_x}" y="{cy + 3}" width="370" height="2" fill="{color}" opacity="0.3"/>
      <text x="{text_x}" y="{cy + 30}" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#f8fafc">{escape(step_title)}</text>
      <text x="{text_x}" y="{cy + 55}" font-family="Arial, sans-serif" font-size="11" fill="#94a3b8">{escape(desc[:60])}</text>
    </g>"""

    timeline_svg = f"""\
    <line x1="{timeline_x}" y1="155" x2="{timeline_x}" y2="610" stroke="#334155" stroke-width="2.5" stroke-dasharray="8,5" opacity="0.4"/>
    <line x1="{timeline_x}" y1="155" x2="{timeline_x}" y2="610" stroke="url(#accentBar)" stroke-width="1.5" stroke-dasharray="8,5" opacity="0.25"/>
    <circle cx="{timeline_x}" cy="155" r="5" fill="#3b82f6" opacity="0.35"/>
    <circle cx="{timeline_x}" cy="610" r="5" fill="#22c55e" opacity="0.35"/>
    <text x="{timeline_x}" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b" letter-spacing="1">START</text>
    <text x="{timeline_x}" y="630" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b" letter-spacing="1">GOAL</text>"""

    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1280\" height=\"720\" viewBox=\"0 0 1280 720\">
  {_svg_background()}
  {_pill("IMPLEMENTATION ROADMAP", 640, 45, 280, centered=True)}
  {_text_block([title], 640, 100, 28, 36, "#f8fafc", "middle", "700")}
  <text x=\"640\" y=\"128\" text-anchor=\"middle\" font-family=\"Arial, sans-serif\" font-size=\"13\" fill=\"#64748b\">Follow this six-step roadmap to establish a successful PMO</text>
{timeline_svg}
{cards_svg}
  {_bottom_bar(seconds, total)}
</svg>"""


def _closing_slide(slide: PMOSlide, seconds: int, total: int) -> str:
    lines = slide.text_on_screen.split("\n")
    title_lines = lines[:1] if lines else [""]
    body_lines = lines[1:] if len(lines) > 1 else [""]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  {_svg_background()}
  {_floating_dots(12, 640, 360, 300)}
  {_pill("SUMMARY", 640, 70, 140, centered=True)}
  {_text_block(title_lines, 640, 170, 44, 54, "#f8fafc", "middle", "700")}
  {_text_block(body_lines, 640, 340, 28, 42, "#f59e0b", "middle", "600")}
  <!-- Celebration scene -->
  <g transform="translate(440, 440)">
    <rect x="0" y="50" width="400" height="110" rx="18" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
    <rect x="0" y="50" width="400" height="40" rx="18" fill="#1e3a5f"/>
    <rect x="0" y="72" width="400" height="18" fill="#1e3a5f"/>
    <text x="200" y="78" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#f8fafc">\U0001f389  Team Celebrating Success  \U0001f389</text>
    <text x="200" y="120" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#64748b">On time  \u2022  On budget  \u2022  Quality delivered</text>
    <text x="200" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#f59e0b">PMO = Better Planning + Better Control + Better Results</text>
  </g>
  {_bottom_bar(seconds, total)}
</svg>"""


# ── Render Dispatch ────────────────────────────────────────────────────────

def render_slide(slide: PMOSlide, seconds: int, total: int) -> bytes:
    renderers = {
        "title": _title_slide,
        "definition": _definition_slide,
        "list": _list_slide,
        "comparison": _comparison_slide,
        "dashboard": _dashboard_slide,
        "benefits": _benefits_slide,
        "tools": _tools_slide,
        "maturity": _maturity_slide,
        "metrics": _metrics_slide,
        "roles_table": _roles_table_slide,
        "challenges": _challenges_slide,
        "roadmap": _roadmap_slide,
        "closing": _closing_slide,
    }
    renderer = renderers.get(slide.slide_type)
    if not renderer:
        raise ValueError(f"Unknown slide type: {slide.slide_type}")
    svg = renderer(slide, seconds, total)
    return svg.encode("utf-8")


# ── SRT Generation ─────────────────────────────────────────────────────────

def _timestamp(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d},000"


def generate_srt(slides: list[PMOSlide], video_duration: int) -> str:
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

def generate_narration(slides: list[PMOSlide], output_dir: Path) -> Path:
    """Generate a gentle male voice narration using OpenAI TTS."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for narration generation. "
            "Set it in your .env file or export it."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install openai: pip install openai") from exc

    full_script = " ".join(slide.narration for slide in slides)
    print("  Generating gentle male voice narration...")

    client = OpenAI(api_key=api_key)
    result = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="echo",
        input=full_script,
        instructions=(
            "Speak in a gentle, calm, warm male voice. Professional but friendly, "
            "like a knowledgeable instructor explaining to a colleague. "
            "Clear and steady pace. Warm and reassuring tone throughout."
        ),
    )

    audio_path = output_dir / "narration.mp3"
    audio_path.write_bytes(result.read())
    print(f"  Narration saved: {audio_path}")
    return audio_path


# ── Background Music Generation ─────────────────────────────────────────────

def generate_background_music(output_dir: Path, duration: float) -> Path:
    """Generate a low ambient background music track using ffmpeg audio synthesis."""
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
    """Get audio duration in seconds using ffprobe."""
    probe = shutil.which("ffprobe") or "ffprobe"
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    probe = shutil.which("ffprobe") or "ffprobe"
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


# ── Video Assembly ─────────────────────────────────────────────────────────

def _build_motion_filter(slide_type: str, frames: int, slide_duration: int) -> str:
    """Build FFmpeg zoompan filter expression for the given slide type."""
    profile = MOTION_PROFILES.get(slide_type, MOTION_PROFILES["benefits"])
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


def assemble_video(slides: list[PMOSlide], output_dir: Path) -> Path:
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
        print(f"  Rendering slide {i}/{len(slides)} ({slide.duration}s) [{MOTION_PROFILES[slide.slide_type]['desc']}]...")
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
        motion_filter = _build_motion_filter(slide.slide_type, frames, slide.duration)

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
        # Single clip, just copy
        temp_mp4 = output_dir / "pmo_video_no_audio.mp4"
        clip_paths[0].rename(temp_mp4)
    else:
        # Build complex filter chain with xfade between each pair of clips
        print(f"  Crossfading {num_clips} clips with {TRANSITION_DUR}s transitions...")

        filter_parts = []
        # Each input needs settb to align timebases
        for i in range(num_clips):
            filter_parts.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]")

        # Chain xfade filters
        cumulative = 0.0
        prev_label = "v0"
        for i in range(1, num_clips):
            # xfade offset: the time in the first input where transition starts
            offset = cumulative + slides[i - 1].duration - TRANSITION_DUR
            cur_label = f"xf{i}"
            filter_parts.append(
                f"[{prev_label}][v{i}]xfade=transition=fade:"
                f"duration={TRANSITION_DUR}:offset={offset:.1f}[{cur_label}]"
            )
            cumulative += slides[i - 1].duration - TRANSITION_DUR
            prev_label = cur_label

        filter_chain = ";".join(filter_parts)

        temp_mp4 = output_dir / "pmo_video_no_audio.mp4"
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
        # Duration matches, just convert to AAC
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
    output_mp4 = output_dir / "pmo_educational_video.mp4"
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

    # Generate SRT subtitles (using actual video duration)
    srt_path = output_dir / "pmo_educational_video.srt"
    srt_path.write_text(generate_srt(slides, int(actual_video_dur)), encoding="utf-8")

    return output_mp4


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  PMO Educational Video Generator")
    print("  Motion graphics + crossfade transitions + ambient audio")
    print("=" * 60)
    print(f"\nSlides: {len(SLIDES)}")
    actual_dur = TOTAL_DURATION - (len(SLIDES) - 1) * TRANSITION_DUR
    print(f"Total duration: {TOTAL_DURATION}s → {actual_dur:.1f}s (with {TRANSITION_DUR}s crossfades)")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    for s in SLIDES:
        profile = MOTION_PROFILES[s.slide_type]
        print(f"  [{s.slide_type:12s}] {s.duration:2d}s  {profile['desc']}")

    print()
    output_mp4 = assemble_video(SLIDES, OUTPUT_DIR)

    srt_path = OUTPUT_DIR / "pmo_educational_video.srt"
    print(f"\n\u2713 Video generated: {output_mp4}")
    print(f"\u2713 Subtitles: {srt_path}")
    final_dur = TOTAL_DURATION - (len(SLIDES) - 1) * TRANSITION_DUR
    print(f"\u2713 Video duration: {final_dur:.1f}s")
    print(f"\u2713 File size: {output_mp4.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
