"""Tests for the Instagram Reels publishing bot (all API calls mocked)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from content_pipeline.bots.instagram import (
    InstagramClient,
    ReelPublishReceipt,
    assert_instagram_publish_allowed,
    authorize_instagram,
    get_instagram_user_id,
    instagram_publish_reel,
    instagram_receipt_path,
    instagram_authorization_url,
    record_instagram_publish,
)
from content_pipeline.config import Settings


def _minimal_settings(**overrides: str) -> Settings:
    base = {
        "instagram_access_token": "test_token_123",
        "instagram_user_id": "test_user_456",
        "instagram_client_id": "test_client_789",
        "instagram_client_secret": "test_secret_000",
    }
    base.update(overrides)
    return Settings(
        output_dir=Path("/tmp/test_output"),
        **{k: v for k, v in base.items() if k != "output_dir"},
    )


class InstagramClientTest(unittest.TestCase):
    """InstagramClient API wrapper tests with mocked HTTP calls."""

    def setUp(self) -> None:
        self.settings = _minimal_settings()
        self.client = InstagramClient(self.settings)

    @patch("content_pipeline.bots.instagram._json_request")
    def test_create_reel_container(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"id": "creation_001"}
        creation_id = self.client.create_reel_container(
            "https://example.com/video.mp4",
            "Test caption #test",
        )
        self.assertEqual(creation_id, "creation_001")
        mock_request.assert_called_once()

    @patch("content_pipeline.bots.instagram._json_request")
    def test_get_container_status(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"status_code": "FINISHED"}
        status = self.client.get_container_status("creation_001")
        self.assertEqual(status, "FINISHED")

    @patch("content_pipeline.bots.instagram._json_request")
    def test_publish_container(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"id": "media_001"}
        media_id = self.client.publish_container("creation_001")
        self.assertEqual(media_id, "media_001")

    @patch.object(InstagramClient, "create_reel_container", return_value="creation_001")
    @patch.object(InstagramClient, "get_container_status", return_value="FINISHED")
    @patch.object(InstagramClient, "publish_container", return_value="media_001")
    def test_publish_reel_full_flow(
        self,
        mock_publish: MagicMock,
        mock_status: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        media_id = self.client.publish_reel(
            "https://example.com/video.mp4",
            "Test caption",
        )
        self.assertEqual(media_id, "media_001")

    @patch.object(InstagramClient, "create_reel_container", return_value="creation_001")
    @patch.object(InstagramClient, "get_container_status", return_value="ERROR")
    def test_publish_reel_raises_on_error_status(
        self,
        mock_status: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        with self.assertRaises(RuntimeError):
            self.client.publish_reel(
                "https://example.com/video.mp4",
                "Test caption",
            )

    def test_create_reel_container_requires_token(self) -> None:
        client = InstagramClient(_minimal_settings(instagram_access_token=""))
        with self.assertRaises(ValueError):
            client._token  # noqa: SLF001  -- accessing property for testing

    def test_create_reel_container_requires_user_id(self) -> None:
        client = InstagramClient(_minimal_settings(instagram_user_id=""))
        with self.assertRaises(ValueError):
            client._user_id  # noqa: SLF001  -- accessing property for testing


class InstagramHelpersTest(unittest.TestCase):
    """ReelPublishReceipt, record, assert helpers."""

    def test_receipt_defaults(self) -> None:
        receipt = ReelPublishReceipt()
        self.assertEqual(receipt.platform, "instagram")
        self.assertEqual(receipt.status, "published")
        self.assertEqual(receipt.media_id, "")

    def test_record_instagram_publish_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            episode_id = "test_ep_001"
            day = "2026-06-01"
            receipt = record_instagram_publish(
                output, episode_id, day, media_id="ig_reel_123",
            )

            self.assertEqual(receipt["media_id"], "ig_reel_123")
            self.assertEqual(receipt["episode_id"], "test_ep_001")

            path = instagram_receipt_path(output, episode_id, day)
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["media_id"], "ig_reel_123")

    def test_assert_instagram_publish_allowed_raises_on_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            record_instagram_publish(output, "ep_001", "2026-06-01", "existing_id")

            with self.assertRaises(RuntimeError):
                assert_instagram_publish_allowed(output, "ep_001", "2026-06-01")

    def test_assert_instagram_publish_allowed_passes_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            record_instagram_publish(output, "ep_001", "2026-06-01", "existing_id")

            # Should not raise
            assert_instagram_publish_allowed(
                output, "ep_001", "2026-06-01", force=True
            )

    def test_assert_instagram_publish_allowed_passes_no_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            assert_instagram_publish_allowed(output, "new_ep", "2026-06-01")

    @patch("content_pipeline.bots.instagram._json_request")
    def test_get_instagram_user_id(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {
            "instagram_business_account": {"id": "ig_user_789"},
        }
        user_id = get_instagram_user_id("test_token", "page_123")
        self.assertEqual(user_id, "ig_user_789")

    @patch("content_pipeline.bots.instagram._json_request")
    def test_get_instagram_user_id_raises_when_missing(
        self, mock_request: MagicMock
    ) -> None:
        mock_request.return_value = {}
        with self.assertRaises(RuntimeError):
            get_instagram_user_id("test_token", "page_123")

    def test_instagram_authorization_url(self) -> None:
        settings = _minimal_settings()
        url = instagram_authorization_url(settings)
        self.assertIn("facebook.com", url)
        self.assertIn("instagram_basic", url)
        self.assertIn("instagram_content_publish", url)

    def test_instagram_authorization_url_requires_client_id(self) -> None:
        settings = _minimal_settings(instagram_client_id="")
        with self.assertRaises(ValueError):
            instagram_authorization_url(settings)

    def test_instagram_publish_reel_rejects_non_mp4(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            with self.assertRaises(ValueError):
                instagram_publish_reel(
                    Path(f.name),
                    "Caption",
                    "https://example.com/video.mp4",
                    _minimal_settings(),
                )

    def test_instagram_publish_reel_rejects_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            instagram_publish_reel(
                Path("/nonexistent/video.mp4"),
                "Caption",
                "https://example.com/video.mp4",
                _minimal_settings(),
            )

    @patch.object(InstagramClient, "publish_reel", return_value="media_001")
    def test_instagram_publish_reel_success(
        self, mock_publish: MagicMock
    ) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"fake mp4 content")
            f.flush()
            media_id = instagram_publish_reel(
                Path(f.name),
                "Test caption #reel",
                "https://example.com/video.mp4",
                _minimal_settings(),
            )
            self.assertEqual(media_id, "media_001")


class InstagramAuthorizationTest(unittest.TestCase):
    """authorize_instagram flow (mocked HTTP and input)."""

    @patch(
        "content_pipeline.bots.instagram._wait_for_oauth_callback",
        return_value={"code": "auth_code_xyz"},
    )
    @patch(
        "content_pipeline.bots.instagram.exchange_instagram_code",
        return_value={"access_token": "short_token"},
    )
    @patch(
        "content_pipeline.bots.instagram._json_request",
    )
    @patch("builtins.input", return_value="fb_page_001")
    @patch(
        "content_pipeline.bots.instagram.get_instagram_user_id",
        return_value="ig_user_789",
    )
    def test_authorize_flow(
        self,
        mock_get_ig_id: MagicMock,
        mock_input: MagicMock,
        mock_json_request: MagicMock,
        mock_exchange: MagicMock,
        mock_callback: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("INSTAGRAM_CLIENT_ID=test_client_789\nINSTAGRAM_CLIENT_SECRET=test_secret_000\n", encoding="utf-8")
            settings = _minimal_settings()
            # Mock the long-lived token exchange
            mock_json_request.return_value = {"access_token": "long_lived_token"}

            result = authorize_instagram(settings, env_path)
            self.assertEqual(result["instagram_user_id"], "ig_user_789")

            env_content = env_path.read_text(encoding="utf-8")
            self.assertIn("INSTAGRAM_ACCESS_TOKEN=", env_content)
            self.assertIn("INSTAGRAM_USER_ID=", env_content)


if __name__ == "__main__":
    unittest.main()
