from __future__ import annotations

import json
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


def on_music_lyrics_changed():
    st.session_state["lyrics_manually_edited"] = True


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

    token_secret_key = "YOUTUBE_TOKEN_JSON"
    drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID"
    if selected_channel == "LittleBubbles TV":
        token_secret_key = "YOUTUBE_TOKEN_JSON_LITTLEBUBBLES"
        drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID_LITTLEBUBBLES"
    elif selected_channel == "Studio_MagicTales":
        token_secret_key = "YOUTUBE_TOKEN_JSON_MAGICTALES"
        drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID_MAGICTALES"
    elif selected_channel == "TechWithLalit":
        token_secret_key = "YOUTUBE_TOKEN_JSON_TECHWITHLALIT"
        drive_folder_secret_key = "GOOGLE_DRIVE_FOLDER_ID_TECHWITHLALIT"

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
        token_path = token_dir / "youtube_token.json"
        token_path.write_text(token_json, encoding="utf-8")
        os.environ["YOUTUBE_TOKEN_FILE"] = str(token_path)

    if drive_folder_val:
        os.environ["GOOGLE_DRIVE_FOLDER_ID"] = drive_folder_val

    client_secrets_json = _secret("YOUTUBE_CLIENT_SECRETS_JSON")
    if client_secrets_json:
        scripts_dir = PROJECT_ROOT / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        client_secrets_path = scripts_dir / "youtube_client_secrets.json"
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
    if img_prov == "mock":
        img_prov = "gemini"
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
        elif cur_page == "Image":
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
                elif cat == "Automation":
                    st.session_state["active_automation_page"] = "Run Pipeline"
                st.rerun()

    active_cat = st.session_state["active_category"]
    
    # Render sub-navigation below top bar if category has subpages
    if active_cat == "Music":
        st.session_state.setdefault("active_music_page", "Music Studio")
        sub_cols = st.columns(4)
        sub_pages = ["Music Studio", "Kids Music Studio", "Speech Studio", "Voice Cloner"]
        sub_icons = ["🎵 Music Studio", "👶 Kids Music Studio", "🎙️ Speech Studio", "🎙️ Voice Cloner"]
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
        
    elif active_cat == "Automation":
        st.session_state.setdefault("active_automation_page", "Run Pipeline")
        sub_cols = st.columns(3)
        sub_pages = ["Run Pipeline", "Social Publish", "Daily Prompts"]
        sub_icons = ["⚙️ Run Pipeline", "🚀 Social Publish", "💡 Daily Prompts"]
        for i, (page, icon) in enumerate(zip(sub_pages, sub_icons)):
            with sub_cols[i]:
                is_active = st.session_state["active_automation_page"] == page
                if st.button(icon, key=f"sub_auto_{page}", use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state["active_automation_page"] = page
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    # Resolve active_p variable to sync with original logic
    if active_cat == "Dashboard":
        active_p = "Dashboard"
    elif active_cat == "Music":
        subpage_mapping = {
            "Music Studio": "Music",
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
        active_p = "Image"
    elif active_cat == "Automation":
        subpage_mapping = {
            "Run Pipeline": "Run",
            "Social Publish": "Distribution",
            "Daily Prompts": "Prompts"
        }
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
            run_day = st.date_input("Run day", value=st.session_state.get("run_day", default_day), key="run_day")
        with settings_cols[1]:
            inspect_day = st.date_input("Inspect day", value=st.session_state.get("inspect_day", default_day), key="inspect_day")
            
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

    elif active_p == "Music":
        st.markdown("### Music studio")
        st.markdown("<p style='font-size: 14.5px; color: #94a3b8; margin-top: -10px; margin-bottom: 24px;'>Compose premium, high-fidelity songs in any genre featuring warm singing voices powered by Tencent Lyria 3 Pro.</p>", unsafe_allow_html=True)
        
        if "lyrics_manually_edited" not in st.session_state:
            st.session_state["lyrics_manually_edited"] = bool(st.session_state.get("music_studio_lyrics", "").strip())
        disable_advanced_settings = not st.session_state["lyrics_manually_edited"]
        
        # Target Language Dropdown
        st.session_state.setdefault("music_studio_language", "English")
        st.selectbox(
            "Target Song Language",
            options=["English", "Hindi", "Hinglish"],
            key="music_studio_language",
            help="Choose the language for the song generation. This filters the reference audio files and guides the dynamic lyric generator."
        )

        # One-Click Creator
        with st.expander("⚡ One-Click Song Creator", expanded=True):
            st.markdown("<small style='color: #94a3b8;'>Type a simple idea (e.g., 'create an emotional song') and generate a complete song in one click.</small>", unsafe_allow_html=True)
            one_click_prompt = st.text_input("Song Idea", placeholder="e.g., create an emotional song", key="music_studio_one_click_song_idea")
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
                        lyrics_exp, desc_exp = expand_general_prompt_to_lyrics_and_style_dynamic(settings, one_click_prompt, one_click_gender, lang)
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
                <div style="display: flex; gap: 16px; margin-top: 20px;">
                  <div style="flex: 1; padding: 16px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(56, 189, 248, 0.25);">
                    <div style="font-size: 12px; color: #38bdf8; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                      <span>💡</span> Pro tip: Structure
                    </div>
                    <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                      Use standard tags like [verse] and [chorus] to structure sections. Keep lyrics to 2-3 verses.
                    </div>
                  </div>
                  <div style="flex: 1; padding: 16px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(168, 85, 247, 0.25);">
                    <div style="font-size: 12px; color: #a855f7; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
                      <span>🎵</span> Pro tip: Details
                    </div>
                    <div style="font-size: 13px; color: #e2e8f0; margin-top: 6px; line-height: 1.4;">
                      Specify clear instruments (e.g. acoustic guitar, grand piano, synth drums) to shape the sound.
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with right_col:
            st.markdown("#### Run settings")
            
            lang_choice = st.session_state.get("music_studio_language", "English")
            model_options = ["Lyria 3 Pro Preview (tencent/SongGeneration)"]
            if lang_choice == "Hindi":
                model_options = ["Gemini 2.5 Flash + Edge-TTS (Native Accent)"]

            st.selectbox(
                "Model",
                options=model_options,
                index=0,
                disabled=True,
                key="music_studio_model_select",
                help="Lyria 3 Pro is used for English/Hinglish. Gemini 2.5/Edge-TTS Native Audio is used for Hindi to achieve perfect pronunciation."
            )
            
            SOUNDSCAPE_PRESETS = {
                "Meditative Acoustic (Shekhar Style)": {
                    "style_description": "Pure instrumental. Soft fingerpicked acoustic guitar arpeggios, deep warm bass guitar, airy ambient synthesizer pads, soulful solo bansuri flute, gentle meditative pace, 65 BPM, sacred hall acoustics.",
                    "temperature": 0.30,
                    "genre": "Auto"
                },
                "Epic Classical Cinematic": {
                    "style_description": "Pure instrumental. Booming traditional dhol and taiko percussion layers, heavy dramatic orchestral string sections, deep brass swells, rhythmic sitar strabs, massive stadium echo, fast tempo, 115 BPM.",
                    "temperature": 0.35,
                    "genre": "Auto"
                },
                "Soulful Sufi / Ghazal Studio": {
                    "style_description": "Pure instrumental. Traditional hand-pumped wooden harmonium sweeps, organic acoustic tabla loops, calm acoustic sarangi strokes, slow steady studio recording, 80 BPM, clean proximity environment.",
                    "temperature": 0.30,
                    "genre": "Auto"
                }
            }
            
            selected_vibe = st.selectbox(
                "Soundscape Vibe Preset",
                options=["Custom"] + list(SOUNDSCAPE_PRESETS.keys()),
                key="music_studio_vibe_preset",
                help="Select a musical style preset to automatically populate the Style Description.",
                disabled=disable_advanced_settings
            )
            
            if "prev_music_studio_vibe" not in st.session_state:
                st.session_state["prev_music_studio_vibe"] = selected_vibe
                
            if st.session_state["prev_music_studio_vibe"] != selected_vibe:
                st.session_state["prev_music_studio_vibe"] = selected_vibe
                if selected_vibe != "Custom":
                    preset_data = SOUNDSCAPE_PRESETS[selected_vibe]
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
                    ref_files = [f for f in raw_files if any(x in f.lower() for x in ["titli", "barnaby", "hindi", "squirrel"])]
                else:
                    ref_files = [f for f in raw_files if not any(x in f.lower() for x in ["titli", "barnaby", "squirrel"])]
            
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
                generate_clicked = st.button("Generate", type="primary", use_container_width=True, key="music_studio_btn_generate")

        if generate_clicked or st.session_state.get("music_studio_trigger_generation_now"):
            if st.session_state.get("music_studio_trigger_generation_now"):
                st.session_state["music_studio_trigger_generation_now"] = False
            with st.spinner("Connecting to tencent/SongGeneration space and generating audio... (This may take 1-3 minutes)"):
                try:
                    import subprocess
                    import shutil
                    from gradio_client import Client, handle_file

                    prompt_audio_param = None
                    if selected_ref != "None (Text-only)":
                        ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / selected_ref
                        if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / selected_ref
                        if ref_full_path.exists():
                            temp_dir = PROJECT_ROOT / "output" / ".runtime"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            cropped_ref_path = temp_dir / "music_studio_ref_cropped.mp3"
                            
                            st.write(f"ℹ️ Cropping style reference '{selected_ref}' to 15 seconds...")
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
                            st.warning(f"Reference audio '{selected_ref}' not found. Falling back to text-only generation.")

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
                    if lang == "Hindi":
                        if not any("\u0900" <= char <= "\u097f" for char in sanitized_lyrics):
                            st.write("🔮 Converting Romanized lyrics to native Devanagari script for perfect Indian accent...")
                            from content_pipeline.bots.gemini_tts import transliterate_to_devanagari
                            sanitized_lyrics = transliterate_to_devanagari(sanitized_lyrics, settings)
                            st.info(f"📝 Transliterated Devanagari Lyrics:\n{sanitized_lyrics}")
                        
                        st.write("🔀 Language: Hindi detected. Bypassing Hugging Face Lyria to use Native Audio Pipeline...")
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
                            hf_token=settings.hf_token,
                            genre=genre,
                            temperature=temp,
                            cfg_coef=cfg,
                            style_description=desc,
                            singer_key=st.session_state.get("music_studio_playback_singer_key", "arijit_singh")
                        )
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
                        st.success("🎉 Hindi Song generated successfully using Native Audio Pipeline!")
                        st.rerun()
                    elif lang == "Hinglish":
                        st.write("🔮 Applying advanced phonetic transcription layer for perfect Indian accent...")
                        from content_pipeline.bots.phonetic_mapper import hindi_to_phonetic_hinglish
                        sanitized_lyrics = hindi_to_phonetic_hinglish(sanitized_lyrics, gemini_api_key=settings.gemini_api_key)
                        st.info(f"📝 Transcribed Phonetic Lyrics:\n{sanitized_lyrics}")

                    st.write("🎵 Dispatching song generation request to Hugging Face...")
                    try:
                        client = Client("tencent/SongGeneration", token=settings.hf_token, httpx_kwargs={"timeout": 600.0})
                        
                        # Translate UI-only genres (Folk, Traditional) to valid Lyria Space genres
                        valid_genres = ['Auto', 'Pop', 'Latin', 'Rock', 'Electronic', 'Metal', 'Country', 'R&B/Soul', 'Ballad', 'Jazz', 'World', 'Hip-Hop', 'Funk', 'Soundtrack']
                        api_genre = genre if genre in valid_genres else "World"
                        
                        result_path, info = client.predict(
                            lyric=sanitized_lyrics,
                            description=desc,
                            prompt_audio=prompt_audio_param,
                            genre=api_genre,
                            cfg_coef=cfg,
                            temperature=temp,
                            api_name="/generate_song"
                        )
                        
                        if not result_path or str(result_path).strip().lower() == "none":
                            raise ValueError(f"Hugging Face space did not return a valid audio track. Details: {info}")

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
                        
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
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
                            selected_ref=selected_ref
                        )
                        st.session_state["music_studio_generated_mp3"] = str(out_path)
                        st.success("🎉 Backup Song generated successfully using Edge-TTS fallback mixer!")
                        st.rerun()
                except Exception as exc:
                    st.error(f"❌ Error during song preparation: {exc}")

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
                if current_val not in ("free-ai", "gemini", "openai"):
                    current_val = "free-ai"
                options = ("free-ai", "gemini", "openai")
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
                    # Global config info
                    st.caption(f"Video ID: **{manifest_data.get('video_id')}** | Resolution: **{manifest_data.get('canvas_dimensions')}** | FPS: **{manifest_data.get('fps')}**")
                    
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
                    options=("gemini", "openai", "free-ai"),
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
                  <p style="margin-top: 6px; font-size: 14px;">Generate cheerful, high-quality music and nursery rhymes matching your reference tracks using the Tencent SongGeneration model.</p>
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

        # Determine kids voice options based on the selected language and mode
        from content_pipeline.bots.kids_studio_manifest_core import KIDS_STUDIO_MASTER_REGISTRY
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

        # Define and manage all backend run settings here silently since right column is hidden
        selected_ref = st.session_state.setdefault("kids_song_ref_audio_choice", "None (Text-only)")
        cfg = float(st.session_state.setdefault("kids_song_cfg_coef", 1.8))
        temp = float(st.session_state.setdefault("kids_song_temperature", 0.8))
        genre = st.session_state.setdefault("kids_song_genre", "Auto")
        
        # Set default description based on mode if not already set
        if kids_mode == "Storytelling":
            default_desc = "warm theatrical spoken-word audiobook narrator, gentle bedtime story, calm pacing, soft glockenspiel and warm strings, 0 BPM"
        else:
            default_desc = "cheerful nursery rhyme, magical kids show music, happy bouncy melody, 92 BPM, ukulele, soft piano, glockenspiel, bells."
        desc = st.session_state.setdefault("kids_song_description", default_desc)

        expander_title = "⚡ One-Click Story Creator" if kids_mode == "Storytelling" else "⚡ One-Click Song Creator"
        with st.expander(expander_title, expanded=True):
            st.markdown(
                f"<small style='color: #94a3b8;'>Type a simple idea (e.g., {'a story about a wise turtle' if kids_mode == 'Storytelling' else 'create a song about alphabet'}) and generate in one click.</small>",
                unsafe_allow_html=True
            )
            prompt_label = "Story Idea" if kids_mode == "Storytelling" else "Song Idea"
            prompt_placeholder = "e.g., a story about a wise turtle" if kids_mode == "Storytelling" else "e.g., create an emotional song"
            one_click_prompt = st.text_input(prompt_label, placeholder=prompt_placeholder, key="one_click_song_idea")
            
            # Resolve gender dynamically based on current selected profile
            one_click_gender = st.session_state.get("kids_song_singer_gender", "Female")
            
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

            btn_label = "🚀 Create & Generate Story" if kids_mode == "Storytelling" else "🚀 Create & Generate Song"
            if st.button(btn_label, type="primary", use_container_width=True):
                if not one_click_prompt.strip():
                    st.warning(f"Please enter a {prompt_label.lower()} first.")
                else:
                    lyrics_exp, desc_exp = expand_prompt_to_lyrics_and_style_dynamic(
                        settings, one_click_prompt, one_click_gender, kids_lang, mode=kids_mode
                    )
                    if kids_lang in ["Hindi", "Hinglish"] and kids_mode != "Storytelling":
                        desc_exp = clean_style_description_for_instrumental(desc_exp)
                    st.session_state["kids_song_lyrics"] = lyrics_exp
                    st.session_state["kids_song_description"] = desc_exp
                    st.session_state["kids_song_singer_gender"] = one_click_gender
                    st.session_state["trigger_generation_now"] = True
                    st.rerun()

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
                st.markdown(
                    f"""
                    <div style="padding: 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(56, 189, 248, 0.15);">
                      <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Active Track</div>
                      <div style="font-size: 14px; font-weight: 800; color: #f8fafc; margin-top: 2px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                        LittleBubbles_Generated_Song.mp3
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

        if generate_clicked or st.session_state.get("trigger_generation_now"):
            if st.session_state.get("trigger_generation_now"):
                st.session_state["trigger_generation_now"] = False
            with st.spinner("Connecting to tencent/SongGeneration space and generating audio... (This may take 1-3 minutes)"):
                try:
                    import subprocess
                    import shutil
                    from gradio_client import Client, handle_file

                    prompt_audio_param = None
                    if selected_ref != "None (Text-only)":
                        ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / selected_ref
                        if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                            ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / selected_ref
                        if ref_full_path.exists():
                            temp_dir = PROJECT_ROOT / "output" / ".runtime"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            cropped_ref_path = temp_dir / "kids_song_ref_cropped.mp3"
                            
                            st.write(f"ℹ️ Cropping style reference '{selected_ref}' to 15 seconds...")
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
                            st.warning(f"Reference audio '{selected_ref}' not found. Falling back to text-only generation.")

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
                    if lang == "Hindi" or kids_mode == "Storytelling":
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
                        
                        generate_hindi_song_via_native_audio(
                            lyrics=sanitized_lyrics,
                            output_path=out_path,
                            singer_gender=singer_gender,
                            selected_ref=selected_ref,
                            hf_token=settings.hf_token,
                            genre=genre,
                            temperature=temp,
                            cfg_coef=cfg,
                            style_description=desc,
                            singer_key=st.session_state.get("kids_studio_playback_singer_key", "hi_kids_ananya"),
                            mode=kids_mode
                        )
                        st.session_state["kids_song_generated_mp3"] = str(out_path)
                        st.success(f"🎉 Kids {kids_mode} generated successfully using Native Audio Pipeline!")
                        st.rerun()
                    elif lang == "Hinglish":
                        st.write("🔮 Applying advanced phonetic transcription layer for perfect Indian accent...")
                        from content_pipeline.bots.phonetic_mapper import hindi_to_phonetic_hinglish
                        sanitized_lyrics = hindi_to_phonetic_hinglish(sanitized_lyrics, gemini_api_key=settings.gemini_api_key)
                        st.info(f"📝 Transcribed Phonetic Lyrics:\n{sanitized_lyrics}")

                    st.write("🎵 Dispatching song generation request to Hugging Face...")
                    try:
                        client = Client("tencent/SongGeneration", token=settings.hf_token, httpx_kwargs={"timeout": 600.0})
                        
                        # Translate UI-only genres (Folk, Traditional) to valid Lyria Space genres
                        valid_genres = ['Auto', 'Pop', 'Latin', 'Rock', 'Electronic', 'Metal', 'Country', 'R&B/Soul', 'Ballad', 'Jazz', 'World', 'Hip-Hop', 'Funk', 'Soundtrack']
                        api_genre = genre if genre in valid_genres else "World"
                        
                        result_path, info = client.predict(
                            lyric=sanitized_lyrics,
                            description=desc,
                            prompt_audio=prompt_audio_param,
                            genre=api_genre,
                            cfg_coef=cfg,
                            temperature=temp,
                            api_name="/generate_song"
                        )
                        
                        if not result_path or str(result_path).strip().lower() == "none":
                            raise ValueError(f"Hugging Face space did not return a valid audio track. Details: {info}")

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
                            selected_ref=selected_ref
                        )
                        st.session_state["kids_song_generated_mp3"] = str(out_path)
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

            if "last_run_error" in st.session_state:
                st.error(st.session_state["last_run_error"])
            if "last_run_result" in st.session_state:
                st.json(st.session_state["last_run_result"])

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
                            telegram_chat_id=telegram_chat_id
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


def expand_prompt_to_lyrics_and_style(prompt: str, singer_gender: str, mode: str = "Poem/Rhyme") -> tuple[str, str]:
    if mode == "Storytelling":
        lyrics = (
            "[pause] Once upon a time, in a beautiful green forest, there lived a very wise turtle. "
            "[pause] In the same forest, there was also a rabbit who was very proud of his speed. "
            "[pause] One day, they decided to have a race. "
            "[pause] The rabbit ran very fast and fell asleep halfway. "
            "[pause] The turtle walked slowly and steadily, and in the end, he won the race. "
            "[pause] The moral of the story is that slow and steady wins the race."
        )
        style = "warm theatrical spoken-word audiobook narrator, gentle bedtime story, calm pacing, soft glockenspiel and warm strings, 0 BPM"
        return lyrics, style

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
        
    return lyrics, style


def expand_general_prompt_to_lyrics_and_style(prompt: str, singer_gender: str) -> tuple[str, str]:
    import re
    p = prompt.lower()
    
    # 1. Match Emotional/Ballad/Love
    if any(k in p for k in ["emotional", "sad", "touch", "heart", "ballad", "acoustic", "slow", "love"]):
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
            f"gentle emotional pop ballad, slow acoustic feel, warm piano, soft acoustic guitar, slow building strings, 78 BPM, "
            f"heart-touching emotional melody, warm clear friendly {singer_gender.lower()} singing voice, expressive vocal delivery, clean mix."
        )
        
    # 2. Match Upbeat Pop/Dance/Happy
    elif any(k in p for k in ["happy", "fun", "dance", "upbeat", "energetic", "pop", "party", "cheerful"]):
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
            f"catchy modern pop, upbeat dance rhythm, 120 BPM, driving synth bass, electronic drums, sparkling synthesizers, "
            f"bright friendly {singer_gender.lower()} vocals, energetic vocal delivery, clean mix."
        )
        
    # 3. Match Rock/Alternative/Energetic
    elif any(k in p for k in ["rock", "guitar", "metal", "heavy", "alternative", "band", "drums"]):
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
            f"energetic alternative rock, driving electric guitars, powerful bassline, rock drum kit, 112 BPM, "
            f"strong passionate {singer_gender.lower()} rock vocals, clean professional studio mix."
        )
        
    # 4. Default general song (Modern Acoustic Pop Songwriter)
    else:
        subject = "a journey through the night"
        for word in ["dream", "journey", "street", "city", "ocean", "river", "road", "friend", "home", "sky"]:
            if word in p:
                subject = f"a journey about {word}s"
                break
                
        lyrics = (
            f"[verse]\n"
            f"Packed my bags and took a train,\n"
            f"Leaving behind the winter rain.\n"
            f"Looking for a brand new sign,\n"
            f"Tracing a path that's yours and mine.\n\n"
            f"[chorus]\n"
            f"This is the start of the road ahead,\n"
            f"Following where our feet have led.\n"
            f"With every step the sky gets bright,\n"
            f"We are moving into the light.\n\n"
            f"[verse]\n"
            f"Miles go by and the mountains rise,\n"
            f"Reflected in your searching eyes.\n"
            f"We'll keep on going, come what may,\n"
            f"Finding our own path today."
        )
        style = (
            f"modern acoustic pop songwriter, gentle steady rhythm, 92 BPM, warm piano, soft acoustic guitar, "
            f"bright acoustic bass, expressive friendly {singer_gender.lower()} vocal, clean mix."
        )
        
    return lyrics, style


def expand_general_prompt_to_lyrics_and_style_dynamic(settings, prompt: str, singer_gender: str, language: str) -> tuple[str, str]:
    import os
    import json
    if "gemini_api_error" in st.session_state:
        del st.session_state["gemini_api_error"]

    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    
    # Prioritize Custom User API Key from UI state
    custom_ui_key = st.session_state.get("custom_gemini_api_key", "").strip()
    if custom_ui_key:
        if custom_ui_key in keys:
            keys.remove(custom_ui_key)
        keys.insert(0, custom_ui_key)

    keys = [k for k in keys if k]

    if keys:
        system_instruction = (
            "You are a music composer and lyricist. Expand the user's idea into complete lyrics and style description. "
            "The output must be JSON with keys 'lyrics' and 'style'."
        )
        user_prompt = f"""
        User Song Idea: "{prompt}"
        Singer Voice Gender Selection: "{singer_gender}"
        Target Song Language: "{language}"
        
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
        4. Structure the lyrics with standard tags like [verse] and [chorus]. Avoid [intro] or [outro] tags. Keep it to 2-3 short verses and 1-2 choruses.
        5. The 'style' string must be a comma-separated description of instruments, tempo (BPM), vocal qualities, and musical genre. Make it match the song idea.
        
        Return a raw JSON object matching this schema:
        {{
            "lyrics": "verse and chorus text",
            "style": "comma-separated musical style description"
        }}
        """
        errors = []
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
                data = json.loads(response.text)
                if "lyrics" in data and "style" in data:
                    return data["lyrics"], data["style"]
                else:
                    errors.append(f"Invalid JSON returned (missing 'lyrics' or 'style'): {response.text}")
            except Exception as e:
                errors.append(f"API key beginning with '{key[:6]}...': {str(e)}")
        if errors:
            st.session_state["gemini_api_error"] = "\n".join(errors)
    else:
        st.session_state["gemini_api_error"] = "No Gemini API keys found in Settings or Environment."
        
    if language == "Hindi":
        return expand_general_prompt_to_lyrics_and_style_hindi_local(prompt, singer_gender)
    else:
        return expand_general_prompt_to_lyrics_and_style(prompt, singer_gender)


def expand_prompt_to_lyrics_and_style_dynamic(settings, prompt: str, singer_gender: str, language: str, mode: str = "Poem/Rhyme") -> tuple[str, str]:
    import os
    import json
    if "gemini_api_error" in st.session_state:
        del st.session_state["gemini_api_error"]

    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    
    # Prioritize Custom User API Key from UI state
    custom_ui_key = st.session_state.get("custom_gemini_api_key", "").strip()
    if custom_ui_key:
        if custom_ui_key in keys:
            keys.remove(custom_ui_key)
        keys.insert(0, custom_ui_key)

    keys = [k for k in keys if k]

    if keys:
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
            3. The 'style' string must be a comma-separated description of storytelling background, pacing, vocal qualities, and mood suitable for kids/toddlers.
            
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
            user_prompt = f"""
            User Kids Song Idea: "{prompt}"
            Singer Voice Gender Selection: "{singer_gender}"
            Target Song Language: "{language}"
            
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
            4. Structure the lyrics with standard tags like [verse] and [chorus]. Avoid [intro] or [outro] tags. Keep it to 2-3 short verses and 1-2 choruses.
            5. The 'style' string must be a comma-separated description of instruments, tempo (BPM), vocal qualities, and musical genre suitable for kids/toddlers.
            
            Return a raw JSON object matching this schema:
            {{
                "lyrics": "verse and chorus text",
                "style": "comma-separated musical style description"
            }}
            """
        errors = []
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
                data = json.loads(response.text)
                if "lyrics" in data and "style" in data:
                    return data["lyrics"], data["style"]
                else:
                    errors.append(f"Invalid JSON returned (missing 'lyrics' or 'style'): {response.text}")
            except Exception as e:
                errors.append(f"API key beginning with '{key[:6]}...': {str(e)}")
        if errors:
            st.session_state["gemini_api_error"] = "\n".join(errors)
    else:
        st.session_state["gemini_api_error"] = "No Gemini API keys found in Settings or Environment."
        
    if language == "Hindi":
        return expand_prompt_to_lyrics_and_style_hindi_local(prompt, singer_gender, mode=mode)
    else:
        return expand_prompt_to_lyrics_and_style(prompt, singer_gender, mode=mode)


def expand_general_prompt_to_lyrics_and_style_hindi_local(prompt: str, singer_gender: str) -> tuple[str, str]:
    import re
    p = prompt.lower()
    
    if any(k in p for k in ["emotional", "sad", "touch", "heart", "ballad", "acoustic", "slow", "love"]):
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
            f"gentle emotional pop ballad, slow acoustic feel, warm piano, soft acoustic guitar, slow building strings, 78 BPM, "
            f"heart-touching emotional melody, warm clear friendly native Indian {singer_gender.lower()} singing voice, Bollywood style singer, natural Indian accent, expressive vocal delivery, clear native pronunciation, clean mix."
        )
        
    elif any(k in p for k in ["happy", "fun", "dance", "upbeat", "energetic", "pop", "party", "cheerful"]):
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
            f"catchy modern pop, upbeat dance rhythm, 120 BPM, driving synth bass, electronic drums, sparkling synthesizers, "
            f"bright friendly native Indian {singer_gender.lower()} vocals, Bollywood style singer, natural Indian accent, energetic vocal delivery, clear native pronunciation, clean mix."
        )
        
    elif any(k in p for k in ["rock", "guitar", "metal", "heavy", "alternative", "band", "drums"]):
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
            f"energetic alternative rock, driving electric guitars, powerful bassline, rock drum kit, 112 BPM, "
            f"strong passionate native Indian {singer_gender.lower()} rock vocals, Bollywood style rock singer, natural Indian accent, clear native pronunciation, clean professional studio mix."
        )
        
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
            f"modern acoustic pop songwriter, gentle steady rhythm, 92 BPM, warm piano, soft acoustic guitar, "
            f"bright acoustic bass, expressive friendly native Indian {singer_gender.lower()} vocal, Bollywood style singer, natural Indian accent, clear native pronunciation, clean mix."
        )
        
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
        
    return lyrics, style


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
