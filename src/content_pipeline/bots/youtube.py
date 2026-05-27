from __future__ import annotations

from pathlib import Path
from typing import Any

from content_pipeline.bots.policy import assert_upload_approved, video_sha256
from content_pipeline.config import Settings


YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


def authorize_youtube(settings: Settings) -> Path:
    if not settings.youtube_client_secrets_file or not settings.youtube_token_file:
        raise ValueError(
            "YOUTUBE_CLIENT_SECRETS_FILE and YOUTUBE_TOKEN_FILE are required for YouTube authorization."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("Install YouTube dependencies with: pip install -e '.[youtube]'") from exc
    flow = InstalledAppFlow.from_client_secrets_file(
        settings.youtube_client_secrets_file,
        YOUTUBE_UPLOAD_SCOPE,
    )
    credentials = flow.run_local_server(port=0)
    token_path = Path(settings.youtube_token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return token_path


def upload_youtube_video(
    video_path: Path,
    title: str,
    description: str,
    policy_report: dict[str, Any],
    settings: Settings,
    privacy_status: str = "private",
) -> str:
    assert_upload_approved(policy_report)
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("privacy_status must be private, unlisted or public")
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    if policy_report.get("video_sha256") != video_sha256(video_path):
        raise RuntimeError("YouTube upload blocked: final video does not match the reviewed policy report.")
    if not settings.youtube_token_file:
        raise ValueError("YOUTUBE_TOKEN_FILE is required for YouTube upload.")
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("Install YouTube dependencies with: pip install -e '.[youtube]'") from exc

    credentials = Credentials.from_authorized_user_file(
        settings.youtube_token_file,
        YOUTUBE_UPLOAD_SCOPE,
    )
    youtube = build("youtube", "v3", credentials=credentials)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "24",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": True,
                "containsSyntheticMedia": True,
            },
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    response = request.execute()
    return response["id"]
