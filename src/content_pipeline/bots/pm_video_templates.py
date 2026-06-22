from __future__ import annotations

import hashlib
import html
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import cairosvg
except ImportError:  # pragma: no cover - optional dependency
    cairosvg = None


@dataclass(frozen=True)
class PMVideoTemplate:
    template_id: str
    name: str
    layout: str
    palette: str
    background_start: str
    background_mid: str
    background_end: str
    accent_primary: str
    accent_secondary: str
    accent_tertiary: str
    panel_fill: str
    panel_border: str
    badge_fill: str
    badge_text: str
    headline_fill: str
    body_fill: str
    highlight_fill: str
    card_fill: str
    card_border: str

    @property
    def style_line(self) -> str:
        return f"{self.name} / {self.layout.replace('_', ' ').title()}"


_LAYOUTS = [
    ("edu_infographic", "Edu Infographic"),
    ("lesson_board", "Lesson Board"),
    ("worksheet_grid", "Worksheet Grid"),
    ("podcast_cover", "Podcast Cover"),
    ("stats_wall", "Stats Wall"),
    ("workshop_notes", "Workshop Notes"),
]

_PALETTES = [
    (
        "indigo_cyan",
        ("#0b1020", "#14213d", "#0f766e"),
        ("#22d3ee", "#f59e0b", "#ffffff"),
        "#111827",
        "#1f2937",
        "#f59e0b",
        "#ffffff",
        "#ffffff",
        "#dbeafe",
        "#f59e0b",
        "#111827",
        "#d1d5db",
    ),
    (
        "emerald_gold",
        ("#071b19", "#0f172a", "#14532d"),
        ("#34d399", "#fbbf24", "#ffffff"),
        "#0f172a",
        "#14532d",
        "#fbbf24",
        "#111827",
        "#ffffff",
        "#dcfce7",
        "#fbbf24",
        "#111827",
        "#dcfce7",
    ),
    (
        "royal_amber",
        ("#0f1024", "#1e1b4b", "#7c2d12"),
        ("#f59e0b", "#60a5fa", "#ffffff"),
        "#111827",
        "#312e81",
        "#f59e0b",
        "#ffffff",
        "#ffffff",
        "#e0e7ff",
        "#f59e0b",
        "#111827",
        "#e5e7eb",
    ),
    (
        "slate_lime",
        ("#08111f", "#111827", "#334155"),
        ("#a3e635", "#38bdf8", "#ffffff"),
        "#0f172a",
        "#1e293b",
        "#a3e635",
        "#111827",
        "#ffffff",
        "#e2e8f0",
        "#a3e635",
        "#111827",
        "#cbd5e1",
    ),
    (
        "rose_cyan",
        ("#12041b", "#1f1147", "#0f766e"),
        ("#f472b6", "#22d3ee", "#ffffff"),
        "#111827",
        "#4c1d95",
        "#f472b6",
        "#ffffff",
        "#ffffff",
        "#fce7f3",
        "#f472b6",
        "#111827",
        "#f8fafc",
    ),
]

_FALLBACK_TEMPLATE = PMVideoTemplate(
    template_id="course_blueprint",
    name="Course Blueprint",
    layout="executive_glass",
    palette="course_blueprint",
    background_start="#07111f",
    background_mid="#0f172a",
    background_end="#1d4ed8",
    accent_primary="#22d3ee",
    accent_secondary="#f59e0b",
    accent_tertiary="#ffffff",
    panel_fill="#0f172a",
    panel_border="#22d3ee",
    badge_fill="#f59e0b",
    badge_text="#111827",
    headline_fill="#ffffff",
    body_fill="#dbeafe",
    highlight_fill="#f59e0b",
    card_fill="#111827",
    card_border="#38bdf8",
)


