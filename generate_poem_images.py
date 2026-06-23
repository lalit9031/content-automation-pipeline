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
            "A high-angle shot looking down at 4 cute children standing in a perfect circular ring in a sunny garden. "
            "They are standing in a round circle formation, smiling and reaching out their hands to hold hands. "
            "We see: one girl in a pink dress, one girl in a yellow dress, one girl in a blue dress, and one boy in a red shirt. "
            "Vibrant 2D vector cartoon style, flat clean vector lines, high-contrast flat colors. "
            "Cheerful happy faces, big cartoon eyes, rosy cheeks. "
            "Detailed background: sharp green grass ground, highly detailed flower garden with red, yellow, and purple flower bushes, clear blue sky, green trees. "
            "Infinite focus, 100% sharp background, no depth of field, no blur, no soft focus, crisp clean details on every distant tree and leaf, flat cartoon colors without gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 2,
        "title": "Pocket_Full_of_Posies",
        "prompt": (
            "A high-angle shot looking down at 4 cute children holding hands in a perfect circular ring, dancing in a circle in a flower garden. "
            "They are arranged in a circular formation, holding hands to form a complete, unbroken closed round loop on the green grass. "
            "We see: one girl in a pink dress, one girl in a yellow dress, one girl in a blue dress, and one boy in a red shirt. "
            "They hold posy flowers in their hands. "
            "Vibrant 2D vector cartoon style, flat clean vector lines, high-contrast flat colors. "
            "All faces visible, laughing and smiling. "
            "Detailed background: sharp green lawn, highly detailed flower garden with red, yellow, and purple flowers, clear blue sky, warm sunny day. "
            "Infinite focus, 100% sharp background, no depth of field, no blur, no soft focus, crisp clean details on every distant tree and leaf, flat cartoon colors without gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 3,
        "title": "Atishoo_Spinning_Fast",
        "prompt": (
            "A high-angle shot looking down at 4 cute children spinning fast in a perfect circular ring, holding hands to form a complete closed circle. "
            "The children are arranged in a circular formation, spinning in a round loop. "
            "We see: one girl in a pink dress, one girl in a yellow dress, one girl in a blue dress, and one boy in a red shirt. "
            "Their dresses flare outward from the spinning motion, hair blowing sideways, all laughing with wide open mouths, joyful expressions. "
            "Vibrant 2D vector cartoon style, flat clean vector lines, high-contrast flat colors. "
            "Motion lines around the spinning ring to show speed. "
            "Detailed background: sharp green lawn, highly detailed flower garden with red, yellow, and purple flowers, clear blue sky, warm sunny day. "
            "Infinite focus, 100% sharp background, no depth of field, no blur, no soft focus, crisp clean details on every distant tree and leaf, flat cartoon colors without gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 4,
        "title": "We_All_Fall_Down",
        "prompt": (
            "A high-angle view looking down at 4 cute children falling down onto soft green grass, arranged in a perfect circle. "
            "We see: one girl in a pink dress, one girl in a yellow dress, one girl in a blue dress, and one boy in a red shirt. "
            "They are falling backward and sideways onto the ground in a circular formation, landing on the grass with legs and arms out, laughing with huge open mouth smiles. "
            "Vibrant 2D vector cartoon style, flat clean vector lines, high-contrast flat colors. "
            "Bright colorful flowers scattered on the grass around them. "
            "Detailed background: sharp green grass ground, highly detailed flower garden, clear blue sky, warm sunny day. "
            "Infinite focus, 100% sharp background, no depth of field, no blur, no soft focus, crisp clean details on every distant tree and leaf, flat cartoon colors without gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 5,
        "title": "Getting_Up_Laughing",
        "prompt": (
            "A high-angle shot of 4 cute children getting up from the green grass, arranged in a perfect circle, helping each other. "
            "We see: one girl in a pink dress, one girl in a yellow dress, one girl in a blue dress, and one boy in a red shirt. "
            "They are in a circular formation on the lawn, one boy extending his hand to help a girl stand up, they are laughing and smiling. "
            "Vibrant 2D vector cartoon style, flat clean vector lines, high-contrast flat colors. "
            "Detailed background: sharp green grass ground, highly detailed flower garden with red, yellow, and purple flowers, clear blue sky, warm sunny day. "
            "Infinite focus, 100% sharp background, no depth of field, no blur, no soft focus, crisp clean details on every distant tree and leaf, flat cartoon colors without gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
    {
        "num": 6,
        "title": "Ring_Forms_Again",
        "prompt": (
            "A high-angle shot looking down at 4 cute children holding hands in a perfect circular ring, standing in a circle in a flower garden. "
            "They are arranged in a circular formation, holding hands to form a complete, unbroken closed round loop. "
            "We see: one girl in a pink dress, one girl in a yellow dress, one girl in a blue dress, and one boy in a red shirt. "
            "Vibrant 2D vector cartoon style, flat clean vector lines, high-contrast flat colors. "
            "All faces clearly visible, smiling warmly at each other with joyful expressions. "
            "Detailed background: sharp green lawn, highly detailed flower garden with red, yellow, and purple flowers, clear blue sky, warm sunny day. "
            "Infinite focus, 100% sharp background, no depth of field, no blur, no soft focus, crisp clean details on every distant tree and leaf, flat cartoon colors without gradients, "
            f"negative: {NEGATIVE}"
        ),
    },
]


def main():
    settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)

    print("\n" + "=" * 70)
    print("Ring-a-Ring O'Roses  --  Keyframe Images  (VECTORED & RE-SHARPENED)")
    print("=" * 70)
    print(f"  Style    : Vibrant 2D vector cartoon (100% sharp background, no blur)")
    print(f"  Process  : Flux 1024x576 -> 1280x720 + sharpen")
    print(f"  Flux     : 30 steps, CFG 3.5")
    print(f"  Cache    : ComfyUI started & stopped fresh per-image to avoid VRAM context issues")
    print(f"  Output   : {OUTPUT_DIR}")
    print("=" * 70)

    generated = []
    t_start = time.time()

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
