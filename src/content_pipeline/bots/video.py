from __future__ import annotations

import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import Path

import cairosvg

from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


WIDTH = 1280
HEIGHT = 720


@dataclass(frozen=True)
class VideoScene:
    title: str
    body: str
    label: str
    duration: int


def scenes_for_package(package: ContentPackage) -> list[VideoScene]:
    scenes = [
        VideoScene(package.topic, package.video_script.hook, "THE PROBLEM", 4),
    ]
    for index, point in enumerate(package.video_script.points, start=1):
        scenes.append(VideoScene(f"Insight {index}", point, "PRACTICAL DELIVERY TIP", 5))
    scenes.append(
        VideoScene("Continue the conversation", package.video_script.cta, "YOUR TURN", 4)
    )
    return scenes


def render_landscape_preview(
    package: ContentPackage,
    storage: LocalDailyStorage,
) -> str:
    scenes = scenes_for_package(package)
    png_paths: list[Path] = []
    for index, scene in enumerate(scenes, start=1):
        basename = f"video/scenes/scene_{index:02d}"
        svg = scene_svg(scene, index, len(scenes))
        storage.write_bytes(package.date, f"{basename}.svg", svg)
        png_path = storage.daily_path(package.date, f"{basename}.png")
        png_path.write_bytes(
            cairosvg.svg2png(bytestring=svg, output_width=WIDTH, output_height=HEIGHT)
        )
        png_paths.append(png_path)
    output_path = storage.daily_path(package.date, "video/landscape_preview_16x9.mp4")
    subtitle_path = storage.daily_path(package.date, "video/landscape_preview_16x9.srt")
    subtitle_path.write_text(subtitles_for_scenes(scenes), encoding="utf-8")
    _assemble_video(scenes, png_paths, output_path)
    return "video/landscape_preview_16x9.mp4"