def build_pm_video_templates() -> list[PMVideoTemplate]:
    templates: list[PMVideoTemplate] = []
    for layout_slug, layout_name in _LAYOUTS:
        for index, (
            palette_name,
            background,
            accents,
            panel_fill,
            panel_border,
            badge_fill,
            badge_text,
            headline_fill,
            body_fill,
            highlight_fill,
            card_fill,
            card_border,
        ) in enumerate(_PALETTES, start=1):
            templates.append(
                PMVideoTemplate(
                    template_id=f"{layout_slug}_{index:02d}",
                    name=f"{layout_name} {index}",
                    layout=layout_slug,
                    palette=palette_name,
                    background_start=background[0],
                    background_mid=background[1],
                    background_end=background[2],
                    accent_primary=accents[0],
                    accent_secondary=accents[1],
                    accent_tertiary=accents[2],
                    panel_fill=panel_fill,
                    panel_border=panel_border,
                    badge_fill=badge_fill,
                    badge_text=badge_text,
                    headline_fill=headline_fill,
                    body_fill=body_fill,
                    highlight_fill=highlight_fill,
                    card_fill=card_fill,
                    card_border=card_border,
                )
            )
    return templates


PM_VIDEO_TEMPLATES = build_pm_video_templates()
_RECOMMENDED_LAYOUTS = {"edu_infographic", "lesson_board", "worksheet_grid"}
_ROLE_LAYOUTS: dict[str, tuple[str, ...]] = {
    "hero": ("podcast_cover", "stats_wall", "lesson_board"),
    "workflow": ("worksheet_grid", "workshop_notes", "lesson_board"),
    "analysis": ("stats_wall", "worksheet_grid", "edu_infographic"),
    "cta": ("lesson_board", "podcast_cover", "workshop_notes"),
    "reference": ("edu_infographic", "lesson_board", "worksheet_grid"),
}
PM_VIDEO_TEMPLATE_POOL = [
    *(template for template in PM_VIDEO_TEMPLATES if template.layout in _RECOMMENDED_LAYOUTS for _ in range(3)),
    *(template for template in PM_VIDEO_TEMPLATES if template.layout not in _RECOMMENDED_LAYOUTS),
]
PM_COURSE_TEMPLATE = _FALLBACK_TEMPLATE


def list_pm_video_templates() -> list[PMVideoTemplate]:
    return [*PM_VIDEO_TEMPLATES]


def get_pm_video_template(template_id: str) -> PMVideoTemplate:
    for template in PM_VIDEO_TEMPLATES:
        if template.template_id == template_id:
            return template
    if template_id == PM_COURSE_TEMPLATE.template_id:
        return PM_COURSE_TEMPLATE
    raise KeyError(template_id)


def select_pm_video_template(topic: str, day: str, template_mode: str = "random") -> PMVideoTemplate:
    if template_mode == "course":
        return PM_COURSE_TEMPLATE
    seed = hashlib.sha1(f"{normalize_topic(topic)}|{day}".encode("utf-8")).hexdigest()
    index = int(seed, 16) % len(PM_VIDEO_TEMPLATE_POOL)
    return PM_VIDEO_TEMPLATE_POOL[index]


def select_pm_video_template_for_role(
    topic: str,
    day: str,
    role: str,
    template_mode: str = "random",
    variant_index: int = 0,
) -> PMVideoTemplate:
    if template_mode == "course":
        return PM_COURSE_TEMPLATE
    role_key = role.strip().lower()
    role_layouts = _ROLE_LAYOUTS.get(role_key, _RECOMMENDED_LAYOUTS)
    candidates = [template for template in PM_VIDEO_TEMPLATE_POOL if template.layout in role_layouts]
    if not candidates:
        candidates = PM_VIDEO_TEMPLATE_POOL
    seed = hashlib.sha1(
        f"{normalize_topic(topic)}|{day}|{role_key}|{variant_index}".encode("utf-8")
    ).hexdigest()
    index = int(seed, 16) % len(candidates)
    return candidates[index]


def normalize_topic(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value)
    return " ".join(cleaned.split())


