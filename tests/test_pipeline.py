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
    assert_character_design_approved,
    bal_krishna_character_design_plan,
    bal_krishna_image_plan,
    character_motion_validation_protocol,
    generate_luma_character_identities,
    generate_planned_images,
    initialize_agent_workspace,
    record_character_design_approval,
    voice_source_policy,
    write_voice_selection,
)
from content_pipeline.bots.motion import (
    LumaMotionProvider,
    bal_krishna_environment_validation_plan,
    bal_krishna_luma_kanha_validation_plan,
    bal_krishna_local_kanha_validation_plan,
    bal_krishna_validation_plan,
)
from content_pipeline.bots.policy import (
    PublicationDeclarations,
    assert_upload_approved,
    review_publication,
)
from content_pipeline.bots.prompt import OpenAIPromptProvider, _fit_long_form_duration
from content_pipeline.bots.krishna_studio import (
    assemble_manual_episode,
    butter_heist_short_episode,
    create_daily_video_workspace,
)
from content_pipeline.bots.story_studio import (
    assemble_story_episode,
    create_story_episode,
    create_story_workspace,
    recent_stories,
)
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

    def test_luma_kanha_motion_plan_requires_approved_https_identity_image(self) -> None:
        with self.assertRaises(ValueError):
            bal_krishna_luma_kanha_validation_plan("/tmp/a-child-photo.jpg")

        plan = bal_krishna_luma_kanha_validation_plan("https://cdn.example/fictional-kanha-v1.jpg")

        self.assertEqual(plan.provider, "luma_dream_machine")
        self.assertEqual(plan.clips[0].duration_seconds, 5)
        self.assertEqual(plan.clips[0].reference_image_url, "https://cdn.example/fictional-kanha-v1.jpg")
        self.assertIn("approved fictional KANHA_V1", plan.provider_rules[0])

    def test_luma_identity_and_motion_adapters_use_fictional_reference_url(self) -> None:
        class Response:
            def __init__(self, data: dict | None = None, content: bytes = b"") -> None:
                self.data = data or {}
                self.content = content

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return self.data

        class Session:
            def __init__(self) -> None:
                self.posts: list[dict] = []
                self.image_counter = 0

            def post(self, url: str, **kwargs: object) -> Response:
                self.posts.append({"url": url, **kwargs})
                if url.endswith("/image"):
                    self.image_counter += 1
                    return Response({"id": f"identity-{self.image_counter}"})
                return Response({"id": "motion-1"})

            def get(self, url: str, **kwargs: object) -> Response:
                if url.endswith("identity-1"):
                    return Response({"state": "completed", "assets": {"image": "https://cdn.example/kanha.jpg"}})
                if url.endswith("identity-2"):
                    return Response({"state": "completed", "assets": {"image": "https://cdn.example/yashoda.jpg"}})
                if url.endswith("motion-1"):
                    return Response({"state": "completed", "assets": {"video": "https://cdn.example/kanha.mp4"}})
                return Response(content=b"asset-bytes")

        session = Session()
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            settings = Settings(output_dir=output, luma_api_key="secret")
            identities = generate_luma_character_identities(
                bal_krishna_character_design_plan(), settings, output, session=session
            )
            plan = bal_krishna_luma_kanha_validation_plan(identities[0]["source_url"])
            path = output / "clip.mp4"
            LumaMotionProvider(settings, session=session).create_clip(plan.clips[0], plan, path)

            self.assertTrue(path.exists())
            self.assertEqual(identities[0]["status"], "awaiting_creator_approval")
            self.assertNotIn("image_ref", session.posts[0]["json"])
            motion_payload = session.posts[-1]["json"]
            self.assertEqual(
                motion_payload["keyframes"]["frame0"]["url"],
                "https://cdn.example/kanha.jpg",
            )

    def test_character_design_approval_records_exact_fictional_asset_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            kanha = Path(temporary_dir) / "kanha.png"
            yashoda = Path(temporary_dir) / "yashoda.png"
            kanha.write_bytes(b"fictional-kanha")
            yashoda.write_bytes(b"fictional-yashoda")

            path = record_character_design_approval(output, kanha, yashoda)
            approval = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(
                approval["approval_status"],
                "creator_approved_for_private_motion_validation",
            )
            self.assertNotEqual(
                approval["characters"]["KANHA_V1"]["sha256"],
                approval["characters"]["YASHODA_V1"]["sha256"],
            )
            self.assertIn("No real-person likeness", approval["approval_scope"])
            assert_character_design_approved(path, "KANHA_V1", kanha)

            kanha.write_bytes(b"changed-image")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                assert_character_design_approved(path, "KANHA_V1", kanha)

    def test_local_kanha_plan_is_no_subscription_moving_still_validation(self) -> None:
        plan = bal_krishna_local_kanha_validation_plan("/tmp/approved-fictional-kanha.png")

        self.assertEqual(plan.provider, "local_2_5d")
        self.assertEqual(plan.clips[0].duration_seconds, 5)
        self.assertIn("not face acting", plan.clips[0].prompt)
        self.assertIn("No external video API", plan.provider_rules[2])

    def test_manual_krishna_video_workspace_writes_dashboard_and_clip_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = butter_heist_short_episode("2026-05-28")
            written = create_daily_video_workspace(output, episode)
            root = output / "kanha_ki_nanhi_leela" / "episodes" / episode.episode_id

            self.assertTrue(all(path.exists() for path in written))
            self.assertTrue((root / "clips" / "inbox" / ".gitkeep").exists())
            dashboard = (root / "ui" / "index.html").read_text(encoding="utf-8")
            prompts = json.loads((root / "scene_prompts.json").read_text(encoding="utf-8"))
            script = (root / "story_script.md").read_text(encoding="utf-8")

            self.assertIn("Manual OpenArt / Meta AI Workflow", dashboard)
            self.assertIn("कान्हा और माखन की मटकी", script)
            self.assertIn("shorts (720x1280)", script)
            self.assertEqual(len(prompts), 8)
            self.assertEqual(prompts[0]["expected_clip_file"], "scene_01.mp4")
            self.assertEqual(prompts[0]["size"], "720x1280")
            self.assertIn("Treat Meta AI commercial usage as unconfirmed", " ".join(episode.safety_rules))

    def test_manual_krishna_video_workspace_supports_landscape_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = butter_heist_short_episode("2026-05-28", aspect="landscape")
            create_daily_video_workspace(output, episode)
            root = output / "kanha_ki_nanhi_leela" / "episodes" / episode.episode_id

            prompts = json.loads((root / "scene_prompts.json").read_text(encoding="utf-8"))
            dashboard = (root / "ui" / "index.html").read_text(encoding="utf-8")

            self.assertEqual(episode.width, 1280)
            self.assertEqual(episode.height, 720)
            self.assertIn("Landscape 16:9", prompts[0]["openart_prompt"])
            self.assertEqual(prompts[0]["size"], "1280x720")
            self.assertIn("landscape - 1280x720", dashboard)

    def test_manual_episode_assembly_reports_missing_downloaded_clips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = butter_heist_short_episode("2026-05-28")
            create_daily_video_workspace(output, episode)
            root = output / "kanha_ki_nanhi_leela" / "episodes" / episode.episode_id

            with patch("content_pipeline.bots.krishna_studio.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self.assertRaisesRegex(FileNotFoundError, "scene_01.mp4"):
                    assemble_manual_episode(root)

    def test_story_studio_creates_kid_workspace_and_recent_story_dropdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            written = create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            prompts = json.loads((root / "scene_prompts.json").read_text(encoding="utf-8"))
            dashboard = (root / "ui" / "index.html").read_text(encoding="utf-8")
            script = (root / "story_script.md").read_text(encoding="utf-8")
            characters = json.loads((root / "characters" / "character_references.json").read_text(encoding="utf-8"))

            self.assertTrue(all(path.exists() for path in written))
            self.assertEqual(episode.audience, "kid")
            self.assertTrue(all(row["visual_mode"] == "motion_video" for row in prompts))
            self.assertIn("Recent stories", dashboard)
            self.assertIn("Adult rule", dashboard)
            self.assertIn("Character References", dashboard)
            self.assertIn("selected_command", dashboard)
            self.assertTrue((root / "characters" / "golu_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "momo_v1_reference.svg").exists())
            self.assertEqual(characters[0]["id"], "momo_v1")
            self.assertIn("Use the approved character reference designs", prompts[0]["openart_prompt"])
            self.assertIn("2-5 year olds", script)
            self.assertEqual(recent_stories(output)[0]["episode_id"], episode.episode_id)

    def test_story_studio_adult_workspace_marks_action_scenes_for_motion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode(
                "adult",
                idea="a queen finds a robot army under the desert",
                episode_date="2026-05-28",
                aspect="landscape",
            )
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id
            prompts = json.loads((root / "scene_prompts.json").read_text(encoding="utf-8"))
            dashboard = (root / "ui" / "index.html").read_text(encoding="utf-8")

            self.assertEqual(episode.width, 1280)
            self.assertEqual(episode.height, 720)
            self.assertEqual(prompts[0]["size"], "1280x720")
            self.assertIn("Landscape 16:9", prompts[0]["openart_prompt"])
            self.assertIn("--audience adult --aspect landscape", dashboard)
            self.assertTrue((root / "characters" / "ira_v1_reference.svg").exists())
            self.assertIn("2_5d_image", {row["visual_mode"] for row in prompts})
            self.assertIn("motion_video", {row["visual_mode"] for row in prompts})

    def test_story_studio_keeps_only_last_three_story_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            for index in range(4):
                episode = create_story_episode("kid", idea=f"story idea {index}", episode_date=f"2026-05-2{index}")
                create_story_workspace(output, episode)

            stories = recent_stories(output)

            self.assertEqual(len(stories), 3)
            self.assertIn("Story Idea 3", stories[0]["title"])

    def test_story_studio_assembly_reports_missing_clips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("adult", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            with patch("content_pipeline.bots.story_studio.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self.assertRaisesRegex(FileNotFoundError, "scene_01.mp4"):
                    assemble_story_episode(root)

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
