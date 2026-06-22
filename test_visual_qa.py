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
                print("❌ Moondream not found in Ollama.")
                print("   Run:  ollama pull moondream")
                return False
            print(f"✅ Ollama running. Models: {names}")
            return True
    except urllib.error.URLError:
        print("❌ Ollama server is not running.")
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


def test_video(video_path: Path, prompt: str, sample_count: int = 5) -> list[dict]:
    """Extract frames from a video and audit each one."""
    try:
        import cv2
    except ImportError:
        print("❌ OpenCV not installed. Run: pip install opencv-python")
        sys.exit(1)

    from content_pipeline.config import Settings
    from content_pipeline.bots.qa_auditor import QAVisualAuditor

    if not video_path.exists():
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)

    settings = Settings.from_environment()
    auditor = QAVisualAuditor(settings)

    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0

    print(f"\n{'='*60}")
    print(f"  MOONDREAM VISUAL QA TEST — VIDEO")
    print(f"{'='*60}")
    print(f"  Video:   {video_path.name}")
    print(f"  Frames:  {total_frames} @ {fps:.1f} FPS ({duration:.1f}s)")
    print(f"  Prompt:  {prompt[:60]}...")
    print(f"  Samples: {sample_count} frames")
    print(f"{'='*60}\n")

    # Sample evenly spaced frames
    import numpy as np
    indices = [int(i) for i in np.linspace(0, total_frames - 1, sample_count)]
    results = []

    for i, frame_idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            print(f"  ⚠️  Could not read frame {frame_idx}")
            continue

        # Encode frame as PNG bytes
        _, buf = cv2.imencode(".png", frame)
        frame_bytes = buf.tobytes()

        print(f"  Auditing frame {frame_idx} ({i+1}/{sample_count})...", end="  ")
        result = auditor.audit_image(frame_bytes, prompt)
        status = result.get("status", "?")
        icon = "✅" if status == "PASS" else "❌"
        reason = f"— {result.get('reason', '')}" if result.get("reason") else ""
        print(f"{icon} {status} {reason}")
        results.append({"frame": frame_idx, **result})

    cap.release()

    # Summary
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = len(results) - passed

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {passed}/{len(results)} frames passed")
    if failed:
        print(f"  ❌ {failed} frames FAILED — video needs re-generation")
    else:
        print(f"  ✅ All frames passed — video quality OK")
    print(f"{'='*60}")

    return results


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