def render_template_gallery_html(templates: Iterable[PMVideoTemplate] | None = None) -> str:
    entries = list(templates or PM_VIDEO_TEMPLATES)
    cards = "\n".join(_template_card(template) for template in entries)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PM Video Template Gallery</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background:
      radial-gradient(circle at top left, rgba(59,130,246,0.24), transparent 32%),
      radial-gradient(circle at bottom right, rgba(245,158,11,0.18), transparent 24%),
      #050816;
      color: #f8fafc; }}
    header {{ padding: 32px 28px 28px; background: linear-gradient(135deg, rgba(17,24,39,0.96), rgba(29,78,216,0.92)); border-bottom: 1px solid rgba(255,255,255,0.08); }}
    main {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(315px, 1fr)); gap: 18px; align-items: start; }}
    .card {{ border-radius: 22px; overflow: hidden; border: 1px solid rgba(255,255,255,0.12); box-shadow: 0 20px 45px rgba(0,0,0,0.35); background: rgba(15, 23, 42, 0.96); text-decoration: none; color: inherit; transition: transform 180ms ease, box-shadow 180ms ease; }}
    .card:hover {{ transform: translateY(-4px); box-shadow: 0 28px 55px rgba(0,0,0,0.46); }}
    .preview {{ display: block; width: 100%; height: auto; }}
    .body {{ padding: 16px; background: rgba(15, 23, 42, 0.96); }}
    .meta {{ color: #cbd5e1; font-size: 14px; line-height: 1.5; }}
    .pill {{ display: inline-block; padding: 5px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; margin-right: 8px; margin-bottom: 8px; }}
    .feature {{ display: inline-block; margin-bottom: 10px; padding: 6px 12px; border-radius: 999px; background: linear-gradient(135deg, #f59e0b, #fb7185); color: #111827; font-size: 12px; font-weight: 900; letter-spacing: 0.04em; text-transform: uppercase; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 5vw, 48px); }}
    header p {{ margin: 0; max-width: 920px; color: #dbeafe; line-height: 1.6; font-size: 16px; }}
  </style>
</head>
<body>
  <header>
    <div class="feature">Recommended templates first</div>
    <h1>PM Video Template Gallery</h1>
    <p>Random-topic PM videos now favor the most educational, eye-catching styles inspired by strong free template libraries. Course videos can stay on the fixed course blueprint template.</p>
  </header>
  <main>
    <div class="grid">
      {cards}
    </div>
  </main>
</body>
</html>
"""


def _template_card(template: PMVideoTemplate) -> str:
    preview_path = f"template_previews/{template.template_id}.svg"
    feature_label = "Recommended" if template.layout in _RECOMMENDED_LAYOUTS else "Library"
    return f"""
    <a class="card" href="{html.escape(preview_path)}" target="_blank" rel="noreferrer">
      <img class="preview" src="{html.escape(preview_path)}" alt="{html.escape(template.name)} preview">
      <div class="body">
        <div class="feature">{feature_label}</div>
        <div class="pill" style="background:{template.badge_fill};color:{template.badge_text}">{html.escape(template.palette)}</div>
        <div class="pill" style="background:{template.accent_primary};color:#0f172a">layout: {html.escape(template.layout)}</div>
        <h2>{html.escape(template.name)}</h2>
        <p class="meta">Template ID: <code>{html.escape(template.template_id)}</code></p>
        <p class="meta">Palette: {html.escape(template.background_start)} / {html.escape(template.background_mid)} / {html.escape(template.background_end)}</p>
        <p class="meta">Highlight: {html.escape(template.highlight_fill)} • Cards: {html.escape(template.card_fill)} / {html.escape(template.card_border)}</p>
      </div>
    </a>
    """


def write_template_gallery(output_dir: Path, templates: Iterable[PMVideoTemplate] | None = None) -> Path:
    entries = list(templates or PM_VIDEO_TEMPLATES)
    gallery_dir = output_dir / "pm_video_templates"
    preview_dir = gallery_dir / "template_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    for template in entries:
        (preview_dir / f"{template.template_id}.svg").write_text(
            render_template_preview_svg(template),
            encoding="utf-8",
        )
    gallery_path = gallery_dir / "template_gallery.html"
    gallery_path.write_text(render_template_gallery_html(entries), encoding="utf-8")
    return gallery_path


def write_template_examples(
    output_dir: Path,
    templates: Iterable[PMVideoTemplate] | None = None,
    seconds: int = 4,
) -> Path:
    if seconds < 3 or seconds > 5:
        raise ValueError("Template examples must be between 3 and 5 seconds long.")
    if cairosvg is None:
        raise RuntimeError("cairosvg is required to render template examples.")
    entries = list(templates or PM_VIDEO_TEMPLATES)
    recommended = [template for template in entries if template.layout in _RECOMMENDED_LAYOUTS]
    selected = (recommended or entries)[:5]
    examples_dir = output_dir / "pm_video_templates" / "template_examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for index, template in enumerate(selected, start=1):
        slug = f"{index:02d}_{template.template_id}"
        svg_path = examples_dir / f"{slug}.svg"
        png_path = examples_dir / f"{slug}.png"
        mp4_path = examples_dir / f"{slug}.mp4"
        svg_path.write_text(render_template_preview_svg(template), encoding="utf-8")
        png_path.write_bytes(
            cairosvg.svg2png(
                bytestring=svg_path.read_bytes(),
                output_width=1280,
                output_height=720,
            )
        )
        _render_preview_mp4(png_path, mp4_path, seconds)
        rows.append(
            {
                "index": f"{index}",
                "title": template.name,
                "template_id": template.template_id,
                "layout": template.layout,
                "mp4": mp4_path.name,
                "svg": svg_path.name,
            }
        )
    html_path = examples_dir / "template_examples.html"
    html_path.write_text(render_template_examples_html(rows, seconds), encoding="utf-8")
    return html_path


def render_template_preview_svg(template: PMVideoTemplate) -> str:
    layout_label = template.layout.replace("_", " ").title()
    title = _wrap_preview_text(template.name.upper(), 22, 3)
    subtitle = _wrap_preview_text(f"{layout_label} / {template.palette}", 26, 2)
    title_svg = "".join(
        f'<text x="72" y="{142 + index * 60}" font-size="54" font-weight="900" letter-spacing="0.5" fill="{template.headline_fill}">{html.escape(line)}</text>'
        for index, line in enumerate(title)
    )
    subtitle_svg = "".join(
        f'<text x="72" y="{300 + index * 34}" font-size="24" font-weight="700" fill="{template.body_fill}">{html.escape(line)}</text>'
        for index, line in enumerate(subtitle)
    )

    if template.template_id == "edu_infographic_01":
        composition = f"""
        <rect x="48" y="48" width="384" height="84" rx="28" fill="{template.badge_fill}"/>
        <text x="86" y="99" font-size="28" font-weight="900" fill="{template.badge_text}">FREE EDUCATION POSTER</text>
        <rect x="58" y="152" width="760" height="472" rx="40" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="6"/>
        <rect x="854" y="152" width="368" height="472" rx="40" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="6"/>
        <rect x="92" y="192" width="300" height="56" rx="18" fill="{template.highlight_fill}" opacity="0.94"/>
        <text x="108" y="228" font-size="26" font-weight="900" fill="{template.badge_text}">TOPIC HIGHLIGHT</text>
        <rect x="92" y="282" width="520" height="28" rx="14" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="92" y="332" width="470" height="28" rx="14" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="92" y="382" width="420" height="28" rx="14" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="92" y="442" width="290" height="180" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="414" y="442" width="282" height="180" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <circle cx="240" cy="528" r="60" fill="{template.accent_primary}" opacity="0.24"/>
        <circle cx="240" cy="528" r="32" fill="{template.highlight_fill}" opacity="0.30"/>
        <rect x="438" y="476" width="172" height="30" rx="15" fill="{template.highlight_fill}"/>
        <rect x="438" y="526" width="120" height="22" rx="11" fill="{template.accent_primary}"/>
        <rect x="438" y="566" width="152" height="22" rx="11" fill="{template.accent_secondary}"/>
        <rect x="888" y="190" width="214" height="42" rx="21" fill="{template.highlight_fill}"/>
        <text x="995" y="218" text-anchor="middle" font-size="20" font-weight="900" fill="{template.badge_text}">EDUCATION POST</text>
        <circle cx="1038" cy="356" r="106" fill="{template.accent_primary}" opacity="0.24"/>
        <circle cx="1038" cy="356" r="64" fill="{template.highlight_fill}" opacity="0.30"/>
        <text x="1038" y="376" text-anchor="middle" font-size="86" font-weight="900" fill="{template.highlight_fill}">A</text>
        <rect x="902" y="496" width="252" height="24" rx="12" fill="{template.highlight_fill}" opacity="0.9"/>
        <rect x="902" y="540" width="196" height="24" rx="12" fill="{template.accent_primary}" opacity="0.82"/>
        """
    elif template.layout == "edu_infographic":
        composition = f"""
        <rect x="56" y="58" width="282" height="64" rx="22" fill="{template.badge_fill}"/>
        <text x="92" y="100" font-size="24" font-weight="900" fill="{template.badge_text}">FREE EDUCATION LAYOUT</text>
        <rect x="58" y="152" width="692" height="472" rx="36" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5"/>
        <rect x="788" y="152" width="434" height="220" rx="34" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="5"/>
        <rect x="788" y="400" width="434" height="224" rx="34" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="5"/>
        <circle cx="1006" cy="268" r="82" fill="{template.accent_primary}" opacity="0.22"/>
        <circle cx="1006" cy="268" r="52" fill="{template.highlight_fill}" opacity="0.28"/>
        <rect x="126" y="198" width="220" height="44" rx="14" fill="{template.highlight_fill}" opacity="0.90"/>
        <rect x="126" y="264" width="524" height="24" rx="12" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="126" y="308" width="456" height="24" rx="12" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="126" y="352" width="394" height="24" rx="12" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="126" y="410" width="600" height="190" rx="28" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="836" y="198" width="140" height="36" rx="18" fill="{template.highlight_fill}"/>
        <text x="906" y="223" text-anchor="middle" font-size="18" font-weight="900" fill="{template.badge_text}">DEFINITION</text>
        <text x="1006" y="268" text-anchor="middle" font-size="72" font-weight="900" fill="{template.highlight_fill}">A</text>
        <rect x="884" y="458" width="242" height="26" rx="13" fill="{template.highlight_fill}" opacity="0.88"/>
        <rect x="884" y="506" width="182" height="26" rx="13" fill="{template.accent_primary}" opacity="0.80"/>
        """
    elif template.layout == "lesson_board":
        composition = f"""
        <rect x="56" y="58" width="278" height="64" rx="22" fill="{template.badge_fill}"/>
        <text x="90" y="100" font-size="24" font-weight="900" fill="{template.badge_text}">LESSON CARD</text>
        <rect x="58" y="152" width="1200" height="470" rx="36" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5"/>
        <rect x="82" y="182" width="380" height="132" rx="24" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="486" y="182" width="360" height="132" rx="24" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="870" y="182" width="360" height="132" rx="24" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="82" y="342" width="1148" height="248" rx="30" fill="{template.card_fill}" stroke="{template.highlight_fill}" stroke-width="4"/>
        <circle cx="272" cy="248" r="58" fill="{template.accent_primary}" opacity="0.24"/>
        <circle cx="272" cy="248" r="28" fill="{template.highlight_fill}" opacity="0.34"/>
        <circle cx="666" cy="248" r="58" fill="{template.accent_secondary}" opacity="0.22"/>
        <circle cx="666" cy="248" r="28" fill="{template.accent_primary}" opacity="0.32"/>
        <circle cx="1054" cy="248" r="58" fill="{template.highlight_fill}" opacity="0.22"/>
        <circle cx="1054" cy="248" r="28" fill="{template.accent_secondary}" opacity="0.32"/>
        <rect x="116" y="404" width="168" height="34" rx="17" fill="{template.highlight_fill}"/>
        <rect x="116" y="458" width="444" height="18" rx="9" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="116" y="498" width="520" height="18" rx="9" fill="{template.body_fill}" opacity="0.22"/>
        <rect x="116" y="538" width="388" height="18" rx="9" fill="{template.body_fill}" opacity="0.22"/>
        """
    elif template.layout == "worksheet_grid":
        composition = f"""
        <rect x="56" y="58" width="304" height="64" rx="22" fill="{template.badge_fill}"/>
        <text x="90" y="100" font-size="24" font-weight="900" fill="{template.badge_text}">WORKSHEET STYLE</text>
        <rect x="58" y="152" width="1200" height="470" rx="36" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5"/>
        <rect x="90" y="184" width="540" height="390" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="664" y="184" width="532" height="184" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="664" y="390" width="260" height="184" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="946" y="390" width="250" height="184" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <path d="M120 230h420" stroke="{template.highlight_fill}" stroke-width="8" stroke-linecap="round"/>
        <path d="M120 274h360" stroke="{template.body_fill}" stroke-opacity="0.55" stroke-width="10" stroke-linecap="round"/>
        <path d="M120 320h330" stroke="{template.body_fill}" stroke-opacity="0.42" stroke-width="10" stroke-linecap="round"/>
        <path d="M120 364h390" stroke="{template.body_fill}" stroke-opacity="0.30" stroke-width="10" stroke-linecap="round"/>
        <rect x="120" y="420" width="168" height="30" rx="15" fill="{template.highlight_fill}" opacity="0.92"/>
        <rect x="120" y="470" width="250" height="20" rx="10" fill="{template.accent_primary}" opacity="0.84"/>
        <rect x="120" y="508" width="300" height="20" rx="10" fill="{template.accent_secondary}" opacity="0.80"/>
        <circle cx="816" cy="276" r="54" fill="{template.highlight_fill}" opacity="0.24"/>
        <circle cx="816" cy="276" r="26" fill="{template.accent_primary}" opacity="0.34"/>
        <circle cx="1070" cy="482" r="54" fill="{template.accent_secondary}" opacity="0.22"/>
        <circle cx="1070" cy="482" r="24" fill="{template.highlight_fill}" opacity="0.34"/>
        """
    elif template.layout == "podcast_cover":
        composition = f"""
        <rect x="56" y="58" width="286" height="64" rx="22" fill="{template.badge_fill}"/>
        <text x="90" y="100" font-size="24" font-weight="900" fill="{template.badge_text}">PODCAST COVER</text>
        <rect x="58" y="152" width="1200" height="470" rx="36" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5"/>
        <rect x="86" y="184" width="354" height="394" rx="32" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="470" y="184" width="354" height="394" rx="32" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="854" y="184" width="372" height="394" rx="32" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <circle cx="264" cy="300" r="102" fill="{template.accent_primary}" opacity="0.24"/>
        <circle cx="264" cy="300" r="66" fill="{template.highlight_fill}" opacity="0.26"/>
        <circle cx="648" cy="300" r="102" fill="{template.accent_secondary}" opacity="0.20"/>
        <circle cx="648" cy="300" r="66" fill="{template.accent_primary}" opacity="0.28"/>
        <circle cx="1040" cy="300" r="102" fill="{template.highlight_fill}" opacity="0.18"/>
        <circle cx="1040" cy="300" r="66" fill="{template.accent_secondary}" opacity="0.28"/>
        <rect x="86" y="504" width="246" height="42" rx="21" fill="{template.highlight_fill}"/>
        <rect x="498" y="232" width="298" height="38" rx="19" fill="{template.highlight_fill}"/>
        <rect x="886" y="232" width="276" height="38" rx="19" fill="{template.accent_primary}"/>
        """
    elif template.layout == "stats_wall":
        composition = f"""
        <rect x="56" y="58" width="282" height="64" rx="22" fill="{template.badge_fill}"/>
        <text x="90" y="100" font-size="24" font-weight="900" fill="{template.badge_text}">INSIGHT WALL</text>
        <rect x="58" y="152" width="1200" height="470" rx="36" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5"/>
        <rect x="90" y="184" width="280" height="350" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="394" y="184" width="764" height="160" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="394" y="368" width="372" height="166" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="786" y="368" width="372" height="166" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="116" y="232" width="124" height="22" rx="11" fill="{template.highlight_fill}"/>
        <rect x="116" y="274" width="168" height="16" rx="8" fill="{template.body_fill}" opacity="0.38"/>
        <rect x="116" y="308" width="140" height="16" rx="8" fill="{template.body_fill}" opacity="0.28"/>
        <rect x="116" y="342" width="188" height="16" rx="8" fill="{template.body_fill}" opacity="0.20"/>
        <rect x="420" y="216" width="136" height="18" rx="9" fill="{template.highlight_fill}" opacity="0.94"/>
        <rect x="420" y="258" width="520" height="18" rx="9" fill="{template.body_fill}" opacity="0.28"/>
        <rect x="420" y="292" width="420" height="18" rx="9" fill="{template.body_fill}" opacity="0.20"/>
        <rect x="434" y="406" width="46" height="88" rx="18" fill="{template.highlight_fill}"/>
        <rect x="498" y="382" width="46" height="112" rx="18" fill="{template.accent_primary}"/>
        <rect x="562" y="428" width="46" height="66" rx="18" fill="{template.accent_secondary}"/>
        <rect x="826" y="404" width="46" height="90" rx="18" fill="{template.highlight_fill}"/>
        <rect x="890" y="382" width="46" height="112" rx="18" fill="{template.accent_primary}"/>
        <rect x="954" y="446" width="46" height="48" rx="18" fill="{template.accent_secondary}"/>
        """
    else:
        composition = f"""
        <rect x="56" y="58" width="304" height="64" rx="22" fill="{template.badge_fill}"/>
        <text x="90" y="100" font-size="24" font-weight="900" fill="{template.badge_text}">WORKSHOP NOTES</text>
        <rect x="58" y="152" width="1200" height="470" rx="36" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5"/>
        <rect x="86" y="184" width="372" height="190" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="486" y="184" width="336" height="190" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="850" y="184" width="332" height="190" rx="30" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="4"/>
        <rect x="86" y="402" width="1096" height="166" rx="30" fill="{template.card_fill}" stroke="{template.highlight_fill}" stroke-width="4"/>
        <path d="M118 236h176" stroke="{template.highlight_fill}" stroke-width="10" stroke-linecap="round"/>
        <path d="M118 274h118" stroke="{template.body_fill}" stroke-opacity="0.4" stroke-width="10" stroke-linecap="round"/>
        <path d="M118 312h140" stroke="{template.body_fill}" stroke-opacity="0.22" stroke-width="10" stroke-linecap="round"/>
        <circle cx="654" cy="278" r="58" fill="{template.accent_primary}" opacity="0.24"/>
        <circle cx="654" cy="278" r="28" fill="{template.highlight_fill}" opacity="0.34"/>
        <circle cx="1016" cy="278" r="58" fill="{template.accent_secondary}" opacity="0.22"/>
        <circle cx="1016" cy="278" r="28" fill="{template.accent_primary}" opacity="0.32"/>
        <rect x="122" y="446" width="220" height="24" rx="12" fill="{template.highlight_fill}" opacity="0.9"/>
        <rect x="122" y="484" width="340" height="18" rx="9" fill="{template.body_fill}" opacity="0.24"/>
        <rect x="122" y="522" width="266" height="18" rx="9" fill="{template.body_fill}" opacity="0.18"/>
        """

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{template.background_start}"/>
      <stop offset="50%" stop-color="{template.background_mid}"/>
      <stop offset="100%" stop-color="{template.background_end}"/>
    </linearGradient>
    <radialGradient id="glow_a" cx="74%" cy="34%" r="38%">
      <stop offset="0%" stop-color="{template.highlight_fill}" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="{template.highlight_fill}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow_b" cx="20%" cy="76%" r="38%">
      <stop offset="0%" stop-color="{template.accent_primary}" stop-opacity="0.24"/>
      <stop offset="100%" stop-color="{template.accent_primary}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#glow_a)"/>
  <rect width="100%" height="100%" fill="url(#glow_b)"/>
  {composition}
  <text x="72" y="42" font-size="22" font-weight="800" fill="{template.accent_tertiary}">Preview template: {html.escape(template.template_id)}</text>
  {title_svg}
  {subtitle_svg}
  <text x="72" y="560" font-size="22" font-weight="800" fill="{template.accent_primary}">Click this card to open the full-size preview image.</text>
  <text x="72" y="646" font-size="20" font-weight="700" fill="{template.body_fill}">Palette: {html.escape(template.background_start)} / {html.escape(template.background_mid)} / {html.escape(template.background_end)}</text>
</svg>
"""


def render_template_examples_html(rows: list[dict[str, str]], seconds: int) -> str:
    cards = "\n".join(
        f"""
        <article class="card">
          <video controls loop muted playsinline poster="{html.escape(row['svg'].replace('.svg', '.png'))}">
            <source src="{html.escape(row['mp4'])}" type="video/mp4">
          </video>
          <div class="meta">
            <div class="index">Example {html.escape(row['index'])}</div>
            <h2>{html.escape(row['title'])}</h2>
            <p><code>{html.escape(row['template_id'])}</code></p>
            <p>{html.escape(row['layout'])}</p>
          </div>
        </article>
        """
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PM Template Examples</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #050816; color: #f8fafc; }}
    header {{ padding: 30px 28px; background: linear-gradient(135deg, #111827, #1d4ed8); border-bottom: 1px solid rgba(255,255,255,0.08); }}
    main {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
    .card {{ border: 1px solid rgba(255,255,255,0.12); border-radius: 22px; overflow: hidden; background: rgba(15, 23, 42, 0.96); box-shadow: 0 20px 45px rgba(0,0,0,0.36); }}
    video {{ width: 100%; height: auto; display: block; background: #000; }}
    .meta {{ padding: 16px; }}
    .index {{ display: inline-block; margin-bottom: 10px; padding: 6px 12px; border-radius: 999px; background: #f59e0b; color: #111827; font-weight: 900; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(30px, 5vw, 48px); }}
    header p {{ margin: 0; max-width: 900px; color: #dbeafe; line-height: 1.6; }}
    .hint {{ margin-top: 8px; color: #cbd5e1; font-size: 14px; }}
    code {{ color: #fbbf24; }}
  </style>
</head>
<body>
  <header>
    <h1>Five PM template examples</h1>
    <p>These are short looping previews, each about {seconds} seconds long, so you can compare the strongest template styles quickly.</p>
    <div class="hint">Click play on any tile. These are static layout demos, not full narrated videos.</div>
  </header>
  <main>
    <div class="grid">
      {cards}
    </div>
  </main>
</body>
</html>
"""


def _render_preview_mp4(png_path: Path, output_path: Path, seconds: int) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to render template example videos.")
    frames = seconds * 30
    fade_out = max(0, seconds - 0.35)
    subprocess.run(
        [
            executable,
            "-y",
            "-loop",
            "1",
            "-i",
            str(png_path),
            "-vf",
            (
                f"scale=1280:720,zoompan=z='min(zoom+0.0002,1.02)':"
                f"d={frames}:s=1280x720:fps=30,"
                f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out}:d=0.35,"
                "format=yuv420p"
            ),
            "-t",
            str(seconds),
            "-an",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _wrap_preview_text(text: str, width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) <= width or not current:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    return lines[:max_lines]
