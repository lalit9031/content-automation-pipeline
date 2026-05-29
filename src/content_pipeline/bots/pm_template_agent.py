from __future__ import annotations

import base64
import json
import shutil
import subprocess
from dataclasses import dataclass
from html import escape
from pathlib import Path

try:
    import cairosvg
except ImportError:  # pragma: no cover - optional dependency
    cairosvg = None


WIDTH = 1280
HEIGHT = 720
ASSET_DIR = Path(__file__).resolve().parents[3] / "assets"
BRAND_LOGO_PATH = ASSET_DIR / "brand" / "tech_with_lalit_logo.png"
PIPELINE_SVG_PATH = ASSET_DIR / "content_automation_pipeline.svg"


@dataclass(frozen=True)
class PMTemplateConcept:
    template_id: str
    name: str
    layout: str
    background_start: str
    background_mid: str
    background_end: str
    accent_primary: str
    accent_secondary: str
    accent_tertiary: str
    panel_fill: str
    panel_border: str
    highlight_fill: str
    body_fill: str
    card_fill: str
    card_border: str


CONCEPTS = [
    PMTemplateConcept(
        "hero_showcase_01",
        "Hero Showcase",
        "hero_showcase",
        "#09111d",
        "#0f172a",
        "#0b4b6f",
        "#38bdf8",
        "#f59e0b",
        "#ffffff",
        "#0f172a",
        "#7dd3fc",
        "#f59e0b",
        "#dbeafe",
        "#111827",
        "#38bdf8",
    ),
    PMTemplateConcept(
        "collage_grid_01",
        "Collage Grid",
        "collage_grid",
        "#f7f4ef",
        "#e5d5c4",
        "#20263f",
        "#0ea5e9",
        "#fb7185",
        "#111827",
        "#ffffff",
        "#cbd5e1",
        "#f59e0b",
        "#1f2937",
        "#ffffff",
        "#60a5fa",
    ),
    PMTemplateConcept(
        "architecture_board_01",
        "Architecture Board",
        "architecture_board",
        "#050816",
        "#111827",
        "#1d4ed8",
        "#a78bfa",
        "#22d3ee",
        "#ffffff",
        "#0f172a",
        "#38bdf8",
        "#f472b6",
        "#dbeafe",
        "#111827",
        "#38bdf8",
    ),
    PMTemplateConcept(
        "sticky_wall_01",
        "Sticky Wall",
        "sticky_wall",
        "#fff3c4",
        "#fde68a",
        "#1f3b8b",
        "#f59e0b",
        "#22c55e",
        "#111827",
        "#ffffff",
        "#f59e0b",
        "#fb7185",
        "#1f2937",
        "#ffffff",
        "#f59e0b",
    ),
    PMTemplateConcept(
        "ai_dashboard_01",
        "AI Dashboard",
        "ai_dashboard",
        "#07111f",
        "#0f172a",
        "#312e81",
        "#38bdf8",
        "#f59e0b",
        "#ffffff",
        "#0f172a",
        "#60a5fa",
        "#38bdf8",
        "#dbeafe",
        "#111827",
        "#60a5fa",
    ),
    PMTemplateConcept(
        "paper_cutout_01",
        "Paper Cutout",
        "paper_cutout",
        "#fdf2f8",
        "#fde68a",
        "#1e3a8a",
        "#ec4899",
        "#22c55e",
        "#111827",
        "#ffffff",
        "#fb7185",
        "#1f2937",
        "#ffffff",
        "#f59e0b",
        "#60a5fa",
    ),
    PMTemplateConcept(
        "night_grid_01",
        "Night Grid",
        "night_grid",
        "#020617",
        "#111827",
        "#312e81",
        "#60a5fa",
        "#f472b6",
        "#ffffff",
        "#0f172a",
        "#38bdf8",
        "#f59e0b",
        "#dbeafe",
        "#111827",
        "#38bdf8",
    ),
    PMTemplateConcept(
        "editorial_blueprint_01",
        "Editorial Blueprint",
        "editorial_blueprint",
        "#f8fafc",
        "#e2e8f0",
        "#1e293b",
        "#0f172a",
        "#38bdf8",
        "#111827",
        "#ffffff",
        "#94a3b8",
        "#0ea5e9",
        "#1f2937",
        "#ffffff",
        "#94a3b8",
    ),
]


def build_pm_template_concepts() -> list[PMTemplateConcept]:
    return [*CONCEPTS]


