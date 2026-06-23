"""
generate_longform_video.py
==========================
Poem video pipeline — Ring-a-Ring O'Roses nursery rhyme.

Each scene has its OWN Flux source image (not just scene 1).
This gives every scene a proper keyframe showing the right moment of the poem.

Run: python generate_longform_video.py
Output: C:\\Users\\user\\Desktop\\Output file\\ring_a_ring_roses\\
"""

import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows cp1252 console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "src")

from content_pipeline.config import Settings
from content_pipeline.bots.long_form_orchestrator import LongFormOrchestrator

# ---------------------------------------------------------------------------
# Ring-a-Ring O'Roses — Scene-by-Scene Poem Storyboard
#
# Each scene has:
#   image_prompt : Sent to Flux to generate a HIGH QUALITY 2D illustration keyframe
#   video_prompt : Sent to LTXV to animate the keyframe (motion description)
#
# IMPORTANT: Every scene generates its OWN Flux image.
# This is what makes each verse of the poem look different and correct.
# ---------------------------------------------------------------------------

POEM_SCENES = [
    {
        # Verse 1: "Ring-a-ring o' roses"
        "scene": 1,
        "title": "Ring a Ring O Roses - gathering",
        "image_prompt": (
            "Beautiful children's book illustration, 4 happy children ages 5-7, "
            "standing together in a sunny green garden about to form a circle, "
            "holding hands, colorful dresses and clothes, pink red yellow blue outfits, "
            "flowers blooming all around them, warm golden afternoon sunlight, "
            "soft watercolor art style, vibrant colors, joyful innocent faces, "
            "sharp detailed illustration, 2K quality"
        ),
        "video_prompt": (
            "Children joining hands and forming a ring, smiling and laughing, "
            "beginning to walk in a slow circle, colorful dresses spinning gently, "
            "flowers visible in the garden background, warm sunlight, joyful motion"
        ),
    },
    {
        # Verse 2: "A pocket full of posies"
        "scene": 2,
        "title": "Pocket full of posies",
        "image_prompt": (
            "Beautiful children's book illustration, 4 happy children ages 5-7, "
            "dancing in a circle in a flower garden, each child holding a small bunch "
            "of colorful wildflowers, pink yellow orange flowers, bright sunny day, "
            "green grass, children laughing with big smiles, colorful dresses twirling, "
            "soft watercolor art style, vibrant warm colors, sharp detailed illustration, 2K quality"
        ),
        "video_prompt": (
            "Children dancing in a ring holding flowers, colorful dresses twirling "
            "as they spin together, laughing faces, flowers waving in the breeze, "
            "joyful circular motion, warm golden light in garden"
        ),
    },
    {
        # Verse 3: "Atishoo! Atishoo!" — spinning faster
        "scene": 3,
        "title": "Atishoo spinning faster",
        "image_prompt": (
            "Beautiful children's book illustration, 4 happy children ages 5-7, "
            "spinning fast in a circle dance, motion blur on their colorful dresses, "
            "big laughing faces, hair flying out from spinning, garden with flowers, "
            "bright sunlight, dynamic energy and joy, soft watercolor art style, "
            "vibrant colors, detailed illustration, 2K quality"
        ),
        "video_prompt": (
            "Children spinning faster in their ring, dresses flying outward, "
            "hair streaming from the motion, laughing and pretending to sneeze, "
            "dynamic joyful spinning motion, garden flowers in background"
        ),
    },
    {
        # Verse 4: "We all fall down!" — falling with laughter
        "scene": 4,
        "title": "We all fall down",
        "image_prompt": (
            "Beautiful children's book illustration, 4 happy children ages 5-7, "
            "all falling down together onto green grass, laughing with delight, "
            "sitting and lying on the grass, flowers around them, colorful outfits, "
            "arms stretched wide, huge smiles, warm sunny garden, "
            "soft watercolor art style, vibrant colors, joyful illustration, 2K quality"
        ),
        "video_prompt": (
            "All children tumbling and falling down onto the soft grass together, "
            "laughing as they land, rolling on the green lawn, flowers around them, "
            "joyful and playful motion, sunshine and warmth"
        ),
    },
    {
        # Verse 5: Getting up, laughing
        "scene": 5,
        "title": "Getting up laughing",
        "image_prompt": (
            "Beautiful children's book illustration, 4 happy children ages 5-7, "
            "getting up from the grass laughing and helping each other up, "
            "big happy smiles, colorful clothes, garden flowers all around, "
            "golden afternoon sunlight, playful and cheerful atmosphere, "
            "soft watercolor art style, warm vibrant colors, detailed illustration, 2K quality"
        ),
        "video_prompt": (
            "Children getting back up from the grass, helping each other stand, "
            "laughing and giggling, brushing grass off clothes, bright garden, "
            "joyful playful energy, warm sunlight filtering through"
        ),
    },
    {
        # Verse 6: Starting again, the ring re-forms
        "scene": 6,
        "title": "Ring forms again - joy",
        "image_prompt": (
            "Beautiful children's book illustration, 4 happy children ages 5-7, "
            "holding hands again in a ring in the sunny garden, smiling at each other, "
            "ready to play again, colorful dresses and outfits, flowers and grass, "
            "warm golden light, pure childhood joy, soft watercolor art style, "
            "vibrant happy colors, detailed 2K quality illustration"
        ),
        "video_prompt": (
            "Children forming the ring again, holding hands and beginning to spin, "
            "smiling at each other with pure joy, colorful dresses starting to twirl, "
            "garden in warm afternoon sunlight, happy circular motion beginning again"
        ),
    },
]

OUTPUT_DIR = Path(r"C:\Users\user\Desktop\Output file")
JOB_NAME   = "ring_a_ring_roses_v2"

# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------

def main():
    settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)

    print("\n" + "=" * 70)
    print("Ring-a-Ring O'Roses  --  Proper Poem Video (per-scene Flux images)")
    print("=" * 70)
    print(f"  Scenes   : {len(POEM_SCENES)} scenes, each with its own Flux keyframe")
    print(f"  Duration : ~{len(POEM_SCENES) * 4}s (97 frames x 24fps = 4s per clip)")
    print(f"  Output   : {OUTPUT_DIR / JOB_NAME}")
    print(f"  Quality  : 1280x720 + unsharp, CRF 18, 45 steps, VAE tile=256")
    print(f"  RAM cap  : 40GB (safe, leaves 24GB for Windows/GPU/apps)")
    print("=" * 70)
    print("\nStarting in 3 seconds...  (Ctrl+C to cancel)")
    time.sleep(3)

    t_start = time.time()
    result = orch.run_poem(
        poem_scenes=POEM_SCENES,
        output_dir=OUTPUT_DIR,
        job_name=JOB_NAME,
    )
    elapsed = time.time() - t_start

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    if result["status"] == "SUCCESS":
        final_path = result.get("final_video_path", "N/A")
        try:
            size_mb = round(Path(str(final_path)).stat().st_size / (1024 * 1024), 1)
        except Exception:
            size_mb = "?"
        print(f"  SUCCESS")
        print(f"  Video  : {final_path}")
        print(f"  Size   : {size_mb} MB")
        print(f"  Time   : {elapsed / 60:.1f} minutes")
    else:
        print(f"  FAILED : {result.get('error', 'Unknown error')}")
        print(f"  Time   : {elapsed / 60:.1f} minutes")

    print("=" * 70)
    print(f"\nOpen your video at: {OUTPUT_DIR / JOB_NAME}")
    print("=" * 70)


if __name__ == "__main__":
    main()