def scene_svg(scene: VideoScene, index: int, total: int) -> bytes:
    content = _scene_layout(scene, index, total)
    progress = int((index / total) * 1128)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">
      <path d="M44 0H0V44" fill="none" stroke="#542498" stroke-width="1.4" opacity="0.52"/>
    </pattern>
    <radialGradient id="glow" cx="50%" cy="48%" r="60%">
      <stop offset="0%" stop-color="#572494" stop-opacity="0.56"/>
      <stop offset="100%" stop-color="#110526" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="spark" x1="0%" y1="50%" x2="100%" y2="50%">
      <stop stop-color="#ffb84a" stop-opacity="0"/>
      <stop offset="55%" stop-color="#ffb84a" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="#e561aa" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#110526"/>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#grid)"/>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#glow)"/>
  <path d="M0 605 C240 550 416 670 680 600 S1060 566 1280 620" fill="none" stroke="url(#spark)" stroke-width="3" opacity="0.36"/>
  <style>
    .title {{ font-family: Arial, Helvetica, sans-serif; font-weight: 700; fill: #fbf9ff; }}
    .body {{ font-family: Arial, Helvetica, sans-serif; font-weight: 400; fill: #ddd3ed; }}
    .caption {{ font-family: Arial, Helvetica, sans-serif; font-weight: 700; fill: #fff3e5; }}
    .small {{ font-family: Arial, Helvetica, sans-serif; font-weight: 500; fill: #beacd9; }}
  </style>
  {content}
  <rect x="76" y="650" width="1128" height="5" rx="2.5" fill="#35145f"/>
  <rect x="76" y="650" width="{progress}" height="5" rx="2.5" fill="#ffae46"/>
  <text x="76" y="687" class="small" font-size="15" letter-spacing="2">PROJECT DELIVERY INSIGHTS</text>
  <text x="1204" y="687" text-anchor="end" class="small" font-size="15">{index:02d} / {total:02d}</text>
</svg>"""
    return svg.encode("utf-8")


def _assemble_video(
    scenes: list[VideoScene],
    png_paths: list[Path],
    output_path: Path,
) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required for video previews. Install it with: brew install ffmpeg")
    clips_dir = output_path.parent / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    concat_path = output_path.parent / "landscape_scenes.txt"
    clip_paths: list[Path] = []
    for index, (scene, path) in enumerate(zip(scenes, png_paths, strict=True), start=1):
        clip_path = clips_dir / f"scene_{index:02d}.mp4"
        frames = scene.duration * 30
        fade_out = max(0, scene.duration - 0.35)
        subprocess.run(
            [
                executable,
                "-y",
                "-loop",
                "1",
                "-i",
                str(path),
                "-vf",
                (
                    f"scale=1280:720,zoompan=z='min(zoom+0.00025,1.025)':"
                    f"d={frames}:s=1280x720:fps=30,"
                    f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out}:d=0.35,"
                    "format=yuv420p"
                ),
                "-t",
                str(scene.duration),
                "-an",
                "-c:v",
                "libx264",
                "-movflags",
                "+faststart",
                str(clip_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        clip_paths.append(clip_path)
    entries = [f"file '{path}'" for path in clip_paths]
    concat_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def subtitles_for_scenes(scenes: list[VideoScene]) -> str:
    subtitles: list[str] = []
    start = 0
    for index, scene in enumerate(scenes, start=1):
        end = start + scene.duration
        subtitles.extend(
            [
                str(index),
                f"{_timestamp(start)} --> {_timestamp(end)}",
                scene.body,
                "",
            ]
        )
        start = end
    return "\n".join(subtitles)


def _timestamp(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, remaining = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining:02d},000"


def _scene_layout(scene: VideoScene, index: int, total: int) -> str:
    if index == 1:
        title = _lines(_wrap(scene.title, width=29, maximum=3), 84, 190, 55, 64, "title")
        body = _lines(_wrap(scene.body, width=42, maximum=3), 84, 422, 27, 40, "body")
        return f"""{_label(scene.label, 84, 94)}
  {title}
  {body}
  {_opening_visual()}"""
    if index == total:
        title = _lines(_wrap(scene.title, width=40, maximum=2), 640, 206, 44, 54, "title", anchor="middle")
        body = _lines(_wrap(scene.body, width=54, maximum=3), 640, 335, 30, 44, "body", anchor="middle")
        return f"""{_label(scene.label, 640, 105, centered=True)}
  {title}
  {body}
  {_closing_visual()}"""
    if index % 2 == 0:
        title = _lines(_wrap(scene.title, width=30, maximum=2), 82, 178, 46, 55, "title")
        body = _lines(_wrap(scene.body, width=39, maximum=4), 82, 308, 28, 41, "body")
        return f"""{_label(scene.label, 82, 92)}
  {title}
  {body}
  {_process_visual()}"""
    title = _lines(_wrap(scene.title, width=48, maximum=2), 640, 170, 45, 54, "title", anchor="middle")
    body = _lines(_wrap(scene.body, width=65, maximum=3), 640, 317, 28, 42, "body", anchor="middle")
    return f"""{_label(scene.label, 640, 88, centered=True)}
  {title}
  {body}
  {_comparison_visual()}"""


def _label(value: str, x: int, y: int, centered: bool = False) -> str:
    width = max(188, len(value) * 10 + 38)
    left = x - (width / 2) if centered else x
    text_x = x if centered else left + (width / 2)
    return (
        f'<rect x="{left}" y="{y}" width="{width}" height="38" rx="6" '
        'fill="#2a104b" stroke="#ffae46" stroke-width="2"/>'
        f'<text x="{text_x}" y="{y + 26}" text-anchor="middle" class="caption" '
        f'font-size="16" letter-spacing="1">{escape(value)}</text>'
    )


def _opening_visual() -> str:
    return """<circle cx="1025" cy="303" r="146" fill="#240c46" stroke="#5f35a5" stroke-width="2"/>
  <circle cx="1025" cy="303" r="116" fill="none" stroke="#844dc2" stroke-width="3" opacity="0.5"/>
  <rect x="910" y="228" width="226" height="128" rx="12" fill="#f4f1fc"/>
  <rect x="932" y="249" width="88" height="10" rx="5" fill="#d5cbea"/>
  <rect x="932" y="272" width="144" height="10" rx="5" fill="#d5cbea"/>
  <path d="M940 327 L979 299 L1017 310 L1060 270 L1102 290" fill="none" stroke="#ffae46" stroke-width="6"/>
  <circle cx="940" cy="327" r="6" fill="#ffae46"/>
  <circle cx="1060" cy="270" r="6" fill="#ffae46"/>
  <circle cx="878" cy="387" r="39" fill="#6d35ad"/>
  <path d="M867 387h22M878 376v22" stroke="#fff" stroke-width="5" stroke-linecap="round"/>"""


def _process_visual() -> str:
    return """<rect x="728" y="182" width="454" height="333" rx="22" fill="#180933" stroke="#562991" stroke-width="2"/>
  <circle cx="820" cy="284" r="48" fill="#382262"/>
  <path d="M798 285h44M820 263v44" stroke="#ffae46" stroke-width="7" stroke-linecap="round"/>
  <circle cx="974" cy="284" r="48" fill="#382262"/>
  <path d="M951 286l15 15 32-37" fill="none" stroke="#50db9b" stroke-width="8" stroke-linecap="round"/>
  <circle cx="1128" cy="284" r="48" fill="#382262"/>
  <path d="M1108 300h40v-39h-40z M1118 250v22 M1138 250v22" fill="none" stroke="#7bd7ff" stroke-width="6"/>
  <path d="M870 284h54 M1024 284h54" stroke="#ffae46" stroke-width="3" stroke-dasharray="8 8"/>
  <text x="820" y="365" text-anchor="middle" class="small" font-size="15">DEFINE</text>
  <text x="974" y="365" text-anchor="middle" class="small" font-size="15">VERIFY</text>
  <text x="1128" y="365" text-anchor="middle" class="small" font-size="15">DELIVER</text>
  <rect x="786" y="421" width="340" height="37" rx="18" fill="#ffae46"/>
  <text x="956" y="446" text-anchor="middle" font-family="Arial" font-size="16" font-weight="700" fill="#28113e">A PRACTICAL CHECKLIST</text>"""


def _comparison_visual() -> str:
    return """<rect x="122" y="457" width="1010" height="113" rx="17" fill="#190a35" stroke="#54318b" stroke-width="2"/>
  <rect x="158" y="485" width="252" height="57" rx="10" fill="#2b1550"/>
  <circle cx="187" cy="513" r="14" fill="#ffae46"/>
  <path d="M181 513l5 5 10-12" fill="none" stroke="#241039" stroke-width="3"/>
  <text x="214" y="520" class="small" font-size="17">CLARITY</text>
  <path d="M435 513h42" stroke="#ffae46" stroke-width="3"/>
  <path d="M469 505l12 8-12 8" fill="#ffae46"/>
  <rect x="506" y="485" width="252" height="57" rx="10" fill="#2b1550"/>
  <circle cx="535" cy="513" r="14" fill="#50db9b"/>
  <path d="M529 513l5 5 10-12" fill="none" stroke="#241039" stroke-width="3"/>
  <text x="562" y="520" class="small" font-size="17">QUALITY</text>
  <path d="M783 513h42" stroke="#ffae46" stroke-width="3"/>
  <path d="M817 505l12 8-12 8" fill="#ffae46"/>
  <rect x="854" y="485" width="242" height="57" rx="10" fill="#2b1550"/>
  <circle cx="883" cy="513" r="14" fill="#7bd7ff"/>
  <text x="910" y="520" class="small" font-size="17">OUTCOME</text>"""


def _closing_visual() -> str:
    return """<rect x="406" y="495" width="468" height="55" rx="27" fill="#ffae46"/>
  <text x="640" y="530" text-anchor="middle" font-family="Arial" font-size="19" font-weight="700" fill="#28113e">SHARE YOUR EXPERIENCE</text>
  <circle cx="352" cy="523" r="29" fill="#312050" stroke="#7048a8" stroke-width="2"/>
  <path d="M339 522l9 9 18-21" fill="none" stroke="#50db9b" stroke-width="5"/>
  <circle cx="928" cy="523" r="29" fill="#312050" stroke="#7048a8" stroke-width="2"/>
  <path d="M915 523h25 M928 511v25" stroke="#7bd7ff" stroke-width="5" stroke-linecap="round"/>"""


def _wrap(value: str, width: int, maximum: int) -> list[str]:
    lines = textwrap.wrap(" ".join(value.split()), width=width) or [""]
    if len(lines) <= maximum:
        return lines
    clipped = lines[:maximum]
    clipped[-1] = clipped[-1].rstrip(".") + "..."
    return clipped


def _lines(
    values: list[str],
    x: int,
    y: int,
    font_size: int,
    line_height: int,
    class_name: str,
    anchor: str = "start",
) -> str:
    return "".join(
        f'<text x="{x}" y="{y + offset * line_height}" text-anchor="{anchor}" class="{class_name}" '
        f'font-size="{font_size}">{escape(line)}</text>'
        for offset, line in enumerate(values)
    )