def write_pm_template_agent_examples(output_dir: Path, topic: str = "Project Management AI", seconds: int = 4) -> Path:
    if seconds < 3 or seconds > 5:
        raise ValueError("Template agent examples must be 3 to 5 seconds long.")
    if cairosvg is None:
        raise RuntimeError("cairosvg is required to render template agent examples.")
    examples_dir = output_dir / "pm_template_agent"
    examples_dir.mkdir(parents=True, exist_ok=True)
    for existing in examples_dir.iterdir():
        if existing.is_file() or existing.is_symlink():
            existing.unlink()
    rows: list[dict[str, str]] = []
    validation: list[dict[str, object]] = []
    for index, concept in enumerate(build_pm_template_concepts(), start=1):
        slug = f"{index:02d}_{concept.template_id}"
        svg_path = examples_dir / f"{slug}.svg"
        png_path = examples_dir / f"{slug}.png"
        mp4_path = examples_dir / f"{slug}.mp4"
        svg = render_pm_template_concept_svg(concept, topic)
        validation.append(verify_pm_template_concept(concept, topic))
        svg_path.write_text(svg, encoding="utf-8")
        png_path.write_bytes(cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=WIDTH, output_height=HEIGHT))
        _render_preview_mp4(png_path, mp4_path, seconds)
        rows.append(
            {
                "index": str(index),
                "name": concept.name,
                "template_id": concept.template_id,
                "layout": concept.layout,
                "mp4": mp4_path.name,
                "png": png_path.name,
            }
        )
    failed = [entry for entry in validation if not bool(entry.get("passes"))]
    if failed:
        raise RuntimeError(
            "Template agent validation failed: "
            + ", ".join(str(item.get("template_id")) for item in failed)
        )
    html_path = examples_dir / "template_agent_examples.html"
    html_path.write_text(render_template_agent_html(rows, topic, seconds), encoding="utf-8")
    (examples_dir / "template_agent_validation.json").write_text(
        json.dumps(validation, indent=2) + "\n",
        encoding="utf-8",
    )
    return html_path


