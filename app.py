from __future__ import annotations

import json
import os
import sys
import re
from dataclasses import replace
from datetime import date
from html import escape
from pathlib import Path
from collections.abc import Mapping

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
import streamlit.components.v1 as components

from content_pipeline.bots.audio import audio_status, render_audio_status_html
from content_pipeline.bots.audio import curate_reference_audio_bank
from content_pipeline.bots.audio import available_voice_options
from content_pipeline.bots.audio import generate_music_preview
from content_pipeline.bots.audio import generate_voice_preview
from content_pipeline.bots.audio import filter_voice_preview_presets
from content_pipeline.bots.audio import normalize_voice_text
from content_pipeline.bots.audio import reference_audio_language_options
from content_pipeline.bots.audio import scan_reference_audio_library
from content_pipeline.bots.audio import voice_gender_options
from content_pipeline.bots.audio import voice_preview_language_options
from content_pipeline.bots.audio import voice_preview_presets
from content_pipeline.bots.image import ImageVariant, image_provider
from content_pipeline.bots.prompt import build_cinematic_image_prompt
from content_pipeline.bots.prompt import build_image_style_pack
from content_pipeline.config import Settings
from content_pipeline.pipeline import run_linkedin_mvp


def _apply_streamlit_secrets() -> None:
    try:
        secrets = st.secrets
    except Exception:
        return

    def _secret(*path: str) -> str | None:
        current: object = secrets
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                return None
            current = current[key]
        return str(current) if current not in (None, "") else None

    direct_keys = [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_IMAGE_MODEL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "GCP_PROJECT_ID",
        "GCP_LOCATION",
        "IMAGEN_MODEL",
        "GEMINI_IMAGE_MODEL",
        "GEMINI_IMAGE_DAILY_BUDGET",
        "GEMINI_IMAGE_MIN_INTERVAL_SECONDS",
        "GEMINI_IMAGE_MAX_ATTEMPTS",
        "GEMINI_IMAGE_RETRY_BACKOFF_SECONDS",
        "IMAGE_FALLBACK_PROVIDER",
        "VOICE_PROVIDER",
        "INDIAN_TTS_VOICE",
        "IMAGE_MAX_DIMENSION",
        "IMAGE_MAX_BYTES",
        "PUBLISH_LINKEDIN",
        "LINKEDIN_CLIENT_ID",
        "LINKEDIN_CLIENT_SECRET",
        "LINKEDIN_REDIRECT_URI",
        "LINKEDIN_ACCESS_TOKEN",
        "LINKEDIN_MEMBER_URN",
        "CANVA_CLIENT_ID",
        "CANVA_CLIENT_SECRET",
        "CANVA_REDIRECT_URI",
        "CANVA_REFRESH_TOKEN",
        "CANVA_BRAND_TEMPLATE_ID",
        "MOTION_PROVIDER",
        "MOTION_MODEL",
        "LUMAAI_API_KEY",
        "LUMA_IMAGE_MODEL",
        "LUMA_VIDEO_MODEL",
        "YOUTUBE_CLIENT_SECRETS_FILE",
        "YOUTUBE_TOKEN_FILE",
        "YOUTUBE_CHANNEL_URL",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_USER_ID",
        "INSTAGRAM_CLIENT_ID",
        "INSTAGRAM_CLIENT_SECRET",
        "CONTENT_OUTPUT_DIR",
        "PIPELINE_MODE",
        "PROMPT_PROVIDER",
        "IMAGE_PROVIDER",
        "REFERENCE_AUDIO_DIR",
    ]
    for key in direct_keys:
        value = _secret(key)
        if value and not os.environ.get(key):
            os.environ[key] = value

    gemini_keys = []
    nested_gemini = secrets.get("gemini_keys", {})
    if isinstance(nested_gemini, Mapping):
        for index in range(1, 5):
            value = nested_gemini.get(f"key_{index}")
            if value:
                gemini_keys.append(str(value))
    for index, value in enumerate(gemini_keys, start=1):
        env_key = "GEMINI_API_KEY" if index == 1 else f"GEMINI_API_KEY_{index}"
        if not os.environ.get(env_key):
            os.environ[env_key] = value

    openai_keys = []
    nested_openai = secrets.get("openai_keys", {})
    if isinstance(nested_openai, Mapping):
        for index in range(1, 6):
            value = nested_openai.get(f"key_{index}")
            if value:
                openai_keys.append(str(value))
    for index, value in enumerate(openai_keys, start=1):
        env_key = "OPENAI_API_KEY" if index == 1 else f"OPENAI_API_KEY_{index}"
        if not os.environ.get(env_key):
            os.environ[env_key] = value


def resolve_output_dir(raw_value: str) -> Path:
    output_dir = Path(raw_value).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    return output_dir


def resolve_project_path(raw_value: str) -> Path:
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def latest_daily_day(output_dir: Path) -> str | None:
    daily_root = output_dir / "daily"
    if not daily_root.exists():
        return None
    days = sorted(path.name for path in daily_root.iterdir() if path.is_dir())
    return days[-1] if days else None


def recent_daily_days(output_dir: Path, limit: int = 14) -> list[str]:
    daily_root = output_dir / "daily"
    if not daily_root.exists():
        return []
    days = sorted((path.name for path in daily_root.iterdir() if path.is_dir()), reverse=True)
    return days[:limit]


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_studio_state(output_dir: Path) -> dict[str, str]:
    path = output_dir / ".runtime" / "studio_state.json"
    payload = load_json(path)
    if not payload:
        return {}
    state: dict[str, str] = {}
    for key in (
        "voice_preset_choice",
        "voice_provider",
        "voice_name",
        "voice_preview_text",
        "voice_preview_path",
        "voice_library_language_filter",
        "voice_gender_filter",
        "reference_audio_root",
        "reference_audio_default_language",
        "reference_audio_language_filter",
        "reference_audio_selected_clip",
        "reference_audio_preview_path",
        "reference_audio_bank_size",
        "image_provider",
        "image_topic",
        "image_subject",
        "image_prompt",
        "music_mood",
        "music_duration_seconds",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value:
            state[key] = value
    return state


def save_studio_state(output_dir: Path, state: dict[str, str]) -> None:
    path = output_dir / ".runtime" / "studio_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "preview"


def render_image_preview(path: Path) -> None:
    if path.suffix.lower() == ".svg":
        components.html(path.read_text(encoding="utf-8"), height=720, scrolling=False)
    else:
        st.image(str(path), use_container_width=True)


def apply_voice_preset_by_key(preset_key: str) -> None:
    preset_lookup = {preset.key: preset for preset in voice_preview_presets()}
    preset = preset_lookup.get(preset_key)
    if not preset:
        return
    st.session_state["voice_preset_choice"] = preset.key
    st.session_state["voice_provider_choice"] = "edge"
    st.session_state["voice_name_choice"] = preset.voice
    st.session_state["voice_preview_text"] = preset.sample_text


def _voice_preview_fallback_voice(gender: str, language: str = "en-IN") -> str:
    gender = (gender or "all").strip().lower()
    language = (language or "").strip().lower()
    if gender == "male":
        if language.startswith("hi"):
            return "hi-IN-AaravNeural"
        return "en-IN-PrabhatNeural"
    if gender == "female":
        if language.startswith("hi"):
            return "hi-IN-SwaraNeural"
        return "en-IN-NeerjaNeural"
    return "en-IN-PrabhatNeural"


def _generate_voice_preview_with_fallback(
    *,
    text: str,
    preview_path: Path,
    voice: str,
    gender_hint: str = "all",
    language_hint: str = "en-IN",
) -> Path:
    try:
        return generate_voice_preview(
            text,
            preview_path,
            provider="edge",
            voice=voice,
        )
    except Exception as exc:
        fallback_voice = _voice_preview_fallback_voice(gender_hint, language_hint)
        if voice != fallback_voice:
            try:
                fallback_path = preview_path.with_name(f"{preview_path.stem}_edge{preview_path.suffix}")
                generate_voice_preview(
                    text,
                    fallback_path,
                    provider="edge",
                    voice=fallback_voice,
                )
                st.warning("Voice preview could not run with the selected voice, so the app fell back to Edge TTS.")
                return fallback_path
            except Exception:
                pass
        raise exc


def file_chip(label: str, path: Path) -> str:
    return f"""
    <div class="file-chip">
      <div class="file-chip-label">{label}</div>
      <div class="file-chip-path">{path}</div>
    </div>
    """


def status_pill(label: str, value: str) -> str:
    return f"""
    <div class="status-pill">
      <span class="status-pill-label">{escape(label)}</span>
      <span class="status-pill-value">{escape(value)}</span>
    </div>
    """


def audio_file_list(paths: list[Path]) -> None:
    if not paths:
        st.info("No audio files found yet. Run the pipeline or open a day with generated samples.")
        return
    for path in paths:
        st.markdown(f"**{path.name}**")
        st.audio(str(path))
        st.caption(str(path))


def day_overview(day_root: Path) -> dict[str, object]:
    dashboard_path = day_root / "daily_dashboard.html"
    audio_path = day_root / "audio_status.html"
    voice_path = day_root / "voice_status.html"
    if day_root.exists():
        file_count = sum(1 for path in day_root.rglob("*") if path.is_file())
        files = [path for path in day_root.rglob("*") if path.is_file()]
    else:
        file_count = 0
        files = []
    suffix_counts: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower() or "[no extension]"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    return {
        "file_count": file_count,
        "suffix_counts": suffix_counts,
        "dashboard_exists": dashboard_path.exists(),
        "audio_exists": audio_path.exists(),
        "voice_exists": voice_path.exists(),
        "dashboard_path": dashboard_path,
        "audio_path": audio_path,
        "voice_path": voice_path,
    }


def render_overview_card(title: str, value: str, detail: str) -> None:
    st.markdown(
        f"""
        <div class="metric-box">
          <div class="metric-label">{escape(title)}</div>
          <div class="metric-value">{escape(value)}</div>
          <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.4;">{escape(detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_link_card(title: str, detail: str, link_label: str | None, link_url: str | None) -> None:
    body = f"""
        <div class="action-card">
          <h3>{escape(title)}</h3>
          <p>{escape(detail)}</p>
    """
    if link_label and link_url:
        body += f'<div class="action-link"><a href="{escape(link_url, quote=True)}" target="_blank">{escape(link_label)}</a></div>'
    else:
        body += '<div class="action-link" style="color:#94a3b8;">Not available yet.</div>'
    body += "</div>"
    st.markdown(body, unsafe_allow_html=True)


def _health_hint(name: str) -> str:
    hints = {
        "Dashboard": "Run the pipeline or inspect another day that already has a daily dashboard.",
        "Audio": "Open the audio tab after a run, or generate the day again if audio artifacts are missing.",
        "Voice": "Voice status appears after the daily voice bundle is written for that day.",
    }
    return hints.get(name, "Check the selected day and rerun the pipeline if needed.")


def render_health_banner(overview: dict[str, object]) -> None:
    checks = [
        ("Dashboard", bool(overview["dashboard_exists"])),
        ("Audio", bool(overview["audio_exists"])),
        ("Voice", bool(overview["voice_exists"])),
    ]
    healthy = sum(1 for _, ok in checks if ok)
    missing = [name for name, ok in checks if not ok]
    label = "All clear" if healthy == len(checks) else "Needs attention"
    detail = "Everything is ready for the selected day." if not missing else "Missing: " + ", ".join(missing)
    pill_bits = []
    for name, ok in checks:
        pill_bits.append(f'<span style="margin-right:12px;">{escape(name)}: {"ready" if ok else "missing"}</span>')
    hint_bits = ""
    if missing:
        hint_bits = "".join(
            f'<li style="margin-top:6px;">{escape(name)}: {escape(_health_hint(name))}</li>'
            for name in missing
        )
    st.markdown(
        f"""
        <div class="action-card" style="margin:14px 0 16px;">
          <h3>{escape(label)}</h3>
          <p>{escape(detail)}</p>
          <div class="action-link" style="color:#cbd5e1;">{''.join(pill_bits)}</div>
          {"<ul style='margin:10px 0 0 18px;color:#cbd5e1;line-height:1.5;'>" + hint_bits + "</ul>" if hint_bits else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_preview_panel(overview: dict[str, object], day_root: Path) -> None:
    st.markdown("#### Latest output preview")
    st.caption(
        "Total files: "
        f"{overview['file_count']} · HTML: {overview['suffix_counts'].get('.html', 0)} · "
        f"JSON: {overview['suffix_counts'].get('.json', 0)} · Images: "
        f"{sum(count for suffix, count in overview['suffix_counts'].items() if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.svg'})}"
    )
    preview_cols = st.columns(3)
    items = [
        (
            "Dashboard",
            day_root / "daily_dashboard.html",
            overview["dashboard_exists"],
            "Open the daily dashboard HTML",
        ),
        (
            "Audio",
            day_root / "audio_status.html",
            overview["audio_exists"],
            "Open the unified audio summary",
        ),
        (
            "Voice",
            day_root / "voice_status.html",
            overview["voice_exists"],
            "Open the voice bundle summary",
        ),
    ]
    for column, (title, path, exists, detail) in zip(preview_cols, items):
        with column:
            st.markdown(
                f"""
                <div class="metric-box">
                  <div class="metric-label">{escape(title)}</div>
                  <div class="metric-value">{'ready' if exists else 'missing'}</div>
                  <div style="margin-top:4px;color:#7dd3fc;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;">{escape(path.name)}</div>
                  <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.4;">{escape(detail)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if exists:
                st.markdown(f"[Open {title.lower()}]({path.as_uri()})")


def render_frontdoor(settings: Settings) -> None:
    latest_day = latest_daily_day(settings.output_dir)
    default_day = date.fromisoformat(latest_day) if latest_day else date.today()

    st.sidebar.header("Studio Controls")
    output_dir_input = st.sidebar.text_input("Output directory", value=str(settings.output_dir))
    ui_output_dir = resolve_output_dir(output_dir_input)
    saved_studio_state = load_studio_state(ui_output_dir)
    if st.session_state.get("_studio_output_dir") != str(ui_output_dir):
        st.session_state["_studio_output_dir"] = str(ui_output_dir)
        st.session_state["voice_preset_choice"] = saved_studio_state.get("voice_preset_choice", "english_explainer")
        st.session_state["voice_provider_choice"] = "edge"
        st.session_state["voice_name_choice"] = saved_studio_state.get("voice_name", settings.indian_tts_voice)
        st.session_state["voice_preview_text"] = saved_studio_state.get(
            "voice_preview_text",
            "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm.",
        )
        st.session_state["image_provider_choice"] = saved_studio_state.get("image_provider", settings.image_provider)
        st.session_state["image_topic"] = saved_studio_state.get("image_topic", "Agile project management")
        st.session_state["image_subject"] = saved_studio_state.get(
            "image_subject",
            "a team reviewing a glowing workflow board",
        )
        st.session_state["image_prompt"] = saved_studio_state.get(
            "image_prompt",
            build_cinematic_image_prompt(
                st.session_state["image_topic"],
                st.session_state["image_subject"],
            ),
        )
        st.session_state["music_mood"] = saved_studio_state.get("music_mood", "cinematic")
        st.session_state["music_duration_seconds"] = int(saved_studio_state.get("music_duration_seconds", "8"))
        st.session_state["reference_audio_root"] = saved_studio_state.get(
            "reference_audio_root",
            str(
                settings.reference_audio_dir
                if settings.reference_audio_dir is not None
                else ui_output_dir / "reference_audio" / "indian_languages_audio_dataset"
            ),
        )
        st.session_state["reference_audio_language_filter"] = saved_studio_state.get(
            "reference_audio_language_filter",
            "all",
        )
        st.session_state["reference_audio_preview_path"] = saved_studio_state.get(
            "reference_audio_preview_path",
            "",
        )
        st.session_state["reference_audio_selected_clip"] = saved_studio_state.get(
            "reference_audio_selected_clip",
            "",
        )
        st.session_state["reference_audio_bank_size"] = int(
            saved_studio_state.get("reference_audio_bank_size", "24")
        )
        st.session_state["reference_audio_default_language"] = saved_studio_state.get(
            "reference_audio_default_language",
            "hindi",
        )
        st.session_state["image_preview_path"] = ""
        st.session_state["music_preview_path"] = ""
    st.session_state.setdefault("voice_preset_choice", "english_explainer")
    st.session_state.setdefault("voice_provider_choice", "edge")
    st.session_state.setdefault("voice_name_choice", settings.indian_tts_voice)
    st.session_state.setdefault(
        "voice_preview_text",
        "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm.",
    )
    st.session_state.setdefault("image_provider_choice", settings.image_provider)
    st.session_state.setdefault("image_topic", "Agile project management")
    st.session_state.setdefault("image_subject", "a team reviewing a glowing workflow board")
    st.session_state.setdefault(
        "image_prompt",
        build_cinematic_image_prompt(
            st.session_state["image_topic"],
            st.session_state["image_subject"],
        ),
    )
    st.session_state.setdefault("music_mood", "cinematic")
    st.session_state.setdefault("music_duration_seconds", 8)
    st.session_state.setdefault("image_preview_path", "")
    st.session_state.setdefault("music_preview_path", "")
    st.session_state.setdefault("voice_preview_path", "")
    st.session_state.setdefault("voice_library_language_filter", "all")
    st.session_state.setdefault("voice_gender_filter", "all")
    st.session_state.setdefault("reference_audio_root", "")
    st.session_state.setdefault("reference_audio_default_language", "hindi")
    st.session_state.setdefault("reference_audio_language_filter", "all")
    st.session_state.setdefault("reference_audio_selected_clip", "")
    st.session_state.setdefault("reference_audio_preview_path", "")
    st.session_state.setdefault("reference_audio_bank_size", 24)
    st.sidebar.subheader("Voice Studio")
    gender_options = voice_gender_options()
    gender_map = {value: label for value, label in gender_options}
    default_voice_gender = st.session_state.get("voice_gender_filter", "all")
    if default_voice_gender not in gender_map:
        default_voice_gender = "all"
        st.session_state["voice_gender_filter"] = default_voice_gender
    st.sidebar.selectbox(
        "Voice gender",
        options=[value for value, _ in gender_options],
        index=[value for value, _ in gender_options].index(default_voice_gender),
        format_func=lambda value: gender_map.get(value, value),
        key="voice_gender_filter",
    )
    preset_options = filter_voice_preview_presets(
        voice_preview_presets(),
        gender=st.session_state["voice_gender_filter"],
    )
    if not preset_options:
        preset_options = voice_preview_presets()
    preset_map = {preset.key: preset for preset in preset_options}
    preset_default = st.session_state.get("voice_preset_choice", preset_options[0].key)
    if preset_default not in preset_map:
        preset_default = preset_options[0].key
        st.session_state["voice_preset_choice"] = preset_default
    st.sidebar.selectbox(
        "Voice preset",
        options=[preset.key for preset in preset_options],
        index=[preset.key for preset in preset_options].index(preset_default),
        format_func=lambda value: f"{preset_map[value].label} - {preset_map[value].description}",
        key="voice_preset_choice",
    )
    apply_voice_preset = st.sidebar.button("Apply voice preset", use_container_width=True)
    if apply_voice_preset:
        preset = preset_map[st.session_state["voice_preset_choice"]]
        st.session_state["voice_provider_choice"] = "edge"
        st.session_state["voice_name_choice"] = preset.voice
        st.session_state["voice_preview_text"] = preset.sample_text
        st.rerun()
    st.sidebar.selectbox(
        "Voice provider",
        options=("edge",),
        index=0,
        key="voice_provider_choice",
    )
    voice_provider_choice = "edge"
    voice_options = available_voice_options("edge", st.session_state["voice_gender_filter"])
    if not voice_options:
        voice_options = available_voice_options("edge")
    voice_option_values = [voice for voice, _ in voice_options]
    default_voice = st.session_state["voice_name_choice"] or settings.indian_tts_voice
    if default_voice not in voice_option_values:
        default_voice = voice_option_values[0]
    if st.session_state["voice_name_choice"] not in voice_option_values:
        st.session_state["voice_name_choice"] = default_voice
    voice_name_choice = st.sidebar.selectbox(
        "Voice name",
        options=voice_option_values,
        index=voice_option_values.index(st.session_state["voice_name_choice"]),
        format_func=lambda value: next(label for voice, label in voice_options if voice == value),
        key="voice_name_choice",
    )
    voice_preview_text = st.sidebar.text_area(
        "Voiceover script preview",
        value=st.session_state["voice_preview_text"],
        height=140,
        key="voice_preview_text",
    )
    current_voice_preset = preset_map[st.session_state["voice_preset_choice"]]
    st.sidebar.caption(
        f"Preset: {current_voice_preset.label} · Script language: {current_voice_preset.language} · Voice type: {current_voice_preset.gender}"
    )
    language_options = voice_preview_language_options()
    language_map = {value: label for value, label in language_options}
    default_language_filter = st.session_state.get("voice_library_language_filter", "all")
    if default_language_filter not in language_map:
        default_language_filter = "all"
        st.session_state["voice_library_language_filter"] = default_language_filter
    st.sidebar.selectbox(
        "Voice library language",
        options=[value for value, _ in language_options],
        index=[value for value, _ in language_options].index(default_language_filter),
        format_func=lambda value: language_map.get(value, value),
        key="voice_library_language_filter",
    )
    st.sidebar.caption(
        f"Voice gender filter: {gender_map.get(st.session_state['voice_gender_filter'], st.session_state['voice_gender_filter'])}"
    )
    st.sidebar.subheader("Image Studio")
    image_provider_options = ("mock", "gemini", "imagen", "openai")
    image_provider_default = st.session_state["image_provider_choice"]
    if image_provider_default not in image_provider_options:
        image_provider_default = settings.image_provider if settings.image_provider in image_provider_options else "mock"
        st.session_state["image_provider_choice"] = image_provider_default
    st.sidebar.selectbox(
        "Image provider",
        options=image_provider_options,
        index=image_provider_options.index(image_provider_default),
        key="image_provider_choice",
    )
    st.sidebar.text_input("Image topic", key="image_topic")
    st.sidebar.text_input("Image subject", key="image_subject")
    st.sidebar.subheader("Music Studio")
    music_mood_options = ("cinematic", "focus", "warm", "uplift", "ambient")
    music_mood_default = st.session_state["music_mood"]
    if music_mood_default not in music_mood_options:
        music_mood_default = "cinematic"
        st.session_state["music_mood"] = music_mood_default
    st.sidebar.selectbox(
        "Music mood",
        options=music_mood_options,
        index=music_mood_options.index(music_mood_default),
        key="music_mood",
    )
    st.sidebar.slider("Music preview length (seconds)", 4, 15, key="music_duration_seconds")
    st.sidebar.subheader("Reference Audio")
    default_reference_audio_root = (
        str(settings.reference_audio_dir)
        if settings.reference_audio_dir is not None
        else str(ui_output_dir / "reference_audio" / "indian_languages_audio_dataset")
    )
    if not st.session_state["reference_audio_root"]:
        st.session_state["reference_audio_root"] = default_reference_audio_root
    st.sidebar.text_input(
        "Reference dataset folder",
        key="reference_audio_root",
        help="Point this to the downloaded Kaggle dataset folder with language subfolders of MP3 clips.",
    )
    st.sidebar.text_input(
        "Reference bank language",
        key="reference_audio_default_language",
        help="Use this when the folder is flat, such as a single Hindi audio bank with numeric filenames.",
    )
    st.sidebar.slider("Reference bank size", 20, 30, key="reference_audio_bank_size")
    reference_audio_options = reference_audio_language_options()
    reference_audio_language_map = {value: label for value, label in reference_audio_options}
    if st.session_state["reference_audio_language_filter"] not in reference_audio_language_map:
        st.session_state["reference_audio_language_filter"] = "all"
    st.sidebar.selectbox(
        "Reference language",
        options=[value for value, _ in reference_audio_options],
        index=[value for value, _ in reference_audio_options].index(
            st.session_state["reference_audio_language_filter"]
        ),
        format_func=lambda value: reference_audio_language_map.get(value, value),
        key="reference_audio_language_filter",
    )
    if st.sidebar.button("Load latest day", use_container_width=True, disabled=not latest_day):
        st.session_state["run_day"] = default_day
        st.session_state["inspect_day"] = default_day
        st.rerun()
    recent_days = recent_daily_days(settings.output_dir)
    selected_day = latest_day or default_day.isoformat()
    if recent_days:
        selected_day = st.sidebar.selectbox(
            "Recent days",
            options=recent_days,
            index=0,
        )
        if st.sidebar.button("Load selected day", use_container_width=True):
            selected = date.fromisoformat(selected_day)
            st.session_state["run_day"] = selected
            st.session_state["inspect_day"] = selected
            st.rerun()
    else:
        st.sidebar.caption("No recent runs yet.")
    run_day = st.sidebar.date_input(
        "Run day",
        value=st.session_state.get("run_day", default_day),
        key="run_day",
    )
    inspect_day = st.sidebar.date_input(
        "Inspect day",
        value=st.session_state.get("inspect_day", default_day),
        key="inspect_day",
    )
    show_json = st.sidebar.checkbox("Show raw JSON", value=False)

    ui_settings = replace(settings, output_dir=ui_output_dir)
    ui_settings = replace(
        ui_settings,
        voice_provider=voice_provider_choice,
        indian_tts_voice=voice_name_choice,
    )
    run_date = run_day.isoformat()
    inspect_date = inspect_day.isoformat()

    st.markdown(
        """
        <style>
          :root {
            --bg: #020617;
            --panel: rgba(15, 23, 42, 0.9);
            --panel-strong: rgba(15, 23, 42, 0.98);
            --line: #334155;
            --text: #f8fafc;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --accent-2: #a855f7;
            --accent-3: #f59e0b;
          }
          .stApp {
            background:
              radial-gradient(circle at top left, rgba(56,189,248,0.14), transparent 26%),
              radial-gradient(circle at top right, rgba(168,85,247,0.12), transparent 22%),
              linear-gradient(180deg, #020617 0%, #0f172a 100%);
          }
          .hero {
            padding: 28px;
            border-radius: 24px;
            background: linear-gradient(135deg, rgba(15,23,42,.94), rgba(2,6,23,.98));
            border: 1px solid var(--line);
            margin-bottom: 16px;
            box-shadow: 0 20px 45px rgba(2, 6, 23, 0.35);
          }
          .hero h1 {
            margin: 0;
            font-size: 38px;
            letter-spacing: -0.03em;
            color: var(--text);
          }
          .hero p {
            margin-top: 8px;
            color: var(--muted);
            line-height: 1.5;
          }
          .status-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 14px 0 20px;
          }
          .status-pill {
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding: 14px 16px;
            border-radius: 18px;
            background: rgba(15, 23, 42, 0.82);
            border: 1px solid var(--line);
          }
          .status-pill-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: .12em;
            color: var(--muted);
            font-weight: 800;
          }
          .status-pill-value {
            color: var(--text);
            font-size: 16px;
            font-weight: 800;
            word-break: break-word;
          }
          .action-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
            margin: 4px 0 16px;
          }
          .action-card {
            padding: 18px;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(15,23,42,.94), rgba(15,23,42,.78));
            border: 1px solid var(--line);
            box-shadow: 0 12px 30px rgba(2, 6, 23, 0.25);
          }
          .action-card h3 {
            margin: 0;
            color: var(--text);
            font-size: 18px;
          }
          .action-card p {
            margin: 8px 0 14px;
            color: var(--muted);
            line-height: 1.45;
          }
          .action-link a {
            color: #cffafe;
            text-decoration: none;
            font-weight: 800;
          }
          .action-link a:hover {
            text-decoration: underline;
          }
          .metric-box, .file-chip, .panel-box {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 16px;
          }
          .metric-label {
            font-size: 12px;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: var(--muted);
          }
          .metric-value {
            margin-top: 6px;
            font-size: 22px;
            font-weight: 800;
            color: var(--text);
          }
          .file-chip + .file-chip { margin-top: 10px; }
          .file-chip-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: var(--accent);
            font-weight: 800;
          }
          .file-chip-path {
            margin-top: 6px;
            color: #e2e8f0;
            word-break: break-all;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <section class="hero">
          <h1>Content Pipeline Studio</h1>
          <p>
            A control center for your daily pipeline, unified audio status, blocker memory,
            and image style tooling. Run the daily build, jump straight into the newest run,
            and inspect the artifacts without hunting through folders.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    latest_dir = ui_settings.output_dir / "daily" / latest_day if latest_day else None
    latest_dashboard = latest_dir / "daily_dashboard.html" if latest_dir else None
    latest_audio = latest_dir / "audio_status.html" if latest_dir else None
    latest_voice = latest_dir / "voice_status.html" if latest_dir else None
    latest_overview = day_overview(latest_dir) if latest_dir else {
        "file_count": 0,
        "suffix_counts": {},
        "dashboard_exists": False,
        "audio_exists": False,
        "voice_exists": False,
        "dashboard_path": None,
        "audio_path": None,
        "voice_path": None,
    }
    selected_day_dir = ui_settings.output_dir / "daily" / inspect_date
    selected_overview = day_overview(selected_day_dir)

    st.markdown(
        f"""
        <div class="status-strip">
          {status_pill("Prompt provider", settings.prompt_provider)}
          {status_pill("Image provider", settings.image_provider)}
          {status_pill("Voice provider", voice_provider_choice)}
          {status_pill("Voice preset", voice_name_choice)}
          {status_pill("Selected day", inspect_date)}
          {status_pill("Latest day", latest_day or "none yet")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_cols = st.columns(3)
    with action_cols[0]:
        st.markdown(
            """
            <div class="action-card">
              <h3>Run the pipeline</h3>
              <p>Generate today’s daily artifacts with the same flow used by the CLI.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_clicked = st.button("Run pipeline", type="primary", use_container_width=True)
    with action_cols[1]:
        st.markdown(
            """
            <div class="action-card">
              <h3>Latest dashboard</h3>
              <p>Open the newest dashboard if a run already exists in the output folder.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if latest_dashboard and latest_dashboard.exists():
            st.markdown(
                f'<div class="action-link"><a href="{latest_dashboard.as_uri()}" target="_blank">Open latest dashboard</a></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No dashboard yet.")
    with action_cols[2]:
        st.markdown(
            """
            <div class="action-card">
              <h3>Audio front door</h3>
              <p>Jump straight into voice, science audio, and PM audio status.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if latest_audio and latest_audio.exists():
            st.markdown(
                f'<div class="action-link"><a href="{latest_audio.as_uri()}" target="_blank">Open audio front door</a></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No audio front door yet.")

    link_cols = st.columns(3)
    with link_cols[0]:
        render_link_card(
            "Selected dashboard",
            "Open the dashboard for the day you are currently inspecting.",
            "Open dashboard",
            selected_overview["dashboard_path"].as_uri() if selected_overview["dashboard_exists"] else None,
        )
    with link_cols[1]:
        render_link_card(
            "Selected audio",
            "Open the audio front door for the currently selected day.",
            "Open audio",
            selected_overview["audio_path"].as_uri() if selected_overview["audio_exists"] else None,
        )
    with link_cols[2]:
        render_link_card(
            "Selected voice",
            "Open the voice bundle for the currently selected day.",
            "Open voice",
            selected_overview["voice_path"].as_uri() if selected_overview["voice_exists"] else None,
        )

    render_health_banner(selected_overview)
    render_preview_panel(selected_overview, selected_day_dir)

    overview_cols = st.columns(4)
    with overview_cols[0]:
        render_overview_card(
            "Selected day",
            inspect_date,
            "The day currently shown in the dashboard and artifact panels.",
        )
    with overview_cols[1]:
        render_overview_card(
            "Artifacts",
            str(selected_overview["file_count"]),
            "Total files in the selected daily folder.",
        )
    with overview_cols[2]:
        render_overview_card(
            "Dashboard",
            "ready" if selected_overview["dashboard_exists"] else "missing",
            "The daily dashboard HTML for the selected run.",
        )
    with overview_cols[3]:
        render_overview_card(
            "Audio bundle",
            "ready" if selected_overview["audio_exists"] else "missing",
            "The unified audio status front door for the selected run.",
        )

    if run_clicked:
        with st.spinner(f"Generating the daily run for {run_date}..."):
            try:
                result = run_linkedin_mvp(run_date, ui_settings)
            except Exception as exc:
                st.session_state["last_run_error"] = str(exc)
            else:
                st.session_state["last_run_result"] = result
                st.session_state["last_run_day"] = run_date
                st.success(f"Pipeline complete for {run_date}")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown(
            f"""
            <div class="metric-box">
              <div class="metric-label">Output dir</div>
              <div class="metric-value">{ui_settings.output_dir}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f"""
            <div class="metric-box">
              <div class="metric-label">Run date</div>
              <div class="metric-value">{run_date}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown(
            f"""
            <div class="metric-box">
              <div class="metric-label">Inspect day</div>
              <div class="metric-value">{inspect_date}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_d:
        st.markdown(
            f"""
            <div class="metric-box">
              <div class="metric-label">Latest day</div>
              <div class="metric-value">{latest_day or "none yet"}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    tab_studio, tab_run, tab_dashboard, tab_audio, tab_files = st.tabs(
        ["Studio", "Run", "Dashboard", "Audio", "Files"]
    )

    with tab_studio:
        st.subheader("Image studio")
        image_style_pack = build_image_style_pack(
            st.session_state["image_topic"],
            subject=st.session_state["image_subject"],
        )
        image_provider_choice = st.session_state["image_provider_choice"]
        image_prompt_default = st.session_state["image_prompt"] or build_cinematic_image_prompt(
            st.session_state["image_topic"],
            st.session_state["image_subject"],
        )
        image_prompt = st.text_area("Image prompt", value=image_prompt_default, height=180, key="image_prompt")
        st.caption("Tip: keep the prompt vivid, specific, and free of text, logos, and watermarks.")
        image_action_cols = st.columns([1, 1])
        with image_action_cols[0]:
            if st.button("Generate image preview", use_container_width=True):
                try:
                    provider = image_provider(replace(ui_settings, image_provider=image_provider_choice))
                    variant = ImageVariant("1:1", 1080, 1080, "image_preview")
                    preview_path = ui_settings.output_dir / ".runtime" / "image_previews" / (
                        f"{_slugify(st.session_state['image_topic'])}_{_slugify(st.session_state['image_subject'])}_{image_provider_choice}{provider.extension}"
                    )
                    preview_path.parent.mkdir(parents=True, exist_ok=True)
                    preview_path.write_bytes(provider.create(image_prompt, variant))
                    st.session_state["image_preview_path"] = str(preview_path)
                    st.success(f"Image preview written to {preview_path}")
                except Exception as exc:
                    st.error(str(exc))
        with image_action_cols[1]:
            st.markdown(
                f"""
                <div class="metric-box">
                  <div class="metric-label">Selected image provider</div>
                  <div class="metric-value">{escape(image_provider_choice)}</div>
                  <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.4;">Topic: {escape(st.session_state['image_topic'])}<br>Subject: {escape(st.session_state['image_subject'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if st.session_state["image_preview_path"]:
            preview_path = Path(st.session_state["image_preview_path"])
            if preview_path.exists():
                render_image_preview(preview_path)
        with st.expander("Image prompt pack", expanded=False):
            st.json(image_style_pack.as_dict())
            st.code(image_prompt, language="text")

        st.markdown("### Music studio")
        music_mood = st.session_state["music_mood"]
        music_duration = int(st.session_state["music_duration_seconds"])
        music_action_cols = st.columns([1, 1])
        with music_action_cols[0]:
            if st.button("Generate music preview", use_container_width=True):
                try:
                    preview_path = ui_settings.output_dir / ".runtime" / "music_previews" / (
                        f"{_slugify(music_mood)}_{music_duration}s.wav"
                    )
                    generate_music_preview(preview_path, music_mood, duration_seconds=music_duration)
                    st.session_state["music_preview_path"] = str(preview_path)
                    st.success(f"Music preview written to {preview_path}")
                except Exception as exc:
                    st.error(str(exc))
        with music_action_cols[1]:
            st.markdown(
                f"""
                <div class="metric-box">
                  <div class="metric-label">Selected mood</div>
                  <div class="metric-value">{escape(music_mood)}</div>
                  <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.4;">Preview length: {music_duration} seconds</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if st.session_state["music_preview_path"]:
            music_preview_path = Path(st.session_state["music_preview_path"])
            if music_preview_path.exists():
                st.audio(str(music_preview_path))
                st.caption(str(music_preview_path))

    with tab_run:
        left, right = st.columns([1.2, 0.8])
        with left:
            st.subheader("Run the daily pipeline")
            st.write("This triggers the same daily content generation flow your CLI uses.")
            st.caption(
                f"Latest day: {latest_day or 'none yet'} · Files in latest run: {latest_overview['file_count']}"
            )

            if "last_run_error" in st.session_state:
                st.error(st.session_state["last_run_error"])

            if "last_run_result" in st.session_state:
                result = st.session_state["last_run_result"]
                st.markdown("#### Last result")
                if show_json:
                    st.code(json.dumps(result, indent=2, ensure_ascii=False), language="json")
                else:
                    st.json(result)

        with right:
            st.subheader("Quick launch")
            current_day_dir = selected_day_dir
            overview = selected_overview
            dashboard_path = overview["dashboard_path"]
            audio_path = overview["audio_path"]
            voice_path = overview["voice_path"]
            st.markdown(file_chip("Daily dashboard", dashboard_path), unsafe_allow_html=True)
            st.markdown(file_chip("Audio front door", audio_path), unsafe_allow_html=True)
            st.markdown(file_chip("Voice status", voice_path), unsafe_allow_html=True)
            if dashboard_path.exists():
                st.markdown(f"[Open daily dashboard]({dashboard_path.as_uri()})")
            if audio_path.exists():
                st.markdown(f"[Open audio front door]({audio_path.as_uri()})")
            if voice_path.exists():
                st.markdown(f"[Open voice status]({voice_path.as_uri()})")

    with tab_dashboard:
        st.subheader("Daily dashboard")
        dashboard_path = ui_settings.output_dir / "daily" / inspect_date / "daily_dashboard.html"
        if dashboard_path.exists():
            dashboard_html = dashboard_path.read_text(encoding="utf-8")
            components.html(dashboard_html, height=1150, scrolling=True)
        else:
            st.info("Run the pipeline or pick a day that already has a daily dashboard.")
            st.caption(str(dashboard_path))
        if dashboard_path.exists():
            st.markdown(f"[Open dashboard file]({dashboard_path.as_uri()})")

    with tab_audio:
        st.subheader("Audio front door")
        audio_path = ui_settings.output_dir / "daily" / inspect_date / "audio_status.html"
        audio_json = ui_settings.output_dir / "daily" / inspect_date / "audio_status.json"
        voice_json = ui_settings.output_dir / "daily" / inspect_date / "voice_status.json"
        if audio_path.exists():
            components.html(audio_path.read_text(encoding="utf-8"), height=520, scrolling=True)
        else:
            st.info("No audio front door found yet for this day.")

        with st.expander("Raw audio JSON", expanded=False):
            payload = load_json(audio_json)
            if payload:
                if show_json:
                    st.code(json.dumps(payload, indent=2, ensure_ascii=False), language="json")
                else:
                    st.json(payload)
            else:
                st.write("No audio status JSON found.")

        with st.expander("Voice bundle", expanded=False):
            voice_payload = load_json(voice_json)
            if voice_payload:
                st.json(voice_payload)
                sample_files = [
                    Path(p)
                    for p in voice_payload.get("sample_files", [])
                    if isinstance(p, str)
                ]
                audio_file_list(sample_files)
                missing_files = [
                    Path(p)
                    for p in voice_payload.get("missing_sample_files", [])
                    if isinstance(p, str)
                ]
                if missing_files:
                    st.warning("Some sample audio files are missing for this day.")
                    st.markdown("**Missing sample audio**")
                    for path in missing_files:
                        st.caption(str(path))
            else:
                st.write("No voice bundle found for this day.")

        st.markdown("#### Voice library")
        preset_options = voice_preview_presets()
        library_language = st.session_state.get("voice_library_language_filter", "all")
        library_gender = st.session_state.get("voice_gender_filter", "all")
        visible_presets = filter_voice_preview_presets(
            preset_options,
            language=library_language,
            gender=library_gender,
        )
        st.caption(
            f"Showing {len(visible_presets)} of {len(preset_options)} presets "
            f"for {language_map.get(library_language, library_language)} · "
            f"{gender_map.get(library_gender, library_gender)}"
        )
        library_cols = st.columns(2)
        if not visible_presets:
            st.info("No voice presets match the selected language filter.")
        for index, preset in enumerate(visible_presets):
            column = library_cols[index % 2]
            sample_path = ui_settings.output_dir / ".runtime" / "voice_previews" / "library" / f"{preset.key}.mp3"
            with column:
                st.markdown(
                    f"""
                    <div class="metric-box">
                      <div class="metric-label">{escape(preset.label)}</div>
                      <div class="metric-value">{escape(preset.provider)} · {escape(preset.voice)}</div>
                      <div style="margin-top:4px;color:#7dd3fc;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;">{escape(preset.language)}</div>
                      <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.45;">{escape(preset.description)}</div>
                      <div style="margin-top:10px;color:#cbd5e1;font-size:12px;line-height:1.5;">{escape(preset.sample_text[:140])}{"..." if len(preset.sample_text) > 140 else ""}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                button_cols = st.columns(2)
                with button_cols[0]:
                    if st.button("Load script", key=f"load_voice_script_{preset.key}", use_container_width=True):
                        apply_voice_preset_by_key(preset.key)
                        st.rerun()
                with button_cols[1]:
                    if st.button("Play sample", key=f"play_voice_sample_{preset.key}", use_container_width=True):
                        try:
                            preview_dir = ui_settings.output_dir / ".runtime" / "voice_previews" / "library"
                            preview_dir.mkdir(parents=True, exist_ok=True)
                            preview_path = preview_dir / f"{preset.key}.mp3"
                            preview_output = _generate_voice_preview_with_fallback(
                                text=preset.sample_text,
                                preview_path=preview_path,
                                voice=preset.voice,
                                gender_hint=preset.gender,
                                language_hint=preset.language,
                            )
                            st.session_state["voice_preview_path"] = str(preview_output)
                            st.session_state["voice_provider_choice"] = "edge"
                            st.session_state["voice_name_choice"] = preset.voice
                            st.session_state["voice_preview_text"] = preset.sample_text
                            st.success(f"Sample written to {preview_output}")
                        except Exception as exc:
                            st.error(str(exc))
                if sample_path.exists():
                    st.audio(str(sample_path))
                    st.caption(str(sample_path))

        st.markdown("#### Voice studio")
        st.caption(
            f"Provider: {voice_provider_choice} · Voice: {voice_name_choice} · Normalized for narration preview."
        )
        normalized_preview = normalize_voice_text(voice_preview_text)
        st.text_area("Normalized script", value=normalized_preview, height=140, disabled=True)
        preview_root = ui_settings.output_dir / ".runtime" / "voice_previews"
        preview_root.mkdir(parents=True, exist_ok=True)
        preview_file = preview_root / f"{voice_provider_choice}_{voice_name_choice}.mp3"
        if st.button("Generate voice preview", use_container_width=True):
            try:
                preview_output = _generate_voice_preview_with_fallback(
                    text=voice_preview_text,
                    preview_path=preview_file,
                    voice=voice_name_choice,
                    gender_hint=st.session_state["voice_gender_filter"],
                    language_hint=current_voice_preset.language,
                )
                st.session_state["voice_preview_path"] = str(preview_output)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(f"Preview written to {st.session_state['voice_preview_path']}")
        if st.session_state.get("voice_preview_path"):
            preview_output_path = Path(st.session_state["voice_preview_path"])
            if preview_output_path.exists():
                st.audio(str(preview_output_path))
                st.caption(str(preview_output_path))

        st.markdown("#### Reference audio explorer")
        reference_audio_root = resolve_project_path(st.session_state["reference_audio_root"])
        reference_samples = scan_reference_audio_library(
            reference_audio_root,
            default_language=st.session_state["reference_audio_default_language"],
        )
        reference_samples = curate_reference_audio_bank(
            reference_samples,
            limit=int(st.session_state["reference_audio_bank_size"]),
        )
        available_languages = sorted({sample.language for sample in reference_samples})
        reference_language_options = reference_audio_language_options(available_languages or None)
        reference_language_map = {value: label for value, label in reference_language_options}
        if st.session_state["reference_audio_language_filter"] not in reference_language_map:
            st.session_state["reference_audio_language_filter"] = "all"
        if not reference_samples:
            st.info(
                "No reference audio found yet. Download the Kaggle dataset into the folder shown in the sidebar, "
                "then each language folder will appear here as a playable reference library."
            )
            st.caption(
                "The Kaggle dataset is useful as a language and pronunciation reference library. "
                "It is not used as a generation source."
            )
        else:
            selected_reference_language = st.session_state["reference_audio_language_filter"]
            reference_query = st.text_input(
                "Search reference clips",
                value="",
                placeholder="Search by filename or clip label",
                key="reference_audio_search_query",
            )
            filtered_reference_samples = [
                sample
                for sample in reference_samples
                if selected_reference_language == "all" or sample.language == selected_reference_language
            ]
            if reference_query.strip():
                query = reference_query.strip().lower()
                filtered_reference_samples = [
                    sample
                    for sample in filtered_reference_samples
                    if query in Path(sample.path).name.lower()
                    or query in sample.source_label.lower()
                    or query in sample.collection.lower()
                ]
            st.caption(
                f"Found {len(reference_samples)} curated reference clips across {len({sample.collection for sample in reference_samples})} collection(s). "
                f"Showing {len(filtered_reference_samples)} clip(s) for {reference_language_map.get(selected_reference_language, selected_reference_language)}."
            )
            if filtered_reference_samples:
                sample_lookup = {
                    f"{Path(sample.path).name} · {sample.source_label} · {sample.language}": sample
                    for sample in filtered_reference_samples
                }
                selected_sample_label = st.session_state.get("reference_audio_selected_clip", "")
                if selected_sample_label not in sample_lookup:
                    selected_sample_label = next(iter(sample_lookup))
                selected_reference_sample_label = st.selectbox(
                    "Pick a reference clip",
                    options=list(sample_lookup.keys()),
                    index=list(sample_lookup.keys()).index(selected_sample_label),
                    key="reference_audio_selected_clip",
                )
                selected_reference_sample = sample_lookup[selected_reference_sample_label]
                st.session_state["reference_audio_preview_path"] = selected_reference_sample.path
                st.markdown(
                    f"""
                    <div class="metric-box">
                      <div class="metric-label">Selected reference clip</div>
                      <div class="metric-value">{escape(Path(selected_reference_sample.path).name)}</div>
                      <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.45;">Collection: {escape(selected_reference_sample.collection)} · Language: {escape(selected_reference_sample.language)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.audio(selected_reference_sample.path)
                st.caption(selected_reference_sample.path)
                preview_grid = st.columns(2)
                for index, sample in enumerate(filtered_reference_samples[:6]):
                    column = preview_grid[index % 2]
                    with column:
                        st.markdown(
                            f"""
                            <div class="metric-box">
                              <div class="metric-label">{escape(sample.language)}</div>
                              <div class="metric-value">{escape(sample.source_label)}</div>
                              <div style="margin-top:6px;color:#94a3b8;font-size:13px;line-height:1.45;">{escape(Path(sample.path).name)}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                if len(filtered_reference_samples) > 6:
                    st.caption("Showing the first 6 matching clips as a quick preview; use search to narrow further.")
            else:
                st.info("No reference clips match the selected filters.")

        overview = selected_overview
        st.markdown(
            f"""
            <div class="status-strip">
              {status_pill("Files", str(overview["file_count"]))}
              {status_pill("Dashboard", "ready" if overview["dashboard_exists"] else "missing")}
              {status_pill("Audio", "ready" if overview["audio_exists"] else "missing")}
              {status_pill("Voice", "ready" if overview["voice_exists"] else "missing")}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with tab_files:
        st.subheader("Artifacts")
        day_root = ui_settings.output_dir / "daily" / inspect_date
        if day_root.exists():
            file_query = st.text_input("Search files", value="", placeholder="Type part of a filename or path")
            file_type = st.selectbox(
                "File type",
                options=["all", "html", "json", "png", "svg", "mp3", "wav", "txt"],
                index=0,
            )
            all_files = sorted(
                [path for path in day_root.rglob("*") if path.is_file()],
                key=lambda path: path.as_posix(),
            )
            if file_query:
                query = file_query.strip().lower()
                all_files = [
                    path for path in all_files
                    if query in path.name.lower() or query in path.as_posix().lower()
                ]
            if file_type != "all":
                all_files = [path for path in all_files if path.suffix.lower().lstrip(".") == file_type]
            if show_json:
                st.code("\n".join(str(path) for path in all_files), language="text")
            else:
                for path in all_files:
                    st.markdown(f"- `{path.relative_to(day_root)}`")
            st.markdown(
                f"""
                <div class="status-strip">
                  {status_pill("Files", str(selected_overview["file_count"]))}
                  {status_pill("HTML", str(selected_overview["suffix_counts"].get(".html", 0)))}
                  {status_pill("JSON", str(selected_overview["suffix_counts"].get(".json", 0)))}
                  {status_pill("Images", str(sum(
                      count for suffix, count in selected_overview["suffix_counts"].items()
                      if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
                  )))}
                </div>
                """,
                unsafe_allow_html=True,
            )
            if file_query or file_type != "all":
                st.caption(f"Filtered results: {len(all_files)}")
        else:
            st.info("No daily artifacts found yet for this day.")

    save_studio_state(
        ui_output_dir,
        {
            "voice_preset_choice": str(st.session_state["voice_preset_choice"]),
            "voice_provider": "edge",
            "voice_name": str(st.session_state["voice_name_choice"]),
            "voice_preview_text": str(st.session_state["voice_preview_text"]),
            "voice_preview_path": str(st.session_state["voice_preview_path"]),
            "voice_library_language_filter": str(st.session_state["voice_library_language_filter"]),
            "voice_gender_filter": str(st.session_state["voice_gender_filter"]),
            "image_provider": str(st.session_state["image_provider_choice"]),
            "image_topic": str(st.session_state["image_topic"]),
            "image_subject": str(st.session_state["image_subject"]),
            "image_prompt": str(st.session_state["image_prompt"]),
            "music_mood": str(st.session_state["music_mood"]),
            "music_duration_seconds": str(st.session_state["music_duration_seconds"]),
            "reference_audio_root": str(st.session_state["reference_audio_root"]),
            "reference_audio_default_language": str(st.session_state["reference_audio_default_language"]),
            "reference_audio_language_filter": str(st.session_state["reference_audio_language_filter"]),
            "reference_audio_selected_clip": str(st.session_state["reference_audio_selected_clip"]),
            "reference_audio_preview_path": str(st.session_state["reference_audio_preview_path"]),
            "reference_audio_bank_size": str(st.session_state["reference_audio_bank_size"]),
        },
    )


def main() -> None:
    _apply_streamlit_secrets()
    settings = Settings.from_environment(PROJECT_ROOT)
    st.set_page_config(page_title="Content Pipeline Studio", page_icon="🎬", layout="wide")
    render_frontdoor(settings)


if __name__ == "__main__":
    main()
