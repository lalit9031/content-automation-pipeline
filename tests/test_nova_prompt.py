from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from content_pipeline.bots.prompt import (
    BedrockClaudePromptProvider,
    NovaPromptProvider,
    _generate_package_with_nova,
    generate_long_form_video_script,
    prompt_provider,
)
from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage, LongFormVideoScript


def _content_package() -> ContentPackage:
    return ContentPackage.from_dict(
        {
            "date": "2026-06-14",
            "topic": "Stakeholder expectations in sprint reviews",
            "image_prompt": "A project team reviewing a dashboard",
            "linkedin_infographic": {
                "headline": "Make sprint reviews useful",
                "subtitle": "Turn feedback into clear delivery decisions",
                "left_panel": {"title": "Prepare", "points": ["Set context"]},
                "right_panel": {"title": "Review", "points": ["Capture decisions"]},
                "takeaway_title": "Close the loop",
                "takeaway_points": ["Assign every action"],
                "workflow": ["Prep", "Demo", "Decide", "Close"],
                "discussion_prompt": "How do you close your sprint review?",
            },
            "video_script": {
                "hook": "Does your sprint review produce decisions?",
                "points": ["Set context", "Show outcomes", "Assign actions"],
                "cta": "What makes your sprint review effective?",
            },
            "linkedin_caption": "A practical sprint review starts with context.",
            "hashtags": ["#AgileDelivery"],
            "seo_title": "How to run useful sprint reviews",
            "seo_description": "A practical guide to sprint review decisions.",
        }
    )


def _long_form_script() -> LongFormVideoScript:
    return LongFormVideoScript.from_dict(
        {
            "title": "Useful sprint reviews",
            "scenes": [
                {
                    "title": f"Scene {index}",
                    "on_screen_text": f"Step {index}",
                    "narration": f"Narration for scene {index}.",
                    "duration_seconds": 13,
                }
                for index in range(1, 15)
            ],
        }
    )


class NovaPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            output_dir=Path("output"),
            prompt_provider="bedrock_nova",
            bedrock_model_id="global.amazon.nova-2-lite-v1:0",
            bedrock_auth_mode="iam",
            aws_region="ap-southeast-2",
        )

    def test_nova_daily_package_uses_bedrock_converse(self) -> None:
        package = _content_package()
        client = Mock()
        client.converse.return_value = {
            "output": {
                "message": {
                    "content": [{"text": json.dumps(package.as_dict())}],
                }
            }
        }

        with patch(
            "content_pipeline.bots.prompt._build_bedrock_client",
            return_value=client,
        ):
            result = _generate_package_with_nova(
                self.settings,
                day="2026-06-14",
                avoid_topics=["Definition of Done"],
            )

        self.assertEqual(result.topic, package.topic)
        request = client.converse.call_args.kwargs
        self.assertEqual(request["modelId"], "global.amazon.nova-2-lite-v1:0")
        self.assertEqual(request["inferenceConfig"]["temperature"], 0.3)
        self.assertIn("Definition of Done", request["messages"][0]["content"][0]["text"])

    def test_nova_provider_falls_back_to_openai(self) -> None:
        package = _content_package()

        with (
            patch(
                "content_pipeline.bots.prompt._generate_package_with_nova",
                side_effect=RuntimeError("Nova unavailable"),
            ) as nova,
            patch(
                "content_pipeline.bots.prompt._generate_package_with_openai",
                return_value=package,
            ) as openai,
        ):
            result = NovaPromptProvider(self.settings).generate("2026-06-14")

        self.assertEqual(result.topic, package.topic)
        nova.assert_called_once()
        openai.assert_called_once()

    def test_nova_provider_tries_nvidia_before_gemini(self) -> None:
        package = _content_package()
        calls: list[str] = []

        def failure(name: str):
            def raise_error(*args, **kwargs):
                calls.append(name)
                raise RuntimeError(f"{name} unavailable")

            return raise_error

        def nvidia_success(*args, **kwargs):
            calls.append("nvidia")
            return package

        with (
            patch(
                "content_pipeline.bots.prompt._generate_package_with_nova",
                side_effect=failure("nova"),
            ),
            patch(
                "content_pipeline.bots.prompt._generate_package_with_openai",
                side_effect=failure("openai"),
            ),
            patch(
                "content_pipeline.bots.prompt._generate_package_with_nvidia",
                side_effect=nvidia_success,
            ),
            patch(
                "content_pipeline.bots.prompt._generate_package_with_gemini",
            ) as gemini,
        ):
            result = NovaPromptProvider(self.settings).generate("2026-06-14")

        self.assertEqual(result.topic, package.topic)
        self.assertEqual(calls, ["nova", "openai", "nvidia"])
        gemini.assert_not_called()

    def test_long_form_uses_openai_before_nova(self) -> None:
        package = _content_package()
        script = _long_form_script()
        calls: list[str] = []

        def openai_failure(*args, **kwargs):
            calls.append("openai")
            raise RuntimeError("OpenAI unavailable")

        def nova_success(*args, **kwargs):
            calls.append("nova")
            return script

        with (
            patch(
                "content_pipeline.bots.prompt._generate_long_form_with_openai",
                side_effect=openai_failure,
            ),
            patch(
                "content_pipeline.bots.prompt._generate_long_form_with_nova",
                side_effect=nova_success,
            ),
        ):
            result = generate_long_form_video_script(
                package,
                self.settings,
                target_minutes=4,
            )

        self.assertEqual(result.title, script.title)
        self.assertEqual(calls, ["openai", "nova"])

    def test_prompt_provider_accepts_bedrock_nova(self) -> None:
        self.assertIsInstance(prompt_provider(self.settings), NovaPromptProvider)

    def test_prompt_provider_switches_to_bedrock_claude_when_flag_enabled(self) -> None:
        settings = Settings(
            output_dir=Path("output"),
            prompt_provider="anthropic",
            claude_code_use_bedrock=True,
            claude_bedrock_model_id="global.anthropic.claude-opus-4-5-20251101-v1:0",
            bedrock_auth_mode="iam",
            aws_region="ap-southeast-2",
        )

        self.assertIsInstance(prompt_provider(settings), BedrockClaudePromptProvider)

    def test_bedrock_claude_provider_uses_bedrock_converse(self) -> None:
        package = _content_package()
        client = Mock()
        client.converse.return_value = {
            "output": {
                "message": {
                    "content": [{"text": json.dumps(package.as_dict())}],
                }
            }
        }
        settings = Settings(
            output_dir=Path("output"),
            prompt_provider="anthropic",
            claude_code_use_bedrock=True,
            claude_bedrock_model_id="global.anthropic.claude-opus-4-5-20251101-v1:0",
            bedrock_auth_mode="iam",
            aws_region="ap-southeast-2",
        )

        with patch(
            "content_pipeline.bots.prompt._build_bedrock_client",
            return_value=client,
        ):
            result = BedrockClaudePromptProvider(settings).generate(
                "2026-06-14",
                avoid_topics=["Definition of Done"],
            )

        self.assertEqual(result.topic, package.topic)
        request = client.converse.call_args.kwargs
        self.assertEqual(request["modelId"], "global.anthropic.claude-opus-4-5-20251101-v1:0")
        self.assertIn("Definition of Done", request["messages"][0]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