def render_template_agent_html(rows: list[dict[str, str]], topic: str, seconds: int) -> str:
    cards = "\n".join(
        f"""
        <article class="card">
          <video controls loop muted playsinline poster="{escape(row['png'])}">
            <source src="{escape(row['mp4'])}" type="video/mp4">
          </video>
          <div class="meta">
            <div class="chip">Concept {escape(row['index'])}</div>
            <h2>{escape(row['name'])}</h2>
            <p><code>{escape(row['template_id'])}</code></p>
            <p>{escape(row['layout'])}</p>
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
  <title>PM Template Agent Examples</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background:
      radial-gradient(circle at top left, rgba(59,130,246,0.24), transparent 32%),
      radial-gradient(circle at bottom right, rgba(245,158,11,0.18), transparent 24%),
      #050816; color: #f8fafc; }}
    header {{ padding: 34px 28px 28px; background: linear-gradient(135deg, rgba(17,24,39,0.96), rgba(29,78,216,0.92)); border-bottom: 1px solid rgba(255,255,255,0.08); }}
    main {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
    .card {{ border-radius: 22px; overflow: hidden; border: 1px solid rgba(255,255,255,0.12); box-shadow: 0 20px 45px rgba(0,0,0,0.36); background: rgba(15, 23, 42, 0.96); }}
    video {{ width: 100%; height: auto; display: block; background: #000; }}
    .meta {{ padding: 16px; }}
    .chip {{ display: inline-block; margin-bottom: 10px; padding: 6px 12px; border-radius: 999px; background: #f59e0b; color: #111827; font-weight: 900; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(30px, 5vw, 48px); }}
    header p {{ margin: 0; max-width: 900px; color: #dbeafe; line-height: 1.6; }}
    .hint {{ margin-top: 8px; color: #cbd5e1; font-size: 14px; }}
    code {{ color: #fbbf24; }}
  </style>
</head>
<body>
  <header>
    <h1>Template agent concepts</h1>
    <p>Ten creative template directions for <strong>{escape(topic)}</strong>, each previewed for about {seconds} seconds.</p>
    <div class="hint">These are intentionally more varied: hero, collage, workflow, split-scene, architecture, sticky-wall, paper-cutout, night-grid, and analytics-board concepts.</div>
  </header>
  <main>
    <div class="grid">
      {cards}
    </div>
  </main>
</body>
</html>
"""


def render_pm_template_concept_svg(concept: PMTemplateConcept, topic: str) -> str:
    title, title_font, title_gap, title_start_y = _fit_title(topic.upper(), concept.layout)
    if concept.layout == "hero_showcase":
        art = _hero_showcase(concept)
    elif concept.layout == "collage_grid":
        art = _collage_grid(concept)
    elif concept.layout == "architecture_board":
        art = _architecture_board(concept)
    elif concept.layout == "workflow_arc":
        art = _workflow_arc(concept)
    elif concept.layout == "split_storyboard":
        art = _split_storyboard(concept)
    elif concept.layout == "sticky_wall":
        art = _sticky_wall(concept)
    elif concept.layout == "paper_cutout":
        art = _paper_cutout(concept)
    elif concept.layout == "night_grid":
        art = _night_grid(concept)
    elif concept.layout == "editorial_blueprint":
        art = _editorial_blueprint(concept)
    else:
        art = _ai_dashboard(concept)
    title_svg = "".join(
        f'<text x="72" y="{title_start_y + idx * title_gap}" font-size="{title_font}" font-weight="900" fill="{concept.highlight_fill}">{escape(line)}</text>'
        for idx, line in enumerate(title)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{concept.background_start}"/>
      <stop offset="50%" stop-color="{concept.background_mid}"/>
      <stop offset="100%" stop-color="{concept.background_end}"/>
    </linearGradient>
    <radialGradient id="glow" cx="70%" cy="32%" r="44%">
      <stop offset="0%" stop-color="{concept.accent_primary}" stop-opacity="0.46"/>
      <stop offset="100%" stop-color="{concept.accent_primary}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">
      <path d="M44 0H0V44" fill="none" stroke="{concept.accent_tertiary}" stroke-opacity="0.10" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#grid)"/>
  <rect width="100%" height="100%" fill="url(#glow)"/>
  {art}
  <rect x="54" y="44" width="260" height="58" rx="20" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="2" opacity="0.95"/>
  <text x="86" y="82" font-size="20" font-weight="900" fill="{concept.accent_tertiary}">TEMPLATE AGENT</text>
  {title_svg}
  <rect x="72" y="482" width="560" height="72" rx="22" fill="{concept.panel_fill}" opacity="0.96" stroke="{concept.panel_border}" stroke-width="2"/>
  <text x="104" y="526" font-size="28" font-weight="900" fill="{concept.accent_secondary}">{escape(concept.name)}</text>
  <text x="72" y="622" font-size="18" font-weight="700" fill="{concept.body_fill}">A richer concept with workflow, architecture, and dashboard storytelling.</text>
  <text x="72" y="658" font-size="18" font-weight="700" fill="{concept.body_fill}">Topic: {escape(topic)}</text>
</svg>
"""


def _fit_title(text: str, layout: str) -> tuple[list[str], int, int, int]:
    limit = 18 if layout in {"hero_showcase", "collage_grid", "night_grid"} else 16
    lines = _wrap_text(text, limit, 2)
    font = 52
    gap = 58
    start = 120
    max_width = 1120
    while font > 38:
        widest = max((_estimate_text_width(line, font) for line in lines), default=0)
        title_height = len(lines) * font + max(0, len(lines) - 1) * max(8, gap - font)
        footer_top = 482
        if widest <= max_width and start + title_height <= footer_top - 18:
            break
        font -= 2
        gap = max(42, gap - 2)
        start = max(104, start - 2)
    return lines, font, gap, start


def _estimate_text_width(text: str, font_size: int) -> int:
    return int(len(text) * font_size * 0.58)


def _load_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/svg+xml"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _brand_logo_image(x: int, y: int, width: int, height: int) -> str:
    href = _load_data_uri(BRAND_LOGO_PATH)
    if not href:
        return ""
    return (
        f'<image href="{href}" x="{x}" y="{y}" width="{width}" height="{height}" '
        'preserveAspectRatio="xMidYMid meet" opacity="0.95"/>'
    )


def _pipeline_image(x: int, y: int, width: int, height: int) -> str:
    href = _load_data_uri(PIPELINE_SVG_PATH)
    if not href:
        return ""
    return (
        f'<image href="{href}" x="{x}" y="{y}" width="{width}" height="{height}" '
        'preserveAspectRatio="xMidYMid meet" opacity="0.95"/>'
    )


def _hero_showcase(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="48" y="96" width="1184" height="540" rx="44" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.96"/>
    <rect x="76" y="124" width="356" height="484" rx="36" fill="{concept.background_start}" opacity="0.56"/>
    <rect x="460" y="124" width="720" height="484" rx="36" fill="{concept.background_mid}" opacity="0.82"/>
    <rect x="498" y="168" width="276" height="216" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="802" y="168" width="340" height="216" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="498" y="412" width="644" height="154" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <circle cx="242" cy="312" r="122" fill="{concept.accent_primary}" opacity="0.20"/>
    <circle cx="242" cy="312" r="74" fill="{concept.highlight_fill}" opacity="0.28"/>
    <path d="M140 476h200" stroke="{concept.body_fill}" stroke-opacity="0.30" stroke-width="8" stroke-linecap="round"/>
    <path d="M140 520h160" stroke="{concept.body_fill}" stroke-opacity="0.18" stroke-width="8" stroke-linecap="round"/>
    <rect x="162" y="510" width="220" height="16" rx="8" fill="{concept.accent_secondary}" opacity="0.46"/>
    <rect x="534" y="212" width="136" height="34" rx="17" fill="{concept.highlight_fill}"/>
    <rect x="842" y="212" width="230" height="34" rx="17" fill="{concept.accent_primary}"/>
    <rect x="534" y="468" width="214" height="24" rx="12" fill="{concept.highlight_fill}" opacity="0.88"/>
    <rect x="534" y="512" width="266" height="24" rx="12" fill="{concept.accent_secondary}" opacity="0.78"/>
    <rect x="838" y="468" width="230" height="24" rx="12" fill="{concept.accent_primary}" opacity="0.84"/>
    <rect x="838" y="512" width="176" height="24" rx="12" fill="{concept.highlight_fill}" opacity="0.88"/>
    <rect x="864" y="250" width="130" height="92" rx="16" fill="{concept.background_end}" opacity="0.42"/>
    <path d="M552 303h198" stroke="{concept.body_fill}" stroke-opacity="0.28" stroke-width="8" stroke-linecap="round"/>
    <path d="M552 336h152" stroke="{concept.body_fill}" stroke-opacity="0.18" stroke-width="8" stroke-linecap="round"/>
    <rect x="880" y="458" width="188" height="114" rx="20" fill="{concept.background_end}" opacity="0.28"/>
    {_brand_logo_image(522, 154, 110, 110)}
    {_pipeline_image(886, 228, 96, 96)}
    """


def _collage_grid(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="38" y="110" width="1204" height="530" rx="40" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.96"/>
    <rect x="60" y="134" width="390" height="224" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="466" y="134" width="430" height="224" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="912" y="134" width="306" height="224" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="60" y="378" width="474" height="234" rx="28" fill="{concept.background_end}" opacity="0.34"/>
    <rect x="554" y="378" width="246" height="234" rx="28" fill="{concept.background_mid}" opacity="0.52"/>
    <rect x="820" y="378" width="398" height="234" rx="28" fill="{concept.background_start}" opacity="0.48"/>
    <circle cx="176" cy="248" r="58" fill="{concept.accent_primary}" opacity="0.28"/>
    <circle cx="360" cy="248" r="58" fill="{concept.highlight_fill}" opacity="0.24"/>
    <circle cx="682" cy="248" r="58" fill="{concept.accent_secondary}" opacity="0.28"/>
    <circle cx="872" cy="248" r="58" fill="{concept.accent_primary}" opacity="0.22"/>
    <circle cx="1074" cy="248" r="58" fill="{concept.highlight_fill}" opacity="0.24"/>
    <path d="M86 430h210" stroke="{concept.body_fill}" stroke-opacity="0.28" stroke-width="8" stroke-linecap="round"/>
    <path d="M86 474h280" stroke="{concept.body_fill}" stroke-opacity="0.20" stroke-width="8" stroke-linecap="round"/>
    <path d="M86 518h220" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="8" stroke-linecap="round"/>
    <rect x="592" y="432" width="158" height="34" rx="17" fill="{concept.highlight_fill}"/>
    <rect x="862" y="430" width="212" height="34" rx="17" fill="{concept.accent_primary}"/>
    <rect x="862" y="484" width="154" height="24" rx="12" fill="{concept.highlight_fill}" opacity="0.86"/>
    <rect x="862" y="526" width="190" height="24" rx="12" fill="{concept.accent_secondary}" opacity="0.78"/>
    {_brand_logo_image(966, 196, 108, 108)}
    {_pipeline_image(580, 422, 128, 128)}
    """


def _architecture_board(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="48" y="110" width="1184" height="534" rx="42" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.96"/>
    <rect x="76" y="144" width="340" height="452" rx="32" fill="{concept.background_start}" opacity="0.48"/>
    <rect x="440" y="144" width="374" height="452" rx="32" fill="{concept.background_mid}" opacity="0.72"/>
    <rect x="836" y="144" width="360" height="452" rx="32" fill="{concept.background_end}" opacity="0.46"/>
    <rect x="106" y="186" width="236" height="54" rx="18" fill="{concept.highlight_fill}"/>
    <path d="M164 258h120" stroke="{concept.body_fill}" stroke-opacity="0.34" stroke-width="8" stroke-linecap="round"/>
    <path d="M164 302h172" stroke="{concept.body_fill}" stroke-opacity="0.24" stroke-width="8" stroke-linecap="round"/>
    <path d="M164 346h146" stroke="{concept.body_fill}" stroke-opacity="0.16" stroke-width="8" stroke-linecap="round"/>
    <rect x="472" y="186" width="290" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="472" y="302" width="290" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="472" y="418" width="290" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="866" y="190" width="264" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="866" y="304" width="264" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="866" y="418" width="264" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <path d="M320 270h114" stroke="{concept.accent_primary}" stroke-width="6" stroke-linecap="round"/>
    <path d="M320 318h114" stroke="{concept.accent_secondary}" stroke-width="6" stroke-linecap="round"/>
    <path d="M320 366h114" stroke="{concept.highlight_fill}" stroke-width="6" stroke-linecap="round"/>
    <path d="M762 238h72" stroke="{concept.accent_primary}" stroke-width="6" stroke-linecap="round"/>
    <path d="M762 350h72" stroke="{concept.accent_secondary}" stroke-width="6" stroke-linecap="round"/>
    <path d="M762 464h72" stroke="{concept.highlight_fill}" stroke-width="6" stroke-linecap="round"/>
    <path d="M672 238h90" stroke="{concept.body_fill}" stroke-opacity="0.3" stroke-width="4" stroke-linecap="round"/>
    <path d="M672 350h90" stroke="{concept.body_fill}" stroke-opacity="0.3" stroke-width="4" stroke-linecap="round"/>
    <path d="M672 464h90" stroke="{concept.body_fill}" stroke-opacity="0.3" stroke-width="4" stroke-linecap="round"/>
    <text x="596" y="546" text-anchor="middle" font-size="24" font-weight="900" fill="{concept.highlight_fill}">FLOW</text>
    <text x="998" y="546" text-anchor="middle" font-size="24" font-weight="900" fill="{concept.highlight_fill}">PUBLISH</text>
    {_pipeline_image(124, 428, 180, 180)}
    {_brand_logo_image(920, 172, 120, 120)}
    """


def _split_storyboard(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="48" y="120" width="1150" height="510" rx="42" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.96"/>
    <rect x="72" y="150" width="470" height="450" rx="34" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="578" y="150" width="592" height="450" rx="34" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="92" y="180" width="180" height="46" rx="16" fill="{concept.accent_primary}"/>
    <rect x="92" y="246" width="310" height="20" rx="10" fill="{concept.body_fill}" opacity="0.32"/>
    <rect x="92" y="284" width="260" height="20" rx="10" fill="{concept.body_fill}" opacity="0.24"/>
    <rect x="92" y="322" width="336" height="20" rx="10" fill="{concept.body_fill}" opacity="0.18"/>
    <rect x="92" y="378" width="136" height="84" rx="16" fill="{concept.background_end}" opacity="0.22"/>
    <rect x="244" y="378" width="136" height="84" rx="16" fill="{concept.background_mid}" opacity="0.22"/>
    <rect x="396" y="378" width="84" height="84" rx="16" fill="{concept.highlight_fill}" opacity="0.24"/>
    <circle cx="434" cy="236" r="72" fill="{concept.accent_secondary}" opacity="0.20"/>
    <circle cx="434" cy="236" r="42" fill="{concept.accent_primary}" opacity="0.24"/>
    <rect x="630" y="190" width="210" height="150" rx="24" fill="{concept.background_start}" opacity="0.52" stroke="{concept.accent_primary}" stroke-width="2"/>
    <rect x="874" y="190" width="248" height="150" rx="24" fill="{concept.background_end}" opacity="0.48" stroke="{concept.accent_secondary}" stroke-width="2"/>
    <rect x="630" y="366" width="492" height="176" rx="24" fill="{concept.background_mid}" opacity="0.68" stroke="{concept.accent_tertiary}" stroke-opacity="0.18" stroke-width="2"/>
    <path d="M660 446H1080" stroke="{concept.accent_tertiary}" stroke-opacity="0.26" stroke-width="4" stroke-dasharray="12 10"/>
    <path d="M700 414L810 414L810 382" stroke="{concept.accent_primary}" stroke-width="5" fill="none"/>
    <path d="M810 382L920 382L920 414" stroke="{concept.accent_secondary}" stroke-width="5" fill="none"/>
    <path d="M920 414L1030 414L1030 382" stroke="{concept.highlight_fill}" stroke-width="5" fill="none"/>
    <circle cx="700" cy="414" r="18" fill="{concept.accent_primary}"/>
    <circle cx="810" cy="382" r="18" fill="{concept.accent_secondary}"/>
    <circle cx="920" cy="414" r="18" fill="{concept.highlight_fill}"/>
    <circle cx="1030" cy="382" r="18" fill="{concept.accent_tertiary}"/>
    """


def _workflow_arc(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="58" y="126" width="1160" height="500" rx="40" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.94"/>
    <path d="M110 370 C240 220 410 220 540 370 S840 520 1090 290" fill="none" stroke="{concept.accent_primary}" stroke-width="8" stroke-linecap="round"/>
    <circle cx="110" cy="370" r="30" fill="{concept.accent_primary}"/>
    <circle cx="330" cy="278" r="30" fill="{concept.accent_secondary}"/>
    <circle cx="540" cy="370" r="30" fill="{concept.highlight_fill}"/>
    <circle cx="760" cy="472" r="30" fill="{concept.accent_secondary}"/>
    <circle cx="1090" cy="290" r="30" fill="{concept.accent_primary}"/>
    <rect x="84" y="184" width="190" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="280" y="168" width="190" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="476" y="184" width="190" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="674" y="334" width="190" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="872" y="228" width="190" height="88" rx="20" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <text x="176" y="238" text-anchor="middle" font-size="22" font-weight="900" fill="{concept.highlight_fill}">INPUT</text>
    <text x="372" y="222" text-anchor="middle" font-size="22" font-weight="900" fill="{concept.highlight_fill}">PLAN</text>
    <text x="572" y="238" text-anchor="middle" font-size="22" font-weight="900" fill="{concept.highlight_fill}">BUILD</text>
    <text x="770" y="388" text-anchor="middle" font-size="22" font-weight="900" fill="{concept.highlight_fill}">VALIDATE</text>
    <text x="968" y="282" text-anchor="middle" font-size="22" font-weight="900" fill="{concept.highlight_fill}">SHARE</text>
    <rect x="84" y="474" width="540" height="120" rx="26" fill="{concept.background_end}" opacity="0.42"/>
    <rect x="674" y="474" width="388" height="120" rx="26" fill="{concept.background_mid}" opacity="0.70"/>
    <path d="M718 528h300" stroke="{concept.body_fill}" stroke-opacity="0.45" stroke-width="10" stroke-linecap="round"/>
    <path d="M718 560h220" stroke="{concept.body_fill}" stroke-opacity="0.28" stroke-width="10" stroke-linecap="round"/>
    <rect x="96" y="496" width="132" height="34" rx="17" fill="{concept.highlight_fill}"/>
    """


def _architecture_stack(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="54" y="126" width="1172" height="502" rx="40" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.95"/>
    <rect x="86" y="166" width="296" height="420" rx="30" fill="{concept.background_start}" opacity="0.42"/>
    <rect x="420" y="166" width="358" height="120" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="420" y="304" width="358" height="120" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="420" y="442" width="358" height="120" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="810" y="166" width="352" height="396" rx="30" fill="{concept.background_end}" opacity="0.42"/>
    <path d="M260 234h112" stroke="{concept.accent_primary}" stroke-width="6" stroke-linecap="round"/>
    <path d="M260 276h112" stroke="{concept.accent_secondary}" stroke-width="6" stroke-linecap="round"/>
    <path d="M260 318h112" stroke="{concept.highlight_fill}" stroke-width="6" stroke-linecap="round"/>
    <path d="M260 360h112" stroke="{concept.accent_primary}" stroke-width="6" stroke-linecap="round"/>
    <circle cx="260" cy="234" r="18" fill="{concept.accent_primary}"/>
    <circle cx="260" cy="276" r="18" fill="{concept.accent_secondary}"/>
    <circle cx="260" cy="318" r="18" fill="{concept.highlight_fill}"/>
    <circle cx="260" cy="360" r="18" fill="{concept.accent_primary}"/>
    <rect x="456" y="194" width="198" height="34" rx="17" fill="{concept.highlight_fill}"/>
    <rect x="456" y="332" width="198" height="34" rx="17" fill="{concept.accent_primary}"/>
    <rect x="456" y="470" width="198" height="34" rx="17" fill="{concept.accent_secondary}"/>
    <path d="M846 236h266" stroke="{concept.accent_primary}" stroke-width="10" stroke-linecap="round"/>
    <path d="M846 294h214" stroke="{concept.body_fill}" stroke-opacity="0.38" stroke-width="10" stroke-linecap="round"/>
    <path d="M846 352h238" stroke="{concept.body_fill}" stroke-opacity="0.26" stroke-width="10" stroke-linecap="round"/>
    <path d="M846 410h180" stroke="{concept.body_fill}" stroke-opacity="0.18" stroke-width="10" stroke-linecap="round"/>
    """


def _sticky_wall(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="48" y="118" width="1186" height="520" rx="40" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.95"/>
    <rect x="80" y="152" width="310" height="130" rx="24" fill="#fef08a"/>
    <rect x="418" y="152" width="310" height="130" rx="24" fill="#fdba74"/>
    <rect x="756" y="152" width="390" height="130" rx="24" fill="#f9a8d4"/>
    <rect x="80" y="314" width="320" height="250" rx="24" fill="#bfdbfe"/>
    <rect x="430" y="314" width="340" height="250" rx="24" fill="#bbf7d0"/>
    <rect x="798" y="314" width="348" height="250" rx="24" fill="#e9d5ff"/>
    <rect x="110" y="188" width="180" height="24" rx="12" fill="{concept.background_end}" opacity="0.22"/>
    <rect x="110" y="230" width="138" height="18" rx="9" fill="{concept.background_end}" opacity="0.18"/>
    <rect x="448" y="188" width="182" height="24" rx="12" fill="{concept.background_end}" opacity="0.22"/>
    <rect x="448" y="230" width="158" height="18" rx="9" fill="{concept.background_end}" opacity="0.18"/>
    <rect x="786" y="188" width="284" height="24" rx="12" fill="{concept.background_end}" opacity="0.22"/>
    <path d="M118 376h262" stroke="{concept.background_end}" stroke-opacity="0.30" stroke-width="8" stroke-linecap="round"/>
    <path d="M118 420h218" stroke="{concept.background_end}" stroke-opacity="0.22" stroke-width="8" stroke-linecap="round"/>
    <path d="M118 464h240" stroke="{concept.background_end}" stroke-opacity="0.18" stroke-width="8" stroke-linecap="round"/>
    <path d="M468 376h280" stroke="{concept.background_end}" stroke-opacity="0.30" stroke-width="8" stroke-linecap="round"/>
    <path d="M468 420h210" stroke="{concept.background_end}" stroke-opacity="0.22" stroke-width="8" stroke-linecap="round"/>
    <path d="M468 464h258" stroke="{concept.background_end}" stroke-opacity="0.18" stroke-width="8" stroke-linecap="round"/>
    <path d="M834 376h246" stroke="{concept.background_end}" stroke-opacity="0.30" stroke-width="8" stroke-linecap="round"/>
    <path d="M834 420h196" stroke="{concept.background_end}" stroke-opacity="0.22" stroke-width="8" stroke-linecap="round"/>
    <path d="M834 464h230" stroke="{concept.background_end}" stroke-opacity="0.18" stroke-width="8" stroke-linecap="round"/>
    <circle cx="986" cy="534" r="56" fill="{concept.accent_primary}" opacity="0.2"/>
    <circle cx="986" cy="534" r="30" fill="{concept.highlight_fill}" opacity="0.24"/>
    """


def _ai_dashboard(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="54" y="124" width="1172" height="500" rx="40" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.95"/>
    <rect x="80" y="160" width="318" height="150" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="424" y="160" width="318" height="150" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="768" y="160" width="348" height="150" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="80" y="336" width="494" height="234" rx="30" fill="{concept.background_end}" opacity="0.42"/>
    <rect x="604" y="336" width="512" height="234" rx="30" fill="{concept.background_mid}" opacity="0.70"/>
    <path d="M108 244h118" stroke="{concept.accent_primary}" stroke-width="8" stroke-linecap="round"/>
    <path d="M108 278h186" stroke="{concept.body_fill}" stroke-opacity="0.36" stroke-width="8" stroke-linecap="round"/>
    <path d="M452 244h118" stroke="{concept.accent_secondary}" stroke-width="8" stroke-linecap="round"/>
    <path d="M452 278h186" stroke="{concept.body_fill}" stroke-opacity="0.36" stroke-width="8" stroke-linecap="round"/>
    <path d="M796 244h160" stroke="{concept.highlight_fill}" stroke-width="8" stroke-linecap="round"/>
    <path d="M796 278h240" stroke="{concept.body_fill}" stroke-opacity="0.36" stroke-width="8" stroke-linecap="round"/>
    <path d="M122 496h150l40-66 54 42 56-84 62 58" fill="none" stroke="{concept.accent_primary}" stroke-width="5"/>
    <path d="M642 514h116l30-40 52 18 56-72 72 34" fill="none" stroke="{concept.accent_secondary}" stroke-width="5"/>
    <circle cx="1020" cy="450" r="88" fill="{concept.accent_primary}" opacity="0.20"/>
    <circle cx="1020" cy="450" r="54" fill="{concept.highlight_fill}" opacity="0.24"/>
    <path d="M1020 400l20 44h-16l12 40-36-56h18l-12-28z" fill="{concept.highlight_fill}"/>
    """


def _paper_cutout(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="50" y="104" width="1180" height="540" rx="44" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.96"/>
    <path d="M110 160h490v430H110z" fill="#fffaf2" opacity="0.96"/>
    <path d="M622 160h560v430H622z" fill="#111827" opacity="0.88"/>
    <rect x="150" y="206" width="240" height="54" rx="18" fill="{concept.highlight_fill}"/>
    <rect x="150" y="286" width="320" height="26" rx="13" fill="{concept.body_fill}" opacity="0.26"/>
    <rect x="150" y="334" width="280" height="26" rx="13" fill="{concept.body_fill}" opacity="0.18"/>
    <rect x="150" y="392" width="180" height="170" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="652" y="206" width="248" height="120" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="920" y="206" width="220" height="120" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="652" y="356" width="488" height="166" rx="24" fill="{concept.background_end}" opacity="0.48"/>
    <circle cx="770" cy="266" r="52" fill="{concept.accent_primary}" opacity="0.24"/>
    <circle cx="1028" cy="266" r="52" fill="{concept.accent_secondary}" opacity="0.24"/>
    <circle cx="900" cy="438" r="86" fill="{concept.highlight_fill}" opacity="0.18"/>
    <rect x="180" y="426" width="120" height="22" rx="11" fill="{concept.accent_secondary}" opacity="0.88"/>
    <rect x="180" y="466" width="88" height="22" rx="11" fill="{concept.accent_primary}" opacity="0.82"/>
    <rect x="694" y="398" width="228" height="22" rx="11" fill="{concept.body_fill}" opacity="0.26"/>
    <rect x="694" y="442" width="338" height="22" rx="11" fill="{concept.body_fill}" opacity="0.18"/>
    {_brand_logo_image(702, 220, 84, 84)}
    {_pipeline_image(916, 224, 78, 78)}
    """


def _night_grid(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="40" y="104" width="1200" height="548" rx="44" fill="{concept.panel_fill}" stroke="{concept.panel_border}" stroke-width="4" opacity="0.96"/>
    <rect x="70" y="136" width="1140" height="110" rx="26" fill="{concept.background_start}" opacity="0.56"/>
    <rect x="70" y="268" width="1140" height="310" rx="26" fill="{concept.background_end}" opacity="0.42"/>
    <path d="M110 348h1060" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M110 410h1060" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M110 472h1060" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M184 298v250" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M358 298v250" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M532 298v250" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M706 298v250" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M880 298v250" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <path d="M1054 298v250" stroke="{concept.body_fill}" stroke-opacity="0.14" stroke-width="2"/>
    <rect x="92" y="170" width="286" height="44" rx="20" fill="{concept.accent_primary}"/>
    <rect x="410" y="170" width="460" height="44" rx="20" fill="{concept.highlight_fill}"/>
    <rect x="900" y="170" width="240" height="44" rx="20" fill="{concept.accent_secondary}"/>
    <rect x="150" y="314" width="240" height="190" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="438" y="314" width="264" height="190" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <rect x="734" y="314" width="426" height="190" rx="28" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="3"/>
    <circle cx="270" cy="408" r="62" fill="{concept.accent_primary}" opacity="0.22"/>
    <circle cx="570" cy="408" r="62" fill="{concept.highlight_fill}" opacity="0.22"/>
    <circle cx="946" cy="408" r="62" fill="{concept.accent_secondary}" opacity="0.22"/>
    <rect x="786" y="356" width="186" height="20" rx="10" fill="{concept.body_fill}" opacity="0.26"/>
    <rect x="786" y="392" width="260" height="20" rx="10" fill="{concept.body_fill}" opacity="0.18"/>
    <rect x="786" y="428" width="214" height="20" rx="10" fill="{concept.body_fill}" opacity="0.12"/>
    """


def _editorial_blueprint(concept: PMTemplateConcept) -> str:
    return f"""
    <rect x="42" y="104" width="1196" height="538" rx="38" fill="#ffffff" opacity="0.96" stroke="{concept.panel_border}" stroke-width="4"/>
    <rect x="70" y="138" width="346" height="470" rx="30" fill="{concept.background_start}" opacity="0.08"/>
    <rect x="442" y="138" width="390" height="470" rx="30" fill="{concept.background_mid}" opacity="0.18"/>
    <rect x="858" y="138" width="332" height="470" rx="30" fill="{concept.background_end}" opacity="0.10"/>
    <rect x="102" y="182" width="244" height="54" rx="18" fill="{concept.highlight_fill}"/>
    <path d="M102 280h230" stroke="{concept.panel_border}" stroke-width="6" stroke-linecap="round"/>
    <path d="M102 320h190" stroke="{concept.panel_border}" stroke-opacity="0.34" stroke-width="6" stroke-linecap="round"/>
    <path d="M102 360h220" stroke="{concept.panel_border}" stroke-opacity="0.22" stroke-width="6" stroke-linecap="round"/>
    <path d="M102 400h160" stroke="{concept.panel_border}" stroke-opacity="0.16" stroke-width="6" stroke-linecap="round"/>
    <rect x="472" y="188" width="310" height="150" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="2"/>
    <rect x="472" y="364" width="310" height="190" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="2"/>
    <rect x="888" y="188" width="252" height="136" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="2"/>
    <rect x="888" y="346" width="252" height="208" rx="24" fill="{concept.card_fill}" stroke="{concept.card_border}" stroke-width="2"/>
    <path d="M510 244h224" stroke="{concept.body_fill}" stroke-opacity="0.24" stroke-width="6" stroke-linecap="round"/>
    <path d="M510 410h224" stroke="{concept.body_fill}" stroke-opacity="0.24" stroke-width="6" stroke-linecap="round"/>
    <circle cx="612" cy="248" r="54" fill="{concept.accent_primary}" opacity="0.18"/>
    <circle cx="612" cy="430" r="74" fill="{concept.accent_secondary}" opacity="0.18"/>
    <rect x="916" y="380" width="160" height="18" rx="9" fill="{concept.body_fill}" opacity="0.28"/>
    <rect x="916" y="418" width="190" height="18" rx="9" fill="{concept.body_fill}" opacity="0.20"/>
    <rect x="916" y="456" width="132" height="18" rx="9" fill="{concept.body_fill}" opacity="0.14"/>
    <rect x="916" y="494" width="168" height="18" rx="9" fill="{concept.body_fill}" opacity="0.10"/>
    """


def verify_pm_template_concept(concept: PMTemplateConcept, topic: str) -> dict[str, object]:
    title_lines, title_font, title_gap, title_start = _fit_title(topic.upper(), concept.layout)
    widest = max((_estimate_text_width(line, title_font) for line in title_lines), default=0)
    title_bottom = title_start + len(title_lines) * title_font + max(0, len(title_lines) - 1) * max(8, title_gap - title_font)
    footer_top = 482
    ok = widest <= 1120 and title_bottom <= footer_top - 18
    return {
        "template_id": concept.template_id,
        "layout": concept.layout,
        "title_lines": title_lines,
        "font_size": title_font,
        "title_bottom": title_bottom,
        "footer_top": footer_top,
        "passes": ok,
        "note": "ok" if ok else "title adjusted to avoid overlap",
    }


def _render_preview_mp4(png_path: Path, output_path: Path, seconds: int) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to render template agent videos.")
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
                f"scale={WIDTH}:{HEIGHT},zoompan=z='min(zoom+0.0002,1.02)':"
                f"d={frames}:s={WIDTH}x{HEIGHT}:fps=30,"
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


def _wrap_text(text: str, width: int, max_lines: int) -> list[str]:
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
