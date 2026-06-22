"""Science Video Agent — produces cinematic 30-minute YouTube videos from a ScienceStoryScript.

Pipeline
--------
    ScienceStoryScript
            │
            ▼
    1. Create workspace (directories, metadata)
            │
            ▼
    2. Generate cinematic still images for each scene
            │
            ▼
    3. Generate Hindi TTS narration audio for each scene
            │
            ▼
    4. Create individual scene clips with FFmpeg
       (still image + audio + Ken Burns zoom/pan + fade)
            │
            ▼
    5. Assemble all clips → burn SRT subtitles → final cinematic YouTube MP4
            │
            ▼
    Output: 1920x1080 MP4 + SRT subtitles + workspace
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import textwrap
import time
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.models import ScienceScene, ScienceStoryScript, ScienceVideoWorkspace
from content_pipeline.bots.audio import generate_indian_voiceover, normalize_voice_text
from content_pipeline.bots.image import ImageProvider, ImageVariant

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  CONSTANTS
# ---------------------------------------------------------------------------

YOUTUBE_WIDTH = 1920
YOUTUBE_HEIGHT = 1080
FPS = 24  # cinematic frame rate
FADE_DURATION = 0.5  # cross-fade between scenes

HINDI_TTS_INSTRUCTIONS = (
    "कृपया शुद्ध, स्वाभाविक भारतीय हिंदी में बोलें। "
    "यह एक वैज्ञानिक डॉक्यूमेंट्री है। "
    "स्वर गंभीर, स्पष्ट और आकर्षक हो — जैसे नेशनल ज्योग्राफिक या डिस्कवरी चैनल का वर्णन। "
    "अंग्रेज़ी शब्दों का उच्चारण भी स्पष्ट हो। "
    "गति धीमी और स्थिर रखें ताकि दर्शक समझ सकें।"
)

# ---------------------------------------------------------------------------
#  WORKSPACE CREATION
# ---------------------------------------------------------------------------


def create_science_video_workspace(
    output_dir: Path,
    script: ScienceStoryScript,
) -> Path:
    """Create the workspace directory structure for a science story video.

    Returns the path to the workspace root.
    """
    slug = _slug(script.title)
    story_id = f"science_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slug}"
    root = output_dir / "science_stories" / story_id

    # Create directory structure
    dirs = [
        root,
        root / "images",
        root / "audio",
        root / "clips",
        root / "video",
        root / "ui",
        root / "subtitles",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Save script
    script_path = root / "script.json"
    script_path.write_text(
        json.dumps(script.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Save workspace metadata
    workspace_meta = ScienceVideoWorkspace(
        story_id=story_id,
        title=script.title,
        topic=script.topic,
        workspace_path=str(root),
        created_at=datetime.now(timezone.utc).isoformat(),
        scene_count=len(script.scenes),
        total_duration_seconds=script.duration_seconds,
    )
    meta_path = root / "workspace.json"
    meta_path.write_text(
        json.dumps(workspace_meta.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Write scene manifest
    scenes_manifest = [
        {
            "scene_index": si,
            "chapter_index": s.chapter_index,
            "chapter": s.chapter,
            "title": s.title,
            "duration_seconds": s.duration_seconds,
            "narration_hi": s.narration_hi,
            "on_screen_text_hi": s.on_screen_text_hi,
            "visual_prompt": s.visual_prompt,
            "image_file": f"scene_{si + 1:04d}.png",
            "audio_file": f"scene_{si + 1:04d}.mp3",
            "clip_file": f"scene_{si + 1:04d}.mp4",
        }
        for si, s in enumerate(script.scenes)
    ]
    (root / "scene_manifest.json").write_text(
        json.dumps(scenes_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _write_audio_manifest(
        root,
        script,
        audio_status="pending",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        generated_audio=[],
        fallback_count=0,
        notes="Narration audio will be generated later or replaced with silent placeholders if needed.",
    )

    # Write storyboard HTML
    _write_storyboard_html(root, script)

    log.info(
        "Science video workspace created: %s (%d scenes, %.1f min)",
        root,
        len(script.scenes),
        script.duration_minutes,
    )
    return root


# ---------------------------------------------------------------------------
#  IMAGE GENERATION
# ---------------------------------------------------------------------------


def generate_scene_images(
    workspace_dir: Path,
    script: ScienceStoryScript,
    image_provider: ImageProvider,
    *,
    request_delay_seconds: float = 0.0,
) -> list[Path]:
    """Generate cinematic still images for each scene.

    Returns paths to all generated image files.
    """
    image_dir = workspace_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    variant = ImageVariant("16:9", YOUTUBE_WIDTH, YOUTUBE_HEIGHT, "unused")

    generated: list[Path] = []
    for index, scene in enumerate(script.scenes):
        image_path = image_dir / f"scene_{index + 1:04d}.png"
        if image_path.exists():
            generated.append(image_path)
            continue

        # Enhance the prompt for cinematic quality
        enhanced_prompt = _cinematic_prompt(scene.visual_prompt)
        try:
            image_bytes = image_provider.create(enhanced_prompt, variant)
            if not image_bytes:
                raise RuntimeError("Image provider returned empty bytes.")
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(image_bytes))
                img.verify()
            except Exception as img_exc:
                raise RuntimeError(f"Invalid image bytes returned: {img_exc}") from img_exc
            # Ensure PNG format
            if image_bytes.startswith(b"<svg") or b"<svg" in image_bytes[:200]:
                image_bytes = _convert_svg_to_png(image_bytes)
            image_path.write_bytes(image_bytes)
            generated.append(image_path)
            log.info("Generated image %d/%d: %s", index + 1, len(script.scenes), scene.title)
        except Exception as exc:
            log.error("Failed to generate image for scene %d: %s", index + 1, exc)
            # Create a placeholder gradient image
            _create_placeholder_image(image_path, scene, index)
            generated.append(image_path)
        if request_delay_seconds > 0 and index + 1 < len(script.scenes):
            time.sleep(request_delay_seconds)

    return generated


# ---------------------------------------------------------------------------
#  AUDIO GENERATION
# ---------------------------------------------------------------------------


def generate_narration_audio(
    workspace_dir: Path,
    script: ScienceStoryScript,
    settings: Settings,
    voice: str = "en-IN-PrabhatNeural",
) -> list[Path]:
    """Generate narration audio for each scene using Edge TTS.

    Args:
        workspace_dir: Path to the workspace directory.
        script: The science story script.
        settings: Pipeline settings.
        voice: Edge TTS voice name.

    Returns:
        Paths to all generated MP3 files.
    """
    audio_dir = workspace_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    use_edge_voice = True
    audio_rows: list[dict[str, Any]] = []
    fallback_count = 0
    for index, scene in enumerate(script.scenes):
        audio_path = audio_dir / f"scene_{index + 1:04d}.mp3"
        if audio_path.exists():
            generated.append(audio_path)
            audio_rows.append(
                {
                    "scene_index": index + 1,
                    "title": scene.title,
                    "audio_file": str(audio_path),
                    "status": "existing",
                    "provider": "edge",
                    "voice": settings.indian_tts_voice if use_edge_voice else voice,
                }
            )
            continue

        try:
            edge_voice = settings.indian_tts_voice if settings.indian_tts_voice else "en-IN-PrabhatNeural"
            generate_indian_voiceover(
                normalize_voice_text(scene.narration_hi),
                audio_path,
                voice=edge_voice,
            )
            generated.append(audio_path)
            audio_rows.append(
                {
                    "scene_index": index + 1,
                    "title": scene.title,
                    "audio_file": str(audio_path),
                    "status": "generated",
                    "provider": "edge",
                    "voice": settings.indian_tts_voice if use_edge_voice else voice,
                }
            )
            log.info("Generated audio %d/%d: %s", index + 1, len(script.scenes), scene.title)
        except Exception as exc:
            log.error("Failed to generate audio for scene %d: %s", index + 1, exc)
            # Create a silent audio placeholder
            _create_silent_audio(audio_path, scene.duration_seconds)
            generated.append(audio_path)
            fallback_count += 1
            audio_rows.append(
                {
                    "scene_index": index + 1,
                    "title": scene.title,
                    "audio_file": str(audio_path),
                    "status": "silent_fallback",
                    "provider": "silent",
                    "voice": "",
                    "error": str(exc),
                }
            )

    _write_audio_manifest(
        workspace_dir,
        script,
        audio_status="ready" if generated else "empty",
        provider="edge",
        voice=settings.indian_tts_voice if use_edge_voice else voice,
        generated_audio=audio_rows,
        fallback_count=fallback_count,
        notes=(
            "Edge TTS is used for every science narration path. "
            "Silent fallback files are created only when narration generation fails."
        ),
    )
    return generated


# ---------------------------------------------------------------------------
#  CLIP ASSEMBLY (FFmpeg)
# ---------------------------------------------------------------------------


def assemble_scene_clips(
    workspace_dir: Path,
    script: ScienceStoryScript,
) -> list[Path]:
    """Assemble individual scene clips by combining images, audio, and Ken Burns zoom/pan.

    For each scene:
        1. Take the still image
        2. Apply Ken Burns gentle zoom/pan
        3. Mix with narration audio
        4. Apply fade in/out

    Note: Hindi text overlays are not applied per-clip.
    Instead, SRT subtitles are burned into the final video for better
    font rendering and editing flexibility.

    Returns paths to all scene clip MP4s.
    """
    executable = _require_ffmpeg()
    clip_dir = workspace_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    image_dir = workspace_dir / "images"
    audio_dir = workspace_dir / "audio"

    generated: list[Path] = []
    total = len(script.scenes)

    for index, scene in enumerate(script.scenes):
        clip_path = clip_dir / f"scene_{index + 1:04d}.mp4"
        if clip_path.exists():
            generated.append(clip_path)
            continue

        image_path = image_dir / f"scene_{index + 1:04d}.png"
        audio_path = audio_dir / f"scene_{index + 1:04d}.mp3"

        if not image_path.exists():
            _create_placeholder_image(image_path, scene, index)
        if not audio_path.exists():
            _create_silent_audio(audio_path, scene.duration_seconds)

        duration = scene.duration_seconds
        frames = duration * FPS

        # Build FFmpeg filter
        # - Gentle Ken Burns zoom/pan
        # - Fade in/out
        # (Text overlays removed — SRT subtitles are burned into the final video instead)
        video_filter = (
            f"zoompan=z='min(zoom+0.00035,1.035)':"
            f"x='iw/2-(iw/zoom/2)+4*sin(on/30)':"
            f"y='ih/2-(ih/zoom/2)-on/15':"
            f"d={frames}:s={YOUTUBE_WIDTH}x{YOUTUBE_HEIGHT}:fps={FPS},"
            f"format=yuv420p"
        )

        fade_out_start = max(0, duration - FADE_DURATION)

        try:
            subprocess.run(
                [
                    executable,
                    "-y",
                    "-loop", "1",
                    "-i", str(image_path),
                    "-i", str(audio_path),
                    "-vf", video_filter,
                    "-af", f"afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out_start}:d=0.3",
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "22",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(clip_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            generated.append(clip_path)
            log.info("Assembled clip %d/%d: %s", index + 1, total, scene.title)
        except subprocess.CalledProcessError as exc:
            log.error("FFmpeg failed for scene %d: %s", index + 1, exc.stderr[-500:] if exc.stderr else "")
            raise

    return generated


# ---------------------------------------------------------------------------
#  FINAL VIDEO ASSEMBLY
# ---------------------------------------------------------------------------


def assemble_final_video(
    workspace_dir: Path,
    script: ScienceStoryScript,
    add_crossfade: bool = True,
) -> Path:
    """Stitch all scene clips into the final YouTube video.

    Optionally adds cross-fade transitions between scenes.
    Also generates SRT subtitles.

    Returns the path to the final assembled MP4.
    """
    executable = _require_ffmpeg()
    clip_dir = workspace_dir / "clips"
    video_dir = workspace_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    subs_dir = workspace_dir / "subtitles"
    subs_dir.mkdir(parents=True, exist_ok=True)

    # Collect all clips in order
    clip_paths = [
        clip_dir / f"scene_{i + 1:04d}.mp4"
        for i in range(len(script.scenes))
    ]

    # Check all clips exist
    missing = [str(p) for p in clip_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing clips: {', '.join(missing)}. Run clip assembly first."
        )

    final_path = video_dir / "final_video.mp4"

    if add_crossfade and len(clip_paths) > 1:
        _assemble_with_xfade(executable, clip_paths, final_path)
    else:
        # Simple concatenation (stream copy, no re-encode)
        concat_file = video_dir / "concat_list.txt"
        concat_file.write_text(
            "\n".join(f"file '{p}'" for p in clip_paths) + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                executable,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-movflags", "+faststart",
                str(final_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    # Generate and burn SRT subtitles into the final video
    srt_path = subs_dir / "subtitles.srt"
    srt_path.write_text(_generate_srt(script), encoding="utf-8")

    # Burn subtitles into video
    _burn_subtitles(executable, final_path, srt_path, subs_dir)

    # Save Python-readable SRT (for backup) — uses cumulative timestamps
    srt_json_path = subs_dir / "subtitles.json"
    cumul_start = 0
    sub_entries = []
    for i, scene in enumerate(script.scenes):
        sub_entries.append({
            "index": i + 1,
            "start": _timestamp(cumul_start),
            "end": _timestamp(cumul_start + scene.duration_seconds),
            "text": scene.narration_hi,
        })
        cumul_start += scene.duration_seconds
    srt_json_path.write_text(
        json.dumps(sub_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log.info(
        "Final video assembled: %s (%.1f min, %d scenes)",
        final_path,
        script.duration_minutes,
        len(script.scenes),
    )
    return final_path


def _assemble_with_xfade(
    executable: str,
    clip_paths: list[Path],
    output_path: Path,
    transition_duration: float = FADE_DURATION,
) -> None:
    """Assemble clips with actual cross-fade transitions using FFmpeg xfade filter.

    Uses xfade (video) and acrossfade (audio) to smoothly transition between
    consecutive scene clips. Requires re-encoding since crossfade operates on
    decoded frames.

    Args:
        executable: Path to the FFmpeg binary.
        clip_paths: List of scene clip paths to stitch.
        output_path: Destination path for the final MP4.
        transition_duration: Duration of the crossfade in seconds.
    """
    n = len(clip_paths)
    if n == 0:
        raise ValueError("No clip paths provided.")
    if n == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(clip_paths[0]), str(output_path))
        return

    # Get duration of each clip using ffprobe
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        ffprobe = executable.replace("ffmpeg", "ffprobe")

    durations: list[float] = []
    for p in clip_paths:
        result = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(p)],
            capture_output=True, text=True, check=True,
        )
        durations.append(float(result.stdout.strip()))

    # Build filter_complex for chained xfade (video) + acrossfade (audio)
    #
    # For N clips with transition duration t:
    #   Transition k (between clip_{i-1} and clip_i):
    #     offset = current_timeline_length - t
    #     where current_timeline_length = sum(durations[0..i-1]) - (i-1)*t
    #
    # Filter chain:
    #   [0:v][1:v]xfade=...:offset=o0[v01];
    #   [v01][2:v]xfade=...:offset=o1[v02];
    #   ...
    #
    # Audio crossfade uses nb_samples (sample count at 48000 Hz = default output rate).

    afade_samples = int(transition_duration * 48000)  # 48000 Hz default output

    filter_parts: list[str] = []
    v_prev = "0:v"
    a_prev = "0:a"
    current_length = durations[0]

    for i in range(1, n):
        offset = current_length - transition_duration
        v_label = f"v{i-1:02d}"
        a_label = f"a{i-1:02d}"

        # Video crossfade
        filter_parts.append(
            f"[{v_prev}][{i}:v]xfade=transition=fade:"
            f"duration={transition_duration}:offset={offset:.3f}[{v_label}]"
        )
        # Audio crossfade (nb_samples controls fade duration)
        filter_parts.append(
            f"[{a_prev}][{i}:a]acrossfade=nb_samples={afade_samples}[{a_label}]"
        )

        v_prev = v_label
        a_prev = a_label
        current_length = current_length + durations[i] - transition_duration

    filter_complex = ";".join(filter_parts)

    # Build input arguments
    cmd: list[str] = [executable, "-y"]
    for p in clip_paths:
        cmd.extend(["-i", str(p)])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{v_prev}]",
        "-map", f"[{a_prev}]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ])

    subprocess.run(cmd, check=True, capture_output=True, text=True)


# ---------------------------------------------------------------------------
#  FULL VIDEO PIPELINE
# ---------------------------------------------------------------------------


def create_science_video(
    settings: Settings,
    topic: str = "",
    target_minutes: int = 30,
    tts_voice: str = "en-IN-PrabhatNeural",
    skip_images: bool = False,
    skip_audio: bool = False,
    skip_assembly: bool = False,
) -> Path:
    """Full pipeline: generate script → create workspace → images → audio → video.

    Args:
        settings: Pipeline settings.
        topic: Science topic. Auto-selects if empty.
        target_minutes: Target video duration in minutes.
        tts_voice: Edge TTS voice name.
        skip_images: Skip image generation (use placeholders).
        skip_audio: Skip audio generation (use silence).
        skip_assembly: Skip final video assembly.

    Returns:
        Path to the workspace root directory.
    """
    from content_pipeline.bots.science_story_agent import generate_science_story_script

    # Step 1: Generate script
    log.info("Generating science story script...")
    script = generate_science_story_script(settings, topic, target_minutes)

    # Step 2: Create workspace
    log.info("Creating workspace...")
    workspace_dir = create_science_video_workspace(settings.output_dir, script)

    # Step 3: Generate images
    if not skip_images:
        log.info("Generating scene images...")
        provider = _get_image_provider(settings)
        generate_scene_images(
            workspace_dir,
            script,
            provider,
            request_delay_seconds=settings.image_request_delay_seconds,
        )

    # Step 4: Generate audio
    if not skip_audio:
        log.info("Generating narration audio...")
        generate_narration_audio(workspace_dir, script, settings, voice=tts_voice)

    # Step 5: Assemble clips
    if not skip_assembly:
        log.info("Assembling scene clips...")
        assemble_scene_clips(workspace_dir, script)

        log.info("Assembling final video...")
        final_path = assemble_final_video(workspace_dir, script)
        log.info("Final video: %s", final_path)

    return workspace_dir


# ---------------------------------------------------------------------------
#  HELPERS
# ---------------------------------------------------------------------------


def _require_ffmpeg() -> str:
    # Prefer ffmpeg-full (Homebrew keg-only) for subtitle/drawtext filter support
    # Check PATH first, then the well-known Homebrew keg-only path
    ffmpeg_full = shutil.which("ffmpeg-full")
    if ffmpeg_full:
        return ffmpeg_full
    keg_only = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg-full")
    if keg_only.exists():
        return str(keg_only)
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError(
            "FFmpeg is required for video assembly. "
            "Install with: brew install ffmpeg-full"
        )
    return executable


def _get_image_provider(settings: Settings) -> ImageProvider:
    from content_pipeline.bots.image import image_provider
    return image_provider(settings)


def _slug(text: str) -> str:
    # Replace non-alphanumeric with _, collapse consecutive _, strip leading/trailing
    result = "".join(c.lower() if c.isalnum() else "_" for c in text)
    while "__" in result:
        result = result.replace("__", "_")
    return result.strip("_")[:48]


def _timestamp(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, secs = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"


def _cinematic_prompt(base_prompt: str) -> str:
    """Enhance a scene prompt for cinematic quality."""
    enhancements = (
        "Cinematic documentary style, 4K, ultra-detailed, dramatic lighting, "
        "professional color grading, shallow depth of field, volumetric lighting, "
        "atmospheric, no text, no logo, no watermark, no people unless described, "
        "photorealistic, historical accuracy where applicable."
    )
    return f"{base_prompt.strip().rstrip('.')}. {enhancements}"

def _multiline_text(text: str, max_chars: int = 30) -> list[str]:
    """Wrap Hindi text into multiple lines for overlay."""
    lines = textwrap.wrap(text, width=max_chars) or [""]
    return lines[:4]  # Max 4 lines


def _create_placeholder_image(
    path: Path,
    scene: ScienceScene,
    index: int,
) -> None:
    """Create a simple gradient placeholder image when AI generation fails."""
    import struct
    import zlib

    width, height = YOUTUBE_WIDTH, YOUTUBE_HEIGHT

    # Create a simple gradient PNG
    def _create_gradient_png(w: int, h: int) -> bytes:
        """Create a dark gradient PNG as placeholder."""
        raw_data = b""
        for y in range(h):
            raw_data += b"\x00"  # filter byte
            for x in range(w):
                r = int(15 + (y / h) * 30)
                g = int(8 + (y / h) * 20)
                b_val = int(25 + (y / h) * 45)
                raw_data += struct.pack("BBB", r, g, b_val)

        def _chunk(chunk_type: bytes, data: bytes) -> bytes:
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        # PNG signature + IHDR + IDAT + IEND
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        idat = _chunk(b"IDAT", zlib.compress(raw_data))
        iend = _chunk(b"IEND", b"")

        return sig + ihdr + idat + iend

    path.write_bytes(_create_gradient_png(width, height))


def _burn_subtitles(
    executable: str,
    video_path: Path,
    srt_path: Path,
    subs_dir: Path,
) -> None:
    """Burn Hindi subtitles into the final video using FFmpeg's ass filter.

    Generates an ASS subtitle file directly from the SRT (with proper styling),
    then uses the `ass` filter (libass) to render subtitles into video frames.
    Styled for readability on dark cinematic content.

    Args:
        executable: Path to the FFmpeg binary (should be ffmpeg-full with libass).
        video_path: Path to the assembled (un-subtitled) video.
        srt_path: Path to the SRT subtitle file.
        subs_dir: Directory for temporary subtitle files.
    """
    ass_path = subs_dir / "subtitles.ass"
    temp_path = video_path.with_name(f"{video_path.stem}_subtitled{video_path.suffix}")

    try:
        # Read SRT and convert to ASS with proper styling
        _convert_srt_to_ass(srt_path, ass_path)

        # Burn subtitles using the ass filter
        subprocess.run(
            [
                executable, "-y",
                "-i", str(video_path),
                "-vf", f"ass={ass_path}",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "22",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(temp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        log.warning(
            "Subtitle burning failed: %s. Video will be saved without hardcoded subtitles.",
            exc.stderr[-300:] if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc),
        )
        return

    # Replace the original video with the subtitled version
    video_path.unlink()
    temp_path.rename(video_path)
    log.info("Subtitles burned into final video: %s", video_path)


def _convert_srt_to_ass(srt_path: Path, ass_path: Path) -> None:
    """Convert an SRT file to ASS format with proper styling.

    Generates a complete ASS subtitle file directly, with Devanagari MT
    font, white text with black outline, bottom-center aligned.
    """
    srt_text = srt_path.read_text(encoding="utf-8")

    # Parse SRT entries
    import re
    entries: list[dict[str, Any]] = []
    blocks = srt_text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        # First line: index (skip)
        # Second line: timestamp
        # Remaining lines: text
        match = re.match(
            r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)",
            lines[1],
        )
        if not match:
            continue
        def _to_ms(h, m, s, ms):
            return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
        start_ms = _to_ms(*match.groups()[:4])
        end_ms = _to_ms(*match.groups()[4:])
        text = "\\N".join(
            line for line in lines[2:] if line.strip()
        )
        entries.append({"start": start_ms, "end": end_ms, "text": text})

    # Generate ASS header
    width, height = YOUTUBE_WIDTH, YOUTUBE_HEIGHT
    ass_content = f"""[Script Info]
