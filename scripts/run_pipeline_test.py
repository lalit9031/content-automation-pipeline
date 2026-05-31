"""Self-contained science pipeline test (no API calls)."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from content_pipeline.models import ScienceScene, ScienceStoryScript
from content_pipeline.bots.science_video_agent import (
    create_science_video_workspace, _generate_srt, _slug,
    _multiline_text, _cinematic_prompt, _timestamp, _create_placeholder_image,
)
from content_pipeline.bots.science_story_agent import (
    list_available_topics, save_script_to_disk, _find_template,
)

passed = 0
total = 0

def check(name, ok):
    global passed, total
    total += 1
    status = "PASS" if ok else "FAIL"
    print(f"  {status}: {name}")

# Cleanup
import shutil
for d in ["/tmp/science_test_ws", "/tmp/science_save", "/tmp/ph_test"]:
    p = Path(d)
    if p.exists():
        shutil.rmtree(p)

# 1. Helpers
print("\n1. Helpers...")
check("slug CRISPR", _slug("CRISPR") == "crispr")
check("slug special chars", _slug("Hello! How?") == "hello_how")
check("multiline short", _multiline_text("short", 30) == ["short"])
check("timestamp 0", _timestamp(0) == "00:00:00,000")
check("timestamp 3661", _timestamp(3661) == "01:01:01,000")
check("cinematic prompt", "Cinematic" in _cinematic_prompt("A test"))
check("find template CRISPR", _find_template("CRISPR") is not None)
check("find no match", _find_template("NonExistentXYZ") is None)
topics = list_available_topics()
check("topics contain CRISPR", any("CRISPR" in t for t in topics))

# 2. Model
print("\n2. Model...")
scenes = []
for ch_name, ch_idx in [("C1", 0), ("C2", 1)]:
    for si in range(10):
        scenes.append(ScienceScene(
            chapter=ch_name, chapter_index=ch_idx, scene_index=len(scenes),
            title=f"S{len(scenes)+1}", narration_hi="Test.",
            on_screen_text_hi="T", visual_prompt="V", duration_seconds=30,
        ))
script = ScienceStoryScript(title="Test", topic="CRISPR", tagline="Test",
                            chapters=["C1", "C2"], scenes=scenes)
check("duration 600s", script.duration_seconds == 600)
check("10 scenes per ch", len(script.scenes_for_chapter(0)) == 10)
d = script.as_dict()
r = ScienceStoryScript.from_dict(d)
check("roundtrip title", r.title == "Test")
check("roundtrip duration", r.duration_seconds == 600)

# 3. Workspace
print("\n3. Workspace...")
out = Path("/tmp/science_test_ws")
root = create_science_video_workspace(out, script)
dirs_ok = all((root / d).is_dir() for d in ["images","audio","clips","video","ui","subtitles"])
check("dirs created", dirs_ok)
files_ok = all((root / f).is_file() for f in ["script.json","workspace.json","scene_manifest.json"])
check("files created", files_ok)
check("storyboard exists", (root / "ui/storyboard.html").is_file())
meta = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
check("meta title", meta["title"] == "Test")
check("meta scene count", meta["scene_count"] == 20)

# 4. Storyboard
print("\n4. Storyboard...")
html = (root / "ui/storyboard.html").read_text(encoding="utf-8")
check("CRISPR in html", "CRISPR" in html)
check("C1 in html", "C1" in html)
check("C2 in html", "C2" in html)
check("S20 in html", "S20" in html)

# 5. SRT
print("\n5. SRT...")
srt = _generate_srt(script)
lines = srt.strip().split("\n")
check("srt has many lines", len(lines) > 60)
check("srt starts with 1", lines[0] == "1")
check("srt first timestamp", "00:00:00,000 --> " in srt)

# 6. Save to disk
print("\n6. Save to disk...")
paths = save_script_to_disk(script, "/tmp/science_save")
check("json file exists", Path(paths["json"]).exists())
check("md file exists", Path(paths["markdown"]).exists())
jd = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
check("saved json title", jd["title"] == "Test")

# 7. Placeholder image
print("\n7. Placeholder image...")
sc = ScienceScene(chapter="T", chapter_index=0, scene_index=0, title="T",
                  narration_hi="T", on_screen_text_hi="T", visual_prompt="T",
                  duration_seconds=25)
img_dir = Path("/tmp/ph_test")
img_dir.mkdir(parents=True, exist_ok=True)
img = img_dir / "test.png"
_create_placeholder_image(img, sc, 0)
check("file exists", img.exists())
check("file size > 100", img.stat().st_size > 100)
sig = img.read_bytes()[:8]
check("valid PNG header", sig == b"\x89PNG\r\n\x1a\n")

print(f"\n{'='*50}")
print(f"  RESULTS: {passed}/{total} passed")
print(f"{'='*50}")
sys.exit(0 if passed == total else 1)
