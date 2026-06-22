from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import requests

from content_pipeline.bots.voicebox import VoiceboxClient, VoiceboxError


class FakeResponse:
    def __init__(
        self,
        *,
        payload=None,
        content: bytes = b"",
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self._payload = payload
        self._content = content
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON")
        return self._payload

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield self._content


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


class VoiceboxClientTest(unittest.TestCase):
    def test_wraps_local_connection_errors(self) -> None:
        class OfflineSession:
            def get(self, url, **kwargs):
                del url, kwargs
                raise requests.ConnectionError("connection refused")

        client = VoiceboxClient(session=OfflineSession())

        with self.assertRaisesRegex(VoiceboxError, "desktop app running"):
            client.list_profiles()

    def test_lists_profiles_from_local_server(self) -> None:
        session = FakeSession(
            [FakeResponse(payload=[{"id": "profile-1", "name": "Narrator"}])]
        )
        client = VoiceboxClient("http://127.0.0.1:17493/", session=session)

        profiles = client.list_profiles()

        self.assertEqual(profiles[0]["name"], "Narrator")
        self.assertEqual(
            session.calls[0][1],
            "http://127.0.0.1:17493/profiles",
        )

    def test_creates_cloned_profile_with_default_engine(self) -> None:
        session = FakeSession(
            [FakeResponse(payload={"id": "profile-2", "name": "Hindi Narrator"})]
        )
        client = VoiceboxClient(session=session)

        profile = client.create_profile(
            name="Hindi Narrator",
            language="hi",
            engine="chatterbox",
        )

        request_payload = session.calls[0][2]["json"]
        self.assertEqual(profile["id"], "profile-2")
        self.assertEqual(request_payload["voice_type"], "cloned")
        self.assertEqual(request_payload["default_engine"], "chatterbox")
        self.assertEqual(request_payload["language"], "hi")

    def test_streams_generated_wav_to_output_file(self) -> None:
        session = FakeSession([FakeResponse(content=b"RIFF-test-wav")])
        client = VoiceboxClient(session=session)
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_path = Path(temporary_dir) / "dub.wav"

            result = client.generate_to_file(
                profile_id="profile-3",
                text="Hello",
                language="en",
                engine="qwen",
                model_size="1.7B",
                output_path=output_path,
            )

            self.assertEqual(result.read_bytes(), b"RIFF-test-wav")
            request_payload = session.calls[0][2]["json"]
            self.assertEqual(request_payload["profile_id"], "profile-3")
            self.assertEqual(request_payload["engine"], "qwen")
            self.assertEqual(request_payload["model_size"], "1.7B")

    def test_surfaces_voicebox_error_detail(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    payload={"detail": {"message": "Model is downloading"}},
                    status_code=409,
                )
            ]
        )
        client = VoiceboxClient(session=session)

        with self.assertRaisesRegex(VoiceboxError, "Model is downloading"):
            client.health()

    def test_reports_background_whisper_download(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    payload={
                        "detail": {
                            "message": "Whisper turbo is being downloaded.",
                            "downloading": True,
                        }
                    },
                    status_code=202,
                )
            ]
        )
        client = VoiceboxClient(session=session)
        with tempfile.TemporaryDirectory() as temporary_dir:
            reference_path = Path(temporary_dir) / "reference.wav"
            reference_path.write_bytes(b"RIFF-test")

            with self.assertRaisesRegex(VoiceboxError, "Retry when it finishes"):
                client.transcribe_reference(reference_path)


if __name__ == "__main__":
    unittest.main()
