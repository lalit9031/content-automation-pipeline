#!/usr/bin/env python3
"""Generate a batch of science scene images using the Gemini provider.

Usage:
    python scripts/gemini_batch_images.py <workspace_dir> --start 10 --batch 10
    python scripts/gemini_batch_images.py <workspace_dir> --start 20 --batch 10
    ...

Processes scenes in small batches with resume support. Existing images
larger than 20KB are considered "real" and are skipped.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from content_pipeline.config import Settings
from content_pipeline.bots.image import image_provider, ImageVariant
from content_pipeline.models import ScienceStoryScript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

YOUTUBE_WIDTH = 1920
YOUTUBE_HEIGHT = 1080
CINEMATIC_SUFFIX = (
    "Cinematic documentary style, 4K, ultra-detailed, dramatic lighting, "
    "professional color grading, shallow depth of field, volumetric lighting, "
    "atmospheric, no text, no logo, no watermark, no people unless described, "
    "photorealistic, historical accuracy where applicable."
)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Batch-generate Gemini scene images")
    parser.add_argument("workspace_dir", help="Path to the workspace directory")
    parser.add_argument("--start", type=int, required=True, help="Start scene index (0-based)")
    parser.add_argument("--batch", type=int, default=10, help="Number of images to generate")
    args = parser.parse_args()

    settings = Settings.from_environment()
    log.info("Settings: image_provider=%s, %d Gemini keys, %d OpenAI keys",
             settings.image_provider, len(settings.gemini_api_keys), len(settings.openai_api_keys))

    # Wire up the Gemini provider
    gemini_settings = replace(settings, image_provider="gemini")
    provider = image_provider(gemini_settings)
    variant = ImageVariant("16:9", YOUTUBE_WIDTH, YOUTUBE_HEIGHT, "unused")

    workspace_dir = Path(args.workspace_dir).resolve()
    script_path = workspace_dir / "script.json"
    script = ScienceStoryScript.from_dict(
        json.loads(script_path.read_text(encoding="utf-8"))
    )
    image_dir = workspace_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    scenes = script.scenes
    total = len(scenes)
    start_idx = args.start
    end_idx = min(start_idx + args.batch, total)

    log.info("Processing scenes %d-%d of %d", start_idx + 1, end_idx, total)

    generated = 0
    skipped = 0
    failed = 0

    for i in range(start_idx, end_idx):
        scene = scenes[i]
        image_path = image_dir / f"scene_{i + 1:04d}.png"

        # Skip if already a real image (>20KB)
        if image_path.exists() and image_path.stat().st_size > 20000:
            log.info("[%d/%d] SKIP (exists): %s", i + 1, total, scene.title)
            skipped += 1
            continue

        prompt = f"{scene.visual_prompt.strip().rstrip('.')}. {CINEMATIC_SUFFIX}"
        log.info("[%d/%d] Generating: %s ...", i + 1, total, scene.title[:60])

        try:
            t0 = time.time()
            image_bytes = provider.create(prompt, variant)
            elapsed = time.time() - t0
            image_path.write_bytes(image_bytes)
            log.info("  ✓ %s (%d bytes, %.1fs)", image_path.name, len(image_bytes), elapsed)
            generated += 1
        except Exception as exc:
            elapsed = time.time() - t0
            log.error("  ✗ Failed after %.1fs: %s", elapsed, exc)
            failed += 1

    log.info("Batch [%d-%d] done: generated=%d, skipped=%d, failed=%d",
             start_idx + 1, end_idx, generated, skipped, failed)


if __name__ == "__main__":
    main()
