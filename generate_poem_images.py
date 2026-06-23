"""
generate_poem_images.py
=======================
Generates 6 keyframe images for Ring-a-Ring O'Roses.
NO video - review images first.

Fixes applied:
  - Flux generates at 1024x1024 (native, no banding artifacts)
  - Center-cropped to 16:9 then resized to 1280x720 with sharpening
  - ComfyUI cache cleared between each generation (no more duplicate images)
  - Steps: 30, CFG: 3.5 (was 1.0 - too low = poor quality)
  - Style: clean flat cartoon (no blur/bokeh/storybook soft focus)

Run: python generate_poem_images.py
Output: C:\\Users\\user\\Desktop\\Output file\\poem_images\\
"""

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "src")

from content_pipeline.config import Settings
from content_pipeline.bots.long_form_orchestrator import LongFormOrchestrator

OUTPUT_DIR = Path(r"C:\Users\user\Desktop\Output file\poem_images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# PROMPT RULES for clear sharp images:
# - Use "flat color cartoon illustration" NOT "storybook" (storybook = blur/glow)
# - Use "crisp clean lines, sharp focus" explicitly
# - Add negative: "no blur, no bokeh, no depth of field, no soft focus, no glow"
# - Be specific about colors and positions
# - Include "detailed background" to force background rendering
# ---------------------------------------------------------------------------

NEGATIVE = (
    "blurry, blur, bokeh, depth of field, soft focus, hazy, foggy, glow, lens flare, "
    "overexposed, washed out, low quality, bad anatomy, extra limbs, watermark, text, logo"
)

SCENES = [
    {
        "num": 1,
        "title": "Ring_a_Ring_Gathering",
        "prompt": (
            "Flat color cartoon illustration, Disney animation style, "
            "4 cute children ages 6-8 standing in a sunny green garden, "
            "3 girls and 1 boy, "
            "girl on left in bright pink dress, "
            "girl in center-left in yellow dress, "
            "girl in center-right in sky blue dress, "
            "boy on right in red t-shirt and blue shorts, "
            "all children reaching toward each other smiling, "
            "big expressive cartoon eyes, rosy cheeks, cheerful happy faces, "
            "detailed background: lush green grass ground, large colorful flower bushes left and right, "
            "blue sky with white fluffy clouds, green trees behind, "
            "warm sunny daylight, clean soft shadows, "
            "crisp clean lines, sharp focus throughout, flat colors no gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 2,
        "title": "Pocket_Full_of_Posies",
        "prompt": (
            "Flat color cartoon illustration, Disney animation style, "
            "4 cute children ages 6-8 holding hands in a circle in a flower garden, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "each child holding a small bunch of bright pink and yellow flowers in their free hand, "
            "all faces visible, big smiles, laughing happily, "
            "children slightly leaning outward as they dance in a circle, "
            "detailed background: green grass, colorful flower garden with red yellow pink flowers, "
            "blue sky, puffy white clouds, sunny day, "
            "crisp clean outlines, sharp focus, flat cartoon colors, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 3,
        "title": "Atishoo_Spinning_Fast",
        "prompt": (
            "Flat color cartoon illustration, Disney animation style, "
            "4 cute children ages 6-8 spinning fast holding hands in a circle, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "dresses flaring outward from spinning motion, hair blowing sideways, "
            "all laughing with wide open mouths, cartoon sneeze expression, "
            "motion lines around the spinning ring to show speed, "
            "detailed background: green lawn, flower garden, bright blue sky, sunny, "
            "crisp clean cartoon lines, sharp focus, vibrant flat colors, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 4,
        "title": "We_All_Fall_Down",
        "prompt": (
            "Flat color cartoon illustration, Disney animation style, "
            "4 cute children ages 6-8 all falling down onto soft green grass simultaneously, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "children in mid-fall, legs in air, arms out wide, "
            "all laughing with huge open mouth smiles, pure delight on their faces, "
            "colorful flowers scattered on the grass around them, "
            "detailed background: bright green grass, flower garden, blue sky, sunny day, "
            "crisp clean cartoon lines, sharp focus, vibrant flat colors, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 5,
        "title": "Getting_Up_Laughing",
        "prompt": (
            "Flat color cartoon illustration, Disney animation style, "
            "4 cute children ages 6-8 getting up from the grass, helping each other, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "one girl brushing grass off her dress, boy extending hand to help a girl up, "
            "all faces showing big happy laughing smiles, "
            "colorful flowers and green grass around them, "
            "detailed background: flower garden, green lawn, blue sky, warm sunlight, "
            "crisp clean cartoon lines, sharp focus, vibrant flat colors, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 6,
        "title": "Ring_Forms_Again",
        "prompt": (
            "Flat color cartoon illustration, Disney animation style, "
            "4 cute children ages 6-8 holding hands again in a ring, smiling at each other, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "children looking at each other warmly with joyful expressions, "
            "all faces clearly visible with big bright smiles, "
            "detailed background: beautiful flower garden, green grass, tall colorful flowers, "
            "golden late afternoon sunlight, blue sky, "
            "crisp clean cartoon lines, sharp focus, vibrant flat colors, "
            f"negative: {NEGATIVE}"
        ),
    },
]


def main():
    settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)

    print("\n" + "=" * 70)
    print("Ring-a-Ring O'Roses  --  Keyframe Images  (FIXED)")
    print("=" * 70)
    print(f"  Style    : Flat cartoon (Disney style, sharp, no blur)")
    print(f"  Process  : Flux 1024x1024 -> crop -> 1280x720 + sharpen")
    print(f"  Flux     : 30 steps, CFG 3.5 (was: 1.0 = too low)")
    print(f"  Cache    : /free called between each image (no duplicates)")
    print(f"  Output   : {OUTPUT_DIR}")
    print("=" * 70)

    from content_pipeline.bots.comfy_client import ComfyUIClient
    client = ComfyUIClient(settings=settings)
    server_proc, server_log = None, None

    if not client._is_listening():
        print("\n[ComfyUI] Starting server...")
        server_proc, server_log = client._start_server()
        if not client._wait_listening():
            print("ERROR: ComfyUI failed to start")
            return
        print("[ComfyUI] Ready!\n")
    else:
        print("[ComfyUI] Already running.\n")

    generated = []
    t_start = time.time()

    try:
        for scene in SCENES:
            num = scene["num"]
            title = scene["title"].replace("_", " ")
            prompt = scene["prompt"]

            print(f"[Scene {num}/6]  {title}")
            t_scene = time.time()

            try:
                img_bytes = orch._generate_image(prompt)
                out_path = OUTPUT_DIR / f"scene_{num:02d}_{scene['title']}.png"
                out_path.write_bytes(img_bytes)
                elapsed = time.time() - t_scene
                size_kb = len(img_bytes) // 1024
                print(f"  Saved: {out_path.name}  ({size_kb}KB, {elapsed:.0f}s)\n")
                generated.append(out_path)
            except Exception as e:
                print(f"  ERROR: {e}\n")

    finally:
        if server_proc:
            print("[ComfyUI] Stopping server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=15)
            except Exception:
                server_proc.kill()
                server_proc.wait()
            if server_log:
                server_log.close()

    total = time.time() - t_start
    print("=" * 70)
    print("IMAGES DONE")
    print("=" * 70)
    print(f"  Generated : {len(generated)}/{len(SCENES)}")
    print(f"  Time      : {total/60:.1f} minutes")
    print(f"  Location  : {OUTPUT_DIR}")
    for p in generated:
        print(f"  {p.name}  ({round(p.stat().st_size/1024)}KB)")
    print("=" * 70)
    print("\nReview images -> tell me what to change -> then we animate!")


if __name__ == "__main__":
    main()
