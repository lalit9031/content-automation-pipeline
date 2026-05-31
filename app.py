from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from collections.abc import Mapping

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
import streamlit.components.v1 as components

from content_pipeline.bots.audio import audio_status, render_audio_status_html
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


def latest_daily_day(output_dir: Path) -> str | None:
    daily_root = output_dir / "daily"
    if not daily_root.exists():
        return None
    days = sorted(path.name for path in daily_root.iterdir() if path.is_dir())
    return days[-1] if days else None


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def file_chip(label: str, path: Path) -> str:
    return f"""
    <div class="file-chip">
      <div class="file-chip-label">{label}</div>
      <div class="file-chip-path">{path}</div>
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


def render_frontdoor(settings: Settings) -> None:
    latest_day = latest_daily_day(settings.output_dir)
    default_day = date.fromisoformat(latest_day) if latest_day else date.today()

    st.sidebar.header("Studio Controls")
    output_dir_input = st.sidebar.text_input("Output directory", value=str(settings.output_dir))
    run_day = st.sidebar.date_input("Run day", value=default_day)
    inspect_day = st.sidebar.date_input("Inspect day", value=default_day)
    show_json = st.sidebar.checkbox("Show raw JSON", value=False)

    ui_settings = replace(settings, output_dir=resolve_output_dir(output_dir_input))
    run_date = run_day.isoformat()
    inspect_date = inspect_day.isoformat()

    st.markdown(
        """
        <style>
          .hero {
            padding: 24px;
            border-radius: 24px;
            background: linear-gradient(135deg, rgba(15,23,42,.92), rgba(2,6,23,.92));
            border: 1px solid #334155;
            margin-bottom: 18px;
          }
          .hero h1 {
            margin: 0;
            font-size: 34px;
            letter-spacing: -0.03em;
            color: #f8fafc;
          }
          .hero p {
            margin-top: 8px;
            color: #94a3b8;
            line-height: 1.5;
          }
          .metric-box, .file-chip, .panel-box {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid #334155;
            border-radius: 18px;
            padding: 16px;
          }
          .metric-label {
            font-size: 12px;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: #94a3b8;
          }
          .metric-value {
            margin-top: 6px;
            font-size: 22px;
            font-weight: 800;
            color: #f8fafc;
          }
          .file-chip + .file-chip { margin-top: 10px; }
          .file-chip-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: #7dd3fc;
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
            A friendly front door for your daily pipeline, unified audio status, blocker memory,
            and image style tooling. Run it locally, inspect the artifacts, and open the daily
            dashboard without bouncing between the CLI and output folders.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
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

    tab_run, tab_dashboard, tab_audio, tab_files = st.tabs(
        ["Run", "Dashboard", "Audio", "Files"]
    )

    with tab_run:
        left, right = st.columns([1.2, 0.8])
        with left:
            st.subheader("Run the daily pipeline")
            st.write("This triggers the same daily content generation flow your CLI uses.")
            if st.button("Run pipeline", type="primary", use_container_width=True):
                with st.spinner(f"Generating the daily run for {run_date}..."):
                    try:
                        result = run_linkedin_mvp(run_date, ui_settings)
                    except Exception as exc:
                        st.session_state["last_run_error"] = str(exc)
                    else:
                        st.session_state["last_run_result"] = result
                        st.session_state["last_run_day"] = run_date
                        st.success(f"Pipeline complete for {run_date}")

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
            current_day_dir = ui_settings.output_dir / "daily" / inspect_date
            dashboard_path = current_day_dir / "daily_dashboard.html"
            audio_path = current_day_dir / "audio_status.html"
            voice_path = current_day_dir / "voice_status.html"
            st.markdown(file_chip("Daily dashboard", dashboard_path), unsafe_allow_html=True)
            st.markdown(file_chip("Audio front door", audio_path), unsafe_allow_html=True)
            st.markdown(file_chip("Voice status", voice_path), unsafe_allow_html=True)
            if dashboard_path.exists():
                st.markdown(f"[Open daily dashboard]({dashboard_path.as_uri()})")
            if audio_path.exists():
                st.markdown(f"[Open audio front door]({audio_path.as_uri()})")

    with tab_dashboard:
        st.subheader("Daily dashboard")
        dashboard_path = ui_settings.output_dir / "daily" / inspect_date / "daily_dashboard.html"
        if dashboard_path.exists():
            dashboard_html = dashboard_path.read_text(encoding="utf-8")
            components.html(dashboard_html, height=1150, scrolling=True)
        else:
            st.info("Run the pipeline or pick a day that already has a daily dashboard.")
            st.caption(str(dashboard_path))

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
            else:
                st.write("No voice bundle found for this day.")

    with tab_files:
        st.subheader("Artifacts")
        day_root = ui_settings.output_dir / "daily" / inspect_date
        if day_root.exists():
            all_files = sorted(
                [path for path in day_root.rglob("*") if path.is_file()],
                key=lambda path: path.as_posix(),
            )
            if show_json:
                st.code("\n".join(str(path) for path in all_files), language="text")
            else:
                for path in all_files:
                    st.markdown(f"- `{path.relative_to(day_root)}`")
        else:
            st.info("No daily artifacts found yet for this day.")


def main() -> None:
    _apply_streamlit_secrets()
    settings = Settings.from_environment(PROJECT_ROOT)
    st.set_page_config(page_title="Content Pipeline Studio", page_icon="🎬", layout="wide")
    render_frontdoor(settings)


if __name__ == "__main__":
    main()
