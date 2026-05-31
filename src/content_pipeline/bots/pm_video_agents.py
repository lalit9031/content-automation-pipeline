from __future__ import annotations

import base64
import math
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

try:
    import cairosvg
except ImportError:  # pragma: no cover - optional dependency
    cairosvg = None

from content_pipeline.bots.linkedin_video import render_video_linkedin_post
from content_pipeline.bots.image import ImageProvider, ImageVariant
from content_pipeline.bots.pm_slide_router import build_slide_plan
from content_pipeline.content_history import ContentHistory, record_history_entry, select_unused_topics
from content_pipeline.models import VideoClip, VideoEpisode
from content_pipeline.storage import LocalDailyStorage
from content_pipeline.bots.pm_video_templates import (
    PMVideoTemplate,
    PM_COURSE_TEMPLATE,
    get_pm_video_template,
    list_pm_video_templates,
    render_template_gallery_html,
    select_pm_video_template,
)


SHARED_PM_VIDEO_PROMPT = (
    "You are creating practical, energetic videos for project managers, PMOs, "
    "Scrum Masters, delivery managers, product owners, business analysts, and "
    "Agile leaders. Choose timely, useful topics around AI in project delivery, "
    "PMP, PMI, Scrum, Agile, SAFe, Jira, Microsoft Copilot, governance, delivery "
    "risk, PM careers, stakeholder management, and modern management tools. "
    "Make the topic interesting without inventing statistics or unverified news. "
    "Teach with concrete examples, clear takeaways, and a professional Indian "
    "English voice. Do not use copyrighted logos, brand UI screenshots, or "
    "watermarks in generated visuals."
)

SUBSCRIBE_CTA = (
    "Subscribe for latest informative videos. Like the video; one like "
    "motivates me to create more. Ask questions in comments. I will reply, "
    "or answer them in a live session. Hit the bell icon for notifications."
)
SHORTS_SUBSCRIBE_CTA = (
    "Subscribe for latest informative videos. Like the video. Ask your "
    "questions in comments; I will reply for sure."
)

TRENDING_TOPIC_BANK = [
    "AI agents inside Jira: what changes for Scrum Masters and delivery managers",
    "PMI Infinity and AI governance: how project managers should ask better questions",
    "Microsoft Copilot for PMO reporting: from meeting notes to executive updates",
    "PMP 2026 readiness: skills project managers should build before the exam refresh",
    "SAFe teams and AI copilots: where automation helps and where governance must stay human",
    "Agile metrics in the AI era: cycle time, escaped defects, and delivery confidence",
    "Jira, Confluence, and Rovo-style agents: how to assign work to humans and AI safely",
    "PMO roles in 2026: moving from status collection to decision intelligence",
    "Scrum Master career shift: facilitation, flow metrics, and AI-enabled coaching",
    "Delivery managers and AI risk: privacy, vendor lock-in, hallucinations, and audit trails",
    "Product owner workflow with AI: better acceptance criteria without losing accountability",
    "Hybrid Agile with AI tools: keeping scope, risk, and change control visible",
]

DEFAULT_HASHTAGS = [
    "#ProjectManagement",
    "#PMP",
    "#ScrumMaster",
    "#Agile",
    "#PMO",
    "#Jira",
    "#MicrosoftCopilot",
    "#AI",
]
NARRATION_SPEED_BOOST = 1.0
YOUTUBE_NARRATION_SPEED_BOOST = 1.06
BRAND_LOGO_PATH = Path(__file__).resolve().parents[3] / "assets" / "brand" / "tech_with_lalit_logo.png"
TALKING_AVATAR_GIF_PATH = Path(__file__).resolve().parents[3] / "assets" / "brand" / "talking_avatar.gif"
DEFAULT_VOICE_SAMPLE_PATH = Path(__file__).resolve().parents[3] / "assets" / "voice" / "lalit_voice_sample.ogg"


@dataclass(frozen=True)
class PMVideoAgent:
    id: str
    name: str
    output_folder: str
    aspect: str
    target_duration_seconds: int
    scenes: int

    @property
    def prompt(self) -> str:
        return SHARED_PM_VIDEO_PROMPT

    def create_episode(
        self,
        topic: str,
        day: str,
        index: int,
        template_mode: str = "random",
        openai_key_count: int = 4,
        gemini_key_count: int = 4,
    ) -> VideoEpisode:
        if self.aspect not in {"shorts", "landscape"}:
            raise ValueError("aspect must be 'shorts' or 'landscape'.")
        template = select_pm_video_template(topic, day, template_mode)
        width, height = (1080, 1920) if self.aspect == "shorts" else (1280, 720)
        clips = _clips_for_topic(
            topic=topic,
            agent=self,
            day=day,
            width=width,
            height=height,
            template_mode=template_mode,
            openai_key_count=openai_key_count,
            gemini_key_count=gemini_key_count,
        )
        title = _title_for(topic, self.aspect, index)
        primary_template = get_pm_video_template(clips[0].template_id) if clips and clips[0].template_id else template
        return VideoEpisode(
            episode_id=f"{day}_{self.id}_{index:02d}_{_slug(topic)}",
            title=title,
            description=f"{self.name} episode generated from the shared PM video prompt.",
            aspect=self.aspect,
            width=width,
            height=height,
            clips=clips,
            youtube_title=title,
            youtube_description=_description_for(topic, self.aspect),
            hashtags=list(DEFAULT_HASHTAGS),
            visual_template_id=primary_template.template_id,
            visual_template_name=primary_template.name,
            visual_template_layout=primary_template.layout,
        )


SHORTS_AGENT = PMVideoAgent(
    id="shorts_agent",
    name="PM Shorts Agent",
    output_folder="shorts",
    aspect="shorts",
    target_duration_seconds=70,
    scenes=10,
)

YOUTUBE_AGENT = PMVideoAgent(
    id="youtube_agent",
    name="PM YouTube Agent",
    output_folder="youtubeVideo",
    aspect="landscape",
    target_duration_seconds=420,
    scenes=35,
)


def agent_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": SHORTS_AGENT.id,
            "name": SHORTS_AGENT.name,
            "output_folder": SHORTS_AGENT.output_folder,
            "format": "65-70 second vertical Shorts",
            "shared_prompt": SHORTS_AGENT.prompt,
        },
        {
            "id": YOUTUBE_AGENT.id,
            "name": YOUTUBE_AGENT.name,
            "output_folder": YOUTUBE_AGENT.output_folder,
            "format": "5-8 minute landscape YouTube video",
            "shared_prompt": YOUTUBE_AGENT.prompt,
        },
    ]


def daily_pm_video_topics(day: str, total: int = 4, used_topics: set[str] | None = None) -> list[str]:
    date.fromisoformat(day)
    offset = date.fromisoformat(day).toordinal() % len(TRENDING_TOPIC_BANK)
    rotated = TRENDING_TOPIC_BANK[offset:] + TRENDING_TOPIC_BANK[:offset]
    if not used_topics:
        return rotated[:total]
    selected = select_unused_topics(rotated, used_topics)
    if len(selected) >= total:
        return selected[:total]
    fallback = [topic for topic in rotated if topic not in selected]
    return [*selected, *fallback][:total]


def create_daily_pm_video_batch(
    output_dir: Path,
    day: str,
    shorts_count: int = 2,
    youtube_count: int = 2,
    render_videos: bool = False,
    template_mode: str = "random",
    openai_api_key: str = "",
    tts_voice: str = "echo",
    voice_sample_path: Path | None = None,
    voiceover_file: Path | None = None,
    youtube_channel_url: str = "",
    openai_key_count: int = 4,
    gemini_key_count: int = 4,
    preview_without_audio: bool = False,
    scene_image_provider: ImageProvider | None = None,
) -> list[Path]:
    history = ContentHistory.load(output_dir)
    topics = daily_pm_video_topics(day, shorts_count + youtube_count, used_topics=history.topic_keys())
    written: list[Path] = []
    manifest: dict[str, Any] = {
        "date": day,
        "shared_prompt": SHARED_PM_VIDEO_PROMPT,
        "closing_cta": SUBSCRIBE_CTA,
        "agents": agent_registry(),
        "template_mode": template_mode,
        "template_catalog_size": len(list_pm_video_templates()),
        "slide_agent_count": 3 if shorts_count and not youtube_count else 4,
        "episodes": [],
        "history_file": str(output_dir / "content_history.json"),
    }

    for index in range(shorts_count):
        episode = SHORTS_AGENT.create_episode(
            topics[index],
            day,
            index + 1,
            template_mode=template_mode,
            openai_key_count=openai_key_count,
            gemini_key_count=gemini_key_count,
        )
        paths = create_pm_video_workspace(
            output_dir,
            SHORTS_AGENT,
            episode,
            render_video=render_videos,
            openai_api_key=openai_api_key,
            tts_voice=tts_voice,
            voice_sample_path=voice_sample_path,
            voiceover_file=voiceover_file,
            youtube_channel_url=youtube_channel_url,
            preview_without_audio=preview_without_audio,
            scene_image_provider=scene_image_provider,
        )
        written.extend(paths)
        manifest["episodes"].append(_manifest_row(SHORTS_AGENT, episode, paths[0].parent))
        record_history_entry(
            output_dir,
            date=day,
            kind="video_episode",
            topic=topics[index],
            title=episode.youtube_title,
            platform="youtube_shorts",
            reference=episode.youtube_title,
            url=youtube_channel_url,
            source=SHORTS_AGENT.name,
        )

    start = shorts_count
    for index in range(youtube_count):
        episode = YOUTUBE_AGENT.create_episode(
            topics[start + index],
            day,
            index + 1,
            template_mode=template_mode,
            openai_key_count=openai_key_count,
            gemini_key_count=gemini_key_count,
        )
        paths = create_pm_video_workspace(
            output_dir,
            YOUTUBE_AGENT,
            episode,
            render_video=render_videos,
            openai_api_key=openai_api_key,
            tts_voice=tts_voice,
            voice_sample_path=voice_sample_path,
            voiceover_file=voiceover_file,
            youtube_channel_url=youtube_channel_url,
            preview_without_audio=preview_without_audio,
            scene_image_provider=scene_image_provider,
        )
        written.extend(paths)
        manifest["episodes"].append(_manifest_row(YOUTUBE_AGENT, episode, paths[0].parent))
        record_history_entry(
            output_dir,
            date=day,
            kind="video_episode",
            topic=topics[start + index],
            title=episode.youtube_title,
            platform="youtube_full",
            reference=episode.youtube_title,
            url=youtube_channel_url,
            source=YOUTUBE_AGENT.name,
        )

    manifest_path = output_dir / "pm_video_agents" / day / "daily_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written.append(manifest_path)
    return written


