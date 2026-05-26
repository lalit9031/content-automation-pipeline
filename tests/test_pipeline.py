import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from content_pipeline.bots.prompt import OpenAIPromptProvider
from content_pipeline.config import Settings
from content_pipeline.pipeline import run_linkedin_mvp


class PipelineTest(unittest.TestCase):
    def test_mock_mvp_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            result = run_linkedin_mvp("2026-05-26", Settings(output_dir=output))
            daily = output / "daily" / "2026-05-26"

            self.assertEqual(result["publishing"]["status"], "prepared")
            self.assertTrue((daily / "prompt.json").exists())
            self.assertTrue((daily / "images" / "image_square.svg").exists())
            self.assertTrue((daily / "images" / "image_portrait.svg").exists())

            payload = json.loads((daily / "publish" / "linkedin_payload.json").read_text())
            self.assertIn("#AI", payload["hashtags"])

    def test_openai_provider_requests_structured_daily_package(self) -> None:
        captured = {}
        content = {
            "date": "2026-05-26",
            "topic": "A generated topic",
            "image_prompt": "A generated image prompt",
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


if __name__ == "__main__":
    unittest.main()
