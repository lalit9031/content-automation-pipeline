from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings


@dataclass(frozen=True)
class GeminiVideoRequest:
    scene_id: str
    title: str
    prompt: str
    duration_seconds: int
    output_file: str


def gemini_config_status(settings: Settings) -> dict[str, Any]:
    return {
        "configured": bool(settings.gemini_api_key),
        "api_key": "configured" if settings.gemini_api_key else "missing",
        "model": settings.gemini_video_model,
        "poll_seconds": settings.gemini_video_poll_seconds,
    }


def build_gemini_requests(workspace_dir: Path) -> list[GeminiVideoRequest]:
    episode = json.loads((workspace_dir / "episode.json").read_text(encoding="utf-8"))
    return [
        GeminiVideoRequest(
            scene_id=scene["id"],
            title=scene["title"],
            prompt=scene["meta_prompt"],
            duration_seconds=int(scene["duration_seconds"]),
            output_file=scene["expected_clip_file"],
        )
        for scene in episode["scenes"]
    ]


def write_gemini_dry_run(workspace_dir: Path) -> Path:
    requests = build_gemini_requests(workspace_dir)
    path = workspace_dir / "gemini_video_requests.json"
    path.write_text(
        json.dumps([asdict(request) for request in requests], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def generate_missing_gemini_clips(
    workspace_dir: Path,
    settings: Settings,
    limit: int | None = None,
    dry_run: bool = False,
) -> list[dict[str, str]]:
    if dry_run:
        return [{"status": "dry_run", "file": str(write_gemini_dry_run(workspace_dir))}]
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required for Gemini/Veo video generation.")
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc

    client = genai.Client(api_key=settings.gemini_api_key)
    inbox = workspace_dir / "clips" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, str]] = []
    for request in build_gemini_requests(workspace_dir):
        output_path = inbox / request.output_file
        if output_path.exists():
            generated.append({"status": "skipped_existing", "scene_id": request.scene_id, "file": str(output_path)})
            continue
        if limit is not None and len([row for row in generated if row["status"] == "completed"]) >= limit:
            generated.append({"status": "limit_reached", "scene_id": request.scene_id, "file": str(output_path)})
            continue
        operation = _start_video_operation(client, settings, request)
        video_bytes = _await_video_bytes(client, operation, settings.gemini_video_poll_seconds)
        output_path.write_bytes(video_bytes)
        generated.append({"status": "completed", "scene_id": request.scene_id, "file": str(output_path)})
    receipt = workspace_dir / "gemini_generation_receipt.json"
    receipt.write_text(json.dumps(generated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return generated


def _start_video_operation(client: Any, settings: Settings, request: GeminiVideoRequest) -> Any:
    kwargs = {
        "model": settings.gemini_video_model,
        "prompt": request.prompt,
    }
    try:
        return client.models.generate_videos(**kwargs)
    except TypeError:
        # Some SDK builds expose video generation directly on models but evolve
        # optional config shapes. Keep the first adapter intentionally minimal.
        return client.models.generate_videos(
            model=settings.gemini_video_model,
            prompt=f"{request.prompt}\nDuration: about {request.duration_seconds} seconds.",
        )


def _await_video_bytes(client: Any, operation: Any, poll_seconds: int) -> bytes:
    while not getattr(operation, "done", False):
        time.sleep(poll_seconds)
        operation = client.operations.get(operation)
    response = getattr(operation, "response", None)
    if response is None:
        raise RuntimeError("Gemini/Veo operation completed without a response.")
    videos = getattr(response, "generated_videos", None) or []
    if not videos:
        raise RuntimeError("Gemini/Veo operation completed without generated videos.")
    video = videos[0]
    video_file = getattr(video, "video", video)
    uri = getattr(video_file, "uri", None)
    if uri and hasattr(client.files, "download"):
        downloaded = client.files.download(file=video_file)
        if isinstance(downloaded, bytes):
            return downloaded
        if hasattr(downloaded, "read"):
            return downloaded.read()
    data = getattr(video_file, "video_bytes", None) or getattr(video_file, "data", None)
    if data:
        return data
    raise RuntimeError("Unable to download Gemini/Veo generated video bytes.")
