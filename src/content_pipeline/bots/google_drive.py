from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings

logger = logging.getLogger(__name__)


def upload_to_google_drive(
    video_path: Path,
    folder_id: str | None,
    settings: Settings,
) -> str:
    """Uploads a compiled MP4 video file to a specific Google Drive folder.

    Reuses the existing YouTube token file for credentials.
    Returns the shareable web view URL of the uploaded file on Google Drive.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found for Drive upload: {video_path}")

    if not settings.youtube_token_file:
        raise ValueError("YOUTUBE_TOKEN_FILE setting is required to fetch credentials.")

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "Google API Client dependencies missing. Install via: pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    # Load token scopes to check if drive.file is authorized
    import json
    token_scopes = []
    try:
        with open(settings.youtube_token_file, "r") as f:
            token_data = json.load(f)
            token_scopes = token_data.get("scopes", [])
    except Exception:
        pass

    drive_scope = "https://www.googleapis.com/auth/drive.file"
    if drive_scope not in token_scopes:
        raise ValueError(
            f"Google Drive scope '{drive_scope}' is not authorized in your current token file.\n"
            f"To enable Google Drive uploads, please delete your token file at '{settings.youtube_token_file}' "
            "and run authorization again to authenticate with full permissions!"
        )

    # Load credentials from the shared YouTube token file
    credentials = Credentials.from_authorized_user_file(
        settings.youtube_token_file,
        scopes=token_scopes,
    )

    # Build the Drive v3 client
    drive_service = build("drive", "v3", credentials=credentials)

    # Build metadata
    file_metadata: dict[str, Any] = {
        "name": video_path.name,
        "mimeType": "video/mp4",
    }
    if folder_id and folder_id.strip():
        file_metadata["parents"] = [folder_id.strip()]

    # Secure, resumable media upload
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=1024 * 1024,
        resumable=True,
    )

    request = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Uploading to Drive: {int(status.progress() * 100)}% complete.")

    file_id = response.get("id")
    web_link = response.get("webViewLink")

    # Construct direct view link as fallback if webViewLink is missing
    if not web_link:
        web_link = f"https://drive.google.com/file/d/{file_id}/view"

    return web_link
