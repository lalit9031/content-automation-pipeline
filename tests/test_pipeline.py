import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from content_pipeline.bots.canva import CanvaAuth, render_canva_video
from content_pipeline.bots.infographic import infographic_svg
from content_pipeline.bots.linkedin import (
    LinkedInClient,
    assert_publish_allowed,
    linkedin_share_payload,
    published_post_receipt,
    record_published_post,
)
from content_pipeline.bots.image import MockImageProvider
from content_pipeline.bots.krishna_agents import (
    agent_registry,
    bal_krishna_character_design_plan,
    bal_krishna_image_plan,
    character_motion_validation_protocol,
    generate_planned_images,
    initialize_agent_workspace,
    voice_source_policy,
    write_voice_selection,
)
from content_pipeline.bots.motion import (
    bal_krishna_environment_validation_plan,
    bal_krishna_validation_plan,
)
from content_pipeline.bots.policy import (
    PublicationDeclarations,
    assert_upload_approved,
    review_publication,
)
from content_pipeline.bots.prompt import OpenAIPromptProvider, _fit_long_form_duration
from content_pipeline.bots.video import (
    _assemble_video,
    long_form_scenes,
    scene_svg,
    scenes_for_package,
    subtitles_for_scenes,
)
from content_pipeline.bots.youtube import upload_youtube_video
from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage, LongFormVideoScript
from content_pipeline.pipeline import run_linkedin_mvp
from content_pipeline.storage import LocalDailyStorage


