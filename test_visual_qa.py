"""
test_visual_qa.py — Standalone Visual QA test runner
======================================================
Run this directly from VS Code terminal or the Run button.

Usage:
    # Test a specific image file
    python test_visual_qa.py

    # Test with a custom image
    python test_visual_qa.py --image "C:/path/to/image.png" --prompt "your prompt"

    # Test a video (extracts frames and audits each)
    python test_visual_qa.py --video "C:/path/to/video.mp4"

Requirements:
    - Ollama running:     ollama serve
    - Moondream pulled:  ollama pull moondream
"""

import argparse
import sys
import json
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — works from any directory in the project
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_IMAGE = Path(r"C:\Users\user\Desktop\Output file\image\girl_in_rain_aligned.png")
DEFAULT_VIDEO = Path(r"C:\Users\user\Desktop\Output file\video\girl_walking_to_river.mp4")
DEFAULT_PROMPT = (
    "Pixar 3D animated style cute girl with colorful umbrella "
    "walking towards the river bank in the rain"
)


def check_ollama() -> bool:
    """Check if Ollama is running and Moondream is available."""
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            models = json.loads(r.read())
            names = [m["name"] for m in models.get("models", [])]
            if not any("moondream" in n for n in names):
                print("[FAIL] Moondream not found in Ollama.")
                print("   Run:  ollama pull moondream")
                return False
            print(f"[OK] Ollama running. Models: {names}")
            return True
    except urllib.error.URLError:
        print("[FAIL] Ollama server is not running.")
        print("   Run:  ollama serve")
        print("   Then: ollama pull moondream")
        return False


def test_image(image_path: Path, prompt: str) -> dict:
    """Audit a single image file."""
    from content_pipeline.config import Settings
    from content_pipeline.bots.qa_auditor import QAVisualAuditor

    if not image_path.exists():
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)

    settings = Settings.from_environment()
    auditor = QAVisualAuditor(settings)

    print(f"\n{'='*60}")
    print(f"  MOONDREAM VISUAL QA TEST — IMAGE")
    print(f"{'='*60}")
    print(f"  Image:  {image_path.name}")
    print(f"  Prompt: {prompt[:70]}...")
    print(f"{'='*60}\n")

    print("Sending to Moondream for analysis...")
    result = auditor.audit_image_file(image_path, prompt)

    status = result.get("status", "UNKNOWN")
    icon = "✅" if status == "PASS" else "❌"

    print(f"\n{icon}  STATUS: {status}")
    if result.get("reason"):
        print(f"   Reason:      {result['reason']}")
    if result.get("defect_type"):
        print(f"   Defect type: {result['defect_type']}")

    print(f"\nFull result: {json.dumps(result, indent=2)}")
    return result


def test_video(video_path: Path, prompt: str, sample_count: int = 8) -> dict:
    """Extract frames from a video and audit using VideoTesterAgent."""
    from content_pipeline.config import Settings
    from content_pipeline.bots.video_tester import VideoTesterAgent

    if not video_path.exists():
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)

    settings = Settings.from_environment()
    tester = VideoTesterAgent(settings)

    print(f"\n{'='*60}")
    print(f"  MOONDREAM VISUAL QA TEST — VIDEO")
    print(f"{'='*60}")
    print(f"  Video:   {video_path.name}")
    print(f"  Prompt:  {prompt[:60]}...")
    print(f"  Samples: {sample_count} frames")
    print(f"{'='*60}\n")

    result = tester.audit_video(video_path, prompt, sample_count)
    
    print(f"\n{'='*60}")
    print(f"  FINAL VIDEO QA RESULT: {result['status']}")
    print(f"  Reason: {result.get('reason')}")
    print(f"{'='*60}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test Moondream Visual QA on image or video",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--image", type=str, default=None,
                        help="Path to image file to audit")
    parser.add_argument("--video", type=str, default=None,
                        help="Path to video file to audit (extracts frames)")
    parser.add_argument("--prompt", type=str, default=DEFAULT_PROMPT,
                        help="The generation prompt to test against")
    parser.add_argument("--samples", type=int, default=5,
                        help="Number of frames to sample from video (default: 5)")
    args = parser.parse_args()

    # Always check Ollama first
    if not check_ollama():
        sys.exit(1)

    if args.video:
        test_video(Path(args.video), args.prompt, args.samples)
    elif args.image:
        test_image(Path(args.image), args.prompt)
    else:
        # Default: test both default image and video if they exist
        print("\n[No --image or --video specified. Running defaults...]\n")
        if DEFAULT_IMAGE.exists():
            test_image(DEFAULT_IMAGE, DEFAULT_PROMPT)
        else:
            print(f"Default image not found: {DEFAULT_IMAGE}")

        if DEFAULT_VIDEO.exists():
            print()
            test_video(DEFAULT_VIDEO, DEFAULT_PROMPT)
        else:
            print(f"Default video not found: {DEFAULT_VIDEO}")


if __name__ == "__main__":
    main()
