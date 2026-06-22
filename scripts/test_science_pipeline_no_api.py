"""Test the science video pipeline end-to-end without any API calls."""
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from content_pipeline.models import ScienceScene, ScienceStoryScript
from content_pipeline.bots.science_video_agent import (
    create_science_video_workspace,
    _generate_srt,
    _slug,
    _multiline_text,
    _cinematic_prompt,
    _timestamp,
    _create_placeholder_image,
    YOUTUBE_WIDTH,
)
from content_pipeline.bots.science_story_agent import (
    list_available_topics,
    save_script_to_disk,
    _find_template,
    _duration_budget_for_chapter,
    SCIENCE_STORY_TEMPLATES,
)

PASS = 0
FAIL = 1

def build_demo_script() -> ScienceStoryScript:
    scenes = []
    idx = 0
    for ch_name, ch_idx, n, dur in [("Chapter 1", 0, 10, 30), ("Chapter 2", 1, 10, 30)]:
        for _ in range(n):
            scenes.append(ScienceScene(
                chapter=ch_name, chapter_index=ch_idx, scene_index=idx,
                title=f"Scene {idx+1}", narration_hi="Test narration.",
                on_screen_text_hi="Test", visual_prompt="A test scene",
                duration_seconds=dur,
            ))
            idx += 1
    return ScienceStoryScript(
        title="CRISPR: The Journey of Gene Editing",
        topic="The CRISPR Revolution",
        tagline="Editing the code of life",
        chapters=["Chapter 1", "Chapter 2"],
        scenes=scenes,
    )


def test_helpers() -> int:
    assert _slug("The CRISPR Revolution") == "the_crispr_revolution"
    assert _slug("Hello! How are you?") == "hello_how_are_you"
    assert _slug("???") == ""
    assert 1 < len(_multiline_text("A" * 50, max_chars=15)) <= 4
    assert _multiline_text("short", max_chars=30) == ["short"]
    assert _multiline_text("", max_chars=30) == [""]
    assert _timestamp(0) == "00:00:00,000"
    assert _timestamp(65) == "00:01:05,000"
    assert _timestamp(3661) == "01:01:01,000"
    assert "Cinematic documentary style" in _cinematic_prompt("A test")
    assert _find_template("CRISPR") is not None
    assert _find_template("NonExistentXYZ") is None
    assert 120 <= _duration_budget_for_chapter([], 1800, 5, 10) <= 1800
    assert "The CRISPR Revolution" in list_available_topics()
    print("  PASS: helpers")
    return PASS


def test_model() -> int:
    script = build_demo_script()
    total = script.duration_seconds
    assert 500 < total < 700, f"duration={total}"
    assert len(script.scenes_for_chapter(0)) == 10
    assert len(script.scenes_for_chapter(1)) == 10
    data = script.as_dict()
    restored = ScienceStoryScript.from_dict(data)
    assert restored.title == script.title
    assert restored.duration_seconds == script.duration_seconds
    print("  PASS: model")
    return PASS


def test_workspace(tmp: Path) -> int:
    script = build_demo_script()
    root = create_science_video_workspace(tmp, script)
    for sub in ["images", "audio", "clips", "video", "ui", "subtitles"]:
        assert (root / sub).is_dir(), f"missing {sub}"
    for fname in ["script.json", "workspace.json", "scene_manifest.json"]:
        assert (root / fname).is_file(), f"missing {fname}"
    assert (root / "ui" / "storyboard.html").is_file()
    meta = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
    assert meta["title"] == script.title
    assert meta["scene_count"] == len(script.scenes)
    print("  PASS: workspace")
    return PASS


def test_storyboard(tmp: Path) -> int:
    script = build_demo_script()
    root = create_science_video_workspace(tmp, script)
    html = (root / "ui" / "storyboard.html").read_text(encoding="utf-8")
    assert "CRISPR" in html
    assert "Chapter 1" in html
    assert "Chapter 2" in html
    assert "Scene 1" in html
    print("  PASS: storyboard HTML")
    return PASS


def test_srt(script: ScienceStoryScript) -> int:
    srt = _generate_srt(script)
    lines = srt.strip().split("\n")
    assert len(lines) > len(script.scenes) * 3
    assert "00:00:00,000 --> " in srt
    # Last timestamp is second-to-last line (after strip, no trailing empty)
    last_ts = lines[-2]
    assert "-->" in last_ts, f"Expected timestamp, got: {last_ts}"
    print("  PASS: SRT")
    return PASS


def test_save_script(tmp: Path) -> int:
    script = build_demo_script()
    paths = save_script_to_disk(script, str(tmp))
    json_path = Path(paths["json"])
    md_path = Path(paths["markdown"])
    assert json_path.exists(), f"missing {json_path}"
    assert md_path.exists(), f"missing {md_path}"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["title"] == script.title
    print("  PASS: save script")
    return PASS


def test_placeholder(tmp: Path) -> int:
    img_dir = tmp / "test_images"
    img_dir.mkdir()
    scene = ScienceScene(chapter="T", chapter_index=0, scene_index=0,
                         title="T", narration_hi="T", on_screen_text_hi="T",
                         visual_prompt="T", duration_seconds=25)
    img_path = img_dir / "test.png"
    _create_placeholder_image(img_path, scene, 0)
    assert img_path.exists()
    assert img_path.stat().st_size > 100
    assert img_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    print("  PASS: placeholder PNG")
    return PASS


def main() -> int:
    import tempfile

    print("=" * 60)
    print("  SCIENCE STORY PIPELINE TEST (No API)")
    print("=" * 60)

    for name, test_fn in [
        ("Helpers", lambda: test_helpers()),
        ("Model", lambda: test_model()),
    ]:
        print(f"\n1. {name}...")
        if test_fn() != PASS:
            return FAIL

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)

        print(f"\n2. Workspace...")
        if test_workspace(output) != PASS:
            return FAIL

        print(f"\n3. Storyboard...")
        if test_storyboard(output) != PASS:
            return FAIL

        print(f"\n4. SRT...")
        if test_srt(build_demo_script()) != PASS:
            return FAIL

        print(f"\n5. Save to disk...")
        if test_save_script(output) != PASS:
            return FAIL

        print(f"\n6. Placeholder image...")
        if test_placeholder(output) != PASS:
            return FAIL

    print("\n" + "-" * 60)
    print("  ALL 6 TESTS PASSED")
    print("-" * 60)
    return PASS


if __name__ == "__main__":
    sys.exit(main())