def create_pm_video_workspace(
    output_dir: Path,
    agent: PMVideoAgent,
    episode: VideoEpisode,
    render_video: bool = False,
    openai_api_key: str = "",
    tts_voice: str = "echo",
    voice_sample_path: Path | None = None,
    voiceover_file: Path | None = None,
    youtube_channel_url: str = "",
    preview_without_audio: bool = False,
    scene_image_provider: ImageProvider | None = None,
) -> list[Path]:
    voice_sample_path = voice_sample_path or _default_voice_sample_path()
    root = output_dir / agent.output_folder / episode.episode_id[:10] / episode.episode_id
    clips_inbox = root / "clips" / "inbox"
    thumbnail = root / "thumbnail"
    video = root / "video"
    ui = root / "ui"
    audio_reference = root / "audio" / "reference"
    for directory in (clips_inbox, thumbnail, video, ui, audio_reference):
        directory.mkdir(parents=True, exist_ok=True)
    (clips_inbox / ".gitkeep").write_text("", encoding="utf-8")

    subtitles = _subtitle_srt(episode)
    paths = [
        _write_json(root / "episode.json", _episode_dict(episode)),
        _write_json(root / "agent.json", {"agent": asdict(agent), "shared_prompt": agent.prompt}),
        _write_json(root / "slide_plan.json", _slide_plan_dict(episode)),
        _write_json(root / "lane_batches.json", _lane_batches_dict(episode)),
        _write_text(root / "script.md", _script_markdown(episode, agent)),
        _write_json(root / "scene_prompts.json", _prompt_rows(episode)),
        _write_text(root / "clip_drop_guide.md", _clip_drop_guide(episode)),
        _write_text(root / "youtube_metadata.md", _metadata_markdown(episode)),
        _write_text(video / "subtitles.srt", subtitles),
        _write_text(thumbnail / "subtitles.srt", subtitles),
        _write_text(thumbnail / "metadata.doc", _metadata_doc(episode, agent)),
        _write_text(thumbnail / "thumbnail_prompt.txt", _thumbnail_prompt(episode, agent)),
        _write_text(thumbnail / "thumbnail.svg", _thumbnail_svg(episode, agent)),
        _write_text(audio_reference / "voice_reference.md", _voice_reference_doc(voice_sample_path)),
        _write_text(ui / "index.html", _dashboard_html(episode, agent, root)),
    ]
    audio_manifest = _audio_reference_manifest(
        episode,
        agent,
        openai_api_key=openai_api_key,
        tts_voice=tts_voice,
        voice_sample_path=voice_sample_path,
        voiceover_file=voiceover_file,
        preview_without_audio=preview_without_audio,
    )
    paths.extend(
        [
            _write_json(audio_reference / "audio_manifest.json", audio_manifest),
            _write_text(audio_reference / "audio_status.html", _audio_reference_status_html(audio_manifest)),
        ]
    )
    paths.append(
        _write_text(
            root / "publish" / "linkedin_post.md",
            _linkedin_post_markdown(episode, agent, youtube_channel_url),
        )
    )
    paths.append(
        _write_json(
            root / "publish" / "linkedin_post.json",
            _linkedin_post_payload(episode, agent, youtube_channel_url),
        )
    )
    paths.append(
        _write_text(
            root / "publish" / "telegram_message.txt",
            _telegram_message(episode, youtube_channel_url),
        )
    )
    paths.append(
        render_video_linkedin_post(
            episode,
            LocalDailyStorage(output_dir),
            reference_label="Shorts reference" if agent.aspect == "shorts" else "Full video reference",
            reference_url=youtube_channel_url,
        )
    )
    if voice_sample_path:
        paths.append(_copy_voice_sample(audio_reference, voice_sample_path))
    if render_video:
        paths.append(
        render_pm_episode_preview(
            root,
            episode,
            agent,
            openai_api_key=openai_api_key,
            tts_voice=tts_voice,
            voiceover_file=voiceover_file,
            preview_without_audio=preview_without_audio,
            scene_image_provider=scene_image_provider,
        )
        )
    return paths


