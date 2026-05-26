from __future__ import annotations

import textwrap
from html import escape

from content_pipeline.models import ContentPackage, InfographicPanel
from content_pipeline.storage import LocalDailyStorage


WIDTH = 1080
HEIGHT = 1350


def render_linkedin_infographic(
    package: ContentPackage,
    storage: LocalDailyStorage,
) -> str:
    svg = infographic_svg(package)
    storage.write_bytes(package.date, "images/linkedin_infographic.svg", svg)
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
    png = cairosvg.svg2png(bytestring=svg, output_width=WIDTH, output_height=HEIGHT)
    filename = "images/linkedin_infographic.png"
    storage.write_bytes(package.date, filename, png)
    return filename


def infographic_svg(package: ContentPackage) -> bytes:
    data = package.linkedin_infographic
    headline = _text_lines(data.headline, width=38, maximum=2)
    subtitle = _text_lines(data.subtitle, width=62, maximum=2)
    headline_svg = _centered_lines(headline, 540, 82, 50, 55, "headline")
    subtitle_y = 82 + len(headline) * 55 + 11
    subtitle_svg = _centered_lines(subtitle, 540, subtitle_y, 28, 36, "subtitle")
    panels_y = 260 if len(headline) == 1 else 278
    left = _panel(data.left_panel, 56, panels_y, "#e7f0fa", "#0a66c2")
    right = _panel(data.right_panel, 554, panels_y, "#e9f6ee", "#27834a")
    takeaway_y = panels_y + 378
    workflow_y = takeaway_y + 225
    footer_y = workflow_y + 166
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#f7fafc"/>
  <rect x="0" y="0" width="{WIDTH}" height="16" fill="#0b2545"/>
  <style>
    text {{ font-family: Arial, Helvetica, sans-serif; }}
    .headline {{ fill: #0b2545; font-weight: 700; }}
    .subtitle {{ fill: #43566d; font-weight: 500; }}
    .panel-title {{ fill: #ffffff; font-weight: 700; }}
    .body {{ fill: #172b4d; font-weight: 500; }}
    .take-title {{ fill: #8a4300; font-weight: 700; }}
    .take-body {{ fill: #3b2a14; font-weight: 500; }}
    .step {{ fill: #0b2545; font-weight: 700; }}
    .footer {{ fill: #ffffff; font-weight: 700; }}
    .brand {{ fill: #708090; font-weight: 500; letter-spacing: 1px; }}
  </style>
  {headline_svg}
  {subtitle_svg}
  {left}
  {right}
  {_takeaway(data.takeaway_title, data.takeaway_points, takeaway_y)}
  {_workflow(data.workflow, workflow_y)}
  {_footer(data.discussion_prompt, footer_y)}
  <text x="540" y="1320" class="brand" text-anchor="middle" font-size="17">PROJECT DELIVERY INSIGHTS</text>
</svg>"""
    return svg.encode("utf-8")


def _panel(
    panel: InfographicPanel,
    x: int,
    y: int,
    background: str,
    accent: str,
) -> str:
    rows: list[str] = []
    cursor = y + 104
    for point in panel.points[:3]:
        lines = _text_lines(point, width=34, maximum=2)
        rows.append(f'<circle cx="{x + 30}" cy="{cursor - 8}" r="8" fill="{accent}"/>')
        rows.append(_left_lines(lines, x + 53, cursor, 21, 28, "body"))
        cursor += max(70, len(lines) * 28 + 25)
    return f"""
  <rect x="{x}" y="{y}" width="470" height="348" rx="20" fill="{background}"/>
  <rect x="{x}" y="{y}" width="470" height="65" rx="20" fill="{accent}"/>
  <rect x="{x}" y="{y + 44}" width="470" height="21" fill="{accent}"/>
  <text x="{x + 27}" y="{y + 42}" class="panel-title" font-size="29">{escape(panel.title)}</text>
  {''.join(rows)}"""


def _takeaway(title: str, points: list[str], y: int) -> str:
    rows: list[str] = []
    cursor = y + 90
    for point in points[:2]:
        lines = _text_lines(point, width=72, maximum=1)
        rows.append(
            f'<circle cx="103" cy="{cursor - 8}" r="8" fill="#f28b20"/>'
            f'{_left_lines(lines, 128, cursor, 22, 29, "take-body")}'
        )
        cursor += 42
    return f"""
  <rect x="56" y="{y}" width="968" height="188" rx="22" fill="#fff0de"/>
  <rect x="56" y="{y}" width="14" height="188" rx="7" fill="#f28b20"/>
  {_left_lines(_text_lines(title, width=58, maximum=1), 92, y + 49, 29, 34, "take-title")}
  {''.join(rows)}"""


def _workflow(steps: list[str], y: int) -> str:
    selected = steps[:5]
    gap = 18
    node_width = int((968 - gap * (len(selected) - 1)) / len(selected))
    nodes: list[str] = []
    for index, step in enumerate(selected):
        x = 56 + index * (node_width + gap)
        fill = "#dbeafe" if index < len(selected) - 1 else "#d9f2e2"
        lines = _text_lines(step, width=15, maximum=2)
        label_y = y + 76 if len(lines) == 1 else y + 66
        nodes.append(
            f'<rect x="{x}" y="{y + 42}" width="{node_width}" height="78" rx="14" fill="{fill}"/>'
            f'{_centered_lines(lines, int(x + node_width / 2), label_y, 19, 24, "step")}'
        )
    return f"""
  <text x="56" y="{y + 22}" class="subtitle" font-size="21">DELIVERY WORKFLOW</text>
  {''.join(nodes)}"""


def _footer(prompt: str, y: int) -> str:
    lines = _text_lines(prompt, width=66, maximum=2)
    text_y = y + 55 if len(lines) == 1 else y + 42
    return f"""
  <rect x="56" y="{y}" width="968" height="112" rx="20" fill="#0b2545"/>
  {_centered_lines(lines, 540, text_y, 27, 34, "footer")}"""


def _text_lines(value: str, width: int, maximum: int) -> list[str]:
    lines = textwrap.wrap(" ".join(value.split()), width=width) or [""]
    if len(lines) <= maximum:
        return lines
    visible = lines[:maximum]
    visible[-1] = _truncate(visible[-1] + "...", width)
    return visible


def _truncate(value: str, width: int) -> str:
    return value if len(value) <= width else value[: max(0, width - 3)].rstrip() + "..."


def _centered_lines(
    lines: list[str], x: int, y: int, size: int, line_height: int, class_name: str
) -> str:
    return "".join(
        f'<text x="{x}" y="{y + index * line_height}" class="{class_name}" '
        f'text-anchor="middle" font-size="{size}">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def _left_lines(
    lines: list[str], x: int, y: int, size: int, line_height: int, class_name: str
) -> str:
    return "".join(
        f'<text x="{x}" y="{y + index * line_height}" class="{class_name}" '
        f'font-size="{size}">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )
