from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_pipeline.bots.policy import assert_upload_approved, video_sha256
from content_pipeline.config import Settings


YOUTUBE_UPLOAD_SCOPE = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def _load_token_scopes(token_file: str) -> list[str] | None:
    try:
        with open(token_file, "r", encoding="utf-8") as f:
            token_data = json.load(f)
            scopes = token_data.get("scopes", None)
            if isinstance(scopes, list) and scopes:
                return [str(scope) for scope in scopes]
    except Exception:
        return None
    return None


def _build_youtube_service(settings: Settings):
    if not settings.youtube_token_file:
        raise ValueError("YOUTUBE_TOKEN_FILE is required for YouTube access.")
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install YouTube dependencies with: pip install -e '.[youtube]'") from exc

    scopes = _load_token_scopes(settings.youtube_token_file) or YOUTUBE_UPLOAD_SCOPE
    credentials = Credentials.from_authorized_user_file(settings.youtube_token_file, scopes)
    return build("youtube", "v3", credentials=credentials)


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
    try:
        credentials = flow.run_local_server(port=0)
    except PermissionError:
        credentials = flow.run_console()
    token_path = Path(settings.youtube_token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return token_path


def review_youtube_upload_readiness(
    *,
    title: str,
    video_path: Path,
    description_text: str,
    policy_report: dict[str, Any],
    thumbnail_path: Path | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(identifier: str, passed: bool, requirement: str) -> None:
        checks.append({"id": identifier, "passed": passed, "requirement": requirement})

    add_check("video_exists", video_path.exists(), "The rendered video file exists.")
    add_check("video_non_empty", video_path.exists() and video_path.stat().st_size > 0, "The rendered video file is not empty.")
    add_check("title_present", bool(title.strip()), "A non-empty YouTube title is provided.")
    add_check("title_length", len(title.strip()) <= 100, "The YouTube title stays within a safe length limit.")
    add_check("description_present", bool(description_text.strip()), "A YouTube description is provided.")
    add_check("description_length", len(description_text.strip()) <= 5000, "The description stays within platform limits.")
    add_check("description_disclosure", "Disclosure:" in description_text, "The description includes the AI disclosure line.")
    add_check(
        "thumbnail_exists",
        thumbnail_path.exists() if thumbnail_path else False,
        "The thumbnail file exists next to the episode workspace.",
    )
    add_check(
        "policy_report_approved",
        policy_report.get("status") == "approved_for_upload" and not policy_report.get("blockers"),
        "The publication policy report is approved.",
    )
    add_check(
        "policy_report_matches_video",
        policy_report.get("video_sha256") == video_sha256(video_path),
        "The policy report fingerprint matches the final video.",
    )
    add_check(
        "policy_report_matches_title",
        str(policy_report.get("title", "")).strip() == title.strip(),
        "The policy report title matches the upload title.",
    )

    blockers = [check["id"] for check in checks if not check["passed"]]
    return {
        "title": title,
        "video_file": str(video_path),
        "thumbnail_file": str(thumbnail_path) if thumbnail_path else "",
        "status": "approved_for_upload" if not blockers else "blocked",
        "blockers": blockers,
        "checks": checks,
    }


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
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("Install YouTube dependencies with: pip install -e '.[youtube]'") from exc

    youtube = _build_youtube_service(settings)
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


def update_youtube_video_metadata(
    settings: Settings,
    video_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    if not video_id.strip():
        raise ValueError("video_id is required.")
    youtube = _build_youtube_service(settings)
    response = youtube.videos().list(
        part="snippet",
        id=video_id,
    ).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError(f"Video not found: {video_id}")

    snippet = dict(items[0].get("snippet", {}))
    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = tags

    if not snippet.get("categoryId"):
        snippet["categoryId"] = "24"

    update_response = youtube.videos().update(
        part="snippet",
        body={
            "id": video_id,
            "snippet": snippet,
        },
    ).execute()
    return update_response


def list_my_uploaded_videos(settings: Settings, max_results: int = 50) -> list[dict[str, Any]]:
    if not settings.youtube_token_file:
        raise ValueError("YOUTUBE_TOKEN_FILE is required for YouTube listing.")
    youtube = _build_youtube_service(settings)
    channel_response = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = channel_response.get("items", [])
    if not items:
        return []
    uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=min(50, max_results),
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            content_details = item.get("contentDetails", {})
            snippet = item.get("snippet", {})
            video_id = str(content_details.get("videoId", ""))
            if not video_id:
                continue
            videos.append(
                {
                    "video_id": video_id,
                    "title": str(snippet.get("title", "")),
                    "published_at": str(snippet.get("publishedAt", "")),
                }
            )
            if len(videos) >= max_results:
                return videos
        page_token = response.get("nextPageToken")
        if not page_token:
            return videos


def get_my_video_details(settings: Settings, video_ids: list[str]) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    if not settings.youtube_token_file:
        raise ValueError("YOUTUBE_TOKEN_FILE is required for YouTube listing.")
    youtube = _build_youtube_service(settings)
    response = youtube.videos().list(
        part="snippet,status,statistics,contentDetails",
        id=",".join(video_ids),
        maxResults=len(video_ids),
    ).execute()
    details: list[dict[str, Any]] = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        status = item.get("status", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        duration = str(content_details.get("duration", ""))
        details.append(
            {
                "video_id": str(item.get("id", "")),
                "title": str(snippet.get("title", "")),
                "description": str(snippet.get("description", "")),
                "tags": list(snippet.get("tags", []) or []),
                "privacy_status": str(status.get("privacyStatus", "")),
                "published_at": str(snippet.get("publishedAt", "")),
                "publish_at": str(status.get("publishAt", "")),
                "duration": duration,
                "view_count": int(statistics.get("viewCount", 0) or 0),
                "like_count": int(statistics.get("likeCount", 0) or 0),
                "comment_count": int(statistics.get("commentCount", 0) or 0),
            }
        )
    return details
