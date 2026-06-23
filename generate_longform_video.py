"""
generate_longform_video.py
==========================
Test runner for the long-form video pipeline.

Run from the project root:
    python generate_longform_video.py

This script:
    1. Runs a single 6-second clip test first
    2. If it passes, runs the 30-second long-form test
    3. Prints a full summary at the end
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from content_pipeline.config import Settings
from content_pipeline.bots.long_form_orchestrator import LongFormOrchestrator

# ---------------------------------------------------------------------------
# CONFIG — change these to test different prompts
# ---------------------------------------------------------------------------

RAW_PROMPT = "girl walking in rain forest toward a river"
SINGLE_CLIP_SECONDS = 6     # First test: single clip
LONG_FORM_SECONDS   = 30    # Second test: 30-second video
OUTPUT_DIR = Path(r"C:\Users\user\Desktop\Output file")

# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------

def main():
    settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)

    print("\n" + "=" * 70)
    print("TEST RUN 1: Single 6-second clip")
    print("=" * 70)
    t1 = time.time()
    result_single = orch.run(
        raw_prompt=RAW_PROMPT,
        target_seconds=SINGLE_CLIP_SECONDS,
        output_dir=OUTPUT_DIR,
        job_name="test_single_clip",
    )
    t1_elapsed = time.time() - t1
    print(f"\nSingle clip result: {result_single['status']}")
    if result_single["status"] == "FAIL":
        print(f"Error: {result_single.get('error')}")
        print("\nSingle clip test failed. Stopping before long-form test.")
        return

    print(f"\nSingle clip video: {result_single['final_video_path']}")
    print(f"Time taken: {t1_elapsed/60:.1f} minutes")

    # Ask before running 30s test
    print("\n" + "=" * 70)
    print("TEST RUN 2: 30-second long-form video")
    print("=" * 70)
    print(f"This will generate 5 chained clips of 6 seconds each.")
    print(f"Estimated time: {5 * t1_elapsed / 60:.0f}–{6 * t1_elapsed / 60:.0f} minutes")
    print("Starting in 5 seconds... (Ctrl+C to cancel)")
    time.sleep(5)

    t2 = time.time()
    result_long = orch.run(
        raw_prompt=RAW_PROMPT,
        target_seconds=LONG_FORM_SECONDS,
        output_dir=OUTPUT_DIR,
        job_name="test_30s_video",
    )
    t2_elapsed = time.time() - t2

    print(f"\n30-second video result: {result_long['status']}")
    if result_long["status"] == "SUCCESS":
        print(f"Final video: {result_long['final_video_path']}")
    print(f"Time taken: {t2_elapsed/60:.1f} minutes")

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Prompt       : {RAW_PROMPT}")
    print(f"Single clip  : {result_single['status']} → {result_single.get('final_video_path', 'N/A')}")
    print(f"30s video    : {result_long['status']} → {result_long.get('final_video_path', 'N/A')}")
    print(f"Total time   : {(t1_elapsed + t2_elapsed)/60:.1f} minutes")
    print("=" * 70)


if __name__ == "__main__":
    main()
