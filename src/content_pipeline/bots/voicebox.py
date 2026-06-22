from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import requests


class VoiceboxError(RuntimeError):
    """Raised when the local Voicebox service cannot complete a request."""


class VoiceboxClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:17493",
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        response = self._get(
            f"{self.base_url}/health",
            action="check Voicebox health",
            timeout=self.timeout_seconds,
        )
        return self._json_response(response, "check Voicebox health")

    def list_profiles(self) -> list[dict[str, Any]]:
        response = self._get(
            f"{self.base_url}/profiles",
            action="list Voicebox profiles",
            timeout=self.timeout_seconds,
        )
        payload = self._json_response(response, "list Voicebox profiles")
        if not isinstance(payload, list):
            raise VoiceboxError("Voicebox returned an invalid profile list.")
        return payload

    def create_profile(
        self,
        *,
        name: str,
        language: str,
        engine: str,
        description: str = "Created by Content Automation Pipeline",
    ) -> dict[str, Any]:
        response = self._post(
            f"{self.base_url}/profiles",
            action="create a Voicebox profile",
            json={
                "name": name,
                "description": description,
                "language": language,
                "voice_type": "cloned",
                "default_engine": engine,
            },
            timeout=self.timeout_seconds,
        )
        return self._json_response(response, "create a Voicebox profile")

    def transcribe_reference(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        model: str = "turbo",
    ) -> str:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
        with audio_path.open("rb") as audio_file:
            response = self._post(
                f"{self.base_url}/transcribe",
                action="transcribe the reference voice",
                files={"file": (audio_path.name, audio_file, content_type)},
                data={
                    "language": language or "",
                    "model": model,
                },
                timeout=(self.timeout_seconds, 600),
            )
        if response.status_code == 202:
            try:
                detail = response.json().get("detail", {})
                message = detail.get("message", detail)
            except (ValueError, AttributeError):
                message = response.text.strip()
            raise VoiceboxError(
                f"Voicebox is downloading the Whisper model. Retry when it finishes: {message}"
            )
        payload = self._json_response(response, "transcribe the reference voice")
        transcript = str(payload.get("text", "")).strip()
        if not transcript:
            raise VoiceboxError("Voicebox returned an empty reference transcript.")
        return transcript

    def add_profile_sample(
        self,
        profile_id: str,
        audio_path: Path,
        *,
        reference_text: str,
    ) -> dict[str, Any]:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
        with audio_path.open("rb") as audio_file:
            response = self._post(
                f"{self.base_url}/profiles/{profile_id}/samples",
                action="add a Voicebox profile sample",
                files={"file": (audio_path.name, audio_file, content_type)},
                data={"reference_text": reference_text},
                timeout=(self.timeout_seconds, 300),
            )
        return self._json_response(response, "add a Voicebox profile sample")

    def generate_to_file(
        self,
        *,
        profile_id: str,
        text: str,
        language: str,
        engine: str,
        output_path: Path,
        model_size: str | None = None,
        instruct: str | None = None,
        max_chunk_chars: int = 800,
        crossfade_ms: int = 50,
    ) -> Path:
        payload: dict[str, Any] = {
            "profile_id": profile_id,
            "text": text,
            "language": language,
            "engine": engine,
            "max_chunk_chars": max_chunk_chars,
            "crossfade_ms": crossfade_ms,
            "normalize": True,
        }
        if model_size:
            payload["model_size"] = model_size
        if instruct:
            payload["instruct"] = instruct

        response = self._post(
            f"{self.base_url}/generate/stream",
            action="generate Voicebox speech",
            json=payload,
            stream=True,
            timeout=(self.timeout_seconds, 900),
        )
        self._raise_for_status(response, "generate Voicebox speech")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_suffix(f"{output_path.suffix}.part")
        with temporary_path.open("wb") as audio_file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    audio_file.write(chunk)

        if not temporary_path.exists() or temporary_path.stat().st_size == 0:
            temporary_path.unlink(missing_ok=True)
            raise VoiceboxError("Voicebox returned an empty audio file.")
        temporary_path.replace(output_path)
        return output_path

    def _get(self, url: str, *, action: str, **kwargs: Any) -> requests.Response:
        try:
            return self.session.get(url, **kwargs)
        except requests.RequestException as exc:
            raise VoiceboxError(
                f"Could not {action}. Is the Voicebox desktop app running at "
                f"{self.base_url}?"
            ) from exc

    def _post(self, url: str, *, action: str, **kwargs: Any) -> requests.Response:
        try:
            return self.session.post(url, **kwargs)
        except requests.RequestException as exc:
            raise VoiceboxError(
                f"Could not {action}. Is the Voicebox desktop app running at "
                f"{self.base_url}?"
            ) from exc

    @staticmethod
    def _json_response(response: requests.Response, action: str) -> Any:
        VoiceboxClient._raise_for_status(response, action)
        try:
            return response.json()
        except ValueError as exc:
            raise VoiceboxError(
                f"Voicebox returned a non-JSON response while trying to {action}."
            ) from exc

    @staticmethod
    def _raise_for_status(response: requests.Response, action: str) -> None:
        if response.ok:
            return
        detail = ""
        try:
            payload = response.json()
            raw_detail = payload.get("detail", payload)
            if isinstance(raw_detail, dict):
                detail = str(raw_detail.get("message", raw_detail))
            else:
                detail = str(raw_detail)
        except (ValueError, AttributeError):
            detail = response.text.strip()
        suffix = f": {detail}" if detail else ""
        raise VoiceboxError(
            f"Could not {action} (HTTP {response.status_code}){suffix}"
        )
