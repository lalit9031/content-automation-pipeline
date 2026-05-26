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
    _assemble_video(scenes, png_paths, output_path)
    return "video/landscape_preview_16x9.mp4"


def scene_svg(scene: VideoScene, index: int, total: int) -> bytes:
    title = _wrap(scene.title, width=36, maximum=2)
    body = _wrap(scene.body, width=56, maximum=4)
    title_svg = _lines(title, 76, 196, 52, 61, "title")
    body_svg = _lines(body, 76, 353, 30, 45, "body")
    progress = int((index / total) * 1128)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#f7fafc"/>
  <rect x="0" y="0" width="{WIDTH}" height="16" fill="#0b2545"/>
  <rect x="76" y="82" width="222" height="38" rx="19" fill="#e5effb"/>
  <text x="187" y="108" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#0a66c2">{escape(scene.label)}</text>
  <style>
    .title {{ font-family: Arial, Helvetica, sans-serif; font-weight: 700; fill: #0b2545; }}
    .body {{ font-family: Arial, Helvetica, sans-serif; font-weight: 500; fill: #3e536b; }}
  </style>
  {title_svg}
  {body_svg}
  <rect x="76" y="630" width="1128" height="8" rx="4" fill="#d9e4f1"/>
  <rect x="76" y="630" width="{progress}" height="8" rx="4" fill="#0a66c2"/>
  <text x="76" y="676" font-family="Arial, Helvetica, sans-serif" font-size="17" fill="#657991">PROJECT DELIVERY INSIGHTS</text>
  <text x="1204" y="676" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="17" fill="#657991">{index:02d} / {total:02d}</text>
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
    concat_path = output_path.parent / "landscape_scenes.txt"
    entries: list[str] = []
    for scene, path in zip(scenes, png_paths, strict=True):
        entries.extend([f"file '{path}'", f"duration {scene.duration}"])
    entries.append(f"file '{png_paths[-1]}'")
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
            "-vf",
            "scale=1280:720,format=yuv420p",
            "-r",
            "30",
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
) -> str:
    return "".join(
        f'<text x="{x}" y="{y + offset * line_height}" class="{class_name}" '
        f'font-size="{font_size}">{escape(line)}</text>'
        for offset, line in enumerate(values)
    )
