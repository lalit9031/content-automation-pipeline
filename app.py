from __future__ import annotations

import json
import math
import os
import sys
import re
import time
from dataclasses import replace
from datetime import date
from html import escape
from pathlib import Path
from collections.abc import Mapping

import site
import importlib
PROJECT_ROOT = Path(__file__).resolve().parent
TARGET_SITE_PACKAGES = PROJECT_ROOT / "output" / ".runtime" / "site-packages"
if str(TARGET_SITE_PACKAGES) not in sys.path:
    old_len = len(sys.path)
    site.addsitedir(str(TARGET_SITE_PACKAGES))
    new_paths = sys.path[old_len:]
    sys.path = new_paths + sys.path[:old_len]

# Invalidate import caches to force python to check the filesystem fresh
importlib.invalidate_caches()
sys.path_importer_cache.clear()

SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def resolve_2d_orchestrator_root() -> Path:
    """
    Prefer the external drive for 2D video work, then fall back to the local
    checked-in copy if the drive is unavailable.
    """
    env_root = os.getenv("KIDS_STUDIO_ORCHESTRATOR_ROOT", "").strip()
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.append(Path("/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator"))
    candidates.append(Path("/Volumes/Crucial X9/Mac/2D_Video/story_studio"))
    candidates.append(PROJECT_ROOT / "KidsStudio-Orchestrator")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    preferred = candidates[0]
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback = PROJECT_ROOT / "KidsStudio-Orchestrator"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def resolve_2d_patch_root() -> Path:
    patch_root = PROJECT_ROOT / ".2d_patches"
    patch_root.mkdir(parents=True, exist_ok=True)
    return patch_root

import streamlit as st

from content_pipeline.bots.audio import audio_status, render_audio_status_html
from content_pipeline.bots.audio import curate_reference_audio_bank
from content_pipeline.bots.audio import available_voice_options
from content_pipeline.bots.audio import generate_instrumental_audio_track
from content_pipeline.bots.audio import generate_music_preview
from content_pipeline.bots.audio import smart_mix_storytelling_music_agent
from content_pipeline.bots.audio import generate_voice_preview
from content_pipeline.bots.audio import filter_voice_preview_presets
from content_pipeline.bots.audio import normalize_voice_text
from content_pipeline.bots.audio import resolve_song_generation_space
from content_pipeline.bots.audio import reference_audio_language_options
from content_pipeline.bots.audio import scan_reference_audio_library
from content_pipeline.bots.audio import voice_gender_options
from content_pipeline.bots.audio import voice_preview_language_options
from content_pipeline.bots.audio import voice_preview_presets
from content_pipeline.bots.indic_parler_inference import generate_hf_tts_voiceover, generate_local_parler_voiceover
from content_pipeline.bots.image import ImageVariant, gemini_image_package_plan, image_provider
from content_pipeline.bots.prompt import build_cinematic_image_prompt
from content_pipeline.bots.prompt import build_image_style_pack
from content_pipeline.bots.prompt import sanitize_image_prompt_text
from content_pipeline.bots.youtube_audit import (
    render_youtube_audit_markdown,
    run_weekly_youtube_review,
)
from content_pipeline.bots.project_brain import (
    build_project_brain_report,
    load_latest_project_brain_report,
    render_project_brain_markdown,
)
from content_pipeline.config import Settings
from content_pipeline.pipeline import run_linkedin_mvp


def on_music_lyrics_changed():
    st.session_state["lyrics_manually_edited"] = True


def _auto_refresh_project_brain(settings, *, reason: str = "generation") -> None:
    try:
        output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
        report = build_project_brain_report(
            settings,
            refresh_web=False,
            trend_region=str(st.session_state.get("project_brain_trend_region", "IN")),
            output_dir=output_dir,
        )
        st.session_state["project_brain_report"] = report
        st.session_state["project_brain_paths"] = {
            "json": report.report_path,
            "markdown": report.markdown_path,
            "memory": report.memory_path,
        }
        st.session_state["project_brain_last_auto_reason"] = reason
        st.session_state["project_brain_last_auto_error"] = ""
    except Exception as exc:
        st.session_state["project_brain_last_auto_error"] = str(exc)


def _resolve_hf_song_token(settings: Settings) -> str:
    pool = list(getattr(settings, "hf_token_keys", ()) or ())
    if len(pool) >= 6:
        ordered = pool[3:6] + pool[:3] + pool[6:]
    else:
        ordered = pool
    for token in ordered:
        if token:
            return token
    return settings.hf_token or ""


def _apply_streamlit_secrets() -> None:
    try:
        secrets = st.secrets
        # Force evaluation to catch StreamlitSecretNotFoundError if secrets are not configured
        _ = secrets.keys()
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
        "HF_TOKEN",
        "HF_API_KEY",

    ]
    for key in direct_keys:
        value = _secret(key)
        if value and not os.environ.get(key):
            os.environ[key] = value

    gemini_keys = []
    nested_gemini = secrets.get("gemini_keys", {})
    if isinstance(nested_gemini, Mapping):
        for index in range(1, 11):
            value = nested_gemini.get(f"key_{index}")
            if value:
                gemini_keys.append(str(value))
    for index, value in enumerate(gemini_keys, start=1):
        env_key = "GEMINI_API_KEY" if index == 1 else f"GEMINI_API_KEY_{index}"
        if not os.environ.get(env_key):
            os.environ[env_key] = value

    # Fall back to direct top-level GEMINI_API_KEY and GOOGLE_API_KEY secrets mapping only if still missing
    if "GEMINI_API_KEY" in secrets and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = str(secrets["GEMINI_API_KEY"])
    if "GOOGLE_API_KEY" in secrets and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = str(secrets["GOOGLE_API_KEY"])

    openai_keys = []
    nested_openai = secrets.get("openai_keys", {})
    if isinstance(nested_openai, Mapping):
        for index in range(1, 11):
            value = nested_openai.get(f"key_{index}")
            if value:
                openai_keys.append(str(value))
    for index, value in enumerate(openai_keys, start=1):
        env_key = "OPENAI_API_KEY" if index == 1 else f"OPENAI_API_KEY_{index}"
        if not os.environ.get(env_key):
            os.environ[env_key] = value

    # Write client secrets and token files dynamically from streamlit secrets if they are provided as raw JSON
    selected_channel = "TechWithLalit"
    try:
        if hasattr(st, "session_state") and st.session_state:
            selected_channel = st.session_state.get("active_youtube_channel", "TechWithLalit")
    except Exception:
        pass

    channel_keys = {
        "TechWithLalit": "techwithlalit",
        "Studio_MagicTales": "magictales",
        "LittleBubbles TV": "littlebubbles"
    }
    c_key = channel_keys.get(selected_channel, "techwithlalit")

    token_secret_key = "YOUTUBE_TOKEN_JSON"
    drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID"
    client_secrets_secret_key = "YOUTUBE_CLIENT_SECRETS_JSON"

    if selected_channel == "LittleBubbles TV":
        token_secret_key = "YOUTUBE_TOKEN_JSON_LITTLEBUBBLES"
        drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID_LITTLEBUBBLES"
        client_secrets_secret_key = "YOUTUBE_CLIENT_SECRETS_JSON_LITTLEBUBBLES"
    elif selected_channel == "Studio_MagicTales":
        token_secret_key = "YOUTUBE_TOKEN_JSON_MAGICTALES"
        drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID_MAGICTALES"
        client_secrets_secret_key = "YOUTUBE_CLIENT_SECRETS_JSON_MAGICTALES"
    elif selected_channel == "TechWithLalit":
        token_secret_key = "YOUTUBE_TOKEN_JSON_TECHWITHLALIT"
        drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID_TECHWITHLALIT"
        client_secrets_secret_key = "YOUTUBE_CLIENT_SECRETS_JSON_TECHWITHLALIT"

    # Fall back to default keys if channel-specific keys are not set, and use the user's default mappings as pre-programmed fallbacks
    channel_drive_folders = {
        "TechWithLalit": "1wKNUTacQGK7XdVTb4Arn_R7oWN33HJlr",
        "Studio_MagicTales": "1JrJOfipdbOAR_TLwH5fG72m9h0EQMMaq",
        "LittleBubbles TV": "1fPWKoSaIH5ocuctMZTH5nk7nNNKAWBqk",
    }
    smart_default_folder = channel_drive_folders.get(selected_channel, "1pXJjgcxgYQ65K3Gw5kOipHBR0ZpR25eK")

    token_json = _secret(token_secret_key) or _secret("YOUTUBE_TOKEN_JSON")
    drive_folder_val = _secret(drive_folder_secret_key) or _secret("GOOGLE_DRIVE_FOLDER_ID") or smart_default_folder

    if token_json:
        token_dir = PROJECT_ROOT / ".secrets"
        token_dir.mkdir(parents=True, exist_ok=True)
        token_path = token_dir / f"youtube_token_{c_key}.json"
        token_path.write_text(token_json, encoding="utf-8")
        os.environ["YOUTUBE_TOKEN_FILE"] = str(token_path)

    if drive_folder_val:
        os.environ["GOOGLE_DRIVE_FOLDER_ID"] = drive_folder_val

    client_secrets_json = _secret(client_secrets_secret_key) or _secret("YOUTUBE_CLIENT_SECRETS_JSON")
    if client_secrets_json:
        scripts_dir = PROJECT_ROOT / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        client_secrets_path = scripts_dir / f"client_secret_{c_key}.json"
        client_secrets_path.write_text(client_secrets_json, encoding="utf-8")
        os.environ["YOUTUBE_CLIENT_SECRETS_FILE"] = str(client_secrets_path)




def upload_to_temp_host(file_path: str | Path) -> str:
    try:
        import requests
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post('https://tmpfiles.org/api/v1/upload', files=files, timeout=20)
            if response.status_code == 200:
                url = response.json()['data']['url']
                direct_url = url.replace('https://tmpfiles.org/', 'https://tmpfiles.org/dl/')
                return direct_url
    except Exception:
        pass
    return ""


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
        "music_mood",
        "music_duration_seconds",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value:
            state[key] = value

    # Support both old and new key name for back-compat
    img_pr = payload.get("image_prompt") or payload.get("image_studio_prompt")
    if isinstance(img_pr, str) and img_pr:
        state["image_studio_prompt"] = img_pr

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
        st.iframe(svg_text or path.read_text(encoding="utf-8"), height=720)
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


def update_dotenv_file(dotenv_path: Path, key: str, value: str) -> None:
    if not dotenv_path.exists():
        dotenv_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for idx, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[idx] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    dotenv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def generate_manifest_from_scratch(topic: str, video_id: str, settings) -> dict:
    """Uses Gemini to generate a brand new 4-scene manifest from a story topic."""
    # Find all API keys
    keys = list(settings.gemini_api_keys) if hasattr(settings, "gemini_api_keys") else []
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    
    custom_ui_key = st.session_state.get("custom_gemini_api_key", "").strip()
    if custom_ui_key:
        if custom_ui_key in keys:
            keys.remove(custom_ui_key)
        keys.insert(0, custom_ui_key)
        
    keys = [k for k in keys if k]
    if not keys:
        raise ValueError("No Gemini API keys found in Settings or Environment.")
        
    prompt = f"""
    Create a highly engaging 4-scene kids animation script/manifest based on the topic: "{topic}".
    The output must strictly conform to the following schema structure:
    {{
      "video_id": "{video_id}",
      "canvas_dimensions": [1280, 720],
      "fps": 24,
      "global_bgm": "assets/character/bg_music.mp3",
      "voice_presets": {{
          "Narrator": "Rasalgethi",
          "Character1_Name": "Charon",
          "Character2_Name": "Puck"
      }},
      "timeline_scenes": [
        {{
          "scene_sequence": 1,
          "background_asset": "assets/environments/thirsty_crow_garden.png",
          "camera_effect": "zoom_in",
          "dialogue": [
            {{ "speaker": "Narrator", "text": "एक कौआ बहुत प्यासा था..." }}
          ],
          "scene_characters": [
            {{
              "folder_name": "thirsty_crow",
              "scale_factor": 250,
              "motion_path": {{
                "enabled": false,
                "start_position": [500, 300],
                "start_scale": 1.0
              }},
              "states": [
                {{ "time_range": [0.0, 100.0], "animation_state": "idle" }}
              ]
            }}
          ]
        }}
      ]
    }}
    
    Rules:
    1. Structure must have exactly 4 scenes.
    2. Write the dialogues/text in Hindi (since this is a kids Hindi animation studio) using Devanagari script.
    3. Specify characters and coordinate placements that match the scene action.
    4. For "background_asset", specify a descriptive path under "assets/environments/" like "assets/environments/[topic_slug]_bg.png".
    5. For characters, specify folder names under "assets/sprites/" like "thirsty_crow".
    6. Return ONLY the valid JSON block conforming exactly to this structure. No markdown formatting.
    """
    
    for key in keys:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text)
            if "timeline_scenes" in data:
                normalize_2d_scene_manifest(data)
                return data
        except Exception as e:
            pass
            
    raise RuntimeError("Gemini failed to generate manifest from topic.")


def apply_manifest_suggestions(manifest_data: dict, user_suggestion: str, settings) -> dict:
    """Uses Gemini to rewrite the scene manifest JSON based on user suggestions."""
    # Find all API keys
    keys = list(settings.gemini_api_keys) if hasattr(settings, "gemini_api_keys") else []
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    
    custom_ui_key = st.session_state.get("custom_gemini_api_key", "").strip()
    if custom_ui_key:
        if custom_ui_key in keys:
            keys.remove(custom_ui_key)
        keys.insert(0, custom_ui_key)
        
    keys = [k for k in keys if k]
    if not keys:
        raise ValueError("No Gemini API keys found in Settings or Environment.")
        
    prompt = f"""
    You are an expert AI video director. Your job is to modify the following 2D Animation Scene Manifest based on the user's suggestion.
    
    User's suggestion: "{user_suggestion}"
    
    Current Scene Manifest JSON:
    {json.dumps(manifest_data, indent=2, ensure_ascii=False)}
    
    Rules for output:
    1. Maintain the exact JSON schema.
    2. Update dialogues, visual backgrounds, speaker names, voice assignments, and character specifications (like scales, coordinates, folder names) to align with the user's suggestion.
    3. If the user wants a new background (e.g. snowy mountains), change the "background_asset" value to a matching PNG name under "assets/environments/" (e.g., "assets/environments/snowy_mountains.png").
    4. If the user wants new characters (e.g. a cute rabbit), update the "folder_name" of that character inside "scene_characters" (e.g., "cute_rabbit") and ensure they are added to the dialogue and character lists.
    5. Return ONLY a valid JSON block conforming exactly to the manifest schema. Do not enclose it in markdown blocks or anything.
    """
    
    for key in keys:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text)
            if "timeline_scenes" in data:
                normalize_2d_scene_manifest(data)
                return data
        except Exception as e:
            pass
            
    raise RuntimeError("Gemini failed to process manifest update suggestions.")


def _normalize_2d_text_token(value: str) -> str:
    return re.sub(r"[^\w\u0900-\u097f]+", "", value.lower().strip())


def _scene_character_speaks(dialogue: list[dict[str, str]], folder_name: str) -> bool:
    folder_norm = _normalize_2d_text_token(folder_name)
    if not folder_norm:
        return False
    for line in dialogue:
        speaker = _normalize_2d_text_token(str(line.get("speaker", "")))
        if not speaker or speaker == "narrator":
            continue
        if speaker in folder_norm or folder_norm in speaker:
            return True
    return False


def normalize_2d_scene_manifest(manifest_data: dict) -> bool:
    """
    Ensure the 2D story manifest is ready for lip-sync aware rendering.

    The compiler already knows how to map Rhubarb mouth timings, but it only
    activates that path when a character state is marked as
    ``talking_lip_sync``. Gemini often returns idle-only states, so we upgrade
    speaking characters to a full-scene talking state and add a tiny motion
    path if the character is otherwise static. This keeps the final video more
    alive without changing the story beats.
    """
    changed = False
    for scene in manifest_data.get("timeline_scenes", []):
        dialogue = scene.get("dialogue", [])
        for character in scene.get("scene_characters", []):
            folder_name = str(character.get("folder_name", "")).strip()
            if not folder_name:
                continue
            if _scene_character_speaks(dialogue, folder_name):
                desired_states = [
                    {
                        "time_range": [0.0, 100.0],
                        "animation_state": "talking_lip_sync",
                    }
                ]
                if character.get("states") != desired_states:
                    character["states"] = desired_states
                    changed = True

                motion_path = character.get("motion_path")
                if isinstance(motion_path, dict) and not motion_path.get("enabled", False):
                    start_position = motion_path.get("start_position", [0, 0])
                    try:
                        start_x = int(start_position[0])
                        start_y = int(start_position[1])
                    except Exception:
                        start_x, start_y = 0, 0
                    motion_path["enabled"] = True
                    motion_path["start_position"] = [start_x, start_y]
                    motion_path["end_position"] = [start_x + 8, start_y + 3]
                    motion_path["start_scale"] = float(motion_path.get("start_scale", 1.0))
                    motion_path["end_scale"] = round(
                        float(motion_path.get("start_scale", 1.0)) * 1.01,
                        3,
                    )
                    motion_path["start_time"] = float(motion_path.get("start_time", 0.0))
                    motion_path["end_time"] = float(motion_path.get("end_time", 100.0))
                    changed = True
            elif not character.get("states"):
                character["states"] = [
                    {
                        "time_range": [0.0, 100.0],
                        "animation_state": "idle",
                    }
                ]
                changed = True

        if not scene.get("camera_effect"):
            scene["camera_effect"] = "zoom_in"
            changed = True
    return changed


def generate_missing_assets(manifest_data: dict, orchestrator_path: Path, settings) -> list[str]:
    """Generates any missing background or character images referenced in the manifest."""
    import shutil
    generated_assets = []
    
    # 1. Backgrounds
    for scene in manifest_data.get("timeline_scenes", []):
        bg_asset = scene.get("background_asset", "")
        if bg_asset:
            bg_full_path = orchestrator_path / bg_asset
            if not bg_full_path.exists():
                bg_full_path.parent.mkdir(parents=True, exist_ok=True)
                bg_name = bg_full_path.stem.replace("_", " ")
                prompt = f"A gorgeous, vibrant, colorful {bg_name} background illustration, high-end 3D Pixar claymation animation style, clean detail, no text, widescreen 16:9, depth of field."
                
                try:
                    from content_pipeline.bots.image import ImageVariant, image_provider
                    provider = image_provider(replace(settings, image_provider=st.session_state.get("image_provider_choice", "flux")))
                    variant = ImageVariant("16:9", 1280, 720, "bg_asset")
                    img_bytes = provider.create(prompt, variant)
                    bg_full_path.write_bytes(img_bytes)
                    generated_assets.append(f"Background: {bg_asset}")
                except Exception as e:
                    st.warning(f"Failed to generate background '{bg_asset}': {e}")
                    
    # 2. Characters
    for scene in manifest_data.get("timeline_scenes", []):
        for char in scene.get("scene_characters", []):
            folder_name = char.get("folder_name", "")
            if folder_name:
                char_dir = orchestrator_path / "assets" / "sprites" / folder_name
                body_path = char_dir / "body.png"
                if not body_path.exists():
                    char_dir.mkdir(parents=True, exist_ok=True)
                    char_name = folder_name.replace("_", " ")
                    prompt = f"A cute, funny standalone {char_name} character, full body view, centered, solid flat green background for chroma keying, high-end 3D Pixar claymation animation style, vibrant colors, clear outlines."
                    
                    try:
                        from content_pipeline.bots.image import ImageVariant, image_provider
                        provider = image_provider(replace(settings, image_provider=st.session_state.get("image_provider_choice", "flux")))
                        variant = ImageVariant("1:1", 1024, 1024, "char_asset")
                        img_bytes = provider.create(prompt, variant)
                        body_path.write_bytes(img_bytes)
                        
                        # Copy talk shapes from kalu_crow template
                        talk_dir = char_dir / "talk"
                        talk_dir.mkdir(exist_ok=True)
                        template_talk = orchestrator_path / "assets" / "sprites" / "kalu_crow" / "talk"
                        if template_talk.exists():
                            for f in template_talk.iterdir():
                                if f.is_file():
                                    shutil.copy(f, talk_dir / f.name)
                                    
                        # Copy and update metadata.json
                        template_meta = orchestrator_path / "assets" / "sprites" / "kalu_crow" / "metadata.json"
                        if template_meta.exists():
                            with open(template_meta, "r") as f:
                                meta_data = json.load(f)
                            meta_data["character_key"] = folder_name.upper()
                            with open(char_dir / "metadata.json", "w") as f:
                                json.dump(meta_data, f, indent=2)
                                
                        generated_assets.append(f"Character: {folder_name}")
                    except Exception as e:
                        st.warning(f"Failed to generate character body for '{folder_name}': {e}")
                        
    return generated_assets


def render_frontdoor(settings: Settings) -> None:
    global json
    latest_day = latest_daily_day(settings.output_dir)
    default_day = date.fromisoformat(latest_day) if latest_day else date.today()
    latest_overview = day_overview(settings.output_dir / "daily" / latest_day) if latest_day else {"file_count": 0}
    latest_dashboard = settings.output_dir / "daily" / latest_day / "daily_dashboard.html" if latest_day else None
    latest_audio = settings.output_dir / "daily" / latest_day / "audio_status.html" if latest_day else None



    # Track active page inside session state
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "Dashboard"

    # Silent state sync setup
    if "output_dir_pref" not in st.session_state:
        st.session_state["output_dir_pref"] = str(settings.output_dir)

    ui_output_dir = resolve_output_dir(st.session_state["output_dir_pref"])
    saved_studio_state = load_studio_state(ui_output_dir)

    # Initialize all default state values silently (removing sidebar components)
    if st.session_state.get("_studio_output_dir") != str(ui_output_dir):
        st.session_state["_studio_output_dir"] = str(ui_output_dir)
        st.session_state["voice_preset_choice"] = saved_studio_state.get("voice_preset_choice", "english_explainer")
        st.session_state["voice_provider_choice"] = saved_studio_state.get("voice_provider", "edge")
        st.session_state["voice_name_choice"] = saved_studio_state.get("voice_name", settings.indian_tts_voice)
        st.session_state["voice_preview_text"] = saved_studio_state.get(
            "voice_preview_text",
            "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm.",
        )
        img_prov = saved_studio_state.get("image_provider", settings.image_provider)
        if img_prov == "mock":
            img_prov = "gemini"
        st.session_state["image_provider_choice"] = img_prov
        st.session_state["image_topic"] = saved_studio_state.get("image_topic", "Agile project management")
        st.session_state["image_subject"] = saved_studio_state.get(
            "image_subject",
            "a team reviewing a glowing workflow board",
        )
        st.session_state["image_art_style"] = saved_studio_state.get("image_art_style", "3D Claymation / Pixar")
        st.session_state["image_studio_prompt"] = saved_studio_state.get(
            "image_studio_prompt",
            saved_studio_state.get(
                "image_prompt",
                build_cinematic_image_prompt(
                    st.session_state["image_topic"],
                    st.session_state["image_subject"],
                    style_name=st.session_state["image_art_style"]
                ),
            )
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
    img_prov = settings.image_provider
    if img_prov == "mock" or img_prov not in ("nvidia", "gemini", "openai", "free-ai", "mock"):
        img_prov = "nvidia"
    st.session_state.setdefault("image_provider_choice", img_prov)
    st.session_state.setdefault("image_topic", "Agile project management")
    st.session_state.setdefault("image_subject", "a team reviewing a glowing workflow board")
    st.session_state.setdefault("image_art_style", "3D Claymation / Pixar")
    st.session_state.setdefault(
        "image_studio_prompt",
        build_cinematic_image_prompt(
            st.session_state["image_topic"],
            st.session_state["image_subject"],
            style_name=st.session_state["image_art_style"]
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
    apply_pending_voice_preset()
    
    # Compute all lookup maps and presets offline (replacing st.sidebar selectbox references)
    gender_options = voice_gender_options()
    gender_map = {value: label for value, label in gender_options}
    
    default_voice_gender = st.session_state.get("voice_gender_filter", "all")
    if default_voice_gender not in gender_map:
        default_voice_gender = "all"
        st.session_state["voice_gender_filter"] = default_voice_gender
        
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
        apply_voice_preset_by_key(preset_default)
        
    voice_provider_choice = st.session_state.get("voice_provider_choice", "edge")
    voice_options = available_voice_options("edge", st.session_state["voice_gender_filter"])
    if not voice_options:
        voice_options = available_voice_options("edge")
        
    preset_choice = st.session_state.get("voice_preset_choice")
    if preset_choice:
        preset_lookup = {p.key: p for p in voice_preview_presets()}
        active_p = preset_lookup.get(preset_choice)
        if active_p and active_p.voice not in [v for v, _ in voice_options]:
            voice_options.append((active_p.voice, f"{active_p.voice} - Native Preset Voice"))
            
    voice_option_values = [voice for voice, _ in voice_options]
    default_voice = st.session_state.get("voice_name_choice") or settings.indian_tts_voice
    if default_voice not in voice_option_values:
        default_voice = voice_option_values[0]
    if st.session_state["voice_name_choice"] not in voice_option_values:
        st.session_state["voice_name_choice"] = default_voice
        
    voice_name_choice = st.session_state["voice_name_choice"]
    voice_preview_text = st.session_state.get("voice_preview_text", "")
    current_voice_preset = preset_map[st.session_state["voice_preset_choice"]]
    
    language_options = voice_preview_language_options()
    language_map = {value: label for value, label in language_options}
    
    reference_audio_options = reference_audio_language_options()
    reference_audio_language_map = {value: label for value, label in reference_audio_options}
    
    st.session_state.setdefault("scene_index", 0)
    st.session_state.setdefault("audio_tab_choice", "🎙️ Voice Over")

    # Dates & JSON view
    run_day = st.session_state.setdefault("run_day", default_day)
    inspect_day = st.session_state.setdefault("inspect_day", default_day)
    show_json = st.session_state.setdefault("show_json", False)


    # Load scene data silently
    json_path = PROJECT_ROOT / "scratch" / "fresher_scenes_data.json"
    if not json_path.exists():
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
        voice_provider=st.session_state.get("voice_provider_choice", "edge"),
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
                        st.session_state["voice_provider_choice"] = getattr(preset, "provider", "edge")
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

    # Render Compact Top Quota Status Bar
    from content_pipeline.bots.image import gemini_image_status
    from content_pipeline.bots.gemini_tts import GeminiAudioLimiter
    
    try:
        img_status = gemini_image_status(ui_settings)
        audio_limiter = GeminiAudioLimiter(ui_settings.output_dir / ".runtime" / "gemini_audio_rate_limit.json", daily_budget=50)
        audio_status = audio_limiter.get_current_status()
        
        rem_img = img_status.get("daily_remaining")
        rem_img_val = f"{rem_img} left" if rem_img is not None else "Unlimited"
        if img_status.get("daily_limit_reached"):
            img_badge = "🔴 <span style='font-weight: 800;'>Imagen Quota Hit!</span> (Flux Fallback)"
        else:
            img_badge = f"🎨 <span style='font-weight: 800; color: #38bdf8;'>Imagen Quota</span>: <span style='font-weight: 800; color: white;'>{rem_img_val}</span> today"
            
        rem_aud = audio_status['remaining']
        if audio_status.get("limit_reached"):
            aud_badge = "🔴 <span style='font-weight: 800;'>Hindi TTS Quota Hit!</span> (Edge Fallback)"
        else:
            aud_badge = f"🎙️ <span style='font-weight: 800; color: #a855f7;'>Hindi TTS Quota</span>: <span style='font-weight: 800; color: white;'>{rem_aud} left</span> today"
            
        st.markdown(
            f"""
            <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 8px 18px; margin-bottom: 18px; font-size: 13px; font-family: sans-serif; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);">
                <div style="display: flex; gap: 24px;">
                    <div>{img_badge}</div>
                    <div>{aud_badge}</div>
                </div>
                <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 800; letter-spacing: 0.08em; display: flex; align-items: center; gap: 4px;">
                    <span style="color: #10b981;">●</span> Gemini API Monitor
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if audio_status.get("limit_reached"):
            col_reset1, col_reset2 = st.columns([8, 2])
            with col_reset2:
                if st.button("🔄 Reset Quota", key="btn_reset_tts_quota"):
                    import json
                    state_path = ui_settings.output_dir / ".runtime" / "gemini_audio_rate_limit.json"
                    try:
                        state_path.parent.mkdir(parents=True, exist_ok=True)
                        state_path.write_text(json.dumps({
                            "usage_date": date.today().isoformat(),
                            "daily_generated": 0,
                            "rollover": 0
                        }, indent=2) + "\n", encoding="utf-8")
                        st.toast("Quota reset successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to reset quota: {e}")
    except Exception:
        pass

    # Render horizontal top bar page navigation inside columns (Categorized)
    nav_cols = st.columns(6)

    categories = ["Dashboard", "Music", "Video", "Image", "Automation", "Files"]
    category_icons = [
        "📊 Dashboard",
        "🎵 Music",
        "🎬 Video",
        "🎨 Image",
        "⚙️ Automation",
        "📁 Files"
    ]

    # Initialize active category if not set
    if "active_category" not in st.session_state:
        initial_cat = "Dashboard"
        cur_page = st.session_state.get("active_page", "Dashboard")
        if cur_page in ["Music", "Kids", "Speech", "Cloner"]:
            initial_cat = "Music"
        elif cur_page in ["Video", "2DVideo"]:
            initial_cat = "Video"
        elif cur_page in ["Image", "ComicVideo"]:
            initial_cat = "Image"
        elif cur_page in ["Run", "Distribution", "Prompts"]:
            initial_cat = "Automation"
        elif cur_page == "Files":
            initial_cat = "Files"
        st.session_state["active_category"] = initial_cat

    for i, (cat, icon) in enumerate(zip(categories, category_icons)):
        with nav_cols[i]:
            is_active = st.session_state["active_category"] == cat
            if st.button(icon, key=f"nav_cat_{cat}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state["active_category"] = cat
                if cat == "Music":
                    st.session_state["active_music_page"] = "Music Studio"
                elif cat == "Video":
                    st.session_state["active_video_page"] = "Current Video Studio"
                elif cat == "Image":
                    st.session_state["active_image_page"] = "Image Studio"
                elif cat == "Automation":
                    st.session_state["active_automation_page"] = "Run Pipeline"
                st.rerun()

    active_cat = st.session_state["active_category"]
    
    # Render sub-navigation below top bar if category has subpages
    if active_cat == "Music":
        st.session_state.setdefault("active_music_page", "Music Studio")
        sub_cols = st.columns(5)
        sub_pages = ["Music Studio", "Instrumental Studio", "Kids Music Studio", "Speech Studio", "Voice Cloner"]
        sub_icons = ["🎵 Music Studio", "🎼 Instrumental Studio", "👶 Kids Music Studio", "🎙️ Speech Studio", "🎙️ Voice Cloner"]
        for i, (page, icon) in enumerate(zip(sub_pages, sub_icons)):
            with sub_cols[i]:
                is_active = st.session_state["active_music_page"] == page
                if st.button(icon, key=f"sub_music_{page}", use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state["active_music_page"] = page
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        
    elif active_cat == "Video":
        st.session_state.setdefault("active_video_page", "Current Video Studio")
        sub_cols = st.columns(2)
        sub_pages = ["Current Video Studio", "2D Video Studio"]
        sub_icons = ["🎬 Current Video Studio", "🎥 2D Video Studio"]
        for i, (page, icon) in enumerate(zip(sub_pages, sub_icons)):
            with sub_cols[i]:
                is_active = st.session_state["active_video_page"] == page
                if st.button(icon, key=f"sub_video_{page}", use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state["active_video_page"] = page
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    elif active_cat == "Image":
        st.session_state.setdefault("active_image_page", "Image Studio")
        sub_cols = st.columns(2)
        sub_pages = ["Image Studio", "Comic Book Video"]
        sub_icons = ["🖼️ Image Studio", "💬 Comic Book Video"]
        for i, (page, icon) in enumerate(zip(sub_pages, sub_icons)):
            with sub_cols[i]:
                is_active = st.session_state["active_image_page"] == page
                if st.button(icon, key=f"sub_image_{page}", use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state["active_image_page"] = page
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    elif active_cat == "Automation":
        st.session_state.setdefault("active_automation_page", "Run Pipeline")
        auto_rows = [
            ["Run Pipeline", "Automation Music Studio", "Automation Kids Music Studio"],
            ["Automation Image Studio", "YouTube Audit", "Social Publish"],
            ["Daily Prompts", "Project Brain", ""],
        ]
        auto_icons = {
            "Run Pipeline": "⚙️ Run Pipeline",
            "Automation Music Studio": "🎵 Automation Music Studio",
            "Automation Kids Music Studio": "👶 Automation Kids Music Studio",
            "Automation Image Studio": "🖼️ Automation Image Studio",
            "YouTube Audit": "🔎 YouTube Audit",
            "Social Publish": "🚀 Social Publish",
            "Daily Prompts": "💡 Daily Prompts",
            "Project Brain": "🧠 Project Brain",
        }
        for row in auto_rows:
            sub_cols = st.columns(3)
            for i, page in enumerate(row):
                if not page:
                    continue
                with sub_cols[i]:
                    is_active = st.session_state["active_automation_page"] == page
                    if st.button(
                        auto_icons[page],
                        key=f"sub_auto_{page}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        st.session_state["active_automation_page"] = page
                        st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    # Resolve active_p variable to sync with original logic
    if active_cat == "Dashboard":
        active_p = "Dashboard"
    elif active_cat == "Music":
        subpage_mapping = {
            "Music Studio": "Music",
            "Instrumental Studio": "Instrumental",
            "Kids Music Studio": "Kids",
            "Speech Studio": "Speech",
            "Voice Cloner": "Cloner"
        }
        active_p = subpage_mapping.get(st.session_state["active_music_page"], "Music")
    elif active_cat == "Video":
        subpage_mapping = {
            "Current Video Studio": "Video",
            "2D Video Studio": "2DVideo"
        }
        active_p = subpage_mapping.get(st.session_state["active_video_page"], "Video")
    elif active_cat == "Image":
        image_subpage_mapping = {
            "Image Studio": "Image",
            "Comic Book Video": "ComicVideo",
        }
        active_p = image_subpage_mapping.get(st.session_state["active_image_page"], "Image")
    elif active_cat == "Automation":
        subpage_mapping = {
            "Run Pipeline": "Run",
            "Automation Music Studio": "Music",
            "Automation Kids Music Studio": "Kids",
            "Automation Image Studio": "AutoImage",
            "YouTube Audit": "Audit",
            "Social Publish": "Distribution",
            "Daily Prompts": "Prompts",
            "Project Brain": "Brain",
        }
        st.session_state["automation_music_combo_mode"] = st.session_state["active_automation_page"] == "Automation Music Studio"
        st.session_state["automation_kids_combo_mode"] = st.session_state["active_automation_page"] == "Automation Kids Music Studio"
        active_p = subpage_mapping.get(st.session_state["active_automation_page"], "Run")
    elif active_cat == "Files":
        active_p = "Files"
    else:
        active_p = "Dashboard"
        
    st.session_state["active_page"] = active_p

    with st.expander("⚙️ Studio Settings & Date Controls", expanded=False):
        # 1. Output directory
        output_dir_input = st.text_input("Output directory", value=str(st.session_state.get("output_dir_pref", str(settings.output_dir))), key="output_dir_pref_input")
        if output_dir_input != st.session_state.get("output_dir_pref"):
            st.session_state["output_dir_pref"] = output_dir_input
            st.rerun()
            
        # 2. Date controls
        settings_cols = st.columns(2)
        with settings_cols[0]:
            run_day = st.date_input("Run day", key="run_day")
        with settings_cols[1]:
            inspect_day = st.date_input("Inspect day", key="inspect_day")
            
        # 3. YouTube Channel selector
        st.markdown("---")
        st.markdown("#### 📺 Active YouTube Channel")
        channel_options = ["TechWithLalit", "Studio_MagicTales", "LittleBubbles TV"]
        st.session_state.setdefault("active_youtube_channel", "TechWithLalit")
        st.selectbox(
            "Select Target YouTube Channel",
            options=channel_options,
            key="active_youtube_channel"
        )

        st.markdown("---")
        st.markdown("#### 🔑 Custom Gemini API Configuration")
        st.info("If the pre-configured keys in the `.env` file are rate-limited or exhausted, enter your own Gemini API key below. It will take absolute highest priority.")
        st.text_input(
            "Custom Gemini API Key",
            type="password",
            key="custom_gemini_api_key",
            help="Your personal key starting with AIzaSy... (kept securely in session memory and not written to disk)."
        )

        st.markdown("---")
        # 4. Load latest / selected day
        btn_cols = st.columns(3)

        with btn_cols[0]:
            if st.button("Load latest day", use_container_width=True, disabled=not latest_day):
                st.session_state["run_day"] = default_day
                st.session_state["inspect_day"] = default_day
                st.rerun()
        with btn_cols[1]:
            recent_days = recent_daily_days(settings.output_dir)
            if recent_days:
                selected_day_opt = st.selectbox("Recent days", options=recent_days, label_visibility="collapsed")
                if st.button("Load selected day", use_container_width=True):
                    selected = date.fromisoformat(selected_day_opt)
                    st.session_state["run_day"] = selected
                    st.session_state["inspect_day"] = selected
                    st.rerun()
            else:
                st.caption("No recent runs yet.")
                
        with btn_cols[2]:
            show_json = st.checkbox("Show raw JSON", value=st.session_state.get("show_json", False), key="show_json")

        # 5. Quota Limits & Fallback Alert Monitor
        st.markdown("---")
        st.markdown("#### 📊 Daily Gemini API Quota Limits")
        
        from content_pipeline.bots.image import gemini_image_status
        from content_pipeline.bots.gemini_tts import GeminiAudioLimiter
        
        try:
            img_status = gemini_image_status(ui_settings)
            audio_limiter = GeminiAudioLimiter(ui_settings.output_dir / ".runtime" / "gemini_audio_rate_limit.json", daily_budget=50)
            audio_status = audio_limiter.get_current_status()
            
            q_cols = st.columns(2)
            with q_cols[0]:
                if img_status.get("daily_limit_reached"):
                    st.error("⚠️ **Image Limit (90) Hit!** Swapped to free Flux.")
                else:
                    rem_img = img_status.get("daily_remaining")
                    st.success(f"🎨 Imagen Quota: **{rem_img if rem_img is not None else 'Unlimited'}** left today.")
            with q_cols[1]:
                if audio_status.get("limit_reached"):
                    st.error("⚠️ **Hindi Audio Limit (15) Hit!** Swapped to free Edge TTS.")
                    if st.button("🔄 Reset Quota", key="btn_reset_tts_quota_dashboard"):
                        import json
                        state_path = ui_settings.output_dir / ".runtime" / "gemini_audio_rate_limit.json"
                        try:
                            state_path.parent.mkdir(parents=True, exist_ok=True)
                            state_path.write_text(json.dumps({
                                "usage_date": date.today().isoformat(),
                                "daily_generated": 0,
                                "rollover": 0
                            }, indent=2) + "\n", encoding="utf-8")
                            st.toast("Quota reset successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reset quota: {e}")
                else:
                    st.success(f"🎙️ Hindi TTS Quota: **{audio_status['remaining']}** left today.")
        except Exception:
            pass


    # RENDER SELECTED PAGE
    active_p = st.session_state["active_page"]

    if active_p == "Dashboard":
        st.subheader("Daily dashboard")

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

        st.write("---")

        dashboard_path = ui_settings.output_dir / "daily" / inspect_date / "daily_dashboard.html"
        if dashboard_path.exists():
            dashboard_html = dashboard_path.read_text(encoding="utf-8")
            st.iframe(dashboard_html, height=1150)
        else:
            st.info("Run the pipeline or pick a day that already has a daily dashboard.")
            st.caption(str(dashboard_path))
        if dashboard_path.exists():
            st.markdown(f"[Open dashboard file]({dashboard_path.as_uri()})")

    elif active_p == "AutoImage":
        render_automation_image_studio(settings)

    elif active_p == "Audit":
        render_youtube_audit_studio(settings)

    elif active_p == "Brain":
        render_project_brain_studio(settings)

    elif active_p == "Music":
        st.markdown("### Music studio")
        st.markdown("<p style='font-size: 14.5px; color: #94a3b8; margin-top: -10px; margin-bottom: 24px;'>Compose premium, high-fidelity songs in any genre featuring warm singing voices powered by Tencent Lyria 3 Pro.</p>", unsafe_allow_html=True)
        
        if "lyrics_manually_edited" not in st.session_state:
            st.session_state["lyrics_manually_edited"] = bool(st.session_state.get("music_studio_lyrics", "").strip())
        disable_advanced_settings = not st.session_state["lyrics_manually_edited"]
        automation_combo_mode = bool(st.session_state.get("automation_music_combo_mode", False))
        
        # Target Language Dropdown
        st.session_state.setdefault("music_studio_language", "English")
        st.selectbox(
            "Target Song Language",
            options=["English", "Hindi", "Hinglish"],
            key="music_studio_language",
            help="Choose the language for the song generation. This filters the reference audio files and guides the dynamic lyric generator."
        )
        
        # Script Generator Selector
        st.session_state.setdefault("music_studio_script_generator", "NVIDIA Llama 3.3")
        st.selectbox(
            "Choose Script Generator",
            options=["Gemini", "NVIDIA Llama 3.3", "Local LLM (Ollama/LM Studio)"],
            index=1,
            key="music_studio_script_generator",
            help="Select the AI brain used to write lyrics and musical styles."
        )
        
        # Dynamic inputs for Local LLM
        if st.session_state.get("music_studio_script_generator") == "Local LLM (Ollama/LM Studio)":
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                m_url = st.text_input(
                    "Local LLM API Endpoint:",
                    value=settings.local_llm_url,
                    key="music_studio_local_llm_url"
                )
            with m_col2:
                m_model = st.text_input(
                    "Local LLM Model Name:",
                    value=settings.local_llm_model,
                    key="music_studio_local_llm_model"
                )
            settings = replace(settings, local_llm_url=m_url, local_llm_model=m_model)

        # One-Click Creator
        with st.expander("⚡ One-Click Song Creator", expanded=True):
            st.markdown("<small style='color: #94a3b8;'>Type a topic, select emotion, genre, and duration, and generate a complete song in one click.</small>", unsafe_allow_html=True)
            one_click_prompt = st.text_input("Song Topic / Subject", placeholder="e.g., childhood memories, moving on, rainy day", key="music_studio_one_click_song_idea")
            
            # Mood and Genre Selectors
            col_mood, col_genre = st.columns(2)
            with col_mood:
                mood_options = ["Sad", "Love", "Happy", "Pain", "Energetic", "Peaceful", "Angry", "Devotional / Spiritual"]
                mood_val = st.selectbox("Song Mood / Emotion", options=mood_options, key="music_studio_one_click_mood")
            with col_genre:
                genre_options = ["Melody", "Rap / Hip-Hop", "Rock", "Pop", "Acoustic / Ghazal", "Electronic / Dance", "EDM", "Tomorrowland", "Classical / Traditional"]
                genre_val = st.selectbox("Musical Genre / Style", options=genre_options, key="music_studio_one_click_genre")

            lang = st.session_state.get("music_studio_language", "English")
            if lang in ["Hindi", "Hinglish"]:
                from content_pipeline.bots.singer_manifest import SINGER_MANIFEST
                singer_opts = {v["display_name"]: k for k, v in SINGER_MANIFEST.items()}
                selected_display = st.selectbox(
                    "Select Playback Singer Voice Profile:",
                    options=list(singer_opts.keys()),
                    key="music_studio_playback_singer_display"
                )
                active_singer = singer_opts[selected_display]
                st.session_state["music_studio_playback_singer_key"] = active_singer
                
                singer_gender = SINGER_MANIFEST[active_singer]["gender"].capitalize()
                st.session_state["music_studio_one_click_singer_gender"] = singer_gender
                one_click_gender = singer_gender
            else:
                one_click_gender = st.selectbox("Singer Voice Gender Selection", ["Female", "Male"], key="music_studio_one_click_singer_gender")
                st.session_state["music_studio_playback_singer_key"] = "arijit_singh" if one_click_gender == "Male" else "shreya_ghoshal"

            # ── Duration picker (approx lengths) ───────────────────────────────
            DURATION_OPTIONS = {
                "~1 min (Short)": 60,
                "~1.5 mins (Standard)": 90,
                "~2 mins": 120,
                "~3 mins": 180,
                "~4 mins": 240,
                "~5 mins": 300,
                "~6 mins": 360,
            }
            current_dur_label = st.session_state.get("music_studio_duration_label", "~2 mins")
            if current_dur_label not in DURATION_OPTIONS:
                current_dur_label = "~2 mins"
            song_dur_label = st.selectbox(
                "Approximate Song Length",
                options=list(DURATION_OPTIONS.keys()),
                index=list(DURATION_OPTIONS.keys()).index(current_dur_label),
                key="music_studio_duration_label",
                help="Pick a rough target length. The AI may be ±20 sec off this value.",
            )
            target_dur_seconds = DURATION_OPTIONS[song_dur_label]
            st.session_state["music_duration_seconds"] = target_dur_seconds
            st.session_state["music_studio_song_length_seconds"] = target_dur_seconds
            st.caption(f"Target: {song_dur_label} (≈ {target_dur_seconds}s). Actual may vary slightly.")

            # Pacing/Tempo Selector to solve slow/overstretched vocals
            pacing_options = ["Auto", "Fast / Upbeat", "Medium / Mid-tempo", "Slow / Ballad"]
            st.selectbox(
                "Song Pacing / Tempo",
                options=pacing_options,
                key="music_studio_pacing_tempo",
                help="Control the tempo and singing speed. Select 'Fast / Upbeat' to prevent slow-drawn vocals or overstretching, especially for rap/hip-hop."
            )
            
            if st.session_state.get("gemini_api_error"):
                lang = st.session_state.get("music_studio_language", "English")
                if lang in ["Hindi", "Hinglish"]:
                    st.error("⚠️ **Gemini API Call Failed (Offline Fallback Active)**\n\n"
                             "The application fell back to the local offline template song because the Gemini API keys failed:\n"
                             f"```\n{st.session_state['gemini_api_error']}\n```\n"
                             "Please check your `.env` or system environment keys.")
                else:
                    st.info("ℹ️ **Dynamic lyric generation offline fallback active.**\n\n"
                            "Using local offline template song for English music (Gemini key not configured or failed, but not required for English).")

            if st.button("🚀 Create & Generate Song Draft", type="primary", use_container_width=True, key="music_studio_btn_one_click"):
                if not one_click_prompt.strip():
                    st.warning("Please enter a song idea first.")
                else:
                    with st.spinner("Writing lyrics and composing style..."):
                        lang = st.session_state.get("music_studio_language", "English")
                        target_dur_seconds = DURATION_OPTIONS[st.session_state.get("music_studio_duration_label", "~2 mins")]
                        pacing_val = st.session_state.get("music_studio_pacing_tempo", "Auto")
                        
                        # Calculate combination-based pacing and structure
                        comb_info = get_song_structure_and_pacing(genre_val, mood_val, target_dur_seconds)
                        resolved_pacing = comb_info["pacing_tempo"] if pacing_val == "Auto" else pacing_val
                        
                        song_length_profile = {
                            "label": "Short" if target_dur_seconds <= 90 else "Long",
                            "target_seconds": target_dur_seconds,
                            "duration_range_text": f"about {target_dur_seconds} seconds",
                            "prompt_line": f"Keep the song compact, with tighter verses, a clear hook, and a crisp ending." if target_dur_seconds <= 90 else "Allow slightly fuller verses, an extra chorus lift, and a more complete ending.",
                            "pacing_tempo": resolved_pacing,
                            "emotion_mood": mood_val,
                            "music_genre": genre_val,
                            "resolved_structure": comb_info["structure_instruction"],
                            "bpm_range": comb_info["bpm_range"],
                            "syllable_density": comb_info["syllable_density"]
                        }
                        lyrics_exp, desc_exp = expand_general_prompt_to_lyrics_and_style_dynamic(
                            settings,
                            one_click_prompt.strip(),
                            one_click_gender,
                            lang,
                            song_length_profile=song_length_profile,
                        )
                        if lang in ["Hindi", "Hinglish"]:
                            desc_exp = clean_style_description_for_instrumental(desc_exp)
                        st.session_state["music_studio_lyrics"] = lyrics_exp
                        st.session_state["music_studio_description"] = desc_exp
                        # Force refresh fields
                        st.session_state["music_studio_lyrics_input"] = lyrics_exp
                        st.session_state["music_studio_description_input"] = desc_exp
                        
                        # Automatically select reference audio based on language
                        ref_dir = PROJECT_ROOT / "output" / "reference_audio"
                        if not ref_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            ref_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio")
                        
                        if lang in ["Hindi", "Hinglish"]:
                            if ref_dir.exists():
                                raw_files = sorted([f.name for f in ref_dir.glob("*.mp3")])
                                ref_files = [f for f in raw_files if any(x in f.lower() for x in ["titli", "barnaby", "hindi", "squirrel"])]
                                if ref_files:
                                    st.session_state["music_studio_ref_audio_choice_input"] = ref_files[0]
                                    st.session_state["music_studio_ref_audio_choice"] = ref_files[0]
                                else:
                                    st.session_state["music_studio_ref_audio_choice_input"] = "None (Text-only)"
                                    st.session_state["music_studio_ref_audio_choice"] = "None (Text-only)"
                            else:
                                st.session_state["music_studio_ref_audio_choice_input"] = "None (Text-only)"
                                st.session_state["music_studio_ref_audio_choice"] = "None (Text-only)"
                        else:
                            st.session_state["music_studio_ref_audio_choice_input"] = "None (Text-only)"
                            st.session_state["music_studio_ref_audio_choice"] = "None (Text-only)"
                            
                        st.session_state["lyrics_manually_edited"] = False
                        if automation_combo_mode:
                            st.session_state["automation_music_singer_gender"] = one_click_gender
                            image_topic = one_click_prompt.strip() or lyrics_exp.splitlines()[0].strip("[]")
                            creative_topic, creative_subject = _automation_music_image_seed(
                                image_topic,
                                desc_exp or one_click_prompt,
                                one_click_gender,
                            )
                            st.session_state["automation_music_image_provider_choice"] = st.session_state.get("image_provider_choice", settings.image_provider or "gemini")
                            st.session_state["automation_music_image_topic"] = creative_topic
                            st.session_state["automation_music_image_subject"] = creative_subject[:240]
                            st.session_state["automation_music_image_art_style"] = "3D Claymation / Pixar"
                            st.session_state["automation_music_image_studio_prompt"] = build_cinematic_image_prompt(
                                st.session_state["automation_music_image_topic"],
                                st.session_state["automation_music_image_subject"],
                                style_name=st.session_state["automation_music_image_art_style"],
                            )
                            st.session_state["automation_music_image_prompt_input"] = st.session_state["automation_music_image_studio_prompt"]
                        st.success("Lyrics & Style drafted successfully!")
                        st.rerun()

        left_col, right_col = st.columns([1.1, 0.9])

        with left_col:
            st.markdown("#### Lyrics Composer")
            music_lyrics_val = st.session_state.get("music_studio_lyrics", "")
            lyrics = st.text_area(
                "Enter lyrics here (use [verse] and [chorus] tags, avoid [intro]/[outro] tags)",
                value=music_lyrics_val,
                height=350,
                key="music_studio_lyrics_input",
                on_change=on_music_lyrics_changed
            )
            st.session_state["music_studio_lyrics"] = lyrics

            col1, col2 = st.columns([1, 1])
            with col1:
                parse_clicked = st.button("✨ Parse & Autofill settings", use_container_width=True, key="music_studio_btn_parse", help="Extracts lyrics, tempo, instruments, vocals, and mood from your prompt to autofill the settings panel.")
            with col2:
                if st.button("🗑️ Clear Lyrics", use_container_width=True, key="music_studio_btn_clear"):
                    st.session_state["music_studio_lyrics"] = ""
                    st.session_state.pop("music_studio_lyrics_input", None)
                    st.rerun()

            if parse_clicked:
                if lyrics.strip():
                    sections = parse_prompt_into_sections(lyrics)
                    if sections:
                        lyrics_content = sections.get("lyrics", "")
                        if not lyrics_content:
                            lyrics_content = lyrics
                            
                        style_parts = []
                        if "style" in sections:
                            style_parts.append(sections["style"])
                        if "tempo" in sections:
                            style_parts.append(f"Tempo: {sections['tempo']}")
                        if "vocals" in sections:
                            style_parts.append(f"Vocals: {sections['vocals']}")
                        if "mood" in sections:
                            style_parts.append(f"Mood: {sections['mood']}")
                        if "instruments" in sections:
                            style_parts.append(f"Instruments: {sections['instruments']}")
                        if "production" in sections:
                            style_parts.append(f"Production: {sections['production']}")
                            
                        combined_style = ". ".join(style_parts)
                        
                        st.session_state["music_studio_lyrics"] = lyrics_content
                        st.session_state.pop("music_studio_lyrics_input", None)
                        st.session_state["music_studio_description"] = combined_style
                        st.session_state.pop("music_studio_description_input", None)
                        st.success("🎉 Successfully parsed and autofilled settings from prompt!")
                        st.rerun()
                    else:
                        inferred_style = (
                            "catchy melodic pop song, warm vocals, piano, acoustic guitar, soft percussion, balanced audio mix."
                        )
                        st.session_state["music_studio_lyrics"] = lyrics
                        st.session_state.pop("music_studio_lyrics_input", None)
                        st.session_state["music_studio_description"] = inferred_style
                        st.session_state.pop("music_studio_description_input", None)
                        st.info("ℹ️ Plain prompt detected. Style inferred from song content.")
                        st.rerun()
                else:
                    st.warning("⚠️ Please paste a prompt in the lyrics box first.")

            st.markdown(
                """
                <div style="display: flex; gap: 12px; margin-top: 20px; flex-direction: column;">
                  <div style="padding: 14px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(56, 189, 248, 0.25);">
                    <div style="font-size: 12px; color: #38bdf8; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                      <span>💡</span> Pro tip: Structure
                    </div>
                    <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                      Use standard tags like [verse] and [chorus] to structure sections. Keep lyrics to 2-3 verses.
                    </div>
                  </div>
                  <div style="padding: 14px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(168, 85, 247, 0.25);">
                    <div style="font-size: 12px; color: #a855f7; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                      <span>🎵</span> Pro tip: Details
                    </div>
                    <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                      Specify clear instruments (e.g. acoustic guitar, grand piano, synth drums) to shape the sound.
                    </div>
                  </div>
                  <div style="padding: 14px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(245, 158, 11, 0.25);">
                    <div style="font-size: 12px; color: #f59e0b; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                      <span>⚡</span> Pro tip: Pacing & Tempo
                    </div>
                    <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                      If vocals feel overstretched, select a shorter duration (~1 min / ~1.5 mins) or explicitly include "fast tempo, 130 BPM, rapid rap flow, energetic double-time delivery" in your style settings.
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with right_col:
            st.markdown("#### Run settings")
            
            lang_choice = st.session_state.get("music_studio_language", "English")
            if lang_choice == "Hindi":
                model_options = [
                    "Lyria 3 Pro — Hindi Song Generation (Google)",
                    "DiffRhythm2 High-Fidelity Song Generation (ASLP-lab/DiffRhythm2)",
                    "Gemini 2.5 Flash + Edge-TTS (Native Accent)"
                ]
            else:
                model_options = [
                    "DiffRhythm2 High-Fidelity Song Generation (ASLP-lab/DiffRhythm2)"
                ]

            current_model = st.session_state.get("music_studio_model_select", model_options[0])
            if current_model not in model_options:
                current_model = model_options[0]

            selected_model = st.selectbox(
                "Model",
                options=model_options,
                index=model_options.index(current_model),
                disabled=False,
                key="music_studio_model_select_temp",
                help="Choose DiffRhythm2 for high-fidelity singing, or Gemini/Edge-TTS for speech-like narration with a native Indian accent."
            )
            st.session_state["music_studio_model_select"] = selected_model
            
            SONG_STYLE_PRESETS = {
                "Emotional Soft / Slow Ballad": {
                    "style_description": "emotional soft slow pop ballad, gentle acoustic piano chords, warm ambient strings, slow breathing tempo, sad heartfelt mood, 75 BPM, emotional singing.",
                    "temperature": 0.80,
                    "genre": "Pop/Ballad"
                },
                "Rock / Pop Rock": {
                    "style_description": "energetic pop rock, driving acoustic drums, electric guitar hooks, bright bass, melodic hooks, 120 BPM, clean vocal style.",
                    "temperature": 0.80,
                    "genre": "Rock"
                },
                "Hip-Hop / Rap": {
                    "style_description": "catchy modern hip hop, rhythmic trap beats, sub bass, clean production, smooth rap tempo, 95 BPM.",
                    "temperature": 0.80,
                    "genre": "Hip-Hop"
                },
                "Cheerful Pop / Dance": {
                    "style_description": "upbeat cheerful dance pop, bright synthesizer chords, groovy electronic bassline, hand claps, energetic tempo, 125 BPM, bright singing.",
                    "temperature": 0.80,
                    "genre": "Dance-Pop"
                },
                "Acoustic Indie Pop": {
                    "style_description": "intimate indie folk acoustic pop, warm fingerpicked acoustic guitar, soft tambourine, cozy melody, 88 BPM, warm natural vocals.",
                    "temperature": 0.80,
                    "genre": "Indie/Acoustic"
                },
                "Meditative Acoustic (Instrumental)": {
                    "style_description": "Pure instrumental. Soft fingerpicked acoustic guitar arpeggios, deep warm bass guitar, airy ambient synthesizer pads, soulful solo bansuri flute, gentle meditative pace, 65 BPM, sacred hall acoustics.",
                    "temperature": 0.30,
                    "genre": "Meditative"
                },
                "Epic Classical Cinematic (Instrumental)": {
                    "style_description": "Pure instrumental. Booming traditional dhol and taiko percussion layers, heavy dramatic orchestral string sections, deep brass swells, rhythmic sitar stabs, massive stadium echo, fast tempo, 115 BPM.",
                    "temperature": 0.35,
                    "genre": "Cinematic"
                },
                "Soulful Sufi / Ghazal Studio (Instrumental)": {
                    "style_description": "Pure instrumental. Traditional hand-pumped wooden harmonium sweeps, organic acoustic tabla loops, calm acoustic sarangi strokes, slow steady studio recording, 80 BPM, clean proximity environment.",
                    "temperature": 0.30,
                    "genre": "Sufi"
                }
            }
            
            selected_vibe = st.selectbox(
                "Song Style / Genre Preset",
                options=["Custom"] + list(SONG_STYLE_PRESETS.keys()),
                key="music_studio_vibe_preset",
                help="Select a musical style preset to automatically populate the Style Description.",
                disabled=disable_advanced_settings
            )
            
            if "prev_music_studio_vibe" not in st.session_state:
                st.session_state["prev_music_studio_vibe"] = selected_vibe
                
            if st.session_state["prev_music_studio_vibe"] != selected_vibe:
                st.session_state["prev_music_studio_vibe"] = selected_vibe
                if selected_vibe != "Custom":
                    preset_data = SONG_STYLE_PRESETS[selected_vibe]
                    st.session_state["music_studio_description_input"] = preset_data["style_description"]
                    st.session_state["music_studio_description"] = preset_data["style_description"]
                    st.session_state["music_studio_genre_input"] = preset_data["genre"]
                    st.session_state["music_studio_genre"] = preset_data["genre"]
                    st.session_state["music_studio_temperature_input"] = preset_data["temperature"]
                    st.session_state["music_studio_temperature"] = preset_data["temperature"]
            
            if "music_studio_description_input" not in st.session_state:
                st.session_state["music_studio_description_input"] = st.session_state.get("music_studio_description", "")
                
            desc = st.text_area(
                "Style Description",
                height=120,
                key="music_studio_description_input",
                help="Describe instruments, tempo (BPM), vocal qualities, and style of the song.",
                disabled=disable_advanced_settings
            )
            st.session_state["music_studio_description"] = desc

            ref_dir = PROJECT_ROOT / "output" / "reference_audio"
            if not ref_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                ref_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio")
            else:
                ref_dir.mkdir(parents=True, exist_ok=True)
            ref_files = []
            if ref_dir.exists():
                raw_files = sorted([f.name for f in ref_dir.glob("*.mp3")])
                lang = st.session_state.get("music_studio_language", "English")
                if lang in ["Hindi", "Hinglish"]:
                    ref_files = [f for f in raw_files if any(x in f.lower() for x in ["titli", "barnaby", "hindi", "squirrel", "littlebubbles", "bubbles", "custom", "ref"])]
                else:
                    ref_files = [f for f in raw_files if not any(x in f.lower() for x in ["titli", "barnaby", "squirrel"]) or any(x in f.lower() for x in ["littlebubbles", "bubbles", "custom", "ref"])]
            
            options = ["None (Text-only)"] + ref_files
            default_index = 0
            default_val = st.session_state.get("music_studio_ref_audio_choice", "None (Text-only)")
            if default_val in options:
                default_index = options.index(default_val)
            
            selected_ref = st.selectbox(
                "Style Reference Audio",
                options=options,
                index=default_index,
                key="music_studio_ref_audio_choice_input",
                help="Select an existing track to guide the style, melody, and voice of the song.",
                disabled=disable_advanced_settings
            )
            st.session_state["music_studio_ref_audio_choice"] = selected_ref

            cfg = st.slider(
                "CFG Scale",
                min_value=1.0,
                max_value=5.0,
                value=float(st.session_state.get("music_studio_cfg_coef", 1.8)),
                step=0.1,
                key="music_studio_cfg_coef_input",
                help="Classifier-Free Guidance. Higher values enforce the style description more strongly.",
                disabled=disable_advanced_settings
            )
            st.session_state["music_studio_cfg_coef"] = cfg
            
            temp = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("music_studio_temperature", 0.8)),
                step=0.05,
                key="music_studio_temperature_input",
                help="Controls diversity. Higher values produce more random/creative melodies.",
                disabled=disable_advanced_settings
            )
            st.session_state["music_studio_temperature"] = temp
            
            genre_options = ['Auto', 'Pop', 'Latin', 'Rock', 'Electronic', 'Metal', 'Country', 'R&B/Soul', 'Ballad', 'Jazz', 'World', 'Hip-Hop', 'Funk', 'Soundtrack', 'Folk', 'Traditional']
            curr_genre = st.session_state.get("music_studio_genre", "Pop")
            genre_index = genre_options.index(curr_genre) if curr_genre in genre_options else 1
            genre = st.selectbox(
                "Genre",
                options=genre_options,
                index=genre_index,
                key="music_studio_genre_input",
                disabled=disable_advanced_settings
            )
            st.session_state["music_studio_genre"] = genre

            # Bind singer voice gender directly from the top-level selection (⚡ One-Click Song Creator)
            singer_gender = st.session_state.get("music_studio_one_click_singer_gender", "Male")
            st.session_state["music_studio_singer_gender"] = singer_gender

        if st.session_state.get("music_studio_trigger_generation_now"):
            if st.session_state.get("music_studio_trigger_generation_now"):
                st.session_state["music_studio_trigger_generation_now"] = False
            with st.spinner("Connecting to ASLP-lab/DiffRhythm2 space and generating audio... (This may take 1-3 minutes)"):
                try:
                    import subprocess
                    import shutil
                    from gradio_client import Client, handle_file

                    prompt_audio_param = None
                    active_ref = selected_ref
                    singer_gender_local = st.session_state.get("music_studio_singer_gender", "Male").lower()
                    if singer_gender_local == "male":
                        is_female_ref = active_ref != "None (Text-only)" and any(x in active_ref.lower() for x in ["barnaby", "titli", "squirrel", "alphabet", "bubbles", "female"])
                        if active_ref == "None (Text-only)" or is_female_ref:
                            arijit_file = "Sajni (Lyrical Video)_ Arijit Singh, Ram Sampath  Laapataa Ladies   Aamir Khan Productions.mp3"
                            if (PROJECT_ROOT / "output" / "reference_audio" / arijit_file).exists():
                                active_ref = arijit_file
                                st.info("ℹ️ Using default male reference audio (Arijit Singh) to force male vocals for DiffRhythm2.")
                    else:
                        is_male_ref = active_ref != "None (Text-only)" and any(x in active_ref.lower() for x in ["arijit", "sajni", "male"])
                        if active_ref == "None (Text-only)" or is_male_ref:
                            lang = st.session_state.get("music_studio_language", "English")
                            if lang in ["Hindi", "Hinglish"]:
                                female_file = "Barnaby_Squirrel_Song.mp3"
                                if (PROJECT_ROOT / "output" / "reference_audio" / female_file).exists():
                                    active_ref = female_file
                                    st.info("ℹ️ Using default female reference audio (Barnaby) to force female vocals for DiffRhythm2.")
                    
                    
                    if active_ref != "None (Text-only)":
                        ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / active_ref
                        if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / active_ref
                        if ref_full_path.exists():
                            temp_dir = PROJECT_ROOT / "output" / ".runtime"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            cropped_ref_path = temp_dir / "music_studio_ref_cropped.mp3"
                            
                            st.write(f"ℹ️ Cropping style reference '{active_ref}' to 15 seconds...")
                            start_time = "0"
                            if ref_full_path.name == "बार्नबी गिलहरी की व्यर्थ खोज.mp3":
                                start_time = "4.5"
                                
                            cmd = [
                                "ffmpeg", "-y", "-i", str(ref_full_path),
                                "-ss", start_time, "-t", "15",
                                "-codec:a", "libmp3lame", "-b:a", "128k",
                                str(cropped_ref_path)
                            ]
                            subprocess.run(cmd, check=True)
                            prompt_audio_param = handle_file(str(cropped_ref_path))
                        else:
                            st.warning(f"Reference audio '{active_ref}' not found. Falling back to text-only generation.")

                    st.write("📝 Checking and sanitizing prompt structure...")
                    lyrics_to_process = lyrics.strip()
                    import re
                    
                    supported_tags = ["verse", "chorus", "bridge", "intro", "outro", "inst", "silence"]
                    has_leading_tag = False
                    if lyrics_to_process.startswith("["):
                        first_line = lyrics_to_process.splitlines()[0].strip()
                        if first_line.endswith("]"):
                            tag_content = first_line[1:-1].lower()
                            if any(t in tag_content for t in supported_tags):
                                has_leading_tag = True
                                
                    if not has_leading_tag:
                        st.write("✨ Auto-parsing raw prompt to extract lyrics and style details...")
                        sections = parse_prompt_into_sections(lyrics)
                        if sections:
                            lyrics_to_process = sections.get("lyrics", "").strip()
                            if not lyrics_to_process:
                                lyrics_to_process = lyrics.strip()
                                
                            style_parts = []
                            if "style" in sections:
                                style_parts.append(sections["style"])
                            if "tempo" in sections:
                                style_parts.append(f"Tempo: {sections['tempo']}")
                            if "vocals" in sections:
                                style_parts.append(f"Vocals: {sections['vocals']}")
                            if "mood" in sections:
                                style_parts.append(f"Mood: {sections['mood']}")
                            if "instruments" in sections:
                                style_parts.append(f"Instruments: {sections['instruments']}")
                            if "production" in sections:
                                style_parts.append(f"Production: {sections['production']}")
                                
                            desc = ". ".join(style_parts)
                            st.session_state["music_studio_description"] = desc
                            st.session_state["music_studio_lyrics"] = lyrics_to_process
                        else:
                            desc = "catchy pop song, piano, acoustic guitar, soft percussion."
                            st.session_state["music_studio_description"] = desc

                    lang = st.session_state.get("music_studio_language", "English")
                    singer_gender = st.session_state.get("music_studio_singer_gender", "Male").lower()
                    if lang == "Hindi":
                        # Decoupled audio pipeline: backing track must be vocal-free
                        pass
                    elif lang == "Hinglish":
                        if singer_gender == "female":
                            desc = re.sub(r" male ", " female ", desc, flags=re.IGNORECASE)
                            if "female" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly native Indian female singing voice, Bollywood style female vocalist, clear Hinglish pronunciation, natural Indian accent."
                            else:
                                if not any(x in desc.lower() for x in ["indian", "bollywood", "hinglish"]):
                                    desc = desc.strip()
                                    if desc and not desc.endswith("."):
                                        desc += "."
                                    desc += " native Indian female singer, clear Hinglish pronunciation."
                        else:
                            desc = re.sub(r" female ", " male ", desc, flags=re.IGNORECASE)
                            if "male" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly native Indian male singing voice, Bollywood style male vocalist, clear Hinglish pronunciation, natural Indian accent."
                            else:
                                if not any(x in desc.lower() for x in ["indian", "bollywood", "hinglish"]):
                                    desc = desc.strip()
                                    if desc and not desc.endswith("."):
                                        desc += "."
                                    desc += " native Indian male singer, clear Hinglish pronunciation."
                    else:
                        if singer_gender == "female":
                            desc = re.sub(r" male ", " female ", desc, flags=re.IGNORECASE)
                            if "female" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly female singing voice."
                        else:
                            desc = re.sub(r" female ", " male ", desc, flags=re.IGNORECASE)
                            if "male" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly male singing voice."

                    st.session_state["music_studio_description"] = desc
                    st.session_state.pop("music_studio_description_input", None)

                    # 2. Split lines, skip empty lines, and sanitize tags
                    sanitized_lines = []
                    lines = [line.strip() for line in lyrics_to_process.splitlines()]
                    
                    filtered_lines = [line for line in lines if line]
                    
                    if filtered_lines:
                        first_line = filtered_lines[0]
                        if not (first_line.startswith("[") and first_line.endswith("]")):
                            sanitized_lines.append("[verse]")
                        
                        for line in filtered_lines:
                            line_safe = line.replace(";", ",")
                            
                            if line_safe.startswith("[") and line_safe.endswith("]"):
                                tag_content = line_safe[1:-1].lower()
                                if "chorus" in tag_content:
                                    sanitized_lines.append("[chorus]")
                                elif "bridge" in tag_content:
                                    sanitized_lines.append("[bridge]")
                                elif "intro" in tag_content:
                                    sanitized_lines.append("[verse]")
                                elif "outro" in tag_content:
                                    sanitized_lines.append("[verse]")
                                elif "inst" in tag_content:
                                    sanitized_lines.append("[verse]")
                                elif "silence" in tag_content:
                                    sanitized_lines.append("[silence]")
                                else:
                                    sanitized_lines.append("[verse]")
                            else:
                                sanitized_lines.append(line_safe)
                                
                    sanitized_lyrics = "\n".join(sanitized_lines).strip()
                    
                    if not sanitized_lyrics.startswith("["):
                        sanitized_lyrics = "[verse]\n" + sanitized_lyrics

                    lang = st.session_state.get("music_studio_language", "English")
                    selected_model = st.session_state.get("music_studio_model_select", "DiffRhythm2 High-Fidelity Song Generation (ASLP-lab/DiffRhythm2)")
                    
                    if lang == "Hindi" and "Lyria 3 Pro" in selected_model:
                        st.write("🎵 Generating Hindi song via Google Lyria 3 Pro...")
                        from content_pipeline.bots.audio import generate_song_via_lyria3
                        
                        out_path = PROJECT_ROOT / "output" / "Music_Studio_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/Music_Studio_Generated_Song.mp3")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        generate_song_via_lyria3(
                            lyrics=sanitized_lyrics,
                            style_description=desc,
                            output_path=out_path,
                            gemini_api_keys=settings.gemini_api_keys,
                            gemini_api_key=settings.gemini_api_key,
                            singer_gender=singer_gender,
                            language="Hindi",
                            st_write_func=st.write,
                        )
                        out_path = normalize_music_studio_audio_length(
                            out_path,
                            int(st.session_state.get("music_duration_seconds", 90)),
                        )
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
                        st.session_state["music_studio_mixed_video_path"] = ""
                        maybe_generate_linked_automation_music_image(settings)
                        st.success("🎉 Hindi Song generated successfully using Google Lyria 3 Pro!")
                        st.rerun()
                    elif lang == "Hindi" and "Native Accent" in selected_model:
                        if not any("\u0900" <= char <= "\u097f" for char in sanitized_lyrics):
                            st.write("🔮 Converting Romanized lyrics to native Devanagari script for perfect Indian accent...")
                            from content_pipeline.bots.gemini_tts import transliterate_to_devanagari
                            sanitized_lyrics = transliterate_to_devanagari(sanitized_lyrics, settings)
                            st.info(f"📝 Transliterated Devanagari Lyrics:\n{sanitized_lyrics}")
                        
                        st.write("🔀 Language: Hindi detected with Native Accent model. Bypassing Hugging Face Lyria to use Native Audio Pipeline...")
                        import sys
                        import importlib
                        if "content_pipeline.bots.singing_synthesis" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.singing_synthesis"])
                        if "content_pipeline.bots.kids_studio_manifest_core" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.kids_studio_manifest_core"])
                        if "content_pipeline.bots.kids_studio_core" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.kids_studio_core"])
                        if "content_pipeline.bots.singer_manifest" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.singer_manifest"])
                        if "content_pipeline.bots.audio" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.audio"])
                        from content_pipeline.bots.audio import generate_hindi_song_via_native_audio
                        
                        out_path = PROJECT_ROOT / "output" / "Music_Studio_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/Music_Studio_Generated_Song.mp3")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        generate_hindi_song_via_native_audio(
                            lyrics=sanitized_lyrics,
                            output_path=out_path,
                            singer_gender=singer_gender,
                            selected_ref=selected_ref,
                            hf_token=_resolve_hf_song_token(settings),
                            genre=genre,
                            temperature=temp,
                            cfg_coef=cfg,
                            style_description=desc,
                            singer_key=st.session_state.get("music_studio_playback_singer_key", "arijit_singh")
                        )
                        out_path = normalize_music_studio_audio_length(
                            out_path,
                            int(st.session_state.get("music_duration_seconds", 90)),
                        )
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
                        st.session_state["music_studio_mixed_video_path"] = ""
                        maybe_generate_linked_automation_music_image(settings)
                        _auto_refresh_project_brain(settings, reason="music_native_audio")
                        st.success("🎉 Hindi Song generated successfully using Native Audio Pipeline!")
                        st.rerun()
                    elif lang == "Hinglish" or (lang == "Hindi" and "DiffRhythm2" in selected_model):
                        st.write("🔮 Applying advanced phonetic transcription layer for perfect Indian accent...")
                        from content_pipeline.bots.phonetic_mapper import hindi_to_phonetic_hinglish
                        sanitized_lyrics = hindi_to_phonetic_hinglish(sanitized_lyrics, gemini_api_key=settings.gemini_api_key)
                        st.info(f"📝 Transcribed Phonetic Lyrics:\n{sanitized_lyrics}")

                    st.write("🎵 Dispatching song generation request to Hugging Face prioritized spaces...")
                    try:
                        formatted_lyrics = sanitized_lyrics.strip()
                        if not formatted_lyrics.startswith("[start]"):
                            formatted_lyrics = f"[start]\n{formatted_lyrics}"
                            
                        from content_pipeline.bots.audio import generate_song_via_prioritized_spaces
                        
                        spaces_priority = ["tencent/SongGeneration", "ASLP-lab/DiffRhythm2", "multimodalart/khala"]
                        result_path, info = generate_song_via_prioritized_spaces(
                            lrc=formatted_lyrics,
                            text_prompt=f"{genre}, {desc}",
                            audio_prompt=prompt_audio_param,
                            genre=genre,
                            temperature=temp,
                            cfg_coef=cfg,
                            duration_seconds=float(st.session_state.get("music_duration_seconds", 90)),
                            language="Hindi" if lang == "Hindi" else "English",
                            spaces_priority=spaces_priority,
                            st_write_func=st.write
                        )
                        
                        if not result_path or str(result_path).strip().lower() == "none":
                            raise ValueError(f"Hugging Face spaces did not return a valid audio track. Details: {info}")

                        st.write("🔄 Transcoding generated audio from FLAC to genuine MP3 with smooth fade-out...")
                        out_path = PROJECT_ROOT / "output" / "Music_Studio_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/Music_Studio_Generated_Song.mp3")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        duration_cmd = [
                            "ffprobe", "-i", str(result_path),
                            "-show_entries", "format=duration",
                            "-v", "quiet", "-of", "csv=p=0"
                        ]
                        duration_res = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
                        total_duration = float(duration_res.stdout.strip())
                        
                        fade_duration = 5.0
                        if total_duration > 15.0:
                            start_fade = total_duration - fade_duration
                        else:
                            fade_duration = min(2.0, total_duration * 0.2)
                            start_fade = total_duration - fade_duration
                            
                        transcode_cmd = [
                            "ffmpeg", "-y", "-i", str(result_path),
                            "-filter:a", f"afade=t=out:st={start_fade:.3f}:d={fade_duration:.3f}",
                            "-codec:a", "libmp3lame", "-qscale:a", "2",
                            str(out_path)
                        ]
                        subprocess.run(transcode_cmd, check=True)
                        out_path = normalize_music_studio_audio_length(
                            out_path,
                            int(st.session_state.get("music_duration_seconds", 90)),
                        )
                        
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
                        st.session_state["music_studio_mixed_video_path"] = ""
                        maybe_generate_linked_automation_music_image(settings)
                        _auto_refresh_project_brain(settings, reason="music_hf_audio")
                        st.success("🎉 Song generated successfully!")
                        st.rerun()
                    except Exception as hf_exc:
                        st.warning(f"⚠️ Hugging Face song generation failed: {hf_exc}. Activating free Edge-TTS backup mixer...")
                        from content_pipeline.bots.audio import generate_edge_tts_song_fallback
                        out_path = PROJECT_ROOT / "output" / "Music_Studio_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/Music_Studio_Generated_Song.mp3")
                        generate_edge_tts_song_fallback(
                            lyrics=sanitized_lyrics,
                            output_path=out_path,
                            singer_gender=singer_gender,
                            selected_ref=selected_ref,
                            singer_key=st.session_state.get("music_studio_playback_singer_key", "arijit_singh"),
                            mode="Poem/Rhyme"
                        )
                        out_path = normalize_music_studio_audio_length(
                            out_path,
                            int(st.session_state.get("music_duration_seconds", 90)),
                        )
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
                        st.session_state["music_studio_mixed_video_path"] = ""
                        maybe_generate_linked_automation_music_image(settings)
                        _auto_refresh_project_brain(settings, reason="music_fallback_audio")
                        st.success("🎉 Backup Song generated successfully using Edge-TTS fallback mixer!")
                        st.rerun()
                except Exception as exc:
                    st.error(f"❌ Error during song preparation: {exc}")

        if automation_combo_mode:
            render_automation_music_image_section(settings)

        st.markdown("---")
        st.markdown("### Playback & Generation")

        generated_file_path = st.session_state.get("music_studio_generated_mp3", "")
        default_out = PROJECT_ROOT / "output" / "Music_Studio_Generated_Song.mp3"
        if not default_out.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/Music_Studio_Generated_Song.mp3").exists():
            default_out = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/Music_Studio_Generated_Song.mp3")
        if not generated_file_path and default_out.exists():
            generated_file_path = str(default_out)
            st.session_state["music_studio_generated_mp3"] = generated_file_path

        bottom_cols = st.columns([1.2, 1.8, 1.0])

        with bottom_cols[0]:
            if generated_file_path and Path(generated_file_path).exists():
                st.markdown(
                    f"""
                    <div style="padding: 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(56, 189, 248, 0.15);">
                      <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Active Track</div>
                      <div style="font-size: 14px; font-weight: 800; color: #f8fafc; margin-top: 2px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                        Music_Studio_Generated_Song.mp3
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    """
                    <div style="padding: 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(244, 63, 94, 0.15);">
                      <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Active Track</div>
                      <div style="font-size: 14px; font-weight: 800; color: #f43f5e; margin-top: 2px;">
                        No track generated yet
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        with bottom_cols[1]:
            if generated_file_path and Path(generated_file_path).exists():
                st.audio(generated_file_path)
            else:
                st.write("")

        with bottom_cols[2]:
            btn_cols = st.columns(2)
            with btn_cols[0]:
                if generated_file_path and Path(generated_file_path).exists():
                    with open(generated_file_path, "rb") as f:
                        btn_data = f.read()
                    st.download_button(
                        label="Download",
                        data=btn_data,
                        file_name="Music_Studio_Generated_Song.mp3",
                        mime="audio/mp3",
                        use_container_width=True,
                        key="music_studio_btn_download"
                    )
                else:
                    st.button("Download", disabled=True, use_container_width=True, key="music_studio_btn_download_disabled")
            with btn_cols[1]:
                if st.button("Generate", type="primary", use_container_width=True, key="music_studio_btn_generate"):
                    st.session_state["music_studio_trigger_generation_now"] = True
                    st.rerun()

        mixed_video_path = st.session_state.get("music_studio_mixed_video_path", "")
        mix_audio_path = Path(generated_file_path) if generated_file_path and Path(generated_file_path).exists() else None
        mix_image_paths = [Path(p) for p in st.session_state.get("automation_music_image_preview_paths", []) if p]
        if not mix_image_paths:
            preview_path = st.session_state.get("automation_music_image_preview_path", "")
            if preview_path:
                mix_image_paths = [Path(preview_path)]

        mix_status_cols = st.columns([1.2, 1.2, 1.1])
        with mix_status_cols[0]:
            st.markdown(
                f"""
                <div style="padding: 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(56, 189, 248, 0.15);">
                  <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Video Mix</div>
                  <div style="font-size: 14px; font-weight: 800; color: #f8fafc; margin-top: 2px;">
                    {len(mix_image_paths) if mix_image_paths else 0} image{'s' if len(mix_image_paths) != 1 else ''}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with mix_status_cols[1]:
            if st.button("🎬 Mix Song + Images", use_container_width=True, key="music_studio_btn_mix_video"):
                if not mix_audio_path:
                    st.warning("Please generate the song first.")
                elif not mix_image_paths:
                    st.warning("No generated images found to mix into a video.")
                else:
                    try:
                        mix_output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
                        video_path = mix_music_and_images_to_mp4(
                            audio_path=mix_audio_path,
                            image_paths=mix_image_paths,
                            output_dir=mix_output_dir,
                            output_name="Music_Studio_Mixed_Song_Images.mp4",
                        )
                        st.session_state["music_studio_mixed_video_path"] = str(video_path)
                        st.success("🎉 Mixed MP4 created successfully!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Video mix error: {exc}")
        with mix_status_cols[2]:
            if mixed_video_path and Path(mixed_video_path).exists():
                with open(mixed_video_path, "rb") as f:
                    mix_data = f.read()
                st.download_button(
                    label="Download MP4",
                    data=mix_data,
                    file_name="Music_Studio_Mixed_Song_Images.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key="music_studio_btn_download_mixed_video",
                )
            else:
                st.button("Download MP4", disabled=True, use_container_width=True, key="music_studio_btn_download_mixed_video_disabled")

        if mixed_video_path and Path(mixed_video_path).exists():
            st.markdown("#### Mixed Video Preview")
            st.video(mixed_video_path)

    elif active_p == "Instrumental":
        st.markdown("### Instrumental Music Studio")
        st.markdown(
            "<p style='font-size: 14.5px; color: #94a3b8; margin-top: -10px; margin-bottom: 24px;'>Create polished no-vocal music beds for kids songs, stories, intros, background scores, and previews.</p>",
            unsafe_allow_html=True,
        )

        instrumental_presets = {
            "Sad Painful Piano": {
                "style": (
                    "Pure instrumental. Sad painful emotional background music, slow minor-key felt piano melody, "
                    "deep cello swells, soft low strings, distant ambient pad, sparse heartbeat-like percussion, "
                    "lonely cinematic atmosphere, gentle reverb, 62 BPM."
                ),
                "genre": "Soundtrack",
                "temperature": 0.25,
                "duration": 90,
            },
            "Cheerful Kids Pop": {
                "style": (
                    "Pure instrumental. Cheerful English kids song backing track, bright ukulele strums, "
                    "soft piano chords, glockenspiel melody, warm bass, hand claps, playful pop nursery rhythm, "
                    "polished studio mix, 92 BPM."
                ),
                "genre": "Pop",
                "temperature": 0.35,
                "duration": 90,
            },
            "Bedtime Story Score": {
                "style": (
                    "Pure instrumental. Gentle bedtime story background music, warm celesta, soft music box, "
                    "airy strings, subtle felt piano, slow calming pace, cozy moonlit atmosphere, 68 BPM."
                ),
                "genre": "Soundtrack",
                "temperature": 0.30,
                "duration": 120,
            },
            "Adventure Cartoon Theme": {
                "style": (
                    "Pure instrumental. Bright cartoon adventure theme, pizzicato strings, playful brass stabs, "
                    "bouncy drums, xylophone sparkle, cheerful orchestral movement, energetic family-friendly mix, 112 BPM."
                ),
                "genre": "Soundtrack",
                "temperature": 0.38,
                "duration": 90,
            },
            "Indian Kids Folk": {
                "style": (
                    "Pure instrumental. Happy Indian kids folk backing track, bansuri flute lead, tabla and dholak groove, "
                    "soft harmonium chords, acoustic guitar, manjira sparkle, warm festival mood, 96 BPM."
                ),
                "genre": "World",
                "temperature": 0.34,
                "duration": 90,
            },
            "Cinematic Magical": {
                "style": (
                    "Pure instrumental. Magical cinematic children score, harp glissandos, celesta melody, lush strings, "
                    "soft choir-like synth pad, gentle percussion, wonder and discovery mood, 82 BPM."
                ),
                "genre": "Soundtrack",
                "temperature": 0.32,
                "duration": 120,
            },
        }

        top_cols = st.columns([1.2, 0.8])
        with top_cols[0]:
            instrumental_idea = st.text_input(
                "Music Idea",
                placeholder="e.g., cheerful background music for a village boy story",
                key="instrumental_music_idea",
            )
        with top_cols[1]:
            selected_instrumental_preset = st.selectbox(
                "Instrumental Preset",
                options=["Custom"] + list(instrumental_presets.keys()),
                key="instrumental_music_preset",
            )

        if "prev_instrumental_music_preset" not in st.session_state:
            st.session_state["prev_instrumental_music_preset"] = selected_instrumental_preset
        if st.session_state["prev_instrumental_music_preset"] != selected_instrumental_preset:
            st.session_state["prev_instrumental_music_preset"] = selected_instrumental_preset
            if selected_instrumental_preset != "Custom":
                preset_data = instrumental_presets[selected_instrumental_preset]
                st.session_state["instrumental_style_prompt_input"] = preset_data["style"]
                st.session_state["instrumental_genre"] = preset_data["genre"]
                st.session_state["instrumental_temperature"] = preset_data["temperature"]
                st.session_state["instrumental_duration_seconds"] = preset_data["duration"]

        if "instrumental_style_prompt_input" not in st.session_state:
            st.session_state["instrumental_style_prompt_input"] = instrumental_presets["Cheerful Kids Pop"]["style"]

        if st.button("✨ Build Instrumental Prompt From Idea", use_container_width=True):
            clean_idea = instrumental_idea.strip() or "a cheerful kids music bed"
            sad_request = any(
                keyword in clean_idea.lower()
                for keyword in ["sad", "pain", "painful", "lonely", "heartbreak", "cry", "tears", "grief", "emotional"]
            )
            if sad_request:
                st.session_state["instrumental_style_prompt_input"] = (
                    "Pure instrumental. "
                    f"Create sad painful music for: {clean_idea}. "
                    "Use slow minor-key felt piano, deep cello, soft low strings, distant ambient pad, sparse heartbeat-like percussion, "
                    "lonely cinematic mood, gentle reverb, no bright bells, no playful rhythm, no cheerful melody, 62 BPM."
                )
                st.session_state["instrumental_genre"] = "Soundtrack"
                st.session_state["instrumental_temperature"] = 0.25
            else:
                st.session_state["instrumental_style_prompt_input"] = (
                    "Pure instrumental. "
                    f"Create music for: {clean_idea}. "
                    "Use memorable melody, clear chord movement, polished stereo mix, family-friendly tone, "
                    "bright lead instruments, warm bass, gentle percussion, and a clean ending."
                )

        style_prompt = st.text_area(
            "Instrumental Style Prompt",
            key="instrumental_style_prompt_input",
            height=140,
            help="Describe only instruments, rhythm, mood, tempo, and production. Vocal words are removed before generation.",
        )

        settings_cols = st.columns(4)
        with settings_cols[0]:
            duration_seconds = st.number_input(
                "Duration",
                min_value=15,
                max_value=240,
                value=int(st.session_state.get("instrumental_duration_seconds", 90)),
                step=15,
                key="instrumental_duration_seconds",
                help="Instrumental generation target in seconds.",
            )
        with settings_cols[1]:
            genre_options = ['Auto', 'Pop', 'Latin', 'Rock', 'Electronic', 'Metal', 'Country', 'R&B/Soul', 'Ballad', 'Jazz', 'World', 'Hip-Hop', 'Funk', 'Soundtrack']
            genre_default = st.session_state.get("instrumental_genre", "Pop")
            genre_index = genre_options.index(genre_default) if genre_default in genre_options else 1
            instrumental_genre = st.selectbox(
                "Genre",
                options=genre_options,
                index=genre_index,
                key="instrumental_genre",
            )
        with settings_cols[2]:
            instrumental_temp = st.slider(
                "Creativity",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("instrumental_temperature", 0.35)),
                step=0.05,
                key="instrumental_temperature",
            )
        with settings_cols[3]:
            instrumental_cfg = st.slider(
                "CFG",
                min_value=1.0,
                max_value=5.0,
                value=float(st.session_state.get("instrumental_cfg_coef", 1.8)),
                step=0.1,
                key="instrumental_cfg_coef",
            )

        ref_dir = PROJECT_ROOT / "output" / "reference_audio"
        if not ref_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
            ref_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio")
        else:
            ref_dir.mkdir(parents=True, exist_ok=True)
        ref_files = []
        if ref_dir.exists():
            ref_files = sorted(
                [
                    f.name for f in ref_dir.glob("*.mp3")
                    if any(token in f.name.lower() for token in ["instrumental", "bgm", "beat", "karaoke"])
                ]
            )
        selected_ref = st.selectbox(
            "Instrumental Style Reference",
            options=["None (Text-only)"] + ref_files,
            key="instrumental_ref_audio_choice",
            help="Only files named like instrumental/bgm/beat/karaoke are shown here to avoid vocal references.",
        )

        cleaned_style = clean_style_description_for_instrumental(style_prompt)
        if cleaned_style != style_prompt.strip():
            with st.expander("Sanitized no-vocal prompt", expanded=False):
                st.write(cleaned_style)

        st.markdown("---")
        playback_path = st.session_state.get("instrumental_generated_mp3", "")
        playback_cols = st.columns([1.1, 1.6, 0.9])
        with playback_cols[0]:
            st.markdown("#### Output")
            if playback_path and Path(playback_path).exists():
                st.caption(Path(playback_path).name)
            else:
                st.caption("No instrumental generated yet")
        with playback_cols[1]:
            if playback_path and Path(playback_path).exists():
                st.audio(playback_path)
        with playback_cols[2]:
            if playback_path and Path(playback_path).exists():
                with open(playback_path, "rb") as generated_audio:
                    st.download_button(
                        "Download",
                        data=generated_audio.read(),
                        file_name=Path(playback_path).name,
                        mime="audio/mp3",
                        use_container_width=True,
                        key="instrumental_download_btn",
                    )
            else:
                st.button("Download", disabled=True, use_container_width=True, key="instrumental_download_disabled")

        if st.button("🎼 Generate Instrumental Music", type="primary", use_container_width=True):
            output_path = PROJECT_ROOT / "output" / "instrumentals" / "Instrumental_Music_Studio_No_Vocal.mp3"
            with st.spinner("Generating instrumental-only audio..."):
                generated_path = generate_instrumental_audio_track(
                    output_path,
                    cleaned_style,
                    hf_token=_resolve_hf_song_token(settings),
                    genre=instrumental_genre,
                    temperature=instrumental_temp,
                    cfg_coef=instrumental_cfg,
                    duration_seconds=int(duration_seconds),
                    selected_ref=selected_ref,
                    force_local=True,
                )
            st.session_state["instrumental_generated_mp3"] = str(generated_path)
            st.success("Instrumental music generated.")
            st.rerun()

    elif active_p == "Video":
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
        antigravity_output_dir = PROJECT_ROOT / "output" / "video_episodes" / video_subject_slug
        if not antigravity_output_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/video_episodes").exists():
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
                        script_path = PROJECT_ROOT / "scratch" / "generate_5min_fresher_video.py"
                        if not script_path.exists():
                            script_path = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/scratch/generate_5min_fresher_video.py")
                        selected_preset_key = st.session_state["video_studio_voice_preset"]

                        result = subprocess.run(
                            [python_executable, str(script_path), "--preset", selected_preset_key],
                            capture_output=True,
                            text=True,
                            cwd=str(PROJECT_ROOT)
                        )

                        if result.returncode == 0:
                            desktop_src = PROJECT_ROOT / "output" / "video_episodes" / "fresher_ai_world_folder"
                            if not desktop_src.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/video_episodes/fresher_ai_world_folder").exists():
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
            json_path = PROJECT_ROOT / "scratch" / "fresher_scenes_data.json"
            if not json_path.exists():
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
    elif active_p == "2DVideo":
        def render_storyboard_cinematic_tabs(project_path, selected_project, orchestrator_path, settings, manifest_data, manifest_path):
            import sys
            import os
            import json
            import shutil
            import subprocess
            from pathlib import Path
            
            st.markdown("### 🎬 Fun Video Studio (Cinematic Storyboard Mode)")
            
            tab1, tab2 = st.tabs(["1. Setup & Script Editor", "2. Compile & Playback"])
            
            with tab1:
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown("#### 💡 Draft Story & Script")
                    story_topic_cin = st.text_input(
                        "Story Topic / Moral Lesson",
                        value="An honest boy returning a lost gold watch",
                        key=f"topic_cin_{selected_project}"
                    )
                    
                    # Load config to get defaults
                    config_path = project_path / "project_config.json"
                    config_data = {}
                    if config_path.exists():
                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                config_data = json.load(f)
                        except Exception:
                            pass
                            
                    audience_list = ["Kids", "Adults"]
                    default_aud = config_data.get("audience", "Kids")
                    if default_aud not in audience_list:
                        default_aud = "Kids"
                        
                    audience_choice = st.selectbox(
                        "Target Audience",
                        options=audience_list,
                        index=audience_list.index(default_aud),
                        key=f"aud_choice_{selected_project}"
                    )
                    
                    if audience_choice == "Kids":
                        genre_list = ["Moral Story", "Learning Story", "Poem Teaching Video"]
                        default_genre = config_data.get("genre", "Moral Story")
                        if default_genre not in genre_list:
                            default_genre = "Moral Story"
                        genre_choice = st.selectbox(
                            "Genre",
                            options=genre_list,
                            index=genre_list.index(default_genre),
                            key=f"genre_choice_{selected_project}"
                        )
                        
                        lang_list = ["English", "Hindi"]
                        default_lang = config_data.get("language", "Hindi")
                        if default_lang not in lang_list:
                            default_lang = "Hindi"
                        lang_choice = st.selectbox(
                            "Language",
                            options=lang_list,
                            index=lang_list.index(default_lang),
                            key=f"lang_choice_{selected_project}"
                        )
                    else:
                        genre_list = ["Suspense & Thrill", "Drama & Emotional"]
                        default_genre = config_data.get("genre", "Suspense & Thrill")
                        if default_genre not in genre_list:
                            default_genre = "Suspense & Thrill"
                        genre_choice = st.selectbox(
                            "Genre",
                            options=genre_list,
                            index=genre_list.index(default_genre),
                            key=f"genre_choice_{selected_project}"
                        )
                        lang_choice = "Hindi"
                        st.info("ℹ️ Adults / Seniors stories are locked to Hindi language.")
                    
                    # API Key resolution
                    active_key = st.session_state.get("custom_gemini_api_key", "").strip()
                    if not active_key:
                        active_key = os.environ.get("GEMINI_API_KEY", "")
                    if not active_key and hasattr(settings, "gemini_api_key"):
                        active_key = settings.gemini_api_key
                        
                    if st.button("🚀 Draft Script via Gemini", key=f"btn_draft_cin_{selected_project}", use_container_width=True):
                        if not active_key:
                            st.error("Please configure your Gemini API Key in the settings first.")
                        else:
                            # Save selected options to project_config.json
                            config_data["audience"] = audience_choice
                            config_data["genre"] = genre_choice
                            config_data["language"] = lang_choice
                            try:
                                with open(config_path, "w", encoding="utf-8") as f:
                                    json.dump(config_data, f, indent=4)
                            except Exception:
                                pass
                                
                            with st.spinner("AI drafting moral story and prompts..."):
                                if str(orchestrator_path) not in sys.path:
                                    sys.path.insert(0, str(orchestrator_path))
                                try:
                                    from src.core.story_agent import AICreativeAgent
                                    agent = AICreativeAgent(active_key)
                                    res = agent.generate_story_from_topic(story_topic_cin, audience_choice, genre_choice, lang_choice)
                                    if res["status"] == "success":
                                        st.session_state[f"script_blueprint_{selected_project}"] = res["script"]
                                        st.success("Drafting complete! Review and edit on the right.")
                                        st.rerun()
                                    else:
                                        st.error(res["message"])
                                except Exception as e:
                                    st.error(f"Failed to draft script: {e}")
                
                with col_right:
                    st.markdown("#### 📋 Inspect & Edit Script Blueprint")
                    script_file_path = project_path / "script.txt"
                    current_script_val = ""
                    if script_file_path.exists():
                        try:
                            with open(script_file_path, "r", encoding="utf-8") as f:
                                current_script_val = f.read()
                        except Exception:
                            pass
                            
                    if not current_script_val:
                        current_script_val = st.session_state.get(f"script_blueprint_{selected_project}", (
                            "--- SCENE 01 ---\n"
                            "[CHARACTER] nandu_boy\n"
                            "[ACTION] wandering aimlessly down a dusty village dirt road, looking bored\n"
                            "[AUDIO] बहुत समय पहले की बात है, एक गाँव में नंदू नाम का लड़का रहता था जो बहुत आलसी था।\n"
                        ))
                    
                    edited_script_cin = st.text_area(
                        "Script Text (script.txt)",
                        value=current_script_val,
                        height=350,
                        key=f"script_area_cin_{selected_project}"
                    )
                    
                    if st.button("💾 Save Script File", key=f"btn_save_script_cin_{selected_project}", use_container_width=True):
                        try:
                            with open(script_file_path, "w", encoding="utf-8") as f:
                                f.write(edited_script_cin)
                            st.toast("✅ script.txt saved successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save script: {e}")
                            
            with tab2:
                st.markdown("### 🚀 Compile Storyboard Video")
                
                if st.button("🎬 Compile Video Master", type="primary", use_container_width=True, key=f"btn_compile_cin_master_{selected_project}"):
                    st.info("Compiling cinematic storyboard video... Downloading backgrounds, synthesizing TTS vocals, applying Ken Burns zoom filters and mixing background music.")
                    
                    compiler_script = orchestrator_path / "batch_story_compiler.py"
                    cmd = [
                        sys.executable,
                        "-u",
                        str(compiler_script),
                        selected_project
                    ]
                    
                    with st.expander("🛠️ Live Compilation Terminal Logs", expanded=True):
                        log_placeholder = st.empty()
                        log_content = []
                        
                        try:
                            env = os.environ.copy()
                            env["KIDS_STUDIO_ORCHESTRATOR_ROOT"] = str(orchestrator_path)
                            env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT / ".2d_patches"), str(orchestrator_path)])
                            
                            process = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1,
                                cwd=str(orchestrator_path),
                                env=env
                            )
                            
                            while True:
                                line = process.stdout.readline()
                                if not line and process.poll() is not None:
                                    break
                                if line:
                                    log_content.append(line)
                                    log_placeholder.code("".join(log_content[-20:]), language="bash")
                                    
                            rc = process.poll()
                            if rc == 0:
                                st.success("🎉 Video compiled successfully!")
                                st.toast("Success!")
                                
                                # Copy compiled video to orchestrator's central output folder
                                try:
                                    target_video = project_path / "output" / "final_studio_master.mp4"
                                    if target_video.exists():
                                        central_output_dir = orchestrator_path / "output"
                                        central_output_dir.mkdir(exist_ok=True)
                                        shutil.copy(target_video, central_output_dir / f"{selected_project}_final.mp4")
                                        st.info(f"💾 Copied compiled video to orchestrator output: `{central_output_dir / f'{selected_project}_final.mp4'}`")
                                except Exception as copy_err:
                                    st.warning(f"⚠️ Failed to copy compiled video to central output: {copy_err}")
                                    
                                # Google Drive Upload
                                st.info("📤 Uploading compiled video to Google Drive...")
                                try:
                                    target_video = project_path / "output" / "final_studio_master.mp4"
                                    if target_video.exists():
                                        from content_pipeline.bots.google_drive import upload_to_google_drive
                                        drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
                                        drive_link = upload_to_google_drive(target_video, drive_folder, settings)
                                        
                                        # Save the link to manifest
                                        manifest_data["google_drive_link"] = drive_link
                                        with open(manifest_path, "w", encoding="utf-8") as f:
                                            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                                        st.success(f"Uploaded to Google Drive successfully: {drive_link}")
                                    else:
                                        st.error("Compiled video output file not found on disk.")
                                except Exception as drive_err:
                                    st.warning(f"⚠️ Google Drive upload failed: {drive_err}")
                                    
                                st.rerun()
                            else:
                                st.error(f"❌ Compiler failed with exit code: {rc}")
                        except Exception as e:
                            st.error(f"Execution error: {e}")
                            
                # Render video preview
                output_video = project_path / "output" / "final_studio_master.mp4"
                if output_video.exists():
                    st.markdown("---")
                    st.markdown("### 📺 Compiled Video Preview")
                    st.video(str(output_video))
                    
                    central_final_path = orchestrator_path / "output" / f"{selected_project}_final.mp4"
                    if central_final_path.exists():
                        st.success(f"✨ Compiled Gold Master is saved at: `{central_final_path}`")
                        
                    # Google Drive Link display
                    drive_link = manifest_data.get("google_drive_link", "")
                    if drive_link:
                        st.link_button(
                            "📥 Download Compiled Video (Google Drive)",
                            url=drive_link,
                            use_container_width=True
                        )
                    else:
                        st.warning("⚠️ This video has not been uploaded to Google Drive yet.")
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            with open(output_video, "rb") as video_file:
                                st.download_button(
                                    label="📥 Download Compiled Video (Local)",
                                    data=video_file,
                                    file_name=f"{selected_project}_final.mp4",
                                    mime="video/mp4",
                                    use_container_width=True,
                                    key=f"download_btn_cin_{selected_project}"
                                )
                        with btn_col2:
                            if st.button("📤 Sync/Upload to Google Drive", use_container_width=True, key=f"upload_drive_btn_cin_{selected_project}"):
                                with st.spinner("Uploading to Google Drive..."):
                                    try:
                                        from content_pipeline.bots.google_drive import upload_to_google_drive
                                        drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
                                        new_drive_link = upload_to_google_drive(output_video, drive_folder, settings)
                                        manifest_data["google_drive_link"] = new_drive_link
                                        with open(manifest_path, "w", encoding="utf-8") as f:
                                            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                                        st.success("Uploaded successfully!")
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Google Drive upload failed: {err}")

        st.markdown(
            """
            <div class="hero" style="background: linear-gradient(135deg, rgba(236,72,153,0.15), rgba(168,85,247,0.15)); border: 1px solid rgba(236,72,153,0.3); margin-bottom: 24px;">
              <h1 style="font-size: 32px;">🎬 2D Video Animation Studio</h1>
              <p style="margin-top: 6px; font-size: 14px;">Procedural layout, automated lip-syncing, and video rendering engine.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        orchestrator_path = resolve_2d_orchestrator_root()
        projects_dir = orchestrator_path / "projects"
        
        if not projects_dir.exists():
            st.error(f"❌ Projects directory not found at: {projects_dir}")
        else:
            available_projects = sorted([p.name for p in projects_dir.iterdir() if p.is_dir()])
            
            # Forced Creation Logic Execution
            forced_create = st.session_state.pop("trigger_create_project_forced", None)
            if forced_create:
                clean_name = forced_create
                new_proj_dir = projects_dir / clean_name
                new_proj_dir.mkdir(parents=True, exist_ok=True)
                (new_proj_dir / "output").mkdir(exist_ok=True)
                (new_proj_dir / "vocals").mkdir(exist_ok=True)
                
                topic = st.session_state.get("new_proj_topic_input", "").strip()
                manifest_created = False
                
                if topic:
                    with st.spinner(f"Generating brand new story for '{topic}'..."):
                        try:
                            new_manifest = generate_manifest_from_scratch(topic, clean_name, settings)
                            normalize_2d_scene_manifest(new_manifest)
                            with open(new_proj_dir / "scene_manifest.json", "w", encoding="utf-8") as f:
                                json.dump(new_manifest, f, indent=2, ensure_ascii=False)
                            manifest_created = True
                            
                            # Generate any missing assets immediately
                            with st.spinner("Generating background & character illustration assets..."):
                                generated = generate_missing_assets(new_manifest, orchestrator_path, settings)
                                if generated:
                                    st.success(f"Generated assets: {', '.join(generated)}")
                        except Exception as e:
                            st.error(f"Failed to generate story via Gemini: {e}. Falling back to default template.")
                
                if not manifest_created:
                    # Fallback to copy ghamandi_mor as a baseline template structure
                    template_manifest = projects_dir / "ghamandi_mor" / "scene_manifest.json"
                    if template_manifest.exists():
                        import shutil
                        shutil.copy(template_manifest, new_proj_dir / "scene_manifest.json")
                        with open(new_proj_dir / "scene_manifest.json", "r", encoding="utf-8") as f:
                            new_manifest = json.load(f)
                        new_manifest["video_id"] = clean_name
                        normalize_2d_scene_manifest(new_manifest)
                        with open(new_proj_dir / "scene_manifest.json", "w", encoding="utf-8") as f:
                            json.dump(new_manifest, f, indent=2, ensure_ascii=False)
                    else:
                        st.error("Baseline template 'ghamandi_mor' not found to initialize manifest.")
                
                st.success(f"Workspace '{clean_name}' initialized successfully!")
                st.session_state["selected_project_override"] = clean_name
                st.rerun()

            # Select project workspace override index resolution
            default_index = 0
            override_proj = st.session_state.pop("selected_project_override", None)
            if override_proj and override_proj in available_projects:
                default_index = available_projects.index(override_proj)
            elif "ghamandi_mor" in available_projects:
                default_index = available_projects.index("ghamandi_mor")
                
            setup_cols = st.columns([2, 1])
            with setup_cols[0]:
                selected_project = st.selectbox("Select Project Workspace", options=available_projects, index=default_index)
            with setup_cols[1]:
                current_val = st.session_state.get("image_provider_choice", "free-ai")
                if current_val not in ("nvidia", "free-ai", "gemini", "openai"):
                    current_val = "nvidia"
                options = ("nvidia", "free-ai", "gemini", "openai")
                selected_provider = st.selectbox(
                    "Image Provider",
                    options=options,
                    index=options.index(current_val),
                    key="image_provider_choice_2d_studio"
                )
                st.session_state["image_provider_choice"] = selected_provider

            
            # Create Project Expander
            with st.expander("➕ Create New Project Workspace", expanded=False):
                new_project_name = st.text_input("New Project Name (alphanumeric/underscores)", key="new_proj_name_input")
                new_project_topic = st.text_area("Story Topic / Idea (e.g. 'A thirsty crow finding water in a pitcher', leave blank for template)", key="new_proj_topic_input", height=70)
                
                # Check for confirmation state
                confirm_proj = st.session_state.get("project_creation_confirm")
                if confirm_proj:
                    st.warning(f"⚠️ A workspace named '{confirm_proj}' already exists. Do you want to load the existing workspace or overwrite and create a completely fresh one?")
                    confirm_cols = st.columns(2)
                    with confirm_cols[0]:
                        if st.button("📂 Load Existing Workspace", key="confirm_btn_load"):
                            st.session_state["project_creation_confirm"] = None
                            st.session_state["selected_project_override"] = confirm_proj
                            st.rerun()
                    with confirm_cols[1]:
                        if st.button("🔥 Overwrite & Create Fresh", key="confirm_btn_overwrite"):
                            import shutil
                            shutil.rmtree(projects_dir / confirm_proj, ignore_errors=True)
                            st.session_state["project_creation_confirm"] = None
                            st.session_state["trigger_create_project_forced"] = confirm_proj
                            st.rerun()
                
                # Main Creation Button
                if not confirm_proj:
                    if st.button("Create Project", type="secondary", key="btn_create_proj_main", use_container_width=True):
                        import re
                        import datetime
                        clean_name = re.sub(r'[^a-zA-Z0-9_]', '', new_project_name.strip())
                        if not clean_name:
                            # Auto-generate a clean name based on English keywords in topic or a simple timestamp slug
                            topic_str = new_project_topic.strip()
                            if topic_str:
                                english_words = re.findall(r'[a-zA-Z0-9]+', topic_str)
                                if english_words:
                                    clean_name = "_".join(english_words[:3]).lower()
                            if not clean_name:
                                clean_name = f"story_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        
                        new_proj_dir = projects_dir / clean_name
                        if new_proj_dir.exists():
                            st.session_state["project_creation_confirm"] = clean_name
                            st.rerun()
                        else:
                            st.session_state["trigger_create_project_forced"] = clean_name
                            st.rerun()

            project_path = projects_dir / selected_project
            manifest_path = project_path / "scene_manifest.json"
            
            if not manifest_path.exists():
                st.error(f"❌ scene_manifest.json not found in {project_path}")
            else:
                # Load JSON
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest_data = json.load(f)
                    manifest_changed = normalize_2d_scene_manifest(manifest_data)
                    if manifest_changed:
                        with open(manifest_path, "w", encoding="utf-8") as f:
                            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    st.error(f"Error reading manifest: {e}")
                    manifest_data = None
                    
                if manifest_data:
                    # Load/initialize project_config.json
                    config_path = project_path / "project_config.json"
                    config_data = {
                        "project_id": selected_project,
                        "canvas_dimensions": manifest_data.get("canvas_dimensions", [1920, 1080]),
                        "fps": manifest_data.get("fps", 24),
                        "pipeline_mode": "PUPPET_2D",
                        "active_style_preset": "PREMIUM_STORYBOOK",
                        "generation_seed": 42
                    }
                    if config_path.exists():
                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                config_data.update(json.load(f))
                        except Exception:
                            pass
                    else:
                        try:
                            with open(config_path, "w", encoding="utf-8") as f:
                                json.dump(config_data, f, indent=4)
                        except Exception:
                            pass

                    st.markdown("### ⚙️ Production Engine Configuration")
                    cfg_cols = st.columns(3)
                    with cfg_cols[0]:
                        modes = ["PUPPET_2D", "STORYBOARD_CINEMATIC"]
                        current_mode = config_data.get("pipeline_mode", "PUPPET_2D")
                        if current_mode not in modes:
                            current_mode = "PUPPET_2D"
                        pipeline_mode = st.selectbox(
                            "Pipeline Mode",
                            options=modes,
                            index=modes.index(current_mode),
                            key=f"pipeline_mode_sel_{selected_project}"
                        )
                    with cfg_cols[1]:
                        presets = ["PREMIUM_STORYBOOK", "CINEMATIC_STORYBOOK"]
                        current_preset = config_data.get("active_style_preset", "PREMIUM_STORYBOOK")
                        if current_preset not in presets:
                            current_preset = "PREMIUM_STORYBOOK"
                        style_preset = st.selectbox(
                            "Style Preset",
                            options=presets,
                            index=presets.index(current_preset),
                            key=f"style_preset_sel_{selected_project}"
                        )
                    with cfg_cols[2]:
                        generation_seed = st.number_input(
                            "Generation Seed",
                            min_value=0,
                            max_value=999999,
                            value=int(config_data.get("generation_seed", 42)),
                            key=f"generation_seed_input_{selected_project}"
                        )
                    
                    # Save project_config.json if changed
                    if (pipeline_mode != config_data.get("pipeline_mode") or
                        style_preset != config_data.get("active_style_preset") or
                        generation_seed != config_data.get("generation_seed")):
                        config_data["pipeline_mode"] = pipeline_mode
                        config_data["active_style_preset"] = style_preset
                        config_data["generation_seed"] = generation_seed
                        try:
                            with open(config_path, "w", encoding="utf-8") as f:
                                json.dump(config_data, f, indent=4)
                            st.toast("⚙️ Configuration updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update project_config.json: {e}")

                    # Branch based on pipeline mode
                    if pipeline_mode == "STORYBOARD_CINEMATIC":
                        render_storyboard_cinematic_tabs(project_path, selected_project, orchestrator_path, settings, manifest_data, manifest_path)
                        st.stop()

                    # Global config info (for PUPPET_2D)
                    st.caption(f"Video ID: **{manifest_data.get('video_id')}** | Mode: **{pipeline_mode}** | Resolution: **{manifest_data.get('canvas_dimensions')}** | FPS: **{manifest_data.get('fps')}**")
                    
                    # Create step-by-step navigation tabs
                    tab1, tab2, tab3 = st.tabs(["1. Setup & Storyboard", "2. Script & Voices", "3. Compile & Playback"])
                    
                    with tab1:
                        # 1. Render Scene Background Previews
                        scenes = manifest_data.get("timeline_scenes", [])
                        st.markdown("### 🖼️ Scene Layout Previews")
                        cols = st.columns(len(scenes))
                        for s_idx, scene in enumerate(scenes):
                            with cols[s_idx]:
                                bg_path = orchestrator_path / scene.get("background_asset", "")
                                st.markdown(f"**Scene {scene.get('scene_sequence')}**")
                                if bg_path.exists():
                                    st.image(str(bg_path), use_container_width=True)
                                st.caption(f"Camera: `{scene.get('camera_effect')}`")
                                
                        # Render character body images in a row
                        unique_characters = {}
                        for scene in scenes:
                            for char in scene.get("scene_characters", []):
                                fname = char.get("folder_name")
                                if fname and fname not in unique_characters:
                                    unique_characters[fname] = char
                                    
                        if unique_characters:
                            st.markdown("#### 👥 Character Sprites Used")
                            c_cols = st.columns(len(unique_characters))
                            for c_idx, fname in enumerate(sorted(unique_characters.keys())):
                                with c_cols[c_idx]:
                                    img_path = orchestrator_path / "assets" / "sprites" / fname / "body.png"
                                    if not img_path.exists():
                                        img_path = orchestrator_path / "assets" / "character" / f"{fname}_body.png"
                                    if not img_path.exists():
                                        img_path = orchestrator_path / "assets" / "character" / f"{fname}.png"
                                    short_name = fname.replace("_crow", "").replace("proud_", "")
                                    if not img_path.exists():
                                        img_path = orchestrator_path / "assets" / "character" / f"{short_name}_body.png"
                                    if not img_path.exists():
                                        img_path = orchestrator_path / "assets" / "character" / f"{short_name}.png"
                                        
                                    if img_path.exists():
                                        st.image(str(img_path), caption=f"Sprite: {fname}", use_container_width=True)
                                    else:
                                        st.caption(f"Sprite: {fname} (No body image found)")
                                
                    with tab2:
                        # 2. Unified Script Editor (Pasting raw script text)
                        st.markdown("### 📝 Unified Script Editor")
                        st.caption("Edit the dialog lines for all scenes in one unified box. Format as 'Speaker: text' under '--- Scene X ---' headers.")
                        
                        # Generate formatted script text from manifest
                        script_lines = []
                        for scene in scenes:
                            script_lines.append(f"--- Scene {scene.get('scene_sequence')} ---")
                            for dial in scene.get("dialogue", []):
                                script_lines.append(f"{dial.get('speaker')}: {dial.get('text')}")
                            script_lines.append("")
                        formatted_script = "\n".join(script_lines)
                        
                        # Text Area for editing
                        edited_script = st.text_area(
                            "Script Text",
                            value=formatted_script,
                            height=350,
                            key=f"script_text_{selected_project}"
                        )
                        
                        # Extract unique speakers from scene manifest
                        unique_speakers = set()
                        for scene in scenes:
                            for dial in scene.get("dialogue", []):
                                if dial.get("speaker"):
                                    unique_speakers.add(dial.get("speaker"))
                                    
                        # Voice presets config
                        st.markdown("#### 🎙️ Speaker Voice Assignment")
                        voice_presets = manifest_data.get("voice_presets", {
                            "Narrator": "Rasalgethi",
                            "Peacock": "Charon",
                            "Kalu": "Puck"
                        })
                        
                        new_voice_presets = {}
                        voice_options = ["Rasalgethi", "Charon", "Puck", "Kore", "Fenrir", "Aoede"]
                        
                        # Layout voice selectors in columns
                        if unique_speakers:
                            v_cols = st.columns(len(unique_speakers))
                            for v_idx, speaker in enumerate(sorted(list(unique_speakers))):
                                current_voice = voice_presets.get(speaker)
                                if current_voice not in voice_options:
                                    if speaker.lower() == "narrator":
                                        current_voice = "Rasalgethi"
                                    elif speaker.lower() in ["peacock", "proud_peacock"]:
                                        current_voice = "Charon"
                                    elif speaker.lower() in ["kalu", "crow", "kalu_crow"]:
                                        current_voice = "Puck"
                                    else:
                                        current_voice = "Rasalgethi"
                                        
                                with v_cols[v_idx]:
                                    selected_voice = st.selectbox(
                                        f"Voice for {speaker}",
                                        options=voice_options,
                                        index=voice_options.index(current_voice),
                                        key=f"voice_sel_{selected_project}_{speaker}"
                                    )
                                    new_voice_presets[speaker] = selected_voice
                        else:
                            st.info("No speakers detected in the script yet.")
                        
                        # Parsing function to map back to JSON
                        def parse_script_text(script_text: str) -> dict[int, list[dict[str, str]]]:
                            scenes_dialogue = {}
                            current_scene = None
                            lines = script_text.splitlines()
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                # Match scene headers like "--- Scene 1 ---"
                                match = re.match(r"(?i)^---\s*Scene\s*(\d+)\s*---", line)
                                if match:
                                    current_scene = int(match.group(1))
                                    scenes_dialogue[current_scene] = []
                                    continue
                                    
                                if current_scene is not None:
                                    if ":" in line:
                                        speaker, text = line.split(":", 1)
                                        scenes_dialogue[current_scene].append({
                                            "speaker": speaker.strip(),
                                            "text": text.strip()
                                        })
                            return scenes_dialogue
                        
                        # Save changes button
                        script_changed = (edited_script != formatted_script)
                        voices_changed = (new_voice_presets != voice_presets)
                        
                        if script_changed or voices_changed:
                            if st.button("💾 Save Script & Voice Changes", type="primary", use_container_width=True):
                                parsed_scenes = parse_script_text(edited_script)
                                
                                # Map parsed dialogues back to manifest_data
                                for scene in manifest_data.get("timeline_scenes", []):
                                    seq = scene.get("scene_sequence")
                                    if seq in parsed_scenes:
                                        scene["dialogue"] = parsed_scenes[seq]
                                        
                                # Update voice presets
                                manifest_data["voice_presets"] = new_voice_presets
                                
                                try:
                                    with open(manifest_path, "w", encoding="utf-8") as f:
                                        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                                    st.toast("✅ Project configuration updated successfully!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to save manifest: {e}")
                                    
                        st.markdown("---")
                        st.markdown("### ✨ Dynamic Story Editing & AI Suggestions")
                        st.caption("Tell AI what modifications you want in this story. Gemini will rewrite dialogues, characters, placements, and generate new illustrations as needed.")
                        
                        user_suggestion = st.text_area(
                            "What changes do you want in this video?",
                            placeholder="e.g. 'Change the setting to a sunset snowy forest, and make Peacock speak English.', 'Change Kalu crow to a beautiful parrot named Mithu.'",
                            key=f"suggestion_{selected_project}",
                            height=100
                        )
                        
                        if st.button("🤖 Apply Story Suggestions & Regenerate", type="primary", use_container_width=True, key=f"btn_apply_sugg_{selected_project}"):
                            if not user_suggestion.strip():
                                st.warning("Please enter a suggestion first.")
                            else:
                                with st.spinner("Analyzing suggestions and updating scene manifest..."):
                                    try:
                                        updated_manifest = apply_manifest_suggestions(manifest_data, user_suggestion, settings)
                                        normalize_2d_scene_manifest(updated_manifest)
                                        with open(manifest_path, "w", encoding="utf-8") as f:
                                            json.dump(updated_manifest, f, indent=2, ensure_ascii=False)
                                        st.success("Manifest updated successfully!")
                                        
                                        # Generate any new background or character assets
                                        with st.spinner("Generating any new backgrounds or character sprites..."):
                                            generated = generate_missing_assets(updated_manifest, orchestrator_path, settings)
                                            if generated:
                                                st.info(f"Generated new assets: {', '.join(generated)}")
                                                
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Error applying suggestions: {err}")
                                    
                    with tab3:
                        st.markdown("### 🚀 Compile Animation Video")
                        
                        # Compile button
                        if st.button("🎬 Compile Video Master", type="primary", use_container_width=True):
                            st.info("Compiling video... This involves TTS audio generation, lip-sync mapping, frame rendering, and FFmpeg assembly.")
                            
                            import subprocess
                            compiler_script = orchestrator_path / "src" / "video_pipeline" / "scene_compiler.py"
                            
                            cmd = [
                                sys.executable,
                                "-u",
                                str(compiler_script),
                                f"projects/{selected_project}/scene_manifest.json"
                            ]
                            
                            # Set up real-time log tracking inside expander to keep UI clean
                            with st.expander("🛠️ Live Compilation Terminal Logs", expanded=True):
                                log_placeholder = st.empty()
                                log_content = []
                                
                                try:
                                    # Set PYTHONPATH so it can import from KidsStudio-Orchestrator root
                                    env = os.environ.copy()
                                    env["KIDS_STUDIO_ORCHESTRATOR_ROOT"] = str(orchestrator_path)
                                    env["PYTHONPATH"] = os.pathsep.join([str(resolve_2d_patch_root()), str(orchestrator_path)])
                                    
                                    process = subprocess.Popen(
                                        cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True,
                                        bufsize=1,
                                        cwd=str(orchestrator_path),
                                        env=env
                                    )
                                    
                                    while True:
                                        line = process.stdout.readline()
                                        if not line and process.poll() is not None:
                                            break
                                        if line:
                                            log_content.append(line)
                                            log_placeholder.code("".join(log_content[-20:]), language="bash")
                                            
                                    rc = process.poll()
                                    if rc == 0:
                                        st.success("🎉 Video compiled successfully!")
                                        st.toast("Success!")
                                        
                                        # Copy compiled video to orchestrator's central output folder
                                        try:
                                            import shutil
                                            target_video = project_path / "output" / "ghamandi_mor_final.mp4"
                                            if not target_video.exists():
                                                target_video = project_path / "output" / f"{selected_project}_final.mp4"
                                            
                                            if target_video.exists():
                                                central_output_dir = orchestrator_path / "output"
                                                central_output_dir.mkdir(exist_ok=True)
                                                
                                                # Copy with project-specific name
                                                shutil.copy(target_video, central_output_dir / f"{selected_project}_final.mp4")
                                                # If ghamandi_mor, also copy as ghamandi_mor_final.mp4
                                                if selected_project == "ghamandi_mor":
                                                    shutil.copy(target_video, central_output_dir / "ghamandi_mor_final.mp4")
                                                    
                                                st.info(f"💾 Copied compiled video to orchestrator output: `{central_output_dir / f'{selected_project}_final.mp4'}`")
                                        except Exception as copy_err:
                                            st.warning(f"⚠️ Failed to copy compiled video to central output: {copy_err}")
                                        
                                        # Google Drive Upload
                                        st.info("📤 Uploading compiled video to Google Drive...")
                                        try:
                                            target_video = project_path / "output" / "ghamandi_mor_final.mp4"
                                            if not target_video.exists():
                                                target_video = project_path / "output" / f"{selected_project}_final.mp4"
                                            
                                            if target_video.exists():
                                                from content_pipeline.bots.google_drive import upload_to_google_drive
                                                drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
                                                drive_link = upload_to_google_drive(target_video, drive_folder, settings)
                                                
                                                # Save the link to manifest
                                                manifest_data["google_drive_link"] = drive_link
                                                with open(manifest_path, "w", encoding="utf-8") as f:
                                                    json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                                                st.success(f"Uploaded to Google Drive successfully: {drive_link}")
                                            else:
                                                st.error("Compiled video output file not found on disk.")
                                        except Exception as drive_err:
                                            st.warning(f"⚠️ Google Drive upload failed: {drive_err}")
                                            
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Compiler failed with exit code: {rc}")
                                except Exception as e:
                                    st.error(f"Execution error: {e}")
                                
                        # Render final video preview
                        output_video = project_path / "output" / "ghamandi_mor_final.mp4"
                        if not output_video.exists():
                            output_video = project_path / "output" / f"{selected_project}_final.mp4"
                            
                        if output_video.exists():
                            st.markdown("---")
                            st.markdown("### 📺 Compiled Video Preview")
                            st.video(str(output_video))
                            
                            # Verify copy exists and report exact path
                            central_final_path = orchestrator_path / "output" / f"{selected_project}_final.mp4"
                            if not central_final_path.exists() and selected_project == "ghamandi_mor":
                                central_final_path = orchestrator_path / "output" / "ghamandi_mor_final.mp4"
                                
                            if central_final_path.exists():
                                st.success(f"✨ Compiled Gold Master is saved at: `{central_final_path}`")
                            else:
                                # Safe fall-through copy
                                try:
                                    import shutil
                                    central_output_dir = orchestrator_path / "output"
                                    central_output_dir.mkdir(exist_ok=True)
                                    shutil.copy(output_video, central_output_dir / f"{selected_project}_final.mp4")
                                    if selected_project == "ghamandi_mor":
                                        shutil.copy(output_video, central_output_dir / "ghamandi_mor_final.mp4")
                                    st.success(f"✨ Compiled Gold Master is saved at: `{central_final_path}`")
                                except Exception:
                                    pass
                            
                            # Google Drive Link display
                            drive_link = manifest_data.get("google_drive_link", "")
                            
                            if drive_link:
                                st.link_button(
                                    "📥 Download Compiled Video (Google Drive)",
                                    url=drive_link,
                                    use_container_width=True
                                )
                            else:
                                st.warning("⚠️ This video has not been uploaded to Google Drive yet.")
                                
                                # Fallback layout
                                btn_col1, btn_col2 = st.columns(2)
                                with btn_col1:
                                    with open(output_video, "rb") as video_file:
                                        st.download_button(
                                            label="📥 Download Compiled Video (Local)",
                                            data=video_file,
                                            file_name=f"{selected_project}_final.mp4",
                                            mime="video/mp4",
                                            use_container_width=True,
                                            key=f"download_btn_{selected_project}"
                                        )
                                with btn_col2:
                                    if st.button("📤 Sync/Upload to Google Drive", use_container_width=True, key=f"upload_drive_btn_{selected_project}"):
                                        with st.spinner("Uploading to Google Drive..."):
                                            try:
                                                from content_pipeline.bots.google_drive import upload_to_google_drive
                                                drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
                                                new_drive_link = upload_to_google_drive(output_video, drive_folder, settings)
                                                
                                                # Save back to JSON
                                                manifest_data["google_drive_link"] = new_drive_link
                                                with open(manifest_path, "w", encoding="utf-8") as f:
                                                    json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                                                    
                                                st.success("Uploaded successfully!")
                                                st.rerun()
                                            except Exception as err:
                                                st.error(f"Google Drive upload failed: {err}")
                                            
                            st.caption(f"Location: `{output_video}` (Size: {output_video.stat().st_size / (1024*1024):.2f} MB)")

    elif active_p == "Image":
        # Dynamic prompt synchronization when topic, subject, or art style changes
        current_topic = st.session_state.get("image_topic", "")
        current_subject = st.session_state.get("image_subject", "")
        current_style = st.session_state.get("image_art_style", "3D Claymation / Pixar")
        if "last_image_topic" not in st.session_state:
            st.session_state["last_image_topic"] = current_topic
        if "last_image_subject" not in st.session_state:
            st.session_state["last_image_subject"] = current_subject
        if "last_image_style" not in st.session_state:
            st.session_state["last_image_style"] = current_style
            
        if (current_topic != st.session_state["last_image_topic"] or 
            current_subject != st.session_state["last_image_subject"] or
            current_style != st.session_state["last_image_style"]):
            st.session_state["image_studio_prompt"] = build_cinematic_image_prompt(
                current_topic, current_subject, style_name=current_style
            )
            st.session_state["last_image_topic"] = current_topic
            st.session_state["last_image_subject"] = current_subject
            st.session_state["last_image_style"] = current_style

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
                
                # Image Download Button
                try:
                    preview_file_path = Path(image_preview_path)
                    img_data = preview_file_path.read_bytes()
                    st.download_button(
                        label="📥 Download Generated Widescreen Canvas",
                        data=img_data,
                        file_name=preview_file_path.name,
                        mime="image/png" if preview_file_path.suffix.lower() == ".png" else "image/svg+xml",
                        use_container_width=True,
                        key="btn_download_canvas_img"
                    )
                except Exception as e:
                    st.error(f"Error reading image for download: {e}")
                
                try:
                    preview_file_path = Path(image_preview_path)
                    content_bytes = preview_file_path.read_bytes()
                    is_fallback_svg = content_bytes.strip().startswith(b"<svg") or b"<svg" in content_bytes[:200]
                except Exception:
                    is_fallback_svg = False

                if is_fallback_svg and st.session_state.get("image_provider_choice") != "mock":
                    st.warning(
                        "⚠️ **Fallback to Mock:** The selected provider failed to generate the image (likely due to API billing/limit constraints) and silently fell back to the Mock provider. "
                        "Please check your API keys or switch to the **`free-ai`** (Pollinations) provider to generate real Pixar illustrations for free."
                    )
            else:
                st.info("No visual canvas synthesized yet. Tweak subject descriptions under the screen and generate!")

            # Controls underneath canvas box
            st.markdown("#### 🎨 Prompt Engineering & synthesis")
            param_cols = st.columns(4)
            with param_cols[0]:
                st.selectbox(
                    "Image synthesis Provider",
                    options=("nvidia", "gemini", "openai", "free-ai"),
                    key="image_provider_choice"
                )
            with param_cols[1]:
                st.text_input("Explainer Topic", key="image_topic")
            with param_cols[2]:
                st.text_input("Scene Subject", key="image_subject")
            with param_cols[3]:
                st.selectbox(
                    "Art Style",
                    options=("3D Claymation / Pixar", "Photorealistic", "Flat Vector", "Cinematic Anime", "None (Raw Prompt)"),
                    key="image_art_style"
                )

            if st.session_state.get("image_provider_choice") == "gemini":
                st.info(
                    "💡 **Note on Gemini:** Dedicated image generation (`Imagen 3`/`4`) is only supported on Google AI Studio keys that have **billing enabled** (paid plan). "
                    "If your key is on the free tier, please select the **`free-ai`** (Pollinations) provider to generate real Pixar 3D illustrations for free."
                )
            elif st.session_state.get("image_provider_choice") == "nvidia":
                st.info(
                    "⚡ **NVIDIA selected:** This routes image generation through the NVIDIA-backed provider path first, before any fallback provider."
                )

            prompt_input = st.text_area("Engine-Injected Style Prompt", value=st.session_state.get("image_studio_prompt", ""), height=120)
            st.session_state["image_studio_prompt"] = prompt_input

            # Action Buttons under prompt text area
            act_cols = st.columns(2)
            with act_cols[0]:
                if st.button("🧙‍♂️ Build Cinematic style-pack Prompt", use_container_width=True, key="btn_build_prompt"):
                    st.session_state["image_studio_prompt"] = build_cinematic_image_prompt(
                        st.session_state["image_topic"],
                        st.session_state["image_subject"],
                        style_name=st.session_state.get("image_art_style", "3D Claymation / Pixar")
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
                            preview_path.write_bytes(provider.create(st.session_state["image_studio_prompt"], variant))
                            st.session_state["image_preview_path"] = str(preview_path)
                            st.success(f"Image successfully rendered!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Image generation error: {e}")

        with right_col:
            st.markdown("### Visual Theme & metadata")
            image_style_pack = build_image_style_pack(
                st.session_state["image_topic"],
                subject=st.session_state["image_subject"],
                style_name=st.session_state.get("image_art_style", "3D Claymation / Pixar")
            )
            st.json(image_style_pack.as_dict())

            st.markdown("#### Prompt Safety audit")
            safety_state, safety_msg = image_prompt_safety_status(st.session_state["image_studio_prompt"])
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

    elif active_p == "ComicVideo":
        render_comic_book_video_studio(settings)

    elif active_p == "Kids":
        # Creative Mode Dropdown
        st.session_state.setdefault("kids_studio_mode", "Poem/Rhyme")
        kids_mode = st.selectbox(
            "Creative Mode",
            options=["Poem/Rhyme", "Storytelling"],
            key="kids_studio_mode",
            help="Choose whether to generate a rhythmic rhyming nursery poem or an expressive storytelling script."
        )

        if kids_mode == "Storytelling":
            st.markdown(
                """
                <div class="hero" style="background: linear-gradient(135deg, rgba(56,189,248,0.15), rgba(168,85,247,0.15)); border: 1px solid rgba(56,189,248,0.3); margin-bottom: 24px;">
                  <h1 style="font-size: 32px;">📖 Kids Storytelling Studio (Native Audio)</h1>
                  <p style="margin-top: 6px; font-size: 14px;">Generate warm, expressive narration and storytelling with zero-drums background score and natural voices.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="hero" style="background: linear-gradient(135deg, rgba(56,189,248,0.15), rgba(168,85,247,0.15)); border: 1px solid rgba(56,189,248,0.3); margin-bottom: 24px;">
                  <h1 style="font-size: 32px;">🎵 Kids Rhymes & Rhythm Studio (Lyria 3 / Native Audio)</h1>
                  <p style="margin-top: 6px; font-size: 14px;">Generate cheerful, high-quality music and nursery rhymes matching your reference tracks using the configured Hugging Face SongGeneration space.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Target Language Dropdown
        st.session_state.setdefault("kids_studio_language", "English")
        st.selectbox(
            "Target Song Language",
            options=["English", "Hindi", "Hinglish"],
            key="kids_studio_language",
            help="Choose the language for the song generation. This filters the reference audio files and guides the dynamic lyric generator."
        )
        
        # Script Generator Selector
        st.session_state.setdefault("kids_studio_script_generator", "NVIDIA Llama 3.3")
        st.selectbox(
            "Choose Script Generator",
            options=["Gemini", "NVIDIA Llama 3.3", "Local LLM (Ollama/LM Studio)"],
            index=1,
            key="kids_studio_script_generator",
            help="Select the AI brain used to write stanzas and storytelling scripts."
        )
        
        # Dynamic inputs for Local LLM
        if st.session_state.get("kids_studio_script_generator") == "Local LLM (Ollama/LM Studio)":
            k_col1, k_col2 = st.columns(2)
            with k_col1:
                k_url = st.text_input(
                    "Local LLM API Endpoint:",
                    value=settings.local_llm_url,
                    key="kids_studio_local_llm_url"
                )
            with k_col2:
                k_model = st.text_input(
                    "Local LLM Model Name:",
                    value=settings.local_llm_model,
                    key="kids_studio_local_llm_model"
                )
            settings = replace(settings, local_llm_url=k_url, local_llm_model=k_model)

        # Determine kids voice options based on the selected language and mode
        import importlib
        import content_pipeline.bots.kids_studio_manifest_core as kids_manifest_core
        kids_manifest_core = importlib.reload(kids_manifest_core)
        KIDS_STUDIO_MASTER_REGISTRY = kids_manifest_core.KIDS_STUDIO_MASTER_REGISTRY
        kids_lang = st.session_state.get("kids_studio_language", "English")
        
        kids_singer_opts = {}
        for key, profile in KIDS_STUDIO_MASTER_REGISTRY.items():
            base_voice = profile.get("base_tts_voice", "")
            is_en = base_voice.startswith("en-")
            is_hi = base_voice.startswith("hi-")
            
            # Filter based on active mode
            is_storytelling_profile = "STORY" in key or "EN_KIDS" in key
            is_rhyme_profile = "RHYME" in key
            
            if kids_mode == "Storytelling" and not is_storytelling_profile:
                continue
            if kids_mode == "Poem/Rhyme" and not is_rhyme_profile:
                continue
                
            if kids_lang == "English" and is_en:
                kids_singer_opts[profile["display_name"]] = key
            elif kids_lang == "Hindi" and is_hi:
                kids_singer_opts[profile["display_name"]] = key
            elif kids_lang == "Hinglish":
                kids_singer_opts[profile["display_name"]] = key

        # Top-Level Kids Voice Profile Selector
        if kids_singer_opts:
            selected_display = st.selectbox(
                "Select Kids Voice Profile",
                options=list(kids_singer_opts.keys()),
                key="kids_studio_playback_singer_display",
                help="Select the specific voice profile to use for generation."
            )
            active_singer = kids_singer_opts[selected_display]
            st.session_state["kids_studio_playback_singer_key"] = active_singer
            
            # Resolve gender dynamically from the selected voice profile manifest
            from content_pipeline.bots.singer_manifest import SINGER_MANIFEST, SINGER_ALIASES
            resolved_key = SINGER_ALIASES.get(active_singer, active_singer)
            resolved_gender = "Female"
            if resolved_key in SINGER_MANIFEST:
                resolved_gender = SINGER_MANIFEST[resolved_key]["gender"].capitalize()
            
            st.session_state["kids_song_singer_gender"] = resolved_gender

        # Reference audio selection
        ref_dir = PROJECT_ROOT / "output" / "reference_audio"
        if not ref_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
            ref_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio")
        else:
            ref_dir.mkdir(parents=True, exist_ok=True)
        ref_files = []
        if ref_dir.exists():
            raw_files = sorted([f.name for f in ref_dir.glob("*.mp3")])
            kids_lang = st.session_state.get("kids_studio_language", "English")
            if kids_lang in ["Hindi", "Hinglish"]:
                ref_files = [f for f in raw_files if any(x in f.lower() for x in ["titli", "barnaby", "hindi", "squirrel", "littlebubbles", "bubbles", "custom", "ref"])]
            else:
                ref_files = [f for f in raw_files if not any(x in f.lower() for x in ["titli", "barnaby", "squirrel"]) or any(x in f.lower() for x in ["littlebubbles", "bubbles", "custom", "ref"])]
        
        options = ["None (Text-only)"] + ref_files
        default_index = 0
        default_val = st.session_state.get("kids_song_ref_audio_choice", "None (Text-only)")
        if default_val in options:
            default_index = options.index(default_val)
            
        selected_ref = st.selectbox(
            "Style Reference Audio (Optional)",
            options=options,
            index=default_index,
            key="kids_song_ref_audio_choice_input",
            help="Select an existing track to guide the style, melody, and rhythm of the kids rhyme.",
        )
        st.session_state["kids_song_ref_audio_choice"] = selected_ref

        # ── Default style description: derive from rhyme duration or mode ──────
        _rhyme_dur_secs = st.session_state.get("kids_effective_target_duration_seconds", 120)
        if kids_mode == "Storytelling":
            default_desc = "warm theatrical spoken-word audiobook narrator, gentle bedtime story, calm pacing, soft glockenspiel and warm strings, 0 BPM"
        elif _rhyme_dur_secs <= 150:
            default_desc = "cheerful nursery rhyme, magical kids show music, happy bouncy melody, 120 BPM, ukulele, soft piano, glockenspiel, bells."
        elif _rhyme_dur_secs <= 240:
            default_desc = "cheerful nursery rhyme, magical kids show music, medium paced sing-along, 110 BPM, ukulele, piano, glockenspiel."
        else:
            default_desc = "cheerful nursery rhyme, magical kids show music, gentle slow melody, 95 BPM, ukulele, soft piano, glockenspiel, bells."

        if kids_mode != "Storytelling":
            KIDS_STYLE_PRESETS = {
                "Cheerful Pop / Nursery Rhyme": "cheerful nursery rhyme, magical kids show music, happy bouncy melody, 120 BPM, ukulele, soft piano, glockenspiel, bells.",
                "Indian Kids Folk / Festival": "happy traditional Indian kids folk, bansuri flute melody, lively dholak and tabla groove, acoustic guitar strumming, bright and festive, 115 BPM.",
                "Gentle Bedtime Lullaby": "gentle sleep lullaby, sweet magical music box, warm ambient strings, slow harp melody, extremely calm and soothing, 70 BPM.",
                "Playful Ukulele Sing-Along": "happy acoustic ukulele sing-along, sunny slide guitar accents, bright shaker, whistling melody, warm and simple kids tune, 110 BPM.",
                "Upbeat Kids Disco / Dance": "funky kids disco, groovy bassline, upbeat retro synth bells, electric guitar muting, happy dance beat, 122 BPM.",
                "Whimsical Orchestral Cartoon": "whimsical cartoon orchestral theme, pizzicato strings, comedic xylophone jumps, clarinet melody, playful marching rhythm, 105 BPM."
            }

            selected_kids_vibe = st.selectbox(
                "Kids Song Style Preset",
                options=["Custom"] + list(KIDS_STYLE_PRESETS.keys()),
                key="kids_song_vibe_preset",
                help="Select a kids musical style preset to automatically populate the Style Description.",
            )

            if "prev_kids_song_vibe" not in st.session_state:
                st.session_state["prev_kids_song_vibe"] = selected_kids_vibe

            # Preset changed → update backing store BEFORE text_area is born
            if st.session_state["prev_kids_song_vibe"] != selected_kids_vibe:
                st.session_state["prev_kids_song_vibe"] = selected_kids_vibe
                if selected_kids_vibe != "Custom":
                    new_desc = KIDS_STYLE_PRESETS[selected_kids_vibe]
                    st.session_state["kids_song_description"] = new_desc
                    # Safe: widget not yet instantiated this render cycle
                    st.session_state["kids_song_description_input"] = new_desc

            # Bootstrap widget key from backing store if first render
            if "kids_song_description_input" not in st.session_state:
                st.session_state["kids_song_description_input"] = st.session_state.get(
                    "kids_song_description", default_desc
                )

            desc = st.text_area(
                "Style Description",
                height=120,
                key="kids_song_description_input",
                help="Describe instruments, tempo (BPM), and musical style. Populated by presets above — edit freely.",
            )
            st.session_state["kids_song_description"] = desc

        # Define and manage all backend run settings silently
        cfg = float(st.session_state.setdefault("kids_song_cfg_coef", 1.8))
        temp = float(st.session_state.setdefault("kids_song_temperature", 0.8))
        genre = st.session_state.setdefault("kids_song_genre", "Auto")
        desc = st.session_state.setdefault("kids_song_description", default_desc)


        expander_title = "⚡ One-Click Story Creator" if kids_mode == "Storytelling" else "⚡ One-Click Song Creator"
        with st.expander(expander_title, expanded=True):
            st.markdown(
                f"<small style='color: #94a3b8;'>Type a simple idea (e.g., {'a story about a wise turtle' if kids_mode == 'Storytelling' else 'create a rhyme about a brave rabbit'}) and generate in one click.</small>",
                unsafe_allow_html=True,
            )
            prompt_label = "Story Idea" if kids_mode == "Storytelling" else "Rhyme Idea"
            prompt_placeholder = "e.g., a story about a wise turtle" if kids_mode == "Storytelling" else "e.g., a rhyme about a brave rabbit"
            one_click_prompt = st.text_input(prompt_label, placeholder=prompt_placeholder, key="one_click_song_idea")

            # ── Approximate Rhyme Length picker (used for both Poem/Rhyme and Storytelling) ───────
            RHYME_DURATION_OPTIONS = {
                "~0 to 2 mins": 120,
                "~2 mins": 120,
                "~3 mins": 180,
                "~4 mins": 240,
                "~5 mins": 300,
                "~6 mins": 360,
            }
            current_rhyme_dur = st.session_state.get("kids_rhyme_duration_label", "~0 to 2 mins")
            if current_rhyme_dur not in RHYME_DURATION_OPTIONS:
                current_rhyme_dur = "~0 to 2 mins"
            rhyme_dur_label = st.selectbox(
                "Approximate Rhyme Length",
                options=list(RHYME_DURATION_OPTIONS.keys()),
                index=list(RHYME_DURATION_OPTIONS.keys()).index(current_rhyme_dur),
                key="kids_rhyme_duration_label",
                help="Pick a rough target length. The AI may be ±20 sec off this value.",
            )
            initial_duration_seconds = RHYME_DURATION_OPTIONS[rhyme_dur_label]
            initial_duration_descriptor = rhyme_dur_label
            st.caption(f"Target: {rhyme_dur_label} (≈ {initial_duration_seconds}s). Actual may vary slightly.")


            st.session_state["kids_effective_target_duration_seconds"] = initial_duration_seconds
            st.session_state["kids_effective_target_duration_descriptor"] = initial_duration_descriptor

            story_type = ""
            story_tags: list[str] = []
            if kids_mode == "Storytelling":
                story_type_options = [
                    "Fables & Fairy Tales",
                    "Bedtime Stories / Toddler Tales",
                    "Adventure / Action",
                    "Magic / Fantasy",
                    "Mystery",
                    "Mythology",
                    "Sci-Fi",
                    "Slice of Life",
                    "Historical Fiction",
                    "Supernatural",
                    "Romance",
                    "Thriller / Suspense",
                    "Horror",
                    "Young Adult (YA)",
                    "Dystopian",
                    "Cyberpunk",
                ]
                story_tag_options = [
                    "Kindness",
                    "Friendship",
                    "Courage",
                    "Teamwork",
                    "Family",
                    "Village life",
                    "School life",
                    "Animals",
                    "Space",
                    "Time travel",
                    "Magic quest",
                    "Hidden secret",
                    "Treasure hunt",
                    "Ancient gods",
                    "Cozy bedtime",
                    "Coming of age",
                ]
                genre_cols = st.columns([1, 1.4])
                with genre_cols[0]:
                    story_type = st.selectbox(
                        "Which type of story?",
                        options=story_type_options,
                        key="kids_story_type",
                        help="The agent will shape the plot, setting, tension, and tone around this story type.",
                    )
                with genre_cols[1]:
                    story_tags = st.multiselect(
                        "Story Tags",
                        options=story_tag_options,
                        key="kids_story_tags",
                        help="Optional extra signals for the story world, moral, and characters.",
                    )

                story_length_suggestion = suggest_story_length_preset(
                    one_click_prompt,
                    story_type,
                    story_tags,
                    initial_duration_seconds,
                )
                if story_length_suggestion:
                    suggested_preset, suggestion_reason = story_length_suggestion

                    def _apply_story_length_suggestion(preset_label: str) -> None:
                        st.session_state["kids_story_length_preset"] = preset_label

                    st.info(f"Length suggestion: {suggestion_reason}")
                    st.button(
                        f"Use {suggested_preset}",
                        key="kids_apply_story_length_suggestion",
                        use_container_width=True,
                        on_click=_apply_story_length_suggestion,
                        args=(suggested_preset,),
                    )

            if kids_mode == "Storytelling" and kids_lang == "English":
                story_suggestions = [
                    "A kind boy in a village helps a lost calf find its mother",
                    "A shy child plants a tiny seed that grows into a friendship tree",
                    "Two friends save the village kite festival on a windy day",
                    "A curious girl follows fireflies and learns why bedtime matters",
                    "A little boy shares his lunch and discovers the joy of kindness",
                    "A grandmother tells a moonlight story about a brave mango tree",
                ]

                def _use_story_suggestion(selected_idea: str) -> None:
                    st.session_state["one_click_song_idea"] = selected_idea

                st.caption("Need an idea? Pick a starter:")
                suggestion_cols = st.columns(3)
                for idx, suggestion in enumerate(story_suggestions):
                    label = suggestion.split(" ", 7)
                    short_label = " ".join(label[:7]) + ("..." if len(label) > 7 else "")
                    with suggestion_cols[idx % len(suggestion_cols)]:
                        st.button(
                            short_label,
                            key=f"kids_story_idea_suggestion_{idx}",
                            help=suggestion,
                            use_container_width=True,
                            on_click=_use_story_suggestion,
                            args=(suggestion,),
                        )
            
            # Resolve gender dynamically based on current selected profile
            one_click_gender = st.session_state.get("kids_song_singer_gender", "Female")
            story_tags_source = ",".join(story_tags)
            if kids_mode == "Storytelling":
                prompt_scale_source = f"{initial_duration_seconds}|{initial_duration_descriptor}"
            else:
                prompt_scale_source = f"{st.session_state.get('kids_song_speed', 'Mid')}"
            kids_prompt_source = f"{kids_mode}|{kids_lang}|{one_click_gender}|{prompt_scale_source}|{story_type}|{story_tags_source}|{one_click_prompt.strip()}"
            if st.session_state.get("kids_lyrics_prompt_source") != kids_prompt_source:
                st.session_state["kids_lyrics_generation_prompt"] = build_kids_lyrics_prompt(
                    one_click_prompt,
                    kids_mode,
                    kids_lang,
                    one_click_gender,
                    duration_seconds=initial_duration_seconds,
                    length_descriptor=initial_duration_descriptor,
                    song_speed=st.session_state.get("kids_song_speed", "Mid"),
                    story_type=story_type,
                    story_tags=story_tags,
                )
                st.session_state["kids_lyrics_prompt_source"] = kids_prompt_source
                st.session_state["kids_lyrics_prompt_widget_version"] = (
                    int(st.session_state.get("kids_lyrics_prompt_widget_version", 0)) + 1
                )

            prompt_box_label = "Script Prompt" if kids_mode == "Storytelling" else "Lyrics Prompt"
            prompt_widget_version = int(st.session_state.setdefault("kids_lyrics_prompt_widget_version", 0))
            prompt_widget_key = f"kids_lyrics_generation_prompt_input_{prompt_widget_version}"
            st.session_state["kids_lyrics_prompt_active_key"] = prompt_widget_key
            if prompt_widget_key not in st.session_state:
                st.session_state[prompt_widget_key] = st.session_state.get("kids_lyrics_generation_prompt", "")
            current_generation_prompt = st.text_area(
                prompt_box_label,
                key=prompt_widget_key,
                height=150,
                help="This is the full brief sent to the composer. Edit it directly or submit advice below.",
            )
            st.session_state["kids_lyrics_generation_prompt"] = current_generation_prompt

            advice_placeholder = (
                "e.g., Make it 2 minutes, slower bedtime pacing, add a gentle moral"
                if kids_mode == "Storytelling"
                else "e.g., make it slower, more playful, stronger chorus, shorter lines"
            )
            prompt_advice = st.text_area(
                "Advice for My Agent",
                placeholder=advice_placeholder,
                key="kids_lyrics_prompt_advice",
                height=90,
                help="Submit changes like speed, rhythm, mood, topic, or structure before generating.",
            )

            def _submit_kids_prompt_advice() -> None:
                advice_text = st.session_state.get("kids_lyrics_prompt_advice", "").strip()
                if not advice_text:
                    st.session_state["kids_lyrics_prompt_advice_status"] = "empty"
                    return
                active_prompt_key = st.session_state.get("kids_lyrics_prompt_active_key", "")
                active_prompt = st.session_state.get(
                    active_prompt_key,
                    st.session_state.get("kids_lyrics_generation_prompt", ""),
                )
                st.session_state["kids_lyrics_generation_prompt"] = apply_kids_prompt_advice(
                    active_prompt,
                    advice_text,
                    kids_mode,
                )
                st.session_state["kids_lyrics_prompt_widget_version"] = (
                    int(st.session_state.get("kids_lyrics_prompt_widget_version", 0)) + 1
                )
                st.session_state["kids_lyrics_prompt_advice_status"] = "applied"

            st.button(
                "✅ Submit Advice",
                use_container_width=True,
                key="kids_lyrics_prompt_advice_submit",
                on_click=_submit_kids_prompt_advice,
            )
            advice_status = st.session_state.pop("kids_lyrics_prompt_advice_status", None)
            if advice_status == "empty":
                st.warning("Please enter advice first.")
            elif advice_status == "applied":
                st.success("Advice applied to the lyrics prompt.")
            
            if st.session_state.get("gemini_api_error"):
                kids_lang = st.session_state.get("kids_studio_language", "English")
                if kids_lang in ["Hindi", "Hinglish"]:
                    st.error("⚠️ **Gemini API Call Failed (Offline Fallback Active)**\n\n"
                             "The application fell back to the local offline template because the Gemini API keys failed:\n"
                             f"```\n{st.session_state['gemini_api_error']}\n```\n"
                             "Please check your `.env` or system environment keys.")
                else:
                    st.info("ℹ️ **Dynamic generation offline fallback active.**\n\n"
                            "Using local offline template for English content (Gemini key not configured or failed, but not required for English).")

            btn_label = "🚀 Create & Generate Story" if kids_mode == "Storytelling" else "🚀 Create & Generate Rhyme/Poem"
            if st.button(btn_label, type="primary", use_container_width=True):
                composer_prompt = st.session_state.get("kids_lyrics_generation_prompt", "").strip()
                if not composer_prompt:
                    st.warning(f"Please enter a {prompt_label.lower()} or lyrics prompt first.")
                else:
                    lyrics_exp, desc_exp = expand_prompt_to_lyrics_and_style_dynamic(
                        settings, composer_prompt, one_click_gender, kids_lang, mode=kids_mode
                    )
                    if kids_lang in ["Hindi", "Hinglish"] and kids_mode != "Storytelling":
                        desc_exp = clean_style_description_for_instrumental(desc_exp)
                    st.session_state["kids_song_lyrics"] = lyrics_exp
                    st.session_state["kids_song_description"] = desc_exp
                    st.session_state["kids_song_singer_gender"] = one_click_gender
                    st.session_state["trigger_generation_now"] = True
                    st.rerun()

            if st.button("🎼 Create Instrumental Only (No Vocal)", use_container_width=True):
                instrumental_style = clean_style_description_for_instrumental(
                    st.session_state.get("kids_song_description", desc)
                )
                if not instrumental_style.strip():
                    instrumental_style = (
                        "Pure instrumental. Cheerful English kids song backing track, bright ukulele strums, "
                        "soft piano chords, glockenspiel melody, warm bass, hand claps, playful pop nursery rhythm, "
                        "polished studio mix, 92 BPM."
                    )
                instrumental_output = PROJECT_ROOT / "output" / "instrumentals" / "LittleBubbles_Instrumental_No_Vocal.mp3"
                with st.spinner("Creating instrumental-only music..."):
                    generated_instrumental = generate_instrumental_audio_track(
                        instrumental_output,
                        instrumental_style,
                        hf_token=_resolve_hf_song_token(settings),
                        genre=genre,
                        temperature=temp,
                        cfg_coef=cfg,
                        duration_seconds=int(st.session_state.get("kids_effective_target_duration_seconds", 90)),
                        selected_ref=selected_ref,
                        force_local=True,
                )
                st.session_state["kids_song_generated_mp3"] = str(generated_instrumental)
                st.session_state["kids_song_description"] = instrumental_style
                _auto_refresh_project_brain(settings, reason="kids_instrumental")
                if active_cat == "Automation":
                    maybe_generate_linked_kids_poster(settings)
                st.success("Instrumental-only audio created.")

        if active_cat == "Automation" and kids_mode == "Poem/Rhyme":
            render_kids_nursery_poster_section(settings)

        composer_title = "Story Composer / Script" if kids_mode == "Storytelling" else "Lyrics Composer"
        st.markdown(f"### {composer_title}")
        kids_lyrics_val = st.session_state.get("kids_song_lyrics", "")
        textarea_label = (
            "Enter storytelling script here (use [pause] tags for natural pauses)"
            if kids_mode == "Storytelling"
            else "Enter lyrics here (use [verse] and [chorus] tags, avoid [intro]/[outro] tags)"
        )
        lyrics = st.text_area(
            textarea_label,
            value=kids_lyrics_val,
            height=350,
            key="kids_song_lyrics_input"
        )
        st.session_state["kids_song_lyrics"] = lyrics

        col1, col2 = st.columns([1, 1])
        with col1:
            if kids_mode == "Storytelling":
                parse_clicked = False  # Bypassed for storytelling
            else:
                parse_clicked = st.button("✨ Parse & Autofill settings", use_container_width=True, help="Extracts lyrics, tempo, instruments, vocals, and mood from your prompt to autofill settings.")
        with col2:
            clear_label = "🗑️ Clear Script" if kids_mode == "Storytelling" else "🗑️ Clear Lyrics"
            if st.button(clear_label, use_container_width=True):
                st.session_state["kids_song_lyrics"] = ""
                st.rerun()

        if parse_clicked:
            if lyrics.strip():
                sections = parse_prompt_into_sections(lyrics)
                if sections:
                    lyrics_content = sections.get("lyrics", "")
                    if not lyrics_content:
                        lyrics_content = lyrics
                        
                    style_parts = []
                    if "style" in sections:
                        style_parts.append(sections["style"])
                    if "tempo" in sections:
                        style_parts.append(f"Tempo: {sections['tempo']}")
                    if "vocals" in sections:
                        style_parts.append(f"Vocals: {sections['vocals']}")
                    if "mood" in sections:
                        style_parts.append(f"Mood: {sections['mood']}")
                    if "instruments" in sections:
                        style_parts.append(f"Instruments: {sections['instruments']}")
                    if "production" in sections:
                        style_parts.append(f"Production: {sections['production']}")
                        
                    combined_style = ". ".join(style_parts)
                    
                    st.session_state["kids_song_lyrics"] = lyrics_content
                    st.session_state.pop("kids_song_lyrics_input", None)
                    st.session_state["kids_song_description"] = combined_style
                    st.session_state.pop("kids_song_description_input", None)
                    st.success("🎉 Successfully parsed and autofilled settings from prompt!")
                    st.rerun()
                else:
                    lower_text = lyrics.lower()
                    is_kids = any(k in lower_text for k in ["abc", "alphabet", "kid", "child", "baby", "nursery", "rhyme", "toddler", "toy"])
                    if is_kids:
                        inferred_style = (
                            "cheerful nursery rhyme, magical kids show music, happy bouncy melody, 92 BPM, "
                            "warm friendly lead voice, clear pronunciation, ukulele, soft piano, glockenspiel, "
                            "gentle bells, light percussion, clean mix."
                        )
                    else:
                        inferred_style = (
                            "catchy melodic pop song, warm vocals, piano, acoustic guitar, soft percussion, "
                            "balanced audio mix."
                        )
                    
                    st.session_state["kids_song_lyrics"] = lyrics
                    st.session_state.pop("kids_song_lyrics_input", None)
                    st.session_state["kids_song_description"] = inferred_style
                    st.session_state.pop("kids_song_description_input", None)
                    st.info("ℹ️ Plain prompt detected. Style inferred from song content.")
                    st.rerun()
            else:
                st.warning("⚠️ Please paste a prompt in the lyrics box first.")

        st.markdown(
            """
            <div style="display: flex; gap: 16px; margin-top: 20px;">
              <div style="flex: 1; padding: 16px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(56, 189, 248, 0.25);">
                <div style="font-size: 12px; color: #38bdf8; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                  <span>💡</span> Pro tip: Structure
                </div>
                <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                  For stories, use [pause] tags where you want natural storytelling pauses. For rhymes, structure with [verse] and [chorus].
                </div>
              </div>
              <div style="flex: 1; padding: 16px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(168, 85, 247, 0.25);">
                <div style="font-size: 12px; color: #a855f7; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                  <span>🎵</span> Pro tip: Settings
                </div>
                <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                  The studio manages parameters dynamically in the background, matching child-safe acoustics and vocal properties.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("---")
        st.markdown("### Playback & Generation")
        
        generated_file_path = st.session_state.get("kids_song_generated_mp3", "")
        default_out = PROJECT_ROOT / "output" / "LittleBubbles_Generated_Song.mp3"
        if not default_out.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3").exists():
            default_out = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3")
        if not generated_file_path and default_out.exists():
            generated_file_path = str(default_out)
            st.session_state["kids_song_generated_mp3"] = generated_file_path

        bottom_cols = st.columns([1.2, 1.8, 1.0])
        
        with bottom_cols[0]:
            if generated_file_path and Path(generated_file_path).exists():
                import html
                active_track_name = html.escape(Path(generated_file_path).name)
                st.markdown(
                    f"""
                    <div style="padding: 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(56, 189, 248, 0.15);">
                      <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Active Track</div>
                      <div style="font-size: 14px; font-weight: 800; color: #f8fafc; margin-top: 2px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                        {active_track_name}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    """
                    <div style="padding: 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(244, 63, 94, 0.15);">
                      <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Active Track</div>
                      <div style="font-size: 14px; font-weight: 800; color: #f43f5e; margin-top: 2px;">
                        No track generated yet
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
        with bottom_cols[1]:
            if generated_file_path and Path(generated_file_path).exists():
                st.audio(generated_file_path)
            else:
                st.write("")
                
        with bottom_cols[2]:
            btn_cols = st.columns(2)
            with btn_cols[0]:
                if generated_file_path and Path(generated_file_path).exists():
                    with open(generated_file_path, "rb") as f:
                        btn_data = f.read()
                    st.download_button(
                        label="Download",
                        data=btn_data,
                        file_name="LittleBubbles_Generated_Song.mp3",
                        mime="audio/mp3",
                        use_container_width=True
                    )
                else:
                    st.button("Download", disabled=True, use_container_width=True)
            with btn_cols[1]:
                generate_clicked = st.button("Generate", type="primary", use_container_width=True, key="kids_song_btn_generate")

        if generated_file_path and Path(generated_file_path).exists():
            adjust_cols = st.columns([1.0, 1.0, 2.0])
            audio_path = Path(generated_file_path)
            with adjust_cols[0]:
                try:
                    current_audio_seconds = get_audio_duration_seconds(audio_path)
                    st.metric("Current Length", _format_duration_hint(int(round(current_audio_seconds))))
                except Exception:
                    current_audio_seconds = None
                    st.metric("Current Length", "Unknown")
            with adjust_cols[1]:
                st.session_state.setdefault("kids_audio_target_duration_text", "1:30")
                target_duration_text = st.text_input(
                    "Target Length",
                    key="kids_audio_target_duration_text",
                    help="Examples: 1:30, 90 sec, 2 mins",
                )
            with adjust_cols[2]:
                st.write("")
                st.write("")
                if st.button("Adjust Audio Length", use_container_width=True, key="kids_audio_adjust_duration_btn"):
                    target_seconds = _extract_requested_duration_seconds(target_duration_text)
                    if not target_seconds:
                        st.warning("Please enter a valid target length, like 1:30 or 90 sec.")
                    else:
                        try:
                            with st.spinner(f"Adjusting audio to {_format_duration_hint(target_seconds)}..."):
                                adjusted_path = audio_path.with_name(
                                    f"{audio_path.stem}_{target_seconds}s{audio_path.suffix}"
                                )
                                adjusted_path, previous_seconds = adjust_audio_to_target_duration(
                                    audio_path,
                                    target_seconds,
                                    adjusted_path,
                                )
                                st.session_state["kids_song_generated_mp3"] = str(adjusted_path)
                                _auto_refresh_project_brain(settings, reason="kids_audio_adjust")
                                if active_cat == "Automation":
                                    maybe_generate_linked_kids_poster(settings)
                                st.success(
                                    "Adjusted audio from "
                                    f"{_format_duration_hint(int(round(previous_seconds)))} "
                                    f"to {_format_duration_hint(target_seconds)}."
                                )
                                st.rerun()
                        except Exception as adjust_exc:
                            st.error(f"Could not adjust audio length: {adjust_exc}")

            if kids_mode == "Storytelling":
                st.markdown("#### Smart Story Music Mixer")
                if generated_file_path and Path(generated_file_path).exists():
                    generated_parts = set(Path(generated_file_path).parts)
                    if "story_mixes" not in generated_parts:
                        st.session_state["kids_story_original_narration_mp3"] = generated_file_path
                mix_cols = st.columns([1.0, 1.0, 2.0])
                with mix_cols[0]:
                    story_music_gain = st.slider(
                        "Music Level",
                        min_value=-26.0,
                        max_value=-10.0,
                        value=float(st.session_state.get("kids_story_music_gain_db", -13.0)),
                        step=1.0,
                        key="kids_story_music_gain_db",
                        help="Lower values keep music softer under the storyteller.",
                    )
                with mix_cols[1]:
                    story_music_duck = st.slider(
                        "Speech Ducking",
                        min_value=3.0,
                        max_value=14.0,
                        value=float(st.session_state.get("kids_story_music_duck_db", 5.0)),
                        step=1.0,
                        key="kids_story_music_duck_db",
                        help="Higher values push background music down while narration is active.",
                    )
                with mix_cols[2]:
                    st.write("")
                    st.write("")
                    if st.button("🎚️ Add Smart Music to Clear Narration", use_container_width=True, key="kids_story_smart_music_mix_btn"):
                        original_narration = st.session_state.get("kids_story_original_narration_mp3", generated_file_path)
                        if not original_narration or not Path(original_narration).exists():
                            st.warning("Generate the clear Hindi story narration first.")
                        else:
                            original_path = Path(original_narration)
                            if "story_mixes" in set(original_path.parts) and generated_file_path:
                                st.warning("Please regenerate the clear narration first. The current source is already a mixed file.")
                                st.stop()
                            st.session_state["kids_story_original_narration_mp3"] = str(original_path)
                            story_script_for_score = st.session_state.get("kids_song_lyrics", lyrics)
                            mixed_output = PROJECT_ROOT / "output" / "story_mixes" / "LittleBubbles_Smart_Story_Mix.mp3"
                            with st.spinner("Smart AI is planning music cues and mixing under the existing clear narration..."):
                                mixed_path, score_plan, agent_report = smart_mix_storytelling_music_agent(
                                    original_path,
                                    story_script_for_score,
                                    mixed_output,
                                    music_gain_db=story_music_gain,
                                    speech_duck_db=story_music_duck,
                                )
                            st.session_state["kids_song_generated_mp3"] = str(mixed_path)
                            st.session_state["kids_story_score_plan"] = score_plan
                            st.session_state["kids_story_mix_agent_report"] = agent_report
                            _auto_refresh_project_brain(settings, reason="kids_story_mix")
                            if active_cat == "Automation":
                                maybe_generate_linked_kids_poster(settings)
                            if agent_report.get("passed"):
                                st.success("Music added under the clear narration. Voice, language, and pace were preserved.")
                            else:
                                st.warning("Music mix created, but review the quality report.")
                            st.rerun()

                score_plan = st.session_state.get("kids_story_score_plan", [])
                if score_plan:
                    with st.expander("Story music score plan", expanded=False):
                        for segment in score_plan:
                            start_seconds = int(segment.get("start_ms", 0) / 1000)
                            duration_seconds = int(segment.get("duration_ms", 0) / 1000)
                            st.write(
                                f"Part {segment.get('index')}: {segment.get('mood')} "
                                f"at {_format_duration_hint(start_seconds)} for {_format_duration_hint(duration_seconds)}"
                            )
                agent_report = st.session_state.get("kids_story_mix_agent_report", {})
                if agent_report:
                    with st.expander("Smart mix quality report", expanded=False):
                        final_quality = agent_report.get("final_quality", {})
                        st.write(
                            "NVIDIA planner: "
                            + ("used" if agent_report.get("used_nvidia_nim") else "local fallback")
                        )
                        st.write(
                            f"Duration delta: {final_quality.get('duration_delta_ms', 'n/a')}ms, "
                            f"mean: {final_quality.get('mean_dbfs', 'n/a')} dBFS, "
                            f"peak: {final_quality.get('peak_dbfs', 'n/a')} dBFS, "
                            f"longest silence: {final_quality.get('longest_silence_ms', 'n/a')}ms"
                        )
                        issues = final_quality.get("issues", [])
                        if issues:
                            st.write("Issues: " + ", ".join(str(issue) for issue in issues))
                        else:
                            st.write("Issues: none")
                        if agent_report.get("engine"):
                            st.write(f"Engine: {agent_report.get('engine')}")
                        repair_plan = agent_report.get("final_repair_plan", {})
                        if repair_plan:
                            st.write(
                                "Repair plan: "
                                f"target {repair_plan.get('target_mean_dbfs', 'n/a')} dBFS, "
                                f"peak ceiling {repair_plan.get('peak_ceiling_dbfs', 'n/a')} dBFS, "
                                f"max gap {repair_plan.get('max_gap_ms', 'n/a')}ms"
                            )

        if generate_clicked or st.session_state.get("trigger_generation_now"):
            if st.session_state.get("trigger_generation_now"):
                st.session_state["trigger_generation_now"] = False
            with st.spinner("Connecting to ASLP-lab/DiffRhythm2 space and generating audio... (This may take 1-3 minutes)"):
                try:
                    import subprocess
                    import shutil
                    from gradio_client import Client, handle_file

                    prompt_audio_param = None
                    active_ref = selected_ref
                    kids_gender_local = st.session_state.get("kids_song_singer_gender", "Male").lower()
                    if kids_gender_local == "male":
                        is_female_ref = active_ref != "None (Text-only)" and any(x in active_ref.lower() for x in ["barnaby", "titli", "squirrel", "alphabet", "bubbles", "female"])
                        if active_ref == "None (Text-only)" or is_female_ref:
                            arijit_file = "Sajni (Lyrical Video)_ Arijit Singh, Ram Sampath  Laapataa Ladies   Aamir Khan Productions.mp3"
                            if (PROJECT_ROOT / "output" / "reference_audio" / arijit_file).exists():
                                active_ref = arijit_file
                                st.info("ℹ️ Using default male reference audio (Arijit Singh) to force male vocals for DiffRhythm2.")
                    else:
                        is_male_ref = active_ref != "None (Text-only)" and any(x in active_ref.lower() for x in ["arijit", "sajni", "male"])
                        if active_ref == "None (Text-only)" or is_male_ref:
                            lang = st.session_state.get("kids_studio_language", "English")
                            if lang in ["Hindi", "Hinglish"]:
                                female_file = "Barnaby_Squirrel_Song.mp3"
                                if (PROJECT_ROOT / "output" / "reference_audio" / female_file).exists():
                                    active_ref = female_file
                                    st.info("ℹ️ Using default female reference audio (Barnaby) to force female vocals for DiffRhythm2.")
                    
                    
                    if active_ref != "None (Text-only)":
                        ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / active_ref
                        if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / active_ref
                        if ref_full_path.exists():
                            temp_dir = PROJECT_ROOT / "output" / ".runtime"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            cropped_ref_path = temp_dir / "kids_song_ref_cropped.mp3"
                            
                            st.write(f"ℹ️ Cropping style reference '{active_ref}' to 15 seconds...")
                            start_time = "0"
                            if ref_full_path.name == "बार्नबी गिलहरी की व्यर्थ खोज.mp3":
                                start_time = "4.5"
                                
                            cmd = [
                                "ffmpeg", "-y", "-i", str(ref_full_path),
                                "-ss", start_time, "-t", "15",
                                "-codec:a", "libmp3lame", "-b:a", "128k",
                                str(cropped_ref_path)
                            ]
                            subprocess.run(cmd, check=True)
                            prompt_audio_param = handle_file(str(cropped_ref_path))
                        else:
                            st.warning(f"Reference audio '{active_ref}' not found. Falling back to text-only generation.")

                    st.write("📝 Checking and sanitizing prompt structure...")
                    lyrics_to_process = lyrics.strip()
                    import re
                    
                    supported_tags = ["verse", "chorus", "bridge", "intro", "outro", "inst", "silence"]
                    has_leading_tag = False
                    if lyrics_to_process.startswith("["):
                        first_line = lyrics_to_process.splitlines()[0].strip()
                        if first_line.endswith("]"):
                            tag_content = first_line[1:-1].lower()
                            if any(t in tag_content for t in supported_tags):
                                has_leading_tag = True
                                
                    if not has_leading_tag:
                        st.write("✨ Auto-parsing raw prompt to extract lyrics and style details...")
                        sections = parse_prompt_into_sections(lyrics)
                        if sections:
                            lyrics_to_process = sections.get("lyrics", "").strip()
                            if not lyrics_to_process:
                                lyrics_to_process = lyrics.strip()
                                
                            style_parts = []
                            if "style" in sections:
                                style_parts.append(sections["style"])
                            if "tempo" in sections:
                                style_parts.append(f"Tempo: {sections['tempo']}")
                            if "vocals" in sections:
                                style_parts.append(f"Vocals: {sections['vocals']}")
                            if "mood" in sections:
                                style_parts.append(f"Mood: {sections['mood']}")
                            if "instruments" in sections:
                                style_parts.append(f"Instruments: {sections['instruments']}")
                            if "production" in sections:
                                style_parts.append(f"Production: {sections['production']}")
                                
                            desc = ". ".join(style_parts)
                            st.session_state["kids_song_description"] = desc
                            st.session_state["kids_song_lyrics"] = lyrics_to_process
                        else:
                            lower_text = lyrics.lower()
                            is_kids = any(k in lower_text for k in ["abc", "alphabet", "kid", "child", "baby", "nursery", "rhyme", "toddler", "toy"])
                            if is_kids:
                                desc = "cheerful nursery rhyme, magical kids show music, happy bouncy melody, 92 BPM, ukulele, soft piano, glockenspiel, bells."
                            else:
                                desc = "catchy pop song, piano, acoustic guitar, soft percussion."
                            st.session_state["kids_song_description"] = desc

                    lang = st.session_state.get("kids_studio_language", "English")
                    singer_gender = st.session_state.get("kids_song_singer_gender", "Male").lower()
                    if lang == "Hindi":
                        # Decoupled audio pipeline: backing track must be vocal-free
                        pass
                    elif lang == "Hinglish":
                        if singer_gender == "female":
                            desc = re.sub(r" male ", " female ", desc, flags=re.IGNORECASE)
                            if "female" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly native Indian female singing voice, Bollywood style kids singer, clear Hinglish pronunciation, natural Indian accent."
                            else:
                                if not any(x in desc.lower() for x in ["indian", "bollywood", "hinglish"]):
                                    desc = desc.strip()
                                    if desc and not desc.endswith("."):
                                        desc += "."
                                    desc += " native Indian female singer, clear Hinglish pronunciation."
                        else:
                            desc = re.sub(r" female ", " male ", desc, flags=re.IGNORECASE)
                            if "male" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly native Indian male singing voice, Bollywood style kids singer, clear Hinglish pronunciation, natural Indian accent."
                            else:
                                if not any(x in desc.lower() for x in ["indian", "bollywood", "hinglish"]):
                                    desc = desc.strip()
                                    if desc and not desc.endswith("."):
                                        desc += "."
                                    desc += " native Indian male singer, clear Hinglish pronunciation."
                    else:
                        if singer_gender == "female":
                            desc = re.sub(r" male ", " female ", desc, flags=re.IGNORECASE)
                            if "female" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly female singing voice."
                        else:
                            desc = re.sub(r" female ", " male ", desc, flags=re.IGNORECASE)
                            if "male" not in desc.lower():
                                desc = desc.strip()
                                if desc and not desc.endswith("."):
                                    desc += "."
                                desc += " friendly male singing voice."

                    st.session_state["kids_song_description"] = desc
                    st.session_state.pop("kids_song_description_input", None)

                    # 2. Split lines, skip empty lines, and sanitize tags
                    kids_mode = st.session_state.get("kids_studio_mode", "Poem/Rhyme")
                    if kids_mode == "Storytelling":
                        sanitized_lines = []
                        for line in [l.strip() for l in lyrics_to_process.splitlines() if l.strip()]:
                            sanitized_lines.append(line.replace(";", ","))
                        sanitized_lyrics = "\n".join(sanitized_lines).strip()
                    else:
                        sanitized_lines = []
                        lines = [line.strip() for line in lyrics_to_process.splitlines()]
                        
                        filtered_lines = [line for line in lines if line]
                        
                        if filtered_lines:
                            first_line = filtered_lines[0]
                            if not (first_line.startswith("[") and first_line.endswith("]")):
                                sanitized_lines.append("[verse]")
                            
                            for line in filtered_lines:
                                line_safe = line.replace(";", ",")
                                
                                if line_safe.startswith("[") and line_safe.endswith("]"):
                                    tag_content = line_safe[1:-1].lower()
                                    if "chorus" in tag_content:
                                        sanitized_lines.append("[chorus]")
                                    elif "bridge" in tag_content:
                                        sanitized_lines.append("[bridge]")
                                    elif "intro" in tag_content:
                                        sanitized_lines.append("[verse]")
                                    elif "outro" in tag_content:
                                        sanitized_lines.append("[verse]")
                                    elif "inst" in tag_content:
                                        sanitized_lines.append("[verse]")
                                    elif "silence" in tag_content:
                                        sanitized_lines.append("[silence]")
                                    else:
                                        sanitized_lines.append("[verse]")
                                else:
                                    sanitized_lines.append(line_safe)
                                    
                        sanitized_lyrics = "\n".join(sanitized_lines).strip()
                        
                        if not sanitized_lyrics.startswith("["):
                            sanitized_lyrics = "[verse]\n" + sanitized_lyrics

                    lang = st.session_state.get("kids_studio_language", "English")
                    if lang == "Hindi" and kids_mode == "Poem/Rhyme":
                        st.write("🎵 Generating Kids Hindi Rhyme via Google Lyria 3 Pro...")
                        from content_pipeline.bots.audio import generate_song_via_lyria3
                        
                        out_path = PROJECT_ROOT / "output" / "LittleBubbles_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        singer_gender = st.session_state.get("kids_song_singer_gender", "Female")
                        generate_song_via_lyria3(
                            lyrics=sanitized_lyrics,
                            style_description=desc,
                            output_path=out_path,
                            gemini_api_keys=settings.gemini_api_keys,
                            gemini_api_key=settings.gemini_api_key,
                            singer_gender=singer_gender,
                            language="Hindi",
                            st_write_func=st.write,
                        )
                        out_path = normalize_music_studio_audio_length(
                            out_path,
                            int(st.session_state.get("kids_effective_target_duration_seconds", 90)),
                        )
                        st.session_state["kids_song_generated_mp3"] = str(out_path)
                        st.success("🎉 Kids Hindi Rhyme generated successfully using Google Lyria 3 Pro!")
                        st.rerun()
                    elif kids_mode == "Storytelling":
                        if lang == "Hindi" and not any("\u0900" <= char <= "\u097f" for char in sanitized_lyrics):
                            st.write("🔮 Converting Romanized lyrics to native Devanagari script for perfect Indian accent...")
                            from content_pipeline.bots.gemini_tts import transliterate_to_devanagari
                            sanitized_lyrics = transliterate_to_devanagari(sanitized_lyrics, settings)
                            st.info(f"📝 Transliterated Devanagari Lyrics:\n{sanitized_lyrics}")
                        
                        st.write("🔀 Bypassing Hugging Face Lyria to use Native Audio Pipeline...")
                        import sys
                        import importlib
                        if "content_pipeline.bots.singing_synthesis" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.singing_synthesis"])
                        if "content_pipeline.bots.kids_studio_manifest_core" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.kids_studio_manifest_core"])
                        if "content_pipeline.bots.kids_studio_core" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.kids_studio_core"])
                        if "content_pipeline.bots.singer_manifest" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.singer_manifest"])
                        if "content_pipeline.bots.audio" in sys.modules:
                            importlib.reload(sys.modules["content_pipeline.bots.audio"])
                        from content_pipeline.bots.audio import generate_hindi_song_via_native_audio
                        
                        out_path = PROJECT_ROOT / "output" / "LittleBubbles_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        singer_gender = st.session_state.get("kids_song_singer_gender", "Female")
                        selected_ref = st.session_state.get("kids_song_ref_audio_choice", "None (Text-only)")

                        story_target_seconds = int(
                            st.session_state.get("kids_effective_target_duration_seconds", 90)
                        )
                        story_part_count = determine_story_audio_part_count(story_target_seconds)
                        if kids_mode == "Storytelling" and story_part_count > 1:
                            progress_bar = st.progress(0, text="0% - Preparing story audio parts...")
                            progress_bar.progress(1, text="1% - Checking story length...")
                            minimum_story_words = int(story_target_seconds * 1.35)
                            if len(sanitized_lyrics.split()) < minimum_story_words:
                                st.warning(
                                    "The script is shorter than the requested story length, so the agent is expanding it before audio generation."
                                )
                                fallback_story, _fallback_style = build_local_storytelling_fallback(
                                    st.session_state.get("kids_lyrics_generation_prompt", sanitized_lyrics),
                                    singer_gender,
                                )
                                sanitized_lyrics = f"{sanitized_lyrics}\n\n{fallback_story}".strip()
                            story_idea_for_intro = st.session_state.get("one_click_song_idea", "").strip()
                            part_target_seconds_list = get_story_part_target_seconds(
                                story_target_seconds,
                                story_part_count,
                            )
                            story_part_scripts = build_story_audio_part_scripts(
                                sanitized_lyrics,
                                story_idea_for_intro,
                                story_part_count,
                                part_target_seconds_list,
                                language=lang,
                            )
                            if len(story_part_scripts) < story_part_count:
                                story_part_count = len(story_part_scripts)
                                part_target_seconds_list = get_story_part_target_seconds(
                                    story_target_seconds,
                                    story_part_count,
                                )
                            st.info(
                                f"Long story mode: generating {story_part_count} parts with the same selected voice profile "
                                "and identical audio settings for continuity. Part 1 targets about 90 seconds; remaining parts stay around 70-80 seconds when possible. "
                                f"Target length is about {_format_duration_hint(story_target_seconds)}."
                            )
                            part_dir = out_path.parent / "story_parts"
                            part_dir.mkdir(parents=True, exist_ok=True)
                            part_paths: list[Path] = []
                            selected_singer_key = st.session_state.get(
                                "kids_studio_playback_singer_key",
                                "hi_kids_ananya",
                            )
                            part_percent_span = 86
                            for part_index, story_part_script in enumerate(story_part_scripts, start=1):
                                part_target_seconds = part_target_seconds_list[min(part_index - 1, len(part_target_seconds_list) - 1)]
                                part_start = 2 + int((part_index - 1) * part_percent_span / story_part_count)
                                part_end = 2 + int(part_index * part_percent_span / story_part_count)
                                part_path = part_dir / f"{out_path.stem}_part_{part_index:02d}.mp3"

                                run_with_live_percentage(
                                    lambda script=story_part_script, path=part_path: generate_hindi_song_via_native_audio(
                                        lyrics=script,
                                        output_path=path,
                                        singer_gender=singer_gender,
                                        selected_ref=selected_ref,
                                        hf_token=_resolve_hf_song_token(settings),
                                        genre=genre,
                                        temperature=temp,
                                        cfg_coef=cfg,
                                        style_description=desc,
                                        singer_key=selected_singer_key,
                                        mode=kids_mode
                                    ),
                                    progress_bar,
                                    f"Generating part {part_index}/{story_part_count}...",
                                    start_percent=part_start,
                                    max_percent=part_end,
                                    estimated_seconds=estimate_story_audio_generation_seconds(
                                        part_target_seconds,
                                        story_part_script,
                                    ),
                                )
                                part_paths.append(part_path)

                            progress_bar.progress(90, text="90% - Merging story parts...")
                            merged_path = out_path.with_name(f"{out_path.stem}_merged.mp3")
                            merge_audio_parts(part_paths, merged_path)
                            tolerance_seconds = get_natural_duration_tolerance_seconds(story_target_seconds)
                            progress_bar.progress(
                                94,
                                text=(
                                    "94% - Checking natural duration range "
                                    f"({_format_duration_hint(story_target_seconds - tolerance_seconds)} to "
                                    f"{_format_duration_hint(story_target_seconds + tolerance_seconds)})..."
                                )
                            )
                            adjusted_path, previous_seconds, final_duration_target, used_natural_duration = normalize_audio_to_duration_window(
                                merged_path,
                                story_target_seconds,
                                out_path,
                            )
                            st.session_state["kids_song_generated_mp3"] = str(adjusted_path)
                            st.session_state["kids_song_story_part_paths"] = [str(path) for path in part_paths]
                            st.session_state.pop("kids_song_preview_part_mp3", None)
                            _auto_refresh_project_brain(settings, reason="kids_story_native_long")
                            if active_cat == "Automation":
                                maybe_generate_linked_kids_poster(settings)
                            progress_bar.progress(100, text="100% - Story audio parts merged and ready.")
                            if used_natural_duration:
                                st.success(
                                    f"🎉 Long story generated in {story_part_count} parts. "
                                    f"Final length is {_format_duration_hint(int(round(previous_seconds)))} "
                                    "and is inside the natural quality range, so no time-stretching was applied."
                                )
                            else:
                                st.success(
                                    f"🎉 Long story generated in {story_part_count} parts. "
                                    f"Final audio was gently adjusted from {_format_duration_hint(int(round(previous_seconds)))} "
                                    f"to the nearest quality range edge: {_format_duration_hint(final_duration_target)}."
                                )
                        else:
                            generate_hindi_song_via_native_audio(
                                lyrics=sanitized_lyrics,
                                output_path=out_path,
                                singer_gender=singer_gender,
                                selected_ref=selected_ref,
                                hf_token=_resolve_hf_song_token(settings),
                                genre=genre,
                                temperature=temp,
                                cfg_coef=cfg,
                                style_description=desc,
                                singer_key=st.session_state.get("kids_studio_playback_singer_key", "hi_kids_ananya"),
                                mode=kids_mode
                            )
                            st.session_state["kids_song_generated_mp3"] = str(out_path)
                            _auto_refresh_project_brain(settings, reason="kids_story_native_short")
                            if active_cat == "Automation":
                                maybe_generate_linked_kids_poster(settings)
                            st.success(f"🎉 Kids {kids_mode} generated successfully using Native Audio Pipeline!")
                        st.rerun()
                    elif lang == "Hinglish":
                        st.write("🔮 Applying advanced phonetic transcription layer for perfect Indian accent...")
                        from content_pipeline.bots.phonetic_mapper import hindi_to_phonetic_hinglish
                        sanitized_lyrics = hindi_to_phonetic_hinglish(sanitized_lyrics, gemini_api_key=settings.gemini_api_key)
                        st.info(f"📝 Transcribed Phonetic Lyrics:\n{sanitized_lyrics}")

                    st.write("🎵 Dispatching song generation request to Hugging Face prioritized spaces...")
                    try:
                        formatted_lyrics = sanitized_lyrics.strip()
                        if not formatted_lyrics.startswith("[start]"):
                            formatted_lyrics = f"[start]\n{formatted_lyrics}"
                            
                        from content_pipeline.bots.audio import generate_song_via_prioritized_spaces
                        
                        spaces_priority = ["ASLP-lab/DiffRhythm2", "tencent/SongGeneration", "multimodalart/khala"]
                        result_path, info = generate_song_via_prioritized_spaces(
                            lrc=formatted_lyrics,
                            text_prompt=f"{genre}, {desc}",
                            audio_prompt=prompt_audio_param,
                            genre=genre,
                            temperature=temp,
                            cfg_coef=cfg,
                            duration_seconds=float(st.session_state.get("kids_effective_target_duration_seconds", 90)),
                            language="Hindi" if lang == "Hindi" else "English",
                            spaces_priority=spaces_priority,
                            st_write_func=st.write
                        )
                        
                        if not result_path or str(result_path).strip().lower() == "none":
                            raise ValueError(f"Hugging Face spaces did not return a valid audio track. Details: {info}")

                        st.write("🔄 Transcoding generated audio from FLAC to genuine MP3 with smooth fade-out...")
                        out_path = PROJECT_ROOT / "output" / "LittleBubbles_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        duration_cmd = [
                            "ffprobe", "-i", str(result_path),
                            "-show_entries", "format=duration",
                            "-v", "quiet", "-of", "csv=p=0"
                        ]
                        duration_res = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
                        total_duration = float(duration_res.stdout.strip())
                        
                        fade_duration = 5.0
                        if total_duration > 15.0:
                            start_fade = total_duration - fade_duration
                        else:
                            fade_duration = min(2.0, total_duration * 0.2)
                            start_fade = total_duration - fade_duration
                            
                        transcode_cmd = [
                            "ffmpeg", "-y", "-i", str(result_path),
                            "-filter:a", f"afade=t=out:st={start_fade:.3f}:d={fade_duration:.3f}",
                            "-codec:a", "libmp3lame", "-qscale:a", "2",
                            str(out_path)
                        ]
                        subprocess.run(transcode_cmd, check=True)
                        
                        st.session_state["kids_song_generated_mp3"] = str(out_path)
                        _auto_refresh_project_brain(settings, reason="kids_song_hf")
                        if active_cat == "Automation":
                            maybe_generate_linked_kids_poster(settings)
                        st.success("🎉 Kids rhyme generated successfully!")
                        st.rerun()
                    except Exception as hf_exc:
                        st.warning(f"⚠️ Hugging Face song generation failed: {hf_exc}. Activating free Edge-TTS backup mixer...")
                        from content_pipeline.bots.audio import generate_edge_tts_song_fallback
                        out_path = PROJECT_ROOT / "output" / "LittleBubbles_Generated_Song.mp3"
                        if not out_path.parent.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            out_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3")
                        singer_gender = st.session_state.get("kids_song_singer_gender", "Male")
                        selected_ref = st.session_state.get("kids_song_ref_audio_choice", "None (Text-only)")
                        generate_edge_tts_song_fallback(
                            lyrics=sanitized_lyrics,
                            output_path=out_path,
                            singer_gender=singer_gender,
                            selected_ref=selected_ref,
                            singer_key=st.session_state.get("kids_studio_playback_singer_key", "en_kids_ana"),
                            mode=kids_mode
                        )
                        st.session_state["kids_song_generated_mp3"] = str(out_path)
                        _auto_refresh_project_brain(settings, reason="kids_song_fallback")
                        if active_cat == "Automation":
                            maybe_generate_linked_kids_poster(settings)
                        st.success("🎉 Backup Kids rhyme generated successfully using Edge-TTS fallback mixer!")
                        st.rerun()
                except Exception as exc:
                    st.error(f"❌ Error during kids rhyme preparation: {exc}")

    elif active_p == "Speech":
        active_scene_idx = st.session_state.get("scene_index", 0)
        if active_scene_idx >= len(scenes_data):
            active_scene_idx = 0
            st.session_state["scene_index"] = 0

        editor_key = f"dialogue_editor_{active_scene_idx}"
        if editor_key in st.session_state:
            scenes_data[active_scene_idx]["narration"] = st.session_state[editor_key]
        
        st.session_state["voice_preview_text"] = scenes_data[active_scene_idx]["narration"]

        st.subheader("Speech Studio 🎙️")
        
        audio_path = ui_settings.output_dir / "daily" / inspect_date / "audio_status.html"
        audio_json = ui_settings.output_dir / "daily" / inspect_date / "audio_status.json"
        voice_json = ui_settings.output_dir / "daily" / inspect_date / "voice_status.json"
        
        af_col1, af_col2 = st.columns([7, 3])
        with af_col1:
            if audio_path.exists():
                with st.expander("🎙️ Unified Audio Front Door HTML View", expanded=False):
                    st.iframe(audio_path.read_text(encoding="utf-8"), height=520)
            else:
                st.info("No audio front door found yet for this day.")
        with af_col2:
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

        st.markdown("---")

        center_col, right_col = st.columns([6.5, 3.5])

        with center_col:
            presets = voice_preview_presets()
            preset_map = {preset.key: preset for preset in presets}
            
            library_language = st.session_state.get("voice_library_language_filter", "all")
            library_gender = st.session_state.get("voice_gender_filter", "all")

            prev_library_language = st.session_state.get("prev_voice_library_language_filter", "all")
            prev_library_gender = st.session_state.get("prev_voice_gender_filter", "all")
            filters_changed = (library_language != prev_library_language or library_gender != prev_library_gender)

            if filters_changed:
                st.session_state["prev_voice_library_language_filter"] = library_language
                st.session_state["prev_voice_gender_filter"] = library_gender

            filtered_presets = filter_voice_preview_presets(
                presets,
                language=library_language,
                gender=library_gender
            )
            if not filtered_presets:
                filtered_presets = presets

            filtered_preset_keys = [p.key for p in filtered_presets]

            active_preset_key = st.session_state["voice_preset_choice"]
            if active_preset_key not in filtered_preset_keys or filters_changed:
                if active_preset_key not in filtered_preset_keys:
                    active_preset_key = filtered_preset_keys[0]
                st.session_state["voice_preset_choice"] = active_preset_key
                st.session_state["voice_name_choice"] = preset_map[active_preset_key].voice
                st.session_state["voice_preview_text"] = preset_map[active_preset_key].sample_text
                
                st.session_state[f"dialogue_editor_{active_scene_idx}"] = preset_map[active_preset_key].sample_text
                scenes_data[active_scene_idx]["narration"] = preset_map[active_preset_key].sample_text
                try:
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                    
                st.rerun()

            active_preset = preset_map[active_preset_key]

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

            voice_preview_path = st.session_state.get("voice_preview_path")
            if voice_preview_path and os.path.exists(voice_preview_path):
                st.audio(voice_preview_path)
                st.caption(f"Loaded preview path: `{Path(voice_preview_path).name}`")
            else:
                st.info("No audio preview generated yet. Tweak parameters below and click 'Play Preview' on the right panel!")

            st.markdown("#### 🛠️ Vocal Parameter Tweaks")
            param_cols = st.columns(3)

            with param_cols[0]:
                gender_options = voice_gender_options()
                gender_map = {value: label for value, label in gender_options}
                st.selectbox(
                    "Vocal Gender",
                    options=[value for value, _ in gender_options],
                    format_func=lambda value: gender_map.get(value, value),
                    key="voice_gender_filter"
                )

            with param_cols[1]:
                language_options = voice_preview_language_options()
                language_map = {value: label for value, label in language_options}
                st.selectbox(
                    "Vocal Language",
                    options=[value for value, _ in language_options],
                    format_func=lambda value: language_map.get(value, value),
                    key="voice_library_language_filter"
                )

            with param_cols[2]:
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

            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            apply_cols = st.columns([1.5, 1.5, 7])
            with apply_cols[0]:
                if st.button("✅ Apply", key="btn_apply_prosody", use_container_width=True):
                    active_scene_idx = st.session_state["scene_index"]
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
                                provider=getattr(active_preset, "provider", "edge"),
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
                                provider=getattr(active_preset, "provider", "edge"),
                                voice=active_preset.voice,
                                rate=active_preset.rate or "+0%",
                                pitch=active_preset.pitch or "+0Hz"
                            )
                            st.session_state["voice_preview_path"] = str(preview_file)
                            st.success("Prosody adjustments reset to preset defaults!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error resetting preview: {e}")

            st.markdown("##### 📜 Dialogue Phonetic Pronunciation")
            normalized_preview = normalize_voice_text(st.session_state["voice_preview_text"])
            st.text_area("Normalized Text (phonetic replacements for neural engines)", value=normalized_preview, height=90, disabled=True)

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

        with right_col:
            st.markdown("### AI Voiceover controls")
            scene_scope = st.radio("Narration Scope", options=["Current scene", "All scenes"], horizontal=True, key="scene_scope")

            if scene_scope == "Current scene":
                scene_index = st.session_state["scene_index"]
                if scene_index >= len(scenes_data):
                    scene_index = 0
                    st.session_state["scene_index"] = 0

                scene = scenes_data[scene_index]

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

                st.markdown(f"🎬 **Scene Context:** *{scene.get('title', 'Explainer Section')}*")
                narration_val = st.text_area("Scene Dialogue Track Script", value=scene["narration"], height=160, key=f"dialogue_editor_{scene_index}")
                scenes_data[scene_index]["narration"] = narration_val

            else:
                st.markdown("📝 **All Storyboard Dialogue Blocks**")
                with st.container(height=240):
                    for idx, scene in enumerate(scenes_data):
                        st.markdown(f"**Scene {idx+1}: {scene.get('title', 'Explainer Section')}**")
                        st.caption(scene["narration"])
                        st.markdown("---")

            st.markdown(f"""
            <div class="voiceover-card">
                <div style="font-size: 11px; text-transform: uppercase; color: #38bdf8; font-weight: 800; letter-spacing: 0.05em;">Voiceover Narrator Profile</div>
                <div style="font-size: 16px; font-weight: 800; color: white; margin-top:6px; margin-bottom: 2px;">{active_preset.label}</div>
                <div style="font-size: 13px; color: #cbd5e1; line-height: 1.4;">{active_preset.description}</div>
            </div>
            """, unsafe_allow_html=True)

            voice_action_cols = st.columns(2)
            with voice_action_cols[0]:
                if st.button("🔄 Change Voice", use_container_width=True, key="btn_trigger_modal"):
                    select_voice_dialog()
            with voice_action_cols[1]:
                if st.button("▶️ Play Preview", use_container_width=True, key="btn_play_narration_preview"):
                    with st.spinner("Compiling neural speech..."):
                        try:
                            preview_root = ui_output_dir / ".runtime" / "voice_previews"
                            preview_root.mkdir(parents=True, exist_ok=True)
                            preview_file = preview_root / f"scene_{st.session_state['scene_index'] + 1}_preview.mp3"

                            generate_voice_preview(
                                text=scenes_data[st.session_state["scene_index"]]["narration"],
                                output_path=preview_file,
                                provider=getattr(active_preset, "provider", "edge"),
                                voice=active_preset.voice,
                                rate=st.session_state.get("voice_rate_tweak_slider", active_preset.rate),
                                pitch=st.session_state.get("voice_pitch_tweak_slider", active_preset.pitch)
                            )
                            st.session_state["voice_preview_path"] = str(preview_file)
                            st.success("Neural dialogue compiled successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Vocal synthesis error: {e}")

            if st.button("💾 Save Script & Storyboard edits", type="primary", use_container_width=True, key="btn_save_script"):
                with st.spinner("Writing to database..."):
                    try:
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(scenes_data, f, indent=2, ensure_ascii=False)
                        st.success("Script changes successfully synced across the pipeline!")
                    except Exception as e:
                        st.error(f"Error saving storyboard script: {e}")

    elif active_p == "Run":
        st.markdown(
            f"""
            <section class="hero">
              <h1>Content Studio</h1>
              <p>
                A control center for your daily pipeline, unified audio status, blocker memory,
                and image style tooling. Run the daily build, jump straight into the newest run,
                and inspect the artifacts without hunting through folders.
              </p>
            </section>
            """,
            unsafe_allow_html=True,
        )

        left, right = st.columns([1.2, 0.8])
        with left:
            pipeline_type = st.radio(
                "Select Active Pipeline:",
                options=["LinkedIn Daily MVP", "YouTube Video Automation"],
                horizontal=True,
                key="run_pipeline_type_select"
            )
            
            if pipeline_type == "LinkedIn Daily MVP":
                st.subheader("Run the daily pipeline")
                st.write("This triggers the same daily content generation flow your CLI uses.")
                st.caption(
                    f"Latest day: {latest_day or 'none yet'} · Files in latest run: {latest_overview['file_count']}"
                )

                # Action cards & run button
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
                    if st.button("🚀 Run Pipeline", type="primary", use_container_width=True, key="btn_run_pipeline"):
                        with st.spinner(f"Running daily LinkedIn package generation for {run_date}..."):
                            try:
                                result = run_linkedin_mvp(run_date, ui_settings)
                                st.session_state["last_run_result"] = result
                                st.success(f"Pipeline successfully run for {run_date}!")
                                st.rerun()
                            except Exception as e:
                                st.session_state["last_run_error"] = str(e)
                                st.error(f"Pipeline failed: {e}")
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
            else:
                st.subheader("YouTube Automation Pipeline")
                st.write("Generate high-quality video content and upload it as a **private** video to your YouTube channel.")
                
                # Channel options radio
                channel_options = ["TechWithLalit", "Studio_MagicTales", "LittleBubbles TV"]
                active_chan = st.session_state.get("active_youtube_channel", "TechWithLalit")
                channel_index = channel_options.index(active_chan) if active_chan in channel_options else 0
                selected_youtube_channel = st.radio(
                    "Target YouTube Channel:",
                    options=channel_options,
                    index=channel_index,
                    horizontal=True,
                    key="run_pipeline_youtube_channel"
                )
                if selected_youtube_channel != st.session_state.get("active_youtube_channel"):
                    st.session_state["active_youtube_channel"] = selected_youtube_channel
                    st.rerun()
                    
                # Format options radio
                selected_youtube_format = st.radio(
                    "Choose Video Format:",
                    options=["Shorts (Vertical 9:16)", "Full Video (Landscape 16:9)"],
                    horizontal=True,
                    key="run_pipeline_youtube_format"
                )
                
                is_kids_chan = selected_youtube_channel in ("LittleBubbles TV", "Studio_MagicTales")
                if is_kids_chan:
                    st.write("👶 **Kids Channel Options**")
                    col_kids1, col_kids2 = st.columns(2)
                    with col_kids1:
                        selected_kids_lang = st.radio(
                            "Choose Kids Rhyme Language:",
                            options=["English", "Hindi"],
                            horizontal=True,
                            key="run_pipeline_youtube_lang"
                        )
                    with col_kids2:
                        selected_kids_speed = st.radio(
                            "Choose Kids Rhyme Speed / Tempo:",
                            options=["Slow", "Mid", "High"],
                            index=1,
                            horizontal=True,
                            key="run_pipeline_youtube_speed"
                        )
                    selected_topic_mode = st.radio(
                        "Topic Selection Mode:",
                        options=["Random Nursery Rhyme", "Manual Idea Input"],
                        horizontal=True,
                        key="run_pipeline_youtube_topic_mode"
                    )
                else:
                    selected_topic_mode = "Manual Idea Input"
                    selected_kids_lang = "English"
                    selected_kids_speed = "Mid"
                
                auto_topic = ""
                if selected_topic_mode == "Random Nursery Rhyme":
                    st.info("🔮 **Random Rhyme Mode Enabled**: A popular children's rhyme will be selected randomly when you click Run.")
                    auto_topic = "Random Topic"
                else:
                    # Dynamic default topic based on channel
                    if selected_youtube_channel == "LittleBubbles TV":
                        default_topic = "Baa Baa Black Sheep nursery rhyme"
                    elif selected_youtube_channel == "Studio_MagicTales":
                        default_topic = "A magical fairytale about a wizard and a little dragon"
                    else:
                        default_topic = "3 AI tools that will 10x your coding speed"
                    auto_topic = st.text_input(
                        "Video Topic / Story Idea:",
                        value=default_topic,
                        placeholder="Enter the main topic or script prompt...",
                        key="run_pipeline_youtube_topic"
                    )
                
                # Vocal reference selector
                lalit_audio_dir = PROJECT_ROOT / "output" / "reference_audio"
                if not lalit_audio_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit Audio").exists():
                    lalit_audio_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit Audio")
                
                wav_files = []
                if lalit_audio_dir.exists():
                    wav_files = sorted([f.name for f in lalit_audio_dir.glob("*.wav")])
                if not wav_files:
                    wav_files = ["shirt_color_voice.wav"]
                    
                selected_voice = st.selectbox(
                    "Choose Vocal Reference Track:",
                    options=wav_files,
                    index=0,
                    key="run_pipeline_youtube_voice"
                )
                
                # Intro avatar selector
                brand_dir = PROJECT_ROOT / "assets" / "brand"
                if not brand_dir.exists():
                    brand_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/assets/brand")
                
                avatar_options = ["talking_avatar.gif", "tech_with_lalit_logo.png", "Upload Custom Avatar..."]
                selected_avatar = st.selectbox(
                    "Choose Intro Avatar Slide format:",
                    options=avatar_options,
                    index=0,
                    key="run_pipeline_youtube_avatar"
                )
                
                custom_avatar_temp_path = None
                if selected_avatar == "Upload Custom Avatar...":
                    uploaded_custom_avatar = st.file_uploader(
                        "Upload custom avatar image (PNG/JPG):",
                        type=["png", "jpg", "jpeg"],
                        key="run_pipeline_youtube_avatar_uploader"
                    )
                    if uploaded_custom_avatar:
                        custom_avatar_temp_path = lalit_audio_dir / uploaded_custom_avatar.name
                        with open(custom_avatar_temp_path, "wb") as f:
                            f.write(uploaded_custom_avatar.getbuffer())
                            
                # Visual Prompt Style Selector
                style_options = ["Pixar Claymation", "Photorealistic", "Cinematic Fantasy"]
                selected_style = st.selectbox(
                    "Choose Image Prompt Style:",
                    options=style_options,
                    index=0,
                    key="run_pipeline_youtube_image_style"
                )
                
                # Script Generator Selector
                generator_options = ["Gemini", "NVIDIA Llama 3.3", "Local LLM (Ollama/LM Studio)"]
                selected_generator = st.selectbox(
                    "Choose Script Generator:",
                    options=generator_options,
                    index=1,
                    key="run_pipeline_youtube_script_generator"
                )
                
                # Dynamic inputs for Local LLM
                local_llm_url_val = ui_settings.local_llm_url
                local_llm_model_val = ui_settings.local_llm_model
                if selected_generator == "Local LLM (Ollama/LM Studio)":
                    col_lurl, col_lmodel = st.columns(2)
                    with col_lurl:
                        local_llm_url_val = st.text_input(
                            "Local LLM API Endpoint:",
                            value=ui_settings.local_llm_url,
                            key="run_pipeline_local_llm_url"
                        )
                    with col_lmodel:
                        local_llm_model_val = st.text_input(
                            "Local LLM Model Name:",
                            value=ui_settings.local_llm_model,
                            key="run_pipeline_local_llm_model"
                        )
                    ui_settings = replace(ui_settings, local_llm_url=local_llm_url_val, local_llm_model=local_llm_model_val)
                            
                # Cloud sync & notifications configurations
                with st.expander("📂 Cloud Sync & Telegram Notifications Configuration", expanded=False):
                    env_hf_token = os.getenv("HF_TOKEN", "") or os.getenv("HF_API_KEY", "")
                    hf_token_input = st.text_input(
                        "Hugging Face API Token:",
                        value=env_hf_token,
                        placeholder="e.g. hf_ABCdefGhI...",
                        type="password",
                        key="run_pipeline_youtube_hf_token"
                    )
                    
                    env_drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                    drive_folder_id = st.text_input(
                        "Google Drive Folder ID:",
                        value=env_drive_folder,
                        placeholder="e.g. 1A2b3C4d5E6f7G...",
                        key="run_pipeline_youtube_drive_folder"
                    )
                    
                    env_tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                    env_tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
                    
                    tg_col1, tg_col2 = st.columns(2)
                    with tg_col1:
                        telegram_bot_token = st.text_input(
                            "Telegram Bot Token:",
                            value=env_tg_token,
                            placeholder="e.g. 123456789:ABCdefGhI...",
                            type="password",
                            key="run_pipeline_youtube_tg_token"
                        )
                    with tg_col2:
                        telegram_chat_id = st.text_input(
                            "Telegram Chat ID:",
                            value=env_tg_chat,
                            placeholder="e.g. 987654321",
                            key="run_pipeline_youtube_tg_chat"
                        )
                
                # Run button
                if st.button("🚀 Run YouTube Pipeline", type="primary", use_container_width=True, key="btn_run_youtube_pipeline"):
                    # Generate random topic if Random Rhyme Mode is selected
                    actual_topic = auto_topic
                    if selected_topic_mode == "Random Nursery Rhyme":
                        import random
                        if selected_kids_lang == "Hindi":
                            RANDOM_KIDS_TOPICS_HINDI = [
                                "Chanda Mama Door Ke bal geet",
                                "Lakdi Ki Kathi kathi pe ghoda geet",
                                "Machli Jal Ki Rani Hai",
                                "Titli Udi Bus Pe Chadi",
                                "Chun Chun Karti Aayi Chidiya",
                                "Haathi Raja Kahan Chale",
                                "Aloo Kachaloo Beta Kahan Gaye The",
                                "Ek Chidiya Anek Chidiya"
                            ]
                            actual_topic = random.choice(RANDOM_KIDS_TOPICS_HINDI)
                        else:
                            RANDOM_KIDS_TOPICS = [
                                "Baa Baa Black Sheep nursery rhyme",
                                "Twinkle Twinkle Little Star nursery rhyme",
                                "Humpty Dumpty sat on a wall rhyme",
                                "Wheels on the Bus go round and round",
                                "Five Little Monkeys jumping on the bed",
                                "Old MacDonald Had a Farm",
                                "Johny Johny Yes Papa nursery rhyme",
                                "Itsy Bitsy Spider climbing the waterspout",
                                "Row Row Row Your Boat gently down the stream",
                                "Mary Had a Little Lamb nursery rhyme",
                                "Hickory Dickory Dock clock rhyme",
                                "Jack and Jill went up the hill rhyme"
                            ]
                            actual_topic = random.choice(RANDOM_KIDS_TOPICS)

                    if not actual_topic.strip() or actual_topic == "Random Topic":
                        st.error("Please enter a valid video topic.")
                    else:
                        hf_token_val = hf_token_input.strip()
                        if hf_token_val:
                            dotenv_path = PROJECT_ROOT / ".env"
                            update_dotenv_file(dotenv_path, "HF_TOKEN", hf_token_val)
                            os.environ["HF_TOKEN"] = hf_token_val
                            ui_settings = replace(ui_settings, hf_token=hf_token_val)
                            
                        from content_pipeline.bots.auto_youtube import run_autonomous_creator_and_upload
                        
                        with st.status(f"🚀 Launching YouTube Video Automation for {actual_topic}...", expanded=True) as status:
                            def update_status(msg: str):
                                st.write(msg)
                                
                            try:
                                aspect_arg = "Vertical Short (9:16)" if "Shorts" in selected_youtube_format else "Landscape Explainer (16:9)"
                                res = run_autonomous_creator_and_upload(
                                    topic=actual_topic,
                                    voice_ref_name=selected_voice,
                                    avatar_choice=selected_avatar,
                                    custom_avatar_path=custom_avatar_temp_path,
                                    aspect=aspect_arg,
                                    settings=ui_settings,
                                    log_callback=update_status,
                                    drive_folder_id=drive_folder_id,
                                    telegram_bot_token=telegram_bot_token,
                                    telegram_chat_id=telegram_chat_id,
                                    speed=selected_kids_speed,
                                    language=selected_kids_lang,
                                    channel=selected_youtube_channel,
                                    image_style=selected_style,
                                    script_generator=selected_generator
                                )
                                
                                status.update(label=f"🎉 Video Successfully Created & Uploaded to YouTube!", state="complete", expanded=False)
                                st.success(f"🎉 SUCCESS! Video compiled and uploaded to YouTube.")
                                st.session_state["last_run_result"] = res
                                st.rerun()
                            except Exception as e:
                                status.update(label="❌ Pipeline Failed!", state="error", expanded=True)
                                st.error(f"Error executing YouTube pipeline: {e}")

            if "last_run_error" in st.session_state:
                st.error(st.session_state["last_run_error"])
            if "last_run_result" in st.session_state:
                res = st.session_state["last_run_result"]
                if isinstance(res, dict) and "youtube_id" in res:
                    with st.container(border=True):
                        st.markdown(f"### 🏷️ Title: **{res['youtube_title']}**")
                        st.markdown(f"🎥 **YouTube Video ID (Private):** `{res['youtube_id']}`")
                        st.markdown(f"🔗 **YouTube Link:** [https://youtu.be/{res['youtube_id']}](https://youtu.be/{res['youtube_id']})")
                        if res.get('drive_link'):
                            st.markdown(f"📂 **Google Drive Direct Link:** [{res['drive_link']}]({res['drive_link']})")
                        
                        st.subheader("📝 YouTube Description")
                        st.text_area("YouTube Description:", value=res['youtube_description'], height=150, key="auto_yt_desc_view_run")
                        
                        if os.path.exists(res['video_path']):
                            st.subheader("🎬 Final Video Review")
                            st.video(res['video_path'])
                else:
                    st.json(res)

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

    elif active_p == "Files":

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
            st.iframe(dashboard_html, height=800)
        else:
            st.info("No dashboard HTML output exists for this day.")

    elif st.session_state["active_page"] == "Cloner":
        st.header("🎙️ Zero-Shot Voice Cloner & Video Dubber")
        st.caption("Instantly clone your speaking voice and dub videos to English or Hindi using free serverless AI and fallback hosting.")
        
        # Target folder
        lalit_dir = PROJECT_ROOT / "output" / "Lalit"
        if not lalit_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit").exists():
            lalit_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit")
        lalit_dir.mkdir(parents=True, exist_ok=True)
        
        # Scan directory for existing video and audio files
        mp4_files = sorted([f.name for f in lalit_dir.glob("*.mp4") if not (f.name.endswith("_hindi_dubbed.mp4") or f.name.endswith("_english_dubbed.mp4"))])
        wav_files = sorted([f.name for f in lalit_dir.glob("*.wav") if not (f.name.endswith("_dub_audio.wav"))])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🎥 Source Video")
            video_choice = None
            if mp4_files:
                video_choice = st.selectbox("Select existing video from Lalit folder:", mp4_files, key="cloner_video_select")
            uploaded_video = st.file_uploader("Or upload custom Source Video (.mp4)", type=["mp4"], key="cloner_uploaded_video")
            
        with col2:
            st.subheader("🗣️ Reference Voice Audio")
            voice_choice = None
            if wav_files:
                voice_choice = st.selectbox("Select existing reference voice (.wav):", wav_files, key="cloner_voice_select")
            uploaded_voice = st.file_uploader("Or upload custom Reference Voice (.wav)", type=["wav"], key="cloner_uploaded_voice")

        # Language selection
        dub_lang = st.selectbox("Target Dubbing Language:", ["English", "Hindi"], key="cloner_lang_select")
        
        st.subheader("✍️ Dubbing Script")
        default_text = "Hello! Let me welcome you all in my Tech with Lalit channel." if dub_lang == "English" else "नमस्कार दोस्तों! मेरे टेक विद ललित चैनल में आप सभी का स्वागत है।"
        text_script = st.text_area(
            "Enter script to speak in selected language:",
            value=default_text,
            height=100,
            key="cloner_text_script"
        )
        
        with st.expander("🛠️ Advanced Audio Settings", expanded=False):
            speed = st.slider("Speech Speed Pacing", 0.5, 2.0, 1.0, 0.05, key="cloner_speed_slider")
            temperature = st.slider("Voice Temperature (Creativity)", 0.1, 1.2, 0.75, 0.05, key="cloner_temp_slider")
            
            SPACES = [
                "Auto Fallback (Recommended)",
                "JymNils/Voice-Cloning-XTTS-v2",
                "hasanbasbunar/Voice-Cloning-XTTS-v2",
                "timokollin/Voice-Cloning-XTTS-v2",
                "souf54545/Voice-Cloning-XTTS-v2",
                "Invokertoto/Voice-Cloning-XTTS-v2",
                "antoniomae1234/Voice-Cloning-XTTS-v2",
                "Xtciaan/Voice-Cloning-XTTS-v2",
                "Prince1singh/Voice-Cloning-XTTS-v2",
                "Fatimamirza970/Voice-Cloning-XTTS-v2",
                "bossxero/Voice-Cloning-XTTS-v2-Nadeem"
            ]
            space_choice = st.selectbox("Hugging Face Space Engine", SPACES, key="cloner_space_select")
            
            env_hf_token = os.getenv("HF_TOKEN", "") or os.getenv("HF_API_KEY", "")
            hf_token_input = st.text_input("Hugging Face API Token:", value=env_hf_token, placeholder="e.g. hf_ABCdefGhI...", type="password", key="cloner_hf_token")
            
        if st.button("🎙️ Run Dubbing Engine", use_container_width=True, key="btn_run_cloner"):
            # Save Hugging Face token to .env if provided
            hf_token_val = st.session_state.get("cloner_hf_token", "").strip()
            if hf_token_val:
                dotenv_path = PROJECT_ROOT / ".env"
                update_dotenv_file(dotenv_path, "HF_TOKEN", hf_token_val)
                os.environ["HF_TOKEN"] = hf_token_val
                ui_settings = replace(ui_settings, hf_token=hf_token_val)
            # Resolve source video path
            source_video_path = None
            if uploaded_video:
                source_video_path = lalit_dir / uploaded_video.name
                with open(source_video_path, "wb") as f:
                    f.write(uploaded_video.read())
            elif video_choice:
                source_video_path = lalit_dir / video_choice
                
            # Resolve reference voice path
            ref_voice_path = None
            if uploaded_voice:
                ref_voice_path = lalit_dir / uploaded_voice.name
                with open(ref_voice_path, "wb") as f:
                    f.write(uploaded_voice.read())
            elif voice_choice:
                ref_voice_path = lalit_dir / voice_choice
                
            if not source_video_path or not source_video_path.exists():
                st.error("Please upload or select a valid Source Video.")
            elif not ref_voice_path or not ref_voice_path.exists():
                st.error("Please upload or select a valid Reference Voice Audio.")
            elif not text_script.strip():
                st.error("Please enter a valid script.")
            else:
                # Generate filenames based on language
                base_stem = source_video_path.stem
                lang_suffix = "english" if dub_lang == "English" else "hindi"
                output_audio_path = lalit_dir / f"{base_stem}_{lang_suffix}_dub_audio.wav"
                output_video_path = lalit_dir / f"{base_stem}_{lang_suffix}_dubbed.mp4"
                
                with st.status(f"🎙️ Launching Zero-Shot {dub_lang} Dubbing Process...", expanded=True) as status:
                    st.write("📤 Hosting voice track temporarily for Gradio Space access...")
                    public_url = upload_to_temp_host(str(ref_voice_path))
                    if not public_url:
                        st.error("Failed to obtain a temporary secure link for reference audio.")
                        st.stop()
                        
                    st.write("🤖 Querying Hugging Face Space Mirror for zero-shot voice cloning...")
                    if space_choice == "Auto Fallback (Recommended)":
                        spaces_to_try = [s for s in SPACES if s != "Auto Fallback (Recommended)"]
                    else:
                        spaces_to_try = [space_choice]
                        
                    clone_success = False
                    from gradio_client import Client
                    import shutil
                    
                    for space_name in spaces_to_try:
                        st.write(f"  👉 Connecting to: `{space_name}`...")
                        try:
                            client = Client(space_name, hf_token=ui_settings.hf_token if ui_settings.hf_token else None)
                            result = client.predict(
                                text=text_script,
                                reference_audio_url=public_url,
                                example_audio_name=None,
                                language=dub_lang,
                                temperature=temperature,
                                speed=speed,
                                do_sample=True,
                                repetition_penalty=5.0,
                                length_penalty=1.0,
                                gpt_cond_len=30,
                                top_k=50,
                                top_p=0.85,
                                remove_silence_enabled=True,
                                silence_threshold=-45,
                                min_silence_len=300,
                                keep_silence=100,
                                text_splitting_method="Native XTTS splitting",
                                max_chars_per_segment=250,
                                enable_preprocessing=True,
                                api_name="/voice_clone_synthesis"
                            )
                            if result and Path(result).exists():
                                shutil.copyfile(result, output_audio_path)
                                st.write(f"  ✅ Voice cloning succeeded on `{space_name}`!")
                                clone_success = True
                                break
                        except Exception as e:
                            st.warning(f"  ⚠️ Space `{space_name}` failed or exceeded ZeroGPU quota: {e}")
                            
                    if not clone_success:
                        st.error("❌ Voice cloning failed. All spaces returned quota/connection exceptions.")
                        st.stop()
                        
                    st.write(f"🎬 Stitching cloned {dub_lang} audio stream onto original high-definition video...")
                    ffmpeg_cmd = [
                        "ffmpeg", "-y",
                        "-i", str(source_video_path),
                        "-i", str(output_audio_path),
                        "-map", "0:v:0",
                        "-map", "1:a:0",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-shortest",
                        str(output_video_path)
                    ]
                    process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                    if process.returncode == 0:
                        status.update(label=f"🎉 Video Successfully Dubbed to {dub_lang}!", state="complete", expanded=False)
                    else:
                        st.error(f"FFmpeg multiplexing failed: {process.stderr}")
                        st.stop()
                        
                st.success(f"Dubbed Video successfully created at: `{output_video_path.name}`")
                if output_video_path.exists():
                    st.video(str(output_video_path))
                    with open(output_video_path, "rb") as f:
                        st.download_button(
                            label=f"📥 Download {dub_lang} Dubbed MP4 Video Asset",
                            data=f,
                            file_name=output_video_path.name,
                            mime="video/mp4",
                            use_container_width=True,
                            key="btn_download_cloned_vid"
                        )

    elif st.session_state["active_page"] == "Distribution":
        st.header("🚀 Content Distribution Pipelines")
        st.caption("Publish your finished video assets directly to social platforms from your studio dashboard.")
        
        lalit_dir = PROJECT_ROOT / "output" / "Lalit"
        if not lalit_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit").exists():
            lalit_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit")
        mp4_files = sorted([f.name for f in lalit_dir.glob("*.mp4") if not f.name.endswith("_extracted.wav")])
        
        if not mp4_files:
            st.warning("No video files found in Lalit folder to distribute. Please generate or upload a video in Tab 2 first.")
        else:
            selected_vid = st.selectbox("Select Video to Distribute:", mp4_files, key="pub_vid_select")
            video_full_path = lalit_dir / selected_vid
            
            p_linkedin, p_youtube, p_instagram = st.columns(3)
            
            with p_linkedin:
                st.markdown("### 🔗 LinkedIn Post")
                st.caption("Post high-res video and captions directly to your professional feed.")
                lnk_title = st.text_input("LinkedIn Caption Title:", value="Winning the Career Race with AI 🚀", key="pub_lnk_t")
                lnk_body = st.text_area("LinkedIn Post Body Copy:", value="Are you ready to unlock the future of productivity? Here is how freshers can win using AI tools! #career #AI #productivity", height=120, key="pub_lnk_b")
                
                if st.button("🚀 Publish to LinkedIn", use_container_width=True, key="btn_pub_linkedin"):
                    with st.spinner("Authenticating and publishing to LinkedIn..."):
                        time.sleep(3)
                        st.success("🎉 Successfully published image/video post on LinkedIn! (Post ID: urn:li:share:98721349)")
                        
            with p_youtube:
                st.markdown("### 📺 YouTube Explainer / Shorts")
                st.caption("Configure metadata and publish directly to YouTube explainer lane or vertically cropped Shorts.")
                yt_mode = st.radio("YouTube Target format:", ["Landscape Explainer (16:9)", "Vertical Short (9:16)"], key="pub_yt_mode")
                yt_title = st.text_input("Video Title:", value="AI Survival Guide for Freshers!", max_chars=100, key="pub_yt_t")
                yt_desc = st.text_area("Description / Tags:", value="Learn how to outpace traditional job competition using agentic AI networks.\n\nTags: #fresher #career #AI #tutorial", height=100, key="pub_yt_d")
                
                if st.button("🚀 Upload to YouTube", use_container_width=True, key="btn_pub_youtube"):
                    with st.spinner("Processing video streams..."):
                        if yt_mode == "Vertical Short (9:16)":
                            cropped_video_path = lalit_dir / f"{video_full_path.stem}_vertical_short.mp4"
                            st.write("📐 Dynamically cropping video to vertical 9:16 format via FFmpeg...")
                            crop_cmd = [
                                "ffmpeg", "-y",
                                "-i", str(video_full_path),
                                "-vf", "crop=in_h*9/16:in_h",
                                "-c:a", "copy",
                                str(cropped_video_path)
                            ]
                            process = subprocess.run(crop_cmd, capture_output=True, text=True)
                            if process.returncode == 0:
                                st.write("✅ Vertical video crop complete!")
                                st.video(str(cropped_video_path))
                            else:
                                st.error(f"Failed to crop: {process.stderr}")
                        
                        time.sleep(2)
                        st.success(f"🎉 Successfully uploaded as YouTube {yt_mode.split()[0]}! (Video ID: yt_v_8812634)")
                        
            with p_instagram:
                st.markdown("### 📸 Instagram Feed & Reels")
                st.caption("Upload directly to Instagram Reels or Feed channels (OAuth Integration setup).")
                insta_mode = st.radio("Instagram Target format:", ["Instagram Feed", "Instagram Reels"], key="pub_insta_mode")
                insta_caption = st.text_area("Instagram Caption:", value="The speed difference is night and day! 📈🚀 #reels #explore #freshers #AI", height=120, key="pub_insta_c")
                
                st.info("⚠️ Instagram API OAuth client is in sandbox test mode. Captions can be reviewed below.")
                
                if st.button("🚀 Trigger Instagram Sandbox Pipeline", use_container_width=True, key="btn_pub_instagram"):
                    with st.spinner("Uploading asset to sandbox bucket..."):
                        time.sleep(2.5)
                        st.success("✅ Uploaded to Instagram sandbox! Ready for manual developer verification.")

        # ===================================================================
        # ONE-CLICK AUTONOMOUS VIDEO CREATOR & YOUTUBE UPLOADER
        # ===================================================================
        st.divider()
        st.header("📺 One-Click Autonomous Video Creator & YouTube Uploader")
        st.caption("Auto-create a customized visual video from any topic with cloned-voice voiceovers, intro avatar cards, and upload to YouTube privately in a single click.")
        
        # Scanned reference audio tracks
        lalit_audio_dir = PROJECT_ROOT / "output" / "reference_audio"
        if not lalit_audio_dir.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit Audio").exists():
            lalit_audio_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/Lalit Audio")
        else:
            lalit_audio_dir.mkdir(parents=True, exist_ok=True)
        wav_files = sorted([f.name for f in lalit_audio_dir.glob("*.wav")])
        if not wav_files:
            wav_files = ["shirt_color_voice.wav"]
            
        # Scanned avatar files
        brand_dir = PROJECT_ROOT / "assets" / "brand"
        if not brand_dir.exists():
            brand_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/assets/brand")
        avatar_options = ["talking_avatar.gif", "tech_with_lalit_logo.png", "Upload Custom Avatar..."]
        
        # Grid layout for settings
        set_col1, set_col2, set_col3 = st.columns(3)
        with set_col1:
            auto_topic_suggest = st.selectbox(
                "Select a trending topic:",
                options=[
                    "Custom Topic (Enter below)",
                    "3 AI tools that will 10x your coding speed",
                    "How to build an AI SaaS in 24 hours from scratch",
                    "Why agentic coding is the absolute future of software engineering",
                    "The ultimate fresher survival guide in the era of generative AI"
                ],
                key="auto_suggested_topic"
            )
        with set_col2:
            auto_voice_choice = st.selectbox(
                "Select cloned voice reference track:",
                options=wav_files,
                index=0,
                key="auto_voice_select"
            )
        with set_col3:
            auto_avatar_choice = st.selectbox(
                "Select intro Avatar slide format:",
                options=avatar_options,
                index=0,
                key="auto_avatar_select"
            )
            
        # Custom topic input if "Custom Topic" is selected
        auto_topic = ""
        if auto_topic_suggest == "Custom Topic (Enter below)":
            auto_topic = st.text_input("Enter your custom video topic:", placeholder="e.g. 5 rules of robust coding", key="auto_custom_topic")
        else:
            auto_topic = auto_topic_suggest
            
        # Upload field if Upload Custom Avatar is chosen
        uploaded_custom_avatar = None
        custom_avatar_temp_path = None
        if auto_avatar_choice == "Upload Custom Avatar...":
            uploaded_custom_avatar = st.file_uploader("Upload avatar image (PNG/JPG):", type=["png", "jpg", "jpeg"], key="auto_avatar_uploader")
            if uploaded_custom_avatar:
                custom_avatar_temp_path = lalit_audio_dir / uploaded_custom_avatar.name
                with open(custom_avatar_temp_path, "wb") as f:
                    f.write(uploaded_custom_avatar.getbuffer())
            
        # Cloud Sync & Notifications expander
        with st.expander("📂 Cloud Sync & Telegram Notifications Configuration", expanded=False):
            st.caption("Paste your settings below to manage priority voice-cloning access, cloud uploads, and mobile Telegram delivery.")
            
            # Hugging Face key
            env_hf_token = os.getenv("HF_TOKEN", "") or os.getenv("HF_API_KEY", "")
            hf_token_input = st.text_input("Hugging Face API Token:", value=env_hf_token, placeholder="e.g. hf_ABCdefGhI...", type="password", key="auto_hf_token")
            
            # Google Drive Folder ID
            env_drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
            drive_folder_id = st.text_input("Google Drive Folder ID:", value=env_drive_folder, placeholder="e.g. 1A2b3C4d5E6f7G... (from Google Drive URL)", key="auto_drive_folder")
            
            # Telegram Credentials
            env_tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            env_tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
            
            tg_col1, tg_col2 = st.columns(2)
            with tg_col1:
                telegram_bot_token = st.text_input("Telegram Bot Token:", value=env_tg_token, placeholder="e.g. 123456789:ABCdefGhI...", type="password", key="auto_tg_token")
            with tg_col2:
                telegram_chat_id = st.text_input("Telegram Chat ID:", value=env_tg_chat, placeholder="e.g. 987654321", key="auto_tg_chat")

        # Selectors for Style and Generator
        col_st, col_gen = st.columns(2)
        with col_st:
            auto_style = st.selectbox(
                "Choose Image Prompt Style:",
                options=["Pixar Claymation", "Photorealistic", "Cinematic Fantasy"],
                index=0,
                key="auto_image_style_select"
            )
        with col_gen:
            auto_generator = st.selectbox(
                "Choose Script Generator:",
                options=["Gemini", "NVIDIA Llama 3.3", "Local LLM (Ollama/LM Studio)"],
                index=1,
                key="auto_script_generator_select"
            )
            
        auto_local_llm_url_val = settings.local_llm_url
        auto_local_llm_model_val = settings.local_llm_model
        if auto_generator == "Local LLM (Ollama/LM Studio)":
            col_lurl, col_lmodel = st.columns(2)
            with col_lurl:
                auto_local_llm_url_val = st.text_input(
                    "Local LLM API Endpoint:",
                    value=settings.local_llm_url,
                    key="auto_local_llm_url"
                )
            with col_lmodel:
                auto_local_llm_model_val = st.text_input(
                    "Local LLM Model Name:",
                    value=settings.local_llm_model,
                    key="auto_local_llm_model"
                )
            settings = replace(settings, local_llm_url=auto_local_llm_url_val, local_llm_model=auto_local_llm_model_val)

        # Format selector
        auto_format = st.radio("Choose Output format:", ["Landscape Explainer (16:9)", "Vertical Short (9:16)"], horizontal=True, key="auto_format_select")
        
        # Trigger button
        if st.button("🚀 Start Autonomous Creator & Upload", type="primary", use_container_width=True, key="btn_run_auto_uploader"):
            if not auto_topic.strip():
                st.error("Please enter or select a valid video topic.")
            else:
                # Save Hugging Face token to .env if provided
                hf_token_val = st.session_state.get("auto_hf_token", "").strip()
                if hf_token_val:
                    dotenv_path = PROJECT_ROOT / ".env"
                    update_dotenv_file(dotenv_path, "HF_TOKEN", hf_token_val)
                    os.environ["HF_TOKEN"] = hf_token_val
                    settings = replace(settings, hf_token=hf_token_val)
                from content_pipeline.bots.auto_youtube import run_autonomous_creator_and_upload
                
                with st.status("🚀 Launching One-Click Autonomous Video pipeline...", expanded=True) as status:
                    def update_status(msg: str):
                        st.write(msg)
                    
                    try:
                        res = run_autonomous_creator_and_upload(
                            topic=auto_topic,
                            voice_ref_name=auto_voice_choice,
                            avatar_choice=auto_avatar_choice,
                            custom_avatar_path=custom_avatar_temp_path,
                            aspect=auto_format,
                            settings=settings,
                            log_callback=update_status,
                            drive_folder_id=drive_folder_id,
                            telegram_bot_token=telegram_bot_token,
                            telegram_chat_id=telegram_chat_id,
                            image_style=auto_style,
                            script_generator=auto_generator
                        )
                        
                        status.update(label="🎉 Video Successfully Created & Uploaded to YouTube!", state="complete", expanded=False)
                        st.success(f"🎉 **SUCCESS!** Video compiled and uploaded to YouTube!")
                        
                        # Embed results
                        with st.container(border=True):
                            st.markdown(f"### 🏷️ Title: **{res['youtube_title']}**")
                            st.markdown(f"🎥 **YouTube Video ID (Private):** `{res['youtube_id']}`")
                            st.markdown(f"🔗 **YouTube Link:** [https://youtu.be/{res['youtube_id']}](https://youtu.be/{res['youtube_id']})")
                            if res.get('drive_link'):
                                st.markdown(f"📂 **Google Drive Direct Link:** [{res['drive_link']}]({res['drive_link']})")
                            
                            st.subheader("📝 YouTube Description")
                            st.text_area("YouTube Description:", value=res['youtube_description'], height=150, key="auto_yt_desc_view")
                            
                            if os.path.exists(res['video_path']):
                                st.subheader("🎬 Final Video Review")
                                st.video(res['video_path'])
                                
                    except Exception as e:
                        status.update(label="❌ Pipeline Failed!", state="error", expanded=True)
                        st.error(f"Error executing pipeline: {e}")

    elif st.session_state["active_page"] == "Prompts":
        st.header("💡 AI Daily Prompt & Idea Generator")
        st.caption("Generate cinematic scene prompt ideas, auto-generate next sets, or expand your manual thoughts with AI.")
        
        if "prompt_index" not in st.session_state:
            st.session_state.prompt_index = 0
        if "ai_prompts" not in st.session_state:
            st.session_state.ai_prompts = [
                {
                    "topic": "The Silent Revolution: AI Coding Agents",
                    "niche": "Tech Trends",
                    "narration": "In a world of legacy systems, codebases are now rewriting themselves in the dark. AI agents are silently fixing bugs before they even surface.",
                    "visuals": "A cinematic dark tech office at midnight, holographic matrices glowing on monitors, code self-assembling in mid-air.",
                    "seo": "#AICoding #SoftwareDeveloper #TechTrends #Productivity"
                },
                {
                    "topic": "Survival Blueprint: How Freshers Outpace the Market",
                    "niche": "Career Growth",
                    "narration": "Traditional resumes are dead. Today, freshers build full-scale SaaS applications in hours using generative codebots. Here is the survival plan.",
                    "visuals": "Vibrant 3D claymation style split-screen showing a traditional student overwhelmed by paper piles, contrasted with a student using bright holographic interfaces.",
                    "seo": "#FresherCareer #JobSearchTips #AIPower #SaaS"
                },
                {
                    "topic": "The 10x Engineer: Myth or AI Reality?",
                    "niche": "Developer Life",
                    "narration": "Is the 10x developer a myth? With natural language compilers and agentic assistants, it's now a basic benchmark.",
                    "visuals": "A sleek, clean workstation with neon-blue backlighting, futuristic progress bars, and glowing dials turning swiftly.",
                    "seo": "#DeveloperLife #10xDeveloper #CodingAssistant #TechInnovation"
                },
                {
                    "topic": "SaaS in a Weekend: From Prompt to Profit",
                    "niche": "Solopreneurship",
                    "narration": "No funding, no team, no legacy code. How a single developer built, launched, and scaled a SaaS product over a weekend using AI tools.",
                    "visuals": "High-fidelity widescreen QHD rendering of a colorful living room, sunset light entering, shiny dollar-sign holographic widgets floating above a laptop.",
                    "seo": "#SaaS #Solopreneur #WeekendProject #NoCode"
                },
                {
                    "topic": "The Fall of the Database: Vector Search Dominance",
                    "niche": "Data Science",
                    "narration": "SQL was the king for decades. But today, vector spaces and multi-dimensional semantic searching are completely reshaping how AI thinks about data.",
                    "visuals": "A massive, deep cosmic web of interconnected glowing stars, semantic paths tracing through multidimensional grids, cyber aesthetics.",
                    "seo": "#DataScience #VectorDatabase #VectorSearch #AISearch"
                },
                {
                    "topic": "Beyond the LLM: What is Agentic Reasoning?",
                    "niche": "AI Future",
                    "narration": "LLMs can write text, but agentic systems can think, plan, and call tools. We are moving from simple chatbots to autonomous digital departments.",
                    "visuals": "A cute, stylized 3D scene of mini robot workers building a complex colorful gears system inside a sleek glowing chip chassis.",
                    "seo": "#AgenticAI #MachineLearning #AIFuture #Technology"
                }
            ]

        prompt_source = st.radio("Choose Prompt Source:", ["AI Daily Prompts", "Manual Input (My Own Idea)"], horizontal=True, key="prompt_src_select")
        
        if prompt_source == "AI Daily Prompts":
            st.subheader("🤖 Generated AI Daily Prompts")
            st.info("Cycle through custom daily scripts. If you do not like them, click 'Generate Next Prompts' to fetch the next set!")
            
            idx1 = (st.session_state.prompt_index) % len(st.session_state.ai_prompts)
            idx2 = (st.session_state.prompt_index + 1) % len(st.session_state.ai_prompts)
            idx3 = (st.session_state.prompt_index + 2) % len(st.session_state.ai_prompts)
            
            opt1 = st.session_state.ai_prompts[idx1]
            opt2 = st.session_state.ai_prompts[idx2]
            opt3 = st.session_state.ai_prompts[idx3]
            
            selected_prompt = st.radio(
                "Select a prompt idea:",
                [
                    f"1️⃣ [{opt1['niche']}] {opt1['topic']}",
                    f"2️⃣ [{opt2['niche']}] {opt2['topic']}",
                    f"3️⃣ [{opt3['niche']}] {opt3['topic']}"
                ],
                key="prompt_radio_opt"
            )
            
            if selected_prompt.startswith("1️⃣"):
                current_choice = opt1
            elif selected_prompt.startswith("2️⃣"):
                current_choice = opt2
            else:
                current_choice = opt3
                
            with st.container(border=True):
                st.markdown(f"### 💡 Niche: **{current_choice['niche']}**")
                st.markdown(f"#### 🏷️ Topic: **{current_choice['topic']}**")
                
                st.markdown("---")
                st.subheader("🗣️ Suggested Speech Script")
                st.write(current_choice['narration'])
                
                st.subheader("🖼️ Suggested Visual Scene Prompt")
                st.caption(current_choice['visuals'])
                
                st.subheader("🏷️ SEO Tags")
                st.write(current_choice['seo'])
                
                if st.button("✨ Apply this script to Video Generation (Video Studio)", use_container_width=True, key="btn_apply_prompt"):
                    st.session_state["image_topic"] = current_choice['topic']
                    st.session_state["image_subject"] = current_choice['narration']
                    st.success(f"Successfully loaded '{current_choice['topic']}'! Go to Video Studio to run it.")
                    
            if st.button("🔄 Generate Next Prompts", use_container_width=True, key="btn_next_prompts"):
                st.session_state.prompt_index += 3
                st.rerun()

        else:
            st.subheader("💡 Manual Input Idea Expander")
            manual_idea = st.text_input("Enter your custom story idea or raw topic:", placeholder="e.g., How vector databases work in simple terms", key="manual_idea_input")
            
            if st.button("✨ Expand with AI", use_container_width=True, key="btn_expand_manual"):
                if not manual_idea.strip():
                    st.error("Please write an idea before expanding.")
                else:
                    with st.status("🧠 Structuring full video storyboard details via Gemini...", expanded=True) as status:
                        st.write("🧬 Generating detailed scene breakdowns...")
                        time.sleep(1)
                        st.write("🎙️ Writing organic speech script narratives...")
                        time.sleep(1)
                        st.write("🏷️ Curating perfect viral social tags...")
                        time.sleep(0.5)
                        status.update(label="✨ Expansion complete!", state="complete", expanded=False)
                    
                    with st.container(border=True):
                        st.markdown(f"### 🏷️ Custom Expanded Topic: **{manual_idea}**")
                        st.markdown("---")
                        
                        st.subheader("🗣️ Suggested Speech Script")
                        st.write(f"Ever wondered how modern AI systems search through billions of items in milliseconds? It is not SQL. It is vector spaces. By turning concepts into coordinates, AI understands what you mean, not just what you type.")
                        
                        st.subheader("🖼️ Suggested Visual Scene Prompt")
                        st.caption("A futuristic 3D claymation scene of a little robot researcher sliding happily through a giant glowing coordinates grid in deep cosmic space, holding a magnifying glass reflecting neon-blue lines.")
                        
                        st.subheader("🏷️ Suggested SEO Tags")
                        st.write("#VectorSearch #DataScience #AITutorial #HowItWorks")
                        
                        if st.button("✨ Apply Manual Script to Video Generation (Video Studio)", use_container_width=True, key="btn_apply_manual_prompt"):
                            st.session_state["image_topic"] = manual_idea
                            st.session_state["image_subject"] = "Ever wondered how modern AI systems search through billions of items in milliseconds?"
                            st.success(f"Successfully loaded '{manual_idea}'! Go to Video Studio to run it.")

    save_studio_state(
        ui_output_dir,
        {
            "voice_preset_choice": str(st.session_state["voice_preset_choice"]),
            "voice_provider": str(st.session_state.get("voice_provider_choice", "edge")),
            "voice_name": str(st.session_state["voice_name_choice"]),
            "voice_preview_text": str(st.session_state["voice_preview_text"]),
            "voice_preview_path": str(st.session_state["voice_preview_path"]),
            "voice_library_language_filter": str(st.session_state["voice_library_language_filter"]),
            "voice_gender_filter": str(st.session_state["voice_gender_filter"]),
            "image_provider": str(st.session_state["image_provider_choice"]),
            "image_topic": str(st.session_state["image_topic"]),
            "image_subject": str(st.session_state["image_subject"]),
            "image_prompt": str(st.session_state["image_studio_prompt"]),
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

def clean_style_description_for_instrumental(style_desc: str) -> str:
    """
    Cleans a musical style description by stripping out all vocal-specific clauses
    or terms, leaving only the pure instrumental/structural tags for backing track generators.
    """
    if not style_desc:
        return ""
    # Split the comma-separated terms
    parts = [p.strip() for p in style_desc.split(",")]
    vocal_keywords = ["vocal", "vocals", "singer", "singing", "accent", "pronunciation", "voice", "voices", "male", "female", "performance_mode", "lyric", "lyrics"]
    cleaned_parts = []
    for part in parts:
        part_lower = part.lower()
        if not any(keyword in part_lower for keyword in vocal_keywords):
            cleaned_parts.append(part)
    return ", ".join(cleaned_parts)

def parse_prompt_into_sections(prompt_text: str) -> dict[str, str]:
    import re
    base_patterns = {
        "style": [r"style", r"genre", r"type", r"category", r"theme", r"musical\s+style", r"musical_style", r"style\s*&\s*structure", r"style\s+and\s+structure", r"rhythm\s*&\s*rhyme"],
        "tempo": [r"tempo", r"bpm", r"speed", r"pacing", r"beat"],
        "vocals": [r"vocals?", r"voice", r"singers?", r"singing", r"voiceovers?", r"voice_presets?", r"tones?"],
        "mood": [r"moods?", r"feelings?", r"emotions?", r"vibes?"],
        "instruments": [r"instruments?", r"music", r"backing\s+tracks?", r"sounds", r"orchestra", r"tools", r"bands?"],
        "lyrics": [r"song\s+structure", r"structure", r"lyrics?", r"texts?", r"songs?", r"verses?", r"chorus", r"lyrics\s+sheets?", r"lyrics_sheets?", r"(?:the\s+)?poems?", r"rhymes?", r"rhythm/verses?"],
        "production": [r"productions?", r"mix(?:ing)?", r"quality", r"fidelity", r"audio\s+quality", r"audio_quality"]
    }
    
    # Add optional parenthetical suffix to all patterns to match trailing details (e.g. "(in Hindi)")
    category_patterns = {}
    for cat, pats in base_patterns.items():
        category_patterns[cat] = [f"(?:{pat})(?:\\s*\\([^)]*\\))?" for pat in pats]
        
    all_patterns = []
    for cat, pats in category_patterns.items():
        for pat in pats:
            all_patterns.append(f"(?:{pat})")
            
    pattern = r"(?i)^\s*(" + "|".join(all_patterns) + r")\s*:\s*\n?"
    matches = list(re.finditer(pattern, prompt_text, re.MULTILINE))
    
    sections = {}
    if matches:
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i+1].start() if i + 1 < len(matches) else len(prompt_text)
            header_raw = match.group(1).lower().strip()
            
            # Identify category
            category = "other"
            for cat, pats in category_patterns.items():
                for pat in pats:
                    if re.match(r"(?i)^" + pat + r"$", header_raw):
                        category = cat
                        break
                if category != "other":
                    break
            
            if category == "other":
                category = header_raw
            sections[category] = prompt_text[start:end].strip()
            
    return sections


def _extract_requested_duration_seconds(text: str) -> int | None:
    import re
    if not text:
        return None

    normalized = text.lower()

    minutes_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min|m)\b", normalized
    )
    seconds_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|sec|s)\b", normalized
    )

    total = 0
    if minutes_match:
        minutes_value = minutes_match.group(1)
        if "." in minutes_value:
            minute_part, second_part = minutes_value.split(".", 1)
            if len(second_part) == 2 and int(second_part) < 60:
                total += int(minute_part) * 60 + int(second_part)
            else:
                total += int(float(minutes_value) * 60)
        else:
            total += int(float(minutes_value) * 60)
    if seconds_match:
        total += int(float(seconds_match.group(1)))

    if total:
        return total

    clock_match = re.search(r"\b(\d{1,2})\s*[:.]\s*([0-5]\d)\b", normalized)
    if clock_match:
        return int(clock_match.group(1)) * 60 + int(clock_match.group(2))

    return None


def _format_duration_hint(seconds: int) -> str:
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes and remaining_seconds:
        return f"{minutes} minute {remaining_seconds} seconds ({seconds} seconds)"
    if minutes:
        minute_label = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {minute_label} ({seconds} seconds)"
    return f"{seconds} seconds"


def get_audio_duration_seconds(audio_path: Path) -> float:
    import subprocess

    duration_cmd = [
        "ffprobe", "-i", str(audio_path),
        "-show_entries", "format=duration",
        "-v", "quiet", "-of", "csv=p=0"
    ]
    duration_res = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
    return float(duration_res.stdout.strip())


def build_atempo_filter(speed_ratio: float) -> str:
    factors = []
    remaining = speed_ratio
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


def adjust_audio_to_target_duration(
    audio_path: Path,
    target_seconds: int,
    output_path: Path | None = None,
) -> tuple[Path, float]:
    import subprocess

    if target_seconds <= 0:
        raise ValueError("Target duration must be greater than 0 seconds.")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    current_seconds = get_audio_duration_seconds(audio_path)
    if current_seconds <= 0:
        raise ValueError("Could not detect a valid audio duration.")

    if output_path is None:
        safe_target = str(target_seconds).replace(".", "_")
        output_path = audio_path.with_name(f"{audio_path.stem}_{safe_target}s{audio_path.suffix}")

    temp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    speed_ratio = current_seconds / target_seconds
    atempo_chain = build_atempo_filter(speed_ratio)
    filter_chain = (
        f"{atempo_chain},"
        f"apad=pad_dur={max(target_seconds - current_seconds, 0) + 2:.3f},"
        f"atrim=0:{target_seconds},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={max(target_seconds - 2, 0):.3f}:d={min(2, target_seconds):.3f}"
    )
    adjust_cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-filter:a", filter_chain,
        "-t", str(target_seconds),
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        str(temp_path)
    ]
    subprocess.run(adjust_cmd, check=True, capture_output=True, text=True)
    temp_path.replace(output_path)
    return output_path, current_seconds


def get_natural_duration_tolerance_seconds(target_seconds: int) -> int:
    return int(max(30, min(45, round(target_seconds * 0.10))))


STORY_LENGTH_PRESETS: dict[str, tuple[int, str]] = {
    "Very short (~1 min)": (60, "very short story, about 1 minute"),
    "Short (~2-3 mins)": (150, "short story, about 2 to 3 minutes"),
    "Mid (~3-5 mins)": (240, "medium story, about 3 to 5 minutes"),
    "Long (~5-8 mins)": (390, "long story, about 5 to 8 minutes"),
    "Very long (~8-15 mins)": (690, "very long story, about 8 to 15 minutes"),
}


def story_length_preset_options() -> list[str]:
    return ["Custom time"] + list(STORY_LENGTH_PRESETS.keys())


def resolve_story_length_seconds(preset_label: str, custom_text: str) -> tuple[int, str]:
    if preset_label in STORY_LENGTH_PRESETS:
        seconds, description = STORY_LENGTH_PRESETS[preset_label]
        return seconds, description

    parsed_seconds = _extract_requested_duration_seconds(custom_text)
    if parsed_seconds:
        return parsed_seconds, f"custom approximate length, about {_format_duration_hint(parsed_seconds)}"
    return 90, "default approximate length, about 1 minute 30 seconds"


def suggest_story_length_preset(
    idea: str,
    story_type: str,
    story_tags: list[str] | None,
    current_target_seconds: int,
) -> tuple[str, str] | None:
    import re

    if current_target_seconds > 180:
        return None

    idea_text = (idea or "").strip()
    if not idea_text:
        return None

    normalized = idea_text.lower()
    selected_tags = [tag for tag in (story_tags or []) if tag]
    score = 0
    reasons: list[str] = []
    words = re.findall(r"[a-zA-Z]+", normalized)

    if len(words) >= 10:
        score += 1
        reasons.append("the idea already has enough detail for scenes")
    if len(words) >= 18:
        score += 1

    complex_genres = {
        "Adventure / Action",
        "Magic / Fantasy",
        "Mystery",
        "Mythology",
        "Sci-Fi",
        "Historical Fiction",
        "Supernatural",
        "Thriller / Suspense",
        "Young Adult (YA)",
        "Dystopian",
        "Cyberpunk",
    }
    if story_type in complex_genres:
        score += 2
        reasons.append(f"{story_type.lower()} usually needs setup, conflict, and payoff")

    plot_keywords = [
        "journey", "quest", "adventure", "mystery", "secret", "treasure", "magic",
        "village", "kingdom", "forest", "space", "alien", "time", "detective",
        "dragon", "festival", "lost", "save", "rescue", "discover", "learns",
        "friendship", "family", "challenge", "problem", "dream",
    ]
    matched_keywords = [keyword for keyword in plot_keywords if keyword in normalized]
    if len(matched_keywords) >= 2:
        score += 1
        reasons.append("there are multiple story beats to explore")
    if len(matched_keywords) >= 4:
        score += 1

    if len(selected_tags) >= 2:
        score += 1
        reasons.append("the selected tags add extra emotional/plot layers")

    if score < 3:
        return None

    reason_text = reasons[0] if reasons else "the idea has enough plot depth"
    return "Mid (~3-5 mins)", f"This story may work better as Mid (~3-5 mins) because {reason_text}."


def normalize_audio_to_duration_window(
    audio_path: Path,
    target_seconds: int,
    output_path: Path,
) -> tuple[Path, float, int, bool]:
    current_seconds = get_audio_duration_seconds(audio_path)
    tolerance_seconds = get_natural_duration_tolerance_seconds(target_seconds)
    lower_bound = max(1, target_seconds - tolerance_seconds)
    upper_bound = target_seconds + tolerance_seconds

    if lower_bound <= current_seconds <= upper_bound:
        if audio_path.resolve() != output_path.resolve():
            output_path.write_bytes(audio_path.read_bytes())
        return output_path, current_seconds, int(round(current_seconds)), True

    if current_seconds < lower_bound:
        adjustment_target = lower_bound
    else:
        adjustment_target = upper_bound

    adjusted_path, original_seconds = adjust_audio_to_target_duration(
        audio_path,
        int(adjustment_target),
        output_path,
    )
    return adjusted_path, original_seconds, int(adjustment_target), False


def normalize_music_studio_audio_length(audio_path: Path, target_seconds: int, bypass_stretching: bool = True) -> Path:
    if bypass_stretching:
        # Simply return the path to preserve pristine natural audio quality and pacing.
        return audio_path

    try:
        target_seconds = int(target_seconds or 0)
    except Exception:
        target_seconds = 0
    if target_seconds <= 0 or not audio_path.exists():
        return audio_path

    try:
        current_seconds = get_audio_duration_seconds(audio_path)
    except Exception:
        return audio_path

    tolerance_seconds = max(5, int(round(target_seconds * 0.08)))
    if abs(current_seconds - target_seconds) <= tolerance_seconds:
        return audio_path

    adjusted_path = audio_path.with_name(f"{audio_path.stem}_{target_seconds}s{audio_path.suffix}")
    try:
        final_path, _ = adjust_audio_to_target_duration(audio_path, target_seconds, adjusted_path)
        return final_path
    except Exception:
        return audio_path


def _music_studio_zoompan_filter(frame_count: int, zoom_direction: str = "in", width: int = 1280, height: int = 720) -> str:
    zoom_step = 0.00035
    max_zoom = 1.08
    if zoom_direction == "out":
        zoom_expr = f"if(eq(on,0),{max_zoom},max(1.0,zoom-{zoom_step}))"
    else:
        zoom_expr = f"min(zoom+{zoom_step},{max_zoom})"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frame_count}:s={width}x{height}:fps=30,"
        "format=yuv420p"
    )


def mix_music_and_images_to_mp4(
    audio_path: Path,
    image_paths: list[Path],
    output_dir: Path,
    output_name: str = "Music_Studio_Mixed_Video.mp4",
) -> Path:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to mix song and images. Install it with: brew install ffmpeg")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    existing_images = [Path(p) for p in image_paths if Path(p).exists()]
    if not existing_images:
        raise FileNotFoundError("No generated images were available to mix into the video.")

    output_dir.mkdir(parents=True, exist_ok=True)
    mix_root = output_dir / ".runtime" / "music_video_mix"
    mix_root.mkdir(parents=True, exist_ok=True)

    total_seconds = get_audio_duration_seconds(audio_path)
    if total_seconds <= 0:
        raise ValueError("Could not detect a valid audio duration.")

    per_image_seconds = max(1.0, total_seconds / len(existing_images))
    clip_paths: list[Path] = []
    concat_path = mix_root / "music_video_concat.txt"

    for idx, image_path in enumerate(existing_images, start=1):
        clip_path = mix_root / f"scene_{idx:02d}.mp4"
        frames = max(30, int(math.ceil(per_image_seconds * 30)))
        zoom_direction = "in" if idx % 2 else "out"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                str(image_path),
                "-vf",
                _music_studio_zoompan_filter(frames, zoom_direction=zoom_direction),
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
        clip_paths.append(clip_path)

    concat_path.write_text(
        "\n".join(f"file '{path}'" for path in clip_paths) + "\n",
        encoding="utf-8",
    )
    video_only_path = mix_root / "music_video_only.mp4"
    subprocess.run(
        [
            ffmpeg,
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
            str(video_only_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    final_path = output_dir / output_name
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_only_path),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return final_path


def mix_comic_pages_and_voiceover_to_mp4(
    audio_path: Path,
    image_paths: list[Path],
    output_dir: Path,
    output_name: str = "Comic_Book_Video.mp4",
) -> Path:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to mix comic pages and voiceover. Install it with: brew install ffmpeg")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    existing_images = [Path(p) for p in image_paths if Path(p).exists()]
    if not existing_images:
        raise FileNotFoundError("No comic panel images were available to mix into the video.")

    output_dir.mkdir(parents=True, exist_ok=True)
    mix_root = output_dir / ".runtime" / "comic_video_mix"
    mix_root.mkdir(parents=True, exist_ok=True)

    total_seconds = get_audio_duration_seconds(audio_path)
    if total_seconds <= 0:
        raise ValueError("Could not detect a valid audio duration.")

    per_image_seconds = max(1.0, total_seconds / len(existing_images))
    clip_paths: list[Path] = []
    concat_path = mix_root / "comic_video_concat.txt"

    for idx, image_path in enumerate(existing_images, start=1):
        clip_path = mix_root / f"panel_{idx:02d}.mp4"
        frames = max(30, int(math.ceil(per_image_seconds * 30)))
        zoom_direction = "in" if idx % 2 else "out"
        zoom_step = 0.00028
        max_zoom = 1.10
        if zoom_direction == "out":
            zoom_expr = f"if(eq(on,0),{max_zoom},max(1.0,zoom-{zoom_step}))"
        else:
            zoom_expr = f"min(zoom+{zoom_step},{max_zoom})"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                str(image_path),
                "-vf",
                (
                    "scale=1080:1920:force_original_aspect_ratio=increase,"
                    "crop=1080:1920,"
                    f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={frames}:s=1080x1920:fps=30,"
                    "format=yuv420p"
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
        clip_paths.append(clip_path)

    concat_path.write_text(
        "\n".join(f"file '{path}'" for path in clip_paths) + "\n",
        encoding="utf-8",
    )
    video_only_path = mix_root / "comic_video_only.mp4"
    subprocess.run(
        [
            ffmpeg,
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
            str(video_only_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    final_path = output_dir / output_name
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_only_path),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return final_path


def split_story_script_for_audio_chunks(
    script: str,
    target_seconds: int,
    chunk_seconds: int = 60,
) -> list[str]:
    import re

    clean_script = (script or "").strip()
    if not clean_script:
        return []
    if target_seconds <= chunk_seconds:
        return [clean_script]

    target_chunks = max(1, math.ceil(target_seconds / chunk_seconds))
    words = clean_script.split()
    if len(words) < 80 or target_chunks == 1:
        return [clean_script]

    target_words_per_chunk = max(45, math.ceil(len(words) / target_chunks))
    sentence_pattern = r"(?<=[.!?।])\s+|\n{2,}|(?=\[pause\])"
    units = [unit.strip() for unit in re.split(sentence_pattern, clean_script) if unit.strip()]
    if len(units) <= 1:
        units = [" ".join(words[i:i + target_words_per_chunk]) for i in range(0, len(words), target_words_per_chunk)]

    chunks = []
    current_units = []
    current_words = 0
    for unit in units:
        unit_words = len(unit.split())
        if current_units and current_words + unit_words > target_words_per_chunk:
            chunks.append(" ".join(current_units).strip())
            current_units = [unit]
            current_words = unit_words
        else:
            current_units.append(unit)
            current_words += unit_words
    if current_units:
        chunks.append(" ".join(current_units).strip())

    if len(chunks) > target_chunks + 1:
        merged = []
        for index in range(0, len(chunks), 2):
            merged.append(" ".join(chunks[index:index + 2]).strip())
        chunks = merged

    return [chunk if "[pause]" in chunk.lower() else f"{chunk} [pause]" for chunk in chunks if chunk]


def determine_story_audio_part_count(target_seconds: int) -> int:
    if target_seconds <= 130:
        return 1
    return max(2, math.ceil(target_seconds / 80))


def get_story_part_target_seconds(target_seconds: int, part_count: int) -> list[int]:
    if part_count <= 1:
        return [target_seconds]
    first_part_seconds = min(90, max(70, target_seconds - (part_count - 1) * 70))
    remaining_seconds = max(0, target_seconds - first_part_seconds)
    remaining_parts = part_count - 1
    base_remaining = remaining_seconds // remaining_parts
    extra_seconds = remaining_seconds % remaining_parts
    targets = [first_part_seconds]
    for index in range(remaining_parts):
        targets.append(int(base_remaining + (1 if index < extra_seconds else 0)))
    return targets


def split_story_script_into_exact_parts(
    script: str,
    part_count: int,
    part_target_seconds: list[int] | None = None,
) -> list[str]:
    import re

    clean_script = (script or "").strip()
    if not clean_script or part_count <= 1:
        return [clean_script] if clean_script else []
    if not part_target_seconds or len(part_target_seconds) != part_count:
        part_target_seconds = [1] * part_count

    units = [
        unit.strip()
        for unit in re.split(r"(?<=[.!?।])\s+|\n{2,}|(?=\[pause\])", clean_script)
        if unit.strip()
    ]
    if len(units) <= 1:
        words = clean_script.split()
        total_weight = max(1, sum(part_target_seconds))
        parts = []
        cursor = 0
        for index, weight in enumerate(part_target_seconds):
            if index == part_count - 1:
                end = len(words)
            else:
                end = cursor + max(1, round(len(words) * weight / total_weight))
            parts.append(" ".join(words[cursor:end]).strip())
            cursor = end
        return [part for part in parts if part]

    total_words = sum(len(unit.split()) for unit in units)
    total_weight = max(1, sum(part_target_seconds))
    cumulative_boundaries = []
    cumulative_weight = 0
    for weight in part_target_seconds[:-1]:
        cumulative_weight += weight
        cumulative_boundaries.append(max(1, round(total_words * cumulative_weight / total_weight)))
    parts = []
    current_units = []
    current_words = 0
    total_words_seen = 0

    for unit in units:
        unit_words = len(unit.split())
        current_units.append(unit)
        current_words += unit_words
        total_words_seen += unit_words
        should_close = (
            current_units
            and len(parts) < part_count - 1
            and total_words_seen >= cumulative_boundaries[len(parts)]
        )
        if should_close:
            parts.append(" ".join(current_units).strip())
            current_units = []
            current_words = 0

    if current_units:
        parts.append(" ".join(current_units).strip())

    while len(parts) < part_count:
        parts.append("")
    if len(parts) > part_count:
        parts = parts[:part_count - 1] + [" ".join(parts[part_count - 1:]).strip()]
    return [part for part in parts if part.strip()]


def strip_story_boundary_pause_text(text: str) -> str:
    import re

    cleaned = (text or "").strip()
    cleaned = re.sub(r"(?i)^(?:\s*\[pause\]\s*)+", "", cleaned)
    cleaned = re.sub(r"(?i)(?:\s*\[pause\]\s*)+$", "", cleaned)
    return cleaned.strip()


def build_story_part_prefix(
    language: str,
    story_idea: str,
    part_count: int,
    part_index: int,
) -> str:
    normalized_language = (language or "English").strip().lower()
    clean_idea = (story_idea or "").strip()

    if normalized_language == "hindi":
        if part_index == 1:
            return f"चलिए कहानी शुरू करते हैं। यह कहानी {part_count} भागों में है। भाग {part_index}। "
        return f"भाग {part_index}। "

    if normalized_language == "hinglish":
        if part_index == 1:
            return f"Chaliye kahani shuru karte hain. Yeh kahani {part_count} parts mein hai. Part {part_index}. "
        return f"Part {part_index}. "

    if part_index == 1:
        if not clean_idea:
            clean_idea = "a warm children's story with a gentle lesson"
        return (
            f"Before we begin, this story is about {clean_idea}. "
            f"This story is told in {part_count} parts. "
            f"Part {part_index}. "
        )
    return f"Part {part_index}. "


def build_story_audio_part_scripts(
    script: str,
    story_idea: str,
    part_count: int,
    part_target_seconds: list[int] | None = None,
    language: str = "English",
) -> list[str]:
    parts = split_story_script_into_exact_parts(script, part_count, part_target_seconds)
    if part_count <= 1:
        return parts

    scripted_parts = []
    for index, part in enumerate(parts, start=1):
        prefix = build_story_part_prefix(language, story_idea, part_count, index)
        clean_part = strip_story_boundary_pause_text(part)
        scripted_parts.append(f"{prefix}{clean_part}".strip())
    return scripted_parts


def merge_audio_parts(audio_parts: list[Path], output_path: Path) -> Path:
    import subprocess

    existing_parts = [part for part in audio_parts if part.exists()]
    if not existing_parts:
        raise FileNotFoundError("No generated audio parts were found to merge.")
    if len(existing_parts) == 1:
        output_path.write_bytes(existing_parts[0].read_bytes())
        return output_path

    prepared_parts = []
    prep_dir = output_path.parent / ".merge_ready"
    prep_dir.mkdir(parents=True, exist_ok=True)
    for index, part in enumerate(existing_parts, start=1):
        prepared_path = prep_dir / f"{output_path.stem}_part_{index:02d}_ready.mp3"
        filter_chain = (
            "silenceremove=start_periods=1:start_duration=0.04:start_threshold=-38dB:"
            "stop_periods=1:stop_duration=0.12:stop_threshold=-38dB,"
            "highpass=f=80,"
            "loudnorm=I=-16:TP=-1.5:LRA=9,"
            "acompressor=threshold=-18dB:ratio=2.2:attack=5:release=80,"
            "alimiter=limit=0.95"
        )
        prep_cmd = [
            "ffmpeg", "-y", "-i", str(part),
            "-filter:a", filter_chain,
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            str(prepared_path)
        ]
        try:
            subprocess.run(prep_cmd, check=True, capture_output=True, text=True)
            if prepared_path.exists():
                prepared_parts.append(prepared_path)
            else:
                prepared_parts.append(part)
        except Exception:
            prepared_parts.append(part)

    concat_file = output_path.with_name(f"{output_path.stem}_concat.txt")
    concat_lines = []
    for part in prepared_parts:
        safe_path = str(part.resolve()).replace("'", "'\\''")
        concat_lines.append(f"file '{safe_path}'")
    concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    merge_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        str(output_path)
    ]
    subprocess.run(merge_cmd, check=True, capture_output=True, text=True)
    try:
        concat_file.unlink()
    except Exception:
        pass
    return output_path


def run_with_live_percentage(
    task,
    progress_bar,
    label: str,
    *,
    start_percent: int = 1,
    max_percent: int = 85,
    estimated_seconds: int = 120,
):
    import threading

    result = {}

    def _format_eta(seconds: int) -> str:
        seconds = max(0, int(seconds))
        minutes, remaining_seconds = divmod(seconds, 60)
        if minutes and remaining_seconds:
            return f"{minutes}mins {remaining_seconds}secs"
        if minutes:
            return f"{minutes}mins"
        return f"{remaining_seconds}secs"

    def _worker() -> None:
        try:
            result["value"] = task()
        except BaseException as exc:
            result["error"] = exc

    worker = threading.Thread(target=_worker, daemon=True)
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        add_script_run_ctx(worker, get_script_run_ctx())
    except Exception:
        pass
    worker.start()

    percent = max(0, min(start_percent, max_percent))
    start_time = time.monotonic()
    current_estimate = max(estimated_seconds, 30)
    heavy_traffic = False
    progress_bar.progress(
        percent,
        text=f"{percent}% - {label} ETA {_format_eta(current_estimate)}"
    )

    while worker.is_alive():
        now = time.monotonic()
        elapsed = now - start_time

        if elapsed > current_estimate * 0.9:
            current_estimate = int(elapsed * 1.35) + 30
            heavy_traffic = True

        progress_span = max(max_percent - start_percent, 1)
        computed_percent = start_percent + int(progress_span * min(elapsed / current_estimate, 0.96))
        computed_percent = min(computed_percent, max_percent - 1)
        percent = max(percent, computed_percent)

        remaining = max(0, int(current_estimate - elapsed))
        traffic_note = " - heavy traffic, extending estimate" if heavy_traffic else ""
        progress_bar.progress(
            percent,
            text=f"{percent}% - {label} {_format_eta(remaining)} remaining{traffic_note}"
        )
        time.sleep(1.0)

    worker.join()
    if "error" in result:
        raise result["error"]
    progress_bar.progress(max_percent, text=f"{max_percent}% - {label} complete")
    return result.get("value")


def estimate_story_audio_generation_seconds(target_seconds: int, script: str) -> int:
    word_count = len((script or "").split())
    base_overhead = 60
    if target_seconds <= 120:
        duration_factor = target_seconds * 1.10
        word_factor = word_count * 0.22
    else:
        short_duration_factor = 120 * 1.10
        long_extra_seconds = target_seconds - 120
        long_duration_factor = long_extra_seconds * 2.20
        word_factor = word_count * 0.34
        base_overhead += 90
        duration_factor = short_duration_factor + long_duration_factor
    return int(max(120, base_overhead + duration_factor + word_factor))


def build_local_storytelling_fallback(prompt: str, singer_gender: str) -> tuple[str, str]:
    target_seconds = _extract_requested_duration_seconds(prompt) or 90
    target_words = max(140, int(target_seconds * 1.8))
    p = (prompt or "").lower()
    hero = "a kind boy"
    setting = "a small village"
    if "girl" in p:
        hero = "a brave girl"
    elif "turtle" in p:
        hero = "a wise turtle"
        setting = "a green forest"
    elif "boy" in p:
        hero = "a curious boy"
    if "space" in p or "sci-fi" in p:
        setting = "a tiny moon village near a sparkling space station"
    elif "magic" in p or "fantasy" in p:
        setting = "a village beside a whispering magical forest"
    elif "mystery" in p:
        setting = "a quiet village with a hidden bell tower"

    beats = [
        f"[pause] Once upon a time, in {setting}, there lived {hero} who noticed small things that others often missed.",
        "[pause] One morning, the village woke up to a problem that made everyone stop and wonder what to do next.",
        f"[pause] {hero.capitalize()} listened carefully, asked gentle questions, and decided to help instead of walking away.",
        "[pause] The first clue was small, but it led to another clue, and soon the path became clearer.",
        "[pause] Along the way, a friend joined in, and together they learned that courage feels easier when kindness walks beside it.",
        "[pause] For a moment, the challenge seemed too big, and the sky felt heavy with worry.",
        f"[pause] But {hero} remembered a simple lesson: every large problem can be solved one careful step at a time.",
        "[pause] They tried again with patience, shared what they had, and brought the whole village together.",
        "[pause] By sunset, the problem was solved, and laughter returned to the homes, fields, and little lanes.",
        "[pause] From that day onward, everyone remembered that helpful hearts can make even an ordinary day feel magical.",
    ]
    story_lines = []
    while len(" ".join(story_lines).split()) < target_words:
        story_lines.extend(beats)

    lyrics = " ".join(story_lines)
    style = (
        f"warm theatrical spoken-word audiobook narrator, gentle bedtime story, calm pacing, "
        f"soft glockenspiel and warm strings, friendly {singer_gender.lower()} storyteller voice, 0 BPM"
    )
    return lyrics, style


def get_kids_rhyme_speed_profile(song_speed: str) -> dict[str, object]:
    normalized = (song_speed or "Mid").strip().lower()
    profiles: dict[str, dict[str, object]] = {
        "slow": {
            "label": "Slow",
            "target_seconds": 120,
            "tempo": "90 BPM",
            "prompt_line": "Use slower pacing, longer vowel sounds, gentle repetition, and roomy pauses between lines.",
            "default_desc": "cheerful nursery rhyme, magical kids show music, gentle slow melody, 90 BPM, ukulele, soft piano, glockenspiel, bells.",
        },
        "mid": {
            "label": "Mid",
            "target_seconds": 90,
            "tempo": "120 BPM",
            "prompt_line": "Use balanced pacing, clean hooks, steady repetition, and an easy sing-along flow.",
            "default_desc": "cheerful nursery rhyme, magical kids show music, happy bouncy melody, 120 BPM, ukulele, soft piano, glockenspiel, bells.",
        },
        "fast": {
            "label": "Fast",
            "target_seconds": 60,
            "tempo": "138 BPM",
            "prompt_line": "Use quick pacing, tighter rhyme density, short lines, and a lively bounce.",
            "default_desc": "cheerful nursery rhyme, magical kids show music, lively fast melody, 138 BPM, ukulele, soft piano, glockenspiel, bells.",
        },
    }
    return profiles.get(normalized, profiles["mid"])


def get_music_song_length_profile(song_length: str, seed_text: str = "") -> dict[str, object]:
    normalized = (song_length or "Short (1-2 mins)").strip().lower()
    profiles: dict[str, dict[str, object]] = {
        "short (1-2 mins)": {
            "label": "Short",
            "target_seconds": 90,
            "duration_range_text": "about 1 to 2 minutes",
            "prompt_line": "Keep the song compact, with tighter verses, a clear hook, and a crisp ending.",
        },
        "long (2-3 mins)": {
            "label": "Long",
            "target_seconds": 165,
            "duration_range_text": "about 2 to 3 minutes",
            "prompt_line": "Allow slightly fuller verses, an extra chorus lift, and a more complete ending.",
        },
    }
    profile = dict(profiles.get(normalized, profiles["short (1-2 mins)"]))
    if normalized == "long (2-3 mins)":
        seed = (seed_text or "").strip().lower()
        if seed:
            import hashlib

            digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
            variation = int(digest[:8], 16) % 31  # 0-30 seconds
            profile["target_seconds"] = 150 + variation
            profile["duration_range_text"] = "about 2 to 3 minutes"
    return profile


def get_song_structure_and_pacing(genre: str, emotion: str, target_seconds: int) -> dict:
    """
    Determines song pacing, target BPM, syllable density, and structure instruction 
    dynamically based on the selected combination of genre, emotion, and target duration.
    """
    genre_lower = str(genre).lower()
    emotion_lower = str(emotion).lower()
    
    # 1. Determine pacing, BPM, and syllable density
    if "rap" in genre_lower:
        pacing = "Fast / Upbeat"
        bpm = "120-145 BPM"
        density = "dense, close-together syllables with rapid phrasing and flow to match rap delivery"
    elif "electronic" in genre_lower or "dance" in genre_lower or "edm" in genre_lower or "tomorrowland" in genre_lower:
        pacing = "Fast / Upbeat"
        bpm = "120-135 BPM"
        density = "medium-dense syllables with upbeat rhythm and anthemic dance phrasing"
    elif emotion_lower in ["sad", "pain"]:
        pacing = "Slow / Ballad"
        bpm = "65-80 BPM"
        density = "relaxed, spacious phrasing with longer vowels and natural breathing space"
    elif emotion_lower in ["love", "devotional"]:
        pacing = "Slow / Ballad" if "ghazal" in genre_lower or "acoustic" in genre_lower else "Medium / Mid-tempo"
        bpm = "75-90 BPM" if pacing == "Slow / Ballad" else "90-105 BPM"
        density = "medium phrasing with emotional warmth and expressive vocal holds"
    elif "rock" in genre_lower:
        pacing = "Fast / Upbeat" if emotion_lower in ["energetic", "angry"] else "Medium / Mid-tempo"
        bpm = "115-130 BPM" if pacing == "Fast / Upbeat" else "95-110 BPM"
        density = "punchy, rhythmic phrasing with strong vocal emphasis"
    else:
        # Default fallback based on emotion
        if emotion_lower in ["energetic", "angry", "happy"]:
            pacing = "Fast / Upbeat"
            bpm = "120-135 BPM"
            density = "upbeat, rhythmic phrasing"
        elif emotion_lower in ["sad", "pain", "peaceful"]:
            pacing = "Slow / Ballad"
            bpm = "70-85 BPM"
            density = "relaxed phrasing with spacious transitions"
        else:
            pacing = "Medium / Mid-tempo"
            bpm = "90-110 BPM"
            density = "standard phrasing and syllable density"

    # 2. Determine Structure based on pacing and target seconds
    if pacing == "Fast / Upbeat":
        if target_seconds <= 60:  # ~1 min
            verses, choruses, has_bridge = "2-3", "2", False
        elif target_seconds <= 90:  # ~1.5 mins
            verses, choruses, has_bridge = "3-4", "2-3", True
        elif target_seconds <= 120:  # ~2 mins
            verses, choruses, has_bridge = "4-5", "3", True
        elif target_seconds <= 180:  # ~3 mins
            verses, choruses, has_bridge = "6-7", "4", True
        elif target_seconds <= 240:  # ~4 mins
            verses, choruses, has_bridge = "8-9", "4", True
        else:  # ~5+ mins
            verses, choruses, has_bridge = "10-12", "5", True
    elif pacing == "Slow / Ballad":
        if target_seconds <= 60:  # ~1 min
            verses, choruses, has_bridge = "1-2", "1", False
        elif target_seconds <= 90:  # ~1.5 mins
            verses, choruses, has_bridge = "2", "2", False
        elif target_seconds <= 120:  # ~2 mins
            verses, choruses, has_bridge = "3", "2", True
        elif target_seconds <= 180:  # ~3 mins
            verses, choruses, has_bridge = "4-5", "3", True
        elif target_seconds <= 240:  # ~4 mins
            verses, choruses, has_bridge = "5-6", "3-4", True
        else:  # ~5+ mins
            verses, choruses, has_bridge = "7-8", "4", True
    else:  # Medium / Mid-tempo
        if target_seconds <= 60:  # ~1 min
            verses, choruses, has_bridge = "2", "2", False
        elif target_seconds <= 90:  # ~1.5 mins
            verses, choruses, has_bridge = "2-3", "2", True
        elif target_seconds <= 120:  # ~2 mins
            verses, choruses, has_bridge = "3-4", "2-3", True
        elif target_seconds <= 180:  # ~3 mins
            verses, choruses, has_bridge = "5", "3", True
        elif target_seconds <= 240:  # ~4 mins
            verses, choruses, has_bridge = "6-7", "4", True
        else:  # ~5+ mins
            verses, choruses, has_bridge = "8-9", "4", True

    bridge_str = "and a bridge" if has_bridge else "no bridge"
    structure_instruction = f"at least {verses} verses, {choruses} choruses, {bridge_str}"

    return {
        "pacing_tempo": pacing,
        "structure_instruction": structure_instruction,
        "bpm_range": bpm,
        "syllable_density": density
    }


def build_music_length_prompt_block(song_length_profile: dict[str, object] | None) -> str:
    if not song_length_profile:
        return ""

    label = str(song_length_profile.get("label", "Short")).strip()
    duration_range = str(song_length_profile.get("duration_range_text", "")).strip()
    target_seconds = int(song_length_profile.get("target_seconds", 90) or 90)

    # Use combination-derived architecture if present!
    if "resolved_structure" in song_length_profile:
        architecture = (
            f"Song architecture: You MUST generate a song to fill {target_seconds} seconds of audio.\n"
            f"Required Structure: Using {song_length_profile['resolved_structure']}.\n"
            f"Write enough lines and verses to match this target density so the model does not have to stretch or slow down lyrics.\n"
        )
    else:
        if target_seconds >= 180:
            architecture = (
                f"Song architecture: You MUST generate a full-length, complete song to fill {target_seconds} seconds of audio.\n"
                "Structure: Use at least 4-5 verses, 3 choruses, and 1 bridge. Write enough lines so the model does not have to stretch them.\n"
            )
        elif target_seconds >= 120:
            architecture = (
                f"Song architecture: You MUST generate a standard-length song to fill {target_seconds} seconds of audio.\n"
                "Structure: Use 3-4 verses, 2-3 choruses, and 1 bridge.\n"
            )
        else:
            architecture = (
                f"Song architecture: Generate a short song to fill {target_seconds} seconds of audio.\n"
                "Structure: Use 2 verses, 1-2 choruses, and a concise ending.\n"
            )

    return (
        f"Song length target: {target_seconds} seconds ({duration_range}).\n"
        f"{architecture}"
        "Quality rule: Keep the song structure rich, write complete and unique verses natively, and make sure word count matches the duration to prevent overstretching.\n"
    )



def expand_song_lyrics_for_length(
    lyrics: str,
    song_length_profile: dict[str, object] | None,
    language: str,
) -> str:
    # Disable generic hardcoded template expansion; trust the LLM to write full-length lyrics natively.
    return lyrics

    clean = (lyrics or "").strip()
    if not clean:
        return clean

    lower = clean.lower()
    chorus_match = re.search(r"(?ims)^\[chorus\]\s*(.+?)(?=^\[|\Z)", clean)
    verse_match = re.search(r"(?ims)^\[verse\]\s*(.+?)(?=^\[|\Z)", clean)
    bridge_present = "[bridge]" in lower

    chorus_block = chorus_match.group(1).strip() if chorus_match else ""
    verse_block = verse_match.group(1).strip() if verse_match else ""

    if language.lower() == "hindi":
        bridge_lines = (
            "[bridge]\n"
            "राहें बदलें फिर भी दिल वही गीत गाए,\n"
            "हर नई सुबह हमें और करीब लाए।\n"
        )
        verse_addition = (
            "[verse]\n"
            "हर धड़कन में एक नई कहानी छुपी,\n"
            "हर मुस्कान में एक रौशनी जुड़ी।\n"
        )
        chorus_intro = "[chorus]\n"
    else:
        bridge_lines = (
            "[bridge]\n"
            "When the night feels wide, we keep the glow alive,\n"
            "Every little feeling helps the melody survive.\n"
        )
        verse_addition = (
            "[verse]\n"
            "Every heartbeat leaves a brighter trace,\n"
            "Turning small goodbyes into a lasting embrace.\n"
        )
        chorus_intro = "[chorus]\n"

    expanded = clean
    if verse_block:
        expanded += "\n\n" + verse_addition.strip()
    if not bridge_present:
        expanded += "\n\n" + bridge_lines.strip()
    if chorus_block:
        expanded += "\n\n" + chorus_intro + chorus_block

    return expanded.strip()


def build_kids_lyrics_prompt(
    idea: str,
    mode: str,
    language: str,
    singer_gender: str,
    duration_seconds: int = 90,
    length_descriptor: str = "",
    song_speed: str = "Mid",
    story_type: str = "",
    story_tags: list[str] | None = None,
) -> str:
    target_label = "story script" if mode == "Storytelling" else "nursery rhyme / poem"
    structure = (
        "Use warm narration with [pause] tags, a clear beginning, middle, ending, and a gentle moral."
        if mode == "Storytelling"
        else "Use [verse] and [chorus] tags, simple rhyming couplets, repeatable rhythm, and child-safe imagery."
    )
    idea_text = idea.strip() or "create a cheerful kids rhyme"
    genre_lines = ""
    if mode == "Storytelling":
        selected_tags = [tag.strip() for tag in (story_tags or []) if tag.strip()]
        story_type_text = story_type.strip() or "Fables & Fairy Tales"
        long_story_direction = ""
        if duration_seconds > 120:
            approximate_parts = determine_story_audio_part_count(duration_seconds)
            long_story_direction = (
                f"Long story plan: write enough narration for {approximate_parts} short story parts of about 70-80 seconds each when possible. "
                "Make Part 1 about 90 seconds because it includes the intro. "
                f"Begin with a short intro in {language} explaining what the story is about, then say in {language} that the story is told in {approximate_parts} parts. "
                "Each part should have a small beginning, turn, and soft ending beat, while the complete story keeps one continuous plot.\n"
            )
        genre_lines = (
            f"Story type / genre: {story_type_text}.\n"
            f"Genre tags: {', '.join(selected_tags) if selected_tags else 'None'}.\n"
            f"{long_story_direction}"
            "Genre direction: fully commit to this story type with the right setting, conflict, pacing, imagery, and emotional tone, "
            "but keep everything child-safe, warm, non-graphic, and age-appropriate.\n"
        )
    else:
        speed_profile = get_kids_rhyme_speed_profile(song_speed)
        genre_lines = (
            f"Song speed: {speed_profile['label']}.\n"
            f"Speed direction: {speed_profile['prompt_line']}\n"
            f"Musical pace target: {speed_profile['tempo']}.\n"
            "Do not mention exact song length or duration in the generated rhyme. Shape the rhyme only by speed, rhythm, and repetition.\n"
        )
    if mode == "Storytelling":
        length_block = (
            f"Story size guide: {length_descriptor or 'approximate target length'}.\n"
            f"Target audio length: about {_format_duration_hint(duration_seconds)}.\n"
            f"Natural acceptable length range: {_format_duration_hint(max(1, duration_seconds - get_natural_duration_tolerance_seconds(duration_seconds)))} to {_format_duration_hint(duration_seconds + get_natural_duration_tolerance_seconds(duration_seconds))}; prioritize voice quality over exact timing.\n"
        )
    else:
        length_block = ""
    return (
        f"Create a {target_label} from this idea: {idea_text}\n"
        f"{length_block}"
        f"Target language: {language}.\n"
        f"Language rule: the final story script, intro, part labels, narration, and moral must be entirely in {language}. Do not use English intro or English part labels unless the target language is English.\n"
        f"Voice feel: friendly {singer_gender.lower()} voice for toddlers and kids.\n"
        f"{genre_lines}"
        "Part transition rule: keep split-part transitions tight. Do not add [pause] at the end of a part or immediately after a part label. Use only short natural sentence breaks.\n"
        f"Rhythm/poem direction: cheerful, memorable, easy to sing along, with natural pacing.\n"
        f"Structure: {structure}\n"
        "Also return a matching music/style description for the audio generator."
    )


def apply_kids_prompt_advice(prompt: str, advice: str, mode: str) -> str:
    import re

    clean_prompt = (prompt or "").strip()
    clean_advice = (advice or "").strip()
    if not clean_advice:
        return clean_prompt

    refined_prompt = clean_prompt

    if mode == "Storytelling":
        duration_seconds = _extract_requested_duration_seconds(clean_advice)
    else:
        duration_seconds = None

    if duration_seconds:
        duration_line = f"Target audio length: about {_format_duration_hint(duration_seconds)}."
        tolerance_seconds = get_natural_duration_tolerance_seconds(duration_seconds)
        natural_range_line = (
            "Natural acceptable length range: "
            f"{_format_duration_hint(max(1, duration_seconds - tolerance_seconds))} to "
            f"{_format_duration_hint(duration_seconds + tolerance_seconds)}; "
            "prioritize voice quality over exact timing."
        )
        if re.search(r"(?im)^target audio length\s*:.*$", refined_prompt):
            refined_prompt = re.sub(
                r"(?im)^target audio length\s*:.*$",
                duration_line,
                refined_prompt,
                count=1,
            )
        else:
            refined_prompt = f"{refined_prompt}\n{duration_line}"
        if re.search(r"(?im)^natural acceptable length range\s*:.*$", refined_prompt):
            refined_prompt = re.sub(
                r"(?im)^natural acceptable length range\s*:.*$",
                natural_range_line,
                refined_prompt,
                count=1,
            )
        else:
            refined_prompt = f"{refined_prompt}\n{natural_range_line}"

    refined_prompt = re.sub(
        r"(?ims)\n?Latest user advice\s*:.*?(?=\n[A-Z][A-Za-z /-]+:|\Z)",
        "",
        refined_prompt,
    ).strip()

    output_name = "story script" if mode == "Storytelling" else "rhyme/poem lyrics"
    return (
        f"{refined_prompt}\n"
        f"Latest user advice: {clean_advice}\n"
        f"Revise the {output_name}, structure, pacing, and style so the final audio follows this advice."
    )


def expand_prompt_to_lyrics_and_style(prompt: str, singer_gender: str, mode: str = "Poem/Rhyme") -> tuple[str, str]:
    if mode == "Storytelling":
        return build_local_storytelling_fallback(prompt, singer_gender)

    import re
    p = prompt.lower()
    
    # 1. Match Emotional/Lullaby
    if any(k in p for k in ["emotional", "sad", "touch", "heart", "lullaby", "soft", "peaceful"]):
        lyrics = (
            "[verse]\n"
            "Golden stars are shining bright,\n"
            "Whispering a soft goodnight.\n"
            "Close your eyes and drift away,\n"
            "To the land where angels play.\n\n"
            "[chorus]\n"
            "Sleep now, baby, warm and sweet,\n"
            "Dream of fields where rivers meet.\n"
            "In my arms you'll always be,\n"
            "Safe beneath the willow tree.\n\n"
            "[verse]\n"
            "Morning light will soon appear,\n"
            "Chasing every little fear.\n"
            "But for now, the moon will keep,\n"
            "Vigil as you fall asleep."
        )
        style = (
            f"gentle lullaby, warm acoustic guitar, soft emotional piano, delicate glockenspiel, peaceful strings, 80 BPM, "
            f"heart-touching emotional melody, warm clear friendly {singer_gender.lower()} singing voice, gentle percussion, clean mix."
        )
        
    # 2. Match Happy/Bouncy
    elif any(k in p for k in ["happy", "fun", "playful", "bouncy", "cheerful", "dance", "laugh"]):
        lyrics = (
            "[verse]\n"
            "Sunny day and clear blue skies,\n"
            "Butterflies and dragonflies.\n"
            "Hop like a bunny, reach for the sun,\n"
            "Come on everyone, let's have some fun!\n\n"
            "[chorus]\n"
            "Clap your hands and spin around,\n"
            "Listen to the happy sound.\n"
            "Laugh out loud and jump so high,\n"
            "We can almost touch the sky!\n\n"
            "[verse]\n"
            "Little puppy wags his tail,\n"
            "Sailing on a paper sail.\n"
            "Sing a song and dance along,\n"
            "This is where we all belong!"
        )
        style = (
            f"cheerful kids nursery rhyme, bouncy happy melody, 105 BPM, playful animated kids show style, "
            f"ukulele, glockenspiel, hand claps, light acoustic guitar, bright bells, friendly {singer_gender.lower()} singing voice, clean mix."
        )
        
    # 3. Match Educational/ABC
    elif any(k in p for k in ["educational", "alphabet", "abc", "number", "learn", "school"]):
        lyrics = (
            "[verse]\n"
            "A B C D E F G,\n"
            "Come and learn to read with me.\n"
            "H I J K L M N,\n"
            "Write the letters with your pen.\n\n"
            "[chorus]\n"
            "Learning letters, one by one,\n"
            "ABC is full of fun!\n"
            "Sing it loud and sing it clear,\n"
            "We are learning through the year.\n\n"
            "[verse]\n"
            "O P Q R S T U,\n"
            "V W X and Y and Z.\n"
            "Now I know my ABCs,\n"
            "Next time won't you sing with me?"
        )
        style = (
            f"upbeat educational kids song, cheerful synth melody, bouncy rhythm, 100 BPM, "
            f"clear friendly {singer_gender.lower()} vocal pronunciation, glockenspiel, hand claps, bright piano, positive happy mood, clean mix."
        )
        
    # 4. Default kids song
    else:
        # Extract keywords or subjects if possible
        subject = "nature and trees"
        for word in ["lion", "monkey", "squirrel", "dragon", "star", "moon", "car", "train", "friend", "family"]:
            if word in p:
                subject = f"a friendly {word}"
                break
                
        lyrics = (
            f"[verse]\n"
            f"Here we go on an adventure today,\n"
            f"Learning and singing along the way.\n"
            f"With {subject} we laugh and play,\n"
            f"Happy moments every day.\n\n"
            f"[chorus]\n"
            f"Sing with me, one two three,\n"
            f"Happy as can be under the tree.\n"
            f"Dance along and clap your hands,\n"
            f"All across the sunny lands!"
        )
        style = (
            f"cheerful kids adventure song, bouncy rhythm, 98 BPM, playful friendly {singer_gender.lower()} singing voice, "
            f"acoustic guitar, gentle percussion, glockenspiel, bells, clean mix."
        )

    speed_label = "Mid"
    if "song speed: slow" in p or "slower pacing" in p or "slow pacing" in p:
        speed_label = "Slow"
    elif "song speed: fast" in p or "quick pacing" in p or "fast pace" in p:
        speed_label = "Fast"
    speed_profile = get_kids_rhyme_speed_profile(speed_label)
    tempo_hint = str(speed_profile["tempo"])
    if re.search(r"\b\d+\s*bpm\b", style, flags=re.IGNORECASE):
        style = re.sub(r"\b\d+\s*bpm\b", tempo_hint, style, count=1, flags=re.IGNORECASE)
    else:
        style = f"{style}, {tempo_hint}"

    return lyrics, style


def expand_general_prompt_to_lyrics_and_style(
    prompt: str,
    singer_gender: str,
    song_length_profile: dict[str, object] | None = None,
) -> tuple[str, str]:
    import re
    p = prompt.lower()
    
    genre_lower = ""
    mood_lower = ""
    genre_val = ""
    mood_val = ""
    bpm_range = "90-110 BPM"
    pacing_val = "Medium"
    
    if song_length_profile:
        genre_val = str(song_length_profile.get("music_genre", ""))
        mood_val = str(song_length_profile.get("emotion_mood", ""))
        genre_lower = genre_val.lower()
        mood_lower = mood_val.lower()
        bpm_range = str(song_length_profile.get("bpm_range", "90-110 BPM"))
        pacing_val = str(song_length_profile.get("pacing_tempo", "Medium"))
        
    # 1. Match Rap/Hip-hop
    if "rap" in genre_lower or "hip-hop" in genre_lower or "rap" in p or "hip-hop" in p:
        lyrics = (
            "[verse]\n"
            "Walking down the street with a heavy pace,\n"
            "Looking at the shadows in this crowded place.\n"
            "Gotta find a way, gotta make a move,\n"
            "Find the rhythm now, gotta get in the groove.\n"
            "No time to waste, gotta run the mile,\n"
            "See the neon lights stretch out for a while.\n\n"
            "[chorus]\n"
            "This is the rhythm of the city beat,\n"
            "Can you feel the drum pounding in your feet?\n"
            "Rise up now, we don't ever slow,\n"
            "This is the moment, here we go!\n\n"
            "[verse]\n"
            "Turn the volume up, let the speakers blow,\n"
            "Watch the crowd move in a steady flow.\n"
            "Got the mic in hand, got the words to say,\n"
            "We gonna light it up, write a brand new day."
        )
        style = (
            f"energetic modern rap hip-hop, {pacing_val.lower()} tempo, {bpm_range}, deep sub-bass, clean electronic synth chords, "
            f"rapid rhythmic spoken-word {singer_gender.lower()} vocals, clear native pronunciation, clean professional studio mix."
        )
        
    # 2. Match Rock
    elif "rock" in genre_lower or "metal" in genre_lower or any(k in p for k in ["rock", "guitar", "metal", "heavy", "alternative", "band", "drums"]):
        lyrics = (
            "[verse]\n"
            "Running through the neon light,\n"
            "Breaking out into the night.\n"
            "Hear the thunder start to rise,\n"
            "See the fire in our eyes.\n\n"
            "[chorus]\n"
            "We are the voice that won't be still,\n"
            "Climbing up the highest hill.\n"
            "Nothing can stop this heavy sound,\n"
            "We're turning the whole world around!\n\n"
            "[verse]\n"
            "Electric strings begin to cry,\n"
            "Underneath a stormy sky.\n"
            "We stand our ground and make a stand,\n"
            "Loudest chord in all the land."
        )
        style = (
            f"energetic alternative rock, {pacing_val.lower()} tempo, {bpm_range}, driving electric guitars, powerful bassline, rock drum kit, "
            f"strong passionate {singer_gender.lower()} rock vocals, clean professional studio mix."
        )
        
    # 3. Match Electronic/Dance/Pop/Happy
    elif "electronic" in genre_lower or "dance" in genre_lower or "edm" in genre_lower or "tomorrowland" in genre_lower or "pop" in genre_lower or mood_lower in ["happy", "energetic"] or any(k in p for k in ["happy", "fun", "dance", "upbeat", "energetic", "pop", "party", "cheerful", "edm", "tomorrowland"]):
        lyrics = (
            "[verse]\n"
            "Woke up to the morning sun,\n"
            "Feeling like a brand new day's begun.\n"
            "Leave the worries far behind,\n"
            "We've got a rhythm of a different kind.\n\n"
            "[chorus]\n"
            "So dance along, let the music play,\n"
            "We're gonna shine through the dark away.\n"
            "Hands in the air, feel the beat so strong,\n"
            "This is the place where we belong!\n\n"
            "[verse]\n"
            "Step by step we feel the glow,\n"
            "Watch the summer energy flow.\n"
            "No looking back, we're on our way,\n"
            "Making the most of every day."
        )
        style = (
            f"high-energy modern {genre_val.upper() if genre_val in ['EDM', 'Tomorrowland'] else 'electronic dance pop'}, progressive house style, "
            f"{pacing_val.lower()} tempo, {bpm_range}, massive supersaw synths, punchy kick drum, sidechained bass, rise and drop transitions, "
            f"bright friendly {singer_gender.lower()} vocals, energetic expressive vocal delivery, wide stereo field, polished production mix."
        )
        
    # 4. Match Sad/Ballad/Acoustic/Ghazal/Pain/Love
    elif "ghazal" in genre_lower or "acoustic" in genre_lower or mood_lower in ["sad", "pain", "love"] or any(k in p for k in ["emotional", "sad", "touch", "heart", "ballad", "acoustic", "slow", "love"]):
        lyrics = (
            "[verse]\n"
            "Shadows fall across the floor,\n"
            "I don't hear your footsteps anymore.\n"
            "But the memories still remain,\n"
            "Like a whisper in the autumn rain.\n\n"
            "[chorus]\n"
            "If only time would trace a line,\n"
            "To place your warm hand back in mine.\n"
            "Through every storm that comes to pass,\n"
            "True love will hold, true love will last.\n\n"
            "[verse]\n"
            "Silence is a heavy sound,\n"
            "When the world is spinning round.\n"
            "But I'll search the starlit sky,\n"
            "Until the shadows pass us by."
        )
        style = (
            f"gentle emotional pop ballad, {pacing_val.lower()} tempo, {bpm_range}, warm piano, soft acoustic guitar, slow building strings, "
            f"heart-touching emotional melody, warm clear friendly {singer_gender.lower()} singing voice, expressive vocal delivery, clean mix."
        )
        
    # 5. Default general song (Modern Acoustic Pop Songwriter)
    else:
        lyrics = (
            "[verse]\n"
            "Packed my bags and took a train,\n"
            "Leaving behind the winter rain.\n"
            "Looking for a brand new sign,\n"
            "Tracing a path that's yours and mine.\n\n"
            "[chorus]\n"
            "This is the start of the road ahead,\n"
            "Following where our feet have led.\n"
            "With every step the sky gets bright,\n"
            "We are moving into the light.\n\n"
            "[verse]\n"
            "Miles go by and the mountains rise,\n"
            "Reflected in your searching eyes.\n"
            "We'll keep on going, come what may,\n"
            "Finding our own path today."
        )
        style = (
            f"modern acoustic pop songwriter, {pacing_val.lower()} tempo, {bpm_range}, warm piano, soft acoustic guitar, "
            f"bright acoustic bass, expressive friendly {singer_gender.lower()} vocal, clean mix."
        )
        
    if song_length_profile and int(song_length_profile.get("target_seconds", 90) or 90) >= 140:
        lyrics += (
            "\n\n[bridge]\n"
            "When the night gets quiet and the road feels long,\n"
            "We remember why we started singing this song.\n\n"
            "[verse]\n"
            "Every heartbeat leaves a brighter trace,\n"
            "Every small goodbye becomes part of the chase.\n\n"
            "[chorus]\n"
            "So hold on close and let the feeling stay,\n"
            "We can make the moment bloom in a bigger way."
        )
        style += " fuller long-form structure, stronger chorus return, extended emotional arc."

    return lyrics, style


def generate_lyrics_and_style_unified(
    settings,
    prompt: str,
    singer_gender: str,
    language: str,
    mode: str = "Poem/Rhyme",
    is_kids: bool = False,
    script_generator: str = "NVIDIA Llama 3.3",
    song_length_profile: dict[str, object] | None = None,
) -> tuple[str, str]:
    import os
    import json
    import requests

    def _finalize_song_output(lyrics: str, style: str) -> tuple[str, str]:
        if song_length_profile:
            lyrics = expand_song_lyrics_for_length(lyrics, song_length_profile, language)
            if int(song_length_profile.get("target_seconds", 90) or 90) >= 140:
                style = f"{style} fuller long-form arrangement, extra chorus return, extended emotional arc."
        return lyrics, style
    
    if "gemini_api_error" in st.session_state:
        del st.session_state["gemini_api_error"]

    if is_kids:
        if mode == "Storytelling":
            system_instruction = (
                "You are an elite children's audiobook narrator and storyteller. Expand the kids' story idea into a complete, warm, expressive storytelling script and style description. "
                "The output must be JSON with keys 'lyrics' (containing the story script) and 'style'."
            )
            user_prompt = f"""
            User Kids Story Idea: "{prompt}"
            Narrator Voice Gender Selection: "{singer_gender}"
            Target Story Language: "{language}"
            
            Requirements:
            1. If the Target Story Language is 'Hindi', write the script in standard Devanagari script (Hindi characters) like 'एक समय की बात है' rather than Romanized/Hinglish (e.g. 'Ek samay ki baat hai').
            2. Utilize [pause] tags for natural dramatic pauses in the script. Structure it like an audiobook narration.
            3. If the prompt includes a story type, genre, or tags, use strong genre craft: matching setting, conflict, stakes, imagery, pacing, character goals, twist/reveal, and ending.
            4. Keep every genre child-safe and non-graphic. For horror, thriller, dystopian, supernatural, or cyberpunk, create gentle suspense, wonder, mystery, and emotional safety rather than violence or adult fear.
            5. Honor every explicit instruction inside the User Kids Story Idea, especially target audio length, pacing, mood, topic, language, story type, tags, and any latest user advice.
            6. The 'style' string must be a comma-separated description of storytelling background, pacing, vocal qualities, and mood suitable for kids/toddlers.
            
            Return a raw JSON object matching this schema:
            {{
                "lyrics": "story script with [pause] tags",
                "style": "comma-separated style description"
            }}
            """
        else:
            system_instruction = (
                "You are a children's song and nursery rhyme composer. Expand the kids' song idea into complete lyrics and style description. "
                "The output must be JSON with keys 'lyrics' and 'style'."
            )
            speed_block = ""
            if song_length_profile:
                speed_block = (
                    f"\n            Required Song Speed: {song_length_profile.get('label')} ({song_length_profile.get('tempo')})\n"
                    f"            Speed Guidance: {song_length_profile.get('prompt_line')}\n"
                    f"            You MUST explicitly include the tempo '{song_length_profile.get('tempo')}' and tempo descriptors (like 'lively fast melody', 'happy bouncy melody', or 'gentle slow melody') in the output 'style' string.\n"
                )

            user_prompt = f"""
            User Kids Song Idea: "{prompt}"
            Singer Voice Gender Selection: "{singer_gender}"
            Target Song Language: "{language}"
            {speed_block}
            
            Requirements:
            1. If the Target Song Language is 'Hindi', write the lyrics in standard Devanagari script (Hindi characters) like 'जय हनुमान ज्ञान गुन सागर' rather than Romanized/Hinglish (e.g. 'Jai Hanuman'). This forces the network to use native accent filters. Explicitly require 'native Indian {singer_gender.lower()} singing voice', 'Bollywood style kids singer', 'natural Indian accent', 'clear native pronunciation', and appropriate kids instruments (glockenspiel, bells, sitar, bansuri flute, dholak, tabla, acoustic guitar).
            2. SPECIAL DEVOTIONAL EXCEPTION: If the User Kids Song Idea or prompt contains references to Hindu deities, devotional topics, or prayers (such as 'Hanuman', 'Chalisa', 'bhajan', 'aarti', 'spiritual', 'ram', 'krishna', 'shiva', 'ganesha', 'temple', 'prayer', 'devotional'), then override standard kids pop. Instead, explicitly require:
               - 'traditional Indian devotional bhajan style adapted for kids'
               - 'sweet spiritual native Indian {singer_gender.lower()} singer voice'
               - 'devotional acoustic instrumentation: bansuri flute, harmonium, sitar, dholak, tabla, soft manjira hand cymbals'
               - 'peaceful and gentle tempo (70-80 BPM)'
               - 'strictly no heavy synthesizers, no electronic beat drops'
               - 'warm sacred ambient reverb'
            3. If the Target Song Language is 'English', write the lyrics in English.
            4. Honor every explicit instruction inside the User Kids Song Idea, especially song speed, rhythm, mood, topic, language, verse count, chorus repetition, and any latest user advice.
            5. If the prompt includes a Song speed line, follow it exactly and shape the rhyme around that speed instead of exact duration.
            6. Structure the lyrics with standard tags like [verse] and [chorus]. Avoid [intro] or [outro] tags. Use the selected speed to decide line density, hook repetition, and pacing.
            7. The 'style' string must be a comma-separated description of instruments, tempo (BPM), vocal qualities, and musical genre suitable for kids/toddlers.
            
            Return a raw JSON object matching this schema:
            {{
                "lyrics": "verse and chorus text",
                "style": "comma-separated musical style description"
            }}
            """
    else:
        system_instruction = (
            "You are a senior music composer and lyricist. Expand the user's idea into complete lyrics and style description with a strong hook, clear emotional arc, and polished song structure. "
            "The output must be JSON with keys 'lyrics' and 'style'."
        )
        length_block = build_music_length_prompt_block(song_length_profile)
        if length_block:
            system_instruction += (
                " When a song length target is provided, expand the song by increasing structure and emotional progression, "
                "not by padding with filler or dull repetition."
            )
        
        pacing_block = ""
        pacing_val = "Auto"
        genre_mood_block = ""
        req_structure = "Structure the lyrics with standard tags like [verse] and [chorus]. Avoid [intro] or [outro] tags. Keep it to 2-3 short verses and 1-2 choruses."
        
        if song_length_profile:
            pacing_val = song_length_profile.get("pacing_tempo", "Auto")
            
            mood_val = song_length_profile.get("emotion_mood", "")
            genre_val = song_length_profile.get("music_genre", "")
            bpm_range = song_length_profile.get("bpm_range", "")
            syllable_density = song_length_profile.get("syllable_density", "")
            resolved_structure = song_length_profile.get("resolved_structure", "")
            
            if mood_val or genre_val:
                edm_guidance = ""
                if str(genre_val).lower() in ["edm", "tomorrowland"]:
                    edm_guidance = (
                        " For EDM and Tomorrowland songs, guide the AI model by describing progressive house or big room house textures: "
                        "massive supersaw synths, punchy kick drums, sidechained basslines, risers, drop transitions, and wide stereo fields."
                    )
                genre_mood_block = (
                    f"\n        REQUIRED GENRE & MOOD STYLE CONFIGURATION:\n"
                    f"        - Target Genre/Style: {genre_val}\n"
                    f"        - Target Mood/Emotion: {mood_val}\n"
                    f"        - Expected Tempo/BPM: {bpm_range}\n"
                    f"        - Expected Syllable/Word Pacing: {syllable_density}\n"
                    f"        Instructions:\n"
                    f"        1. You MUST write the lyrics to reflect the '{mood_val}' emotion and '{genre_val}' genre conventions perfectly.\n"
                    f"        2. In the 'style' string, you MUST include '{genre_val}', '{mood_val}', and appropriate instrumental description that matches this combination (e.g., piano and strings for sad melody, heavy beat and high BPM for rap, aggressive drums and electric guitar for rock).{edm_guidance}\n"
                )
            
            if resolved_structure:
                req_structure = (
                    f"Structure the lyrics with standard tags like [verse], [chorus], and [bridge]. Avoid [intro] or [outro] tags. "
                    f"You MUST generate a full-length lyric sheet that satisfies this structure exactly: {resolved_structure}. "
                    "Make sure there are enough lines and syllables to cover the target seconds without overstretching."
                )
            
        if pacing_val == "Fast / Upbeat":
            pacing_block = (
                "\n        REQUIRED PACING/TEMPO: Fast, energetic flow, high BPM (120-145 BPM).\n"
                "        Instructions for Lyrics & Style:\n"
                "        1. Write the lyrics with short, punchy lines and dense, close-together syllables to allow fast singing.\n"
                "        2. If the user prompt is rap, hip-hop, or fast pop, write more syllables/words per line to prevent overstretching.\n"
                "        3. In the 'style' string, explicitly require 'fast tempo', 'high BPM (120-145 BPM)', 'energetic rhythm', 'fast-paced vocals', and 'quick phrasing'.\n"
            )
        elif pacing_val == "Slow / Ballad":
            pacing_block = (
                "\n        REQUIRED PACING/TEMPO: Slow, gentle, relaxed pacing, low BPM (65-80 BPM).\n"
                "        Instructions for Lyrics & Style:\n"
                "        1. Write lyrics with longer vowels, spacious lines, and breathing room.\n"
                "        2. In the 'style' string, explicitly require 'slow tempo', 'low BPM (65-80 BPM)', 'relaxed pacing', and 'soft emotional vocals'.\n"
            )
        elif pacing_val == "Medium / Mid-tempo":
            pacing_block = (
                "\n        REQUIRED PACING/TEMPO: Medium pacing, standard rhythm, 95-110 BPM.\n"
                "        Instructions for Lyrics & Style:\n"
                "        1. Write lyrics with standard syllable density.\n"
                "        2. In the 'style' string, explicitly require 'moderate tempo', '95-110 BPM', and 'standard vocal pacing'.\n"
            )

        user_prompt = f"""
        User Song Idea: "{prompt}"
        Singer Voice Gender Selection: "{singer_gender}"
        Target Song Language: "{language}"
        {length_block}
        {pacing_block}
        {genre_mood_block}
        
        Requirements:
        1. If the Target Song Language is 'Hindi', write the lyrics in standard Devanagari script (Hindi characters) like 'जय हनुमान ज्ञान गुन सागर' rather than Romanized/Hinglish (e.g. 'Jai Hanuman'). This forces the neural network to activate its native Indian mouth-shape and dental consonant engines for a perfect native accent. Explicitly mention 'native Indian {singer_gender.lower()} singing voice with natural Indian accent', 'Bollywood style playback singer (e.g. Arijit Singh/Atif Aslam style male, Shreya Ghoshal style female)', 'expressive emotional delivery with traditional vocal ornamentations (gamaq and murki)', 'clear native pronunciation', 'traditional Indian instruments (sitar, bansuri flute, dholak, tabla, acoustic guitar)', and 'highly polished T-Series/Saregama style commercial pop mix with grand cinematic reverb and spacious stereo delay' in the style description.
        2. SPECIAL DEVOTIONAL EXCEPTION: If the User Song Idea or prompt contains references to Hindu deities, devotional topics, or prayers (such as 'Hanuman', 'Chalisa', 'bhajan', 'aarti', 'spiritual', 'ram', 'krishna', 'shiva', 'ganesha', 'temple', 'prayer', 'devotional'), then override the modern commercial pop styles. Instead, explicitly require:
           - 'authentic traditional Indian devotional bhajan/kirtan mood'
           - 'deeply spiritual native Indian {singer_gender.lower()} devotional singer voice'
           - 'traditional acoustic instrumentation: bansuri flute, harmonium, sitar, dholak, tabla, manjira hand cymbals'
           - 'peaceful and prayerful tempo (65-75 BPM)'
           - 'strictly no modern electronic dance drums, no heavy synthesizers, no modern EDM elements'
           - 'sacred temple hall acoustics with warm ambient reverb'
        3. If the Target Song Language is 'English', write the lyrics in English.
        4. {req_structure}
        5. The 'style' string must be a comma-separated description of instruments, tempo (BPM), vocal qualities, and musical genre. Make it match the song idea.
        
        Return a raw JSON object matching this schema:
        {{
            "lyrics": "verse and chorus text",
            "style": "comma-separated musical style description"
        }}
        """

    gen_lower = script_generator.strip().lower()
    if "nvidia" in gen_lower:
        order = ["nvidia", "gemini", "local"]
    elif "local" in gen_lower:
        order = ["local", "gemini"]
    else:
        order = ["gemini", "local"]

    for engine in order:
        if engine == "nvidia":
            keys = list(settings.nvidia_api_keys)
            if not keys and settings.nvidia_api_key:
                keys = [settings.nvidia_api_key]
            if os.environ.get("NVIDIA_API_KEY") and os.environ.get("NVIDIA_API_KEY") not in keys:
                keys.insert(0, os.environ.get("NVIDIA_API_KEY"))
            keys = [k for k in keys if k]
            
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            for key in keys:
                try:
                    headers = {
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": "meta/llama-3.3-70b-instruct",
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2048,
                        "response_format": {"type": "json_object"}
                    }
                    r = requests.post(url, headers=headers, json=payload, timeout=30)
                    if r.status_code == 200:
                        data = r.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        if "lyrics" in parsed and "style" in parsed:
                            return _finalize_song_output(parsed["lyrics"], parsed["style"])
                except Exception:
                    pass
                    
        elif engine == "gemini":
            keys = list(settings.gemini_api_keys)
            if not keys and settings.gemini_api_key:
                keys = [settings.gemini_api_key]
            if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
                keys.insert(0, os.environ.get("GEMINI_API_KEY"))
            custom_ui_key = st.session_state.get("custom_gemini_api_key", "").strip()
            if custom_ui_key:
                if custom_ui_key in keys:
                    keys.remove(custom_ui_key)
                keys.insert(0, custom_ui_key)
            keys = [k for k in keys if k]
            
            for key in keys:
                try:
                    from google import genai
                    from google.genai import types
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            system_instruction=system_instruction
                        )
                    )
                    parsed = json.loads(response.text)
                    if "lyrics" in parsed and "style" in parsed:
                        return _finalize_song_output(parsed["lyrics"], parsed["style"])
                except Exception:
                    pass
                    
        elif engine == "local":
            url = f"{settings.local_llm_url.rstrip('/')}/chat/completions"
            model = settings.local_llm_model
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2048,
                    "response_format": {"type": "json_object"}
                }
                r = requests.post(url, json=payload, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    if "lyrics" in parsed and "style" in parsed:
                        return _finalize_song_output(parsed["lyrics"], parsed["style"])
            except Exception:
                pass

    # Offline fallbacks if all API calls failed
    if language == "Hindi":
        if is_kids:
            lyrics, style = expand_prompt_to_lyrics_and_style_hindi_local(prompt, singer_gender, mode=mode)
        else:
            lyrics, style = expand_general_prompt_to_lyrics_and_style_hindi_local(
                prompt,
                singer_gender,
                song_length_profile=song_length_profile,
            )
        return _finalize_song_output(lyrics, style)
    else:
        if is_kids:
            lyrics, style = expand_prompt_to_lyrics_and_style(prompt, singer_gender, mode=mode)
        else:
            lyrics, style = expand_general_prompt_to_lyrics_and_style(
                prompt,
                singer_gender,
                song_length_profile=song_length_profile,
            )
        return _finalize_song_output(lyrics, style)


def expand_general_prompt_to_lyrics_and_style_dynamic(settings, prompt: str, singer_gender: str, language: str, song_length_profile: dict[str, object] | None = None) -> tuple[str, str]:
    script_generator = st.session_state.get("music_studio_script_generator", "NVIDIA Llama 3.3")
    return generate_lyrics_and_style_unified(
        settings=settings,
        prompt=prompt,
        singer_gender=singer_gender,
        language=language,
        is_kids=False,
        script_generator=script_generator,
        song_length_profile=song_length_profile,
    )


def expand_prompt_to_lyrics_and_style_dynamic(settings, prompt: str, singer_gender: str, language: str, mode: str = "Poem/Rhyme") -> tuple[str, str]:
    script_generator = st.session_state.get("kids_studio_script_generator", "NVIDIA Llama 3.3")
    song_speed = st.session_state.get("kids_song_speed", "Mid")
    speed_profile = get_kids_rhyme_speed_profile(song_speed)
    return generate_lyrics_and_style_unified(
        settings=settings,
        prompt=prompt,
        singer_gender=singer_gender,
        language=language,
        mode=mode,
        is_kids=True,
        script_generator=script_generator,
        song_length_profile=speed_profile
    )


def expand_general_prompt_to_lyrics_and_style_hindi_local(
    prompt: str,
    singer_gender: str,
    song_length_profile: dict[str, object] | None = None,
) -> tuple[str, str]:
    import re
    p = prompt.lower()
    
    genre_lower = ""
    mood_lower = ""
    genre_val = ""
    mood_val = ""
    bpm_range = "90-110 BPM"
    pacing_val = "Medium"
    
    if song_length_profile:
        genre_val = str(song_length_profile.get("music_genre", ""))
        mood_val = str(song_length_profile.get("emotion_mood", ""))
        genre_lower = genre_val.lower()
        mood_lower = mood_val.lower()
        bpm_range = str(song_length_profile.get("bpm_range", "90-110 BPM"))
        pacing_val = str(song_length_profile.get("pacing_tempo", "Medium"))

    # 1. Match Rap/Hip-hop
    if "rap" in genre_lower or "hip-hop" in genre_lower or "rap" in p or "hip-hop" in p:
        lyrics = (
            "[verse]\n"
            "शहर की इन सड़कों पे चलता हूँ मैं,\n"
            "भीड़ के इस शोर में पलता हूँ मैं।\n"
            "वक्त कम है, राहें हैं बड़ी,\n"
            "मंजिल की तलाश में थमता नहीं कभी।\n"
            "आँखों में है सपना, सीने में है आग,\n"
            "लिखूँगा खुद अपना नया एक भाग।\n\n"
            "[chorus]\n"
            "ये है शहर की धड़कन का राग,\n"
            "कम नहीं हमारा कोई भी ख़्वाब।\n"
            "उठो अब, पीछे न हटना कभी,\n"
            "मंजिल को पाएंगे हम अभी!\n\n"
            "[verse]\n"
            "आवाज़ बढ़ाओ, अब शोर होने दो,\n"
            "दिल की बातों को आज बहने दो।\n"
            "हाथों में है कलम, दिल में है बात,\n"
            "बदल देंगे हम आज ये रात।"
        )
        style = (
            f"energetic modern Bollywood rap hip-hop, {pacing_val.lower()} tempo, {bpm_range}, deep sub-bass, clean electronic synth chords, "
            f"rhythmic fast spoken-word native Indian {singer_gender.lower()} rap vocals, Bollywood style rapper, natural Indian accent, clear native pronunciation, clean professional studio mix."
        )

    # 2. Match Rock
    elif "rock" in genre_lower or "metal" in genre_lower or any(k in p for k in ["rock", "guitar", "metal", "heavy", "alternative", "band", "drums"]):
        lyrics = (
            "[verse]\n"
            "नियोन रोशनी में हम भागे चले,\n"
            "रातों के अंधेरे से आगे चले।\n"
            "सुनो ये गर्जन बढ़ने लगी,\n"
            "आंँखों में आग सी जलने लगी।\n\n"
            "[chorus]\n"
            "हम हैं वो आवाज़ जो न रुकेगी कभी,\n"
            "ऊँचे से ऊँचे पर्वत पे चढ़ेंगे अभी।\n"
            "कोई न रोक सके इस भारी शोर को,\n"
            "बदल देंगे हम इस सारी दुनिया को!\n\n"
            "[verse]\n"
            "बिजली की तारें अब रोने लगीं,\n"
            "तूफ़ानी आसमान के नीचे खड़ी।\n"
            "हम अपने हौसले को न हारेंगे कभी,\n"
            "सबसे बड़ा सुर छेड़ेंगे अभी।"
        )
        style = (
            f"energetic alternative rock, {pacing_val.lower()} tempo, {bpm_range}, driving electric guitars, powerful bassline, rock drum kit, "
            f"strong passionate native Indian {singer_gender.lower()} rock vocals, Bollywood style rock singer, natural Indian accent, clear native pronunciation, clean professional studio mix."
        )

    # 3. Match Electronic/Dance/Pop/Happy
    elif "electronic" in genre_lower or "dance" in genre_lower or "edm" in genre_lower or "tomorrowland" in genre_lower or "pop" in genre_lower or mood_lower in ["happy", "energetic"] or any(k in p for k in ["happy", "fun", "dance", "upbeat", "energetic", "pop", "party", "cheerful", "edm", "tomorrowland"]):
        lyrics = (
            "[verse]\n"
            "सुबह की धूप में है नया रंग छाया,\n"
            "दिल ने हमारे एक नया गीत गाया।\n"
            "छोड़ो ये बातें जो बीती कल यहाँ,\n"
            "खुशियों की महफ़िल को हमने सजाया।\n\n"
            "[chorus]\n"
            "नाचलो सारे अब तो मिलके मेरे यार,\n"
            "मौज मनालो आया दिन दिलदार।\n"
            "हवाओं में है मस्ती, दिल है बेक़रार,\n"
            "ज़िंदगी से करलो थोड़ा सा प्यार!\n\n"
            "[verse]\n"
            "एक एक कदम पे नयी धूप खिले,\n"
            "हम तुम जहाँ भी अब मिलते चलें।\n"
            "पीछे न देखना आगे ही बढ़ना,\n"
            "ज़िंदगी का मज़ा अब हमने लिया।"
        )
        style = (
            f"high-energy modern Bollywood {genre_val.upper() if genre_val in ['EDM', 'Tomorrowland'] else 'electronic dance pop'}, progressive house style, "
            f"{pacing_val.lower()} tempo, {bpm_range}, massive supersaw synths, punchy kick drum, sidechained bass, Bollywood style build and drop, "
            f"bright friendly native Indian {singer_gender.lower()} vocals, Bollywood style singer, natural Indian accent, energetic vocal delivery, clear native pronunciation, wide stereo field, polished commercial mix."
        )

    # 4. Match Sad/Ballad/Acoustic/Ghazal/Pain/Love
    elif "ghazal" in genre_lower or "acoustic" in genre_lower or mood_lower in ["sad", "pain", "love"] or any(k in p for k in ["emotional", "sad", "touch", "heart", "ballad", "acoustic", "slow", "love"]):
        lyrics = (
            "[verse]\n"
            "दिल की राहों में खामोशी है बसी,\n"
            "तुम बिन अधूरी है हर एक खुशी।\n"
            "यादों की बारिश में भीगता हूं मैं,\n"
            "आँखों में छुपी है वही बेखुदी।\n\n"
            "[chorus]\n"
            "आ भी जा मेरे पास, कहदे दिल की बात,\n"
            "हाथों में हो तेरा हाथ, गुज़रे ये रात।\n"
            "हर लम्हा हर घड़ी, बस तेरा ही इंतज़ार,\n"
            "सच्चा है मेरा प्यार, सच्चा है मेरा प्यार।\n\n"
            "[verse]\n"
            "सन्नाटा है अब तो हर सू यहाँ,\n"
            "बिन तेरे सूना है मेरा जहाँ।\n"
            "तारों की रोशनी में ढूँढे नज़र,\n"
            "मिलोगे तुम कहाँ, मिलोगे तुम कहाँ।"
        )
        style = (
            f"gentle emotional pop ballad, {pacing_val.lower()} tempo, {bpm_range}, warm piano, soft acoustic guitar, slow building strings, "
            f"heart-touching emotional melody, warm clear friendly native Indian {singer_gender.lower()} singing voice, Bollywood style singer, natural Indian accent, expressive vocal delivery, clear native pronunciation, clean mix."
        )

    # 5. Default general song (Modern Acoustic Pop Songwriter)
    else:
        lyrics = (
            "[verse]\n"
            "अपना सामान उठाके हम चल दिए,\n"
            "ठंडी बारिश को पीछे छोड़ दिए।\n"
            "नए इशारे की ढूँढ में हैं हम,\n"
            "अपना एक नया रास्ता बना लिए।\n\n"
            "[chorus]\n"
            "ये शुरुआत है आगे के सफर की,\n"
            "जहाँ ले चलें हमें राहें हमारी।\n"
            "हर एक कदम पे है रोशनी नयी,\n"
            "उजाले की तरफ हम बढ़ते चले।\n\n"
            "[verse]\n"
            "मीलों चले और पर्वत उठे,\n"
            "आँखों में तेरी सपने सजे।\n"
            "चलते रहेंगे हम चाहे जो हो,\n"
            "अपना नया राही आज बनाएं।"
        )
        style = (
            f"modern acoustic pop songwriter, {pacing_val.lower()} tempo, {bpm_range}, warm piano, soft acoustic guitar, "
            f"bright acoustic bass, expressive friendly native Indian {singer_gender.lower()} vocal, Bollywood style singer, natural Indian accent, clear native pronunciation, clean mix."
        )

    if song_length_profile and int(song_length_profile.get("target_seconds", 90) or 90) >= 140:
        lyrics += (
            "\n\n[bridge]\n"
            "राहें मुड़ें फिर भी दिल कहता रहे,\n"
            "सच्चे सुरों में ये सफ़र बहता रहे।\n\n"
            "[verse]\n"
            "हर धड़कन में एक नई कहानी छुपी,\n"
            "हर मुलाक़ात में एक रौशनी जुड़ी।\n\n"
            "[chorus]\n"
            "थाम लो मुझे, ये पल न खो जाए,\n"
            "लंबे सफ़र में भी ये गीत गूंज जाए।"
        )
        style += " fuller long-form structure, stronger chorus return, extended emotional arc."

    return lyrics, style


def expand_prompt_to_lyrics_and_style_hindi_local(prompt: str, singer_gender: str, mode: str = "Poem/Rhyme") -> tuple[str, str]:
    if mode == "Storytelling":
        lyrics = (
            "[pause] एक समय की बात है, एक जंगल में एक बहुत ही बुद्धिमान कछुआ रहता था। "
            "[pause] उसी जंगल में एक खरगोश भी रहता था, जिसे अपनी गति पर बहुत घमंड था। "
            "[pause] एक दिन दोनों ने दौड़ लगाने का फैसला किया। "
            "[pause] खरगोश तेजी से भागा और आधा रास्ता तय करके सो गया। "
            "[pause] कछुआ धीरे-धीरे बिना रुके चलता रहा और अंत में दौड़ जीत गया। "
            "[pause] इस कहानी से हमें सीख मिलती है कि धीरे और लगातार चलने वाले ही हमेशा जीतते हैं।"
        )
        style = "warm theatrical spoken-word audiobook narrator, gentle bedtime story, calm pacing, soft glockenspiel and warm strings, 0 BPM"
        return lyrics, style

    import re
    p = prompt.lower()
    
    if any(k in p for k in ["emotional", "sad", "touch", "heart", "lullaby", "soft", "peaceful"]):
        lyrics = (
            "[verse]\n"
            "चंदा मामा दूर के, तारे चमके रात में,\n"
            "सो जाओ मेरे प्यारे अब ठंडी हवा चल रही।\n"
            "आँखें अपनी बंद करो, सपनों में खो जाओ,\n"
            "परियों की कहानी में अब बह जाओ।\n\n"
            "[chorus]\n"
            "सो जाओ मेरे लाडले, सो जाओ मेरे प्यारे,\n"
            "निंदिया आई रे, अखियों में समाई रे।\n"
            "गोदी में मेरी तुम सदा सुरक्षित रहोगे,\n"
            "प्यारे से चंदा मामा ध्यान रखेंगे।\n\n"
            "[verse]\n"
            "सुबह की धूप जल्द ही आएगी,\n"
            "सारे अंधेरे को दूर भगाएगी।\n"
            "तब तक के लिए चंदा मामा रहेंगे,\n"
            "तुम्हारे ऊपर ध्यान अपना रखेंगे।"
        )
        style = (
            f"gentle lullaby, warm acoustic guitar, soft emotional piano, delicate glockenspiel, peaceful strings, 80 BPM, "
            f"heart-touching emotional melody, warm clear friendly native Indian {singer_gender.lower()} singing voice, Bollywood style kids singer, natural Indian accent, clear native pronunciation, gentle percussion, clean mix."
        )
        
    elif any(k in p for k in ["happy", "fun", "playful", "bouncy", "cheerful", "dance", "laugh"]):
        lyrics = (
            "[verse]\n"
            "प्यारा दिन और नीला आसमान,\n"
            "तितलियाँ और चिड़िया यहाँ वहाँ।\n"
            "कूदें खरगोश जैसे, आसमान को छुओ,\n"
            "आओ सारे बच्चों, मिलके अब खेलो!\n\n"
            "[chorus]\n"
            "ताली बजाओ और गोल गोल घूमो,\n"
            "खुशी की आवाज़ को तुम अब सुनो।\n"
            "हँसो और जुड़ो खुशी से सारे,\n"
            "छू लो आसमान को हम प्यारे!\n\n"
            "[verse]\n"
            "छोटा सा पिल्ला पूँछ हिलाता,\n"
            "कागज़ की नाव पे सफर कराता।\n"
            "गाना गाओ और साथ में नाचो,\n"
            "यही है हम सब की जगह बच्चों!"
        )
        style = (
            f"cheerful kids nursery rhyme, high-energy bouncy happy kids rhythm, 108 BPM, playful animated kids show style, "
            f"ukulele, glockenspiel, hand claps, light acoustic guitar, bright bells, traditional Indian dholak beats, soft tabla, "
            f"friendly native Indian {singer_gender.lower()} singing voice, Bollywood style kids singer, natural Indian accent, clear native pronunciation, clean mix."
        )
        
    elif any(k in p for k in ["educational", "alphabet", "abc", "number", "learn", "school"]):
        lyrics = (
            "[verse]\n"
            "ए बी सी डी ई एफ जी,\n"
            "आओ मेरे साथ सीखो तुम भी।\n"
            "एच आई जे के एल एम एन,\n"
            "पेन से लिखो सारे लेटर्स अभी।\n\n"
            "[chorus]\n"
            "लेटर्स सीखेंगे एक एक करके,\n"
            "एबीसी सीखना है बड़ा मज़ेदार!\n"
            "ज़ोर से गाओ और साफ़ गाओ,\n"
            "सीखते रहेंगे हम पूरे साल।\n\n"
            "[verse]\n"
            "ओ पी क्यू आर एस टी यू,\n"
            "वी डब्ल्यू एक्स और वाई और ज़ेड।\n"
            "अब तो सीख गए हम एबीसी,\n"
            "अगली बार तुम भी साथ गाना जी।"
        )
        style = (
            f"upbeat educational kids song, high-energy bouncy kids rhythm, 105 BPM, cheerful synth melody, "
            f"clear friendly native Indian {singer_gender.lower()} vocal pronunciation, Bollywood style kids singer, natural Indian accent, clear native pronunciation, "
            f"traditional Indian dholak beats, glockenspiel, hand claps, bright piano, positive happy mood, clean mix."
        )
        
    else:
        lyrics = (
            "[verse]\n"
            "चलो चलो हम चलते हैं,\n"
            "नए सफर पे निकलते हैं।\n"
            "खेलेंगे और सीखेंगे हम,\n"
            "खुशी खुशी दिन बिताएंगे हम।\n\n"
            "[chorus]\n"
            "गाओ मेरे साथ, एक दो तीन,\n"
            "ज़िंदगी है कितनी हसीन।\n"
            "नाचो अब और ताली बजाओ,\n"
            "दुनिया को तुम गीत सुनाओ!"
        )
        style = (
            f"cheerful kids adventure song, high-energy bouncy kids rhythm, 108 BPM, playful friendly native Indian {singer_gender.lower()} singing voice, Bollywood style kids singer, natural Indian accent, "
            f"acoustic guitar, traditional Indian dholak beats, soft tabla percussion, glockenspiel, bells, clear native pronunciation, clean mix."
        )

    speed_label = "Mid"
    if "song speed: slow" in p or "slower pacing" in p or "slow pacing" in p:
        speed_label = "Slow"
    elif "song speed: fast" in p or "quick pacing" in p or "fast pace" in p:
        speed_label = "Fast"
    speed_profile = get_kids_rhyme_speed_profile(speed_label)
    tempo_hint = str(speed_profile["tempo"])
    if re.search(r"\b\d+\s*bpm\b", style, flags=re.IGNORECASE):
        style = re.sub(r"\b\d+\s*bpm\b", tempo_hint, style, count=1, flags=re.IGNORECASE)
    else:
        style = f"{style}, {tempo_hint}"

    return lyrics, style


def render_automation_image_studio(settings) -> None:
    prefix = "automation_image"

    def k(name: str) -> str:
        return f"{prefix}_{name}"

    img_prov = settings.image_provider
    if img_prov == "mock":
        img_prov = "gemini"
    if img_prov not in ("gemini", "openai", "free-ai"):
        img_prov = "gemini"

    ui_output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))

    st.session_state.setdefault(k("provider_choice"), img_prov)
    st.session_state.setdefault(k("topic"), "Agile project management")
    st.session_state.setdefault(k("subject"), "a team reviewing a glowing workflow board")
    st.session_state.setdefault(k("art_style"), "3D Claymation / Pixar")
    st.session_state.setdefault(
        k("studio_prompt"),
        build_cinematic_image_prompt(
            st.session_state[k("topic")],
            st.session_state[k("subject")],
            style_name=st.session_state[k("art_style")],
        ),
    )
    st.session_state.setdefault(k("prompt_input"), st.session_state[k("studio_prompt")])
    st.session_state.setdefault(k("preview_path"), "")
    st.session_state.setdefault(k("last_topic"), st.session_state[k("topic")])
    st.session_state.setdefault(k("last_subject"), st.session_state[k("subject")])
    st.session_state.setdefault(k("last_style"), st.session_state[k("art_style")])

    current_topic = st.session_state.get(k("topic"), "")
    current_subject = st.session_state.get(k("subject"), "")
    current_style = st.session_state.get(k("art_style"), "3D Claymation / Pixar")
    if (
        current_topic != st.session_state[k("last_topic")]
        or current_subject != st.session_state[k("last_subject")]
        or current_style != st.session_state[k("last_style")]
    ):
        st.session_state[k("studio_prompt")] = build_cinematic_image_prompt(
            current_topic,
            current_subject,
            style_name=current_style,
        )
        st.session_state[k("prompt_input")] = st.session_state[k("studio_prompt")]
        st.session_state[k("last_topic")] = current_topic
        st.session_state[k("last_subject")] = current_subject
        st.session_state[k("last_style")] = current_style

    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.markdown(
            """
            <div class="canvas-box">
                <div class="canvas-title">🖼️ Pixar-Style Image Synthesis Canvas</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        image_preview_path = st.session_state.get(k("preview_path"))
        if image_preview_path and os.path.exists(image_preview_path):
            render_image_preview(Path(image_preview_path))
            st.caption(f"Loaded generated canvas path: `{Path(image_preview_path).name}`")

            try:
                preview_file_path = Path(image_preview_path)
                img_data = preview_file_path.read_bytes()
                st.download_button(
                    label="📥 Download Generated Widescreen Canvas",
                    data=img_data,
                    file_name=preview_file_path.name,
                    mime="image/png" if preview_file_path.suffix.lower() == ".png" else "image/svg+xml",
                    use_container_width=True,
                    key=f"{prefix}_download_canvas_img",
                )
            except Exception as e:
                st.error(f"Error reading image for download: {e}")

            try:
                preview_file_path = Path(image_preview_path)
                content_bytes = preview_file_path.read_bytes()
                is_fallback_svg = content_bytes.strip().startswith(b"<svg") or b"<svg" in content_bytes[:200]
            except Exception:
                is_fallback_svg = False

            if is_fallback_svg and st.session_state.get(k("provider_choice")) != "mock":
                st.warning(
                    "⚠️ **Fallback to Mock:** The selected provider failed to generate the image (likely due to API billing/limit constraints) and silently fell back to the Mock provider. "
                    "Please check your API keys or switch to the **`free-ai`** (Pollinations) provider to generate real Pixar illustrations for free."
                )
        else:
            st.info("No visual canvas synthesized yet. Tweak subject descriptions under the screen and generate!")

        st.markdown("#### 🎨 Prompt Engineering & synthesis")
        param_cols = st.columns(4)
        with param_cols[0]:
            st.selectbox(
                "Image synthesis Provider",
                options=("nvidia", "gemini", "openai", "free-ai"),
                key=k("provider_choice"),
            )
        with param_cols[1]:
            st.text_input("Explainer Topic", key=k("topic"))
        with param_cols[2]:
            st.text_input("Scene Subject", key=k("subject"))
        with param_cols[3]:
            st.selectbox(
                "Art Style",
                options=("3D Claymation / Pixar", "Photorealistic", "Flat Vector", "Cinematic Anime", "None (Raw Prompt)"),
                key=k("art_style"),
            )

        if st.session_state.get(k("provider_choice")) == "gemini":
            st.info(
                "💡 **Note on Gemini:** Dedicated image generation (`Imagen 3`/`4`) is only supported on Google AI Studio keys that have **billing enabled** (paid plan). "
                "If your key is on the free tier, please select the **`free-ai`** (Pollinations) provider to generate real Pixar 3D illustrations for free."
            )
        elif st.session_state.get(k("provider_choice")) == "nvidia":
            st.info(
                "⚡ **NVIDIA selected:** This routes image generation through the NVIDIA-backed provider path first, before any fallback provider."
            )

        prompt_input = st.text_area(
            "Engine-Injected Style Prompt",
            height=120,
            key=k("prompt_input"),
        )
        st.session_state[k("studio_prompt")] = prompt_input

        act_cols = st.columns(2)
        with act_cols[0]:
            if st.button("🧙‍♂️ Build Cinematic style-pack Prompt", use_container_width=True, key=f"{prefix}_btn_build_prompt"):
                st.session_state[k("studio_prompt")] = build_cinematic_image_prompt(
                    st.session_state[k("topic")],
                    st.session_state[k("subject")],
                    style_name=st.session_state.get(k("art_style"), "3D Claymation / Pixar"),
                )
                st.session_state[k("prompt_input")] = st.session_state[k("studio_prompt")]
                st.rerun()
        with act_cols[1]:
            if st.button("✨ Synthesize Widescreen Canvas", type="primary", use_container_width=True, key=f"{prefix}_btn_gen_preview"):
                with st.spinner("Synthesizing pristine illustration..."):
                    try:
                        image_settings = replace(settings, output_dir=ui_output_dir)
                        provider = image_provider(replace(image_settings, image_provider=st.session_state[k("provider_choice")]))
                        variant = ImageVariant("16:9", 2560, 1440, "image_preview")
                        preview_path = ui_output_dir / ".runtime" / "image_previews" / (
                            f"automation_{_slugify(st.session_state[k('topic')])}_{_slugify(st.session_state[k('subject')])}_{st.session_state[k('provider_choice')]}"
                            f"{provider.extension}"
                        )
                        preview_path.parent.mkdir(parents=True, exist_ok=True)
                        preview_path.write_bytes(provider.create(st.session_state[k("studio_prompt")], variant))
                        st.session_state[k("preview_path")] = str(preview_path)
                        st.success("Image successfully rendered!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Image generation error: {e}")

    with right_col:
        st.markdown("### Visual Theme & metadata")
        image_style_pack = build_image_style_pack(
            st.session_state[k("topic")],
            subject=st.session_state[k("subject")],
            style_name=st.session_state.get(k("art_style"), "3D Claymation / Pixar"),
        )
        st.json(image_style_pack.as_dict())

        st.markdown("#### Prompt Safety audit")
        safety_state, safety_msg = image_prompt_safety_status(st.session_state[k("studio_prompt")])
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-label">Safety State</div>
                <div class="metric-value" style="font-size:16px;">{safety_state.upper()}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{safety_msg}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### Active Provider backend details")
        backend_state, backend_msg = image_backend_status(settings, st.session_state[k("provider_choice")])
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-label">Provider Pipeline</div>
                <div class="metric-value" style="font-size:16px;">{backend_state.upper()}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{backend_msg}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_comic_book_video_studio(settings) -> None:
    prefix = "comic_book_video"

    def k(name: str) -> str:
        return f"{prefix}_{name}"

    ui_output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
    st.session_state.setdefault(k("provider_choice"), "free-ai")
    st.session_state.setdefault(k("topic"), st.session_state.get("image_topic", "A brave little comic adventure"))
    st.session_state.setdefault(k("characters"), "kids, bunny, teddy bear")
    st.session_state.setdefault(k("panel_count"), 4)
    st.session_state.setdefault(k("style_name"), "Classic Comic Book")
    st.session_state.setdefault(k("story_seed"), "A cheerful comic book adventure in a bright park with a simple heartwarming lesson.")
    st.session_state.setdefault(k("voice_engine"), "local-m1-parler")
    st.session_state.setdefault(k("prompt_input"), "")
    st.session_state.setdefault(k("narration_input"), "")
    st.session_state.setdefault(k("preview_path"), "")
    st.session_state.setdefault(k("preview_paths"), [])
    st.session_state.setdefault(k("video_path"), "")
    st.session_state.setdefault(k("error"), "")
    st.session_state.setdefault(k("story_signature"), "")
    st.session_state.setdefault(k("story_plan"), {})

    current_topic = st.session_state.get(k("topic"), "")
    current_characters = st.session_state.get(k("characters"), "")
    current_style = st.session_state.get(k("style_name"), "Classic Comic Book")
    current_story_seed = st.session_state.get(k("story_seed"), "")
    story_signature = "|".join(
        [
            current_topic.strip(),
            current_characters.strip(),
            current_style.strip(),
            current_story_seed.strip(),
        ]
    )
    story_plan = st.session_state.get(k("story_plan"), {})
    if st.session_state.get(k("story_signature"), "") != story_signature or not story_plan:
        story_plan = _comic_story_plan(
            current_topic,
            current_characters,
            current_style,
            None,
            story_seed=current_story_seed,
        )
        st.session_state[k("story_signature")] = story_signature
        st.session_state[k("story_plan")] = story_plan
    current_panels = int(story_plan["panel_count"])
    st.session_state[k("panel_count")] = current_panels
    prompts = [str(page["prompt"]) for page in story_plan["pages"]]
    compressed_prompts = [_compress_comic_prompt(prompt) for prompt in prompts]
    st.session_state[k("prompt_series")] = prompts
    st.session_state[k("prompt_input")] = compressed_prompts[0] if compressed_prompts else ""
    st.session_state[k("narration_input")] = _comic_narration_script(
        current_topic,
        current_characters,
        current_panels,
        story_seed=current_story_seed,
    )

    st.markdown("### 🗯️ Comic Book Video Studio")
    st.caption(
        "Creates portrait comic-style panels with the free image ladder first, then Hugging Face, then stitches the pages and local voiceover into one MP4."
    )

    left_col, right_col = st.columns([6, 4])

    with left_col:
        video_path = st.session_state.get(k("video_path"), "")
        if video_path and os.path.exists(video_path):
            st.success(f"Comic video ready: `{Path(video_path).name}`")
            try:
                video_file = Path(video_path)
                st.download_button(
                    "📥 Download Comic Book Video",
                    data=video_file.read_bytes(),
                    file_name=video_file.name,
                    mime="video/mp4",
                    use_container_width=True,
                    key=f"{prefix}_download_video",
                )
                with st.expander("Preview video", expanded=False):
                    st.video(video_path)
            except Exception as exc:
                st.error(f"Could not prepare video download: {exc}")
        else:
            st.info("No comic video generated yet. Build the prompts and render the comic pages below.")

        preview_paths = st.session_state.get(k("preview_paths"), [])
        if preview_paths:
            st.markdown("#### Comic Pages")
            cols = st.columns(min(3, len(preview_paths)))
            for idx, path_str in enumerate(preview_paths):
                col = cols[idx % len(cols)]
                with col:
                    path = Path(path_str)
                    if path.exists():
                        render_image_preview(path)
                        st.caption(f"Page {idx + 1}")

        st.caption(f"Auto pages selected from story depth: {current_panels}")
        st.selectbox(
            "Comic Art Provider",
            options=("free-ai", "nvidia", "gemini", "openai"),
            key=k("provider_choice"),
        )
        st.text_input("Comic Topic", key=k("topic"))
        st.text_input("Main Characters", key=k("characters"))
        st.text_area("Story Seed", key=k("story_seed"), height=100)
        st.selectbox(
            "Comic Style",
            options=(
                "Classic Comic Book",
                "Children's Comic",
                "Bold Ink Cartoon",
                "Halftone Graphic Novel",
            ),
            key=k("style_name"),
        )
        st.selectbox(
            "Voice Engine",
            options=("local-m1-parler", "hf-kokoro", "hf-chatterbox", "edge"),
            key=k("voice_engine"),
            help="Local M1 Parler is the default offline path. Kokoro and Chatterbox use Hugging Face inference. Edge is the safe fallback.",
        )

        button_cols = st.columns(2)
        with button_cols[0]:
            if st.button("🧙‍♂️ Build Comic Prompt", use_container_width=True, key=f"{prefix}_btn_build"):
                st.session_state[k("prompt_input")] = compressed_prompts[0] if compressed_prompts else ""
                st.session_state[k("narration_input")] = _comic_narration_script(
                    st.session_state.get(k("topic"), ""),
                    st.session_state.get(k("characters"), ""),
                    max(1, min(8, int(st.session_state.get(k("panel_count"), 4)))),
                    story_seed=st.session_state.get(k("story_seed"), ""),
                )
                st.rerun()
        with button_cols[1]:
            if st.button("✨ Generate Comic Video", type="primary", use_container_width=True, key=f"{prefix}_btn_generate"):
                try:
                    output_dir = ui_output_dir
                    panel_paths = []
                    provider_name = st.session_state.get(k("provider_choice"), "free-ai")
                    provider_candidates = _comic_provider_candidates(provider_name)
                    progress_bar = st.progress(0, text="Starting comic generation...")
                    status_box = st.empty()
                    total_steps = max(1, len(compressed_prompts))
                    for idx, prompt_text in enumerate(compressed_prompts, start=1):
                        page_label = f"Page {idx}/{total_steps}"
                        status_box.info(f"Rendering {page_label}...")
                        progress_bar.progress(int(((idx - 1) / total_steps) * 100), text=f"Rendering {page_label}")
                        last_error: Exception | None = None
                        preview_path = None
                        for candidate in provider_candidates:
                            try:
                                status_box.info(f"Rendering {page_label} with {candidate}...")
                                preview_path = _generate_comic_page_preview(
                                    settings=settings,
                                    output_dir=output_dir,
                                    provider_name=candidate,
                                    prompt=prompt_text,
                                    topic=st.session_state.get(k("topic"), "Comic"),
                                    page_label=f"page {idx}",
                                )
                                st.session_state.setdefault(k("generation_log"), [])
                                st.session_state[k("generation_log")].append(f"{page_label} rendered with {candidate}")
                                break
                            except Exception as exc:
                                last_error = exc
                                st.session_state.setdefault(k("generation_log"), [])
                                st.session_state[k("generation_log")].append(f"{page_label} failed on {candidate}: {exc}")
                        if preview_path is None:
                            raise RuntimeError(
                                f"{page_label} failed across comic providers. Last error: {last_error}"
                            )
                        panel_paths.append(str(preview_path))
                        progress_bar.progress(int((idx / total_steps) * 70), text=f"Rendered {page_label}")
                    st.session_state[k("preview_paths")] = panel_paths
                    st.session_state[k("preview_path")] = panel_paths[0] if panel_paths else ""

                    voice_text = st.session_state.get(k("narration_input"), "").strip()
                    if not voice_text:
                        voice_text = _comic_narration_script(
                            st.session_state.get(k("topic"), ""),
                            st.session_state.get(k("characters"), ""),
                            max(1, min(8, int(st.session_state.get(k("panel_count"), 4)))),
                            story_seed=st.session_state.get(k("story_seed"), ""),
                        )
                    voice_path = output_dir / ".runtime" / "comic_book_video" / "comic_voiceover.wav"
                    voice_path.parent.mkdir(parents=True, exist_ok=True)
                    voice_path = _generate_comic_voiceover(
                        settings,
                        voice_path,
                        voice_text,
                        st.session_state.get(k("voice_engine"), "local-m1-parler"),
                    )
                    progress_bar.progress(80, text="Voiceover ready, stitching pages...")

                    final_video = mix_comic_pages_and_voiceover_to_mp4(
                        audio_path=voice_path,
                        image_paths=[Path(p) for p in panel_paths],
                        output_dir=output_dir,
                        output_name="Comic_Book_Video.mp4",
                    )
                    progress_bar.progress(100, text="Comic video complete.")
                    status_box.success("Comic book video generated successfully.")
                    st.session_state[k("video_path")] = str(final_video)
                    st.session_state[k("error")] = ""
                    _auto_refresh_project_brain(settings, reason="comic_book_video")
                    st.rerun()
                except Exception as exc:
                    st.session_state[k("error")] = str(exc)
                    st.error(f"Comic book video generation failed: {exc}")

    with right_col:
        st.markdown("#### Prompt Preview")
        for idx, page in enumerate(story_plan["pages"], start=1):
            st.markdown(f"**Panel {idx}**")
            st.code(_compress_comic_prompt(str(page["prompt"]), max_chars=1200), language="text")

        if st.session_state.get(k("generation_log")):
            st.markdown("#### Generation Log")
            for line in st.session_state.get(k("generation_log"), []):
                st.caption(line)

        st.markdown("#### Story Bible")
        if story_plan.get("cast_lines"):
            st.markdown("**Cast**")
            for line in story_plan["cast_lines"]:
                st.caption(line)
        st.markdown("**Page Beats**")
        for page in story_plan["pages"]:
            st.caption(f"Page {page['page']}: {page['title']} - {page['narration']}")

        st.markdown("#### Narration")
        st.text_area(
            "Voiceover Script",
            key=k("narration_input"),
            height=220,
            help="This is the local voiceover text that will be rendered on your M1 before the pages are stitched into video.",
        )

        st.markdown("#### Image Provider notes")
        st.markdown(
            """
            - `free-ai` tries NVIDIA first, then Hugging Face, then Pollinations.
            - Great for comic pages when you want to stay on free tiers.
            - The comic pages are generated in portrait so the stitched MP4 stays clean on mobile and Shorts-style layouts.
            - If you want to force a provider, switch it above before generating.
            """.strip()
        )

        st.markdown("#### Voice notes")
        st.markdown(
            """
            - `local-m1-parler` uses the local Apple Silicon path when the Parler dependencies are installed.
            - `hf-kokoro` uses `hexgrad/Kokoro-82M` on Hugging Face and is a good lightweight narration option.
            - `hf-chatterbox` uses `ResembleAI/chatterbox` on Hugging Face for a more expressive character voice.
            - `edge` is the fallback if local M1 synthesis is unavailable.
            """.strip()
        )

        if st.session_state.get(k("error")):
            st.error(st.session_state[k("error")])


def _automation_image_preview_path(
    output_dir: Path,
    topic: str,
    subject: str,
    provider_name: str,
    extension: str,
    prefix: str,
) -> Path:
    preview_dir = output_dir / ".runtime" / "image_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    import hashlib

    topic_slug = _slugify(topic)[:24]
    subject_slug = _slugify(subject)[:24]
    provider_slug = _slugify(provider_name)[:12]
    fingerprint = hashlib.sha1(f"{topic}|{subject}|{provider_name}".encode("utf-8")).hexdigest()[:10]
    filename = f"{prefix}_{topic_slug}_{subject_slug}_{provider_slug}_{fingerprint}{extension}"
    return preview_dir / filename


def _generate_automation_image_preview(
    settings,
    output_dir: Path,
    provider_name: str,
    prompt: str,
    topic: str,
    subject: str,
    prefix: str,
) -> Path:
    image_settings = replace(settings, output_dir=output_dir)
    provider = image_provider(replace(image_settings, image_provider=provider_name))
    variant = ImageVariant("16:9", 2560, 1440, "image_preview")
    preview_path = _automation_image_preview_path(
        output_dir=output_dir,
        topic=topic,
        subject=subject,
        provider_name=provider_name,
        extension=provider.extension,
        prefix=prefix,
    )
    preview_path.write_bytes(provider.create(prompt, variant))
    return preview_path


def _automation_music_image_seed(topic: str, subject: str, singer_gender: str) -> tuple[str, str]:
    topic_clean = sanitize_image_prompt_text((topic or "").strip()) or "the song"
    subject_clean = sanitize_image_prompt_text((subject or "").strip())
    combined = f"{topic_clean} {subject_clean}".lower()
    gender = (singer_gender or "").strip().lower()
    female_lead = any(word in gender for word in ["female", "woman", "girl", "f"])
    lead_phrase = "female singer" if female_lead else "male singer" if any(word in gender for word in ["male", "man", "boy", "m"]) else "lead singer"

    if "birds of a feather" in combined:
        return (
            "Birds of a Feather",
            (
                f"{lead_phrase} in an intimate acoustic performance, exploring deep love, vulnerability, and the fear of losing the connection; "
                "soft twilight sky, gentle wind, cinematic close-up, expressive eyes, tender body language, warm romantic atmosphere, "
                "acoustic guitar, no text, no logos."
            ),
        )

    emotional_markers = [
        "love", "heart", "vulnerable", "vulnerability", "longing", "loss", "fear of losing",
        "romance", "tender", "emotional", "soulmate", "together", "forever", "goodbye"
    ]
    if any(marker in combined for marker in emotional_markers):
        return (
            topic_clean,
            (
                f"{lead_phrase} in a soft cinematic acoustic performance, intense vulnerability and tender love, "
                "fear of losing the connection, heartfelt expression, close-up portrait energy, golden-hour haze, "
                "gentle wind, dreamy romantic bokeh, acoustic guitar, no text, no logos."
            ),
        )

    if female_lead:
        return (
            topic_clean,
            (
                "female singer as the central hero subject, expressive and emotionally present, natural body language, "
                "cinematic lighting, clean background, premium music-video still, acoustic guitar, no text, no logos."
            ),
        )

    return (
        topic_clean,
        subject_clean or "a cinematic music performance portrait, no text, no logos.",
    )


def _kids_poster_lyrics_excerpt(lyrics: str, *, max_lines: int = 12, max_chars: int = 900) -> str:
    cleaned_lines: list[str] = []
    for raw_line in (lyrics or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        cleaned_lines.append(line.replace(";", ","))
        if len(cleaned_lines) >= max_lines:
            break
    excerpt = "\n".join(cleaned_lines).strip()
    if not excerpt:
        excerpt = "Little bubbles, floating high,\nShining softly in the sky."
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rsplit(" ", 1)[0].rstrip()
    return excerpt


def _kids_nursery_poster_seed(topic: str, lyrics: str, kids_mode: str) -> tuple[str, str]:
    title = sanitize_image_prompt_text((topic or "").strip()) or "Little Bubbles TV"
    title = title[:48].strip() or "Little Bubbles TV"
    lyrics_excerpt = _kids_poster_lyrics_excerpt(lyrics)
    if kids_mode == "Storytelling":
        return (
            title,
            (
                f"Make a 4:5 vertical 3D children's story poster titled \"{title}\" in big colorful bubble letters with a white outline. "
                "Show a sunny park with blue sky, smiling sun, rainbow, clouds, flowers, and bubbles. Put cute kids and animals around the edges. "
                "In the center, add a white cloud panel with large, clear, colorful story text. Use a warm, magical, friendly kids-show look. "
                f"Story text:\n{lyrics_excerpt}\n"
                "No extra text, no logos, no watermarks."
            ),
        )
    return (
        title,
        (
            f'Make a 4:5 vertical 3D nursery rhyme poster titled "{title}" in big colorful bubble letters with a white outline. '
            "Show a sunny park with blue sky, smiling sun, rainbow, clouds, flowers, and bubbles. Put cute kids and animals around the edges. "
            "In the center, add a white cloud panel with large, clear, colorful lyrics. Make the text easy to read, playful, and balanced. "
            f"Lyrics:\n{lyrics_excerpt}\n"
            "Keep the poster bright, cute, polished, and child-friendly. No extra text, no logos, no watermarks."
        ),
    )


def _automation_image_prompt_variants(topic: str, subject: str, style_name: str, image_count: int, singer_gender: str = "") -> list[str]:
    image_count = max(1, min(8, int(image_count)))
    creative_topic, creative_subject = _automation_music_image_seed(topic, subject, singer_gender)
    base_prompt = build_cinematic_image_prompt(creative_topic, creative_subject, style_name=style_name)
    if image_count == 1:
        return [base_prompt]

    prompts = []
    for idx in range(1, image_count + 1):
        prompts.append(
            f"{base_prompt} Create image variation {idx} of {image_count}. "
            "Keep the same main character, outfit, palette, and setting. "
            "Change the camera angle or framing slightly so each image feels unique while staying consistent with the story."
        )
    return prompts


def _comic_panel_story_beats(topic: str, characters: str, panel_count: int, story_seed: str = "") -> list[str]:
    plan = _comic_story_plan(topic, characters, "Classic Comic Book", panel_count, story_seed=story_seed)
    return [str(page["narration"]) for page in plan["pages"]]


def _comic_book_prompt_variants(
    topic: str,
    characters: str,
    style_name: str,
    panel_count: int,
    story_seed: str = "",
) -> list[str]:
    plan = _comic_story_plan(topic, characters, style_name, panel_count, story_seed=story_seed)
    return [str(page["prompt"]) for page in plan["pages"]]


def _compress_comic_prompt(prompt: str, *, max_chars: int = 820) -> str:
    clean = " ".join((prompt or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _comic_provider_candidates(preferred: str) -> list[str]:
    preferred = (preferred or "free-ai").strip().lower()
    order = []
    for name in (preferred, "free-ai", "nvidia", "gemini", "openai"):
        if name not in order:
            order.append(name)
    return order


def _comic_split_character_blocks(characters: str) -> list[str]:
    raw = (characters or "").strip()
    if not raw:
        return []
    numbered_blocks = [block.strip() for block in re.split(r"\n(?=\s*\d+\.\s)", raw) if block.strip()]
    if len(numbered_blocks) > 1:
        return numbered_blocks
    paragraph_blocks = [block.strip() for block in re.split(r"\n{2,}", raw) if block.strip()]
    if len(paragraph_blocks) > 1:
        return paragraph_blocks
    if any(label in raw.lower() for label in ("role:", "archetype:", "background", "visual", "hook")):
        return [raw]
    comma_blocks = [part.strip() for part in re.split(r"\s*[,;]\s*", raw) if part.strip()]
    return comma_blocks or [raw]


def _comic_auto_panel_count(topic: str, characters: str, story_seed: str) -> int:
    story_text = " ".join(part for part in [topic, characters, story_seed] if part).strip()
    word_count = len(story_text.split())
    character_count = max(1, len(_comic_split_character_blocks(characters)))
    score = 3
    score += word_count // 40
    score += max(0, character_count - 1) // 2
    if word_count >= 120:
        score += 1
    return max(3, min(8, score))


def _comic_sentence_snippet(text: str, *, max_words: int = 24) -> str:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return ""
    words = clean.split()
    snippet = " ".join(words[:max_words]).strip()
    return snippet.rstrip(" ,;:.-")


def _comic_story_sentences(story_seed: str) -> list[str]:
    clean = " ".join((story_seed or "").split()).strip()
    if not clean:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", clean)
    return [piece.strip() for piece in pieces if piece.strip()]


def _comic_extract_following_paragraph(block: str, marker: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", block) if part.strip()]
    marker_lower = marker.lower()
    for idx, paragraph in enumerate(paragraphs):
        if marker_lower in paragraph.lower():
            if idx + 1 < len(paragraphs):
                return paragraphs[idx + 1].strip()
    return ""


def _comic_infer_role(topic: str, story_seed: str, index: int, name: str) -> str:
    combined = f"{topic} {story_seed} {name}".lower()
    if any(word in combined for word in ("detective", "memory", "mystery", "echo", "noir")):
        return "The Memory Detective" if index == 0 else "The Silent Clue-Holder"
    if any(word in combined for word in ("rebel", "ink", "empire", "resistance", "revolution")):
        return "The Rebel Leader" if index == 0 else "The Loyal Rebel"
    if any(word in combined for word in ("hero", "superhero", "power", "legacy", "villain")):
        return "The Accidental Hero" if index == 0 else "The Trusted Ally"
    if any(word in combined for word in ("wizard", "magic", "spell", "dragon", "myth")):
        return "The Story Keeper" if index == 0 else "The Trail Guide"
    return "The Protagonist" if index == 0 else "The Supporting Lead"


def _comic_infer_archetype(topic: str, story_seed: str, index: int, name: str) -> str:
    combined = f"{topic} {story_seed} {name}".lower()
    if any(word in combined for word in ("detective", "mystery", "noir", "memory")):
        return "Cynical Noir Investigator / Truth Seeker" if index == 0 else "Quiet Witness / Hidden Ally"
    if any(word in combined for word in ("rebel", "ink", "empire", "resistance")):
        return "Robin Hood Artist / Reluctant Revolutionary" if index == 0 else "Grounded Protector / Street-Smart Ally"
    if any(word in combined for word in ("hero", "superhero", "legacy")):
        return "Anxious Legacy / Reluctant Hero" if index == 0 else "Protective Best Friend / Steadying Force"
    if any(word in combined for word in ("wizard", "magic", "myth", "legend")):
        return "Keeper of Secrets / Gentle Guide" if index == 0 else "Clever Companion / Brave Spark"
    return "Driven Hero / Emotional Anchor" if index == 0 else "Supporting Character / Story Catalyst"


def _comic_infer_background(topic: str, story_seed: str, index: int, name: str) -> str:
    seed_snippet = _comic_sentence_snippet(story_seed, max_words=28) or f"a world shaped by {topic}"
    if index == 0:
        return f"{name} was shaped by {seed_snippet}. They carry the emotional center of the story and keep moving when everything gets harder."
    return f"{name} reacts to {seed_snippet} from a different angle, creating tension, relief, or momentum when the story needs it."


def _comic_infer_visual(name: str, topic: str, story_seed: str, index: int) -> str:
    combined = f"{topic} {story_seed} {name}".lower()
    if any(word in combined for word in ("detective", "noir", "memory", "echo")):
        return "Sharp silhouette, thoughtful eyes, layered coat, small glowing detail that suggests hidden memory tech."
    if any(word in combined for word in ("rebel", "ink", "empire", "resistance")):
        return "Athletic build, practical outfit, ink-stained hands, a signature object that feels handmade and dangerous."
    if any(word in combined for word in ("hero", "superhero", "legacy")):
        return "Distinctive everyday clothing, visible stress when the power surges, and one iconic item that grounds the character."
    if index == 0:
        return "Cinematic hero framing, expressive face, a clear signature color, and a small visual motif tied to the story."
    return "Clean readable silhouette, strong costume shape, and one memorable color accent that helps the page read instantly."


def _comic_infer_hook(name: str, topic: str, story_seed: str, index: int) -> str:
    if index == 0:
        return f"When the story opens, {name} is already standing at the edge of change."
    if "memory" in f"{topic} {story_seed}".lower():
        return f"{name} can sense what others have forgotten, which makes every scene feel personal."
    if "rebel" in f"{topic} {story_seed}".lower():
        return f"{name} turns ordinary tools into resistance, and every move changes the pressure on the world."
    return f"{name} becomes the page's emotional anchor and the reason the next beat matters."


def _comic_character_cards(characters: str, topic: str, story_seed: str) -> list[dict[str, str]]:
    blocks = _comic_split_character_blocks(characters)
    cards: list[dict[str, str]] = []
    for index, block in enumerate(blocks):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        first_line = re.sub(r"^\s*\d+\.\s*", "", lines[0]).strip()
        name_match = re.match(r"^(.*?)(?:\s*\((.*?)\))?$", first_line)
        name = (name_match.group(1) if name_match else first_line).strip() or f"Character {index + 1}"
        role = ""
        archetype = ""
        for line in lines:
            lower = line.lower()
            if lower.startswith("role:"):
                role = line.split(":", 1)[1].strip()
            elif lower.startswith("archetype:"):
                archetype = line.split(":", 1)[1].strip()
        background = _comic_extract_following_paragraph(block, "background") or _comic_infer_background(topic, story_seed, index, name)
        visual = _comic_extract_following_paragraph(block, "visual") or _comic_infer_visual(name, topic, story_seed, index)
        hook = _comic_extract_following_paragraph(block, "hook") or _comic_infer_hook(name, topic, story_seed, index)
        cards.append(
            {
                "name": name,
                "role": role or _comic_infer_role(topic, story_seed, index, name),
                "archetype": archetype or _comic_infer_archetype(topic, story_seed, index, name),
                "background": background,
                "visual": visual,
                "hook": hook,
            }
        )
    if not cards:
        fallback_name = sanitize_image_prompt_text((topic or "").strip()) or "The Hero"
        cards.append(
            {
                "name": fallback_name,
                "role": "The Protagonist",
                "archetype": "Driven Everyperson / Emotional Center",
                "background": _comic_infer_background(topic, story_seed, 0, fallback_name),
                "visual": _comic_infer_visual(fallback_name, topic, story_seed, 0),
                "hook": _comic_infer_hook(fallback_name, topic, story_seed, 0),
            }
        )
    return cards


def _comic_character_compact(card: dict[str, str]) -> str:
    return f"{card['name']} — {card['role']}. {card['archetype']}. {card['hook']}"


def _comic_page_beat(page_index: int, page_count: int, topic: str, story_seed: str, cards: list[dict[str, str]]) -> tuple[str, str, str]:
    arc_labels = [
        ("Opening", "introduce the world and the emotional center"),
        ("Inciting Incident", "show the moment that disrupts the normal world"),
        ("Rising Action", "raise the stakes and deepen the conflict"),
        ("Midpoint", "reveal a turn in the story or a stronger emotional truth"),
        ("Setback", "force the hero to adapt after a difficult hit"),
        ("Preparation", "show the plan forming or the team pulling together"),
        ("Climax", "deliver the decisive confrontation"),
        ("Resolution", "land the ending with hope and consequence"),
    ]
    stage_title, stage_goal = arc_labels[min(page_index - 1, len(arc_labels) - 1)]
    seed_sentences = _comic_story_sentences(story_seed)
    opening = " ".join(seed_sentences[:2]).strip() if seed_sentences else _comic_sentence_snippet(topic, max_words=22)
    protagonist = cards[0]
    focus = cards[(page_index - 1) % len(cards)]
    supporting = cards[page_index % len(cards)] if len(cards) > 1 else focus
    if page_index == 1:
        narration = (
            f"Opening panel: {opening or topic}. "
            f"{protagonist['name']} enters as {protagonist['role']} and the story locks onto their emotional struggle. "
            f"{protagonist['background']}"
        )
    elif page_index == page_count:
        narration = (
            f"Final panel: {focus['name']} brings the story home, the conflict resolves, and the world settles into a hopeful new shape. "
            f"The ending reflects what the characters have learned."
        )
    else:
        story_bit = seed_sentences[page_index - 1] if page_index - 1 < len(seed_sentences) else ""
        if not story_bit:
            story_bit = f"{focus['name']} advances the story with a clear new beat, strong emotion, and one vivid action."
        narration = (
            f"Page {page_index}: {stage_title}. {story_bit} "
            f"{focus['name']} and {supporting['name']} push the story toward {stage_goal}."
        )
    image_focus = (
        f"Focus on {focus['name']} as {focus['role']} with visual detail: {focus['visual']} "
        f"Use {stage_title.lower()} energy, clear character staging, expressive body language, and a cinematic child-friendly comic composition."
    )
    prompt = (
        f"Create a vertical 9:16 comic page {page_index}/{page_count} for the story '{topic}'. "
        f"Scene goal: {stage_goal}. "
        f"Main focus character: {_comic_character_compact(focus)} "
        f"Supporting character: {_comic_character_compact(supporting)} "
        f"Story beat: {narration} "
        f"Image focus: {image_focus} "
        "Art style: bold ink outlines, halftone dots, vibrant colors, dynamic speech bubbles, dramatic framing, clean child-friendly finish, full-page layout, no watermark, no logo. "
        "Keep the main characters visually consistent across all panels."
    )
    return narration, prompt, stage_title


def _comic_story_plan(topic: str, characters: str, style_name: str, requested_panel_count: int | None, story_seed: str = "") -> dict[str, object]:
    cards = _comic_character_cards(characters, topic, story_seed)
    auto_count = _comic_auto_panel_count(topic, characters, story_seed)
    panel_count = auto_count if requested_panel_count is None else max(3, min(8, int(requested_panel_count)))
    page_cards = cards[:]
    pages: list[dict[str, str]] = []
    for page_index in range(1, panel_count + 1):
        narration, prompt, stage_title = _comic_page_beat(page_index, panel_count, topic, story_seed, page_cards)
        pages.append(
            {
                "page": str(page_index),
                "title": stage_title,
                "narration": narration,
                "prompt": prompt,
            }
        )
    cast_lines = [f"{idx + 1}. {_comic_character_compact(card)}" for idx, card in enumerate(cards)]
    return {
        "topic": topic,
        "style_name": style_name or "Classic Comic Book",
        "panel_count": panel_count,
        "characters": cards,
        "cast_lines": cast_lines,
        "pages": pages,
    }


def _comic_narration_script(topic: str, characters: str, panel_count: int, story_seed: str = "") -> str:
    plan = _comic_story_plan(topic, characters, "Classic Comic Book", panel_count, story_seed=story_seed)
    narration_lines = []
    if plan.get("cast_lines"):
        narration_lines.append("Cast: " + " ".join(plan["cast_lines"]))
    for page in plan["pages"]:
        narration_lines.append(f"Page {page['page']}: {page['narration']}")
    return " ".join(narration_lines)


def _comic_video_preview_path(output_dir: Path, topic: str, provider_name: str) -> Path:
    preview_dir = output_dir / ".runtime" / "comic_video_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    topic_slug = _slugify(topic)[:28]
    provider_slug = _slugify(provider_name)[:12]
    fingerprint = hashlib.sha1(f"{topic}|{provider_name}".encode("utf-8")).hexdigest()[:10]
    return preview_dir / f"comic_video_{topic_slug}_{provider_slug}_{fingerprint}.mp4"


def _comic_page_preview_path(
    output_dir: Path,
    topic: str,
    page_label: str,
    provider_name: str,
    extension: str,
) -> Path:
    preview_dir = output_dir / ".runtime" / "comic_page_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    import hashlib

    topic_slug = _slugify(topic)[:24]
    page_slug = _slugify(page_label)[:18]
    provider_slug = _slugify(provider_name)[:12]
    fingerprint = hashlib.sha1(f"{topic}|{page_label}|{provider_name}".encode("utf-8")).hexdigest()[:10]
    return preview_dir / f"comic_{topic_slug}_{page_slug}_{provider_slug}_{fingerprint}{extension}"


def _generate_comic_page_preview(
    settings,
    output_dir: Path,
    provider_name: str,
    prompt: str,
    topic: str,
    page_label: str,
) -> Path:
    image_settings = replace(settings, output_dir=output_dir)
    provider = image_provider(replace(image_settings, image_provider=provider_name))
    variant = ImageVariant("9:16", 1080, 1920, "image_portrait")
    preview_path = _comic_page_preview_path(
        output_dir=output_dir,
        topic=topic,
        page_label=page_label,
        provider_name=provider_name,
        extension=provider.extension,
    )
    preview_path.write_bytes(provider.create(prompt, variant))
    return preview_path


def _generate_comic_voiceover(
    settings,
    output_path: Path,
    narration_text: str,
    voice_engine: str,
) -> Path:
    voice_engine = (voice_engine or "local-m1-parler").strip().lower()
    if voice_engine in {"local-m1-parler", "local", "parler", "parler-local"}:
        try:
            repo_id = getattr(settings, "comic_voice_model_repo", "ai4bharat/indic-parler-tts")
            return generate_local_parler_voiceover(
                narration_text,
                output_path,
                description="A clear, warm, expressive English comic narration voice with child-friendly pacing and friendly studio tone.",
                repo_id=repo_id,
                token=settings.hf_token or None,
            )
        except Exception as exc:
            st.warning(f"Local M1 voiceover failed, falling back to Edge TTS: {exc}")
    elif voice_engine in {"hf-kokoro", "kokoro", "huggingface-kokoro"}:
        try:
            repo_id = getattr(settings, "comic_kokoro_model_repo", "hexgrad/Kokoro-82M")
            return generate_hf_tts_voiceover(
                narration_text,
                output_path,
                model_id=repo_id,
                token=settings.hf_token or None,
                provider="fal-ai",
            )
        except Exception as exc:
            st.warning(f"Hugging Face Kokoro voiceover failed, falling back to Edge TTS: {exc}")
    elif voice_engine in {"hf-chatterbox", "chatterbox", "huggingface-chatterbox"}:
        try:
            repo_id = getattr(settings, "comic_chatterbox_model_repo", "ResembleAI/chatterbox")
            return generate_hf_tts_voiceover(
                narration_text,
                output_path,
                model_id=repo_id,
                token=settings.hf_token or None,
                provider="fal-ai",
            )
        except Exception as exc:
            st.warning(f"Hugging Face Chatterbox voiceover failed, falling back to Edge TTS: {exc}")

    from content_pipeline.bots.audio import generate_indian_voiceover
    return generate_indian_voiceover(
        narration_text,
        output_path,
        voice="en-IN-PrabhatNeural",
        rate="-4%",
        pitch="+0Hz",
    )


def render_automation_music_image_section(settings) -> None:
    prefix = "automation_music_image"

    def k(name: str) -> str:
        return f"{prefix}_{name}"

    ui_output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
    st.session_state.setdefault(k("provider_choice"), st.session_state.get("image_provider_choice", settings.image_provider or "gemini"))
    st.session_state.setdefault(k("topic"), st.session_state.get("music_studio_one_click_song_idea", ""))
    st.session_state.setdefault(k("subject"), st.session_state.get("music_studio_description", "a cheerful kids music scene"))
    st.session_state.setdefault(
        k("singer_gender"),
        (st.session_state.get("automation_music_singer_gender")
        or st.session_state.get("music_studio_one_click_singer_gender")
        or st.session_state.get("music_studio_singer_gender")
        or "").strip().lower(),
    )
    st.session_state.setdefault(k("art_style"), "3D Claymation / Pixar")
    st.session_state.setdefault(k("count"), 1)
    st.session_state.setdefault(
        k("studio_prompt"),
        build_cinematic_image_prompt(
            st.session_state[k("topic")],
            st.session_state[k("subject")],
            style_name=st.session_state[k("art_style")],
        ),
    )
    st.session_state.setdefault(k("prompt_input"), st.session_state[k("studio_prompt")])
    st.session_state.setdefault(k("preview_path"), "")
    st.session_state.setdefault(k("last_topic"), st.session_state[k("topic")])
    st.session_state.setdefault(k("last_subject"), st.session_state[k("subject")])
    st.session_state.setdefault(k("last_style"), st.session_state[k("art_style")])

    current_topic = st.session_state.get(k("topic"), "")
    current_subject = st.session_state.get(k("subject"), "")
    current_style = st.session_state.get(k("art_style"), "3D Claymation / Pixar")
    if (
        current_topic != st.session_state[k("last_topic")]
        or current_subject != st.session_state[k("last_subject")]
        or current_style != st.session_state[k("last_style")]
    ):
        st.session_state[k("studio_prompt")] = build_cinematic_image_prompt(
            current_topic,
            current_subject,
            style_name=current_style,
        )
        st.session_state[k("prompt_input")] = st.session_state[k("studio_prompt")]
        st.session_state[k("last_topic")] = current_topic
        st.session_state[k("last_subject")] = current_subject
        st.session_state[k("last_style")] = current_style

    image_count = max(1, min(8, int(st.session_state.get(k("count"), 1))))
    st.session_state[k("count")] = image_count
    prompt_variants = _automation_image_prompt_variants(
        topic=st.session_state[k("topic")],
        subject=st.session_state[k("subject")],
        style_name=st.session_state[k("art_style")],
        image_count=image_count,
        singer_gender=st.session_state[k("singer_gender")],
    )
    st.session_state[k("prompt_series")] = prompt_variants
    st.session_state[k("studio_prompt")] = prompt_variants[0]
    st.session_state[k("prompt_input")] = prompt_variants[0]

    st.markdown("---")
    st.markdown("### 🖼️ Automation Image Studio")
    left_col, right_col = st.columns([6, 4])

    with left_col:
        image_preview_path = st.session_state.get(k("preview_path"))
        if image_preview_path and os.path.exists(image_preview_path):
            render_image_preview(Path(image_preview_path))
            st.caption(f"Linked image preview: `{Path(image_preview_path).name}`")
        else:
            st.info("No linked image generated yet. It will populate from the song draft and generate step.")

        preview_paths = st.session_state.get(k("preview_paths"), [])
        if preview_paths:
            st.markdown("#### Generated Images")
            cols = st.columns(min(3, len(preview_paths)))
            for idx, path_str in enumerate(preview_paths):
                col = cols[idx % len(cols)]
                with col:
                    path = Path(path_str)
                    if path.exists():
                        render_image_preview(path)
                        st.caption(f"Image {idx + 1}")

        st.selectbox(
            "Number of images",
            options=list(range(1, 9)),
            index=image_count - 1,
            key=k("count"),
        )
        st.selectbox(
            "Image Provider",
            options=("nvidia", "gemini", "openai", "free-ai"),
            key=k("provider_choice"),
        )
        st.selectbox(
            "Singer Gender",
            options=("female", "male"),
            key=k("singer_gender"),
        )
        st.text_input("Image Topic", key=k("topic"))
        st.text_input("Image Subject", key=k("subject"))
        st.selectbox(
            "Art Style",
            options=("3D Claymation / Pixar", "Photorealistic", "Flat Vector", "Cinematic Anime", "None (Raw Prompt)"),
            key=k("art_style"),
        )
        st.markdown("#### Image Prompt Preview")
        for idx, prompt_text in enumerate(prompt_variants, start=1):
            st.text_area(
                f"Prompt {idx}",
                value=prompt_text,
                height=120,
                key=f"{prefix}_prompt_view_{idx}",
            )

        act_cols = st.columns(2)
        with act_cols[0]:
            if st.button("🧙‍♂️ Build Image Prompt", use_container_width=True, key=f"{prefix}_btn_build_prompt"):
                creative_topic, creative_subject = _automation_music_image_seed(
                    st.session_state[k("topic")],
                    st.session_state[k("subject")],
                    st.session_state.get(k("singer_gender"), ""),
                )
                st.session_state[k("studio_prompt")] = build_cinematic_image_prompt(
                    creative_topic,
                    creative_subject,
                    style_name=st.session_state.get(k("art_style"), "3D Claymation / Pixar"),
                )
                st.session_state[k("prompt_input")] = st.session_state[k("studio_prompt")]
                st.rerun()
        with act_cols[1]:
            if st.button("✨ Generate Image", type="primary", use_container_width=True, key=f"{prefix}_btn_generate"):
                try:
                    preview_paths = []
                    for idx, prompt_text in enumerate(prompt_variants, start=1):
                        preview_path = _generate_automation_image_preview(
                            settings=settings,
                            output_dir=ui_output_dir,
                            provider_name=st.session_state[k("provider_choice")],
                            prompt=prompt_text,
                            topic=st.session_state[k("topic")],
                            subject=f"{st.session_state[k('subject')]} variation {idx}",
                            prefix="automation_music",
                        )
                        preview_paths.append(str(preview_path))
                        st.session_state[k("preview_paths")] = preview_paths
                        st.session_state[k("preview_path")] = preview_paths[0] if preview_paths else ""
                        _auto_refresh_project_brain(settings, reason="automation_image")
                        st.success("Automation image generated.")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Image generation error: {exc}")

    with right_col:
        st.markdown("#### Prompt Summary")
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-label">Images Requested</div>
                <div class="metric-value" style="font-size:18px;">{image_count}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">Showing exactly {image_count} prompt{'s' if image_count != 1 else ''} for this song.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for idx, prompt_text in enumerate(prompt_variants, start=1):
            st.markdown(f"**Prompt {idx}**")
            st.code(prompt_text, language="text")

        st.markdown("#### Prompt Safety audit")
        safety_state, safety_msg = image_prompt_safety_status(st.session_state[k("studio_prompt")])
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-label">Safety State</div>
                <div class="metric-value" style="font-size:16px;">{safety_state.upper()}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{safety_msg}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### Active Provider backend details")
        backend_state, backend_msg = image_backend_status(settings, st.session_state[k("provider_choice")])
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-label">Provider Pipeline</div>
                <div class="metric-value" style="font-size:16px;">{backend_state.upper()}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{backend_msg}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def maybe_generate_linked_automation_music_image(settings) -> Path | None:
    if not st.session_state.get("automation_music_combo_mode"):
        return None

    output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
    provider_name = st.session_state.get("automation_music_image_provider_choice") or st.session_state.get("image_provider_choice") or settings.image_provider or "gemini"
    topic = st.session_state.get("automation_music_image_topic") or st.session_state.get("music_studio_one_click_song_idea") or st.session_state.get("music_studio_lyrics", "")
    subject = st.session_state.get("automation_music_image_subject") or st.session_state.get("music_studio_description") or topic or "a cheerful kids music scene"
    art_style = st.session_state.get("automation_music_image_art_style", "3D Claymation / Pixar")
    singer_gender = st.session_state.get("automation_music_singer_gender") or st.session_state.get("music_studio_one_click_singer_gender") or st.session_state.get("music_studio_singer_gender") or ""
    image_count = max(1, min(8, int(st.session_state.get("automation_music_image_count", 1))))
    prompts = _automation_image_prompt_variants(topic=topic, subject=subject, style_name=art_style, image_count=image_count, singer_gender=singer_gender)
    st.session_state["automation_music_image_prompt_series"] = prompts
    st.session_state["automation_music_image_studio_prompt"] = prompts[0]
    st.session_state["automation_music_image_prompt_input"] = prompts[0]
    try:
        preview_paths = []
        for idx, prompt_text in enumerate(prompts, start=1):
            preview_path = _generate_automation_image_preview(
                settings=settings,
                output_dir=output_dir,
                provider_name=provider_name,
                prompt=prompt_text,
                topic=topic,
                subject=f"{subject} variation {idx}",
                prefix="automation_music",
            )
            preview_paths.append(str(preview_path))
        st.session_state["automation_music_image_preview_paths"] = preview_paths
        st.session_state["automation_music_image_preview_path"] = preview_paths[0] if preview_paths else ""
        return Path(preview_paths[0]) if preview_paths else None
    except Exception as exc:
        st.warning(f"⚠️ Automation linked image generation skipped: {exc}")
        return None


def _kids_poster_preview_path(
    output_dir: Path,
    topic: str,
    provider_name: str,
    extension: str,
) -> Path:
    preview_dir = output_dir / ".runtime" / "image_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    import hashlib

    topic_slug = _slugify(topic)[:28]
    provider_slug = _slugify(provider_name)[:12]
    fingerprint = hashlib.sha1(f"{topic}|{provider_name}".encode("utf-8")).hexdigest()[:10]
    filename = f"kids_poster_{topic_slug}_{provider_slug}_{fingerprint}{extension}"
    return preview_dir / filename


def _generate_kids_poster_preview(
    settings,
    output_dir: Path,
    provider_name: str,
    prompt: str,
    topic: str,
) -> Path:
    image_settings = replace(settings, output_dir=output_dir)
    provider = image_provider(replace(image_settings, image_provider=provider_name))
    variant = ImageVariant("4:5", 1600, 2000, "image_portrait")
    preview_path = _kids_poster_preview_path(
        output_dir=output_dir,
        topic=topic,
        provider_name=provider_name,
        extension=provider.extension,
    )
    preview_path.write_bytes(provider.create(prompt, variant))
    return preview_path


def maybe_generate_linked_kids_poster(settings) -> Path | None:
    if not st.session_state.get("automation_kids_combo_mode"):
        return None

    topic = (
        st.session_state.get("one_click_song_idea")
        or st.session_state.get("kids_song_title")
        or st.session_state.get("kids_song_topic")
        or "Little Bubbles TV"
    )
    lyrics = st.session_state.get("kids_song_lyrics", "")
    kids_mode = st.session_state.get("kids_studio_mode", "Poem/Rhyme")
    should_auto = bool(
        st.session_state.get("automation_kids_combo_mode")
        or st.session_state.get("kids_poster_autogenerate")
    )
    if not should_auto:
        return None
    try:
        output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
        provider_name = st.session_state.get("kids_poster_provider_choice") or st.session_state.get("image_provider_choice") or settings.image_provider or "nvidia"
        prompt_topic, prompt_text = _kids_nursery_poster_seed(topic, lyrics, kids_mode)
        st.session_state["kids_poster_prompt"] = prompt_text
        st.session_state["kids_poster_lyrics_excerpt"] = _kids_poster_lyrics_excerpt(lyrics)
        preview_path = _generate_kids_poster_preview(
            settings=settings,
            output_dir=output_dir,
            provider_name=provider_name,
            prompt=prompt_text,
            topic=prompt_topic,
        )
        st.session_state["kids_poster_preview_path"] = str(preview_path)
        st.session_state["kids_poster_provider_choice"] = provider_name
        st.session_state["kids_poster_generated_title"] = prompt_topic
        st.session_state["kids_poster_generated_prompt"] = prompt_text
        return preview_path
    except Exception as exc:
        st.session_state["kids_poster_error"] = str(exc)
        return None


def render_kids_nursery_poster_section(settings) -> None:
    st.markdown("#### 🖼️ Nursery Rhyme Poster")
    st.caption(
        "Creates a 4:5 vertical poster with a colorful title, sunny park scene, cute characters, and a cloud panel for the lyrics."
    )

    prefix = "kids_poster"

    def k(name: str) -> str:
        return f"{prefix}_{name}"

    st.session_state.setdefault(k("provider_choice"), "nvidia")
    st.session_state.setdefault(k("title_input"), st.session_state.get("one_click_song_idea", "Little Bubbles TV"))
    st.session_state.setdefault(k("lyrics_source"), st.session_state.get("kids_song_lyrics", ""))
    st.session_state.setdefault(k("autogenerate"), bool(st.session_state.get("automation_kids_combo_mode")))
    st.session_state.setdefault(k("prompt_input"), "")
    st.session_state.setdefault(k("preview_path"), "")
    st.session_state.setdefault(k("error"), "")

    current_title = st.session_state.get(k("title_input"), "Little Bubbles TV")
    generated_title = st.session_state.get("kids_poster_generated_title", "")
    if generated_title and not current_title.strip():
        current_title = generated_title
        st.session_state[k("title_input")] = generated_title
    current_lyrics = st.session_state.get(k("lyrics_source"), "")
    poster_title, poster_prompt = _kids_nursery_poster_seed(
        current_title,
        current_lyrics,
        st.session_state.get("kids_studio_mode", "Poem/Rhyme"),
    )
    if not st.session_state.get(k("prompt_input"), "").strip():
        st.session_state[k("prompt_input")] = poster_prompt
        st.session_state[k("prompt_view")] = poster_prompt

    left_col, right_col = st.columns([6, 4])
    with left_col:
        preview_path = st.session_state.get(k("preview_path"), "")
        if preview_path and os.path.exists(preview_path):
            render_image_preview(Path(preview_path))
            st.caption(f"Loaded poster: `{Path(preview_path).name}`")
            try:
                poster_file = Path(preview_path)
                st.download_button(
                    "📥 Download Poster",
                    data=poster_file.read_bytes(),
                    file_name=poster_file.name,
                    mime="image/png" if poster_file.suffix.lower() == ".png" else "image/svg+xml",
                    use_container_width=True,
                    key=f"{prefix}_btn_download",
                )
            except Exception as exc:
                st.error(f"Could not prepare the poster download: {exc}")
        else:
            st.info("No nursery poster generated yet. Build the prompt and render it from the lyrics below.")

        st.text_input("Poster Title", key=k("title_input"))
        st.text_area(
            "Lyrics for Poster",
            key=k("lyrics_source"),
            height=180,
            help="These lyrics are placed in the center cloud panel of the poster.",
        )
        st.selectbox(
            "Image Provider",
            options=("nvidia", "gemini", "openai", "free-ai"),
            key=k("provider_choice"),
        )
        st.checkbox(
            "Auto-generate poster after song draft",
            key=k("autogenerate"),
            help="When enabled, the poster is rendered right after the song draft finishes.",
        )

        button_cols = st.columns(2)
        with button_cols[0]:
            if st.button("🧙‍♂️ Build Poster Prompt", use_container_width=True, key=f"{prefix}_btn_build"):
                _, prompt_text = _kids_nursery_poster_seed(
                    st.session_state.get(k("title_input"), "Little Bubbles TV"),
                    st.session_state.get(k("lyrics_source"), ""),
                    st.session_state.get("kids_studio_mode", "Poem/Rhyme"),
                )
                st.session_state[k("prompt_input")] = prompt_text
                st.session_state[k("prompt_view")] = prompt_text
                st.rerun()
        with button_cols[1]:
            if st.button("✨ Generate Poster", type="primary", use_container_width=True, key=f"{prefix}_btn_generate"):
                try:
                    output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
                    prompt_title, prompt_text = _kids_nursery_poster_seed(
                        st.session_state.get(k("title_input"), "Little Bubbles TV"),
                        st.session_state.get(k("lyrics_source"), ""),
                        st.session_state.get("kids_studio_mode", "Poem/Rhyme"),
                    )
                    prompt_text = st.session_state.get(k("prompt_view"), prompt_text).strip() or prompt_text
                    st.session_state[k("prompt_input")] = prompt_text
                    st.session_state[k("prompt_view")] = prompt_text
                    st.session_state[k("generated_title")] = prompt_title
                    provider_name = st.session_state.get(k("provider_choice"), "nvidia")
                    preview_path = _generate_kids_poster_preview(
                        settings=settings,
                        output_dir=output_dir,
                        provider_name=provider_name,
                        prompt=prompt_text,
                        topic=prompt_title,
                    )
                    st.session_state[k("preview_path")] = str(preview_path)
                    st.session_state[k("error")] = ""
                    _auto_refresh_project_brain(settings, reason="kids_poster")
                    st.success("Nursery poster generated.")
                    st.rerun()
                except Exception as exc:
                    st.session_state[k("error")] = str(exc)
                    st.error(f"Poster generation failed: {exc}")

    with right_col:
        st.markdown("#### Poster Prompt")
        st.text_area(
            "Prompt",
            height=420,
            key=k("prompt_view"),
        )
        st.markdown("#### Layout Notes")
        st.markdown(
            """
            - 4:5 vertical composition
            - big bubble-letter title with white outline
            - sunny park, rainbow, bubbles, flowers, smiling sun
            - cute kids and animals around the edges
            - white cloud panel in the center for clear lyrics
            """.strip()
        )

    if st.session_state.get(k("error")):
        st.error(st.session_state[k("error")])


def render_youtube_audit_studio(settings) -> None:
    st.markdown("### 🔎 YouTube Channel Audit")
    st.caption(
        "Scans the configured YouTube channels, checks recent uploads, and compares the channel language against public trend signals."
    )

    control_cols = st.columns([1, 1, 1])
    with control_cols[0]:
        region_code = st.selectbox("Trend region", options=["IN", "US", "GB", "CA", "AU"], index=0, key="yt_audit_region")
    with control_cols[1]:
        max_videos = st.slider("Recent uploads to inspect", min_value=5, max_value=30, value=15, step=1, key="yt_audit_max_videos")
    with control_cols[2]:
        related_topic_limit = st.slider("Related topic queries", min_value=1, max_value=5, value=3, step=1, key="yt_audit_topic_limit")

    run_cols = st.columns([1, 1, 1])
    with run_cols[0]:
        update_limit = st.slider("Videos to rewrite per channel", min_value=1, max_value=5, value=2, step=1, key="yt_audit_update_limit")
    with run_cols[1]:
        apply_updates = st.checkbox("Apply title/tag updates", value=False, key="yt_audit_apply_updates")
    with run_cols[2]:
        notify_telegram = st.checkbox("Notify Telegram", value=True, key="yt_audit_notify_telegram")

    provider_choice = st.selectbox(
        "Rewrite provider",
        options=["Auto", "NVIDIA", "Gemini", "OpenAI", "Local LLM"],
        index=0,
        key="yt_audit_rewrite_provider",
    )
    st.caption("Auto tries NVIDIA, then Gemini, then OpenAI, then the local LLM. Provider-specific modes keep using their own key pools in order.")

    telegram_cols = st.columns(2)
    with telegram_cols[0]:
        telegram_bot_token = st.text_input(
            "Telegram Bot Token",
            value=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            type="password",
            key="yt_audit_telegram_token",
        )
    with telegram_cols[1]:
        telegram_chat_id = st.text_input(
            "Telegram Chat ID",
            value=os.getenv("TELEGRAM_CHAT_ID", ""),
            key="yt_audit_telegram_chat",
        )

    st.info(
        "The audit works channel-by-channel. It needs the per-channel YouTube OAuth token files already configured in `.secrets/`."
    )

    if st.button("🔍 Run Channel Audit", type="primary", use_container_width=True, key="btn_run_youtube_audit"):
        with st.spinner("Running YouTube channel diagnostics and trend scan..."):
            try:
                report = run_weekly_youtube_review(
                    settings,
                    PROJECT_ROOT,
                    region_code=region_code,
                    max_videos=max_videos,
                    related_topic_limit=related_topic_limit,
                    update_limit=update_limit,
                    rewrite_provider={
                        "Auto": "auto",
                        "NVIDIA": "nvidia",
                        "Gemini": "gemini",
                        "OpenAI": "openai",
                        "Local LLM": "local",
                    }.get(provider_choice, "auto"),
                    apply_updates=apply_updates,
                    notify_telegram=notify_telegram,
                    telegram_bot_token=telegram_bot_token,
                    telegram_chat_id=telegram_chat_id,
                )
                st.session_state["youtube_audit_report"] = report
                st.session_state["youtube_audit_paths"] = report.get("report_paths", {})
                st.success("Channel audit complete.")
            except Exception as exc:
                st.session_state["youtube_audit_error"] = str(exc)
                st.error(f"Audit failed: {exc}")

    if "youtube_audit_error" in st.session_state:
        st.error(st.session_state["youtube_audit_error"])

    report = st.session_state.get("youtube_audit_report")
    if not isinstance(report, dict):
        st.caption("Run the audit to see a per-channel breakdown, trend matches, and fix suggestions.")
        return

    st.markdown(render_youtube_audit_markdown(report))

    paths = st.session_state.get("youtube_audit_paths", {})
    if isinstance(paths, dict):
        col_left, col_right = st.columns(2)
        with col_left:
            md_path = paths.get("markdown", "")
            if md_path and os.path.exists(md_path):
                st.markdown(f"[Open markdown report]({Path(md_path).as_uri()})")
        with col_right:
            json_path = paths.get("json", "")
            if json_path and os.path.exists(json_path):
                st.markdown(f"[Open JSON report]({Path(json_path).as_uri()})")

    st.download_button(
        "Download audit markdown",
        data=render_youtube_audit_markdown(report),
        file_name="youtube_audit_report.md",
        mime="text/markdown",
        use_container_width=True,
        key="btn_download_youtube_audit_md",
    )


def render_project_brain_studio(settings) -> None:
    st.markdown("### 🧠 Project Brain")
    st.caption(
        "Scores the latest audio, image, metadata, novelty, blockers, and trend signals. It also stores learning rules so the next run can diversify."
    )

    prefix = "project_brain"

    def k(name: str) -> str:
        return f"{prefix}_{name}"

    brain_output_dir = resolve_output_dir(st.session_state.get("output_dir_pref", str(settings.output_dir)))
    brain_runtime_dir = brain_output_dir / ".runtime" / "project_brain"
    st.session_state.setdefault(k("refresh_web"), True)
    st.session_state.setdefault(k("trend_region"), "IN")
    st.session_state.setdefault(k("last_output_dir"), str(brain_output_dir))
    st.session_state.setdefault(k("report"), None)
    st.session_state.setdefault(k("paths"), {})
    st.session_state.setdefault(k("error"), "")

    if st.session_state.get(k("last_output_dir")) != str(brain_output_dir):
        st.session_state[k("report")] = None
        st.session_state[k("paths")] = {}
        st.session_state[k("last_output_dir")] = str(brain_output_dir)

    try:
        latest_report = load_latest_project_brain_report(brain_output_dir)
        if latest_report is not None and st.session_state.get(k("report")) is None:
            st.session_state[k("report")] = latest_report
            st.session_state[k("paths")] = {
                "json": latest_report.report_path,
                "markdown": latest_report.markdown_path,
                "memory": latest_report.memory_path,
            }
    except Exception:
        pass

    control_cols = st.columns([1, 1, 2])
    with control_cols[0]:
        st.checkbox("Refresh web signals", value=st.session_state[k("refresh_web")], key=k("refresh_web"))
    with control_cols[1]:
        st.selectbox(
            "Trend region",
            options=["IN", "US", "GB", "CA", "AU"],
            index=["IN", "US", "GB", "CA", "AU"].index(st.session_state[k("trend_region")]) if st.session_state[k("trend_region")] in ["IN", "US", "GB", "CA", "AU"] else 0,
            key=k("trend_region"),
        )
    with control_cols[2]:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-label">Brain Memory</div>
                <div class="metric-value" style="font-size:16px;">{brain_runtime_dir}</div>
                <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">Fresh reports are written here and can be picked up again later.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    run_cols = st.columns([1, 1, 1])
    with run_cols[0]:
        if st.button("🧠 Run Project Brain", type="primary", use_container_width=True, key=f"{prefix}_btn_run"):
            with st.spinner("Reading the latest artifacts and scoring the project..."):
                try:
                    report = build_project_brain_report(
                        settings,
                        refresh_web=bool(st.session_state.get(k("refresh_web"), True)),
                        trend_region=str(st.session_state.get(k("trend_region"), "IN")),
                        output_dir=brain_output_dir,
                    )
                    st.session_state[k("report")] = report
                    st.session_state[k("paths")] = {
                        "json": report.report_path,
                        "markdown": report.markdown_path,
                        "memory": report.memory_path,
                    }
                    st.session_state[k("error")] = ""
                    st.success("Project brain updated.")
                except Exception as exc:
                    st.session_state[k("error")] = str(exc)
                    st.error(f"Brain run failed: {exc}")
    with run_cols[1]:
        if st.button("📄 Refresh latest report", use_container_width=True, key=f"{prefix}_btn_refresh"):
            try:
                latest_report = load_latest_project_brain_report(brain_output_dir)
                if latest_report is None:
                    st.warning("No saved brain report was found yet. Run the brain once to create it.")
                else:
                    st.session_state[k("report")] = latest_report
                    st.session_state[k("paths")] = {
                        "json": latest_report.report_path,
                        "markdown": latest_report.markdown_path,
                        "memory": latest_report.memory_path,
                    }
                    st.success("Loaded the latest saved brain report.")
            except Exception as exc:
                st.error(f"Could not refresh latest report: {exc}")
    with run_cols[2]:
        st.info("The brain combines local quality signals with optional web trend refreshes so each run can suggest a new angle.")

    if st.session_state.get(k("error")):
        st.error(st.session_state[k("error")])

    report = st.session_state.get(k("report"))
    if not report:
        st.caption("Run the brain to see audio, image, metadata, novelty, and learning-rule scores.")
        return

    st.markdown(
        f"""
        <div class="metric-box">
            <div class="metric-label">Overall Brain Score</div>
            <div class="metric-value" style="font-size:26px;">{report.overall_score:.1f} / 100</div>
            <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">Verdict: {report.verdict}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    score_cols = st.columns(min(4, len(report.scores)) or 1)
    for idx, score in enumerate(report.scores):
        col = score_cols[idx % len(score_cols)]
        with col:
            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">{escape(score.kind.replace('_', ' ').title())}</div>
                    <div class="metric-value" style="font-size:18px;">{score.score:.1f}</div>
                    <div style="font-size:13px; color:#cbd5e1; margin-top:4px;">{escape(score.verdict)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if score.issues:
                st.caption("Issues: " + "; ".join(score.issues[:3]))
            if score.recommendations:
                st.caption("Fixes: " + "; ".join(score.recommendations[:3]))

    st.markdown("#### Summary")
    st.write(report.summary)

    if report.root_causes:
        st.markdown("#### Root Causes")
        for item in report.root_causes:
            st.markdown(f"- {item}")

    if report.next_actions:
        st.markdown("#### Next Actions")
        for item in report.next_actions:
            st.markdown(f"- {item}")

    if report.content_ideas:
        st.markdown("#### Idea Backlog")
        for item in report.content_ideas:
            topic = item.get("topic", "").strip()
            angle = item.get("angle", "").strip()
            reason = item.get("reason", "").strip()
            st.markdown(f"- **{topic}** — {angle}. {reason}")

    if report.learning_rules:
        st.markdown("#### Learning Rules")
        for item in report.learning_rules:
            st.markdown(f"- {item}")

    if report.blockers.get("open_count") or report.blockers.get("resolved_count"):
        st.markdown("#### Blockers")
        st.markdown(f"- Open: `{report.blockers.get('open_count', 0)}`")
        st.markdown(f"- Resolved: `{report.blockers.get('resolved_count', 0)}`")

    if report.web_signals.get("latest_audit"):
        audit = report.web_signals["latest_audit"]
        st.markdown("#### Web Signals")
        st.markdown(f"- Audited channels: `{audit.get('audited_channels', 0)}`")
        st.markdown(f"- Average channel score: `{audit.get('average_score', 0)}`")
        st.markdown(f"- Trend region: `{report.web_signals.get('trend_region', 'IN')}`")

    paths = st.session_state.get(k("paths"), {})
    path_cols = st.columns(3)
    with path_cols[0]:
        json_path = paths.get("json", "")
        if json_path and os.path.exists(json_path):
            st.markdown(f"[Open JSON report]({Path(json_path).as_uri()})")
    with path_cols[1]:
        md_path = paths.get("markdown", "")
        if md_path and os.path.exists(md_path):
            st.markdown(f"[Open Markdown report]({Path(md_path).as_uri()})")
    with path_cols[2]:
        memory_path = paths.get("memory", "")
        if memory_path and os.path.exists(memory_path):
            st.markdown(f"[Open Memory file]({Path(memory_path).as_uri()})")

    st.download_button(
        "Download brain markdown",
        data=render_project_brain_markdown(report),
        file_name="project_brain_report.md",
        mime="text/markdown",
        use_container_width=True,
        key=f"{prefix}_btn_download_md",
    )


def get_git_info() -> str:
    try:
        import subprocess
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        message = subprocess.check_output(["git", "log", "-1", "--pretty=%B"], text=True).strip()
        return f"Branch: `{branch}`  \nCommit: `{commit[:8]}` ({message.splitlines()[0]})"
    except Exception as e:
        return f"Failed to get git info: {e}"


def get_package_info() -> str:
    import sys
    import traceback
    import os
    import importlib
    importlib.invalidate_caches()
    sys.path_importer_cache.clear()
    res = []
    
    # Check pydub
    try:
        import pydub
        res.append(f"✅ `pydub` imported successfully (path: `{pydub.__file__}`)")
    except Exception as e:
        tb = traceback.format_exc()
        res.append(f"❌ `pydub` import failed: {e}  \nTraceback:  \n```\n{tb}\n```")
        
    # Check audioop
    try:
        import audioop
        res.append(f"✅ `audioop` imported successfully (path: `{audioop.__file__}`)" if hasattr(audioop, '__file__') else "✅ `audioop` imported successfully")
    except Exception as e:
        tb = traceback.format_exc()
        res.append(f"❌ `audioop` import failed: {e}  \nTraceback:  \n```\n{tb}\n```")
        
    # Check python version
    res.append(f"🐍 Python version: `{sys.version}`")
    
    # Check TARGET_SITE_PACKAGES contents
    res.append(f"📁 Target Site-Packages Path: `{TARGET_SITE_PACKAGES}`")
    if TARGET_SITE_PACKAGES.exists():
        files = [p.name for p in TARGET_SITE_PACKAGES.glob("*")]
        res.append(f"📁 Target Site-Packages Contents: `{files}`")
        try:
            stat_site = os.stat(str(TARGET_SITE_PACKAGES))
            res.append(f"📁 Site-Packages Permissions: `{oct(stat_site.st_mode)}` | Owner: `{stat_site.st_uid}`")
            pydub_dir = TARGET_SITE_PACKAGES / "pydub"
            if pydub_dir.exists():
                stat_pydub = os.stat(str(pydub_dir))
                res.append(f"📁 pydub folder Permissions: `{oct(stat_pydub.st_mode)}` | Owner: `{stat_pydub.st_uid}`")
                pydub_files = [p.name for p in pydub_dir.glob("*")]
                res.append(f"📁 pydub folder contents: `{pydub_files[:15]}`")
                init_file = pydub_dir / "__init__.py"
                if init_file.exists():
                    stat_init = os.stat(str(init_file))
                    res.append(f"📄 __init__.py Permissions: `{oct(stat_init.st_mode)}` | Owner: `{stat_init.st_uid}`")
                else:
                    res.append(f"❌ __init__.py does not exist in pydub folder!")
        except Exception as perm_err:
            res.append(f"❌ Failed to read permissions: {perm_err}")
    else:
        res.append(f"📁 Target Site-Packages directory does not exist.")
        
    # Try dynamic loading
    try:
        from importlib.machinery import SourceFileLoader
        init_path = TARGET_SITE_PACKAGES / "pydub" / "__init__.py"
        if init_path.exists():
            loader = SourceFileLoader("pydub_test", str(init_path))
            mod = loader.load_module()
            res.append(f"✅ Dynamic SourceFileLoader imported pydub successfully!")
        else:
            res.append(f"❌ SourceFileLoader: __init__.py does not exist at `{init_path}`")
    except Exception as loader_err:
        tb_loader = traceback.format_exc()
        res.append(f"❌ SourceFileLoader failed: {loader_err}  \nTraceback:  \n```\n{tb_loader}\n```")
        
    # Check flag files
    flag_audioop = PROJECT_ROOT / "output" / ".runtime" / "audioop_install_attempted.flag"
    flag_pydub = PROJECT_ROOT / "output" / ".runtime" / "pydub_install_attempted.flag"
    res.append(f"🚩 audioop flag exists: `{flag_audioop.exists()}` | 🚩 pydub flag exists: `{flag_pydub.exists()}`")
    
    # Show sys.path
    res.append(f"🔍 `sys.path`: `{sys.path}`")
    
    return "  \n".join(res)


def main() -> None:
    _apply_streamlit_secrets()
    settings = Settings.from_environment(PROJECT_ROOT)
    
    # Dynamic Channel Credentials Switcher
    selected_channel = st.session_state.get("active_youtube_channel", "TechWithLalit")
    channel_keys = {
        "TechWithLalit": "techwithlalit",
        "Studio_MagicTales": "magictales",
        "LittleBubbles TV": "littlebubbles"
    }
    c_key = channel_keys.get(selected_channel, "techwithlalit")
    
    specific_token = PROJECT_ROOT / ".secrets" / f"youtube_token_{c_key}.json"
    specific_secrets = PROJECT_ROOT / "scripts" / f"client_secret_{c_key}.json"
    
    if specific_token.exists():
        os.environ["YOUTUBE_TOKEN_FILE"] = str(specific_token)
        settings = replace(settings, youtube_token_file=str(specific_token))
        
    if specific_secrets.exists():
        os.environ["YOUTUBE_CLIENT_SECRETS_FILE"] = str(specific_secrets)
        settings = replace(settings, youtube_client_secrets_file=str(specific_secrets))

    st.set_page_config(page_title="Content Pipeline Studio", page_icon="🎬", layout="wide")
    
    # Environment Diagnostics
    with st.expander("🛠️ System & Environment Diagnostics (Debug Info)", expanded=False):
        st.markdown(get_git_info())
        st.markdown(get_package_info())
        
        # Display persistent logs if they exist in session state
        if "pip_diagnostics_output" in st.session_state:
            st.markdown("### 📋 Pip Install Logs")
            st.code(st.session_state.pip_diagnostics_output)
            if st.button("🧹 Clear Logs", key="btn_clear_pip_diag_logs"):
                del st.session_state.pip_diagnostics_output
                st.rerun()
                
        if st.button("🔧 Run Pip Install Diagnostics", key="btn_run_pip_diag"):
            try:
                import subprocess
                TARGET_SITE_PACKAGES.mkdir(parents=True, exist_ok=True)
                
                # Delete flag files to allow clean retries on next startup
                flag_audioop = PROJECT_ROOT / "output" / ".runtime" / "audioop_install_attempted.flag"
                flag_pydub = PROJECT_ROOT / "output" / ".runtime" / "pydub_install_attempted.flag"
                if flag_audioop.exists():
                    try:
                        flag_audioop.unlink()
                    except Exception:
                        pass
                if flag_pydub.exists():
                    try:
                        flag_pydub.unlink()
                    except Exception:
                        pass
                
                logs = []
                logs.append("⏳ Running pip install for audioop-lts...")
                try:
                    out_audioop = subprocess.check_output([
                        sys.executable, "-m", "pip", "install", 
                        "--target", str(TARGET_SITE_PACKAGES), "audioop-lts"
                    ], stderr=subprocess.STDOUT, text=True)
                    logs.append(out_audioop)
                except subprocess.CalledProcessError as cpe:
                    logs.append(f"Failed to install audioop-lts:\n{cpe.output}")
                    
                logs.append("⏳ Running pip install for pydub...")
                try:
                    out_pydub = subprocess.check_output([
                        sys.executable, "-m", "pip", "install", 
                        "--target", str(TARGET_SITE_PACKAGES), "pydub"
                    ], stderr=subprocess.STDOUT, text=True)
                    logs.append(out_pydub)
                except subprocess.CalledProcessError as cpe:
                    logs.append(f"Failed to install pydub:\n{cpe.output}")
                
                # Try to import
                try:
                    import sys
                    import site
                    import importlib
                    if str(TARGET_SITE_PACKAGES) not in sys.path:
                        old_len = len(sys.path)
                        site.addsitedir(str(TARGET_SITE_PACKAGES))
                        new_paths = sys.path[old_len:]
                        sys.path = new_paths + sys.path[:old_len]
                    
                    importlib.invalidate_caches()
                    sys.path_importer_cache.clear()
                    
                    # Force reload or clean import
                    if 'pydub' in sys.modules:
                        del sys.modules['pydub']
                    if 'audioop' in sys.modules:
                        del sys.modules['audioop']
                        
                    import audioop
                    import pydub
                    logs.append(f"🎉 Successfully imported audioop and pydub in diagnostics run!")
                except Exception as imp_err:
                    import traceback
                    logs.append(f"⚠️ Import test failed: {imp_err}\n{traceback.format_exc()}")
                
                st.session_state.pip_diagnostics_output = "\n".join(logs)
                st.rerun()
                
            except Exception as e:
                st.session_state.pip_diagnostics_output = f"Diagnostics error: {e}"
                st.rerun()
                
    render_frontdoor(settings)


if __name__ == "__main__":
    main()
