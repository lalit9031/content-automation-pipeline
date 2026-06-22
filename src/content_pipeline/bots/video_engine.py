"""Video Engine — clip → episode → compilation pipeline.

Architecture
------------
    Scene Clip (5-8 s each)
        ├── auto_2_5d   → fully automated: still image + FFmpeg Ken Burns
        └── manual       → user generates via OpenArt / Meta AI
               │
               ▼
    Episode (2-3 min = ~15–30 clips)
        ├── Shorts  (9:16)  for YouTube Shorts / Instagram Reels
        └── Landscape (16:9) for YouTube episodes
               │
               ▼
    Compilation (20-30 min = ~8–10 episodes)
        └── Stitched episodes + transition slides → final YouTube video

Usage
-----
    # 1. Plan an episode from a topic
    video-clip-plan --date 2026-05-28 --topic "..." --audience kid|adult

    # 2. Auto-generate 2.5D clips (free, no API cost)
    video-episode --workspace <path>

    # 3. OR generate scene clips manually, drop in clips/inbox/
    #    then run the same assemble step
    video-episode --workspace <path>

    # 4. Compile several episodes into one long video
    video-compilation --workspace <path> --episodes id1,id2,...
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
import tempfile
import zipfile

from content_pipeline.bots.image import ImageProvider, ImageVariant
from content_pipeline.config import Settings
from content_pipeline.models import (
    ContentPackage,
    VideoClip,
    VideoCompilation,
    VideoEpisode,
)
from content_pipeline.storage import LocalDailyStorage


# ---------------------------------------------------------------------------
#  WORKSPACE
# ---------------------------------------------------------------------------

def create_episode_workspace(
    output_dir: Path,
    episode: VideoEpisode,
) -> list[Path]:
    """Create the on-disk workspace for an episode.

    Returns paths to all created files.
    """
    root = _episode_root(output_dir, episode)
    inbox = root / "clips" / "inbox"
    auto_dir = root / "clips" / "auto_2_5d"
    video_dir = root / "video"
    ui_dir = root / "ui"
    for directory in (inbox, auto_dir, video_dir, ui_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").write_text("", encoding="utf-8")

    paths: list[Path] = []

    # — episode manifest
    episode_path = root / "episode.json"
    episode_path.write_text(
        json.dumps(_episode_as_dict(episode), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths.append(episode_path)

    # — story script (narration + on-screen text)
    script_path = root / "story_script.md"
    script_path.write_text(_story_markdown(episode), encoding="utf-8")
    paths.append(script_path)

    # — scene prompts (for manual generation)
    prompts_path = root / "scene_prompts.json"
    prompts_path.write_text(
        json.dumps(_prompt_rows(episode), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths.append(prompts_path)

    # — clip drop guide
    guide_path = root / "clip_drop_guide.md"
    guide_path.write_text(_clip_drop_guide(episode), encoding="utf-8")
    paths.append(guide_path)

    # — YouTube metadata reference
    meta_path = root / "youtube_metadata.md"
    meta_path.write_text(
        _youtube_metadata_markdown(episode), encoding="utf-8"
    )
    paths.append(meta_path)

    # — dashboard HTML
    ui_path = ui_dir / "index.html"
    ui_path.write_text(
        _episode_dashboard_html(episode, root), encoding="utf-8"
    )
    paths.append(ui_path)

    return paths


def create_compilation_workspace(
    output_dir: Path,
    compilation: VideoCompilation,
) -> Path:
    """Write the compilation manifest."""
    root = output_dir / "video_compilations" / compilation.compilation_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / "compilation.json"
    path.write_text(
        json.dumps(compilation.as_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
#  AUTO 2.5D CLIP GENERATION  (free, fully automated)
# ---------------------------------------------------------------------------

def generate_auto_2_5d_clips(
    episode: VideoEpisode,
    image_provider: ImageProvider,
    output_dir: Path,
) -> list[Path]:
    """Generate still images + FFmpeg Ken Burns MP4s for auto_2_5d clips.

    Only processes clips where ``source_type == \"auto_2_5d\"``.
    Each clip becomes:
        1. A still image (PNG or SVG depending on provider)
        2. A short MP4 with gentle zoom / pan motion

    Returns paths to the generated clip MP4s.
    """
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError(
            "FFmpeg is required to generate 2.5D clips. Install with: brew install ffmpeg"
        )

    root = _episode_root(output_dir, episode)
    auto_dir = root / "clips" / "auto_2_5d"
    auto_dir.mkdir(parents=True, exist_ok=True)

    variant = ImageVariant(
        "9:16" if episode.aspect == "shorts" else "16:9",
        episode.width,
        episode.height,
        "unused",
    )

    generated: list[Path] = []
    for clip in episode.clips:
        if clip.source_type != "auto_2_5d":
            continue

        clip_path = auto_dir / clip.expected_file
        if clip_path.exists():
            generated.append(clip_path)
            continue

        # 1. Generate still image if it doesn't exist
        still_path = clip_path.with_suffix(".png")
        if not still_path.exists():
            image_bytes = image_provider.create(clip.prompt, variant)
            still_path.parent.mkdir(parents=True, exist_ok=True)
            # The provider may return SVG or PNG bytes; convert SVG to PNG
            _ = _ensure_png_bytes(image_bytes, still_path)

        # 2. Create clean, pin-sharp 2D MP4 from still (avoids zoompan pixelation/stretch)
        frames = clip.duration_seconds * 25
        
        # Draw clean on-screen text as a professional lower-third overlay
        clean_text = clip.on_screen_text.replace("'", "").replace(":", "")
        text_filter = ""
        if clean_text:
            drawtext_supported = False
            try:
                filters_output = subprocess.check_output([executable, "-filters"], text=True)
                if "drawtext" in filters_output:
                    drawtext_supported = True
            except Exception:
                pass

            if drawtext_supported:
                text_filter = (
                    f",drawtext=text='{clean_text}':fontcolor=white:fontsize=42:font='Arial':"
                    "box=1:boxcolor=black@0.65:boxborderw=18:x=(w-text_w)/2:y=h-100"
                )
            else:
                print(f"  ⚠️ Warning: FFmpeg 'drawtext' filter not supported. Skipping subtitles overlay.")
            
        subprocess.run(
            [
                executable,
                "-y",
                "-loop",
                "1",
                "-i",
                str(still_path),
                "-vf",
                (
                    f"scale={episode.width}:{episode.height}:"
                    "force_original_aspect_ratio=decrease,"
                    f"pad={episode.width}:{episode.height}:"
                    f"(ow-iw)/2:(oh-ih)/2,"
                    f"format=yuv420p{text_filter}"
                ),
                "-frames:v",
                str(frames),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(clip_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        generated.append(clip_path)

    return generated


def generate_hf_image_to_video_clips(
    episode: VideoEpisode,
    image_provider: ImageProvider,
    output_dir: Path,
    settings: Settings,
) -> list[Path]:
    """Generate animated clips using ZeroGPU Space or direct HF inference."""
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError(
            "FFmpeg is required to normalize Hugging Face video clips. Install with: brew install ffmpeg"
        )
    has_token = settings.hf_token or (settings.hf_tokens and any(settings.hf_tokens))
    if not has_token:
        raise ValueError("HF_TOKEN is required for Hugging Face video generation.")

    root = _episode_root(output_dir, episode)
    auto_dir = root / "clips" / "auto_2_5d"
    auto_dir.mkdir(parents=True, exist_ok=True)

    variant = ImageVariant(
        "9:16" if episode.aspect == "shorts" else "16:9",
        episode.width,
        episode.height,
        "unused",
    )

    generated: list[Path] = []
    for clip in episode.clips:
        if clip.source_type != "auto_2_5d":
            continue

        clip_path = auto_dir / clip.expected_file
        if clip_path.exists():
            generated.append(clip_path)
            continue

        still_path = clip_path.with_suffix(".png")
        if not still_path.exists():
            image_bytes = image_provider.create(clip.prompt, variant)
            _ensure_png_bytes(image_bytes, still_path)

    render_mode = getattr(settings, "hf_video_render_mode", "zero_gpu_space").strip().lower() or "zero_gpu_space"
    if render_mode == "legacy_2_5d":
        return generate_auto_2_5d_clips(episode, image_provider, output_dir)
    if render_mode == "zero_gpu_space":
        space_id = getattr(settings, "hf_zero_gpu_space_id", "").strip()
        if not space_id:
            raise ValueError(
                "HF_ZERO_GPU_SPACE_ID is required for HF_VIDEO_RENDER_MODE=zero_gpu_space. "
                "Set the Space ID to avoid billed Hugging Face inference usage."
            )
        generated_paths: list[Path] = []
        for clip in episode.clips:
            if clip.source_type != "auto_2_5d":
                continue
            clip_path = auto_dir / clip.expected_file
            if clip_path.exists():
                generated_paths.append(clip_path)
                continue
            package_zip = _build_hf_zero_gpu_episode_package(root, episode, [clip])
            rendered_zip = _render_episode_via_zero_gpu_space(package_zip, settings)
            _extract_zip_to_workspace(rendered_zip, root)
            if not clip_path.exists():
                raise FileNotFoundError(
                    f"ZeroGPU space finished but rendered clip is missing: {clip_path}"
                )
            generated_paths.append(clip_path)
        return generated_paths

    return _generate_hf_motion_clips_via_inference(
        episode=episode,
        image_provider=image_provider,
        output_dir=output_dir,
        settings=settings,
        executable=executable,
        variant=variant,
    )


def _generate_hf_motion_clips_via_inference(
    *,
    episode: VideoEpisode,
    image_provider: ImageProvider,
    output_dir: Path,
    settings: Settings,
    executable: str,
    variant: ImageVariant,
) -> list[Path]:
    try:
        from huggingface_hub import InferenceClient
        from huggingface_hub.inference._generated.types.image_to_video import ImageToVideoTargetSize
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for Hugging Face video generation.") from exc

    root = _episode_root(output_dir, episode)
    auto_dir = root / "clips" / "auto_2_5d"
    auto_dir.mkdir(parents=True, exist_ok=True)

    client_kwargs: dict[str, Any] = {
        "api_key": settings.hf_token,
        "timeout": 300,
    }
    hf_video_provider = getattr(settings, "hf_video_provider", "auto") or "auto"
    if hf_video_provider != "auto":
        client_kwargs["provider"] = hf_video_provider
    client = InferenceClient(**client_kwargs)

    generated: list[Path] = []
    for clip in episode.clips:
        if clip.source_type != "auto_2_5d":
            continue

        clip_path = auto_dir / clip.expected_file
        if clip_path.exists():
            generated.append(clip_path)
            continue

        still_path = clip_path.with_suffix(".png")
        if not still_path.exists():
            image_bytes = image_provider.create(clip.prompt, variant)
            _ensure_png_bytes(image_bytes, still_path)

        motion_prompt = _hf_motion_prompt(clip, episode)
        raw_path = clip_path.with_name(f"{clip_path.stem}.hf_raw.mp4")
        animated_bytes = _generate_hf_motion_bytes(
            client,
            still_path,
            motion_prompt,
            episode,
            clip,
            getattr(settings, "hf_video_model", "Wan-AI/Wan2.2-I2V-A14B"),
            ImageToVideoTargetSize(height=episode.height, width=episode.width),
        )
        raw_path.write_bytes(animated_bytes)
        _normalize_video_to_duration(
            executable=executable,
            input_path=raw_path,
            output_path=clip_path,
            target_duration_seconds=clip.duration_seconds,
            width=episode.width,
            height=episode.height,
            overlay_text=clip.on_screen_text or clip.title,
        )
        try:
            raw_path.unlink(missing_ok=True)
        except Exception:
            pass
        generated.append(clip_path)

    return generated


def _build_hf_zero_gpu_episode_package(
    workspace_dir: Path,
    episode: VideoEpisode,
    clips: list[VideoClip] | None = None,
) -> Path:
    runtime_dir = workspace_dir / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_".join(clip.id for clip in clips) if clips else "all"
    package_path = runtime_dir / f"{episode.episode_id}_{suffix}_zero_gpu_input.zip"
    if package_path.exists():
        package_path.unlink()
    episode_payload = episode.as_dict()
    if clips is not None:
        episode_payload["clips"] = [clip.as_dict() for clip in clips]
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("episode.json", json.dumps(episode_payload, indent=2, ensure_ascii=False) + "\n")
        clip_iterable = clips if clips is not None else [
            clip for clip in episode.clips if clip.source_type == "auto_2_5d"
        ]
        for clip in clip_iterable:
            if clip.source_type != "auto_2_5d":
                continue
            still_path = workspace_dir / "clips" / "auto_2_5d" / Path(clip.expected_file).with_suffix(".png").name
            if not still_path.exists():
                raise FileNotFoundError(f"Missing still image for {clip.expected_file}: {still_path}")
            archive.write(
                still_path,
                arcname=f"clips/auto_2_5d/{still_path.name}",
            )
    return package_path


def _render_episode_via_zero_gpu_space(package_zip: Path, settings: Settings) -> Path:
    try:
        from gradio_client import Client, handle_file
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError as exc:
        raise RuntimeError("gradio_client is required to submit work to the ZeroGPU space.") from exc

    space_id = getattr(settings, "hf_zero_gpu_space_id", "").strip()
    if not space_id:
        raise ValueError("HF_ZERO_GPU_SPACE_ID is required for ZeroGPU rendering.")

    timeout = {"httpx_kwargs": {"timeout": float(getattr(settings, "hf_zero_gpu_space_timeout_seconds", 1800))}}
    client_kwargs: dict[str, Any] = {"src": space_id, **timeout}
    result = None
    last_error: Exception | None = None
    
    tokens_to_try = list(settings.hf_tokens) if settings.hf_tokens else []
    if not tokens_to_try and settings.hf_token:
        tokens_to_try = [settings.hf_token]
    tokens_to_try = [t for t in tokens_to_try if t]
    tokens_to_try.append(None)
    
    for token in tokens_to_try:
        try:
            if token:
                client_kwargs["token"] = token
            else:
                client_kwargs.pop("token", None)
            client = Client(**client_kwargs)
            api_name = getattr(settings, "hf_zero_gpu_space_api_name", "/render_package")
            try:
                result = client.predict(
                    handle_file(str(package_zip)),
                    api_name=api_name,
                )
            except ValueError as api_error:
                if "api_name" not in str(api_error):
                    raise
                result = client.predict(
                    handle_file(str(package_zip)),
                    fn_index=0,
                )
            last_error = None
            break
        except Exception as exc:
            exc_str = str(exc).lower()
            is_auth_error = False
            if isinstance(exc, HfHubHTTPError):
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code == 401:
                    is_auth_error = True
                if status_code == 404:
                    raise FileNotFoundError(
                        f"ZeroGPU Space '{space_id}' was not found or is not accessible. "
                        "Check the Space repo ID (owner/space-name), make sure the Space exists, "
                        "and confirm your HF token can access it if the Space is private."
                    ) from exc
            
            is_gated_error = "gated" in exc_str or "restricted" in exc_str or "authorized" in exc_str or "forbidden" in exc_str
            
            if token and (is_auth_error or is_gated_error or "quota" in exc_str or "exceeded" in exc_str or "limit" in exc_str or "429" in exc_str or "401" in exc_str):
                token_display = f"{token[:8]}..."
                print(f"⚠️ ZeroGPU Space call failed with token {token_display}: {exc}. Trying next token...")
                last_error = exc
                continue
            raise
    if last_error is not None:
        error_msg = str(last_error)
        if "gated" in error_msg.lower() or "restricted" in error_msg.lower():
            raise RuntimeError(
                f"ZeroGPU Space rendering failed due to Gated Repo access restriction: {last_error}.\n"
                "👉 To fix this, visit https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1 "
                "on your Hugging Face account(s), accept the license agreement, and try again."
            ) from last_error
        raise FileNotFoundError(
            f"ZeroGPU Space '{space_id}' rejected the provided tokens or failed with: {last_error}."
        ) from last_error
    if isinstance(result, (list, tuple)):
        result = result[0]
    if not result:
        raise RuntimeError("ZeroGPU space returned no output package.")
    rendered_zip = Path(str(result))
    if not rendered_zip.exists():
        raise RuntimeError(f"ZeroGPU space output package does not exist: {rendered_zip}")
    return rendered_zip


def _extract_zip_to_workspace(zip_path: Path, workspace_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = workspace_dir / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.is_dir():
                continue
            with archive.open(member, "r") as source, open(target, "wb") as destination:
                shutil.copyfileobj(source, destination)


# ---------------------------------------------------------------------------
#  EPISODE ASSEMBLY  (auto + manual clips → final MP4 + SRT)
# ---------------------------------------------------------------------------

def assemble_episode(workspace_dir: Path) -> Path:
    """Assemble an episode from its auto-generated and manual clips.

    1. Reads ``episode.json`` to determine the clip order and source types.
    2. Copies auto-generated clips from ``clips/auto_2_5d/``.
    3. Checks that manual clips exist in ``clips/inbox/``.
    4. Normalises all clips to the target resolution.
    5. Concatenates them with FFmpeg.
    6. Writes an SRT subtitle sidecar.

    Returns the path to the assembled MP4.
    """
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError(
            "FFmpeg is required to assemble episodes. Install with: brew install ffmpeg"
        )

    episode = VideoEpisode.from_dict(
        json.loads((workspace_dir / "episode.json").read_text(encoding="utf-8"))
    )
    inbox = workspace_dir / "clips" / "inbox"
    auto_dir = workspace_dir / "clips" / "auto_2_5d"

    # Verify all clip files are available
    missing_manual = [
        clip.expected_file
        for clip in episode.clips
        if clip.source_type == "manual" and not (inbox / clip.expected_file).exists()
    ]
    if missing_manual:
        raise FileNotFoundError(
            "Manual clips missing from clips/inbox: " + ", ".join(missing_manual)
        )
    missing_auto = [
        clip.expected_file
        for clip in episode.clips
        if clip.source_type == "auto_2_5d" and not (auto_dir / clip.expected_file).exists()
    ]
    if missing_auto:
        raise FileNotFoundError(
            "Auto-generated clips missing from clips/auto_2_5d: "
            + ", ".join(missing_auto)
            + ". Run video-episode first to generate them."
        )

    # Normalise all clips to target resolution
    normalised_dir = workspace_dir / "clips" / "normalised"
    normalised_dir.mkdir(parents=True, exist_ok=True)
    normalised_paths: list[Path] = []
    for clip in episode.clips:
        source = (
            auto_dir if clip.source_type == "auto_2_5d" else inbox
        ) / clip.expected_file
        destination = normalised_dir / clip.expected_file

        if not destination.exists():
            subprocess.run(
                [
                    executable,
                    "-y",
                    "-i",
                    str(source),
                    "-vf",
                    (
                        f"scale={episode.width}:{episode.height}:"
                        f"force_original_aspect_ratio=decrease,"
                        f"pad={episode.width}:{episode.height}:"
                        f"(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                    ),
                    "-r",
                    "25",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-movflags",
                    "+faststart",
                    str(destination),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        normalised_paths.append(destination)

    # Concatenate
    video_dir = workspace_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    concat_path = video_dir / "episode_clips.txt"
    concat_path.write_text(
        "\n".join(f"file '{path}'" for path in normalised_paths) + "\n",
        encoding="utf-8",
    )
    output_path = video_dir / "episode_review.mp4"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # SRT subtitles
    srt_path = video_dir / "subtitles.srt"
    srt_path.write_text(_subtitle_srt(episode), encoding="utf-8")

    return output_path


# ---------------------------------------------------------------------------
#  COMPILATION ASSEMBLY  (multiple episodes → final long video)
# ---------------------------------------------------------------------------

def assemble_compilation(
    output_dir: Path,
    compilation: VideoCompilation,
    episode_dirs: list[Path],
) -> Path:
    """Stitch multiple episode MP4s into a single compilation video.

    Looks for ``video/episode_review.mp4`` in each episode directory.
    Inserts a short transition title card between episodes.
    """
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError(
            "FFmpeg is required to assemble compilations. Install with: brew install ffmpeg"
        )

    episode_mp4s: list[Path] = []
    for episode_dir in episode_dirs:
        mp4 = episode_dir / "video" / "episode_review.mp4"
        if not mp4.exists():
            raise FileNotFoundError(
                f"Episode MP4 not found at {mp4}. "
                "Run episode assembly first."
            )
        episode_mp4s.append(mp4)

    root = output_dir / "video_compilations" / compilation.compilation_id
    root.mkdir(parents=True, exist_ok=True)
    transitions_dir = root / "transitions"
    transitions_dir.mkdir(parents=True, exist_ok=True)

    # Build final concat file with transition cards between episodes
    all_clips: list[Path] = []
    for index, mp4 in enumerate(episode_mp4s):
        if index > 0:
            transition = _render_transition_card(
                transitions_dir,
                index,
                compilation.title,
                compilation.transition_duration_seconds,
            )
            all_clips.append(transition)
        all_clips.append(mp4)

    concat_path = root / "compilation_clips.txt"
    concat_path.write_text(
        "\n".join(f"file '{path}'" for path in all_clips) + "\n",
        encoding="utf-8",
    )
    output_path = root / "final_compilation.mp4"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _render_transition_card(
    transitions_dir: Path,
    index: int,
    title: str,
    duration: int,
) -> Path:
    """Render a simple branded transition slide between episodes."""
    from io import BytesIO
    import cairosvg

    card_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
        f'  <rect width="1280" height="720" fill="#110526"/>'
        f'  <rect width="1280" height="720" fill="url(#grid)"/>'
        f'  <rect width="1280" height="720" fill="url(#glow)"/>'
        f'  <defs>'
        f'    <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">'
        f'      <path d="M44 0H0V44" fill="none" stroke="#542498" stroke-width="1.4" opacity="0.52"/>'
        f'    </pattern>'
        f'    <radialGradient id="glow" cx="50%" cy="48%" r="60%">'
        f'      <stop offset="0%" stop-color="#572494" stop-opacity="0.56"/>'
        f'      <stop offset="100%" stop-color="#110526" stop-opacity="0"/>'
        f'    </radialGradient>'
        f'  </defs>'
        f'  <text x="640" y="340" text-anchor="middle" '
        f'     font-family="Arial, sans-serif" font-size="38" font-weight="700" fill="#fff7ec">'
        f'    {escape(title)}</text>'
        f'  <text x="640" y="400" text-anchor="middle" '
        f'     font-family="Arial, sans-serif" font-size="22" font-weight="500" fill="#beacd9">'
        f'    Episode {index}</text>'
        f'  <rect x="460" y="460" width="360" height="3" rx="1.5" fill="#ffae46"/>'
        f'</svg>'
    )
    png_data = cairosvg.svg2png(
        bytestring=card_svg.encode("utf-8"),
        output_width=1280,
        output_height=720,
    )
    png_path = transitions_dir / f"transition_{index:02d}.png"
    png_path.write_bytes(png_data)

    # Create a short MP4 from the PNG
    card_path = transitions_dir / f"transition_{index:02d}.mp4"
    frames = duration * 25
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-y",
            "-loop",
            "1",
            "-i",
            str(png_path),
            "-vf",
            f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration - 0.5}:d=0.5,format=yuv420p",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(card_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return card_path


# ---------------------------------------------------------------------------
#  SHORTS / REELS DISTRIBUTION  (metadata, recording, duplicate protection)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShortsPublishMetadata:
    """Metadata for publishing an episode as YouTube Shorts / Instagram Reels."""
    platform: str  # "youtube" or "instagram"
    episode_id: str
    title: str
    description: str
    hashtags: list[str]
    aspect: str
    duration_seconds: int
    video_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def shorts_publish_metadata(
    episode: VideoEpisode,
    platform: str = "youtube",
    video_path: Path | None = None,
) -> ShortsPublishMetadata:
    """Generate structured publish metadata from a VideoEpisode.

    Args:
        episode: The assembled episode to publish.
        platform: Target platform ("youtube" or "instagram").
        video_path: Optional path to the assembled MP4.

    Returns:
        ShortsPublishMetadata with platform-appropriate titles and descriptions.
    """
    if episode.aspect != "shorts":
        raise ValueError(
            f"Episode '{episode.episode_id}' has aspect '{episode.aspect}', "
            "not 'shorts'. Only 9:16 episodes can be published as Shorts/Reels."
        )

    if episode.duration_seconds > 60:
        raise ValueError(
            f"Episode duration ({episode.duration_seconds}s) exceeds the 60s "
            "limit for Shorts/Reels. Reduce the target duration."
        )

    if platform == "instagram":
        # Instagram captions have different formatting
        description = episode.youtube_description.replace("\\n", "\n")[:2200]
        hashtags_text = " ".join(episode.hashtags)
        combined = f"{description}\n\n{hashtags_text}"
        # Instagram caption limit is 2200 characters
        caption = combined[:2200]
        return ShortsPublishMetadata(
            platform="instagram",
            episode_id=episode.episode_id,
            title=episode.title,
            description=caption,
            hashtags=episode.hashtags,
            aspect=episode.aspect,
            duration_seconds=episode.duration_seconds,
            video_path=str(video_path) if video_path else None,
        )

    # YouTube Shorts
    return ShortsPublishMetadata(
        platform="youtube",
        episode_id=episode.episode_id,
        title=episode.youtube_title,
        description=episode.youtube_description,
        hashtags=episode.hashtags,
        aspect=episode.aspect,
        duration_seconds=episode.duration_seconds,
        video_path=str(video_path) if video_path else None,
    )


def shorts_receipt_path(output_dir: Path, episode_id: str, platform: str) -> Path:
    """Path to the publish receipt for a shorts episode."""
    path = output_dir / "publish"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"shorts_{platform}_{episode_id}.json"


def record_shorts_publish(
    output_dir: Path,
    episode_id: str,
    platform: str,
    media_id: str,
) -> dict[str, Any]:
    """Record a successful Shorts/Reels publish so it won't be republished."""
    receipt = {
        "platform": platform,
        "episode_id": episode_id,
        "media_id": media_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    path = shorts_receipt_path(output_dir, episode_id, platform)
    path.write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def assert_shorts_publish_allowed(
    output_dir: Path,
    episode_id: str,
    platform: str,
    force: bool = False,
) -> None:
    """Raise if a publish receipt already exists for this episode + platform."""
    path = shorts_receipt_path(output_dir, episode_id, platform)
    if path.exists() and not force:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        raise RuntimeError(
            f"Short/Reel already published for episode '{episode_id}' "
            f"on {platform}: media_id={receipt.get('media_id', 'unknown')}. "
            "Use --force-republish to override."
        )


# ---------------------------------------------------------------------------
#  CLIP PLAN GENERATION  (topic → structured clip list)
# ---------------------------------------------------------------------------

def create_clip_plan(
    topic: str,
    audience: str = "adult",
    aspect: str = "shorts",
    episode_date: str | None = None,
    target_duration_seconds: int = 150,
) -> VideoEpisode:
    """Generate a structured clip plan from a topic string.

    For ``audience == \"kid\"`` all clips are ``motion_video`` (requires
    manual generation via OpenArt / Meta AI) because young children need
    expressive character animation.

    For ``audience == \"adult\"`` mood / atmospheric scenes are
    ``2_5d_image`` (fully automated) and action / discovery scenes are
    ``motion_video`` (manual or paid API).

    When OpenAI is configured this can be expanded to generate richer,
    more varied clip plans.
    """
    day = episode_date or date.today().isoformat()
    if aspect not in ("shorts", "landscape"):
        raise ValueError("aspect must be 'shorts' or 'landscape'")
    width, height = (720, 1280) if aspect == "shorts" else (1280, 720)

    aspect_label = "Landscape 16:9" if aspect == "landscape" else "Vertical 9:16"

    clips: list[VideoClip]
    slug = _slug(topic)

    if audience == "kid":
        clips = _kid_clips(topic, aspect, width, height, aspect_label, day)
    else:
        clips = _adult_clips(topic, aspect, width, height, aspect_label, day)

    # Trim / pad to target duration
    clips = _fit_clips_to_duration(clips, target_duration_seconds)

    return VideoEpisode(
        episode_id=f"{day}_{slug}_{aspect}",
        title=_capped(topic, 60),
        description=f"A {audience} episode about: {topic}",
        aspect=aspect,
        width=width,
        height=height,
        clips=clips,
        youtube_title=_capped(topic, 80),
        youtube_description=(
            f"An original {audience} video about {topic}.\\n\\n"
            "Disclosure: AI-generated visuals and narration may be used. "
            "Original fictional characters only."
        ),
        hashtags=["#AIAnimation", "#OriginalContent", f"#{audience.capitalize()}Content"],
    )


def _kid_clips(
    topic: str,
    aspect: str,
    width: int,
    height: int,
    aspect_label: str,
    day: str,
) -> list[VideoClip]:
    """Build a kid-friendly clip plan. All clips use motion_video (needs manual gen)."""
    style = (
        f"{aspect_label}, original bright 3D children's cartoon, soft rounded shapes, "
        "warm nursery colours, simple expressive faces, gentle motion, "
        "no scary visuals, no copyrighted characters, no text, logo or watermark."
    )
    clips = [
        VideoClip(
            id="scene_01",
            title="Opening",
            duration_seconds=7,
            narration=f"Today we learn about {topic}.",
            on_screen_text=f"Let's Explore!",
            visual_mode="motion_video",
            prompt=(
                f"{style} Wide establishing shot of a cheerful storybook "
                f"scene for: {topic}. Warm colours, soft light, camera slowly pushes in."
            ),
            source_type="manual",
            expected_file="scene_01.mp4",
        ),
        VideoClip(
            id="scene_02",
            title="The Idea",
            duration_seconds=8,
            narration=f"A friendly character has an idea about {topic}.",
            on_screen_text="A Big Idea!",
            visual_mode="motion_video",
            prompt=(
                f"{style} A friendly cartoon character has a kind idea, "
                f"eyes light up, soft sparkles, happy expression, harmless."
            ),
            source_type="manual",
            expected_file="scene_02.mp4",
        ),
        VideoClip(
            id="scene_03",
            title="Fun Moment",
            duration_seconds=8,
            narration="Everyone works together and has fun.",
            on_screen_text="Teamwork!",
            visual_mode="motion_video",
            prompt=(
                f"{style} Cute characters playing together safely, "
                "giggling, gentle motion, joyful and warm."
            ),
            source_type="manual",
            expected_file="scene_03.mp4",
        ),
        VideoClip(
            id="scene_04",
            title="Lesson",
            duration_seconds=8,
            narration=f"And that's why {topic} is so wonderful. The end!",
            on_screen_text="The Moral",
            visual_mode="motion_video",
            prompt=(
                f"{style} Closing shot: characters waving together, "
                "soft confetti, warm bedtime-story ending."
            ),
            source_type="manual",
            expected_file="scene_04.mp4",
        ),
    ]
    return clips


def _adult_clips(
    topic: str,
    aspect: str,
    width: int,
    height: int,
    aspect_label: str,
    day: str,
) -> list[VideoClip]:
    """Build an adult clip plan. Mood scenes are auto_2_5d; action is manual motion_video."""
    style_2_5d = (
        f"{aspect_label}, cinematic original adult frame, high-detail "
        "2.5D illustrated style, dramatic lighting, mature tone, "
        "no copyrighted franchise, no logo, no watermark."
    )
    style_motion = (
        f"{aspect_label}, cinematic original adult scene, dramatic lighting, "
        "smooth camera motion, no copyrighted franchise, no logo, no watermark."
    )
    clips = [
        VideoClip(
            id="scene_01",
            title="Establishing Mood",
            duration_seconds=7,
            narration=f"We explore {topic} in depth today.",
            on_screen_text=f"Exploring {_capped(topic, 40)}",
            visual_mode="2_5d_image",
            prompt=(
                f"{style_2_5d} Wide atmospheric scene related to: {topic}. "
                "Moody lighting, subtle motion, cinematic composition."
            ),
            source_type="auto_2_5d",
            expected_file="scene_01.mp4",
        ),
        VideoClip(
            id="scene_02",
            title="The Discovery",
            duration_seconds=8,
            narration=f"A key insight about {topic} emerges.",
            on_screen_text="Key Insight",
            visual_mode="2_5d_image",
            prompt=(
                f"{style_2_5d} A discovery moment showing key details related to {topic}. "
                "Warm light illuminates the subject, thoughtful composition, 2.5D depth."
            ),
            source_type="auto_2_5d",
            expected_file="scene_02.mp4",
        ),
        VideoClip(
            id="scene_03",
            title="Action or Change",
            duration_seconds=8,
            narration="This changes everything we thought we knew.",
            on_screen_text="The Turning Point",
            visual_mode="motion_video",
            prompt=(
                f"{style_motion} A dramatic cinematic action moment, "
                "smooth camera move, creative scene transition, "
                "emotional or awe-inspiring."
            ),
            source_type="manual",
            expected_file="scene_03.mp4",
        ),
        VideoClip(
            id="scene_04",
            title="Resolution",
            duration_seconds=7,
            narration=f"{_capped(topic, 60)} — something to think about.",
            on_screen_text="What's Next?",
            visual_mode="2_5d_image",
            prompt=(
                f"{style_2_5d} Closing atmospheric scene focusing on elements of {topic}, "
                "fading light, contemplative mood, cinematic final frame."
            ),
            source_type="auto_2_5d",
            expected_file="scene_04.mp4",
        ),
    ]
    return clips


# ---------------------------------------------------------------------------
#  HELPERS
# ---------------------------------------------------------------------------


def _ensure_png_bytes(image_bytes: bytes, png_path: Path) -> Path:
    """Convert SVG bytes to PNG using CairoSVG if needed, otherwise write as-is."""
    import cairosvg

    stripped = image_bytes.lstrip()
    if stripped.startswith(b"<") and (b"<svg" in stripped[:200] or b"<?xml" in stripped[:200]):
        cairosvg.svg2png(
            bytestring=image_bytes,
            write_to=str(png_path),
        )
    else:
        png_path.write_bytes(image_bytes)
    return png_path


def _hf_motion_prompt(clip: VideoClip, episode: VideoEpisode) -> str:
    base = clip.prompt.strip()
    if episode.aspect == "shorts":
        aspect_hint = "Vertical kids animation in a 9:16 frame."
    else:
        aspect_hint = "Landscape kids animation in a 16:9 frame."
    return (
        f"{base} "
        f"{aspect_hint} "
        "Animate the approved still as a colorful, child-friendly storybook video with gentle character acting, "
        "smooth camera drift, expressive faces, lively background motion, and a polished cinematic feel. "
        "Keep the same composition and character design from the approved image. "
        "No text, no subtitles, no logo, no watermark, no sudden cuts, no flicker."
    )


def _hf_num_frames_for_duration(duration_seconds: int) -> float:
    if duration_seconds <= 5:
        return 49.0
    if duration_seconds <= 8:
        return 65.0
    if duration_seconds <= 10:
        return 81.0
    return 97.0


def _stable_seed(value: str) -> int:
    seed = 0
    for index, char in enumerate(value):
        seed = (seed + (index + 1) * ord(char)) % 2_147_483_647
    return seed or 1


def _generate_hf_motion_bytes(
    client: Any,
    image_path: Path,
    prompt: str,
    episode: VideoEpisode,
    clip: VideoClip,
    model: str,
    target_size: Any,
) -> bytes:
    last_error: Exception | None = None
    base_kwargs = {
        "model": model,
        "prompt": prompt,
        "negative_prompt": (
            "text, subtitles, captions, watermark, logo, flicker, jitter, distortion, extra limbs, warped faces, "
            "scene cuts, low quality"
        ),
        "num_frames": _hf_num_frames_for_duration(clip.duration_seconds),
        "num_inference_steps": 30,
        "guidance_scale": 7.0,
        "seed": _stable_seed(f"{episode.episode_id}:{clip.id}"),
        "target_size": target_size,
    }
    attempts = [
        base_kwargs,
        {
            "model": model,
            "prompt": prompt,
            "negative_prompt": base_kwargs["negative_prompt"],
            "num_frames": base_kwargs["num_frames"],
            "seed": base_kwargs["seed"],
        },
        {
            "model": model,
            "prompt": prompt,
            "negative_prompt": base_kwargs["negative_prompt"],
        },
    ]
    for kwargs in attempts:
        try:
            return client.image_to_video(image_path, **kwargs)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"Hugging Face image-to-video failed for {clip.id}: {last_error}"
    )


