import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
import wave
from unittest.mock import patch

from content_pipeline.bots.canva import CanvaAuth, render_canva_video
from content_pipeline.bots.blocker_agent import record_blocker
from content_pipeline.bots.infographic import infographic_svg
from content_pipeline.bots.image import (
    GeminiImageLimiter,
    GeminiImageProvider,
    ImageVariant,
    MockImageProvider,
    gemini_image_package_plan,
    gemini_image_status,
)
from content_pipeline.bots.linkedin import (
    LinkedInClient,
    assert_publish_allowed,
    linkedin_share_payload,
    published_post_receipt,
    record_published_post,
)
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
from content_pipeline.bots.prompt import build_image_style_pack
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
    save_reference_media_upload,
)
from content_pipeline.bots.prompt import build_cinematic_image_prompt
from content_pipeline.bots.gemini_video import (
    build_gemini_requests,
    gemini_budget_report,
    gemini_config_status,
    generate_missing_gemini_clips,
    write_gemini_budget_report,
    write_gemini_dry_run,
)
from content_pipeline.bots.video import (
    _assemble_video,
    long_form_scenes,
    scene_svg,
    scenes_for_package,
    subtitles_for_scenes,
)
from content_pipeline.bots.audio import audio_status
from content_pipeline.bots.audio import ReferenceAudioSample
from content_pipeline.bots.audio import curate_reference_audio_bank
from content_pipeline.bots.audio import available_voice_options
from content_pipeline.bots.audio import generate_music_preview
from content_pipeline.bots.audio import filter_voice_preview_presets
from content_pipeline.bots.audio import normalize_voice_text
from content_pipeline.bots.audio import render_audio_status_html
from content_pipeline.bots.audio import reference_audio_language_options
from content_pipeline.bots.audio import scan_reference_audio_library
from content_pipeline.bots.audio import voice_gender_options
from content_pipeline.bots.audio import voice_preview_language_options
from content_pipeline.bots.audio import voice_preview_presets
from content_pipeline.bots.audio import voice_status
from content_pipeline.bots.audio import write_voice_daily_artifacts
from content_pipeline.bots.youtube import upload_youtube_video
from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage, LongFormVideoScript
from content_pipeline.openai_usage import summarize_openai_usage
from content_pipeline.pipeline import run_linkedin_mvp
from content_pipeline.storage import LocalDailyStorage