class PipelineTest(unittest.TestCase):
    def test_mock_mvp_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            result = run_linkedin_mvp("2026-05-26", Settings(output_dir=output))
            daily = output / "daily" / "2026-05-26"

            self.assertEqual(result["mode"], "mock")
            self.assertEqual(result["publishing"]["status"], "prepared")
            self.assertTrue((daily / "prompt.json").exists())
            self.assertTrue((daily / "images" / "image_square.svg").exists())
            self.assertTrue((daily / "images" / "image_portrait.svg").exists())
            self.assertTrue((daily / "images" / "linkedin_infographic.png").exists())

            payload = json.loads((daily / "publish" / "linkedin_payload.json").read_text())
            self.assertIn("#ProjectManagement", payload["hashtags"])
            self.assertEqual(payload["image_file"], "images/linkedin_infographic.png")
            self.assertEqual(payload["posting_target"], "personal_profile")
            self.assertEqual(payload["required_scope"], "w_member_social")

    def test_manifest_reports_live_when_a_live_provider_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            settings = Settings(output_dir=output, image_provider="mock", prompt_provider="openai")
            with patch("content_pipeline.pipeline.prompt_provider") as provider:
                provider.return_value.generate.return_value = ContentPackage.from_dict(
                    {
                        "date": "2026-05-26",
                        "topic": "Topic",
                        "image_prompt": "Illustration",
                        "linkedin_infographic": {
                            "headline": "Headline",
                            "subtitle": "Subtitle",
                            "left_panel": {"title": "Left", "points": ["A"]},
                            "right_panel": {"title": "Right", "points": ["B"]},
                            "takeaway_title": "Takeaway",
                            "takeaway_points": ["C"],
                            "workflow": ["Plan", "Done"],
                            "discussion_prompt": "Discuss?",
                        },
                        "video_script": {"hook": "Hook", "points": ["Point"], "cta": "CTA"},
                        "linkedin_caption": "Caption",
                        "hashtags": ["#ProjectManagement"],
                        "seo_title": "Title",
                        "seo_description": "Description",
                    }
                )
                result = run_linkedin_mvp("2026-05-26", settings)

            self.assertEqual(result["mode"], "live")
            self.assertEqual(result["providers"]["linkedin_infographic"], "template")

    def test_openai_provider_requests_structured_daily_package(self) -> None:
        captured = {}
        content = {
            "date": "2026-05-26",
            "topic": "A generated topic",
            "image_prompt": "A generated image prompt",
            "linkedin_infographic": {
                "headline": "Headline",
                "subtitle": "Subtitle",
                "left_panel": {"title": "Left", "points": ["Point"]},
                "right_panel": {"title": "Right", "points": ["Point"]},
                "takeaway_title": "Takeaway",
                "takeaway_points": ["Do this"],
                "workflow": ["Plan", "Done"],
                "discussion_prompt": "Your view?",
            },
            "video_script": {"hook": "Hook", "points": ["Point"], "cta": "CTA"},
            "linkedin_caption": "Caption",
            "hashtags": ["#AI"],
            "seo_title": "Title",
            "seo_description": "Description",
        }

        class FakeResponses:
            def create(self, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(output_text=json.dumps(content))

        class FakeOpenAI:
            def __init__(self, api_key):
                captured["api_key"] = api_key
                self.responses = FakeResponses()

        fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
        settings = Settings(
            output_dir=Path("output"),
            openai_api_key="test-key",
            openai_model="gpt-5.4-mini",
        )

        with patch.dict(sys.modules, {"openai": fake_module}):
            package = OpenAIPromptProvider(settings).generate("2026-05-26")

        self.assertEqual(package.topic, "A generated topic")
        self.assertEqual(captured["model"], "gpt-5.4-mini")
        self.assertEqual(captured["text"]["format"]["type"], "json_schema")
        self.assertTrue(captured["text"]["format"]["strict"])
        self.assertIn("Scrum Masters", captured["instructions"])
        self.assertIn("infographic", captured["instructions"])

    def test_linkedin_authorization_requests_personal_post_scope(self) -> None:
        settings = Settings(
            output_dir=Path("output"),
            linkedin_client_id="public-client-id",
            linkedin_redirect_uri="http://localhost:8080/callback",
        )

        url = LinkedInClient(settings).authorization_url("safe-state")

        self.assertIn("w_member_social", url)
        self.assertIn("openid+profile+email", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback", url)

    def test_canva_refresh_persists_rotated_single_use_token(self) -> None:
        response = types.SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "access_token": "access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 14400,
            },
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            dotenv_path = Path(temporary_dir) / ".env"
            dotenv_path.write_text(
                "CANVA_CLIENT_ID=client-id\nCANVA_REFRESH_TOKEN=old-refresh-token\n",
                encoding="utf-8",
            )
            settings = Settings(
                output_dir=Path(temporary_dir) / "output",
                canva_client_id="client-id",
                canva_client_secret="client-secret",
                canva_refresh_token="old-refresh-token",
                dotenv_path=dotenv_path,
            )
            with (
                patch("content_pipeline.bots.canva.requests.post", return_value=response),
                patch.dict(os.environ, {"CANVA_REFRESH_TOKEN": "old-refresh-token"}),
            ):
                self.assertEqual(CanvaAuth(settings).get_access_token(), "access-token")
                self.assertEqual(os.environ["CANVA_REFRESH_TOKEN"], "new-refresh-token")

            self.assertIn(
                "CANVA_REFRESH_TOKEN=new-refresh-token",
                dotenv_path.read_text(encoding="utf-8"),
            )

    def test_canva_render_reports_template_without_autofill_fields(self) -> None:
        settings = Settings(
            output_dir=Path("output"),
            canva_client_id="client-id",
            canva_client_secret="client-secret",
            canva_refresh_token="refresh-token",
            canva_brand_template_id="template-id",
        )
        with patch(
            "content_pipeline.bots.canva.get_brand_template_dataset", return_value={}
        ):
            with self.assertRaisesRegex(
                ValueError, "none of the expected text autofill fields"
            ):
                render_canva_video(
                    types.SimpleNamespace(date="2026-05-27"),
                    settings,
                    LocalDailyStorage(Path("output")),
                )

    def test_linkedin_post_payload_targets_member_image_post(self) -> None:
        package = ContentPackage.from_dict(
            {
                "date": "2026-05-26",
                "topic": "Topic",
                "image_prompt": "Image prompt",
                "linkedin_infographic": {
                    "headline": "AC vs DoD",
                    "subtitle": "Two useful checks",
                    "left_panel": {"title": "AC", "points": ["Right requirement"]},
                    "right_panel": {"title": "DoD", "points": ["Right quality"]},
                    "takeaway_title": "Use both",
                    "takeaway_points": ["Deliver confidently"],
                    "workflow": ["Refine", "Build", "Done"],
                    "discussion_prompt": "How does your team work?",
                },
                "video_script": {"hook": "Hook", "points": ["Point"], "cta": "CTA"},
                "linkedin_caption": "Caption",
                "hashtags": ["#AI", "#Automation"],
                "seo_title": "Title",
                "seo_description": "Description",
            }
        )

        payload = linkedin_share_payload("urn:li:person:abc", package, "urn:li:digitalmediaAsset:1")

        self.assertEqual(payload["author"], "urn:li:person:abc")
        self.assertEqual(
            payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"],
            "IMAGE",
        )
        self.assertIn("#AI", payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"])

    def test_infographic_svg_renders_structured_copy_exactly(self) -> None:
        package = ContentPackage.from_dict(
            {
                "date": "2026-05-26",
                "topic": "Topic",
                "image_prompt": "Supporting illustration",
                "linkedin_infographic": {
                    "headline": "Acceptance Criteria vs Definition of Done",
                    "subtitle": "Two delivery checks",
                    "left_panel": {"title": "Acceptance Criteria", "points": ["Feature outcome"]},
                    "right_panel": {"title": "Definition of Done", "points": ["Quality gate"]},
                    "takeaway_title": "Use both",
                    "takeaway_points": ["Reduce surprises"],
                    "workflow": ["Refine", "Build", "Review", "Done"],
                    "discussion_prompt": "What does your team check?",
                },
                "video_script": {"hook": "Hook", "points": ["Point"], "cta": "CTA"},
                "linkedin_caption": "Caption",
                "hashtags": ["#ProjectManagement"],
                "seo_title": "Title",
                "seo_description": "Description",
            }
        )

        svg = infographic_svg(package).decode("utf-8")

        self.assertIn("Acceptance Criteria vs Definition of", svg)
        self.assertIn(">Done</text>", svg)
        self.assertIn("Feature outcome", svg)
        self.assertIn("Quality gate", svg)
        self.assertNotIn("IMAGE BOT PLACEHOLDER", svg)

    def test_published_receipt_prevents_duplicate_post_by_default(self) -> None:
        package = ContentPackage.from_dict(
            {
                "date": "2026-05-26",
                "topic": "Topic",
                "image_prompt": "Supporting illustration",
                "linkedin_infographic": {
                    "headline": "Headline",
                    "subtitle": "Subtitle",
                    "left_panel": {"title": "Left", "points": ["A"]},
                    "right_panel": {"title": "Right", "points": ["B"]},
                    "takeaway_title": "Takeaway",
                    "takeaway_points": ["C"],
                    "workflow": ["Plan", "Done"],
                    "discussion_prompt": "Discuss?",
                },
                "video_script": {"hook": "Hook", "points": ["Point"], "cta": "CTA"},
                "linkedin_caption": "Caption",
                "hashtags": ["#ProjectManagement"],
                "seo_title": "Title",
                "seo_description": "Description",
            }
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            storage = LocalDailyStorage(Path(temporary_dir) / "output")
            record_published_post(package, "images/linkedin_infographic.png", "urn:li:share:1", storage)
            receipt = published_post_receipt(storage, package.date)

        self.assertEqual(receipt["status"], "published")
        self.assertEqual(receipt["post_id"], "urn:li:share:1")
        with self.assertRaisesRegex(RuntimeError, "already recorded"):
            assert_publish_allowed(receipt, force_republish=False)
        assert_publish_allowed(receipt, force_republish=True)

    def test_video_scenes_use_structured_script_copy(self) -> None:
        package = ContentPackage.from_dict(
            {
                "date": "2026-05-26",
                "topic": "Acceptance Criteria That Prevent Rework",
                "image_prompt": "Illustration",
                "linkedin_infographic": {
                    "headline": "Headline",
                    "subtitle": "Subtitle",
                    "left_panel": {"title": "Left", "points": ["A"]},
                    "right_panel": {"title": "Right", "points": ["B"]},
                    "takeaway_title": "Takeaway",
                    "takeaway_points": ["C"],
                    "workflow": ["Plan", "Done"],
                    "discussion_prompt": "Discuss?",
                },
                "video_script": {
                    "hook": "Why does rework happen?",
                    "points": ["Clarify outcomes", "Make criteria testable"],
                    "cta": "What does your team check?",
                },
                "linkedin_caption": "Caption",
                "hashtags": ["#ProjectManagement"],
                "seo_title": "Title",
                "seo_description": "Description",
            }
        )

        scenes = scenes_for_package(package)
        svg = scene_svg(scenes[0], 1, len(scenes)).decode("utf-8")
        subtitles = subtitles_for_scenes(scenes)

        self.assertEqual(len(scenes), 4)
        self.assertIn("Acceptance Criteria That", svg)
        self.assertIn("Prevent Rework", svg)
        self.assertIn("Why does rework happen?", svg)
        self.assertIn('id="grid"', svg)
        self.assertIn("#ffae46", svg)
        self.assertEqual(scenes[-1].label, "YOUR TURN")
        self.assertIn("00:00:00,000 --> 00:00:04,000", subtitles)
        self.assertIn("00:00:14,000 --> 00:00:18,000", subtitles)
        self.assertIn("Why does rework happen?", subtitles)

    def test_video_assembly_requires_ffmpeg_when_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir)
            with patch("content_pipeline.bots.video.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "FFmpeg is required"):
                    _assemble_video(
                        [types.SimpleNamespace(duration=3)],
                        [path / "scene.png"],
                        path / "preview.mp4",
                    )

    def test_long_form_video_uses_narration_and_planned_duration(self) -> None:
        script = LongFormVideoScript.from_dict(
            {
                "title": "Long explainer",
                "scenes": [
                    {
                        "title": "Opening",
                        "on_screen_text": "Write criteria teams can test",
                        "narration": "A complete spoken opening explaining why clarity matters.",
                        "duration_seconds": 12,
                    },
                    {
                        "title": "Close",
                        "on_screen_text": "Review before commitment",
                        "narration": "A spoken closing question for the audience.",
                        "duration_seconds": 10,
                    },
                ],
            }
        )

        scenes = long_form_scenes(script)
        subtitles = subtitles_for_scenes(scenes)

        self.assertEqual(script.duration_seconds, 22)
        self.assertEqual(scenes[0].label, "OPENING")
        self.assertEqual(scenes[-1].label, "YOUR TURN")
        self.assertIn("A complete spoken opening", subtitles)
        self.assertNotIn("Write criteria teams can test", subtitles)
        self.assertIn("00:00:12,000 --> 00:00:22,000", subtitles)

    def test_long_form_video_timing_is_clamped_to_requested_range(self) -> None:
        script = LongFormVideoScript.from_dict(
            {
                "title": "Long explainer",
                "scenes": [
                    {
                        "title": f"Scene {index}",
                        "on_screen_text": "Visible copy",
                        "narration": "Spoken copy",
                        "duration_seconds": 20,
                    }
                    for index in range(16)
                ],
            }
        )

        adjusted = _fit_long_form_duration(script, 180, 300)

        self.assertEqual(adjusted.duration_seconds, 300)

    def test_bal_krishna_motion_plan_uses_prompt_only_safe_validation_clips(self) -> None:
        plan = bal_krishna_validation_plan()

        self.assertEqual(plan.provider, "openai_sora")
        self.assertEqual(plan.size, "720x1280")
        self.assertEqual([clip.duration_seconds for clip in plan.clips], [8, 8])
        self.assertIn("not a real child", plan.clips[0].prompt)
        self.assertIn("No climbing", plan.clips[0].prompt)
        self.assertTrue(any("do not upload family photos" in rule for rule in plan.provider_rules))
        self.assertTrue(any("Vertex Veo is not selected" in rule for rule in plan.provider_rules))

    def test_environment_motion_plan_contains_no_people_for_provider_validation(self) -> None:
        plan = bal_krishna_environment_validation_plan()

        self.assertEqual(plan.project_id, "bal_krishna_environment_motion_validation")
        self.assertTrue(all("No people, no faces" in clip.prompt for clip in plan.clips))
        self.assertIn("peacock feather", plan.clips[1].prompt)

    def test_krishna_agent_registry_keeps_jobs_separate(self) -> None:
        agents = agent_registry()

        self.assertEqual(
            [agent.id for agent in agents],
            [
                "story_agent",
                "voice_agent",
                "image_agent",
                "motion_video_agent",
                "assembly_agent",
                "copyright_policy_agent",
                "youtube_publish_agent",
            ],
        )
        requirements = " ".join(voice_source_policy()["later_custom_voice_requirements"])
        self.assertIn("consent", requirements)

    def test_krishna_agent_workspace_and_image_agent_write_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            written = initialize_agent_workspace(output)
            images = generate_planned_images(
                bal_krishna_image_plan(),
                MockImageProvider(),
                output,
            )

            self.assertTrue(all(path.exists() for path in written))
            self.assertEqual(len(images), 2)
            self.assertTrue(all(path.suffix == ".svg" for path in images))
            manifest = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["agent_order"]), 7)
            self.assertIn("No copyrighted cartoon character", bal_krishna_image_plan().shots[0].prompt)
            self.assertIn("IMAGE BOT PLACEHOLDER", images[0].read_text(encoding="utf-8"))

    def test_selected_krishna_voice_records_creator_approved_builtin_voice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = write_voice_selection(Path(temporary_dir), "sample_01_marin_warm.mp3")
            selection = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(selection["voice"], "marin")
            self.assertEqual(selection["selection_status"], "creator_approved")
            self.assertEqual(selection["voice_source_mode"], "built_in_ai_voice")
            self.assertTrue(selection["disclosure_required"])

    def test_character_identity_pack_requires_supported_motion_provider(self) -> None:
        plan = bal_krishna_character_design_plan()
        protocol = character_motion_validation_protocol()

        self.assertEqual([shot.id for shot in plan.shots], ["kanha_v1_identity", "yashoda_v1_identity"])
        self.assertIn("Entirely fictional design", plan.shots[0].prompt)
        self.assertEqual(protocol["provider_gate"]["openai_sora_character_motion"], "blocked_for_this_route")
        self.assertIn("Luma Dream Machine", protocol["provider_gate"]["next_character_route"])
        self.assertEqual(len(protocol["planned_character_test_clips"]), 2)
        self.assertIn("approved identity", protocol["human_review_checklist"][0])

    def test_youtube_policy_gate_blocks_missing_declarations(self) -> None:
        report = review_publication(
            "Episode",
            "video.mp4",
            PublicationDeclarations(ai_audio_disclosed=True),
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("story_rights", report["blockers"])
        with self.assertRaisesRegex(RuntimeError, "policy review"):
            assert_upload_approved(report)

    def test_youtube_policy_gate_approves_complete_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            video = Path(temporary_dir) / "video.mp4"
            video.write_bytes(b"reviewed-video")
            report = review_publication(
                "Episode",
                str(video),
                PublicationDeclarations(
                    original_or_licensed_story=True,
                    original_or_licensed_music=True,
                    ai_audio_disclosed=True,
                    ai_visuals_disclosed=True,
                    fictional_or_consented_likenesses=True,
                    no_face_reference_supplied_to_video_api=True,
                    made_for_kids_selected=True,
                    no_copyrighted_characters_or_style_copy=True,
                    human_final_review=True,
                ),
            )

            self.assertEqual(report["status"], "approved_for_upload")
            self.assertIsNotNone(report["video_sha256"])
            assert_upload_approved(report)

    def test_youtube_upload_rejects_file_changed_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            video = Path(temporary_dir) / "video.mp4"
            video.write_bytes(b"reviewed-video")
            report = review_publication(
                "Episode",
                str(video),
                PublicationDeclarations(
                    original_or_licensed_story=True,
                    original_or_licensed_music=True,
                    ai_audio_disclosed=True,
                    ai_visuals_disclosed=True,
                    fictional_or_consented_likenesses=True,
                    no_face_reference_supplied_to_video_api=True,
                    made_for_kids_selected=True,
                    no_copyrighted_characters_or_style_copy=True,
                    human_final_review=True,
                ),
            )
            video.write_bytes(b"changed-after-review")

            with self.assertRaisesRegex(RuntimeError, "does not match"):
                upload_youtube_video(video, "Episode", "Description", report, Settings(output_dir=Path("output")))


if __name__ == "__main__":
    unittest.main()
