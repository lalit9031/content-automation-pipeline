#!/usr/bin/env python3
"""Fast workspace filler: copies placeholder images and generates silent audio.

Usage:
    python scripts/prepare_workspace.py <workspace_dir>
    python scripts/prepare_workspace.py <workspace_dir> --clips    (also assemble clips)
    python scripts/prepare_workspace.py <workspace_dir> --all     (full pipeline)
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from content_pipeline.models import ScienceStoryScript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

W, H = 1920, 1080


def ensure_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFmpeg is required. Install with: brew install ffmpeg")
    return exe


def _create_reference_gradient(ffmpeg: str, output: Path) -> None:
    """Create one reference gradient image using FFmpeg's gradients filter."""
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi",
         "-i", f"gradients=s={W}x{H}:c0=0x0f0819:c1=0x2d1445:c2=0x0a0610:c3=0x1a0c2d:n=4,format=rgb24",
         "-frames:v", "1", str(output)],
        check=True, capture_output=True, text=True,
    )


def fill_images(workspace_dir: Path, script: ScienceStoryScript) -> int:
    """Fill all missing scene images with gradient placeholders (fast copy)."""
    ffmpeg = ensure_ffmpeg()
    img_dir = workspace_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    # Create reference gradient once
    ref = workspace_dir / ".reference_gradient.png"
    if not ref.exists():
        _create_reference_gradient(ffmpeg, ref)
        log.info("Reference gradient created: %s (%d bytes)", ref, ref.stat().st_size)

    created = 0
    for i in range(len(script.scenes)):
        p = img_dir / f"scene_{i + 1:04d}.png"
        # Skip if it's a real image (AI-generated, > 20KB)
        if p.exists() and p.stat().st_size > 20000:
            continue
        shutil.copy2(str(ref), str(p))
        created += 1

    if created:
        log.info("Placeholder images: %d created (total: %d)", created, len(script.scenes))
    return created


def fill_audio(workspace_dir: Path, script: ScienceStoryScript) -> int:
    """Fill all missing scene audio with silent MP3 (fast FFmpeg)."""
    ffmpeg = ensure_ffmpeg()
    audio_dir = workspace_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    audios = sum(1 for _ in audio_dir.glob("scene_*.mp3"))
    log.info("Existing audio files: %d / %d", audios, len(script.scenes))

    for i, scene in enumerate(script.scenes):
        p = audio_dir / f"scene_{i + 1:04d}.mp3"
        if p.exists() and p.stat().st_size > 500:
            continue

        dur = max(scene.duration_seconds, 1)
        t0 = time.time()
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", str(dur), "-c:a", "libmp3lame", "-b:a", "128k", str(p)],
            check=True, capture_output=True, text=True,
        )
        created += 1
        if created % 10 == 0:
            elapsed = time.time() - t0
            log.info("  Audio progress: %d/%d created (%.1fs last)", created, len(script.scenes), elapsed)

    if created:
        log.info("Silent audio: %d created", created)
    return created


def assemble_clips(workspace_dir: Path, script: ScienceStoryScript) -> int:
    """Assemble individual scene clips."""
    from content_pipeline.bots.science_video_agent import assemble_scene_clips
    clips = assemble_scene_clips(workspace_dir, script)
    log.info("Scene clips: %d assembled", len(clips))
    return len(clips)


def assemble_final(workspace_dir: Path, script: ScienceStoryScript) -> Path:
    """Assemble final video with crossfade."""
    from content_pipeline.bots.science_video_agent import assemble_final_video
    path = assemble_final_video(workspace_dir, script, add_crossfade=True)
    log.info("Final video: %s", path)
    return path


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Prepare science video workspace")
    parser.add_argument("workspace_dir", help="Path to the workspace directory")
    parser.add_argument("--clips", action="store_true", help="Also assemble scene clips")
    parser.add_argument("--all", action="store_true", help="Full pipeline: images + audio + clips + final")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).resolve()
    script_path = workspace_dir / "script.json"
    if not script_path.exists():
        log.error("No script.json found in %s", workspace_dir)
        sys.exit(1)

    script = ScienceStoryScript.from_dict(
        json.loads(script_path.read_text(encoding="utf-8"))
    )
    log.info("Workspace: %s (%d scenes, %.1f min)",
             workspace_dir, len(script.scenes), script.duration_minutes)

    do_all = args.all

    # Step 1: Images (fast)
    fill_images(workspace_dir, script)

    # Step 2: Audio (fast per file but 65 scenes = a few min)
    fill_audio(workspace_dir, script)

    if args.clips or do_all:
        # Step 3: Clips (slow - 65 FFmpeg renders)
        log.info("Assembling scene clips...")
        assemble_clips(workspace_dir, script)

    if do_all:
        # Step 4: Final video
        log.info("Assembling final video...")
        final = assemble_final(workspace_dir, script)
        log.info("=" * 50)
        log.info("Pipeline complete!")
        log.info("  Video: %s", final)
        log.info("  Duration: %.1f min", script.duration_minutes)
        log.info("  Storyboard: %s", workspace_dir / "ui" / "storyboard.html")
        log.info("=" * 50)


if __name__ == "__main__":
    main()
