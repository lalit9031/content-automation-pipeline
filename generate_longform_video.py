"""
generate_longform_video.py
==========================
Test runner for the long-form video pipeline.

Run from the project root:
    python generate_longform_video.py

Current test: Ring-a-Ring O'Roses — nursery rhyme for kids
  6 scenes x 5s = 30-second video
  Output: C:\\Users\\user\\Desktop\\Output file\\ring_a_ring_roses\\
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from content_pipeline.config import Settings
from content_pipeline.bots.long_form_orchestrator import LongFormOrchestrator

# ---------------------------------------------------------------------------
# CONFIG
# Ring-a-Ring O'Roses nursery rhyme for kids.
# Bright, colourful, cheerful — children dancing in a circle.
# ---------------------------------------------------------------------------

RAW_PROMPT = (
    "happy children playing Ring-a-Ring O Roses in a sunny garden, "
    "holding hands in a circle, spinning and dancing, "
    "bright colorful dresses, green grass, flowers all around, "
    "joyful smiling faces, warm golden sunlight"
)

LONG_FORM_SECONDS = 30      # 6 scenes x 5s = 30 seconds
OUTPUT_DIR = Path(r"C:\Users\user\Desktop\Output file")
JOB_NAME   = "ring_a_ring_roses"

# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------

def main():
    settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)

    print("\n" + "=" * 70)
    print("Ring-a-Ring O'Roses  --  Nursery Rhyme Video")
    print("=" * 70)
    print(f"  Prompt   : {RAW_PROMPT[:80]}...")
    print(f"  Duration : {LONG_FORM_SECONDS}s  ({LONG_FORM_SECONDS // 5} scenes x 5s each)")
    print(f"  Output   : {OUTPUT_DIR / JOB_NAME}")
    print(f"  Quality  : 1280x720, CRF 18 (sharp), 45 steps, CFG 3.5")
    print("=" * 70)
    print("\nStarting in 3 seconds...  (Ctrl+C to cancel)")
    time.sleep(3)

    t_start = time.time()
    result = orch.run(
        raw_prompt=RAW_PROMPT,
        target_seconds=LONG_FORM_SECONDS,
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
        print(f"  FAILED")
        print(f"  Error  : {result.get('error', 'Unknown error')}")
        print(f"  Time   : {elapsed / 60:.1f} minutes")

    print("=" * 70)
    print(f"\nOpen your video at: {OUTPUT_DIR / JOB_NAME}")
    print("=" * 70)


if __name__ == "__main__":
    main()
