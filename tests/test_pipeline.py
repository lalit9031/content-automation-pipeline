import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from content_pipeline.bots.infographic import infographic_svg
from content_pipeline.bots.linkedin import (
    LinkedInClient,
    assert_publish_allowed,
    linkedin_share_payload,
    published_post_receipt,
    record_published_post,
)
from content_pipeline.bots.prompt import OpenAIPromptProvider
from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
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


if __name__ == "__main__":
    unittest.main()
