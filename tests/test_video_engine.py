"""Tests for the clip → episode → compilation video engine."""

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_pipeline.bots.image import MockImageProvider
from content_pipeline.bots.video_engine import (
    VideoClip,
    VideoCompilation,
    VideoEpisode,
    assemble_episode,
    assert_shorts_publish_allowed,
    create_clip_plan,
    create_compilation_workspace,
    create_episode_workspace,
    generate_auto_2_5d_clips,
    record_shorts_publish,
    shorts_publish_metadata,
)


class ClipPlanTest(unittest.TestCase):
    """create_clip_plan returns structurally correct episodes."""

    def test_adult_defaults_to_mixed_source_types(self) -> None:
        episode = create_clip_plan(
            topic="Risk management in Agile delivery",
            audience="adult",
            aspect="shorts",
        )

        self.assertEqual(episode.aspect, "shorts")
        self.assertEqual(episode.width, 720)
        self.assertEqual(episode.height, 1280)
        self.assertGreater(len(episode.clips), 0)
        self.assertIn("2_5d_image", {c.visual_mode for c in episode.clips})
        self.assertIn("motion_video", {c.visual_mode for c in episode.clips})
        self.assertIn("auto_2_5d", {c.source_type for c in episode.clips})
        self.assertIn("manual", {c.source_type for c in episode.clips})
        for clip in episode.clips:
            self.assertTrue(clip.id.startswith("scene_"))
            self.assertTrue(3 <= clip.duration_seconds <= 15)

    def test_kid_uses_motion_video_only(self) -> None:
        episode = create_clip_plan(
            topic="Telling the truth",
            audience="kid",
            aspect="landscape",
        )

        self.assertEqual(episode.aspect, "landscape")
        self.assertEqual(episode.width, 1280)
        self.assertEqual(episode.height, 720)
        self.assertGreater(len(episode.clips), 0)
        self.assertTrue(all(c.visual_mode == "motion_video" for c in episode.clips))
        self.assertTrue(all(c.source_type == "manual" for c in episode.clips))

    def test_target_duration_is_respected(self) -> None:
        episode = create_clip_plan(
            topic="Sprint retrospectives",
            audience="adult",
            target_duration_seconds=30,
        )

        self.assertAlmostEqual(episode.duration_seconds, 30, delta=10)

    def test_clip_durations_are_within_bounds(self) -> None:
        episode = create_clip_plan(
            topic="Daily stand-ups",
            audience="adult",
            target_duration_seconds=150,
        )

        for clip in episode.clips:
            self.assertTrue(3 <= clip.duration_seconds <= 15)

    def test_episode_includes_youtube_metadata(self) -> None:
        episode = create_clip_plan(
            topic="User story mapping",
            audience="adult",
            aspect="landscape",
        )

        self.assertTrue(len(episode.youtube_title) > 0)
        self.assertTrue(len(episode.youtube_description) > 0)
        self.assertTrue(len(episode.hashtags) > 0)
        self.assertIn("#AIAnimation", episode.hashtags)
        self.assertTrue(episode.episode_id.startswith(episode.episode_id.split("_")[0]))

    def test_aspect_validation(self) -> None:
        with self.assertRaises(ValueError):
            create_clip_plan(
                topic="Test",
                aspect="unknown",  # type: ignore[arg-type]
            )

    def test_empty_audience_defaults_error(self) -> None:
        # _adult_clips is the default branch; kid clips only when explicitly "kid"
        episode = create_clip_plan(
            topic="Test topic",
            audience="adult",
        )
        self.assertIn("auto_2_5d", {c.source_type for c in episode.clips})


