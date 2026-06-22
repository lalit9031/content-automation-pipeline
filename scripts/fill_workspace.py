#!/usr/bin/env python3
"""Fill missing workspace assets and assemble the final video.

Generates gradient placeholder images and silent audio for any missing scenes,
then assembles scene clips and the final video with crossfade transitions.
No API calls are made — everything uses local resources (FFmpeg).

Usage:
    python scripts/fill_workspace.py <workspace_dir>
"""

from __future__ import annotations

import json
import logging
import struct
import subprocess
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from content_pipeline.bots.science_video_agent import (
    assemble_final_video,
    assemble_scene_clips,
    _require_ffmpeg,
)
from content_pipeline.models import ScienceStoryScript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

YOUTUBE_WIDTH = 1920
YOUTUBE_HEIGHT = 1080


def fill_placeholders(workspace_dir: Path, script: ScienceStoryScript) -> None:
    """Fill all missing images with gradient placeholders."""
    image_dir = workspace_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    filled = 0

    for i, scene in enumerate(script.scenes):
        img_path = image_dir / f"scene_{i + 1:04d}.png"

        # Skip if real image exists (>10KB = likely real, not placeholder)
        if img_path.exists() and img_path.stat().st_size > 10000:
            continue

        # Create gradient placeholder with scene label
        _create_labeled_placeholder(img_path, scene, i)
        filled += 1
        if filled % 10 == 0:
            log.info("  Placeholder images: %d/%d done", filled, len(script.scenes))

    log.info("Created %d placeholder images", filled)


def fill_silent_audio(workspace_dir: Path, script: ScienceStoryScript) -> None:
    """Fill all missing audio with silent MP3."""
    executable = _require_ffmpeg()
    audio_dir = workspace_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    filled = 0

    for i, scene in enumerate(script.scenes):
        audio_path = audio_dir / f"scene_{i + 1:04d}.mp3"

        if audio_path.exists() and audio_path.stat().st_size > 1000:
            continue

        duration = scene.duration_seconds
        try:
            subprocess.run(
                [executable, "-y", "-f", "lavfi", "-i",
                 f"anullsrc=r=44100:cl=mono", "-t", str(duration),
                 "-c:a", "libmp3lame", "-b:a", "128k", str(audio_path)],
                check=True, capture_output=True, text=True,
            )
            filled += 1
            if filled % 10 == 0:
                log.info("  Silent audio: %d/%d done", filled, len(script.scenes))
        except subprocess.CalledProcessError as exc:
            log.error("  FFmpeg failed for scene %d: %s", i + 1, exc.stderr[-200:])

    log.info("Created %d silent audio files", filled)


def _create_labeled_placeholder(path: Path, scene: object, index: int) -> None:
    """Create a gradient PNG with a scene label inscribed."""
    scene_index = index + 1

    # Dark gradient background
    raw = b""
    for y in range(YOUTUBE_HEIGHT):
        raw += b"\x00"
        for x in range(YOUTUBE_WIDTH):
            r = int(15 + (y / YOUTUBE_HEIGHT) * 30)
            g = int(8 + (y / YOUTUBE_HEIGHT) * 20)
            b_val = int(25 + (y / YOUTUBE_HEIGHT) * 45)
            raw += struct.pack("BBB", r, g, b_val)

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", YOUTUBE_WIDTH, YOUTUBE_HEIGHT, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sig + ihdr + idat + iend)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/fill_workspace.py <workspace_dir>", file=sys.stderr)
        sys.exit(1)

    workspace_dir = Path(sys.argv[1]).resolve()
    script_path = workspace_dir / "script.json"

    if not script_path.exists():
        log.error("No script.json found in %s", workspace_dir)
        sys.exit(1)

    script = ScienceStoryScript.from_dict(
        json.loads(script_path.read_text(encoding="utf-8"))
    )

    log.info("Workspace: %s (%d scenes, %.1f min)",
             workspace_dir, len(script.scenes), script.duration_minutes)

    # Step 1: Fill placeholder images
    log.info("Step 1/4: Filling placeholder images...")
    fill_placeholders(workspace_dir, script)

    # Step 2: Fill silent audio
    log.info("Step 2/4: Filling silent audio...")
    fill_silent_audio(workspace_dir, script)

    # Step 3: Assemble scene clips
    log.info("Step 3/4: Assembling scene clips (this will take a while)...")
    clip_paths = assemble_scene_clips(workspace_dir, script)
    log.info("Assembled %d scene clips", len(clip_paths))

    # Step 4: Assemble final video with crossfade
    log.info("Step 4/4: Assembling final video with crossfade...")
    final_path = assemble_final_video(workspace_dir, script, add_crossfade=True)
    log.info("Final video: %s", final_path)

    # Summary
    log.info("=" * 50)
    log.info("Workspace complete!")
    log.info("  Storyboard: %s", workspace_dir / "ui" / "storyboard.html")
    log.info("  Final video: %s", final_path)
    log.info("  Subtitles: %s", workspace_dir / "subtitles" / "subtitles.srt")
    log.info("  Duration: %.1f minutes", script.duration_minutes)
    log.info("=" * 50)


if __name__ == "__main__":
    main()
