import json
import tempfile
import unittest
from pathlib import Path

from content_pipeline.bots.pm_video_agents import (
    SHORTS_AGENT,
    SHORTS_SUBSCRIBE_CTA,
    SUBSCRIBE_CTA,
    YOUTUBE_AGENT,
    agent_registry,
    create_daily_pm_video_batch,
    create_pm_video_workspace,
    daily_pm_video_topics,
)
from content_pipeline.bots.prompt_pack import create_prompt_pack
from content_pipeline.bots.pm_video_templates import (
    PM_COURSE_TEMPLATE,
    list_pm_video_templates,
    select_pm_video_template,
)
from content_pipeline.bots.pm_slide_router import build_slide_plan
from content_pipeline.bots.policy import video_sha256
from content_pipeline.bots.youtube import review_youtube_upload_readiness
from content_pipeline.content_history import ContentHistory, record_history_entry


class PMVideoAgentsTest(unittest.TestCase):
    def test_two_agents_share_the_same_prompt(self) -> None:
        registry = agent_registry()

        self.assertEqual(len(registry), 2)
        self.assertEqual(registry[0]["shared_prompt"], registry[1]["shared_prompt"])
        self.assertEqual(registry[0]["output_folder"], "shorts")
        self.assertEqual(registry[1]["output_folder"], "youtubeVideo")

    def test_template_catalog_has_many_variants_and_course_template_is_fixed(self) -> None:
        templates = list_pm_video_templates()

        self.assertGreaterEqual(len(templates), 25)
        self.assertEqual(select_pm_video_template("PMP 2026 readiness", "2026-05-31", "course"), PM_COURSE_TEMPLATE)
        self.assertEqual(
            select_pm_video_template("PMP 2026 readiness", "2026-05-31", "random"),
            select_pm_video_template("PMP 2026 readiness", "2026-05-31", "random"),
        )
        self.assertIn(
            select_pm_video_template("PMP 2026 readiness", "2026-05-31", "random").template_id,
            [template.template_id for template in templates],
        )

    def test_prompt_pack_writes_docx_documents_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            paths = create_prompt_pack(
                "Why project managers must master prompt engineering to survive the AI revolution",
                day="2026-05-29",
                output_dir=output,
            )
            manifest = output / "prompt_packs" / "2026-05-29"
            self.assertTrue(all(path.exists() for path in paths))
            docx_files = list(manifest.rglob("*.docx"))
            self.assertEqual(len(docx_files), 2)
            self.assertIn("prompt_pack.json", {path.name for path in paths})
            self.assertIn("prompt_pack.md", {path.name for path in paths})
            self.assertGreater(docx_files[0].stat().st_size, 1000)

    def test_slide_plan_uses_cinematic_image_prompt_formula(self) -> None:
        plan = build_slide_plan(
            topic="Agile metrics in the AI era: cycle time, escaped defects, and delivery confidence",
            day="2026-05-29",
            aspect="landscape",
            total_slides=35,
            template_mode="random",
            max_dimension=2048,
            max_bytes=5 * 1024 * 1024,
        )

        first_prompt = plan.slides[0].image_prompt
        final_prompt = plan.slides[-1].image_prompt

        self.assertIn("Hero scene, bold YouTube learning video cover", first_prompt)
        self.assertIn('Renderer-only headline: "AGILE METRICS IN THE AI ERA"', first_prompt)
        self.assertIn('Renderer-only hook: "The PM AI question"', first_prompt)
        self.assertIn("Absolutely no large readable text", first_prompt)
        self.assertIn("Cycle Time represented by a futuristic precision clock", first_prompt)
        self.assertIn("Escaped Defects represented by a glowing software bug", first_prompt)
        self.assertIn("Delivery Confidence represented by a shield", first_prompt)
        self.assertIn("NEXT STEP: ENGAGE WITH THE COURSE!", final_prompt)

    def test_shorts_agent_creates_dynamic_episode_with_cta(self) -> None:
        episode = SHORTS_AGENT.create_episode(
            "AI agents inside Jira for Scrum Masters",
            "2026-05-28",
            1,
        )

        self.assertEqual(episode.aspect, "shorts")
        self.assertEqual(episode.width, 1080)
        self.assertEqual(episode.height, 1920)
        self.assertGreaterEqual(episode.duration_seconds, 65)
        self.assertLessEqual(episode.duration_seconds, 80)
        self.assertEqual(len(episode.clips), 10)
        self.assertTrue(all(6 <= clip.duration_seconds <= 12 for clip in episode.clips))
        self.assertGreater(episode.clips[0].duration_seconds, episode.clips[1].duration_seconds)
        self.assertGreater(episode.clips[-1].duration_seconds, episode.clips[1].duration_seconds)
        self.assertGreaterEqual(max(clip.duration_seconds for clip in episode.clips[1:-1]), 7)
        self.assertIn(SHORTS_SUBSCRIBE_CTA, episode.clips[-1].narration)

    def test_youtube_agent_creates_5_to_8_minute_episode_with_cta(self) -> None:
        episode = YOUTUBE_AGENT.create_episode(
            "Microsoft Copilot for PMO reporting",
            "2026-05-28",
            1,
        )

        self.assertEqual(episode.aspect, "landscape")
        self.assertEqual(episode.width, 1280)
        self.assertEqual(episode.height, 720)
        self.assertGreaterEqual(episode.duration_seconds, 300)
        self.assertLessEqual(episode.duration_seconds, 480)
        self.assertEqual(len(episode.clips), 35)
        self.assertTrue(all(3 <= clip.duration_seconds <= 15 for clip in episode.clips))
        self.assertIn("subscribe", episode.clips[-1].narration.lower())
        self.assertIn("hit the bell", episode.clips[-1].narration.lower())
        self.assertGreaterEqual(len({clip.template_layout for clip in episode.clips}), 3)
        self.assertTrue(all(clip.template_id for clip in episode.clips))

    def test_workspace_writes_thumbnail_doc_subtitles_and_metadata(self) -> None:
        episode = SHORTS_AGENT.create_episode(
            "PMI Infinity and AI governance",
            "2026-05-28",
            1,
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            paths = create_pm_video_workspace(
                output,
                SHORTS_AGENT,
                episode,
                youtube_channel_url="https://www.youtube.com/@Lalitsingh-ge6js",
            )
            root = output / "shorts" / "2026-05-28" / episode.episode_id

            self.assertTrue(all(path.exists() for path in paths))
            self.assertTrue((root / "episode.json").exists())
            self.assertTrue((root / "thumbnail" / "metadata.doc").exists())
            self.assertTrue((root / "thumbnail" / "thumbnail.svg").exists())
            self.assertTrue((root / "thumbnail" / "subtitles.srt").exists())
            self.assertTrue((root / "video" / "subtitles.srt").exists())
            self.assertTrue((root / "publish" / "linkedin_post.md").exists())
            self.assertTrue((root / "publish" / "linkedin_post.json").exists())
            self.assertTrue((root / "publish" / "telegram_message.txt").exists())
            self.assertTrue((root / "slide_plan.json").exists())
            self.assertEqual(episode.visual_template_id, json.loads((root / "episode.json").read_text(encoding="utf-8"))["visual_template_id"])
            self.assertIn(
                "https://www.youtube.com/@Lalitsingh-ge6js",
                (root / "publish" / "linkedin_post.json").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Next step: open and publish the video.",
                (root / "publish" / "telegram_message.txt").read_text(encoding="utf-8"),
            )
            self.assertTrue(
                (output / "daily" / "2026-05-28" / "publish" / "linkedin_video_post.png").exists()
                or (output / "daily" / "2026-05-28" / "publish" / "linkedin_video_post.svg").exists()
            )
            self.assertIn(SUBSCRIBE_CTA, (root / "thumbnail" / "metadata.doc").read_text(encoding="utf-8"))

    def test_youtube_upload_preflight_approves_matching_review_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            video = root / "episode_review.mp4"
            video.write_bytes(b"fake mp4 bytes")
            thumbnail_dir = root / "thumbnail"
            thumbnail_dir.mkdir(parents=True, exist_ok=True)
            (thumbnail_dir / "thumbnail.svg").write_text("<svg></svg>", encoding="utf-8")
            description = root / "youtube_metadata.md"
            description.write_text("Disclosure: AI-generated visuals or narration may be used.", encoding="utf-8")
            report = {
                "title": "Test PM video",
                "video_file": str(video),
                "video_sha256": video_sha256(video),
                "status": "approved_for_upload",
                "blockers": [],
            }

            readiness = review_youtube_upload_readiness(
                title="Test PM video",
                video_path=video,
                description_text=description.read_text(encoding="utf-8"),
                policy_report=report,
                thumbnail_path=thumbnail_dir / "thumbnail.svg",
            )

            self.assertEqual(readiness["status"], "approved_for_upload")
            self.assertFalse(readiness["blockers"])
            self.assertGreaterEqual(sum(1 for check in readiness["checks"] if check["passed"]), 5)

    def test_workspace_stores_creator_voice_sample_reference(self) -> None:
        episode = SHORTS_AGENT.create_episode(
            "AI agents inside Jira for Scrum Masters",
            "2026-05-28",
            1,
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            voice_sample = Path(temporary_dir) / "voice_sample.ogg"
            voice_sample.write_bytes(b"sample voice bytes")
            paths = create_pm_video_workspace(
                output,
                SHORTS_AGENT,
                episode,
                voice_sample_path=voice_sample,
            )
            root = output / "shorts" / "2026-05-28" / episode.episode_id

            self.assertIn(root / "audio" / "reference" / "creator_voice_sample.ogg", paths)
            self.assertTrue((root / "audio" / "reference" / "creator_voice_sample.ogg").exists())
            self.assertTrue((root / "audio" / "reference" / "audio_manifest.json").exists())
            self.assertTrue((root / "audio" / "reference" / "audio_status.html").exists())
            audio_manifest = json.loads((root / "audio" / "reference" / "audio_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(audio_manifest["voice_sample_reference"], str(voice_sample))
            self.assertEqual(audio_manifest["voice_sample_copied"], True)
            self.assertIn(
                "creator voice reference",
                (root / "audio" / "reference" / "voice_reference.md").read_text(encoding="utf-8"),
            )

    def test_daily_batch_creates_two_shorts_two_youtube_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            paths = create_daily_pm_video_batch(output, "2026-05-28")
            manifest_path = output / "pm_video_agents" / "2026-05-28" / "daily_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(all(path.exists() for path in paths))
            self.assertEqual(len(manifest["episodes"]), 4)
            self.assertEqual(
                len(list((output / "shorts" / "2026-05-28").glob("*"))),
                2,
            )
            self.assertEqual(
                len(list((output / "youtubeVideo" / "2026-05-28").glob("*"))),
                2,
            )
            self.assertEqual(manifest["closing_cta"], SUBSCRIBE_CTA)
            self.assertEqual(manifest["slide_agent_count"], 4)

    def test_daily_topics_are_deterministic_and_distinct(self) -> None:
        topics = daily_pm_video_topics("2026-05-28", total=4)

        self.assertEqual(topics, daily_pm_video_topics("2026-05-28", total=4))
        self.assertEqual(len(topics), 4)
        self.assertEqual(len(set(topics)), 4)

    def test_daily_topics_skip_history_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            record_history_entry(
                output,
                date="2026-05-27",
                kind="youtube_publish",
                topic="AI agents inside Jira: what changes for Scrum Masters and delivery managers",
                title="Test",
                platform="youtube",
                reference="abc123",
                source="test",
            )
            history = ContentHistory.load(output)
            topics = daily_pm_video_topics(
                "2026-05-28",
                total=4,
                used_topics=history.topic_keys(),
            )

            self.assertNotIn(
                "AI agents inside Jira: what changes for Scrum Masters and delivery managers",
                topics,
            )

    def test_daily_topics_skip_close_title_variants_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            record_history_entry(
                output,
                date="2026-05-27",
                kind="youtube_publish",
                topic="PMI Infinity and AI governance - 5 Things PMs Should Know",
                title="PMI Infinity and AI governance - 5 Things PMs Should Know",
                platform="youtube",
                reference="abc123",
                source="test",
            )
            history = ContentHistory.load(output)
            topics = daily_pm_video_topics(
                "2026-05-29",
                total=4,
                used_topics=history.topic_keys(),
            )

            self.assertNotIn(
                "PMI Infinity and AI governance: how project managers should ask better questions",
                topics,
            )

    def test_daily_topics_skip_shortened_title_variants_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            record_history_entry(
                output,
                date="2026-05-27",
                kind="youtube_publish",
                topic="PMP 2026 readiness | PM AI Playbook",
                title="PMP 2026 readiness | PM AI Playbook",
                platform="youtube",
                reference="abc123",
                source="test",
            )
            history = ContentHistory.load(output)
            topics = daily_pm_video_topics(
                "2026-05-29",
                total=4,
                used_topics=history.topic_keys(),
            )

            self.assertNotIn(
                "PMP 2026 readiness: skills project managers should build before the exam refresh",
                topics,
            )


if __name__ == "__main__":
    unittest.main()
