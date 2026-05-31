"""Run science story pipeline tests without API calls."""
import sys, json, tempfile
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
    if ok:
        passed += 1
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name}")

# 1. Helpers
print("1. Helper functions...")
check("slug basic", _slug("The CRISPR Revolution") == "the_crispr_revolution")
check("slug special chars", _slug("Hello! How are you?") == "hello_how_are_you")
check("slug only special", _slug("???") == "")
check("multiline short", _multiline_text("short", 30) == ["short"])
check("multiline empty", _multiline_text("", 30) == [""])
check("multiline wrap", 1 < len(_multiline_text("A" * 50, 15)) <= 4)
check("timestamp 0", _timestamp(0) == "00:00:00,000")
check("timestamp 65", _timestamp(65) == "00:01:05,000")
check("timestamp 3661", _timestamp(3661) == "01:01:01,000")
check("cinematic prompt", "Cinematic" in _cinematic_prompt("A test"))
check("find template", _find_template("CRISPR") is not None)
check("find no match", _find_template("NonExistentXYZ") is None)
check("list topics", "The CRISPR Revolution" in list_available_topics())

# 2. Script building & model validation
print("2. Script building & model validation...")
scenes = []
for ch_idx, ch_name in [(0, "Ch1"), (1, "Ch2")]:
    for si in range(10):
        scenes.append(ScienceScene(
            chapter=ch_name, chapter_index=ch_idx, scene_index=len(scenes),
            title=f"S{len(scenes)+1}", narration_hi="Test narration.",
            on_screen_text_hi="Test Title", visual_prompt="A test scene",
            duration_seconds=30,
        ))
script = ScienceStoryScript(
    title="CRISPR Test", topic="The CRISPR Revolution",
    tagline="Test", chapters=["Ch1", "Ch2"], scenes=scenes,
)
check("duration", script.duration_seconds == 600)
check("scenes per ch0", len(script.scenes_for_chapter(0)) == 10)
check("scenes per ch1", len(script.scenes_for_chapter(1)) == 10)
data = script.as_dict()
restored = ScienceStoryScript.from_dict(data)
check("roundtrip title", restored.title == script.title)
check("roundtrip duration", restored.duration_seconds == script.duration_seconds)

# 3-7. Workspace + storyboard + SRT + save + placeholder
print("3-7. Workspace, storyboard, SRT, save, placeholder...")
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    root = create_science_video_workspace(out, script)

    # Workspace
    dirs_ok = all((root / d).is_dir() for d in ["images","audio","clips","video","ui","subtitles"])
    check("workspace dirs", dirs_ok)
    files_ok = all((root / f).is_file() for f in ["script.json","workspace.json","scene_manifest.json"])
    check("workspace files", files_ok)
    meta = json.loads((root / "workspace.json").read_text())
    check("workspace metadata title", meta["title"] == script.title)
    check("workspace metadata count", meta["scene_count"] == 20)

    # Storyboard
    html = (root / "ui" / "storyboard.html").read_text()
    check("storyboard CRISPR", "CRISPR" in html)
    check("storyboard chapters", "Ch1" in html and "Ch2" in html)
    check("storyboard scenes", "S1" in html and "S20" in html)

    # SRT
    srt = _generate_srt(script)
    lines = srt.strip().split("\n")
    check("srt many lines", len(lines) > 60)
    check("srt first ts", "00:00:00,000 --> " in srt)
    check("srt last ts", "-->" in lines[-2])

    # Save script
    paths = save_script_to_disk(script, str(out))
    check("save json exists", Path(paths["json"]).exists())
    check("save md exists", Path(paths["markdown"]).exists())
    jd = json.loads(Path(paths["json"]).read_text())
    check("save json content", jd["title"] == script.title)

    # Placeholder image
    img_dir = out / "pix"
    img_dir.mkdir()
    sc = ScienceScene(chapter="T", chapter_index=0, scene_index=0,
                      title="T", narration_hi="T", on_screen_text_hi="T",
                      visual_prompt="T", duration_seconds=25)
    ip = img_dir / "test.png"
    _create_placeholder_image(ip, sc, 0)
    check("placeholder exists", ip.exists())
    check("placeholder size > 100", ip.stat().st_size > 100)
    check("placeholder valid png", ip.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n")

print(f"\nResults: {passed}/{total} passed")
sys.exit(0 if passed == total else 1)