; ASS subtitle file generated by Codebuff Science Video Agent
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Devanagari MT,22,&H00FFFFFF,&H00000000,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Add dialog lines
    for entry in entries:
        def _fmt(h, m, s, ms):
            return f"{h}:{m:02d}:{s:02d}.{ms:02d}"
        start_h = entry["start"] // 3600000
        start_m = (entry["start"] % 3600000) // 60000
        start_s = (entry["start"] % 60000) // 1000
        start_ms = (entry["start"] % 1000) // 10
        end_h = entry["end"] // 3600000
        end_m = (entry["end"] % 3600000) // 60000
        end_s = (entry["end"] % 60000) // 1000
        end_ms = (entry["end"] % 1000) // 10
        start_str = f"{start_h}:{start_m:02d}:{start_s:02d}.{start_ms:02d}"
        end_str = f"{end_h}:{end_m:02d}:{end_s:02d}.{end_ms:02d}"
        ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{entry['text']}\n"

    ass_path.write_text(ass_content, encoding="utf-8")
    log.info("ASS subtitle file generated: %s (%d entries)", ass_path, len(entries))


def _create_silent_audio(path: Path, duration_seconds: int) -> None:
    """Create a silent MP3 placeholder when TTS generation fails."""
    executable = _require_ffmpeg()
    subprocess.run(
        [
            executable,
            "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration_seconds),
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_audio_manifest(
    workspace_dir: Path,
    script: ScienceStoryScript,
    *,
    audio_status: str,
    provider: str,
    voice: str,
    generated_audio: list[dict[str, Any]],
    fallback_count: int,
    notes: str,
) -> Path:
    audio_dir = workspace_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "story_title": script.title,
        "topic": script.topic,
        "scene_count": len(script.scenes),
        "duration_seconds": script.duration_seconds,
        "audio_status": audio_status,
        "provider": provider,
        "voice": voice,
        "fallback_count": fallback_count,
        "generated_audio": generated_audio,
        "notes": notes,
    }
    manifest_path = audio_dir / "audio_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    status_html = audio_dir / "audio_status.html"
    status_html.write_text(_audio_status_html(manifest), encoding="utf-8")
    return manifest_path


def _audio_status_html(manifest: dict[str, Any]) -> str:
    rows = []
    for row in manifest.get("generated_audio", []):
        rows.append(
            "<li>"
            f"Scene {escape(str(row.get('scene_index', '')))}: "
            f"{escape(str(row.get('title', '')))} "
            f"({escape(str(row.get('status', '')))}, {escape(str(row.get('provider', '')))} / {escape(str(row.get('voice', '')) or 'silent')})"
            "</li>"
        )
    if not rows:
        rows.append("<li>No audio files tracked yet.</li>")
    return f"""<section style="background:#111827;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Science audio</div>
  <div style="margin-top:6px;font-size:20px;font-weight:800;">{escape(str(manifest.get('audio_status') or 'unknown'))}</div>
  <div style="margin-top:4px;color:#94a3b8;">Provider: {escape(str(manifest.get('provider') or 'unknown'))} · Voice: {escape(str(manifest.get('voice') or 'unknown'))} · Fallbacks: {escape(str(manifest.get('fallback_count') or 0))}</div>
  <div style="margin-top:12px;color:#cbd5e1;">{escape(str(manifest.get('notes') or ''))}</div>
  <ul style="margin:14px 0 0;padding-left:18px;color:#cbd5e1;">{''.join(rows)}</ul>
</section>"""


def _convert_svg_to_png(svg_bytes: bytes) -> bytes:
    """Convert SVG bytes to PNG bytes using CairoSVG."""
    import cairosvg
    return cairosvg.svg2png(
        bytestring=svg_bytes,
        output_width=YOUTUBE_WIDTH,
        output_height=YOUTUBE_HEIGHT,
    )


def _generate_srt(script: ScienceStoryScript) -> str:
    """Generate SRT subtitle content from the script."""
    lines: list[str] = []
    start = 0
    for index, scene in enumerate(script.scenes, start=1):
        end = start + scene.duration_seconds
        lines.extend(
            [
                str(index),
                f"{_timestamp(start)} --> {_timestamp(end)}",
                scene.narration_hi,
                "",
            ]
        )
        start = end
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  STORYBOARD HTML
# ---------------------------------------------------------------------------


def _write_storyboard_html(workspace_dir: Path, script: ScienceStoryScript) -> None:
    """Write a visual storyboard HTML page for the workspace."""
    ui_dir = workspace_dir / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)

    chapter_rows: list[str] = []
    for ci, chapter in enumerate(script.chapters):
        chapter_scenes = script.scenes_for_chapter(ci)
        chapter_duration = sum(s.duration_seconds for s in chapter_scenes)
        scene_rows = "\n".join(
            f"""<tr>
            <td class="num">{s.scene_index + 1}</td>
            <td class="time">{s.duration_seconds}s</td>
            <td>{escape(s.title)}</td>
            <td class="hi">{escape(s.narration_hi[:100])}...</td>
            <td class="hi">{escape(s.on_screen_text_hi)}</td>
          </tr>"""
            for s in chapter_scenes
        )
        chapter_rows.append(f"""<div class="chapter">
        <h2>{escape(f'Chapter {ci + 1}: {chapter}')} <span class="meta">{len(chapter_scenes)} scenes / {chapter_duration}s</span></h2>
        <table>
          <thead><tr><th>#</th><th>Dur</th><th>Title</th><th>Narration (Hindi)</th><th>On Screen (Hindi)</th></tr></thead>
          <tbody>{scene_rows}</tbody>
        </table>
      </div>""")

    scene_count = len(script.scenes)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(script.title)} - Science Storyboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0a0a14; color: #f0ede8; font-family: Avenir Next, Helvetica, Arial, sans-serif; padding: 30px; }}
    h1 {{ font-size: 36px; margin-bottom: 6px; }}
    .tagline {{ color: #9a9abf; font-size: 18px; margin-bottom: 24px; }}
    .stats {{ display: flex; gap: 14px; margin-bottom: 28px; flex-wrap: wrap; }}
    .stat {{ background: #16162a; border: 1px solid #2f2f5a; border-radius: 12px; padding: 12px 20px; }}
    .stat .val {{ font-size: 28px; font-weight: 800; color: #f0b34b; }}
    .stat .lbl {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #7878a0; }}
    .chapter {{ background: #12121e; border: 1px solid #2a2a50; border-radius: 16px; padding: 22px; margin-bottom: 22px; }}
    .chapter h2 {{ font-size: 22px; margin-bottom: 14px; }}
    .chapter h2 .meta {{ font-size: 14px; color: #7878a0; font-weight: 400; margin-left: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th {{ text-align: left; padding: 8px 10px; border-bottom: 2px solid #2f2f5a; color: #7878a0; text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #1e1e3a; }}
    .num {{ width: 30px; color: #7878a0; }}
    .time {{ width: 50px; color: #f0b34b; font-weight: 700; }}
    .hi {{ color: #b0b0d0; }}
    tr:hover td {{ background: #1a1a32; }}
  </style>
</head>
<body>
  <h1>{escape(script.title)}</h1>
  <p class="tagline">{escape(script.tagline)}</p>
  <div class="stats">
    <div class="stat"><div class="val">{scene_count}</div><div class="lbl">Scenes</div></div>
    <div class="stat"><div class="val">{script.duration_minutes:.1f}</div><div class="lbl">Minutes</div></div>
    <div class="stat"><div class="val">{len(script.chapters)}</div><div class="lbl">Chapters</div></div>
  </div>
  {''.join(chapter_rows)}
  <p class="tagline" style="margin-top:30px">Topic: {escape(script.topic)}</p>
</body>
</html>"""

    (ui_dir / "storyboard.html").write_text(html, encoding="utf-8")
