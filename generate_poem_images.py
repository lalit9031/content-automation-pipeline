"""
generate_poem_images.py
=======================
Generates ONLY the 6 keyframe images for Ring-a-Ring O'Roses.
NO video. Review images first, then we animate.

Resolution: 1280x720 (16:9, matches final video -- zero upscaling)
Output: C:\\Users\\user\\Desktop\\Output file\\poem_images\\

Run: python generate_poem_images.py
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
# 6 scene image prompts — each is a specific moment in the poem
# Generated at 1280x720, no upscaling, sharp and clear
# ---------------------------------------------------------------------------

SCENES = [
    {
        "num": 1,
        "title": "Ring_a_Ring_Gathering",
        "prompt": (
            "Beautiful high quality children's book illustration, "
            "4 happy children ages 5-8, 3 girls and 1 boy, "
            "standing in a sunny green garden about to join hands to form a circle, "
            "colorful bright outfits - girl in pink dress, girl in yellow dress, "
            "girl in blue dress, boy in red shirt and shorts, "
            "big joyful smiling faces clearly visible, large expressive eyes, "
            "wildflowers blooming all around, lush green grass, "
            "warm golden afternoon sunlight, soft shadows, "
            "vibrant saturated colors, clean sharp illustration, "
            "children's storybook art style, no blur, no watermark"
        ),
    },
    {
        "num": 2,
        "title": "Pocket_Full_of_Posies_Dancing_Ring",
        "prompt": (
            "Beautiful high quality children's book illustration, "
            "4 happy children ages 5-8 holding hands in a circle dance, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "each child holding a small bunch of pink and yellow wildflowers, "
            "colorful dresses gently swirling, faces smiling and laughing clearly visible, "
            "green garden with colorful flowers everywhere, warm sunlight streaming in, "
            "vibrant saturated colors, clean sharp storybook illustration, no blur, no watermark"
        ),
    },
    {
        "num": 3,
        "title": "Atishoo_Spinning_Fast",
        "prompt": (
            "Beautiful high quality children's book illustration, "
            "4 happy children ages 5-8 spinning fast in a circle, holding hands, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "colorful dresses flaring outward from spinning, hair flying, "
            "faces with wide open laughing mouths, cheeks puffed like sneezing Atishoo!, "
            "dynamic motion energy, sunny garden with flowers in background, "
            "vibrant saturated colors, clean sharp storybook illustration, no blur, no watermark"
        ),
    },
    {
        "num": 4,
        "title": "We_All_Fall_Down",
        "prompt": (
            "Beautiful high quality children's book illustration, "
            "4 happy children ages 5-8 all falling down together onto soft green grass, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "all laughing with absolute delight, arms and legs in the air mid-fall, "
            "flowers scattered around them on the grass, sunny garden, "
            "faces showing pure joy and laughter very clearly, "
            "vibrant saturated colors, clean sharp storybook illustration, no blur, no watermark"
        ),
    },
    {
        "num": 5,
        "title": "Getting_Up_Laughing",
        "prompt": (
            "Beautiful high quality children's book illustration, "
            "4 happy children ages 5-8 sitting on green grass getting up and helping each other, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "laughing and smiling together, one girl brushing grass off her dress, "
            "colorful flowers in sunny garden background, warm golden light, "
            "faces with big happy smiles very clearly visible, "
            "vibrant saturated colors, clean sharp storybook illustration, no blur, no watermark"
        ),
    },
    {
        "num": 6,
        "title": "Ring_Forms_Again_Pure_Joy",
        "prompt": (
            "Beautiful high quality children's book illustration, "
            "4 happy children ages 5-8 holding hands again forming a circle, "
            "girl in pink dress, girl in yellow dress, girl in blue dress, boy in red shirt, "
            "smiling warmly at each other, looking at each other with joyful faces, "
            "garden full of colorful flowers in warm golden afternoon light, "
            "children's faces radiant and full of joy and happiness, "
            "vibrant saturated colors, clean sharp storybook illustration, no blur, no watermark"
        ),
    },
]


def main():
    settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)

    print("\n" + "=" * 70)
    print("Ring-a-Ring O'Roses  --  Scene Keyframe Images")
    print("=" * 70)
    print(f"  Scenes     : {len(SCENES)}")
    print(f"  Resolution : 1280x720 (16:9, same as final video -- no upscaling)")
    print(f"  Output     : {OUTPUT_DIR}")
    print("=" * 70)

    # Start ComfyUI once for all 6 images (no restart needed between images)
    from content_pipeline.bots.comfy_client import ComfyUIClient
    client = ComfyUIClient(settings=settings)
    server_proc, server_log = None, None

    if not client._is_listening():
        print("\n[ComfyUI] Starting server for image generation...")
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
            title = scene["title"]
            prompt = scene["prompt"]

            print(f"[Scene {num}/6]  {title.replace('_', ' ')}")
            t_scene = time.time()

            try:
                img_bytes = orch._generate_image(prompt)
                out_path = OUTPUT_DIR / f"scene_{num:02d}_{title}.png"
                out_path.write_bytes(img_bytes)
                elapsed = time.time() - t_scene
                size_kb = len(img_bytes) // 1024
                print(f"  Saved: {out_path.name}  ({size_kb}KB, {elapsed:.0f}s)")
                generated.append(out_path)
            except Exception as e:
                print(f"  ERROR on scene {num}: {e}")

    finally:
        if server_proc:
            print("\n[ComfyUI] Stopping server and freeing RAM...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=15)
            except Exception:
                server_proc.kill()
                server_proc.wait()
            if server_log:
                server_log.close()
            print("[ComfyUI] Done.")

    total = time.time() - t_start
    print("\n" + "=" * 70)
    print("ALL IMAGES DONE")
    print("=" * 70)
    print(f"  Generated : {len(generated)}/{len(SCENES)} images")
    print(f"  Time      : {total/60:.1f} minutes")
    print(f"  Location  : {OUTPUT_DIR}")
    print()
    for p in generated:
        size_kb = round(p.stat().st_size / 1024)
        print(f"  {p.name}  --  {size_kb}KB")
    print("=" * 70)
    print()
    print("Review the images in your Output file folder.")
    print("Tell me what to change before we start the video!")


if __name__ == "__main__":
    main()