def _probe_video_duration_seconds(path: Path) -> float:
    probe = shutil.which("ffprobe")
    if not probe:
        return 0.0
    try:
        result = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _normalize_video_to_duration(
    *,
    executable: str,
    input_path: Path,
    output_path: Path,
    target_duration_seconds: int,
    width: int,
    height: int,
    overlay_text: str = "",
) -> None:
    source_duration = _probe_video_duration_seconds(input_path)
    if source_duration <= 0:
        source_duration = max(1.0, float(target_duration_seconds))
    speed = max(0.1, float(target_duration_seconds) / source_duration)

    text_filter = ""
    clean_text = overlay_text.replace("'", "").replace(":", "").strip()
    if clean_text:
        try:
            filters_output = subprocess.check_output([executable, "-filters"], text=True)
            if "drawtext" in filters_output:
                text_filter = (
                    f",drawtext=text='{clean_text}':fontcolor=white:fontsize=42:font='Arial':"
                    "box=1:boxcolor=black@0.65:boxborderw=18:x=(w-text_w)/2:y=h-100"
                )
        except Exception:
            text_filter = ""

    subprocess.run(
        [
            executable,
            "-y",
            "-i",
            str(input_path),
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                f"setpts={speed:.6f}*PTS"
                f"{text_filter}"
            ),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _episode_root(output_dir: Path, episode: VideoEpisode) -> Path:
    return (
        output_dir
        / "video_episodes"
        / episode.episode_id
    )


def _episode_as_dict(episode: VideoEpisode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "title": episode.title,
        "description": episode.description,
        "aspect": episode.aspect,
        "width": episode.width,
        "height": episode.height,
        "clips": [asdict(clip) for clip in episode.clips],
        "youtube_title": episode.youtube_title,
        "youtube_description": episode.youtube_description,
        "hashtags": episode.hashtags,
    }


def _safe_text(value: object) -> str:
    return "" if value is None else str(value)


def _fit_clips_to_duration(
    clips: list[VideoClip],
    target_seconds: int,
) -> list[VideoClip]:
    """Pad or trim the clip list to roughly match the target duration."""
    if not clips:
        return clips
    current = sum(c.duration_seconds for c in clips)
    if current >= target_seconds:
        # Trim last clip if needed
        return clips
    # Extend the last clip to fill the gap
    extra = target_seconds - current
    last = clips[-1]
    if last.duration_seconds + extra <= 15:
        clips = list(clips)
        clips[-1] = VideoClip(
            id=last.id,
            title=last.title,
            duration_seconds=last.duration_seconds + extra,
            narration=last.narration,
            on_screen_text=last.on_screen_text,
            visual_mode=last.visual_mode,
            prompt=last.prompt,
            source_type=last.source_type,
            expected_file=last.expected_file,
        )
    return clips


def _capped(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else value[: maximum - 3].rstrip() + "..."


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")[:48]


# ---------------------------------------------------------------------------
#  MARKDOWN / HTML GENERATORS
# ---------------------------------------------------------------------------

def _story_markdown(episode: VideoEpisode) -> str:
    lines = [
        f"# {episode.title}",
        "",
        f"**Format:** {episode.aspect} ({episode.width}x{episode.height})",
        f"**Duration target:** {episode.duration_seconds} seconds ({len(episode.clips)} clips)",
        "",
        episode.description,
        "",
        "## Clip Script",
        "",
    ]
    for index, clip in enumerate(episode.clips, start=1):
        mode_label = "🎬 Motion" if clip.visual_mode == "motion_video" else "🖼️ 2.5D"
        source_label = "🤖 Auto" if clip.source_type == "auto_2_5d" else "✋ Manual"
        lines.extend(
            [
                f"### {index}. {clip.title}  ({clip.duration_seconds}s)  {mode_label}  {source_label}",
                "",
                _safe_text(clip.narration),
                "",
                f"On screen: {_safe_text(clip.on_screen_text)}",
                "",
                f"Save as: `{clip.expected_file}`",
                "",
            ]
        )
    return "\n".join(lines)


def _prompt_rows(episode: VideoEpisode) -> list[dict[str, Any]]:
    return [
        {
            "clip": clip.id,
            "title": clip.title,
            "duration_seconds": clip.duration_seconds,
            "visual_mode": clip.visual_mode,
            "source_type": clip.source_type,
            "aspect": episode.aspect,
            "size": f"{episode.width}x{episode.height}",
            "expected_file": clip.expected_file,
            "prompt": clip.prompt,
        }
        for clip in episode.clips
    ]


def _clip_drop_guide(episode: VideoEpisode) -> str:
    auto_count = sum(1 for c in episode.clips if c.source_type == "auto_2_5d")
    manual_count = sum(1 for c in episode.clips if c.source_type == "manual")
    lines = [
        "# Clip Drop Guide",
        "",
        f"Target: `{episode.aspect}` / `{episode.width}x{episode.height}`",
        f"Auto 2.5D clips: {auto_count} (generated automatically)",
        f"Manual clips needed: {manual_count} (generate in OpenArt / Meta AI)",
        "",
        "## Expected Files",
        "",
    ]
    for clip in episode.clips:
        label = "🤖 Auto (will be generated)" if clip.source_type == "auto_2_5d" else "✋ Generate manually"
        lines.append(f"- `{clip.expected_file}`  — {clip.title} ({clip.duration_seconds}s)  {label}")
    if manual_count:
        lines.extend(
            [
                "",
                "## Manual Clips",
                "",
                "Generate each manual scene in OpenArt or Meta AI, download the MP4, rename it exactly as shown above, and place it in:",
                "",
                "`clips/inbox/`",
                "",
                "Then run the episode assemble command.",
                "",
            ]
        )
    return "\n".join(lines)


def _youtube_metadata_markdown(episode: VideoEpisode) -> str:
    return "\n".join(
        [
            f"# {episode.youtube_title}",
            "",
            "## Description",
            "",
            _safe_text(episode.youtube_description),
            "",
            "## Hashtags",
            "",
            " ".join(_safe_text(tag) for tag in episode.hashtags),
            "",
        ]
    )


def _episode_dashboard_html(episode: VideoEpisode, root: Path) -> str:
    clip_cards = "\n".join(_clip_card(clip, index) for index, clip in enumerate(episode.clips, start=1))
    total_auto = sum(1 for c in episode.clips if c.source_type == "auto_2_5d")
    total_manual = sum(1 for c in episode.clips if c.source_type == "manual")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(episode.title)} - Video Studio</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #13091f; color: #fff7ec; }}
    header {{ padding: 34px; background: linear-gradient(135deg, #31135c, #8f3d1b); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }}
    .card {{ background: #211030; border: 1px solid #6a3f79; border-radius: 18px; padding: 18px; box-shadow: 0 16px 44px rgba(0,0,0,.28); }}
    .clip {{ border-left: 5px solid #ffc05a; }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    p, li {{ line-height: 1.55; color: #f4dfcf; }}
    textarea {{ width: 100%; min-height: 120px; box-sizing: border-box; border-radius: 12px; border: 1px solid #8c6798; padding: 12px; background: #100817; color: #fff9ef; }}
    button {{ background: #ffc05a; color: #1a0b22; border: 0; border-radius: 999px; padding: 9px 14px; font-weight: 700; cursor: pointer; }}
    code {{ color: #ffd27a; }}
    .muted {{ color: #d3b8c9; }}
    .pill {{ display: inline-block; margin: 3px 6px 3px 0; padding: 5px 10px; border-radius: 999px; background: #41214f; color: #ffe1aa; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <div class="pill">{escape(episode.aspect)} - {episode.width}x{episode.height}</div>
    <div class="pill">{episode.duration_seconds}s target</div>
    <div class="pill">{total_auto} auto 2.5D</div>
    <div class="pill">{total_manual} manual</div>
    <h1>{escape(episode.title)}</h1>
    <p>{escape(episode.description)}</p>
    <p class="muted">Workspace: <code>{escape(str(root))}</code></p>
  </header>
  <main>
    <section class="grid">
      <div class="card">
        <h2>Workflow</h2>
        <p><strong>Auto 2.5D clips</strong> (🖼️) are generated automatically via FFmpeg Ken Burns. No action needed.</p>
        <p><strong>Manual clips</strong> (🎬) need OpenArt / Meta AI generation. Copy prompts below, generate, download, rename, and drop into <code>clips/inbox/</code>.</p>
        <p>Then run: <code>video-episode --workspace &lt;path&gt;</code></p>
      </div>
      <div class="card">
        <h2>YouTube Metadata</h2>
        <p><strong>{escape(episode.youtube_title)}</strong></p>
        <textarea id="metadata">{escape(episode.youtube_description)}\\n\\n{" ".join(episode.hashtags)}</textarea>
        <button onclick="copyText('metadata')">Copy Metadata</button>
      </div>
    </section>
    <h2 style="margin-top: 30px;">Clips</h2>
    <section class="grid">{clip_cards}</section>
  </main>
  <script>
    function copyText(id) {{
      const el = document.getElementById(id);
      el.select();
      navigator.clipboard.writeText(el.value);
    }}
  </script>
</body>
</html>
"""


def _clip_card(clip: VideoClip, index: int) -> str:
    prompt_id = f"prompt_{index:02d}"
    mode_emoji = "🎬" if clip.visual_mode == "motion_video" else "🖼️"
    source_label = "Auto 2.5D" if clip.source_type == "auto_2_5d" else "Manual"
    return f"""<article class="card clip">
  <div class="pill">{mode_emoji} {escape(clip.visual_mode)}</div>
  <div class="pill">{source_label}</div>
  <div class="pill">{clip.duration_seconds}s</div>
  <h3>{escape(clip.title)}</h3>
  <p><strong>Narration:</strong> {escape(_safe_text(clip.narration))}</p>
  <p><strong>On screen:</strong> {escape(_safe_text(clip.on_screen_text))}</p>
  <p><strong>Save as:</strong> <code>{escape(clip.expected_file)}</code></p>
  <label>Prompt</label>
  <textarea id="{prompt_id}">{escape(_safe_text(clip.prompt))}</textarea>
  <button onclick="copyText('{prompt_id}')">Copy Prompt</button>
</article>"""


def _subtitle_srt(episode: VideoEpisode) -> str:
    lines: list[str] = []
    start = 0
    for index, clip in enumerate(episode.clips, start=1):
        end = start + clip.duration_seconds
        lines.extend(
            [
                str(index),
                f"{_timestamp(start)} --> {_timestamp(end)}",
                _safe_text(clip.narration or clip.on_screen_text),
                "",
            ]
        )
        start = end
    return "\n".join(lines)


def _timestamp(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, secs = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"