def render_pm_episode_preview(
    root: Path,
    episode: VideoEpisode,
    agent: PMVideoAgent,
    openai_api_key: str = "",
    tts_voice: str = "echo",
    voiceover_file: Path | None = None,
    preview_without_audio: bool = False,
    scene_image_provider: ImageProvider | None = None,
) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to render PM videos. Install it with: brew install ffmpeg")
    if cairosvg is None:
        raise RuntimeError("cairosvg is required to render PM video previews.")

    scene_dir = root / "video" / "scenes"
    clip_dir = root / "video" / "rendered_clips"
    scene_dir.mkdir(parents=True, exist_ok=True)
    clip_dir.mkdir(parents=True, exist_ok=True)

    visual_paths: list[Path] = []
    audio_paths: list[Path] = []
    art_paths: list[Path | None] = []
    for index, clip in enumerate(episode.clips, start=1):
        art_path = None
        if scene_image_provider is not None:
            art_path = _render_scene_art(root, episode, clip, index, scene_image_provider)
        art_paths.append(art_path)
        svg = _scene_svg(episode, agent, clip, index, art_path=art_path)
        svg_path = scene_dir / f"scene_{index:02d}.svg"
        png_path = scene_dir / f"scene_{index:02d}.png"
        visual_path = clip_dir / clip.expected_file
        svg_path.write_text(svg, encoding="utf-8")
        png_path.write_bytes(
            cairosvg.svg2png(
                bytestring=svg.encode("utf-8"),
                output_width=episode.width,
                output_height=episode.height,
            )
        )
        frames = clip.duration_seconds * 30
        fade_out = max(0, clip.duration_seconds - 0.35)
        subprocess.run(
            [
                executable,
                "-y",
                "-loop",
                "1",
                "-i",
                str(png_path),
                "-vf",
                (
                    f"scale={episode.width}:{episode.height},"
                    f"zoompan=z='min(zoom+0.0002,1.02)':d={frames}:"
                    f"s={episode.width}x{episode.height}:fps=30,"
                    f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out}:d=0.35,"
                    "format=yuv420p"
                ),
                "-t",
                str(clip.duration_seconds),
                "-an",
                "-c:v",
                "libx264",
                "-movflags",
                "+faststart",
                str(visual_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if episode.aspect == "shorts" and _talking_avatar_enabled():
            visual_path = _overlay_talking_avatar(
                executable,
                clip_dir,
                visual_path,
                clip.duration_seconds,
                index,
            )
        visual_paths.append(visual_path)
        if not voiceover_file:
            audio_paths.append(
                _render_scene_audio(
                    root,
                    clip,
                    index,
                    speed_boost=(
                        NARRATION_SPEED_BOOST
                        if episode.aspect == "shorts"
                        else YOUTUBE_NARRATION_SPEED_BOOST
                    ),
                    openai_api_key=openai_api_key,
                    tts_voice=tts_voice,
                    preview_without_audio=preview_without_audio,
                )
            )

    concat_path = root / "video" / "pm_video_scenes.txt"
    concat_path.write_text("\n".join(f"file '{path}'" for path in visual_paths) + "\n", encoding="utf-8")
    silent_path = root / "video" / "episode_review_silent.mp4"
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
            str(silent_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    narration_path = (
        _prepare_user_voiceover(root, voiceover_file, episode.duration_seconds)
        if voiceover_file
        else _concat_audio(root, audio_paths)
    )
    music_path = _render_background_music(root, episode.duration_seconds)
    mixed_audio_path = _mix_audio(root, narration_path, music_path, episode.duration_seconds)
    output_path = root / "video" / "episode_review.mp4"
    subprocess.run(
        [
            executable,
            "-y",
            "-i",
            str(silent_path),
            "-i",
            str(mixed_audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _render_scene_audio(
    root: Path,
    clip: VideoClip,
    index: int,
    speed_boost: float,
    openai_api_key: str = "",
    tts_voice: str = "echo",
    preview_without_audio: bool = False,
) -> Path:
    raw_dir = root / "audio" / "raw"
    synced_dir = root / "audio" / "synced"
    raw_dir.mkdir(parents=True, exist_ok=True)
    synced_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"scene_{index:02d}.mp3"
    if not openai_api_key:
        if preview_without_audio:
            return _silent_scene_audio(root, clip.duration_seconds, index)
        raise RuntimeError("OpenAI TTS is required for PM narration.")
    try:
        _openai_tts(clip.narration, raw_path, openai_api_key, tts_voice)
    except RuntimeError:
        if preview_without_audio:
            return _silent_scene_audio(root, clip.duration_seconds, index)
        raise
    synced_path = synced_dir / f"scene_{index:02d}.m4a"
    _sync_audio_to_duration(raw_path, synced_path, clip.duration_seconds, speed_boost)
    return synced_path


def _silent_scene_audio(root: Path, duration: int, index: int) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to create silent PM review audio.")
    synced_dir = root / "audio" / "synced"
    synced_dir.mkdir(parents=True, exist_ok=True)
    output_path = synced_dir / f"scene_{index:02d}.m4a"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            str(duration),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _openai_tts(text: str, output_path: Path, api_key: str, voice: str) -> None:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("OpenAI package is required for polished PM narration.") from exc
    try:
        result = OpenAI(api_key=api_key).audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            instructions=(
                "Speak in a warm, energetic Indian English male business educator voice. "
                "Use the creator's supplied voice sample only as a style reference, not "
                "as an exact clone: natural Indian cadence, confident but friendly tone, "
                "clear PM trainer delivery, medium pace, crisp emphasis on key terms, "
                "and no dramatic announcer style. Match a finished project management "
                "YouTube explainer: clear, practical, trustworthy, and conversational. "
                "Keep the pace engaging, never stretched, and pause briefly after questions."
            ),
        )
    except Exception as exc:
        raise RuntimeError("OpenAI TTS failed; refusing to render low-quality fallback narration.") from exc
    output_path.write_bytes(result.read())
    _require_valid_audio(output_path, "OpenAI TTS")


def _local_say_tts(text: str, output_path: Path) -> None:
    say_executable = shutil.which("say")
    espeak_executable = shutil.which("espeak-ng") or shutil.which("espeak")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to create PM narration audio.")
    if espeak_executable:
        wav_path = output_path.with_suffix(".wav")
        subprocess.run(
            [espeak_executable, "-s", "178", "-v", "en-us+f3", "-w", str(wav_path), text],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [ffmpeg, "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-q:a", "4", str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        wav_path.unlink(missing_ok=True)
        _require_valid_audio(output_path, "espeak-ng TTS")
        return
    if not say_executable:
        raise RuntimeError("No local TTS engine found. Install espeak-ng or use --openai-tts.")
    aiff_path = output_path.with_suffix(".aiff")
    subprocess.run(
        [say_executable, "-v", "Samantha", "-r", "185", "-o", str(aiff_path), text],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [ffmpeg, "-y", "-i", str(aiff_path), "-c:a", "libmp3lame", "-q:a", "4", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    aiff_path.unlink(missing_ok=True)
    _require_valid_audio(output_path, "macOS say TTS")


def _sync_audio_to_duration(input_path: Path, output_path: Path, duration: int, speed_boost: float) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to sync PM video audio.")
    source_duration = _audio_duration(input_path)
    if source_duration <= 0:
        raise RuntimeError(f"Narration audio was not created correctly: {input_path}")
    target_speech_duration = max(1, duration / max(1.0, speed_boost))
    speed = max(1.0, min(2.0, source_duration / target_speech_duration))
    filters = _atempo_filters(speed)
    filtered_duration = source_duration / speed
    if filtered_duration <= duration:
        filters.append(f"apad=whole_dur={duration}")
    filters.append(f"atrim=0:{duration}")
    filters.append("asetpts=N/SR/TB")
    subprocess.run(
        [
            executable,
            "-y",
            "-i",
            str(input_path),
            "-af",
            ",".join(filters),
            "-t",
            str(duration),
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _concat_audio(root: Path, audio_paths: list[Path]) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to concatenate PM video audio.")
    concat_path = root / "audio" / "audio_scenes.txt"
    concat_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path.write_text("\n".join(f"file '{path}'" for path in audio_paths) + "\n", encoding="utf-8")
    output_path = root / "audio" / "narration.m4a"
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
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _copy_voice_sample(destination: Path, source: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Voice sample not found: {source}")
    output_path = destination / f"creator_voice_sample{source.suffix.lower() or '.audio'}"
    shutil.copyfile(source, output_path)
    return output_path


def _default_voice_sample_path() -> Path | None:
    return DEFAULT_VOICE_SAMPLE_PATH if DEFAULT_VOICE_SAMPLE_PATH.exists() else None


def _voice_reference_doc(voice_sample_path: Path | None) -> str:
    if not voice_sample_path:
        return (
            "# Voice reference\n\n"
            "No creator voice sample was supplied for this episode.\n\n"
            "To use your own voice as final narration, record the complete script "
            "and pass it with `--voiceover-file` while rendering.\n"
        )
    duration = _audio_duration(voice_sample_path)
    duration_line = f"- Duration: {duration:.2f} seconds\n" if duration > 0 else ""
    return (
        "# Voice reference\n\n"
        f"- Source: {voice_sample_path}\n"
        f"{duration_line}"
        "- Usage: this file is stored as the creator voice reference. It is not "
        "stretched across a full video, because that would create unnatural audio.\n"
        "- Final narration: record the complete script and render with `--voiceover-file`.\n"
    )


def _audio_reference_manifest(
    episode: VideoEpisode,
    agent: PMVideoAgent,
    *,
    openai_api_key: str,
    tts_voice: str,
    voice_sample_path: Path | None,
    voiceover_file: Path | None,
    preview_without_audio: bool,
) -> dict[str, Any]:
    narration_mode = "openai_tts" if openai_api_key else "preview_without_audio" if preview_without_audio else "unavailable"
    return {
        "episode_id": episode.episode_id,
        "agent": agent.name,
        "aspect": agent.aspect,
        "scene_count": len(episode.clips),
        "duration_seconds": episode.duration_seconds,
        "narration_mode": narration_mode,
        "tts_voice": tts_voice,
        "voice_sample_reference": str(voice_sample_path) if voice_sample_path else "",
        "voiceover_file": str(voiceover_file) if voiceover_file else "",
        "preview_without_audio": preview_without_audio,
        "voice_sample_copied": bool(voice_sample_path),
        "note": (
            "PM narration is OpenAI-first. The stored sample is a creator reference, "
            "and preview_without_audio enables a silent review path when rendering is not desired."
        ),
    }


def _audio_reference_status_html(manifest: dict[str, Any]) -> str:
    badge = "OpenAI narration" if manifest.get("narration_mode") == "openai_tts" else "Silent preview"
    return f"""<section style="background:#111827;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">PM audio</div>
  <div style="margin-top:6px;font-size:20px;font-weight:800;">{escape(badge)}</div>
  <div style="margin-top:4px;color:#94a3b8;">Voice sample: {escape(str(manifest.get('voice_sample_reference') or 'none'))}</div>
  <div style="margin-top:4px;color:#94a3b8;">Voiceover file: {escape(str(manifest.get('voiceover_file') or 'none'))}</div>
  <div style="margin-top:4px;color:#94a3b8;">TTS voice: {escape(str(manifest.get('tts_voice') or ''))}</div>
  <div style="margin-top:10px;color:#cbd5e1;">{escape(str(manifest.get('note') or ''))}</div>
</section>"""


def _prepare_user_voiceover(root: Path, source: Path, duration: int) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Voiceover file not found: {source}")
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to prepare user voiceover audio.")
    source_duration = _audio_duration(source)
    if source_duration <= 0:
        raise RuntimeError(f"Voiceover audio is invalid: {source}")
    minimum_duration = duration * 0.75
    maximum_duration = duration * 1.35
    if source_duration < minimum_duration:
        raise RuntimeError(
            "Voiceover is too short for this video. "
            f"Need at least {minimum_duration:.1f}s for a {duration}s video; "
            f"got {source_duration:.1f}s from {source}."
        )
    if source_duration > maximum_duration:
        raise RuntimeError(
            "Voiceover is too long for this video. "
            f"Keep it under {maximum_duration:.1f}s for a {duration}s video; "
            f"got {source_duration:.1f}s from {source}."
        )
    output_path = root / "audio" / "creator_voiceover.m4a"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    speed = max(0.85, min(1.2, source_duration / duration))
    filters = _atempo_filters(speed)
    filtered_duration = source_duration / speed
    if filtered_duration <= duration:
        filters.append(f"apad=whole_dur={duration}")
    filters.extend([f"atrim=0:{duration}", "asetpts=N/SR/TB"])
    subprocess.run(
        [
            executable,
            "-y",
            "-i",
            str(source),
            "-af",
            ",".join(filters),
            "-t",
            str(duration),
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    _require_valid_audio(output_path, "creator voiceover")
    return output_path


def _overlay_talking_avatar(
    executable: str,
    clip_dir: Path,
    visual_path: Path,
    duration: int,
    index: int,
) -> Path:
    output_path = clip_dir / f"scene_{index:02d}_avatar.mp4"
    subprocess.run(
        [
            executable,
            "-y",
            "-i",
            str(visual_path),
            "-stream_loop",
            "-1",
            "-i",
            str(TALKING_AVATAR_GIF_PATH),
            "-filter_complex",
            (
                "[1:v]fps=30,crop=560:620:270:260,scale=430:-1,format=rgba,"
                "colorkey=0x00ff00:0.34:0.12,colorkey=0xffffff:0.08:0.04[avatar];"
                "[0:v][avatar]overlay=612:850:shortest=1:format=auto,format=yuv420p[out]"
            ),
            "-map",
            "[out]",
            "-t",
            str(duration),
            "-an",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _render_background_music(root: Path, duration: int) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to render background audio.")
    output_path = root / "audio" / "background_music.m4a"
    _silent_audio(output_path, duration)
    return output_path


def _render_background_tone(root: Path, duration: int) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to render background audio.")
    output_path = root / "audio" / "background_music.m4a"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=174:sample_rate=44100:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=261.63:sample_rate=44100:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=392:sample_rate=44100:duration={duration}",
            "-filter_complex",
            (
                "[0:a][1:a][2:a]amix=inputs=3:normalize=0,"
                f"volume=0.045,afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, duration - 1.5)}:d=1.5[out]"
            ),
            "-map",
            "[out]",
            "-t",
            str(duration),
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _mix_audio(root: Path, narration_path: Path, music_path: Path, duration: int) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to mix PM video audio.")
    output_path = root / "audio" / "final_mix.m4a"
    subprocess.run(
        [
            executable,
            "-y",
            "-i",
            str(narration_path),
            "-i",
            str(music_path),
            "-filter_complex",
            (
                "[0:a]volume=1.4[n];"
                "[1:a]volume=0.0[m];"
                "[n][m]amix=inputs=2:duration=first:dropout_transition=2,"
                "loudnorm=I=-18:TP=-3:LRA=11,alimiter=limit=0.85,"
                "aformat=sample_rates=48000:channel_layouts=stereo[out]"
            ),
            "-map",
            "[out]",
            "-t",
            str(duration),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _require_valid_audio(path: Path, source: str) -> None:
    duration = _audio_duration(path)
    if duration <= 0.1:
        raise RuntimeError(f"{source} produced invalid audio: {path}")


def _silent_audio(output_path: Path, duration: int) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to create fallback audio.")
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            str(duration),
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _audio_duration(path: Path) -> float:
    executable = shutil.which("ffprobe")
    if not executable:
        return 0
    try:
        result = subprocess.run(
            [
                executable,
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
    except subprocess.CalledProcessError:
        return 0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0


def _atempo_filters(speed: float) -> list[str]:
    filters: list[str] = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return filters


def _clips_for_topic(
    topic: str,
    agent: PMVideoAgent,
    day: str,
    width: int,
    height: int,
    template_mode: str = "random",
    openai_key_count: int = 4,
    gemini_key_count: int = 4,
) -> list[VideoClip]:
    scene_count = agent.scenes
    beats = _short_beats(topic) if agent.aspect == "shorts" else _youtube_beats(topic, scene_count)
    durations = _clip_durations(agent, beats)
    if any(duration > 15 for duration in durations):
        raise ValueError("VideoClip duration limit is 15 seconds; increase scene count.")

    slide_plan = build_slide_plan(
        topic=topic,
        day=day,
        aspect=agent.aspect,
        total_slides=scene_count,
        template_mode=template_mode,
        max_dimension=2048,
        max_bytes=5 * 1024 * 1024,
        openai_key_count=openai_key_count,
        gemini_key_count=gemini_key_count,
    )

    clips: list[VideoClip] = []
    for index in range(scene_count):
        beat = beats[index]
        source_type = "auto_2_5d"
        visual_mode = "2_5d_image"
        slide = slide_plan.slides[index]
        clips.append(
            VideoClip(
                id=f"scene_{index + 1:02d}",
                title=beat["title"],
                duration_seconds=durations[index],
                narration=beat["narration"],
                on_screen_text=beat["on_screen_text"],
                visual_mode=visual_mode,
                prompt=slide.image_prompt,
                source_type=source_type,
                expected_file=f"scene_{index + 1:02d}.mp4",
                template_id=slide.template_id,
                template_name=slide.template_name,
                template_layout=slide.template_layout,
                provider_family=slide.provider,
                provider_slot=slide.provider_slot,
                slide_role=slide.role,
                image_max_dimension=slide.max_dimension,
                image_max_bytes=slide.max_bytes,
            )
        )
    return clips


def _short_beats(topic: str) -> list[dict[str, str]]:
    return [
        {
            "title": "Hook",
            "on_screen_text": "Your AI co-pilot is here",
            "narration": f"Project managers, here is the fast view on {topic}.",
            "visual": "hero frame, creator portrait, friendly AI robot, neon headline, project dashboard",
        },
        {
            "title": "Signal",
            "on_screen_text": "Meeting notes -> actions",
            "narration": "First win: turn meeting notes into actions, owners, dates, and open questions.",
            "visual": "speech bubbles turning into action cards with owner and due date chips",
        },
        {
            "title": "Backlog",
            "on_screen_text": "Clean weak stories fast",
            "narration": "Second win: ask AI to find vague stories, missing acceptance criteria, and hidden dependencies.",
            "visual": "backlog cards sorted into clear, unclear, blocked, with glowing AI scanner",
        },
        {
            "title": "Risk",
            "on_screen_text": "Ask: what can fail?",
            "narration": "Third win: generate risk prompts before sprint planning, release planning, or steering reviews.",
            "visual": "risk radar, red amber green markers, PM reviewing risks with AI assistant",
        },
        {
            "title": "Status",
            "on_screen_text": "Draft status, then verify",
            "narration": "Fourth win: draft stakeholder updates, but verify every date, dependency, and commitment yourself.",
            "visual": "PMO status dashboard, draft update, human approval stamp, executive summary panel",
        },
        {
            "title": "Jira",
            "on_screen_text": "Keep work in the tool",
            "narration": "Do not leave insights in chat. Connect them back to Jira, the backlog, or your action tracker.",
            "visual": "AI insights flowing into sprint board columns, no real product logos, neon workflow arrows",
        },
        {
            "title": "Copilot",
            "on_screen_text": "Use AI for admin load",
            "narration": "Use Copilot-style tools for summaries, follow-ups, decision logs, and first drafts.",
            "visual": "calendar, email, document and decision log icons connected by blue circuit lines",
        },
        {
            "title": "Governance",
            "on_screen_text": "Never skip review",
            "narration": "Keep privacy, client data, scope decisions, and prioritization under human control.",
            "visual": "security shield, privacy lock, human review gate, AI suggestion queue",
        },
        {
            "title": "Formula",
            "on_screen_text": "Capture -> Draft -> Validate -> Communicate",
            "narration": "Simple formula: capture, draft, validate, then communicate. That is your AI-enabled PM loop.",
            "visual": "four-step neon vertical workflow: capture, draft, validate, communicate",
        },
        {
            "title": "Subscribe CTA",
            "on_screen_text": "Subscribe, like, ask",
            "narration": SHORTS_SUBSCRIBE_CTA,
            "visual": "creator portrait, subscribe button, like icon, comment questions, live session badge",
        },
    ]


def _clip_durations(agent: PMVideoAgent, beats: list[dict[str, str]]) -> list[int]:
    if agent.aspect == "shorts":
        durations: list[int] = []
        for index, beat in enumerate(beats[: agent.scenes]):
            words = len(beat["narration"].split())
            duration = max(6, min(12, math.ceil(words / 2.35) + 1))
            if index == 0:
                duration = max(duration, 9)
            if index == agent.scenes - 1:
                duration = max(duration, 10)
            durations.append(duration)
        return durations
    base_duration = agent.target_duration_seconds // agent.scenes
    remainder = agent.target_duration_seconds % agent.scenes
    return [base_duration + (1 if index < remainder else 0) for index in range(agent.scenes)]


def _youtube_beats(topic: str, scene_count: int) -> list[dict[str, str]]:
    base = [
        ("Opening Hook", "AI will not replace PMs. Slow PMs will struggle.", f"Today we break down {topic}. Stay with me, because this is not a tool demo. This is a practical operating model for project leaders."),
        ("Promise", "By the end, you get a reusable PM workflow", "You will get a simple way to use AI for notes, backlog clarity, risks, stakeholder updates, and governance without losing accountability."),
        ("Question 1", "Question: where does a PM lose time?", "Quick question for you. Where do project managers lose the most time: meetings, status reports, backlog cleanup, or follow-ups? Think for two seconds."),
        ("Answer 1", "Answer: context switching kills delivery focus", "The answer is usually context switching. You attend a meeting, write notes, chase actions, update Jira, prepare status, and then explain the same story again."),
        ("Punch Line", "AI is not the PM. AI is the assistant PM.", "Punch line: AI should not make delivery decisions for you. It should prepare the information so your decision is faster and cleaner."),
        ("Workflow Map", "Capture -> Draft -> Validate -> Communicate", "Use this loop: capture the raw input, draft useful outputs, validate with human judgement, then communicate clearly to the right audience."),
        ("Step 1", "Capture: collect the messy input", "Capture meeting notes, chat decisions, blocker comments, customer feedback, change requests, and unclear backlog items in one trusted workspace."),
        ("Step 1 Example", "Example: meeting notes become action candidates", "After a planning call, ask AI to list decisions, action items, owners, dates, dependencies, and questions that still need confirmation."),
        ("Question 2", "Question: should AI create tasks directly?", "Now pause. Should AI directly create tasks and assign owners without your review? Think about what could go wrong."),
        ("Answer 2", "No. Review before creating work.", "No. AI can suggest tasks, but you approve the owner, date, priority, and wording. Otherwise the team receives noise instead of clarity."),
        ("Step 2", "Draft: turn rough notes into useful PM output", "Draft status updates, risk summaries, RAID entries, acceptance criteria, decision logs, and stakeholder messages from the captured input."),
        ("Backlog Tip", "Backlog prompt: find vague stories", "For backlog refinement, ask: which stories are not testable, which acceptance criteria are missing, and which dependencies could block delivery?"),
        ("Acceptance Criteria", "Good AC removes rework", "A strong AI-assisted acceptance criteria review should still end with a product owner and team conversation. The tool improves preparation, not ownership."),
        ("Risk Tip", "Risk prompt: what can fail?", "Before a sprint, release, or steering meeting, ask AI to challenge assumptions, integration points, privacy risks, vendor risks, and decision delays."),
        ("Question 3", "Question: what is the biggest AI risk?", "Another question. What is the biggest AI risk in project management: privacy, hallucination, over-trust, or weak governance? Hold that answer."),
        ("Answer 3", "The risk is blind trust", "My answer: blind trust. Privacy and hallucination are serious, but blind trust is what lets a wrong output become a project commitment."),
        ("Step 3", "Validate: facts, dates, scope, commitments", "Validation means you check every date, owner, dependency, risk rating, scope statement, and customer promise before it leaves your desk."),
        ("Jira Rule", "Do not leave insight in chat", "If your team uses Jira or any delivery tool, do not leave insight inside an AI chat. Convert reviewed insight into the real work system."),
        ("Copilot Rule", "Copilot is strongest with clean inputs", "Copilot-style tools work best when calendars, notes, documents, and decisions are already organized. Bad input creates confident confusion."),
        ("PMO Angle", "PMO should move from status to insight", "A modern PMO should not only collect red, amber, green status. It should surface decisions, constraints, risk trends, and recovery options."),
        ("Scrum Master Angle", "Scrum Masters can coach with patterns", "Scrum Masters can use AI to spot recurring blockers, meeting overload, unclear ownership, and flow issues, but facilitation stays human."),
        ("Delivery Manager Angle", "Delivery managers need decision intelligence", "Delivery managers can use AI to prepare escalation packs: what happened, impact, options, recommendation, owner, and next checkpoint."),
        ("SAFe Angle", "At scale, define approval boundaries", "In SAFe or large programs, define where AI may draft, where it may summarize, and where human approval is mandatory."),
        ("PMP Angle", "PMP thinking becomes more valuable", "PMP thinking still matters because AI needs boundaries: scope, risk, change control, stakeholders, procurement, quality, and ethics."),
        ("Question 4", "Question: what should you automate first?", "If you start tomorrow, what should you automate first? Status reports, meeting actions, risk discovery, or backlog review? Think practically."),
        ("Answer 4", "Start where review is easiest", "Start where review is easiest and value is visible. For most PMs, that means meeting actions or weekly status drafting."),
        ("Seven Day Pilot", "Run a seven-day pilot", "For seven days, use AI on one workflow only. Compare time saved, missed follow-ups, quality of updates, and team feedback."),
        ("Measurement", "Measure outcomes, not excitement", "Do not measure hype. Measure fewer missed actions, cleaner stories, faster updates, better risk conversations, and less admin fatigue."),
        ("Anti Pattern 1", "Do not copy-paste blindly", "Anti-pattern one: copying AI output directly to stakeholders. That is how wrong dates, wrong owners, and wrong commitments spread."),
        ("Anti Pattern 2", "Do not create more dashboards", "Anti-pattern two: generating more dashboards without better decisions. More reporting is not the same as better control."),
        ("Anti Pattern 3", "Do not replace conversation", "Anti-pattern three: using AI to avoid difficult conversations. Delivery still needs alignment, negotiation, and leadership courage."),
        ("Starter Checklist", "Your checklist", "Use this checklist: trusted input, clear prompt, human review, data protection, tool-of-record update, and outcome measurement."),
        ("Viewer Action", "Comment your workflow", "Tell me in the comments: which workflow should I explain next: Jira cleanup, PMO reporting, Copilot prompts, risk management, or PMP study planning?"),
        ("Recap", "AI prepares. PM decides.", "Final recap: AI prepares the work, the project manager makes the judgement, the team owns delivery, and governance protects the outcome."),
        ("Subscribe CTA", "Like, subscribe, and hit the bell", "If this was useful, like the video and subscribe for practical PM, Agile, AI, PMP, Jira, and Copilot videos. Do not forget to hit the bell icon for notifications when I upload a new video."),
    ]
    return [
        {
            "title": title,
            "on_screen_text": on_screen,
            "narration": narration,
            "visual": f"{title.lower()} for {topic}",
        }
        for title, on_screen, narration in base[:scene_count]
    ]


def _manifest_row(agent: PMVideoAgent, episode: VideoEpisode, root: Path) -> dict[str, Any]:
    return {
        "agent_id": agent.id,
        "episode_id": episode.episode_id,
        "title": episode.title,
        "topic": episode.title,
        "aspect": episode.aspect,
        "duration_seconds": episode.duration_seconds,
        "visual_template_id": episode.visual_template_id,
        "visual_template_name": episode.visual_template_name,
        "workspace": str(root),
        "metadata_doc": str(root / "thumbnail" / "metadata.doc"),
        "thumbnail": str(root / "thumbnail" / "thumbnail.svg"),
        "subtitles": str(root / "video" / "subtitles.srt"),
        "slide_plan": str(root / "slide_plan.json"),
        "slide_roles": sorted({clip.slide_role for clip in episode.clips if clip.slide_role}),
        "api_key_slots": sorted({clip.provider_family + ":" + clip.provider_slot for clip in episode.clips if clip.provider_family or clip.provider_slot}),
    }


def _episode_dict(episode: VideoEpisode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "title": episode.title,
        "description": episode.description,
        "aspect": episode.aspect,
        "width": episode.width,
        "height": episode.height,
        "duration_seconds": episode.duration_seconds,
        "clips": [asdict(clip) for clip in episode.clips],
        "youtube_title": episode.youtube_title,
        "youtube_description": episode.youtube_description,
        "hashtags": episode.hashtags,
        "visual_template_id": episode.visual_template_id,
        "visual_template_name": episode.visual_template_name,
        "visual_template_layout": episode.visual_template_layout,
    }


def _slide_plan_dict(episode: VideoEpisode) -> dict[str, Any]:
    return {
        "topic": episode.title,
        "aspect": episode.aspect,
        "total_slides": len(episode.clips),
        "slides": [
            {
                "index": index,
                "clip_id": clip.id,
                "title": clip.title,
                "role": clip.slide_role,
                "provider": clip.provider_family,
                "provider_slot": clip.provider_slot,
                "template_id": clip.template_id,
                "template_name": clip.template_name,
                "template_layout": clip.template_layout,
                "image_prompt": clip.prompt,
                "max_dimension": clip.image_max_dimension,
                "max_bytes": clip.image_max_bytes,
            }
            for index, clip in enumerate(episode.clips, start=1)
        ],
    }


def _lane_batches_dict(episode: VideoEpisode) -> dict[str, Any]:
    lanes: dict[tuple[str, str], dict[str, Any]] = {}
    for index, clip in enumerate(episode.clips, start=1):
        key = (clip.provider_family or "unknown", clip.provider_slot or "unknown")
        lane = lanes.setdefault(
            key,
            {
                "provider": key[0],
                "provider_slot": key[1],
                "slide_role": clip.slide_role,
                "template_family": clip.template_layout,
                "clips": [],
            },
        )
        lane["clips"].append(
            {
                "index": index,
                "clip_id": clip.id,
                "title": clip.title,
                "template_id": clip.template_id,
                "template_name": clip.template_name,
                "template_layout": clip.template_layout,
                "prompt": clip.prompt,
                "image_max_dimension": clip.image_max_dimension,
                "image_max_bytes": clip.image_max_bytes,
            }
        )
    return {
        "topic": episode.title,
        "aspect": episode.aspect,
        "lanes": [lane for lane in lanes.values()],
    }


def _title_for(topic: str, aspect: str, index: int) -> str:
    topic_headline = _topic_headline(topic, 42 if aspect == "shorts" else 52)
    if aspect == "shorts":
        variants = [
            f"{topic_headline} - 5 Things PMs Should Know",
            f"{topic_headline} | Quick AI Update for PMs",
            f"Stop Doing This in {topic_headline}",
            f"{topic_headline} | Fast PM Lesson",
        ]
        return _capped(variants[(index - 1) % len(variants)], 72)
    variants = [
        f"{topic_headline} | PM AI Playbook",
        f"How PMs Can Use AI for {topic_headline}",
        f"{topic_headline} | Practical PMO Guidance",
        f"{topic_headline} | Real-World Delivery Strategy",
    ]
    return _capped(variants[(index - 1) % len(variants)], 92)


def _description_for(topic: str, aspect: str) -> str:
    format_line = "YouTube Short" if aspect == "shorts" else "5-8 minute YouTube explainer"
    topic_line = _trim_topic(topic, 96)
    return (
        f"{format_line} on {topic_line}.\n\n"
        "What you will get:\n"
        "- a clear breakdown of the idea\n"
        "- practical delivery examples\n"
        "- a takeaway you can use in your team\n\n"
        "We cover practical project management, Agile delivery, Scrum, PMO, Jira, "
        "Microsoft Copilot, AI tools, governance, and delivery leadership.\n\n"
        f"{SUBSCRIBE_CTA}\n\n"
        "Disclosure: AI-generated visuals or narration may be used. Review all "
        "claims before public upload."
    )


def _thumbnail_angle(episode: VideoEpisode) -> str:
    title = episode.youtube_title.lower()
    if "copilot" in title:
        return "Faster reporting, cleaner updates"
    if "jira" in title:
        return "Turn chaos into clear actions"
    if "risk" in title:
        return "Show risk before it grows"
    if "status" in title:
        return "Make status worth reading"
    if "planning" in title:
        return "Plan smarter, rework less"
    if "governance" in title:
        return "Keep AI useful and safe"
    return "Practical PM lesson in minutes"


def _trim_topic(topic: str, maximum: int) -> str:
    words = topic.split()
    value = " ".join(words)
    return _capped(value, maximum)


def _topic_headline(topic: str, maximum: int) -> str:
    base = topic.split(":", 1)[0].split(" - ", 1)[0].strip()
    if not base:
        base = topic
    return _capped(" ".join(base.split()), maximum)


def _shorten_title(title: str, maximum: int = 64) -> str:
    return _capped(" ".join(title.split()), maximum)


def _script_markdown(episode: VideoEpisode, agent: PMVideoAgent) -> str:
    lines = [
        f"# {episode.title}",
        "",
        f"Agent: {agent.name}",
        f"Format: {episode.aspect} ({episode.width}x{episode.height})",
        f"Duration: {episode.duration_seconds} seconds",
        "",
        "## Shared Prompt",
        "",
        agent.prompt,
        "",
        "## Scenes",
        "",
    ]
    for index, clip in enumerate(episode.clips, start=1):
        lines.extend(
            [
                f"### {index}. {clip.title} ({clip.duration_seconds}s)",
                "",
                f"On screen: {clip.on_screen_text}",
                "",
                clip.narration,
                "",
                f"Expected file: `{clip.expected_file}`",
                "",
            ]
        )
    return "\n".join(lines)


def _prompt_rows(episode: VideoEpisode) -> list[dict[str, str | int]]:
    return [
        {
            "clip": clip.id,
            "title": clip.title,
            "duration_seconds": clip.duration_seconds,
            "on_screen_text": clip.on_screen_text,
            "expected_file": clip.expected_file,
            "prompt": clip.prompt,
            "template_id": clip.template_id,
            "template_name": clip.template_name,
            "template_layout": clip.template_layout,
            "provider_family": clip.provider_family,
            "provider_slot": clip.provider_slot,
            "slide_role": clip.slide_role,
            "api_key_family": clip.provider_family,
            "api_key_slot": clip.provider_slot,
        }
        for clip in episode.clips
    ]


def _clip_drop_guide(episode: VideoEpisode) -> str:
    lines = [
        "# Clip Drop Guide",
        "",
        f"Create or render clips at {episode.width}x{episode.height}.",
        "Save final clips with the exact filenames below in `clips/inbox/`.",
        "",
    ]
    for clip in episode.clips:
        lines.append(f"- `{clip.expected_file}` - {clip.title} ({clip.duration_seconds}s)")
    return "\n".join(lines) + "\n"


def _metadata_markdown(episode: VideoEpisode) -> str:
    return (
        f"# {episode.youtube_title}\n\n"
        "## Description\n\n"
        f"{episode.youtube_description}\n\n"
        "## Hashtags\n\n"
        f"{' '.join(episode.hashtags)}\n"
    )


def _episode_template(episode: VideoEpisode) -> PMVideoTemplate:
    if episode.visual_template_id:
        try:
            return get_pm_video_template(episode.visual_template_id)
        except KeyError:
            pass
    return PM_COURSE_TEMPLATE


def _telegram_message(episode: VideoEpisode, youtube_channel_url: str = "") -> str:
    channel_line = f"\nChannel: {youtube_channel_url}" if youtube_channel_url else ""
    hashtags = " ".join(episode.hashtags[:5])
    return (
        f"Video ready: {episode.youtube_title}\n"
        f"Duration: {episode.duration_seconds} seconds\n"
        f"Topic: {episode.title}\n"
        f"Thumbnail: {_thumbnail_angle(episode)}\n"
        f"Hashtags: {hashtags}"
        f"{channel_line}\n"
        "Next step: open and publish the video."
    )


def _linkedin_post_markdown(
    episode: VideoEpisode,
    agent: PMVideoAgent,
    youtube_channel_url: str = "",
) -> str:
    reference_label = "Shorts reference" if agent.aspect == "shorts" else "Full video reference"
    first_lines = [clip.on_screen_text or clip.title for clip in episode.clips[:4] if (clip.on_screen_text or clip.title)]
    bullets = "\n".join(f"- {point}" for point in first_lines)
    channel_line = f"\nYouTube channel: {youtube_channel_url}\n" if youtube_channel_url else "\n"
    return (
        f"# {episode.youtube_title}\n\n"
        f"Reference: {reference_label}\n\n"
        f"{channel_line}"
        "Hook:\n"
        f"{episode.clips[0].narration if episode.clips else episode.title}\n\n"
        "Key points:\n"
        f"{bullets}\n\n"
        "Caption idea:\n"
        f"{episode.youtube_description}\n\n"
        "Hashtags:\n"
        f"{' '.join(episode.hashtags)}\n"
    )


def _linkedin_post_payload(
    episode: VideoEpisode,
    agent: PMVideoAgent,
    youtube_channel_url: str = "",
) -> dict[str, Any]:
    reference_label = "Shorts reference" if agent.aspect == "shorts" else "Full video reference"
    return {
        "platform": "linkedin",
        "topic": episode.title,
        "reference": reference_label,
        "reference_url": youtube_channel_url,
        "title": episode.youtube_title,
        "description": episode.youtube_description,
        "hashtags": episode.hashtags,
        "aspect": episode.aspect,
        "duration_seconds": episode.duration_seconds,
        "image_file": "publish/linkedin_video_post.png",
    }


def _metadata_doc(episode: VideoEpisode, agent: PMVideoAgent) -> str:
    template = _episode_template(episode)
    scene_rows = "".join(
        f"<tr><td>{escape(clip.id)}</td><td>{escape(clip.title)}</td>"
        f"<td>{clip.duration_seconds}s</td><td>{escape(clip.narration)}</td></tr>"
        for clip in episode.clips
    )
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{escape(episode.title)}</title></head>
<body>
<h1>{escape(episode.youtube_title)}</h1>
<p><strong>Agent:</strong> {escape(agent.name)}</p>
<p><strong>Format:</strong> {escape(episode.aspect)} / {episode.width}x{episode.height}</p>
<p><strong>Duration:</strong> {episode.duration_seconds} seconds</p>
<p><strong>Template:</strong> {escape(template.style_line)} ({escape(template.template_id)})</p>
<p><strong>Thumbnail angle:</strong> {escape(_thumbnail_angle(episode))}</p>
<h2>Description</h2>
<p>{escape(episode.youtube_description).replace(chr(10), "<br>")}</p>
<h2>Thumbnail Prompt</h2>
<p>{escape(_thumbnail_prompt(episode, agent))}</p>
<h2>Subtitles</h2>
<p>Subtitle file is saved as thumbnail/subtitles.srt and video/subtitles.srt.</p>
<h2>Scene Script</h2>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>Clip</th><th>Title</th><th>Duration</th><th>Narration</th></tr>
{scene_rows}
</table>
</body>
</html>
"""


def _thumbnail_prompt(episode: VideoEpisode, agent: PMVideoAgent) -> str:
    template = _episode_template(episode)
    angle = _thumbnail_angle(episode)
    return (
        f"Create a high-contrast YouTube thumbnail for '{episode.title}'. "
        f"Thumbnail angle: {angle}. "
        f"Visual template: {template.style_line}. "
        "Use a confident project manager or delivery leader in a cinematic pose, "
        "AI assistant concept, Jira-style planning board shapes without real logos, "
        "modern PMO dashboard, bold readable headline space, sharp contrast, "
        "professional blue, green, amber and white palette, no watermark. "
        f"Add one short readable phrase only if it is absolutely necessary. Format: {episode.width}x{episode.height}. "
        f"Agent: {agent.name}."
    )


def _thumbnail_svg(episode: VideoEpisode, agent: PMVideoAgent) -> str:
    template = _episode_template(episode)
    title = _wrap_svg_text(_shorten_title(episode.youtube_title), 28 if episode.aspect == "shorts" else 32, 3)
    title_y = 118 if episode.aspect == "shorts" else 132
    title_gap = 52 if episode.aspect == "shorts" else 58
    lines = "".join(
        f'<text x="{56 if template.layout != "signal_dashboard" else 72}" y="{title_y + index * title_gap}" font-size="{38 if episode.aspect == "shorts" else 42}" font-weight="800" fill="{template.headline_fill}">{escape(line)}</text>'
        for index, line in enumerate(title)
    )
    angle = escape(_thumbnail_angle(episode))
    template_name = escape(template.style_line)
    if template.layout == "boardroom_chalk":
        accent_band = f'<rect x="0" y="0" width="{episode.width}" height="{int(episode.height * 0.28)}" fill="{template.background_mid}" opacity="0.95"/><rect x="{int(episode.width * 0.58)}" y="0" width="{int(episode.width * 0.42)}" height="{episode.height}" fill="{template.accent_secondary}" opacity="0.32"/>'
        shape = f'<rect x="{episode.width - 360}" y="{int(episode.height * 0.25)}" width="260" height="260" rx="30" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5" opacity="0.94"/>'
        overlay = f'<text x="{episode.width - 230}" y="{int(episode.height * 0.42)}" font-size="120" font-weight="900" fill="{template.highlight_fill}" text-anchor="middle">PM</text>'
        caption_y = episode.height - 82
    elif template.layout == "signal_dashboard":
        accent_band = f'<rect x="0" y="0" width="{episode.width}" height="{int(episode.height * 0.22)}" fill="{template.background_mid}" opacity="0.92"/><rect x="0" y="{int(episode.height * 0.52)}" width="{episode.width}" height="{int(episode.height * 0.48)}" fill="{template.background_end}" opacity="0.35"/>'
        shape = f'<rect x="{episode.width - 420}" y="{int(episode.height * 0.16)}" width="320" height="420" rx="28" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="5" opacity="0.95"/>'
        overlay = f'<text x="{episode.width - 260}" y="{int(episode.height * 0.39)}" font-size="54" font-weight="900" fill="{template.highlight_fill}" text-anchor="middle">AI</text>'
        caption_y = episode.height - 92
    elif template.layout == "editorial_stage":
        accent_band = f'<rect x="0" y="0" width="{episode.width}" height="{int(episode.height * 0.36)}" fill="{template.background_mid}" opacity="0.94"/><path d="M0 {int(episode.height * 0.62)} L{int(episode.width * 0.48)} {int(episode.height * 0.35)} L{episode.width} {int(episode.height * 0.58)} L{episode.width} {episode.height} L0 {episode.height} Z" fill="{template.accent_primary}" opacity="0.16"/>'
        shape = f'<circle cx="{int(episode.width * 0.82)}" cy="{int(episode.height * 0.34)}" r="{int(min(episode.width, episode.height) * 0.18)}" fill="{template.accent_secondary}" opacity="0.2"/>'
        overlay = f'<text x="{int(episode.width * 0.82)}" y="{int(episode.height * 0.37)}" font-size="66" font-weight="900" fill="{template.highlight_fill}" text-anchor="middle">AI</text>'
        caption_y = episode.height - 86
    elif template.layout == "workshop_lens":
        accent_band = f'<rect x="0" y="0" width="{episode.width}" height="{int(episode.height * 0.30)}" fill="{template.background_mid}" opacity="0.9"/><rect x="0" y="{int(episode.height * 0.48)}" width="{episode.width}" height="{int(episode.height * 0.52)}" fill="{template.background_end}" opacity="0.28"/>'
        shape = f'<rect x="{episode.width - 400}" y="{int(episode.height * 0.20)}" width="310" height="310" rx="34" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="5" opacity="0.95"/>'
        overlay = f'<text x="{episode.width - 245}" y="{int(episode.height * 0.38)}" font-size="62" font-weight="900" fill="{template.highlight_fill}" text-anchor="middle">PM</text>'
        caption_y = episode.height - 80
    elif template.layout == "future_ops":
        accent_band = f'<rect x="0" y="0" width="{episode.width}" height="{int(episode.height * 0.30)}" fill="{template.background_mid}" opacity="0.96"/><rect x="{int(episode.width * 0.62)}" y="0" width="{int(episode.width * 0.38)}" height="{episode.height}" fill="{template.accent_primary}" opacity="0.18"/>'
        shape = f'<rect x="{episode.width - 380}" y="{int(episode.height * 0.18)}" width="300" height="340" rx="34" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="5" opacity="0.95"/>'
        overlay = f'<text x="{episode.width - 230}" y="{int(episode.height * 0.40)}" font-size="66" font-weight="900" fill="{template.highlight_fill}" text-anchor="middle">OPS</text>'
        caption_y = episode.height - 90
    else:
        accent_band = f'<rect x="0" y="0" width="{episode.width}" height="{int(episode.height * 0.34)}" fill="{template.background_mid}" opacity="0.95"/><rect x="{int(episode.width * 0.58)}" y="0" width="{int(episode.width * 0.42)}" height="{episode.height}" fill="{template.accent_secondary}" opacity="0.30"/>'
        shape = f'<circle cx="{int(episode.width * 0.78)}" cy="{int(episode.height * 0.42)}" r="{int(min(episode.width, episode.height) * 0.18)}" fill="{template.accent_tertiary}" opacity="0.18"/>'
        overlay = f'<text x="{int(episode.width * 0.78)}" y="{int(episode.height * 0.43)}" font-size="90" font-weight="900" fill="{template.highlight_fill}" text-anchor="middle">AI</text>'
        caption_y = episode.height - 86
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{episode.width}" height="{episode.height}" viewBox="0 0 {episode.width} {episode.height}">
  <defs>
    <linearGradient id="thumb_bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{template.background_start}"/>
      <stop offset="50%" stop-color="{template.background_mid}"/>
      <stop offset="100%" stop-color="{template.background_end}"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#thumb_bg)"/>
  {accent_band}
  {shape}
  <text x="56" y="60" font-size="26" font-weight="700" fill="{template.accent_primary}">{escape(agent.name)}</text>
  <text x="{episode.width - 56}" y="60" text-anchor="end" font-size="22" font-weight="800" fill="{template.accent_tertiary}">{template_name}</text>
  {lines}
  {overlay}
  <rect x="56" y="{caption_y - 64}" width="{min(920, episode.width - 112)}" height="72" rx="20" fill="{template.panel_fill}" opacity="0.94" stroke="{template.panel_border}" stroke-width="2"/>
  <text x="88" y="{caption_y - 16}" font-size="30" font-weight="900" fill="{template.highlight_fill}">{angle}</text>
  <text x="56" y="{episode.height - 42}" font-size="28" font-weight="700" fill="{template.body_fill}">PMP • Agile • AI • PMO</text>
</svg>
"""


def _scene_svg(
    episode: VideoEpisode,
    agent: PMVideoAgent,
    clip: VideoClip,
    index: int,
    art_path: Path | None = None,
) -> str:
    template = _clip_template(episode, clip)
    if episode.aspect == "shorts":
        return _short_scene_svg(episode, agent, clip, index, template, art_path=art_path)
    return _landscape_scene_svg(episode, agent, clip, index, template, art_path=art_path)


def _clip_template(episode: VideoEpisode, clip: VideoClip) -> PMVideoTemplate:
    if clip.template_id:
        try:
            return get_pm_video_template(clip.template_id)
        except KeyError:
            pass
    return _episode_template(episode)


def _short_scene_svg(
    episode: VideoEpisode,
    agent: PMVideoAgent,
    clip: VideoClip,
    index: int,
    template: PMVideoTemplate,
    art_path: Path | None = None,
) -> str:
    title_lines = _wrap_svg_text(clip.on_screen_text, 24, 3)
    narration_lines = _wrap_svg_text(clip.narration, 40, 4)
    title_svg = "".join(
        f'<text x="70" y="{330 + line_index * 82}" font-size="76" font-weight="900" fill="{(template.headline_fill if line_index != 1 else template.highlight_fill)}">{escape(line)}</text>'
        for line_index, line in enumerate(title_lines)
    )
    body_svg = "".join(
        f'<text x="88" y="{598 + line_index * 38}" font-size="29" font-weight="700" fill="{template.body_fill}">{escape(line)}</text>'
        for line_index, line in enumerate(narration_lines)
    )
    progress = int((index / len(episode.clips)) * (episode.width - 116))
    scene_tag = escape(clip.title.upper())
    action_cards = _short_action_cards(clip, index)
    keyword_highlight = _short_keyword_highlight(clip, index)
    logo_svg = _brand_logo_svg(episode.width - 236, 70, 164)
    bot_mouth = _bot_mouth_svg(index)
    avatar_svg = "" if _talking_avatar_enabled() else _short_bot_svg(bot_mouth)
    bg_grid = "url(#grid)" if template.layout != "future_ops" else "url(#future_grid)"
    left_panel_fill = template.card_fill if template.layout in {"signal_dashboard", "future_ops"} else "#0f172a"
    left_panel_border = template.card_border if template.layout in {"signal_dashboard", "future_ops"} else "#22d3ee"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{episode.width}" height="{episode.height}" viewBox="0 0 {episode.width} {episode.height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{template.background_start}"/>
      <stop offset="42%" stop-color="{template.background_mid}"/>
      <stop offset="100%" stop-color="{template.background_end}"/>
    </linearGradient>
    <radialGradient id="accent_glow" cx="82%" cy="34%" r="38%">
      <stop offset="0%" stop-color="{template.highlight_fill}" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="{template.highlight_fill}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="secondary_glow" cx="22%" cy="78%" r="45%">
      <stop offset="0%" stop-color="{template.accent_primary}" stop-opacity="0.36"/>
      <stop offset="100%" stop-color="{template.accent_primary}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M48 0H0V48" fill="none" stroke="{template.accent_secondary}" stroke-width="1.3" opacity="0.2"/>
    </pattern>
    <pattern id="future_grid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M60 0H0V60" fill="none" stroke="{template.accent_primary}" stroke-width="1.1" opacity="0.14"/>
    </pattern>
    <filter id="soft_shadow"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000000" flood-opacity="0.45"/></filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  {_image_layer_svg(art_path, episode.width, episode.height, opacity=0.38)}
  <rect width="100%" height="100%" fill="{bg_grid}"/>
  <rect width="100%" height="100%" fill="url(#accent_glow)"/>
  <rect width="100%" height="100%" fill="url(#secondary_glow)"/>
  <g font-family="Arial, Helvetica, sans-serif">
    <rect x="70" y="72" width="406" height="66" rx="24" fill="{template.badge_fill}"/>
    <text x="116" y="116" font-size="32" font-weight="900" fill="{template.badge_text}">LEARN WITH LALIT</text>
    <rect x="70" y="166" width="392" height="70" rx="20" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="3"/>
    <text x="106" y="212" font-size="34" font-weight="900" fill="{template.highlight_fill}">AI</text>
    <text x="174" y="212" font-size="31" font-weight="800" fill="{template.headline_fill}">FOR PMS</text>
    {logo_svg}
    <text x="70" y="286" font-size="28" font-weight="900" fill="{template.highlight_fill}">{scene_tag}</text>
    {title_svg}
    <rect x="70" y="546" width="940" height="192" rx="28" fill="{left_panel_fill}" stroke="{left_panel_border}" stroke-width="3" opacity="0.88" filter="url(#soft_shadow)"/>
    {body_svg}
    {keyword_highlight}
    {action_cards}
    {avatar_svg}
    <rect x="58" y="{episode.height - 92}" width="{episode.width - 116}" height="9" rx="4.5" fill="{template.panel_border}"/>
    <rect x="58" y="{episode.height - 92}" width="{progress}" height="9" rx="4.5" fill="{template.highlight_fill}"/>
    <text x="58" y="{episode.height - 40}" font-size="26" font-weight="900" fill="{template.headline_fill}">FOCUS • PLAN • DELIVER</text>
    <text x="{episode.width - 58}" y="{episode.height - 40}" text-anchor="end" font-size="26" font-weight="900" fill="{template.accent_primary}">{index:02d}/{len(episode.clips):02d}</text>
  </g>
</svg>
"""


def _landscape_scene_svg(
    episode: VideoEpisode,
    agent: PMVideoAgent,
    clip: VideoClip,
    index: int,
    template: PMVideoTemplate,
    art_path: Path | None = None,
) -> str:
    title_lines = _wrap_svg_text(clip.on_screen_text, 34, 2)
    narration_lines = _wrap_svg_text(clip.narration, 58, 4)
    title_svg = "".join(
        f'<text x="70" y="{176 + line_index * 54}" font-size="48" font-weight="900" fill="{(template.headline_fill if line_index == 0 else template.highlight_fill)}">{escape(line)}</text>'
        for line_index, line in enumerate(title_lines)
    )
    body_svg = "".join(
        f'<text x="92" y="{322 + line_index * 31}" font-size="23" font-weight="700" fill="{template.body_fill}">{escape(line)}</text>'
        for line_index, line in enumerate(narration_lines)
    )
    progress = int((index / len(episode.clips)) * 1130)
    panel_fill = template.panel_fill if template.layout != "future_ops" else template.card_fill
    panel_border = template.panel_border if template.layout != "future_ops" else template.accent_primary
    badge_x = 54 if template.layout != "workshop_lens" else 72
    hero_border = template.card_border if template.layout in {"signal_dashboard", "future_ops"} else template.panel_border
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{episode.width}" height="{episode.height}" viewBox="0 0 {episode.width} {episode.height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{template.background_start}"/>
      <stop offset="50%" stop-color="{template.background_mid}"/>
      <stop offset="100%" stop-color="{template.background_end}"/>
    </linearGradient>
    <radialGradient id="glow" cx="76%" cy="44%" r="42%">
      <stop offset="0%" stop-color="{template.highlight_fill}" stop-opacity="0.34"/>
      <stop offset="100%" stop-color="{template.highlight_fill}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M40 0H0V40" fill="none" stroke="{template.accent_primary}" stroke-width="1" opacity="0.13"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  {_image_layer_svg(art_path, episode.width, episode.height, opacity=0.42)}
  <rect width="100%" height="100%" fill="url(#grid)"/>
  <rect width="100%" height="100%" fill="url(#glow)"/>
  <g font-family="Arial, sans-serif">
    <rect x="{badge_x}" y="34" width="282" height="48" rx="20" fill="{template.badge_fill}"/>
    <text x="{badge_x + 34}" y="66" font-size="25" font-weight="900" fill="{template.badge_text}">LEARN WITH LALIT</text>
    <rect x="378" y="34" width="184" height="48" rx="16" fill="{template.panel_fill}" stroke="{template.panel_border}" stroke-width="2"/>
    <text x="402" y="66" font-size="23" font-weight="900" fill="{template.highlight_fill}">AI</text>
    <text x="448" y="66" font-size="22" font-weight="800" fill="{template.headline_fill}">FOR PMS</text>
    <text x="70" y="130" font-size="22" font-weight="900" fill="{template.highlight_fill}">{escape(clip.title.upper())}</text>
    {title_svg}
    <rect x="70" y="282" width="675" height="150" rx="20" fill="{panel_fill}" stroke="{panel_border}" stroke-width="2.5" opacity="0.92"/>
    {body_svg}
    <g transform="translate(802 118)">
      <rect x="0" y="0" width="390" height="404" rx="28" fill="{template.card_fill}" stroke="{hero_border}" stroke-width="3"/>
      <text x="34" y="56" font-size="24" font-weight="900" fill="{template.headline_fill}">PM AI LOOP</text>
      <text x="34" y="106" font-size="25" font-weight="900" fill="{template.highlight_fill}">01 Capture</text>
      <text x="34" y="166" font-size="25" font-weight="900" fill="{template.accent_primary}">02 Draft</text>
      <text x="34" y="226" font-size="25" font-weight="900" fill="{template.accent_secondary}">03 Validate</text>
      <text x="34" y="286" font-size="25" font-weight="900" fill="{template.headline_fill}">04 Communicate</text>
      <path d="M270 92 C336 124 336 268 270 316" fill="none" stroke="{template.highlight_fill}" stroke-width="8" stroke-linecap="round"/>
      <circle cx="282" cy="92" r="15" fill="{template.accent_primary}"/>
      <circle cx="282" cy="318" r="15" fill="{template.highlight_fill}"/>
    </g>
    <g transform="translate(92 492)">
      <rect width="236" height="86" rx="18" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="2"/>
      <text x="28" y="36" font-size="22" font-weight="900" fill="{template.accent_primary}">Risk</text>
      <text x="28" y="66" font-size="25" font-weight="900" fill="{template.headline_fill}">Visible</text>
    </g>
    <g transform="translate(360 492)">
      <rect width="236" height="86" rx="18" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="2"/>
      <text x="28" y="36" font-size="22" font-weight="900" fill="{template.accent_secondary}">Flow</text>
      <text x="28" y="66" font-size="25" font-weight="900" fill="{template.headline_fill}">Faster</text>
    </g>
    <g transform="translate(628 492)">
      <rect width="236" height="86" rx="18" fill="{template.card_fill}" stroke="{template.card_border}" stroke-width="2"/>
      <text x="28" y="36" font-size="22" font-weight="900" fill="{template.highlight_fill}">Review</text>
      <text x="28" y="66" font-size="25" font-weight="900" fill="{template.headline_fill}">Human</text>
    </g>
    <rect x="70" y="650" width="1130" height="7" rx="3.5" fill="{template.panel_border}"/>
    <rect x="70" y="650" width="{progress}" height="7" rx="3.5" fill="{template.highlight_fill}"/>
    <text x="70" y="690" font-size="18" font-weight="900" fill="{template.body_fill}">PMP • SCRUM • AGILE • SAFe • JIRA • COPILOT • PMO</text>
    <text x="1200" y="690" text-anchor="end" font-size="20" font-weight="900" fill="{template.accent_primary}">{index:02d}/{len(episode.clips):02d}</text>
  </g>
</svg>
"""


def _short_action_cards(clip: VideoClip, index: int) -> str:
    labels = _short_card_labels(clip)
    rows = []
    for row, (title, detail) in enumerate(labels):
        y = 850 + row * 155
        active = row == index % len(labels)
        stroke = "#22d3ee" if active else "#7c3aed"
        fill = "#07111f" if active else "#160f2d"
        glow = "0.96" if active else "0.82"
        rows.append(
            f"""<g transform="translate(76 {y})">
      <rect x="0" y="0" width="456" height="116" rx="24" fill="{fill}" stroke="{stroke}" stroke-width="{5 if active else 3}" opacity="{glow}"/>
      <circle cx="62" cy="58" r="34" fill="#0f172a" stroke="#f59e0b" stroke-width="6"/>
      <path d="M44 60 L57 74 L82 42" fill="none" stroke="#22d3ee" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
      <text x="124" y="50" font-size="32" font-weight="900" fill="#ffffff">{escape(title)}</text>
      <text x="124" y="88" font-size="25" font-weight="800" fill="#93c5fd">{escape(detail)}</text>
    </g>"""
        )
    return "\n".join(rows)


def _short_card_labels(clip: VideoClip) -> list[tuple[str, str]]:
    title = clip.title.lower()
    if "hook" in title:
        return [("AI Co-pilot", "PM focus"), ("Trend", "What changes"), ("Use Case", "Quick win"), ("Guardrail", "Human review")]
    if "signal" in title:
        return [("Notes", "Meeting input"), ("Actions", "Owner"), ("Dates", "Due date"), ("Questions", "Open points")]
    if "backlog" in title:
        return [("Stories", "Weak items"), ("AC", "Testable"), ("Dependency", "Blocked"), ("Refine", "Next step")]
    if "risk" in title:
        return [("Risk", "What can fail"), ("Impact", "Delivery"), ("Owner", "Response"), ("Review", "Before plan")]
    if "status" in title:
        return [("Status", "Draft"), ("Dates", "Verify"), ("Dependency", "Check"), ("Commitment", "Own it")]
    if "jira" in title:
        return [("Insight", "From chat"), ("Ticket", "Tool record"), ("Backlog", "Visible"), ("Tracker", "Updated")]
    if "copilot" in title:
        return [("Summary", "Minutes"), ("Follow-up", "Email"), ("Decision", "Log"), ("Draft", "First pass")]
    if "governance" in title:
        return [("Privacy", "Protect"), ("Scope", "Control"), ("Priority", "Human"), ("Approval", "Gate")]
    if "formula" in title:
        return [("Capture", "Input"), ("Draft", "Output"), ("Validate", "Review"), ("Communicate", "Clear")]
    return [("Subscribe", "More videos"), ("Like", "Motivation"), ("Ask", "Comments"), ("Live", "Answers")]


def _short_keyword_highlight(clip: VideoClip, index: int) -> str:
    cards = _short_card_labels(clip)
    keyword, detail = cards[index % len(cards)]
    return f"""<g transform="translate(88 752)">
      <rect x="0" y="0" width="520" height="58" rx="22" fill="#f59e0b" opacity="0.96"/>
      <text x="30" y="38" font-size="25" font-weight="900" fill="#111827">Now: {escape(keyword)} • {escape(detail)}</text>
    </g>"""


def _bot_mouth_svg(index: int) -> str:
    if index % 3 == 0:
        return '<ellipse cx="194" cy="218" rx="34" ry="16" fill="none" stroke="#22d3ee" stroke-width="10"/>'
    if index % 3 == 1:
        return '<path d="M158 214 C178 238 210 238 230 214" fill="none" stroke="#22d3ee" stroke-width="10" stroke-linecap="round"/>'
    return '<path d="M160 222 L230 222" fill="none" stroke="#22d3ee" stroke-width="10" stroke-linecap="round"/>'


def _short_bot_svg(bot_mouth: str) -> str:
    return f"""<g transform="translate(628 820)">
      <ellipse cx="188" cy="430" rx="174" ry="40" fill="#7c3aed" opacity="0.36"/>
      <circle cx="190" cy="150" r="112" fill="#dbeafe" stroke="#22d3ee" stroke-width="9"/>
      <rect x="82" y="120" width="216" height="116" rx="48" fill="#0f172a"/>
      <circle cx="148" cy="178" r="18" fill="#22d3ee"/>
      <circle cx="232" cy="178" r="18" fill="#22d3ee"/>
      {bot_mouth}
      <rect x="128" y="270" width="124" height="144" rx="38" fill="#1f2937" stroke="#22d3ee" stroke-width="7"/>
      <text x="190" y="360" text-anchor="middle" font-size="58" font-weight="900" fill="#22d3ee">AI</text>
      <path d="M96 304 C24 326 10 410 44 474" fill="none" stroke="#dbeafe" stroke-width="28" stroke-linecap="round"/>
      <path d="M286 306 C372 342 374 432 326 488" fill="none" stroke="#dbeafe" stroke-width="28" stroke-linecap="round"/>
      <line x1="326" y1="488" x2="392" y2="410" stroke="#f59e0b" stroke-width="12" stroke-linecap="round"/>
    </g>"""


def _talking_avatar_enabled() -> bool:
    return TALKING_AVATAR_GIF_PATH.exists()


def _brand_logo_svg(x: int, y: int, size: int) -> str:
    if not BRAND_LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(BRAND_LOGO_PATH.read_bytes()).decode("ascii")
    return f"""<defs>
      <clipPath id="brand_logo_clip"><circle cx="{x + size // 2}" cy="{y + size // 2}" r="{size // 2}"/></clipPath>
    </defs>
    <circle cx="{x + size // 2}" cy="{y + size // 2}" r="{size // 2 + 7}" fill="#f59e0b"/>
    <image href="data:image/png;base64,{encoded}" x="{x}" y="{y}" width="{size}" height="{size}" preserveAspectRatio="xMidYMid slice" clip-path="url(#brand_logo_clip)"/>"""


def _short_sticky_notes(index: int) -> str:
    notes = [
        ("Owner?", "#f59e0b", 78, 790),
        ("Risk?", "#a855f7", 258, 802),
        ("Due date", "#06b6d4", 408, 786),
    ]
    rendered = []
    for note_index, (text, color, x, y) in enumerate(notes):
        tilt = [-8, 5, -3][note_index]
        rendered.append(
            f"""<g transform="translate({x} {y}) rotate({tilt})">
      <rect width="132" height="94" rx="8" fill="{color}" opacity="0.92"/>
      <text x="18" y="56" font-size="25" font-weight="900" fill="#020617">{escape(text)}</text>
    </g>"""
        )
    return "\n".join(rendered)


def _render_scene_art(
    root: Path,
    episode: VideoEpisode,
    clip: VideoClip,
    index: int,
    provider: ImageProvider,
) -> Path:
    art_dir = root / "video" / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    variant = ImageVariant(
        "9:16" if episode.aspect == "shorts" else "16:9",
        episode.width,
        episode.height,
        f"scene_{index:02d}_art",
    )
    art_bytes = provider.create(clip.prompt, variant)
    art_path = art_dir / f"scene_{index:02d}_art{provider.extension}"
    art_path.write_bytes(art_bytes)
    return art_path


def _image_layer_svg(art_path: Path | None, width: int, height: int, opacity: float = 0.4) -> str:
    if not art_path or not art_path.exists():
        return ""
    href = _image_data_uri(art_path)
    return (
        f'<image href="{href}" x="0" y="0" width="{width}" height="{height}" '
        f'preserveAspectRatio="xMidYMid slice" opacity="{opacity}"/>'
    )


def _image_data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/svg+xml"
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _dashboard_html(episode: VideoEpisode, agent: PMVideoAgent, root: Path) -> str:
    template = _episode_template(episode)
    cards = "\n".join(
        f"<article><h3>{escape(clip.title)} ({clip.duration_seconds}s)</h3>"
        f"<p>{escape(clip.narration)}</p><textarea>{escape(clip.prompt)}</textarea></article>"
        for clip in episode.clips
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(episode.title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f8fafc; color: #111827; }}
    header {{ background: #111827; color: white; padding: 28px; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    article {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px; margin: 12px 0; background: white; }}
    textarea {{ width: 100%; min-height: 96px; box-sizing: border-box; }}
    code {{ color: #14532d; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(episode.title)}</h1>
    <p>{escape(agent.name)} • {escape(episode.aspect)} • {episode.duration_seconds}s</p>
    <p>Template: {escape(template.style_line)}</p>
    <p>Workspace: <code>{escape(str(root))}</code></p>
  </header>
  <main>
    <h2>Metadata</h2>
    <p>{escape(episode.youtube_description).replace(chr(10), "<br>")}</p>
    <h2>Scenes</h2>
    {cards}
  </main>
</body>
</html>
"""


def _subtitle_srt(episode: VideoEpisode) -> str:
    lines: list[str] = []
    start = 0
    for index, clip in enumerate(episode.clips, start=1):
        end = start + clip.duration_seconds
        lines.extend([str(index), f"{_timestamp(start)} --> {_timestamp(end)}", clip.narration, ""])
        start = end
    return "\n".join(lines)


def _timestamp(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _capped(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else value[: maximum - 3].rstrip() + "..."


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value)
    return "_".join(part for part in slug.split("_") if part)[:56]


def _wrap_svg_text(value: str, maximum: int, max_lines: int) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= maximum:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines
