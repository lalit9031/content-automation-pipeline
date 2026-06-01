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
from content_pipeline.bots.image import ImageVariant, gemini_image_package_plan, image_provider
from content_pipeline.bots.prompt import build_cinematic_image_prompt
from content_pipeline.bots.prompt import build_image_style_pack
from content_pipeline.bots.prompt import sanitize_image_prompt_text
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
        "IMAGE_REQUEST_DELAY_SECONDS",
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


def _svg_preview_text(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff").lstrip()
    except OSError:
        return None
    if raw.startswith("<svg") or raw.startswith("<?xml") and "<svg" in raw[:256]:
        return raw
    return None


def render_image_preview(path: Path) -> None:
    svg_text = _svg_preview_text(path) if path.exists() else None
    if path.suffix.lower() == ".svg" or svg_text is not None:
        components.html(svg_text or path.read_text(encoding="utf-8"), height=720, scrolling=False)
        return

    if not path.exists():
        st.warning("Image preview is not available yet.")
        return

    if path.stat().st_size < 1024:
        st.error(
            "The image preview file is too small to be a valid image. The generated payload may be an error message."
        )
        try:
            path.unlink()
        except OSError:
            pass
        return

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        st.image(str(path), use_container_width=True)
        return

    try:
        with Image.open(path) as image:
            image.verify()
        st.image(str(path), use_container_width=True)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        st.error(
            "The image preview could not be decoded as an image. The generated payload may be a text error or corrupted file."
        )
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                preview = handle.read(240).strip()
            if preview:
                st.caption(f"Raw preview: {preview}")
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass


def image_preview_status(path: Path | None) -> tuple[str, str]:
    if path is None:
        return "missing", "No preview path set yet."
    if not path.exists():
        return "missing", f"No preview file found at {path.name}."
    if _svg_preview_text(path) is not None:
        return "ready", f"SVG preview stored at {path.name}."
    if path.stat().st_size < 1024:
        return "broken", f"{path.name} is too small to be a valid image."
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return "ready", f"Preview stored at {path.name}."
    try:
        with Image.open(path) as image:
            image.verify()
        return "ready", f"Preview stored at {path.name}."
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return "broken", f"{path.name} could not be decoded as an image."


def image_preview_source_status(path: Path | None) -> tuple[str, str]:
    if path is None:
        return "missing", "No preview file selected yet."
    if not path.exists():
        return "missing", f"No preview file found at {path.name}."
    svg_text = _svg_preview_text(path)
    if svg_text is not None:
        if "Local renderer baseline" in svg_text:
            return "mock fallback", "This preview came from the local mock renderer, not a live image API."
        return "svg preview", "This preview is SVG markup rendered directly in the browser."
    return "binary preview", "This preview is a binary image file."


def image_backend_status(settings: Settings, selected_provider: str) -> tuple[str, str]:
    provider = (selected_provider or "").strip().lower() or "unknown"
    if provider == "gemini" and settings.gcp_project_id:
        return (
            "imagen active",
            f"Gemini selection is routed to Imagen generate_images on project {settings.gcp_project_id}.",
        )
    if provider != "gemini":
        return provider, f"{provider} selected for this preview."
    plan = gemini_image_package_plan(settings, packages_requested=1)
    recommended_provider = str(plan.get("recommended_provider") or settings.image_fallback_provider or "imagen")
    if recommended_provider != "gemini":
        return "fallback active", f"Gemini is limited right now. Using {recommended_provider} for a single image preview."
    if bool(plan.get("daily_limit_reached")):
        return "gemini limited", "Gemini daily budget is exhausted, but the preview path will stay responsive."
    if bool(plan.get("stop_before_failure")):
        return "fallback ready", "Gemini is close to a limit. The fallback path is ready if needed."
    return "gemini ready", "Gemini can handle one image preview now."


def image_prompt_safety_status(prompt: str) -> tuple[str, str]:
    sanitized_prompt = sanitize_image_prompt_text(prompt)
    if sanitized_prompt != prompt:
        return "safe prompt", "Brand-heavy terms were softened before the image request."
    return "safe prompt", "Prompt is ready for a single image preview."


def apply_voice_preset_by_key(preset_key: str) -> None:
    preset_lookup = {preset.key: preset for preset in voice_preview_presets()}
    preset = preset_lookup.get(preset_key)
    if not preset:
        return
    st.session_state["voice_preset_choice"] = preset.key
    st.session_state["voice_name_choice"] = preset.voice
    st.session_state["voice_preview_text"] = preset.sample_text


def queue_voice_preset_by_key(preset_key: str) -> None:
    preset_lookup = {preset.key: preset for preset in voice_preview_presets()}
    preset = preset_lookup.get(preset_key)
    if not preset:
        return
    st.session_state["voice_preset_pending_key"] = preset.key


def apply_pending_voice_preset() -> None:
    pending_key = st.session_state.pop("voice_preset_pending_key", "")
    if pending_key:
        apply_voice_preset_by_key(pending_key)


def apply_selected_voice_preset() -> None:
    apply_voice_preset_by_key(str(st.session_state.get("voice_preset_choice", "")))


def _voice_preview_fallback_voice(gender: str, language: str = "en-IN") -> str:
    gender = (gender or "all").strip().lower()
    language = (language or "").strip().lower()
    if gender == "male":
        if language.startswith("hi"):
            return "hi-IN-MadhurNeural"
        return "en-IN-PrabhatNeural"
    if gender == "female":
        if language.startswith("hi"):
            return "hi-IN-SwaraNeural"
        return "en-IN-NeerjaNeural"
    return "en-IN-PrabhatNeural"


def _voice_preview_fallback_candidates(gender: str, language: str = "en-IN") -> list[str]:
    language = (language or "").strip().lower()
    gender = (gender or "all").strip().lower()
    candidates: list[str] = []
    if language.startswith("hi"):
        if gender == "male":
            candidates.extend(["hi-IN-MadhurNeural", "hi-IN-AaravNeural", "hi-IN-KunalNeural", "hi-IN-RehaanNeural"])
        elif gender == "female":
            candidates.extend(["hi-IN-SwaraNeural", "hi-IN-AnanyaNeural", "hi-IN-KavyaNeural"])
        else:
            candidates.extend(
                [
                    "hi-IN-MadhurNeural",
                    "hi-IN-AaravNeural",
                    "hi-IN-KunalNeural",
                    "hi-IN-RehaanNeural",
                    "hi-IN-SwaraNeural",
                ]
            )
    if gender == "male":
        candidates.extend(["en-IN-PrabhatNeural", "en-IN-KunalNeural"])
    elif gender == "female":
        candidates.extend(["en-IN-NeerjaNeural", "hi-IN-SwaraNeural"])
    else:
        candidates.extend(["en-IN-PrabhatNeural", "en-IN-NeerjaNeural"])
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _generate_voice_preview_with_fallback(
    *,
    text: str,
    preview_path: Path,
    voice: str,
    gender_hint: str = "all",
    language_hint: str = "en-IN",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Path:
    attempts = [voice, *_voice_preview_fallback_candidates(gender_hint, language_hint)]
    seen: set[str] = set()
    last_error: Exception | None = None
    for index, candidate in enumerate(attempts):
        if candidate in seen:
            continue
        seen.add(candidate)
        candidate_path = preview_path if index == 0 else preview_path.with_name(
            f"{preview_path.stem}_{candidate}{preview_path.suffix}"
        )
        try:
            output = generate_voice_preview(
                text,
                candidate_path,
                provider="edge",
                voice=candidate,
                rate=rate,
                pitch=pitch,
            )
            if output.exists() and output.stat().st_size > 0:
                if candidate != voice:
                    st.warning(
                        f"Voice preview could not run with the selected voice, so the app fell back to {candidate}."
                    )
                return output
            raise RuntimeError("No audio was received.")
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("Voice preview could not be generated.")


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


def copy_prompt_button(prompt: str, *, button_id: str) -> str:
    escaped_prompt = json.dumps(prompt)
    return f"""
    <button
      id="{escape(button_id)}"
      style="
        width: 100%;
        padding: 10px 14px;
        border-radius: 14px;
        border: 1px solid #334155;
        background: linear-gradient(180deg, rgba(15,23,42,.95), rgba(15,23,42,.78));
        color: #e2e8f0;
        font-weight: 800;
        cursor: pointer;
      "
      onclick='navigator.clipboard.writeText({escaped_prompt}).then(() => {{
        const el = document.getElementById("{escape(button_id)}");
        if (el) {{
          const prev = el.textContent;
          el.textContent = "Copied prompt";
          setTimeout(() => {{ el.textContent = prev || "Copy prompt"; }}, 1200);
        }}
      }}); return false;'
    >Copy prompt</button>
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

    # Track active page inside session state
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "Home"

    # Silent state sync setup
    if "output_dir_pref" not in st.session_state:
        st.session_state["output_dir_pref"] = str(settings.output_dir)

    ui_output_dir = resolve_output_dir(st.session_state["output_dir_pref"])
    saved_studio_state = load_studio_state(ui_output_dir)

    # Initialize all default state values silently (removing sidebar components)
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
        st.session_state["voice_preview_path"] = ""

    st.session_state.setdefault("voice_preset_choice", "english_explainer")
    st.session_state.setdefault("prev_voice_library_language_filter", "all")
    st.session_state.setdefault("prev_voice_gender_filter", "all")
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
    st.session_state.setdefault("scene_index", 0)
    st.session_state.setdefault("audio_tab_choice", "🎙️ Voice Over")

    # Day selection states
    st.session_state.setdefault("run_day", default_day)
    st.session_state.setdefault("inspect_day", default_day)

    # Load scene data silently
    json_path = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/scratch/fresher_scenes_data.json")
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                scenes_data = json.load(f)
        except Exception:
            scenes_data = []
    else:
        scenes_data = []

    if not scenes_data:
        scenes_data = [
            {
                "title": "Welcome scene",
                "narration": st.session_state["voice_preview_text"],
                "on_screen_text": "Content Studio"
            }
        ]

    run_day = st.session_state["run_day"]
    inspect_day = st.session_state["inspect_day"]
    run_date = run_day.isoformat()
    inspect_date = inspect_day.isoformat()

    ui_settings = replace(settings, output_dir=ui_output_dir)
    ui_settings = replace(
        ui_settings,
        voice_provider="edge",
        indian_tts_voice=st.session_state["voice_name_choice"],
    )

    selected_day_dir = ui_settings.output_dir / "daily" / inspect_date
    selected_overview = day_overview(selected_day_dir)

    # NATIVE SELECT A VOICE MODAL POPUP
    @st.dialog("Select a voice", width="large")
    def select_voice_dialog():
        st.markdown("### 🎙️ Premium Neural Voice Library")
        st.write("Browse and preview our collection of high-quality neural voices. Click **Play** to listen.")

        # Filter controls inside the modal to make it even more powerful!
        library_language = st.selectbox(
            "Filter by Language",
            options=["all", "en-US", "en-IN", "hi-IN"],
            format_func=lambda l: {"all": "All Languages", "en-US": "English (US)", "en-IN": "Hinglish (IN)", "hi-IN": "Hindi (IN)"}.get(l, l),
            key="modal_lang_filter"
        )

        presets = voice_preview_presets()
        if library_language != "all":
            presets = [p for p in presets if p.language == library_language]

        # Grid of voices
        cols = st.columns(3)
        for idx, preset in enumerate(presets):
            col = cols[idx % 3]
            with col:
                st.markdown(f"""
                <div class="preset-modal-card">
                    <div style="font-weight: 800; color: #f8fafc; font-size: 14px;">{preset.label}</div>
                    <div style="color: #94a3b8; font-size: 12px; margin-top: 4px; min-height: 42px; line-height: 1.35;">{preset.description}</div>
                    <div style="display: flex; gap: 8px; margin-top: 8px; font-size: 11px; font-weight: bold; text-transform: uppercase;">
                        <span style="color: #38bdf8;">{preset.language}</span>
                        <span style="color: #a855f7;">{preset.gender}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                btn_cols = st.columns(2)
                with btn_cols[0]:
                    if st.button("▶️ Play", key=f"modal_play_{preset.key}", use_container_width=True):
                        st.session_state["modal_playing_preset"] = preset.key
                        st.rerun()
                with btn_cols[1]:
                    if st.button("✅ Select", key=f"modal_select_{preset.key}", use_container_width=True):
                        st.session_state["voice_preset_choice"] = preset.key
                        st.session_state["voice_name_choice"] = preset.voice
                        st.session_state["voice_preview_text"] = preset.sample_text
                        
                        # Sync script editor text area & DB
                        active_scene_idx = st.session_state["scene_index"]
                        st.session_state[f"dialogue_editor_{active_scene_idx}"] = preset.sample_text
                        scenes_data[active_scene_idx]["narration"] = preset.sample_text
                        try:
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass

                        if preset.gender != "all":
                            st.session_state["voice_gender_filter"] = preset.gender
                        if preset.language != "all":
                            st.session_state["voice_library_language_filter"] = preset.language
                        st.session_state.pop("modal_playing_preset", None)
                        st.rerun()

        playing_preset = st.session_state.get("modal_playing_preset")
        if playing_preset:
            active_p = next((p for p in voice_preview_presets() if p.key == playing_preset), None)
            if active_p:
                st.markdown("---")
                st.markdown(f"🔊 Playing Audio Sample for: **{active_p.label}**")

                manual_map = {
                    "toddler_girl": "scratch/presets_verification/toddler_girl_manual.mp3",
                    "toddler_boy": "scratch/presets_verification/toddler_boy_manual.mp3",
                    "story_female": "scratch/presets_verification/story_female_manual.mp3",
                    "story_male": "scratch/presets_verification/story_male_manual.mp3",
                    "indian_english_corporate_male": "scratch/presets_verification/corporate_manual.mp3"
                }

                sample_path = manual_map.get(active_p.key)
                if sample_path and os.path.exists(sample_path):
                    st.audio(sample_path, autoplay=True)
                else:
                    # Dynamically generate edge-tts preview
                    try:
                        preview_dir = ui_output_dir / ".runtime" / "voice_previews" / "library"
                        preview_dir.mkdir(parents=True, exist_ok=True)
                        preview_path = preview_dir / f"{active_p.key}.mp3"
                        if not preview_path.exists():
                            _generate_voice_preview_with_fallback(
                                text=active_p.sample_text[:85],
                                preview_path=preview_path,
                                voice=active_p.voice,
                                gender_hint=active_p.gender,
                                language_hint=active_p.language,
                                rate=active_p.rate,
                                pitch=active_p.pitch,
                            )
                        st.audio(str(preview_path), autoplay=True)
                    except Exception as e:
                        st.error(f"Error previewing voice: {e}")

    # Inject premium styles
    st.markdown(
        """
        <style>
          :root {
            --bg: #020617;
            --panel: rgba(15, 23, 42, 0.7);
            --panel-strong: rgba(15, 23, 42, 0.95);
            --line: rgba(51, 65, 85, 0.5);
            --text: #f8fafc;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --accent-2: #a855f7;
            --accent-3: #f59e0b;
          }
          .stApp {
            background:
              radial-gradient(circle at 10% 20%, rgba(56,189,248,0.15), transparent 35%),
              radial-gradient(circle at 90% 80%, rgba(168,85,247,0.15), transparent 35%),
              linear-gradient(180deg, #020617 0%, #0f172a 100%);
          }
          /* Custom Top Navigation Container */
          .top-nav {
            display: flex;
            justify-content: center;
            align-items: center;
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(20px);
            border-radius: 20px;
            padding: 10px 30px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
          }
          /* Premium Canvas Box */
          .canvas-box {
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 15px 35px rgba(2, 6, 23, 0.4);
          }
          .canvas-title {
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: .12em;
            color: #38bdf8;
            font-weight: 800;
            margin-bottom: 16px;
            border-bottom: 1px solid rgba(56, 189, 248, 0.15);
            padding-bottom: 8px;
          }
          /* Voiceover & Story Card */
          .voiceover-card {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.7));
            border: 1px solid rgba(168, 85, 247, 0.3);
            border-radius: 20px;
            padding: 20px;
            margin-top: 20px;
            box-shadow: 0 12px 25px rgba(0, 0, 0, 0.3);
          }
          /* Grid Preset Cards */
          .preset-modal-card {
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 12px;
            transition: all 0.3s ease;
          }
          .preset-modal-card:hover {
            border-color: #38bdf8;
            box-shadow: 0 8px 20px rgba(56, 189, 248, 0.15);
            transform: translateY(-2px);
          }
          /* Standard Cards */
          .metric-box, .panel-box {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            padding: 16px;
          }
          .action-card {
            padding: 18px;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(15,23,42,.94), rgba(15,23,42,.78));
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 12px 30px rgba(2, 6, 23, 0.25);
          }
          .hero {
            padding: 28px;
            border-radius: 24px;
            background: linear-gradient(135deg, rgba(15,23,42,.94), rgba(2,6,23,.98));
            border: 1px solid rgba(255, 255, 255, 0.08);
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
            border: 1px solid rgba(255, 255, 255, 0.08);
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
          .file-chip {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            padding: 16px;
          }
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
          /* Custom active state highlight for Streamlit native primary buttons in nav row */
          button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #a855f7, #38bdf8) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4) !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Render horizontal top bar page navigation inside columns
    nav_cols = st.columns([1, 1, 1, 1, 1])
    pages = ["Home", "Audio", "Image", "Video", "Content"]
    icons = ["🏠 Home", "🎵 Audio Studio", "🖼️ Image Studio", "🎬 Video Studio", "⚙️ Content Pipeline"]

    for i, (page, icon) in enumerate(zip(pages, icons)):
        with nav_cols[i]:
            is_active = st.session_state["active_page"] == page
            if st.button(icon, key=f"nav_{page}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state["active_page"] = page
                st.rerun()

    # RENDER SELECTED PAGE
    if st.session_state["active_page"] == "Home":
        st.markdown(
            """
            <div style="text-align:center; padding: 40px 20px;">
                <h1 style="font-size: 42px; margin-bottom: 12px; background: linear-gradient(135deg, #a855f7, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800;">
                    Welcome to Content Pipeline Studio
                </h1>
                <p style="font-size: 16px; color: #94a3b8; max-width: 650px; margin: 0 auto 30px;">
                    Orchestrate your visual stories with unified neural narration, 3D Pixar character illustrations, 
                    and high-contrast subtitled video compilation in a clean, state-of-the-art visual laboratory.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Overview cards
        st.markdown("### 📊 Studio Orchestration Overview")
        metric_cols = st.columns(4)
        with metric_cols[0]:
            render_overview_card(
                "Neural TTS Presets",
                f"{len(voice_preview_presets())} Active Profiles",
                "Authoritative baritones, friendly storytellers, and toddler vocal modifiers."
            )
        with metric_cols[1]:
            render_overview_card(
                "Image Synthesis",
                "FLUX / Gemini",
                "Pixel-perfect 16:9 widescreen 3D Pixar claymation scene synthesis."
            )
        with metric_cols[2]:
            render_overview_card(
                "Explainer Timeline",
                f"{len(scenes_data)} Story Scenes",
                "Complete storyboard mapping from fresher AI survival guide compilation."
            )
        with metric_cols[3]:
            render_overview_card(
                "Pipeline Health",
                "100% Core Passing",
                "All 81 internal automation and integration tests verified successfully."
            )

        # Visual Quick Nav guides
        st.markdown("### ⚡ Quick Navigation Guides")
        action_cols = st.columns(3)
        with action_cols[0]:
            st.markdown(
                """
                <div class="action-card">
                  <h3>🎙️ Voiceover Studio</h3>
                  <p>Design beautiful neural pacing, preview accents, and tweak SSML prosody directly under the preview canvas.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open Audio Studio", key="quick_audio", use_container_width=True):
                st.session_state["active_page"] = "Audio"
                st.rerun()
        with action_cols[1]:
            st.markdown(
                """
                <div class="action-card">
                  <h3>🎬 Video Compiler</h3>
                  <p>Browse the compiled 5-minute episode storyboards, captions, and execute high-speed FFmpeg mergers.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open Video Studio", key="quick_video", use_container_width=True):
                st.session_state["active_page"] = "Video"
                st.rerun()
        with action_cols[2]:
            st.markdown(
                """
                <div class="action-card">
                  <h3>⚙️ Pipeline Console</h3>
                  <p>Trigger technical background builds, analyze daily metrics logs, and browse generated raw artifacts files.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open Pipeline Panel", key="quick_content", use_container_width=True):
                st.session_state["active_page"] = "Content"
                st.rerun()

    elif st.session_state["active_page"] == "Audio":
        # 1. Instantly pull latest edited narration from widget state if it exists
        active_scene_idx = st.session_state.get("scene_index", 0)
        if active_scene_idx >= len(scenes_data):
            active_scene_idx = 0
            st.session_state["scene_index"] = 0

        editor_key = f"dialogue_editor_{active_scene_idx}"
        if editor_key in st.session_state:
            scenes_data[active_scene_idx]["narration"] = st.session_state[editor_key]
        
        # 2. Sync voice_preview_text to ensure phonetic pronunciation card and previews match active text
        st.session_state["voice_preview_text"] = scenes_data[active_scene_idx]["narration"]

        # Columns layout: Left sub-nav (1.5), Center canvas (5.5), Right panel (3.5)
        left_col, center_col, right_col = st.columns([1.5, 5, 3.5])

        with left_col:
            st.markdown("### Audio Subsections")
            audio_tab_choice = st.radio(
                "Choose Section",
                options=["🎙️ Voice Over", "🎵 Music Studio"],
                label_visibility="collapsed",
                key="audio_tab_choice"
            )
            st.caption("Switch between configuring vocal dialogue tracks or environmental backing audio tracks.")

        with center_col:
            # Resolving preset map
            presets = voice_preview_presets()
            preset_map = {preset.key: preset for preset in presets}
            
            # Extract filters first for dynamic cascade
            library_language = st.session_state.get("voice_library_language_filter", "all")
            library_gender = st.session_state.get("voice_gender_filter", "all")

            # Detect filter changes to enforce selectbox synchronization
            prev_library_language = st.session_state.get("prev_voice_library_language_filter", "all")
            prev_library_gender = st.session_state.get("prev_voice_gender_filter", "all")
            filters_changed = (library_language != prev_library_language or library_gender != prev_library_gender)

            if filters_changed:
                st.session_state["prev_voice_library_language_filter"] = library_language
                st.session_state["prev_voice_gender_filter"] = library_gender

            # Apply dependent cascaded filtering to voice presets
            filtered_presets = filter_voice_preview_presets(
                presets,
                language=library_language,
                gender=library_gender
            )
            if not filtered_presets:
                filtered_presets = presets

            filtered_preset_keys = [p.key for p in filtered_presets]

            # Auto-align active preset choice if it falls out of the filtered scope or if filters changed
            active_preset_key = st.session_state["voice_preset_choice"]
            if active_preset_key not in filtered_preset_keys or filters_changed:
                if active_preset_key not in filtered_preset_keys:
                    active_preset_key = filtered_preset_keys[0]
                st.session_state["voice_preset_choice"] = active_preset_key
                st.session_state["voice_name_choice"] = preset_map[active_preset_key].voice
                st.session_state["voice_preview_text"] = preset_map[active_preset_key].sample_text
                
                # Sync script editor text area & DB
                st.session_state[f"dialogue_editor_{active_scene_idx}"] = preset_map[active_preset_key].sample_text
                scenes_data[active_scene_idx]["narration"] = preset_map[active_preset_key].sample_text
                try:
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                    
                st.rerun()

            active_preset = preset_map[active_preset_key]

            if audio_tab_choice == "🎙️ Voice Over":
                # Centered Large Preview Canvas Box
                st.markdown(f"""
                <div class="canvas-box">
                    <div class="canvas-title">🔊 Neural Dialogue Preview Canvas</div>
                    <div style="text-align:center; padding: 15px 0;">
                        <span style="font-size: 52px; color: #38bdf8;">🎙️</span>
                        <p style="margin-top: 10px; color: #f8fafc; font-weight: 800; font-size:18px; margin-bottom: 2px;">{active_preset.label}</p>
                        <p style="color: #94a3b8; font-size: 13px; margin-bottom: 0;">Base Voice Model: <code>{active_preset.voice}</code></p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Active preview player right under preview box
                voice_preview_path = st.session_state.get("voice_preview_path")
                if voice_preview_path and os.path.exists(voice_preview_path):
                    st.audio(voice_preview_path)
                    st.caption(f"Loaded preview path: `{Path(voice_preview_path).name}`")
                else:
                    st.info("No audio preview generated yet. Tweak parameters below and click 'Play Preview' on the right panel!")

                # Voice parameters underneath preview box (Cascaded: Gender -> Language -> Preset)
                st.markdown("#### 🛠️ Vocal Parameter Tweaks")
                param_cols = st.columns(3)

                with param_cols[0]:
                    # 1st Filter: Gender selection (Cascades down)
                    gender_options = voice_gender_options()
                    gender_map = {value: label for value, label in gender_options}
                    st.selectbox(
                        "Vocal Gender",
                        options=[value for value, _ in gender_options],
                        format_func=lambda value: gender_map.get(value, value),
                        key="voice_gender_filter"
                    )

                with param_cols[1]:
                    # 2nd Filter: Language selection (Cascades down)
                    language_options = voice_preview_language_options()
                    language_map = {value: label for value, label in language_options}
                    st.selectbox(
                        "Vocal Language",
                        options=[value for value, _ in language_options],
                        format_func=lambda value: language_map.get(value, value),
                        key="voice_library_language_filter"
                    )

                with param_cols[2]:
                    # 3rd Filter: Preset selection (Dynamically reduced based on Gender and Language)
                    selected_preset_key = st.selectbox(
                        "Narration Preset",
                        options=filtered_preset_keys,
                        index=filtered_preset_keys.index(active_preset_key),
                        format_func=lambda k: preset_map[k].label,
                    )
                    if selected_preset_key != active_preset_key:
                        st.session_state["voice_preset_choice"] = selected_preset_key
                        st.session_state["voice_name_choice"] = preset_map[selected_preset_key].voice
                        st.session_state["voice_preview_text"] = preset_map[selected_preset_key].sample_text
                        
                        # Sync script editor text area & DB
                        active_scene_idx = st.session_state["scene_index"]
                        st.session_state[f"dialogue_editor_{active_scene_idx}"] = preset_map[selected_preset_key].sample_text
                        scenes_data[active_scene_idx]["narration"] = preset_map[selected_preset_key].sample_text
                        try:
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                            
                        st.rerun()

                st.markdown("##### SSML Prosody Adjustments")
                tweak_cols = st.columns(2)
                with tweak_cols[0]:
                    # Pitch adjustment
                    active_pitch_options = ["-10Hz", "-8Hz", "-6Hz", "-4Hz", "-2Hz", "+0Hz", "+2Hz", "+4Hz", "+6Hz", "+8Hz", "+10Hz"]
                    preset_pitch = active_preset.pitch or "+0Hz"
                    if preset_pitch not in active_pitch_options:
                        active_pitch_options.append(preset_pitch)
                    st.select_slider(
                        "Vocal Pitch Tweak",
                        options=sorted(active_pitch_options),
                        value=preset_pitch,
                        key="voice_pitch_tweak_slider"
                    )
                with tweak_cols[1]:
                    # Rate adjustment
                    active_rate_options = ["-20%", "-15%", "-10%", "-5%", "+0%", "+5%", "+10%", "+15%", "+20%"]
                    preset_rate = active_preset.rate or "+0%"
                    if preset_rate not in active_rate_options:
                        active_rate_options.append(preset_rate)
                    st.select_slider(
                        "Speech Pacing (Rate) Tweak",
                        options=sorted(active_rate_options),
                        value=preset_rate,
                        key="voice_rate_tweak_slider"
                    )

                # Centered dynamic controls below the sliders
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                apply_cols = st.columns([1.5, 1.5, 7])
                with apply_cols[0]:
                    if st.button("✅ Apply", key="btn_apply_prosody", use_container_width=True):
                        active_scene_idx = st.session_state["scene_index"]
                        # Synchronize the script editor text area and active scene narration in memory & DB!
                        st.session_state[f"dialogue_editor_{active_scene_idx}"] = active_preset.sample_text
                        scenes_data[active_scene_idx]["narration"] = active_preset.sample_text
                        st.session_state["voice_preview_text"] = active_preset.sample_text
                        try:
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass

                        with st.spinner("Applying adjustments..."):
                            try:
                                preview_root = ui_output_dir / ".runtime" / "voice_previews"
                                preview_root.mkdir(parents=True, exist_ok=True)
                                preview_file = preview_root / f"scene_{active_scene_idx + 1}_preview.mp3"

                                generate_voice_preview(
                                    text=active_preset.sample_text,
                                    output_path=preview_file,
                                    provider="edge",
                                    voice=active_preset.voice,
                                    rate=st.session_state.get("voice_rate_tweak_slider", active_preset.rate),
                                    pitch=st.session_state.get("voice_pitch_tweak_slider", active_preset.pitch)
                                )
                                st.session_state["voice_preview_path"] = str(preview_file)
                                st.success("Speech pacing & pitch adjustments applied!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Vocal synthesis error: {e}")
                with apply_cols[1]:
                    if st.button("🔄 Reset", key="btn_reset_prosody", use_container_width=True):
                        active_scene_idx = st.session_state["scene_index"]
                        st.session_state["voice_pitch_tweak_slider"] = active_preset.pitch or "+0Hz"
                        st.session_state["voice_rate_tweak_slider"] = active_preset.rate or "+0%"
                        
                        # Reset script editor text area and active scene narration in memory & DB!
                        st.session_state[f"dialogue_editor_{active_scene_idx}"] = active_preset.sample_text
                        scenes_data[active_scene_idx]["narration"] = active_preset.sample_text
                        st.session_state["voice_preview_text"] = active_preset.sample_text
                        try:
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass

                        with st.spinner("Resetting to defaults..."):
                            try:
                                preview_root = ui_output_dir / ".runtime" / "voice_previews"
                                preview_root.mkdir(parents=True, exist_ok=True)
                                preview_file = preview_root / f"scene_{active_scene_idx + 1}_preview.mp3"

                                generate_voice_preview(
                                    text=active_preset.sample_text,
                                    output_path=preview_file,
                                    provider="edge",
                                    voice=active_preset.voice,
                                    rate=active_preset.rate or "+0%",
                                    pitch=active_preset.pitch or "+0Hz"
                                )
                                st.session_state["voice_preview_path"] = str(preview_file)
                                st.success("Prosody adjustments reset to preset defaults!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error resetting preview: {e}")

                # Dynamic normalized preview string
                st.markdown("##### 📜 Dialogue Phonetic Pronunciation")
                normalized_preview = normalize_voice_text(st.session_state["voice_preview_text"])
                st.text_area("Normalized Text (phonetic replacements for neural engines)", value=normalized_preview, height=90, disabled=True)

                # Reference Audio Bank
                with st.expander("📁 Kaggle Indian Pronunciation Reference Dataset", expanded=False):
                    reference_audio_root = resolve_project_path(st.session_state["reference_audio_root"])
                    reference_samples = scan_reference_audio_library(
                        reference_audio_root,
                        default_language=st.session_state["reference_audio_default_language"],
                    )
                    reference_samples = curate_reference_audio_bank(
                        reference_samples,
                        limit=int(st.session_state["reference_audio_bank_size"]),
                    )
                    if not reference_samples:
                        st.info("No pronunciation samples found in Kaggle audio directories.")
                    else:
                        ref_cols = st.columns(2)
                        with ref_cols[0]:
                            st.text_input("Dataset folder", key="reference_audio_root")
                        with ref_cols[1]:
                            st.selectbox("Language Filter", options=[value for value, _ in reference_audio_language_options()], key="reference_audio_language_filter")

                        sample_labels = {f"{Path(sample.path).name} · {sample.language}": sample for sample in reference_samples}
                        chosen_ref_label = st.selectbox("Select Pronunciation Sample File", options=list(sample_labels.keys()))
                        chosen_sample = sample_labels[chosen_ref_label]
                        st.audio(chosen_sample.path)

            elif audio_tab_choice == "🎵 Music Studio":
                st.markdown(f"""
                <div class="canvas-box" style="border-color: rgba(168, 85, 247, 0.3);">
                    <div class="canvas-title" style="color: #a855f7; border-bottom-color: rgba(168, 85, 247, 0.15);">🎵 Wavelength Music Preview Canvas</div>
                    <div style="text-align:center; padding: 24px 0;">
                        <span style="font-size: 52px; color: #a855f7;">🎸</span>
                        <p style="margin-top: 10px; color: #f8fafc; font-weight: 800; font-size:18px; margin-bottom: 2px;">Active Atmosphere: {st.session_state["music_mood"].title()}</p>
                        <p style="color: #94a3b8; font-size: 13px; margin-bottom: 0;">Preview Duration: {st.session_state["music_duration_seconds"]} seconds</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                music_preview_path = st.session_state.get("music_preview_path")
                if music_preview_path and os.path.exists(music_preview_path):
                    st.audio(music_preview_path)
                    st.caption(f"Loaded music preview: `{Path(music_preview_path).name}`")
                else:
                    st.info("No backing music track generated yet. Tweak settings below to render preview WAV file!")

                # Parameters under preview box
                st.markdown("#### ⚙️ Music Generation Settings")
                music_param_cols = st.columns(2)
                with music_param_cols[0]:
                    st.selectbox("Atmosphere Mood", options=("cinematic", "focus", "warm", "uplift", "ambient"), key="music_mood")
                with music_param_cols[1]:
                    st.slider("Atmosphere Length (seconds)", 4, 15, key="music_duration_seconds")

                if st.button("✨ Render Atmosphere Wave WAV Preview", type="primary", use_container_width=True):
                    with st.spinner("Synthesizing ambient harmonies..."):
                        try:
                            preview_path = ui_settings.output_dir / ".runtime" / "music_previews" / f"{_slugify(st.session_state['music_mood'])}_{st.session_state['music_duration_seconds']}s.wav"
                            generate_music_preview(
                                preview_path,
                                st.session_state["music_mood"],
                                duration_seconds=int(st.session_state["music_duration_seconds"])
                            )
                            st.session_state["music_preview_path"] = str(preview_path)
                            st.success("Atmosphere WAV file synthesized successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error rendering music: {e}")

        with right_col:
            # AI Voiceover controls panel
            st.markdown("### AI Voiceover controls")

            # Segmented scope
            scene_scope = st.radio("Narration Scope", options=["Current scene", "All scenes"], horizontal=True, key="scene_scope")

            if scene_scope == "Current scene":
                scene_index = st.session_state["scene_index"]
                if scene_index >= len(scenes_data):
                    scene_index = 0
                    st.session_state["scene_index"] = 0

                scene = scenes_data[scene_index]

                # Scene Pager Row
                pager_cols = st.columns([1, 2, 1])
                with pager_cols[0]:
                    if st.button("◀️ Prev", disabled=(scene_index == 0), key="btn_prev_scene", use_container_width=True):
                        st.session_state["scene_index"] = scene_index - 1
                        st.rerun()
                with pager_cols[1]:
                    st.markdown(f"<div style='text-align:center; font-weight:800; font-size:14px; margin-top:6px; color:#cbd5e1;'>Scene {scene_index + 1} of {len(scenes_data)}</div>", unsafe_allow_html=True)
                with pager_cols[2]:
                    if st.button("Next ▶️", disabled=(scene_index == len(scenes_data) - 1), key="btn_next_scene", use_container_width=True):
                        st.session_state["scene_index"] = scene_index + 1
                        st.rerun()

                # Narration Editor
                st.markdown(f"🎬 **Scene Context:** *{scene.get('title', 'Explainer Section')}*")
                narration_val = st.text_area("Scene Dialogue Track Script", value=scene["narration"], height=160, key=f"dialogue_editor_{scene_index}")
                scenes_data[scene_index]["narration"] = narration_val

            else:
                # All Scenes View
                st.markdown("📝 **All Storyboard Dialogue Blocks**")
                with st.container(height=240):
                    for idx, scene in enumerate(scenes_data):
                        st.markdown(f"**Scene {idx+1}: {scene.get('title', 'Explainer Section')}**")
                        st.caption(scene["narration"])
                        st.markdown("---")

            # Voiceover selection card
            st.markdown(f"""
            <div class="voiceover-card">
                <div style="font-size: 11px; text-transform: uppercase; color: #38bdf8; font-weight: 800; letter-spacing: 0.05em;">Voiceover Narrator Profile</div>
                <div style="font-size: 16px; font-weight: 800; color: white; margin-top:6px; margin-bottom: 2px;">{active_preset.label}</div>
                <div style="font-size: 13px; color: #cbd5e1; line-height: 1.4;">{active_preset.description}</div>
            </div>
            """, unsafe_allow_html=True)

            # Change / Play preview row
            voice_action_cols = st.columns(2)
            with voice_action_cols[0]:
                if st.button("🔄 Change Voice", use_container_width=True, key="btn_trigger_modal"):
                    select_voice_dialog()
            with voice_action_cols[1]:
                # Play Preview of current script text
                if st.button("▶️ Play Preview", use_container_width=True, key="btn_play_narration_preview"):
                    with st.spinner("Compiling neural speech..."):
                        try:
                            preview_root = ui_output_dir / ".runtime" / "voice_previews"
                            preview_root.mkdir(parents=True, exist_ok=True)
                            preview_file = preview_root / f"scene_{st.session_state['scene_index'] + 1}_preview.mp3"

                            # Generate speech
                            generate_voice_preview(
                                text=scenes_data[st.session_state["scene_index"]]["narration"],
                                output_path=preview_file,
                                provider="edge",
                                voice=active_preset.voice,
                                rate=st.session_state.get("voice_rate_tweak_slider", active_preset.rate),
                                pitch=st.session_state.get("voice_pitch_tweak_slider", active_preset.pitch)
                            )
                            st.session_state["voice_preview_path"] = str(preview_file)
                            st.success("Neural dialogue compiled successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Vocal synthesis error: {e}")

            # Update entire script button
            if st.button("💾 Save Script & Storyboard edits", type="primary", use_container_width=True, key="btn_save_script"):
                with st.spinner("Writing to database..."):
                    try:
                        # Write back edited scene data
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                        st.success("Script changes successfully synced across the pipeline!")
                    except Exception as e:
                        st.error(f"Error saving storyboard script: {e}")

    elif st.session_state["active_page"] == "Image":
        left_col, right_col = st.columns([6, 4])

        with left_col:
            # Center Preview Box
            st.markdown(f"""
            <div class="canvas-box">
                <div class="canvas-title">🖼️ Pixar-Style Image Synthesis Canvas</div>
            </div>
            """, unsafe_allow_html=True)

            image_preview_path = st.session_state.get("image_preview_path")
            if image_preview_path and os.path.exists(image_preview_path):
                render_image_preview(Path(image_preview_path))
                st.caption(f"Loaded generated canvas path: `{Path(image_preview_path).name}`")
            else:
                st.info("No visual canvas synthesized yet. Tweak subject descriptions under the screen and generate!")

            # Controls underneath canvas box
            st.markdown("#### 🎨 Prompt Engineering & synthesis")
            param_cols = st.columns(3)
            with param_cols[0]:
                st.selectbox(
                    "Image synthesis Provider",
                    options=("mock", "free-ai", "gemini", "openai"),
                    key="image_provider_choice"
                )
            with param_cols[1]:
                st.text_input("Explainer Topic", key="image_topic")
            with param_cols[2]:
                st.text_input("Scene Subject", key="image_subject")

            prompt_input = st.text_area("Engine-Injected Style Prompt", value=st.session_state.get("image_prompt", ""), height=120)
            st.session_state["image_prompt"] = prompt_input

            # Action Buttons under prompt text area
            act_cols = st.columns(2)
            with act_cols[0]:
                if st.button("🧙‍♂️ Build Cinematic style-pack Prompt", use_container_width=True, key="btn_build_prompt"):
                    st.session_state["image_prompt"] = build_cinematic_image_prompt(
                        st.session_state["image_topic"],
                        st.session_state["image_subject"]
                    )
                    st.rerun()
            with act_cols[1]:
                if st.button("✨ Synthesize Widescreen Canvas", type="primary", use_container_width=True, key="btn_gen_preview"):
                    with st.spinner("Synthesizing pristine illustration..."):
                        try:
                            image_settings = replace(settings, output_dir=ui_output_dir)
                            provider = image_provider(replace(image_settings, image_provider=st.session_state["image_provider_choice"]))
                            variant = ImageVariant("16:9", 2560, 1440, "image_preview")
                            preview_path = ui_output_dir / ".runtime" / "image_previews" / (
                                f"{_slugify(st.session_state['image_topic'])}_{_slugify(st.session_state['image_subject'])}_{st.session_state['image_provider_choice']}{provider.extension}"
                            )
                            preview_path.parent.mkdir(parents=True, exist_ok=True)
                            preview_path.write_bytes(provider.create(st.session_state["image_prompt"], variant))
                            st.session_state["image_preview_path"] = str(preview_path)
                            st.success(f"Image successfully rendered!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Image generation error: {e}")

        with right_col:
            st.markdown("### Visual Theme & metadata")
            image_style_pack = build_image_style_pack(
                st.session_state["image_topic"],
                subject=st.session_state["image_subject"]
            )
            st.json(image_style_pack.as_dict())

            st.markdown("#### Prompt Safety audit")
            safety_state, safety_msg = image_prompt_safety_status(st.session_state["image_prompt"])
            st.markdown(f"""
            <div class="metric-box">
                <div class="metric-label">Safety State</div>
                <div class="metric-value" style="font-size:16px;">{safety_state.upper()}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{safety_msg}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("#### Active Provider backend details")
            backend_state, backend_msg = image_backend_status(settings, st.session_state["image_provider_choice"])
            st.markdown(f"""
            <div class="metric-box">
                <div class="metric-label">Provider Pipeline</div>
                <div class="metric-value" style="font-size:16px;">{backend_state.upper()}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{backend_msg}</div>
            </div>
            """, unsafe_allow_html=True)

    elif st.session_state["active_page"] == "Video":
        st.markdown(
            """
            <div class="hero" style="background: linear-gradient(135deg, rgba(168,85,247,0.15), rgba(56,189,248,0.15)); border: 1px solid rgba(168,85,247,0.3); margin-bottom: 24px;">
              <h1 style="font-size: 32px;">🎬 Premium Video Compilation Studio</h1>
              <p style="margin-top: 6px; font-size: 14px;">Generate, render, and orchestrate stunning 5-minute premium explainer videos featuring cohesive 3D Pixar character illustrations.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        left_col, right_col = st.columns([5.5, 4.5])

        # Output directory slug setup
        video_subject_slug = _slugify(st.session_state.get("video_studio_subject", "How Freshers Can Survive in the AI World"))
        antigravity_output_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/video_episodes") / video_subject_slug

        with left_col:
            # Centered Video Canvas Box
            st.markdown(f"""
            <div class="canvas-box">
                <div class="canvas-title">🎬 Explainer Video Output Canvas</div>
            </div>
            """, unsafe_allow_html=True)

            final_video_file = antigravity_output_dir / "fresher_survive_ai_world.mp4"
            if final_video_file.exists():
                st.success("✨ Premium Explainer Video successfully compiled!")
                st.video(str(final_video_file))
                st.caption(f"Video saved location: `{final_video_file}`")
            else:
                st.info("No compiled video found for this subject yet. Configure options below and click 'Compile Full Video'!")

            # Video parameters under canvas box
            st.markdown("#### ⚙️ Compiler parameters")
            video_cols = st.columns(3)
            with video_cols[0]:
                st.text_input("Episode Topic", value="How Freshers Can Survive in the AI World", key="video_studio_topic")
            with video_cols[1]:
                st.text_input("Folder Subject", value="How Freshers Can Survive in the AI World", key="video_studio_subject")
            with video_cols[2]:
                presets = voice_preview_presets()
                preset_keys = [p.key for p in presets]
                preset_labels = {p.key: f"{p.label}" for p in presets}
                default_preset_key = st.session_state.get("voice_preset_choice", "indian_english_corporate_male")
                if default_preset_key not in preset_keys:
                    default_preset_key = "indian_english_corporate_male"
                st.selectbox(
                    "Narrator Preset Style",
                    options=preset_keys,
                    index=preset_keys.index(default_preset_key),
                    format_func=lambda k: preset_labels.get(k, k),
                    key="video_studio_voice_preset"
                )

            st.number_input("Scenes Count", min_value=5, max_value=35, value=35, step=1, key="video_studio_scenes")

            if st.button("🚀 Compile Widescreen Pixar Explainer Video", type="primary", use_container_width=True, key="btn_compile_video"):
                with st.spinner("Rendering edge speech voiceovers, captioned overlays, and executing high-speed FFmpeg concatenation..."):
                    try:
                        antigravity_output_dir.mkdir(parents=True, exist_ok=True)
                        import subprocess
                        import sys
                        import shutil

                        python_executable = sys.executable
                        script_path = "/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/scratch/generate_5min_fresher_video.py"
                        selected_preset_key = st.session_state["video_studio_voice_preset"]

                        result = subprocess.run(
                            [python_executable, script_path, "--preset", selected_preset_key],
                            capture_output=True,
                            text=True,
                            cwd="/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline"
                        )

                        if result.returncode == 0:
                            desktop_src = Path("/Users/lalitprasadsingh/Desktop/antigravity/video_episodes/fresher_ai_world_folder")
                            if desktop_src.exists():
                                if antigravity_output_dir.exists():
                                    shutil.rmtree(antigravity_output_dir)
                                shutil.copytree(desktop_src, antigravity_output_dir)
                                st.success("🎉 Video compiled and successfully saved under your Antigravity folder!")
                            st.rerun()
                        else:
                            st.error(f"Compilation failed with error code {result.returncode}")
                            st.code(result.stderr)
                    except Exception as e:
                        st.error(f"Compilation error: {e}")

        with right_col:
            # Storyboard Gallery and behind the scenes
            st.markdown("### 🎞️ Premium Storyboard Gallery")
            images_dir = antigravity_output_dir / "images"
            if images_dir.exists():
                image_files = sorted(list(images_dir.glob("scene_*.png")))
                if image_files:
                    img_cols = st.columns(2)
                    for idx, img_path in enumerate(image_files[:6]):
                        col_idx = idx % 2
                        with img_cols[col_idx]:
                            st.image(str(img_path), caption=f"Scene {idx+1}", use_container_width=True)
                    if len(image_files) > 6:
                        st.caption(f"Showing first 6 of {len(image_files)} scenes in this view. All scenes are compiled cleanly.")
                else:
                    st.info("Render images folder to view storyboard slides.")
            else:
                st.info("Compile video first to view visual storyboard gallery here.")

            st.markdown("---")
            st.markdown("### 📋 Storyboard & Scene Explorer")
            json_path = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/scratch/fresher_scenes_data.json")
            if json_path.exists():
                selected_scene_num = st.selectbox(
                    "Inspect Scene Block",
                    options=[i for i in range(1, len(scenes_data) + 1)],
                    format_func=lambda x: f"Scene {x}: {scenes_data[x-1]['title']}"
                )
                scene_info = scenes_data[selected_scene_num - 1]
                st.markdown(f"""
                <div class="metric-box">
                    <div style="font-weight:bold; color:#a855f7;">{scene_info['title']}</div>
                    <div style="margin-top:6px; font-size:13px; color:#f8fafc;"><b>Narration dialogue:</b> <i>"{scene_info['narration']}"</i></div>
                    <div style="margin-top:4px; font-size:12px; color:#94a3b8;"><b>Subtitle card:</b> <code>{scene_info['on_screen_text']}</code></div>
                </div>
                """, unsafe_allow_html=True)

                scene_img_file = antigravity_output_dir / "images" / f"scene_{selected_scene_num:02d}.png"
                if scene_img_file.exists():
                    st.image(str(scene_img_file), caption=f"Pristine slide illustration", use_container_width=True)

    elif st.session_state["active_page"] == "Content":
        st.markdown("### ⚙️ Pipeline controls & logs")

        # Pipeline Controls Row
        left_p, right_p = st.columns([6, 4])
        with left_p:
            st.markdown("#### Background Pipeline runner")
            st.write("Trigger daily LinkedIn content automated pipelines.")
            if "last_run_error" in st.session_state:
                st.error(st.session_state["last_run_error"])
            if "last_run_result" in st.session_state:
                st.json(st.session_state["last_run_result"])

            if st.button("🚀 Execute Daily LinkedIn content Pipeline", type="primary", use_container_width=True, key="btn_run_pipeline"):
                with st.spinner(f"Running daily LinkedIn package generation for {run_date}..."):
                    try:
                        result = run_linkedin_mvp(run_date, ui_settings)
                        st.session_state["last_run_result"] = result
                        st.success(f"Pipeline successfully run for {run_date}!")
                        st.rerun()
                    except Exception as e:
                        st.session_state["last_run_error"] = str(e)
                        st.error(f"Pipeline failed: {e}")

        with right_p:
            st.markdown("#### System Log & directory path settings")
            st.text_input("Active Project Output directory", key="output_dir_pref")

            # Date selections
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.date_input("Run Day", value=st.session_state["run_day"], key="run_day")
            with col_d2:
                st.date_input("Inspect Day", value=st.session_state["inspect_day"], key="inspect_day")

        st.markdown("---")
        st.markdown("#### 📂 Day Artifact Files explorer")

        day_root = ui_settings.output_dir / "daily" / inspect_date
        if day_root.exists():
            file_query = st.text_input("Search files in directory", value="", placeholder="Type filter text...")
            file_type = st.selectbox("File suffix filter", options=["all", "html", "json", "png", "svg", "mp3", "wav", "txt"])

            all_files = sorted(
                [path for path in day_root.rglob("*") if path.is_file()],
                key=lambda path: path.as_posix(),
            )
            if file_query:
                query = file_query.strip().lower()
                all_files = [p for p in all_files if query in p.name.lower()]
            if file_type != "all":
                all_files = [p for p in all_files if p.suffix.lower().lstrip(".") == file_type]

            for path in all_files[:20]:
                st.markdown(f"- [`{path.relative_to(day_root)}`]({path.as_uri()})")
            if len(all_files) > 20:
                st.caption(f"Showing first 20 of {len(all_files)} total files.")
        else:
            st.info("No daily directory found yet. Rerun pipeline to write files.")

        # Daily HTML Dashboard view
        st.markdown("---")
        st.markdown("#### 📊 Daily dashboard dashboard view")
        dashboard_path = ui_settings.output_dir / "daily" / inspect_date / "daily_dashboard.html"
        if dashboard_path.exists():
            dashboard_html = dashboard_path.read_text(encoding="utf-8")
            components.html(dashboard_html, height=800, scrolling=True)
        else:
            st.info("No dashboard HTML output exists for this day.")

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
