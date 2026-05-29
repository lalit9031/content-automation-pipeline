from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import requests


def compose_video_created_message(
    *,
    date: str,
    title: str,
    episode_folder: str,
    manifest_path: str,
    thumbnail_path: str = "",
    checklist: list[str] | None = None,
) -> str:
    checklist = checklist or [
        "Check title, description, and thumbnail.",
        "Review the video once before upload.",
        "Upload to YouTube as private.",
    ]
    checklist_text = "\n".join(f"- {item}" for item in checklist)
    thumbnail_line = f"\nThumbnail: {thumbnail_path}" if thumbnail_path else ""
    return (
        f"Video creation complete for {date}.\n"
        f"Title: {title}\n"
        f"Episode folder: {episode_folder}\n"
        f"Review manifest: {manifest_path}"
        f"{thumbnail_line}\n\n"
        f"Review checklist:\n{checklist_text}\n\n"
        "Next step: review and upload to YouTube."
    )


def compose_youtube_upload_message(
    *,
    title: str,
    youtube_url: str,
    privacy_status: str = "private",
    thumbnail_path: str = "",
) -> str:
    thumbnail_line = f"\nThumbnail: {thumbnail_path}" if thumbnail_path else ""
    return (
        "YouTube upload complete.\n"
        f"Title: {title}\n"
        f"Privacy: {privacy_status}\n"
        f"Link: {youtube_url}"
        f"{thumbnail_line}\n\n"
        "Next step: review the video and change it to public when ready."
    )


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> dict[str, object]:
    if not bot_token:
        raise ValueError("Telegram bot token is required.")
    if not chat_id:
        raise ValueError("Telegram chat id is required.")
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send_telegram_document(
    bot_token: str,
    chat_id: str,
    document_path: Path,
    caption: str = "",
) -> dict[str, object]:
    if not bot_token:
        raise ValueError("Telegram bot token is required.")
    if not chat_id:
        raise ValueError("Telegram chat id is required.")
    if not document_path.exists():
        raise FileNotFoundError(document_path)
    with document_path.open("rb") as handle:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (document_path.name, handle)},
            timeout=30,
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok", False):
        raise RuntimeError(f"Telegram sendDocument failed: {data}")
    return data