class PipelineTest(unittest.TestCase):
    def test_mock_mvp_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            record_blocker(
                output,
                command="gemini-image-plan",
                issue="Gemini daily budget is low",
                solution="Use the fallback provider after the safe threshold.",
                component="image",
                source_title="Internal runbook",
                source_url="https://example.com/runbook",
            )
            result = run_linkedin_mvp("2026-05-26", Settings(output_dir=output))
            daily = output / "daily" / "2026-05-26"

            self.assertEqual(result["mode"], "mock")
            self.assertEqual(result["publishing"]["status"], "prepared")
            self.assertTrue((daily / "blocker_status.json").exists())
            self.assertTrue((daily / "blocker_journal_snapshot.json").exists())
            self.assertTrue((daily / "blocker_suggestions.json").exists())
            self.assertTrue((daily / "image_style_pack.json").exists())
            self.assertTrue((daily / "image_storyboard_prompts.json").exists())
            self.assertTrue((daily / "thumbnail_prompt.txt").exists())
            self.assertTrue((daily / "voice_profile.json").exists())
            self.assertTrue((daily / "voice_normalization_preview.txt").exists())
            self.assertTrue((daily / "indian_voice_samples" / "voice_samples_manifest.json").exists())
            self.assertTrue((daily / "audio_status.json").exists())
            self.assertTrue((daily / "audio_status.html").exists())
            self.assertTrue((daily / "blocker_status.html").exists())
            self.assertTrue((daily / "daily_dashboard.html").exists())
            self.assertTrue((daily / "prompt.json").exists())
            self.assertTrue((daily / "images" / "image_square.svg").exists())
            self.assertTrue((daily / "images" / "image_portrait.svg").exists())
            self.assertTrue((daily / "images" / "linkedin_infographic.png").exists())
            dashboard = (daily / "daily_dashboard.html").read_text(encoding="utf-8")
            style_pack = json.loads((daily / "image_style_pack.json").read_text(encoding="utf-8"))
            self.assertIn("Gemini image quota", dashboard)
            self.assertIn("Blocker learning agent", dashboard)
            self.assertIn("Gemini daily budget is low", dashboard)
            self.assertIn("Image style pack", dashboard)
            self.assertIn("Storyboard prompts", dashboard)
            self.assertIn("Thumbnail prompt", dashboard)
            self.assertIn("Voice profile", dashboard)
            self.assertIn("Voice preview", dashboard)
            self.assertIn("Indian voice samples", dashboard)
            self.assertIn("Voice footer", dashboard)
            self.assertIn("Audio status front door", dashboard)
            self.assertIn("gemini_image_status.json", dashboard)
            self.assertIn("blocker_journal_snapshot.json", dashboard)
            self.assertIn("blocker_suggestions.json", dashboard)
            self.assertIn("audio_status.html", dashboard)
            self.assertEqual(style_pack["topic"], json.loads((daily / "prompt.json").read_text(encoding="utf-8"))["topic"])
            self.assertEqual(len(style_pack["storyboard_prompts"]), 35)
            self.assertIn("no text, logos, or watermarks", style_pack["notes"][-1])
            voice_profile = json.loads((daily / "voice_profile.json").read_text(encoding="utf-8"))
            voice_preview = (daily / "voice_normalization_preview.txt").read_text(encoding="utf-8")
            samples_manifest = json.loads(
                (daily / "indian_voice_samples" / "voice_samples_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(voice_profile["voice"], "en-IN-PrabhatNeural")
            self.assertIn("A.I.", voice_preview)
            self.assertEqual(samples_manifest["voice"], "en-IN-PrabhatNeural")
            self.assertEqual(len(samples_manifest["samples"]), 4)

            payload = json.loads((daily / "publish" / "linkedin_payload.json").read_text())
            self.assertIn("#ProjectManagement", payload["hashtags"])
            self.assertEqual(payload["image_file"], "images/linkedin_infographic.png")
            self.assertEqual(payload["posting_target"], "personal_profile")
            self.assertEqual(payload["required_scope"], "w_member_social")

    def test_cinematic_image_prompt_recipe_is_vivid_and_text_free(self) -> None:
        prompt = build_cinematic_image_prompt(
            "Agile project management",
            "a project manager reviewing a glowing workflow board",
            "PM leaders",
        )

        self.assertIn("Agile project management", prompt)
        self.assertIn("pastel purple and cyan highlights", prompt)
        self.assertIn("no text, logos, or watermarks", prompt)
        self.assertIn("hero image", prompt)

    def test_cinematic_image_prompt_sanitizes_brand_names(self) -> None:
        prompt = build_cinematic_image_prompt(
            "Jira workflow management",
            "a team reviewing a Jira board",
            "PM leaders",
        )

        self.assertNotIn("Jira", prompt)
        self.assertIn("project dashboard", prompt)
        self.assertIn("project dashboard workflow management", prompt)

    def test_image_prompt_safety_status_reports_safe_prompt(self) -> None:
        try:
            import app as streamlit_app
        except ModuleNotFoundError:
            self.skipTest("Streamlit is not installed in the test environment")

        state, message = streamlit_app.image_prompt_safety_status(
            build_cinematic_image_prompt(
                "Agile project management",
                "a team reviewing a glowing workflow board",
            )
        )

        self.assertEqual(state, "safe prompt")
        self.assertIn("ready", message)

    def test_image_style_pack_builds_storyboard_and_thumbnail_prompts(self) -> None:
        pack = build_image_style_pack("Agile project management", subject="a team board")

        self.assertEqual(pack.topic, "Agile project management")
        self.assertEqual(len(pack.storyboard_prompts), 35)
        self.assertIn("Agile project management", pack.topic_prompt)
        self.assertIn("Agile project management", pack.thumbnail_prompt)
        self.assertIn("hero", pack.thumbnail_prompt.lower())
        self.assertIn("Scene 01", pack.storyboard_prompts[0]["segment"])
        self.assertIn("vibrant, cinematic 3D", pack.storyboard_prompts[0]["prompt"])
        self.assertIn("no text, logos, or watermarks", " ".join(pack.notes))

    def test_voice_normalization_expands_abbreviations(self) -> None:
        normalized = normalize_voice_text("AI for PM teams using Jira and Scrum.")

        self.assertIn("A.I.", normalized)
        self.assertIn("P.M.", normalized)
        self.assertIn("Jee-ra", normalized)
        self.assertIn("Skrum", normalized)

    def test_available_voice_options_cover_edge_only(self) -> None:
        edge_options = available_voice_options("edge")
        edge_male_options = available_voice_options("edge", "male")

        self.assertIn("en-IN-PrabhatNeural", [voice for voice, _ in edge_options])
        self.assertIn("en-IN-NeerjaNeural", [voice for voice, _ in edge_options])
        self.assertIn("hi-IN-MadhurNeural", [voice for voice, _ in edge_options])
        self.assertIn("en-IN-PrabhatNeural", [voice for voice, _ in edge_male_options])
        self.assertIn("hi-IN-MadhurNeural", [voice for voice, _ in edge_male_options])

    def test_voice_preview_presets_include_hindi_and_hinglish(self) -> None:
        presets = voice_preview_presets()
        labels = {preset.label for preset in presets}
        texts = "\n".join(preset.sample_text for preset in presets)

        self.assertIn("Hindi story", labels)
        self.assertIn("Hindi devotional", labels)
        self.assertIn("Hindi bulletin", labels)
        self.assertIn("Hindi explainer male", labels)
        self.assertIn("Hinglish teacher", labels)
        self.assertIn("कान्हा", texts)
        self.assertIn("Jira", texts)
        self.assertTrue(any(preset.voice == "hi-IN-MadhurNeural" for preset in presets))

    def test_voice_preview_language_options_cover_all_languages(self) -> None:
        languages = voice_preview_language_options()

        self.assertIn(("all", "All languages"), languages)
        self.assertIn(("en-IN", "Hinglish"), languages)
        self.assertIn(("hi-IN", "Hindi"), languages)

    def test_voice_gender_options_cover_all_gender_filters(self) -> None:
        genders = voice_gender_options()

        self.assertIn(("all", "All voices"), genders)
        self.assertIn(("male", "Male voices"), genders)
        self.assertIn(("female", "Female voices"), genders)
        self.assertIn(("neutral", "Neutral voices"), genders)

    def test_voice_preview_fallback_uses_edge_when_selected_voice_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            preview_path = Path(temporary_dir) / "preview.mp3"

            try:
                import app as streamlit_app
            except ModuleNotFoundError:
                self.skipTest("Streamlit is not installed in the test environment")

            def fake_generate_voice_preview(text, output_path, *, provider, voice, openai_api_key=""):
                if voice == "unsupported-voice":
                    raise RuntimeError("voice_failed")
                output_path.write_bytes(b"edge-fallback")
                return output_path

            with patch.object(streamlit_app, "generate_voice_preview", side_effect=fake_generate_voice_preview):
                output = streamlit_app._generate_voice_preview_with_fallback(
                    text="नमस्ते",
                    preview_path=preview_path,
                    voice="unsupported-voice",
                    gender_hint="male",
                    language_hint="hi-IN",
                )

            self.assertTrue(output.exists())
            self.assertIn("hi-IN-MadhurNeural", output.name)
            self.assertEqual(output.read_bytes(), b"edge-fallback")

    def test_render_image_preview_cleans_up_invalid_png_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            preview_path = Path(temporary_dir) / "broken.png"
            preview_path.write_text("not really a png" * 100, encoding="utf-8")

            try:
                import app as streamlit_app
            except ModuleNotFoundError:
                self.skipTest("Streamlit is not installed in the test environment")

            with patch.object(streamlit_app.st, "error") as mock_error, patch.object(
                streamlit_app.st, "warning"
            ) as mock_warning, patch.object(streamlit_app.st, "caption") as mock_caption, patch.object(
                streamlit_app.st, "image"
            ) as mock_image:
                streamlit_app.render_image_preview(preview_path)

            self.assertFalse(preview_path.exists())
            mock_error.assert_called()
            mock_warning.assert_not_called()
            mock_image.assert_not_called()
            mock_caption.assert_called()

    def test_render_image_preview_renders_svg_text_payload_even_with_png_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            preview_path = Path(temporary_dir) / "svg_text.png"
            preview_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#07152f"/></svg>',
                encoding="utf-8",
            )

            try:
                import app as streamlit_app
            except ModuleNotFoundError:
                self.skipTest("Streamlit is not installed in the test environment")

            with patch.object(streamlit_app.components, "html") as mock_html, patch.object(
                streamlit_app.st, "error"
            ) as mock_error, patch.object(streamlit_app.st, "warning") as mock_warning, patch.object(
                streamlit_app.st, "image"
            ) as mock_image:
                streamlit_app.render_image_preview(preview_path)

            self.assertTrue(preview_path.exists())
            mock_html.assert_called()
            mock_error.assert_not_called()
            mock_warning.assert_not_called()
            mock_image.assert_not_called()

    def test_image_preview_source_status_reports_mock_fallback_for_svg_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            preview_path = Path(temporary_dir) / "mock.png"
            preview_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><text>Local renderer baseline</text></svg>',
                encoding="utf-8",
            )

            try:
                import app as streamlit_app
            except ModuleNotFoundError:
                self.skipTest("Streamlit is not installed in the test environment")

            state, message = streamlit_app.image_preview_source_status(preview_path)

            self.assertEqual(state, "mock fallback")
            self.assertIn("local mock renderer", message)

    def test_image_preview_status_reports_ready_missing_and_broken(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            ready_path = Path(temporary_dir) / "ready.png"
            try:
                from PIL import Image
            except ImportError:
                self.skipTest("Pillow is not installed in the test environment")
            image = Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3))
            image.save(ready_path, format="PNG")
            broken_path = Path(temporary_dir) / "broken.png"
            broken_path.write_text("broken payload", encoding="utf-8")
            missing_path = Path(temporary_dir) / "missing.png"

            try:
                import app as streamlit_app
            except ModuleNotFoundError:
                self.skipTest("Streamlit is not installed in the test environment")

            ready_state, ready_message = streamlit_app.image_preview_status(ready_path)
            missing_state, missing_message = streamlit_app.image_preview_status(missing_path)
            broken_state, broken_message = streamlit_app.image_preview_status(broken_path)

            self.assertEqual(ready_state, "ready")
            self.assertIn("stored", ready_message)
            self.assertEqual(missing_state, "missing")
            self.assertIn("No preview file found", missing_message)
            self.assertEqual(broken_state, "broken")
            self.assertIn("too small", broken_message)

    def test_image_backend_status_reports_fallback_active_when_gemini_is_limited(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            runtime = output / ".runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            today = datetime.now(timezone.utc).date().isoformat()
            runtime.joinpath("gemini_image_rate_limit.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "usage_date": today,
                        "keys": [
                            {
                                "next_available_at": 0.0,
                                "cooldown_until": 0.0,
                                "consecutive_failures": 0,
                                "usage_date": today,
                                "daily_generated": 1,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            try:
                import app as streamlit_app
            except ModuleNotFoundError:
                self.skipTest("Streamlit is not installed in the test environment")

            settings = Settings(
                output_dir=output,
                image_provider="gemini",
                gemini_api_key="key-1",
                gemini_image_daily_budget=1,
                image_fallback_provider="mock",
            )

            state, message = streamlit_app.image_backend_status(settings, "gemini")

            self.assertEqual(state, "fallback active")
            self.assertIn("Using mock", message)

    def test_image_provider_routes_gemini_to_imagen_when_project_is_configured(self) -> None:
        class FakeImagenProvider:
            def __init__(self, settings) -> None:
                self.settings = settings

            def create(self, prompt, variant):  # pragma: no cover - not exercised
                raise AssertionError("create should not be called in this routing test")

        from content_pipeline.bots import image as image_module

        settings = Settings(
            output_dir=Path("output"),
            image_provider="gemini",
            gcp_project_id="Pixar-Video-Studio",
            imagen_model="imagen-4.0-generate-001",
        )

        with patch.object(image_module, "ImagenProvider", FakeImagenProvider):
            provider = image_module.image_provider(settings)

        self.assertIsInstance(provider, FakeImagenProvider)
        self.assertEqual(provider.settings.gcp_project_id, "Pixar-Video-Studio")

    def test_filter_voice_preview_presets_by_gender(self) -> None:
        presets = voice_preview_presets()
        male_presets = filter_voice_preview_presets(presets, gender="male")
        female_presets = filter_voice_preview_presets(presets, gender="female")

        self.assertTrue(any(preset.gender == "male" for preset in male_presets))
        self.assertTrue(any(preset.gender == "female" for preset in female_presets))
        self.assertTrue(all(preset.gender == "male" for preset in male_presets))
        self.assertTrue(all(preset.gender == "female" for preset in female_presets))

    def test_reference_audio_language_options_cover_indian_languages(self) -> None:
        languages = reference_audio_language_options(["hindi", "tamil", "urdu"])

        self.assertIn(("all", "All languages"), languages)
        self.assertIn(("hindi", "Hindi"), languages)
        self.assertIn(("tamil", "Tamil"), languages)
        self.assertIn(("urdu", "Urdu"), languages)

    def test_scan_reference_audio_library_discovers_language_folder_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir) / "reference_audio" / "indian_languages_audio_dataset"
            hindi_dir = root / "hindi"
            hindi_dir.mkdir(parents=True, exist_ok=True)
            sample = hindi_dir / "sample_001.mp3"
            sample.write_bytes(b"fake-mp3-bytes")

            samples = scan_reference_audio_library(root)

            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0].collection, "hindi")
            self.assertEqual(samples[0].language, "hindi")
            self.assertEqual(samples[0].path, str(sample))

    def test_scan_reference_audio_library_labels_flat_collections_with_default_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir) / "audio"
            root.mkdir(parents=True, exist_ok=True)
            sample = root / "001.mp3"
            sample.write_bytes(b"fake-mp3-bytes")

            samples = scan_reference_audio_library(root, default_language="hindi")

            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0].collection, "audio")
            self.assertEqual(samples[0].language, "hindi")
            self.assertEqual(samples[0].path, str(sample))

    def test_curate_reference_audio_bank_spreads_samples_across_collection(self) -> None:
        samples = [
            ReferenceAudioSample(
                collection="audio",
                language="hindi",
                path=f"/tmp/{index}.mp3",
                source_label=f"clip {index}",
            )
            for index in range(100)
        ]

        curated = curate_reference_audio_bank(samples, limit=25)

        self.assertEqual(len(curated), 25)
        self.assertEqual(curated[0].path, "/tmp/0.mp3")
        self.assertEqual(curated[-1].path, "/tmp/99.mp3")

    def test_music_preview_writes_wav_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "music.wav"
            preview = generate_music_preview(output, "cinematic", duration_seconds=4)

            self.assertTrue(preview.exists())
            with wave.open(str(preview), "rb") as wav_file:
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertGreater(wav_file.getnframes(), 0)

    def test_voice_daily_artifacts_write_status_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            settings = Settings(output_dir=output, voice_provider="edge", indian_tts_voice="en-IN-PrabhatNeural")

            with patch("content_pipeline.bots.audio.generate_hindi_voice_samples", side_effect=RuntimeError("Mocked offline")):
                written = write_voice_daily_artifacts(output, settings, day="2026-05-26")
            status = voice_status(output, settings, day="2026-05-26")

            self.assertTrue((output / "daily" / "2026-05-26" / "voice_status.json").exists())
            self.assertTrue((output / "daily" / "2026-05-26" / "voice_status.html").exists())
            self.assertEqual(status["day"], "2026-05-26")
            self.assertEqual(status["provider"], "edge")
            self.assertEqual(status["voice"], "en-IN-PrabhatNeural")
            self.assertFalse(status["has_real_audio"])
            self.assertIn("generated_at", status)
            self.assertIn("preview_excerpt", status)
            self.assertIn("A.I.", status["preview_excerpt"])
            self.assertIn("P.M.", status["preview_excerpt"])
            self.assertIn("expected_sample_files", status)
            self.assertIn("missing_sample_files", status)
            self.assertEqual(len(status["expected_sample_files"]), len(status["missing_sample_files"]))
            self.assertEqual(written["voice_status"], output / "daily" / "2026-05-26" / "voice_status.json")
            self.assertEqual(
                written["voice_status_html"],
                output / "daily" / "2026-05-26" / "voice_status.html",
            )
            self.assertIn("manifest only", (output / "daily" / "2026-05-26" / "voice_status.html").read_text())
            self.assertIn("Voice status", (output / "daily" / "2026-05-26" / "voice_status.html").read_text())
            self.assertIn("Last generated", (output / "daily" / "2026-05-26" / "voice_status.html").read_text())
            self.assertIn("Pronunciation preview", (output / "daily" / "2026-05-26" / "voice_status.html").read_text())
            self.assertIn("Missing sample audio", (output / "daily" / "2026-05-26" / "voice_status.html").read_text())

    def test_audio_status_aggregates_daily_science_and_pm_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            settings = Settings(output_dir=output, voice_provider="edge", indian_tts_voice="en-IN-PrabhatNeural")
            write_voice_daily_artifacts(output, settings, day="2026-05-26")

            science_manifest = output / "science_stories" / "science_001" / "audio"
            science_manifest.mkdir(parents=True, exist_ok=True)
            science_manifest.joinpath("audio_manifest.json").write_text(
                json.dumps(
                    {
                        "audio_status": "ready",
                        "provider": "edge",
                        "voice": "en-IN-PrabhatNeural",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            pm_manifest = output / "youtubeVideo" / "2026-05-26" / "episode_001" / "audio" / "reference"
            pm_manifest.mkdir(parents=True, exist_ok=True)
            pm_manifest.joinpath("audio_manifest.json").write_text(
                json.dumps(
                    {
                        "narration_mode": "edge_tts",
                        "tts_voice": "en-IN-PrabhatNeural",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            status = audio_status(output, settings, day="2026-05-26")
            html = render_audio_status_html(status)

            self.assertEqual(status["day"], "2026-05-26")
            self.assertEqual(status["daily_voice_status"]["provider"], "edge")
            self.assertEqual(status["science_audio"]["count"], 1)
            self.assertEqual(status["pm_audio"]["count"], 1)
            self.assertIn("Audio status", html)
            self.assertIn("Science audio", html)
            self.assertIn("PM audio", html)

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

    def test_summarize_openai_usage_handles_chat_and_responses_shapes(self) -> None:
        chat_response = types.SimpleNamespace(
            usage=types.SimpleNamespace(
                prompt_tokens=120,
                completion_tokens=30,
                total_tokens=150,
            )
        )
        responses_response = types.SimpleNamespace(
            usage=types.SimpleNamespace(
                input_tokens=200,
                output_tokens=50,
            )
        )

        chat_summary = summarize_openai_usage(
            chat_response,
            context_window_tokens=1000,
            prompt_rate_per_1m=0.75,
            completion_rate_per_1m=4.50,
        )
        responses_summary = summarize_openai_usage(
            responses_response,
            context_window_tokens=1000,
            prompt_rate_per_1m=0.75,
            completion_rate_per_1m=4.50,
        )

        self.assertEqual(chat_summary.prompt_tokens, 120)
        self.assertEqual(chat_summary.completion_tokens, 30)
        self.assertEqual(chat_summary.total_tokens, 150)
        self.assertEqual(chat_summary.remaining_context_tokens, 850)
        self.assertAlmostEqual(chat_summary.estimated_cost_usd or 0.0, 0.000225)
        self.assertEqual(responses_summary.prompt_tokens, 200)
        self.assertEqual(responses_summary.completion_tokens, 50)
        self.assertEqual(responses_summary.total_tokens, 250)
        self.assertEqual(responses_summary.remaining_context_tokens, 750)
        self.assertAlmostEqual(responses_summary.estimated_cost_usd or 0.0, 0.000375)

    def test_gemini_image_provider_rotates_keys_with_cooldown(self) -> None:
        class FakeClock:
            def __init__(self) -> None:
                self.now = 0.0
                self.sleeps: list[float] = []

            def time(self) -> float:
                return self.now

            def sleep(self, seconds: float) -> None:
                self.sleeps.append(seconds)
                self.now += seconds

        class FakeClient:
            def __init__(self, index: int, calls: list[int]) -> None:
                self.index = index
                self.calls = calls
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                self.calls.append(self.index)
                return types.SimpleNamespace(
                    generated_images=[
                        types.SimpleNamespace(
                            image=types.SimpleNamespace(image_bytes=b"fake-image-bytes")
                        )
                    ]
                )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            clock = FakeClock()
            calls: list[int] = []
            clients = [FakeClient(index, calls) for index in range(4)]
            settings = Settings(
                output_dir=output,
                image_provider="gemini",
                gemini_api_key="key-1",
                gemini_image_daily_budget=50,
                gemini_image_min_interval_seconds=1,
                gemini_image_max_attempts=4,
                gemini_image_retry_backoff_seconds=30,
            )
            limiter = GeminiImageLimiter(
                key_count=4,
                daily_budget=50,
                min_interval_seconds=1,
                max_attempts=4,
                retry_backoff_seconds=30,
                now_fn=clock.time,
                sleep_fn=clock.sleep,
            )
            provider = GeminiImageProvider(
                settings,
                clients=clients,
                limiter=limiter,
                now_fn=clock.time,
                sleep_fn=clock.sleep,
            )
            variant = ImageVariant("16:9", 1280, 720, "unused")

            for _ in range(5):
                image_bytes = provider.create("Prompt text", variant)
                self.assertEqual(image_bytes, b"fake-image-bytes")

            self.assertEqual(calls, [0, 1, 2, 3, 0])
            self.assertIn(1.0, clock.sleeps)

    def test_gemini_image_provider_retries_on_rate_limit(self) -> None:
        class FakeClock:
            def __init__(self) -> None:
                self.now = 0.0
                self.sleeps: list[float] = []

            def time(self) -> float:
                return self.now

            def sleep(self, seconds: float) -> None:
                self.sleeps.append(seconds)
                self.now += seconds

        class ErrorClient:
            def __init__(self, index: int, calls: list[int]) -> None:
                self.index = index
                self.calls = calls
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                self.calls.append(self.index)
                raise RuntimeError("429 Too Many Requests")

        class SuccessClient:
            def __init__(self, index: int, calls: list[int]) -> None:
                self.index = index
                self.calls = calls
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                self.calls.append(self.index)
                return types.SimpleNamespace(
                    generated_images=[
                        types.SimpleNamespace(
                            image=types.SimpleNamespace(image_bytes=b"ok")
                        )
                    ]
                )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            clock = FakeClock()
            calls: list[int] = []
            clients = [ErrorClient(0, calls), SuccessClient(1, calls)]
            settings = Settings(
                output_dir=output,
                image_provider="gemini",
                gemini_api_key="key-1",
                gemini_image_daily_budget=50,
                gemini_image_min_interval_seconds=10,
                gemini_image_max_attempts=4,
                gemini_image_retry_backoff_seconds=30,
            )
            provider = GeminiImageProvider(
                settings,
                clients=clients,
                limiter=GeminiImageLimiter(
                    key_count=2,
                    daily_budget=50,
                    min_interval_seconds=10,
                    max_attempts=4,
                    retry_backoff_seconds=30,
                    now_fn=clock.time,
                    sleep_fn=clock.sleep,
                ),
                now_fn=clock.time,
                sleep_fn=clock.sleep,
            )
            variant = ImageVariant("1:1", 1080, 1080, "unused")

            image_bytes = provider.create("Prompt text", variant)

            self.assertEqual(image_bytes, b"ok")
            self.assertEqual(calls, [0, 1])

    def test_gemini_image_provider_falls_back_on_quota_exhaustion_after_retries(self) -> None:
        class QuotaClient:
            def __init__(self) -> None:
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                raise RuntimeError(
                    "429 RESOURCE_EXHAUSTED: You exceeded your current quota for gemini-2.5-flash-preview-image"
                )

        settings = Settings(
            output_dir=Path("output"),
            image_provider="gemini",
            gemini_api_key="key-1",
            gemini_image_daily_budget=0,
            gemini_image_max_attempts=2,
            image_fallback_provider="mock",
        )
        provider = GeminiImageProvider(settings, clients=[QuotaClient()])

        image_bytes = provider.create("Prompt text", ImageVariant("1:1", 1080, 1080, "unused"))

        self.assertTrue(image_bytes.startswith(b"<svg"))

    def test_gemini_image_status_reports_cooldown_and_next_allowed_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            runtime = output / ".runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc).timestamp()
            today = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
            runtime.joinpath("gemini_image_rate_limit.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at": 100.0,
                        "usage_date": today,
                        "keys": [
                            {
                                "next_available_at": now + 15,
                                "cooldown_until": now + 20,
                                "consecutive_failures": 2,
                                "usage_date": today,
                                "daily_generated": 2,
                            },
                            {
                                "next_available_at": now - 10,
                                "cooldown_until": 0.0,
                                "consecutive_failures": 0,
                                "usage_date": today,
                                "daily_generated": 0,
                            },
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            settings = Settings(
                output_dir=output,
                gemini_api_key="key-1",
                gemini_api_keys=("key-1", "key-2", "key-3", "key-4"),
                gemini_image_daily_budget=10,
                gemini_image_min_interval_seconds=30,
                gemini_image_max_attempts=8,
                gemini_image_retry_backoff_seconds=120,
            )

            status = gemini_image_status(settings, now=now)

            self.assertTrue(status["configured"])
            self.assertEqual(status["configured_key_count"], 4)
            self.assertEqual(status["daily_budget"], 10)
            self.assertEqual(status["daily_generated"], 2)
            self.assertEqual(status["daily_remaining"], 8)
            self.assertEqual(status["cooling_down_slots"], [1])
            self.assertAlmostEqual(status["next_request_allowed_in_seconds"], 0.0)
            self.assertEqual(status["key_states"][0]["slot"], 1)
            self.assertTrue(status["key_states"][0]["cooling_down"])
            self.assertEqual(status["key_states"][1]["slot"], 2)
            self.assertFalse(status["key_states"][1]["cooling_down"])

    def test_gemini_image_plan_estimates_full_packages_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            runtime = output / ".runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc).timestamp()
            today = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
            runtime.joinpath("gemini_image_rate_limit.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "usage_date": today,
                        "keys": [
                            {
                                "next_available_at": 100.0,
                                "cooldown_until": 100.0,
                                "consecutive_failures": 0,
                                "usage_date": today,
                                "daily_generated": 2,
                            },
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            settings = Settings(
                output_dir=output,
                gemini_api_key="key-1",
                gemini_image_daily_budget=5,
                image_provider="gemini",
                image_fallback_provider="mock",
            )

            plan = gemini_image_package_plan(settings, packages_requested=1, now=now)

            self.assertEqual(plan["daily_remaining_images"], 3)
            self.assertEqual(plan["full_packages_remaining"], 1)
            self.assertTrue(plan["can_complete_requested_packages"])
            self.assertEqual(plan["recommended_provider"], "gemini")

            plan2 = gemini_image_package_plan(settings, packages_requested=2, now=now)
            self.assertFalse(plan2["can_complete_requested_packages"])
            self.assertEqual(plan2["recommended_provider"], "mock")
            self.assertTrue(plan2["stop_before_failure"])

    def test_gemini_image_provider_refuses_batch_when_daily_budget_is_too_small(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                raise AssertionError("generate_images should not be called when budget is insufficient")

        settings = Settings(
            output_dir=Path("output"),
            image_provider="gemini",
            gemini_api_key="key-1",
            gemini_image_daily_budget=2,
        )
        provider = GeminiImageProvider(
            settings,
            clients=[FakeClient(), FakeClient(), FakeClient(), FakeClient()],
        )

        with self.assertRaisesRegex(RuntimeError, "daily budget exhausted"):
            provider.ensure_capacity(3)

    def test_gemini_image_provider_falls_back_to_mock_when_daily_budget_is_exhausted(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                raise AssertionError("Gemini client should not be called after budget exhaustion")

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            runtime = output / ".runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            today = datetime.now(timezone.utc).date().isoformat()
            runtime.joinpath("gemini_image_rate_limit.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "usage_date": today,
                        "keys": [
                            {
                                "next_available_at": 0.0,
                                "cooldown_until": 0.0,
                                "consecutive_failures": 0,
                                "usage_date": today,
                                "daily_generated": 1,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            settings = Settings(
                output_dir=output,
                image_provider="gemini",
                gemini_api_key="key-1",
                gemini_image_daily_budget=1,
                image_fallback_provider="mock",
            )
            provider = GeminiImageProvider(
                settings,
                clients=[FakeClient()],
            )

            image_bytes = provider.create("Prompt text", ImageVariant("1:1", 1080, 1080, "unused"))

            self.assertTrue(image_bytes.startswith(b"<svg"))

    def test_gemini_image_provider_falls_back_when_all_keys_are_stuck_waiting(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.models = types.SimpleNamespace(generate_images=self.generate_images)

            def generate_images(self, **kwargs):
                raise AssertionError("Gemini client should not be called when keys are waiting too long")

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            runtime = output / ".runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            future = datetime.now(timezone.utc).timestamp() + 600
            today = datetime.now(timezone.utc).date().isoformat()
            runtime.joinpath("gemini_image_rate_limit.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "usage_date": today,
                        "keys": [
                            {
                                "next_available_at": future,
                                "cooldown_until": future,
                                "consecutive_failures": 3,
                                "usage_date": today,
                                "daily_generated": 0,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            settings = Settings(
                output_dir=output,
                image_provider="gemini",
                gemini_api_key="key-1",
                gemini_image_daily_budget=0,
                image_fallback_provider="mock",
            )
            provider = GeminiImageProvider(
                settings,
                clients=[FakeClient()],
            )

            image_bytes = provider.create("Prompt text", ImageVariant("1:1", 1080, 1080, "unused"))

            self.assertTrue(image_bytes.startswith(b"<svg"))

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
            svg_content = images[0].read_text(encoding="utf-8")
            self.assertIn("THE PM AI QUESTION", svg_content)
            self.assertIn("no API cost", svg_content)

    def test_krishna_planned_images_pace_requests_between_shots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            with patch("content_pipeline.bots.krishna_agents.time.sleep") as sleep_mock:
                images = generate_planned_images(
                    bal_krishna_image_plan(),
                    MockImageProvider(),
                    output,
                    request_delay_seconds=2.5,
                )

            self.assertEqual(len(images), 2)
            sleep_mock.assert_called_once_with(2.5)

    def test_selected_krishna_voice_records_creator_approved_edge_voice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = write_voice_selection(Path(temporary_dir), "sample_01_prabhat_neural.mp3")
            selection = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(selection["voice"], "en-IN-PrabhatNeural")
            self.assertEqual(selection["selection_status"], "creator_approved")
            self.assertEqual(selection["voice_source_mode"], "edge_tts")
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
            self.assertIn("Production Status", dashboard)
            self.assertIn("Upload Reference", dashboard)
            self.assertIn("10-second clip prompts for Scene 01", dashboard)
            self.assertIn("Copy Scene 01-A Prompt", dashboard)
            self.assertIn("split_scene_01_a", dashboard)
            self.assertIn("Recommended: PNG/JPG image", dashboard)
            self.assertIn('enctype="multipart/form-data"', dashboard)
            self.assertIn("0/10 reference media files added", dashboard)
            self.assertIn("0/7 scene clips in clips/inbox", dashboard)
            self.assertTrue((root / "characters" / "golu_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "momo_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "foxy_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "coco_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "bobo_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "bella_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "buzzy_v1_reference.svg").exists())
            self.assertEqual(characters[0]["id"], "momo_v1")
            self.assertEqual(len(characters), 10)
            self.assertIn("Content type", dashboard)
            self.assertIn("Prompt base", dashboard)
            self.assertIn('id="audience_mode"', dashboard)
            self.assertIn('body class="kid-preview"', dashboard)
            self.assertIn("Selected Mode Character Library", dashboard)
            self.assertIn('id="mode_library_kid" class="mode-library-panel active"', dashboard)
            self.assertIn('id="mode_library_adult" class="mode-library-panel"', dashboard)
            self.assertIn('id="workspace_panel_kid" class="mode-workspace-panel active"', dashboard)
            self.assertIn('id="workspace_panel_adult" class="mode-workspace-panel"', dashboard)
            self.assertIn("Adult Character References", dashboard)
            self.assertIn("Adult Scene Prompts", dashboard)
            self.assertIn("adult_split_scene_01_a", dashboard)
            self.assertIn("document.body.className", dashboard)
            self.assertIn("Adult character pack ready", dashboard)
            self.assertIn("Use the approved character reference designs", prompts[0]["openart_prompt"])
            self.assertIn("2-5 year olds", script)
            self.assertEqual(recent_stories(output)[0]["episode_id"], episode.episode_id)

    def test_story_studio_writes_split_scene_prompts_for_copy_create_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            split_prompts = json.loads((root / "split_scene_prompts.json").read_text(encoding="utf-8"))

            self.assertEqual(len(split_prompts), len(episode.scenes) * 5)
            self.assertEqual(split_prompts[0]["clip_id"], "Scene 01-A")
            self.assertEqual(split_prompts[0]["part_label"], "A")
            self.assertEqual(split_prompts[0]["expected_clip_file"], "scene_01_a.mp4")
            self.assertIn("Create only 10 seconds for Scene 01-A", split_prompts[0]["prompt"])
            self.assertIn("Specific beat for this clip", split_prompts[0]["prompt"])

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
            self.assertTrue((root / "characters" / "noor_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "rook7_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "seren_v1_reference.svg").exists())
            self.assertTrue((root / "characters" / "vale_v1_reference.svg").exists())
            self.assertIn("Adult cinematic prompt base", dashboard)
            self.assertIn('body class="adult-preview"', dashboard)
            self.assertIn('id="audience_mode"', dashboard)
            self.assertIn('id="mode_library_kid" class="mode-library-panel"', dashboard)
            self.assertIn('id="mode_library_adult" class="mode-library-panel active"', dashboard)
            self.assertIn('id="workspace_panel_kid" class="mode-workspace-panel"', dashboard)
            self.assertIn('id="workspace_panel_adult" class="mode-workspace-panel active"', dashboard)
            self.assertIn("Kid Character References", dashboard)
            self.assertIn("adult_split_scene_01_a", dashboard)
            self.assertIn("adult learning video explaining a science mystery", dashboard)
            self.assertIn("2_5d_image", {row["visual_mode"] for row in prompts})
            self.assertIn("motion_video", {row["visual_mode"] for row in prompts})

    def test_story_studio_upload_saves_character_reference_with_expected_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            saved = save_reference_media_upload(root, "momo_v1", "manual Gemini Clip.MP4", b"video-bytes")
            dashboard = (root / "ui" / "index.html").read_text(encoding="utf-8")

            self.assertEqual(saved, (root / "references" / "inbox" / "momo_v1_reference.mp4").resolve())
            self.assertEqual(saved.read_bytes(), b"video-bytes")
            self.assertIn("1/10 reference media files added", dashboard)
            self.assertIn("momo_v1_reference.mp4", dashboard)

    def test_story_studio_upload_replaces_old_reference_and_validates_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            old = save_reference_media_upload(root, "golu_v1", "golu.png", b"image")
            new = save_reference_media_upload(root, "golu_v1", "golu.mov", b"video")

            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            with self.assertRaisesRegex(ValueError, "Unsupported reference media type"):
                save_reference_media_upload(root, "golu_v1", "bad.exe", b"data")
            with self.assertRaisesRegex(ValueError, "Unknown character id"):
                save_reference_media_upload(root, "unknown_v1", "clip.mp4", b"data")

    def test_story_studio_dashboard_prefers_image_reference_over_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            references = root / "references" / "inbox"
            (references / "momo_v1_reference.mp4").write_bytes(b"video")
            (references / "momo_v1_reference.png").write_bytes(b"image")
            create_story_workspace(output, episode)
            dashboard = (root / "ui" / "index.html").read_text(encoding="utf-8")

            self.assertIn("momo_v1_reference.png", dashboard)
            self.assertNotIn('src="../references/inbox/momo_v1_reference.mp4"', dashboard)

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

    def test_gemini_dry_run_writes_scene_generation_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            requests = build_gemini_requests(root)
            dry_run = write_gemini_dry_run(root)

            self.assertEqual(len(requests), len(episode.scenes))
            self.assertEqual(requests[0].output_file, "scene_01.mp4")
            self.assertTrue(dry_run.exists())
            self.assertIn("meta_prompt", (root / "episode.json").read_text(encoding="utf-8"))

    def test_gemini_generation_requires_api_key_unless_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id

            result = generate_missing_gemini_clips(root, Settings(output_dir=output), dry_run=True)

            self.assertEqual(result[0]["status"], "dry_run")
            self.assertFalse(gemini_config_status(Settings(output_dir=output))["configured"])
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                generate_missing_gemini_clips(root, Settings(output_dir=output))

    def test_gemini_budget_report_recommends_limited_auto_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            episode = create_story_episode("kid", episode_date="2026-05-28")
            create_story_workspace(output, episode)
            root = output / "story_studio" / "episodes" / episode.episode_id
            settings = Settings(
                output_dir=output,
                gemini_video_daily_clip_budget=2,
                gemini_video_price_per_second_usd=0.15,
            )

            report = gemini_budget_report(root, settings)
            path = write_gemini_budget_report(root, settings)

            self.assertEqual(report["pending_scenes"], len(episode.scenes))
            self.assertEqual(len(report["recommended_auto_today"]), 2)
            self.assertTrue(report["recommended_auto_today_cost_usd"] > 0)
            self.assertTrue(path.exists())

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
