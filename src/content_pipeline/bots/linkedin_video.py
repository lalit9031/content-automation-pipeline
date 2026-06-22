from __future__ import annotations

import textwrap
from html import escape
from pathlib import Path

from content_pipeline.models import VideoEpisode
from content_pipeline.storage import LocalDailyStorage


WIDTH = 1080
HEIGHT = 1350


def render_video_linkedin_post(
    episode: VideoEpisode,
    storage: LocalDailyStorage,
    *,
    reference_label: str,
    reference_url: str = "",
) -> Path:
    svg = video_linkedin_svg(episode, reference_label=reference_label, reference_url=reference_url)
    svg_path = storage.write_bytes(episode.episode_id[:10], "publish/linkedin_video_post.svg", svg)
    try:
        import cairosvg
    except ImportError:  # pragma: no cover - optional dependency
        return svg_path
    png = cairosvg.svg2png(bytestring=svg, output_width=WIDTH, output_height=HEIGHT)
    filename = "publish/linkedin_video_post.png"
    return storage.write_bytes(episode.episode_id[:10], filename, png)


def render_linkedin_post_from_video_details(
    *,
    title: str,
    description: str,
    youtube_url: str,
    hashtags: list[str],
    output_path: Path,
) -> Path:
    svg = video_details_linkedin_svg(
        title=title,
        description=description,
        youtube_url=youtube_url,
        hashtags=hashtags,
    )
    svg_path = output_path.with_suffix(".svg")
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_bytes(svg)
    try:
        import cairosvg
    except ImportError:  # pragma: no cover - optional dependency
        return svg_path
    png = cairosvg.svg2png(bytestring=svg, output_width=WIDTH, output_height=HEIGHT)
    png_path = output_path.with_suffix(".png")
    png_path.write_bytes(png)
    return png_path