class EpisodeWorkspaceTest(unittest.TestCase):
    """create_episode_workspace writes the expected file structure."""

    def test_all_workspace_files_are_created(self) -> None:
        episode = create_clip_plan(
            topic="Test episode",
            audience="adult",
            aspect="shorts",
            episode_date="2026-06-01",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            paths = create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id

            self.assertTrue(all(path.exists() for path in paths))
            self.assertTrue((root / "episode.json").exists())
            self.assertTrue((root / "story_script.md").exists())
            self.assertTrue((root / "scene_prompts.json").exists())
            self.assertTrue((root / "clip_drop_guide.md").exists())
            self.assertTrue((root / "youtube_metadata.md").exists())
            self.assertTrue((root / "ui" / "index.html").exists())
            self.assertTrue((root / "clips" / "inbox" / ".gitkeep").exists())
            self.assertTrue((root / "clips" / "auto_2_5d").exists())
            self.assertTrue((root / "video").exists())

    def test_episode_json_is_valid(self) -> None:
        episode = create_clip_plan(
            topic="Valid JSON episode",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id
            data = json.loads((root / "episode.json").read_text(encoding="utf-8"))

        self.assertEqual(data["episode_id"], episode.episode_id)
        self.assertEqual(len(data["clips"]), len(episode.clips))
        self.assertEqual(data["aspect"], "shorts")

    def test_story_script_includes_narration(self) -> None:
        episode = create_clip_plan(
            topic="Narration test",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id
            script = (root / "story_script.md").read_text(encoding="utf-8")

        self.assertIn("Narration test", script)
        self.assertIn("shorts", script)
        for clip in episode.clips:
            self.assertIn(clip.expected_file, script)

    def test_scene_prompts_contain_expected_keys(self) -> None:
        episode = create_clip_plan(
            topic="Prompt test",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id
            prompts = json.loads((root / "scene_prompts.json").read_text(encoding="utf-8"))

        self.assertEqual(len(prompts), len(episode.clips))
        for prompt, clip in zip(prompts, episode.clips):
            self.assertEqual(prompt["clip"], clip.id)
            self.assertEqual(prompt["source_type"], clip.source_type)
            self.assertEqual(prompt["expected_file"], clip.expected_file)

    def test_clip_drop_guide_mentions_manual_vs_auto(self) -> None:
        episode = create_clip_plan(
            topic="Drop guide",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id
            guide = (root / "clip_drop_guide.md").read_text(encoding="utf-8")

        auto_count = sum(1 for c in episode.clips if c.source_type == "auto_2_5d")
        manual_count = sum(1 for c in episode.clips if c.source_type == "manual")
        if auto_count:
            self.assertIn("Auto 2.5D clips", guide)
        if manual_count:
            self.assertIn("Manual clips", guide)

    def test_dashboard_html_renders(self) -> None:
        episode = create_clip_plan(
            topic="Dashboard test",
            audience="adult",
            aspect="landscape",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id
            html = (root / "ui" / "index.html").read_text(encoding="utf-8")

        self.assertIn("Dashboard test", html)
        self.assertIn("landscape - 1280x720", html)
        self.assertIn("Copy Metadata", html)
        self.assertIn("Copy Prompt", html)

    def test_kid_workspace_labels_all_clips_manual(self) -> None:
        episode = create_clip_plan(
            topic="Kid topic",
            audience="kid",
        )

        self.assertTrue(all(c.source_type == "manual" for c in episode.clips))


class CompilationWorkspaceTest(unittest.TestCase):
    """create_compilation_workspace writes a valid manifest."""

    def test_compilation_manifest_is_written(self) -> None:
        compilation = VideoCompilation(
            compilation_id="test_comp_001",
            title="My Compilation",
            description="A test compilation",
            episode_ids=["ep_001", "ep_002", "ep_003"],
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            path = create_compilation_workspace(output, compilation)
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["compilation_id"], "test_comp_001")
        self.assertEqual(data["episode_ids"], ["ep_001", "ep_002", "ep_003"])
        self.assertEqual(data["transition_duration_seconds"], 2)

    def test_compilation_workspace_uses_custom_transition(self) -> None:
        compilation = VideoCompilation(
            compilation_id="custom_transition",
            title="With Transition",
            description="Testing transition duration",
            episode_ids=["ep_001"],
            transition_duration_seconds=5,
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            path = create_compilation_workspace(output, compilation)
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["transition_duration_seconds"], 5)


class AssembleEpisodeTest(unittest.TestCase):
    """assemble_episode error handling when assets are missing."""

    def test_assemble_reports_missing_manual_clips_for_adult(self) -> None:
        """Adult plan has manual clips; assembler reports those first."""
        episode = create_clip_plan(
            topic="Missing clips",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id

            with patch("content_pipeline.bots.video_engine.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self.assertRaises(FileNotFoundError) as ctx:
                    assemble_episode(root)

            error = str(ctx.exception)
            # Adult plan has scene_03 as the first manual clip
            self.assertIn("scene_03.mp4", error)
            self.assertIn("clips/inbox", error)

    def test_assemble_requires_ffmpeg(self) -> None:
        episode = create_clip_plan(
            topic="No ffmpeg",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id

            with patch("content_pipeline.bots.video_engine.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "FFmpeg is required"):
                    assemble_episode(root)

    def test_assemble_reports_missing_manual_clips(self) -> None:
        episode = create_clip_plan(
            topic="Missing manual clips",
            audience="kid",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id

            with patch("content_pipeline.bots.video_engine.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self.assertRaises(FileNotFoundError) as ctx:
                    assemble_episode(root)

            error = str(ctx.exception)
            self.assertIn("scene_01.mp4", error)
            self.assertIn("clips/inbox", error)


class GenerateAutoClipsTest(unittest.TestCase):
    """generate_auto_2_5d_clips error handling."""

    def test_generate_requires_ffmpeg(self) -> None:
        episode = create_clip_plan(
            topic="Auto gen",
            audience="adult",
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            provider = MockImageProvider()

            with patch("content_pipeline.bots.video_engine.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "FFmpeg is required"):
                    generate_auto_2_5d_clips(episode, provider, output)


class VideoClipModelTest(unittest.TestCase):
    """VideoClip model validation."""

    def test_from_dict_validates_duration(self) -> None:
        with self.assertRaises(ValueError):
            VideoClip.from_dict({
                "id": "scene_01",
                "title": "Too long",
                "duration_seconds": 30,
                "narration": "Test",
                "on_screen_text": "Test",
                "visual_mode": "2_5d_image",
                "prompt": "A test prompt",
                "source_type": "auto_2_5d",
                "expected_file": "scene_01.mp4",
            })

        with self.assertRaises(ValueError):
            VideoClip.from_dict({
                "id": "scene_01",
                "title": "Too short",
                "duration_seconds": 1,
                "narration": "Test",
                "on_screen_text": "Test",
                "visual_mode": "2_5d_image",
                "prompt": "A test prompt",
                "source_type": "auto_2_5d",
                "expected_file": "scene_01.mp4",
            })

    def test_from_dict_validates_visual_mode(self) -> None:
        with self.assertRaises(ValueError):
            VideoClip.from_dict({
                "id": "scene_01",
                "title": "Bad mode",
                "duration_seconds": 5,
                "narration": "Test",
                "on_screen_text": "Test",
                "visual_mode": "invalid_mode",
                "prompt": "A test prompt",
                "source_type": "auto_2_5d",
                "expected_file": "scene_01.mp4",
            })

    def test_from_dict_validates_source_type(self) -> None:
        with self.assertRaises(ValueError):
            VideoClip.from_dict({
                "id": "scene_01",
                "title": "Bad source",
                "duration_seconds": 5,
                "narration": "Test",
                "on_screen_text": "Test",
                "visual_mode": "2_5d_image",
                "prompt": "A test prompt",
                "source_type": "invalid_source",
                "expected_file": "scene_01.mp4",
            })

    def test_valid_clip_round_trips(self) -> None:
        clip = VideoClip.from_dict({
            "id": "scene_01",
            "title": "Opening",
            "duration_seconds": 7,
            "narration": "A spoken line.",
            "on_screen_text": "Visible text",
            "visual_mode": "2_5d_image",
            "prompt": "Cinematic scene of mountains",
            "source_type": "auto_2_5d",
            "expected_file": "scene_01.mp4",
        })

        self.assertEqual(clip.id, "scene_01")
        self.assertEqual(clip.duration_seconds, 7)
        self.assertEqual(clip.visual_mode, "2_5d_image")
        self.assertEqual(clip.source_type, "auto_2_5d")
        self.assertEqual(clip.expected_file, "scene_01.mp4")


class VideoEpisodeModelTest(unittest.TestCase):
    """VideoEpisode model validation."""

    def test_from_dict_validates_aspect(self) -> None:
        with self.assertRaises(ValueError):
            VideoEpisode.from_dict({
                "episode_id": "ep_001",
                "title": "Bad aspect",
                "description": "Test",
                "aspect": "square",
                "clips": [
                    {
                        "id": "scene_01",
                        "title": "Scene 1",
                        "duration_seconds": 5,
                        "narration": "Test",
                        "on_screen_text": "Test",
                        "visual_mode": "2_5d_image",
                        "prompt": "Prompt",
                        "source_type": "auto_2_5d",
                        "expected_file": "scene_01.mp4",
                    }
                ],
                "youtube_title": "Title",
                "youtube_description": "Description",
                "hashtags": ["#Test"],
            })

    def test_from_dict_auto_sets_dimensions_for_shorts(self) -> None:
        episode = VideoEpisode.from_dict({
            "episode_id": "ep_001",
            "title": "Shorts test",
            "description": "Test",
            "aspect": "shorts",
            "clips": [
                {
                    "id": "scene_01",
                    "title": "Scene 1",
                    "duration_seconds": 5,
                    "narration": "Test",
                    "on_screen_text": "Test",
                    "visual_mode": "2_5d_image",
                    "prompt": "Prompt",
                    "source_type": "auto_2_5d",
                    "expected_file": "scene_01.mp4",
                }
            ],
            "youtube_title": "Title",
            "youtube_description": "Description",
            "hashtags": ["#Test"],
        })

        self.assertEqual(episode.width, 720)
        self.assertEqual(episode.height, 1280)

    def test_from_dict_auto_sets_dimensions_for_landscape(self) -> None:
        episode = VideoEpisode.from_dict({
            "episode_id": "ep_001",
            "title": "Landscape test",
            "description": "Test",
            "aspect": "landscape",
            "clips": [
                {
                    "id": "scene_01",
                    "title": "Scene 1",
                    "duration_seconds": 5,
                    "narration": "Test",
                    "on_screen_text": "Test",
                    "visual_mode": "2_5d_image",
                    "prompt": "Prompt",
                    "source_type": "auto_2_5d",
                    "expected_file": "scene_01.mp4",
                }
            ],
            "youtube_title": "Title",
            "youtube_description": "Description",
            "hashtags": ["#Test"],
        })

        self.assertEqual(episode.width, 1280)
        self.assertEqual(episode.height, 720)

    def test_duration_seconds_property(self) -> None:
        episode = VideoEpisode.from_dict({
            "episode_id": "ep_001",
            "title": "Duration test",
            "description": "Test",
            "aspect": "shorts",
            "clips": [
                {
                    "id": "scene_01",
                    "title": "Scene 1",
                    "duration_seconds": 5,
                    "narration": "Test",
                    "on_screen_text": "Test",
                    "visual_mode": "2_5d_image",
                    "prompt": "Prompt",
                    "source_type": "auto_2_5d",
                    "expected_file": "scene_01.mp4",
                },
                {
                    "id": "scene_02",
                    "title": "Scene 2",
                    "duration_seconds": 8,
                    "narration": "Test",
                    "on_screen_text": "Test",
                    "visual_mode": "motion_video",
                    "prompt": "Prompt",
                    "source_type": "manual",
                    "expected_file": "scene_02.mp4",
                },
            ],
            "youtube_title": "Title",
            "youtube_description": "Description",
            "hashtags": ["#Test"],
        })

        self.assertEqual(episode.duration_seconds, 13)


class VideoCompilationModelTest(unittest.TestCase):
    """VideoCompilation model validation."""

    def test_from_dict_parses_correctly(self) -> None:
        compilation = VideoCompilation.from_dict({
            "compilation_id": "comp_001",
            "title": "Big Compilation",
            "description": "10 episodes in one",
            "episode_ids": ["ep_01", "ep_02", "ep_03"],
            "transition_duration_seconds": 3,
        })

        self.assertEqual(compilation.compilation_id, "comp_001")
        self.assertEqual(len(compilation.episode_ids), 3)
        self.assertEqual(compilation.transition_duration_seconds, 3)

    def test_from_dict_defaults_transition(self) -> None:
        compilation = VideoCompilation.from_dict({
            "compilation_id": "comp_002",
            "title": "Default Transition",
            "description": "Should use default",
            "episode_ids": ["ep_01"],
        })

        self.assertEqual(compilation.transition_duration_seconds, 2)

    def test_from_dict_validates_episode_ids(self) -> None:
        with self.assertRaises(ValueError):
            VideoCompilation.from_dict({
                "compilation_id": "comp_003",
                "title": "Empty IDs",
                "description": "Should fail",
                "episode_ids": [],
            })

    def test_estimated_duration_returns_zero_for_no_episodes(self) -> None:
        compilation = VideoCompilation(
            compilation_id="empty",
            title="Empty",
            description="Empty compilation",
            episode_ids=[],
        )

        self.assertEqual(compilation.estimated_duration_seconds, 0)

    def test_as_dict_round_trips(self) -> None:
        original = VideoCompilation(
            compilation_id="round_trip",
            title="Round Trip",
            description="Testing round trip",
            episode_ids=["ep_01", "ep_02"],
        )

        data = original.as_dict()
        restored = VideoCompilation.from_dict(data)

        self.assertEqual(restored.compilation_id, original.compilation_id)
        self.assertEqual(restored.episode_ids, original.episode_ids)


class SubtitleTest(unittest.TestCase):
    """SRT subtitle generation from episode clips."""

    def test_srt_has_correct_structure(self) -> None:
        episode = create_clip_plan(
            topic="SRT test",
            audience="adult",
            target_duration_seconds=30,
        )

        # Access the subtitle generation through assemble_episode
        # by examining episode.json
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            create_episode_workspace(output, episode)
            root = output / "video_episodes" / episode.episode_id

            # Re-read the episode and check subtitles from the engine
            from content_pipeline.bots.video_engine import _subtitle_srt
            srt = _subtitle_srt(episode)

        lines = srt.strip().split("\n")
        self.assertTrue(lines[0].isdigit())  # first line is a subtitle number
        self.assertIn("-->", lines[1])  # second line has timestamp
        self.assertIn("00:00:00,000", lines[1])  # starts at zero


class ShortsDistributionTest(unittest.TestCase):
    """shorts_publish_metadata, record_shorts_publish, assert_shorts_publish_allowed."""

    def test_shorts_publish_metadata_youtube(self) -> None:
        episode = create_clip_plan(
            topic="Shorts metadata test",
            audience="adult",
            aspect="shorts",
            target_duration_seconds=30,
        )
        meta = shorts_publish_metadata(episode, platform="youtube")

        self.assertEqual(meta.platform, "youtube")
        self.assertEqual(meta.episode_id, episode.episode_id)
        self.assertEqual(meta.title, episode.youtube_title)
        self.assertEqual(meta.description, episode.youtube_description)
        self.assertEqual(meta.hashtags, episode.hashtags)
        self.assertTrue("#AIAnimation" in meta.hashtags)

    def test_shorts_publish_metadata_instagram(self) -> None:
        episode = create_clip_plan(
            topic="Instagram metadata test",
            audience="adult",
            aspect="shorts",
            target_duration_seconds=30,
        )
        meta = shorts_publish_metadata(episode, platform="instagram")

        self.assertEqual(meta.platform, "instagram")
        self.assertEqual(meta.episode_id, episode.episode_id)
        self.assertTrue(len(meta.description) > 0)
        self.assertLessEqual(len(meta.description), 2200)
        for tag in episode.hashtags:
            self.assertIn(tag, meta.description)

    def test_shorts_publish_metadata_rejects_landscape(self) -> None:
        episode = create_clip_plan(
            topic="Landscape episode",
            audience="adult",
            aspect="landscape",
        )
        with self.assertRaises(ValueError):
            shorts_publish_metadata(episode)

    def test_shorts_publish_metadata_rejects_over_60s(self) -> None:
        # Manually construct an episode over 60s since create_clip_plan caps clips at 15s
        long_clips = [
            VideoClip(
                id=f"scene_{i:02d}",
                title=f"Long clip {i}",
                duration_seconds=15,
                narration="Test narration.",
                on_screen_text="Test",
                visual_mode="2_5d_image",
                prompt="A test prompt",
                source_type="auto_2_5d",
                expected_file=f"scene_{i:02d}.mp4",
            )
            for i in range(1, 6)  # 5 clips × 15s = 75s
        ]
        episode = VideoEpisode(
            episode_id="too_long_ep",
            title="Too Long",
            description="An episode that is too long for shorts",
            aspect="shorts",
            width=720,
            height=1280,
            clips=long_clips,
            youtube_title="Too Long",
            youtube_description="Too long description",
            hashtags=["#Test"],
        )
        self.assertGreater(episode.duration_seconds, 60)
        with self.assertRaises(ValueError):
            shorts_publish_metadata(episode)

    def test_record_shorts_publish_creates_receipt(self) -> None:
        import tempfile
        from datetime import date

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            receipt = record_shorts_publish(
                output,
                episode_id="test_ep_001",
                platform="youtube",
                media_id="yt_video_abc123",
            )

        self.assertEqual(receipt["platform"], "youtube")
        self.assertEqual(receipt["episode_id"], "test_ep_001")
        self.assertEqual(receipt["media_id"], "yt_video_abc123")
        self.assertIn("published_at", receipt)

    def test_assert_shorts_publish_allowed_raises_on_existing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            record_shorts_publish(output, "dup_ep", "youtube", "existing_id")

            with self.assertRaises(RuntimeError):
                assert_shorts_publish_allowed(output, "dup_ep", "youtube")

    def test_assert_shorts_publish_allowed_passes_with_force(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            record_shorts_publish(output, "force_ep", "youtube", "existing_id")

            # Should not raise with force=True
            assert_shorts_publish_allowed(output, "force_ep", "youtube", force=True)

    def test_assert_shorts_publish_allowed_passes_when_no_receipt(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            # No receipt written yet — should not raise
            assert_shorts_publish_allowed(output, "new_ep", "youtube")

    def test_shorts_publish_metadata_includes_video_path(self) -> None:
        episode = create_clip_plan(
            topic="Video path test",
            audience="adult",
            aspect="shorts",
            target_duration_seconds=30,
        )
        video_path = Path("/tmp/test_episode.mp4")
        meta = shorts_publish_metadata(episode, video_path=video_path)

        self.assertEqual(meta.video_path, "/tmp/test_episode.mp4")

    def test_shorts_publish_metadata_instagram_caption_crop(self) -> None:
        episode = create_clip_plan(
            topic="Long caption test",
            audience="adult",
            aspect="shorts",
            target_duration_seconds=30,
        )
        # Force a very long description
        long_desc = "A" * 3000
        episode = dataclasses.replace(
            episode, youtube_description=long_desc
        )

        meta = shorts_publish_metadata(episode, platform="instagram")
        self.assertLessEqual(len(meta.description), 2200)


if __name__ == "__main__":
    unittest.main()
