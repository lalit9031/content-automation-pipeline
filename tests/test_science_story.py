"""Tests for the Science Discovery Story agents and models."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_pipeline.models import (
    ScienceScene,
    ScienceStoryScript,
    ScienceVideoWorkspace,
)
from content_pipeline.bots.science_story_agent import (
    generate_science_story_script,
    list_available_topics,
    save_script_to_disk,
    _find_template,
    _duration_budget_for_chapter,
    _validate_script_duration,
    SCIENCE_STORY_TEMPLATES,
)
from content_pipeline.bots.science_video_agent import (
    create_science_video_workspace,
    _slug,
    _multiline_text,
    _generate_srt,
    YOUTUBE_WIDTH,
    YOUTUBE_HEIGHT,
)
from content_pipeline.config import Settings
from content_pipeline.bots.image import MockImageProvider, ImageVariant


class ScienceSceneModelTest(unittest.TestCase):
    """Test the ScienceScene dataclass parsing and validation."""

    def test_valid_scene_parses_correctly(self) -> None:
        scene = ScienceScene.from_dict({
            "chapter": "The Accidental Laboratory",
            "chapter_index": 0,
            "scene_index": 0,
            "title": "A Messy Bench",
            "narration_hi": "1928 में, अलेक्जेंडर फ्लेमिंग की प्रयोगशाला गंदी थी।",
            "on_screen_text_hi": "एक गंदी प्रयोगशाला",
            "visual_prompt": "A cluttered 1920s laboratory bench with petri dishes, warm lighting, dust particles in sunbeams.",
            "duration_seconds": 25,
        })
        self.assertEqual(scene.chapter, "The Accidental Laboratory")
        self.assertEqual(scene.chapter_index, 0)
        self.assertEqual(scene.scene_index, 0)
        self.assertEqual(scene.title, "A Messy Bench")
        self.assertEqual(scene.duration_seconds, 25)
        self.assertIn("फ्लेमिंग", scene.narration_hi)
        self.assertIn("गंदी", scene.on_screen_text_hi)

    def test_duration_outside_bounds_raises(self) -> None:
        with self.assertRaises(ValueError):
            ScienceScene.from_dict({
                "chapter": "Test",
                "chapter_index": 0,
                "scene_index": 0,
                "title": "Too short",
                "narration_hi": "Test",
                "on_screen_text_hi": "Test",
                "visual_prompt": "Test prompt",
                "duration_seconds": 5,  # below minimum 8
            })
        with self.assertRaises(ValueError):
            ScienceScene.from_dict({
                "chapter": "Test",
                "chapter_index": 0,
                "scene_index": 0,
                "title": "Too long",
                "narration_hi": "Test",
                "on_screen_text_hi": "Test",
                "visual_prompt": "Test prompt",
                "duration_seconds": 50,  # above maximum 45
            })


class ScienceStoryScriptModelTest(unittest.TestCase):
    """Test the ScienceStoryScript dataclass."""

    def make_script(self, scene_count: int = 10) -> ScienceStoryScript:
        scenes = [
            ScienceScene(
                chapter="Test Chapter",
                chapter_index=0,
                scene_index=i,
                title=f"Scene {i + 1}",
                narration_hi=f"यह दृश्य {i + 1} है।",
                on_screen_text_hi=f"दृश्य {i + 1}",
                visual_prompt=f"Test visual prompt {i + 1}",
                duration_seconds=25,
            )
            for i in range(scene_count)
        ]
        return ScienceStoryScript(
            title="Test Science Story",
            topic="The Discovery of Penicillin",
            tagline="A test story",
            chapters=["Test Chapter"],
            scenes=scenes,
        )

    def test_duration_calculation(self) -> None:
        script = self.make_script(scene_count=10)
        self.assertEqual(script.duration_seconds, 250)  # 10 * 25
        self.assertAlmostEqual(script.duration_minutes, 250 / 60)

    def test_scenes_for_chapter(self) -> None:
        script = self.make_script(scene_count=5)
        scenes = script.scenes_for_chapter(0)
        self.assertEqual(len(scenes), 5)
        self.assertEqual(script.scenes_for_chapter(1), [])

    def test_as_dict_roundtrip(self) -> None:
        script = self.make_script(scene_count=30)  # 30 * 25s = 750s >= 600s minimum
        data = script.as_dict()
        restored = ScienceStoryScript.from_dict(data)
        self.assertEqual(restored.title, script.title)
        self.assertEqual(restored.topic, script.topic)
        self.assertEqual(restored.duration_seconds, script.duration_seconds)

    def test_minimum_duration_enforced(self) -> None:
        # Must be at least 600 seconds (10 minutes)
        with self.assertRaises(ValueError):
            ScienceStoryScript.from_dict({
                "title": "Too Short",
                "topic": "Test",
                "tagline": "Test",
                "chapters": ["One"],
                "scenes": [
                    {
                        "chapter": "One",
                        "chapter_index": 0,
                        "scene_index": 0,
                        "title": "Scene",
                        "narration_hi": "Test",
                        "on_screen_text_hi": "Test",
                        "visual_prompt": "Test",
                        "duration_seconds": 15,
                    }
                ],
            })


class ScienceStoryAgentTest(unittest.TestCase):
    """Test the science story agent functions."""

    def test_available_topics(self) -> None:
        topics = list_available_topics()
        self.assertGreaterEqual(len(topics), 5)
        self.assertIn("The Discovery of Penicillin", topics)

    def test_find_template_exact_match(self) -> None:
        template = _find_template("The Discovery of Penicillin")
        self.assertIsNotNone(template)
        if template:
            self.assertEqual(template["topic"], "The Discovery of Penicillin")

    def test_find_template_partial_match(self) -> None:
        template = _find_template("Penicillin")
        self.assertIsNotNone(template)

    def test_find_template_no_match(self) -> None:
        template = _find_template("NonExistentTopicXYZ")
        self.assertIsNone(template)

    def test_duration_budget_allocation(self) -> None:
        budget = _duration_budget_for_chapter(
            scenes_so_far=[],
            target_seconds=1800,
            remaining_chapters=5,
            estimated_scenes=10,
        )
        self.assertGreaterEqual(budget, 120)
        self.assertLessEqual(budget, 1800)

        # With some scenes already used
        from content_pipeline.models import ScienceScene
        used = [
            ScienceScene(
                chapter="Prev",
                chapter_index=0,
                scene_index=i,
                title=f"S{i}",
                narration_hi="Test",
                on_screen_text_hi="Test",
                visual_prompt="Test",
                duration_seconds=25,
            )
            for i in range(10)
        ]
        budget2 = _duration_budget_for_chapter(
            scenes_so_far=used,
            target_seconds=1800,
            remaining_chapters=3,
            estimated_scenes=12,
        )
        self.assertGreaterEqual(budget2, 120)

    def test_script_generation_requires_openai_key(self) -> None:
        settings = Settings(output_dir=Path("output"))
        with self.assertRaises(ValueError):
            generate_science_story_script(settings)


class ScienceVideoWorkspaceTest(unittest.TestCase):
    """Test workspace creation and video agent functions."""

    def make_script(self) -> ScienceStoryScript:
        scenes = [
            ScienceScene(
                chapter="Test Chapter",
                chapter_index=0,
                scene_index=i,
                title=f"Scene {i + 1}",
                narration_hi=f"Narration {i + 1}",
                on_screen_text_hi=f"Text {i + 1}",
                visual_prompt=f"Visual {i + 1}",
                duration_seconds=25,
            )
            for i in range(40)
        ]
        return ScienceStoryScript(
            title="Test Science Video",
            topic="Test Topic",
            tagline="Test tagline",
            chapters=["Test Chapter", "Second Chapter"],
            scenes=scenes,
            background_music_mood="cinematic",
        )

    def test_workspace_creates_directory_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            script = self.make_script()
            root = create_science_video_workspace(output, script)
            self.assertTrue(root.exists())
            self.assertTrue((root / "images").exists())
            self.assertTrue((root / "audio").exists())
            self.assertTrue((root / "audio" / "audio_manifest.json").exists())
            self.assertTrue((root / "audio" / "audio_status.html").exists())
            self.assertTrue((root / "clips").exists())
            self.assertTrue((root / "video").exists())
            self.assertTrue((root / "ui").exists())
            self.assertTrue((root / "subtitles").exists())

    def test_workspace_writes_script_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            script = self.make_script()
            root = create_science_video_workspace(output, script)
            self.assertTrue((root / "script.json").exists())
            self.assertTrue((root / "workspace.json").exists())
            self.assertTrue((root / "scene_manifest.json").exists())

            # Validate workspace metadata
            meta = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["title"], "Test Science Video")
            self.assertEqual(meta["scene_count"], 40)
            audio_manifest = json.loads((root / "audio" / "audio_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(audio_manifest["audio_status"], "pending")
            self.assertEqual(audio_manifest["scene_count"], 40)
            self.assertIn("narration audio will be generated later", audio_manifest["notes"].lower())

    def test_workspace_writes_storyboard_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            script = self.make_script()
            root = create_science_video_workspace(output, script)
            storyboard = root / "ui" / "storyboard.html"
            self.assertTrue(storyboard.exists())
            html = storyboard.read_text(encoding="utf-8")
            self.assertIn("Test Science Video", html)
            self.assertIn("Test Chapter", html)
            self.assertIn("Second Chapter", html)

    def test_workspace_metadata_roundtrip(self) -> None:
        meta = ScienceVideoWorkspace(
            story_id="test_123",
            title="Test",
            topic="Science",
            workspace_path="/tmp/test",
            created_at="2026-05-30T00:00:00",
            scene_count=40,
            total_duration_seconds=1000,
        )
        data = meta.as_dict()
        restored = ScienceVideoWorkspace.from_dict(data)
        self.assertEqual(restored.story_id, "test_123")
        self.assertEqual(restored.scene_count, 40)
        self.assertEqual(restored.total_duration_seconds, 1000)


class ScienceVideoHelpersTest(unittest.TestCase):
    """Test helper functions in the science video agent."""

    def test_slug_creates_safe_filename(self) -> None:
        self.assertEqual(_slug("The Discovery of Penicillin"), "the_discovery_of_penicillin")
        self.assertEqual(_slug("Hello! How are you?"), "hello_how_are_you")
        self.assertEqual(_slug("Hello?World"), "hello_world")
        self.assertEqual(_slug(""), "")

    def test_multiline_text_wrapping(self) -> None:
        text = "यह एक लंबा हिंदी वाक्य है जो कई लाइनों में बंट जाएगा"
        lines = _multiline_text(text, max_chars=20)
        self.assertGreater(len(lines), 1)
        self.assertLessEqual(len(lines), 4)

    def test_multiline_text_short(self) -> None:
        lines = _multiline_text("छोटा वाक्य", max_chars=30)
        self.assertEqual(len(lines), 1)

    def test_multiline_text_empty(self) -> None:
        lines = _multiline_text("", max_chars=30)
        self.assertEqual(lines, [""])

    def test_srt_generation(self) -> None:
        scenes = [
            ScienceScene(
                chapter="Ch1", chapter_index=0, scene_index=0,
                title="S1", narration_hi="Test one.",
                on_screen_text_hi="One", visual_prompt="V1",
                duration_seconds=10,
            ),
            ScienceScene(
                chapter="Ch1", chapter_index=0, scene_index=1,
                title="S2", narration_hi="Test two.",
                on_screen_text_hi="Two", visual_prompt="V2",
                duration_seconds=15,
            ),
        ]
        script = ScienceStoryScript(
            title="Test", topic="T", tagline="TT",
            chapters=["Ch1"], scenes=scenes,
        )
        srt = _generate_srt(script)
        self.assertIn("00:00:00,000 --> 00:00:10,000", srt)
        self.assertIn("Test one.", srt)
        self.assertIn("00:00:10,000 --> 00:00:25,000", srt)
        self.assertIn("Test two.", srt)

    def test_image_dimensions(self) -> None:
        """Verify that the YouTube resolution constants are correct."""
        self.assertEqual(YOUTUBE_WIDTH, 1920)
        self.assertEqual(YOUTUBE_HEIGHT, 1080)

    def test_mock_image_provider(self) -> None:
        """Verify mock image provider works for 16:9 variant."""
        provider = MockImageProvider()
        variant = ImageVariant("16:9", 1920, 1080, "test")
        image_bytes = provider.create("Test prompt for science", variant)
        self.assertTrue(image_bytes.startswith(b"<svg"))
        self.assertIn(b"1920", image_bytes)
        self.assertIn(b"1080", image_bytes)

    def test_save_script_to_disk(self) -> None:
        """Test saving a script produces JSON and Markdown files."""
        with tempfile.TemporaryDirectory() as tmp:
            scenes = [
                ScienceScene(
                    chapter="C1", chapter_index=0, scene_index=0,
                    title="S1", narration_hi="Test.",
                    on_screen_text_hi="T1", visual_prompt="V1",
                    duration_seconds=25,
                )
            ]
            script = ScienceStoryScript(
                title="Disk Test",
                topic="Test Topic",
                tagline="Testing disk save",
                chapters=["C1"],
                scenes=scenes,
            )
            paths = save_script_to_disk(script, tmp)
            self.assertIn("json", paths)
            self.assertIn("markdown", paths)
            json_path = Path(paths["json"])
            md_path = Path(paths["markdown"])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            # Validate the JSON roundtrip
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["title"], "Disk Test")

    def test_save_script_slug_limits(self) -> None:
        """Test that long topic names are truncated in directory names."""
        with tempfile.TemporaryDirectory() as tmp:
            scenes = [
                ScienceScene(
                    chapter="C1", chapter_index=0, scene_index=0,
                    title="S1", narration_hi="Test.",
                    on_screen_text_hi="T1", visual_prompt="V1",
                    duration_seconds=25,
                )
            ]
            script = ScienceStoryScript(
                title="A Very Long Title That Should Be Truncated For The Directory Name",
                topic="A very long topic name that should be truncated for the directory name to ensure it fits",
                tagline="Testing",
                chapters=["C1"],
                scenes=scenes,
            )
            paths = save_script_to_disk(script, tmp)
            json_path = Path(paths["json"])
            # The workspace directory name should be truncated to 48 chars + suffixes
            self.assertLessEqual(len(json_path.parent.name), 48)


if __name__ == "__main__":
    unittest.main()