def video_linkedin_svg(
    episode: VideoEpisode,
    *,
    reference_label: str,
    reference_url: str = "",
) -> bytes:
    title = _text_lines(episode.youtube_title, width=30, maximum=2)
    subtitle = _text_lines(episode.description or episode.youtube_description, width=54, maximum=2)
    left_points = _clip_points(episode, start=0, stop=3)
    right_points = _clip_points(episode, start=3, stop=6)
    reference = _reference_text(reference_label, reference_url)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#07111f"/>
      <stop offset="55%" stop-color="#102b4f"/>
      <stop offset="100%" stop-color="#173f63"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0%" stop-color="#ffb347"/>
      <stop offset="100%" stop-color="#ff7a18"/>
    </linearGradient>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <circle cx="890" cy="120" r="210" fill="#2b5b8f" opacity="0.18"/>
  <circle cx="110" cy="1210" r="260" fill="#ffb347" opacity="0.08"/>
  <rect x="46" y="44" width="988" height="1260" rx="34" fill="#f8fbff" opacity="0.98"/>
  <rect x="46" y="44" width="988" height="18" rx="9" fill="url(#accent)"/>
  <style>
    text {{ font-family: Arial, Helvetica, sans-serif; }}
    .eyebrow {{ fill: #ff7a18; font-weight: 800; letter-spacing: 1.8px; }}
    .title {{ fill: #0b1f36; font-weight: 800; }}
    .subtitle {{ fill: #44566d; font-weight: 500; }}
    .section {{ fill: #0b1f36; font-weight: 800; letter-spacing: 0.6px; }}
    .body {{ fill: #24364a; font-weight: 500; }}
    .chip {{ fill: #0b1f36; font-weight: 700; }}
    .small {{ fill: #5a6b7c; font-weight: 500; }}
    .label {{ fill: #ffffff; font-weight: 700; letter-spacing: 1px; }}
    .reference {{ fill: #0b1f36; font-weight: 700; }}
  </style>
  <text x="92" y="126" class="eyebrow" font-size="18">{escape("YOUTUBE POST REFERENCE")}</text>
  {_centered_lines(title, 540, 186, 50, 55, "title")}
  {_centered_lines(subtitle, 540, 304, 26, 35, "subtitle")}
  <rect x="92" y="348" width="896" height="92" rx="22" fill="#102b4f"/>
  <rect x="92" y="348" width="240" height="92" rx="22" fill="#ff7a18"/>
  <text x="212" y="385" class="label" font-size="22" text-anchor="middle">{escape(reference_label.upper())}</text>
  <text x="212" y="417" class="label" font-size="18" text-anchor="middle">{escape(f"{len(episode.clips)} SCENES")}</text>
  <text x="374" y="405" class="small" font-size="22">{escape(f"Format: {episode.aspect.upper()} | Video title:")}</text>
  <text x="374" y="432" class="label" font-size="19">{escape(_shorten(episode.youtube_title, 62))}</text>
  <rect x="92" y="472" width="420" height="386" rx="24" fill="#eaf2ff"/>
  <rect x="566" y="472" width="420" height="386" rx="24" fill="#eef9f2"/>
  <text x="120" y="516" class="section" font-size="24">{escape("WHAT THIS VIDEO COVERS")}</text>
  <text x="594" y="516" class="section" font-size="24">{escape("WHY IT IS WORTH WATCHING")}</text>
  {_bullet_block(left_points, 120, 564, 32, 41, "body", accent="#0a66c2")}
  {_bullet_block(right_points, 594, 564, 32, 41, "body", accent="#27834a")}
  <rect x="92" y="888" width="896" height="164" rx="24" fill="#fff1e2"/>
  <rect x="92" y="888" width="14" height="164" rx="7" fill="#ff7a18"/>
  <text x="124" y="936" class="section" font-size="24">{escape("REFERENCE")}</text>
  <text x="124" y="978" class="reference" font-size="24">{escape(reference)}</text>
  <text x="124" y="1016" class="small" font-size="19">{escape("Use this card as the LinkedIn companion post for the video.")}</text>
  <rect x="92" y="1078" width="896" height="164" rx="24" fill="#102b4f"/>
  <text x="124" y="1126" class="label" font-size="22">{escape("POST ANGLE")}</text>
  <text x="124" y="1162" class="label" font-size="20">{escape(_shorten(episode.youtube_description.replace("\n", " "), 90))}</text>
  <text x="124" y="1208" class="small" font-size="18">{escape("Save the video, share a note, or comment with your experience.")}</text>
  {_footer_tags(episode.hashtags, 744, 1126)}
  <text x="540" y="1286" class="chip" font-size="17" text-anchor="middle">{escape("LINKEDIN VIDEO COMPANION")}</text>
</svg>"""
    return svg.encode("utf-8")


def video_details_linkedin_svg(
    *,
    title: str,
    description: str,
    youtube_url: str,
    hashtags: list[str],
) -> bytes:
    title_lines = _text_lines(title, width=30, maximum=2)
    subtitle = _text_lines(description, width=54, maximum=2)
    reference = "YouTube video link"
    title_svg = _centered_lines(title_lines, 540, 186, 50, 55, "title")
    subtitle_svg = _centered_lines(subtitle, 540, 304, 26, 35, "subtitle")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#07111f"/>
      <stop offset="55%" stop-color="#102b4f"/>
      <stop offset="100%" stop-color="#173f63"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0%" stop-color="#ffb347"/>
      <stop offset="100%" stop-color="#ff7a18"/>
    </linearGradient>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <circle cx="890" cy="120" r="210" fill="#2b5b8f" opacity="0.18"/>
  <circle cx="110" cy="1210" r="260" fill="#ffb347" opacity="0.08"/>
  <rect x="46" y="44" width="988" height="1260" rx="34" fill="#f8fbff" opacity="0.98"/>
  <rect x="46" y="44" width="988" height="18" rx="9" fill="url(#accent)"/>
  <style>
    text {{ font-family: Arial, Helvetica, sans-serif; }}
    .eyebrow {{ fill: #ff7a18; font-weight: 800; letter-spacing: 1.8px; }}
    .title {{ fill: #0b1f36; font-weight: 800; }}
    .subtitle {{ fill: #44566d; font-weight: 500; }}
    .section {{ fill: #0b1f36; font-weight: 800; letter-spacing: 0.6px; }}
    .body {{ fill: #24364a; font-weight: 500; }}
    .chip {{ fill: #0b1f36; font-weight: 700; }}
    .small {{ fill: #5a6b7c; font-weight: 500; }}
    .label {{ fill: #ffffff; font-weight: 700; letter-spacing: 1px; }}
    .reference {{ fill: #0b1f36; font-weight: 700; }}
  </style>
  <text x="92" y="126" class="eyebrow" font-size="18">{escape("YOUTUBE VIDEO READY")}</text>
  {title_svg}
  {subtitle_svg}
  <rect x="92" y="348" width="896" height="92" rx="22" fill="#102b4f"/>
  <rect x="92" y="348" width="240" height="92" rx="22" fill="#ff7a18"/>
  <text x="212" y="385" class="label" font-size="22" text-anchor="middle">{escape(reference.upper())}</text>
  <text x="212" y="417" class="label" font-size="18" text-anchor="middle">PUBLISHED LINK</text>
  <text x="374" y="405" class="small" font-size="22">{escape("Final YouTube URL:")}</text>
  <text x="374" y="432" class="label" font-size="19">{escape(youtube_url)}</text>
  <rect x="92" y="472" width="420" height="386" rx="24" fill="#eaf2ff"/>
  <rect x="566" y="472" width="420" height="386" rx="24" fill="#eef9f2"/>
  <text x="120" y="516" class="section" font-size="24">{escape("WHAT THIS VIDEO COVERS")}</text>
  <text x="594" y="516" class="section" font-size="24">{escape("WHY IT IS WORTH WATCHING")}</text>
  {_bullet_block(_lines_from_description(description), 120, 564, 32, 41, "body", accent="#0a66c2")}
  {_bullet_block(_detail_points(title, description), 594, 564, 32, 41, "body", accent="#27834a")}
  <rect x="92" y="888" width="896" height="164" rx="24" fill="#fff1e2"/>
  <rect x="92" y="888" width="14" height="164" rx="7" fill="#ff7a18"/>
  <text x="124" y="936" class="section" font-size="24">{escape("VIDEO LINK")}</text>
  <text x="124" y="978" class="reference" font-size="24">{escape(youtube_url)}</text>
  <text x="124" y="1016" class="small" font-size="19">{escape("Use this LinkedIn image post together with the published video URL.")}</text>
  <rect x="92" y="1078" width="896" height="164" rx="24" fill="#102b4f"/>
  <text x="124" y="1126" class="label" font-size="22">{escape("POST ANGLE")}</text>
  <text x="124" y="1162" class="label" font-size="20">{escape(_shorten(description.replace("\n", " "), 90))}</text>
  <text x="124" y="1208" class="small" font-size="18">{escape("Save, comment, and share if it helps your team.")}</text>
  {_footer_tags(hashtags, 744, 1126)}
  <text x="540" y="1286" class="chip" font-size="17" text-anchor="middle">{escape("LINKEDIN VIDEO COMPANION")}</text>
</svg>""".encode("utf-8")


def _clip_points(episode: VideoEpisode, start: int, stop: int) -> list[str]:
    clips = episode.clips[start:stop]
    points = []
    for clip in clips:
        text = clip.on_screen_text or clip.title or clip.narration
        if text:
            points.append(text)
    if not points:
        points = [episode.title, episode.youtube_title]
    return points[:3]


def _reference_text(reference_label: str, reference_url: str) -> str:
    if reference_url:
        return f"{reference_label}: {reference_url}"
    return reference_label


def _bullet_block(
    points: list[str],
    x: int,
    y: int,
    text_x: int,
    line_height: int,
    class_name: str,
    accent: str,
) -> str:
    rows: list[str] = []
    cursor = y
    for point in points[:3]:
        lines = _text_lines(point, width=31, maximum=2)
        rows.append(f'<circle cx="{x + 8}" cy="{cursor - 10}" r="8" fill="{accent}"/>')
        rows.append(_left_lines(lines, text_x, cursor, 21, line_height, class_name))
        cursor += max(72, len(lines) * line_height + 26)
    return "".join(rows)


def _lines_from_description(description: str) -> list[str]:
    lines = [line.strip("- ").strip() for line in description.splitlines() if line.strip()]
    selected = [line for line in lines if len(line) < 70][:3]
    if selected:
        return selected
    return _text_lines(description, width=31, maximum=3)


def _detail_points(title: str, description: str) -> list[str]:
    return [
        f"Topic: {_shorten(title, 32)}",
        "Useful for project managers and teams",
        "Shared as an image post with the video link",
    ]


def _footer_tags(tags: list[str], x: int, y: int) -> str:
    selected = [tag for tag in tags[:4] if tag]
    if not selected:
        selected = ["#ProjectManagement", "#Agile"]
    rows: list[str] = []
    cursor_x = x
    for tag in selected:
        width = max(86, min(168, len(tag) * 11))
        rows.append(f'<rect x="{cursor_x}" y="{y}" width="{width}" height="34" rx="17" fill="#dfe8f4"/>')
        rows.append(f'<text x="{cursor_x + width / 2:.1f}" y="{y + 23}" class="chip" font-size="15" text-anchor="middle">{escape(tag)}</text>')
        cursor_x += width + 12
    return "".join(rows)


def _text_lines(value: str, width: int, maximum: int) -> list[str]:
    lines = textwrap.wrap(" ".join(value.split()), width=width) or [""]
    if len(lines) <= maximum:
        return lines
    visible = lines[:maximum]
    visible[-1] = _shorten(visible[-1] + "...", width)
    return visible


def _shorten(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: max(0, limit - 3)].rstrip() + "..."


def _centered_lines(
    lines: list[str],
    x: int,
    y: int,
    size: int,
    line_height: int,
    class_name: str,
) -> str:
    return "".join(
        f'<text x="{x}" y="{y + index * line_height}" class="{class_name}" '
        f'text-anchor="middle" font-size="{size}">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def _left_lines(
    lines: list[str],
    x: int,
    y: int,
    size: int,
    line_height: int,
    class_name: str,
) -> str:
    return "".join(
        f'<text x="{x}" y="{y + index * line_height}" class="{class_name}" '
        f'font-size="{size}">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )
