from __future__ import annotations

import json
import os
import sys
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
    else:
        file_count = 0
    return {
        "file_count": file_count,
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


def render_frontdoor(settings: Settings) -> None:
    latest_day = latest_daily_day(settings.output_dir)
    default_day = date.fromisoformat(latest_day) if latest_day else date.today()

    st.sidebar.header("Studio Controls")
    output_dir_input = st.sidebar.text_input("Output directory", value=str(settings.output_dir))
    if st.sidebar.button("Load latest day", use_container_width=True, disabled=not latest_day):
        st.session_state["run_day"] = default_day
        st.session_state["inspect_day"] = default_day
        st.rerun()
    recent_days = recent_daily_days(settings.output_dir)
    selected_day = st.sidebar.selectbox(
        "Recent days",
        options=recent_days,
        index=0 if recent_days else None,
        disabled=not recent_days,
    )
    if st.sidebar.button("Load selected day", use_container_width=True, disabled=not recent_days):
        selected = date.fromisoformat(selected_day)
        st.session_state["run_day"] = selected
        st.session_state["inspect_day"] = selected
        st.rerun()
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

    ui_settings = replace(settings, output_dir=resolve_output_dir(output_dir_input))
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
    selected_day_dir = ui_settings.output_dir / "daily" / inspect_date
    selected_overview = day_overview(selected_day_dir)

    st.markdown(
        f"""
        <div class="status-strip">
          {status_pill("Prompt provider", settings.prompt_provider)}
          {status_pill("Image provider", settings.image_provider)}
          {status_pill("Voice provider", settings.voice_provider)}
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

    tab_run, tab_dashboard, tab_audio, tab_files = st.tabs(
        ["Run", "Dashboard", "Audio", "Files"]
    )

    with tab_run:
        left, right = st.columns([1.2, 0.8])
        with left:
            st.subheader("Run the daily pipeline")
            st.write("This triggers the same daily content generation flow your CLI uses.")
            st.caption(
                f"Latest day: {latest_day or 'none yet'} · Files in latest run: {latest_file_count}"
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
        st.markdown(
            f"[Open dashboard file]({dashboard_path.as_uri()})" if dashboard_path.exists() else "",
            unsafe_allow_html=True,
        )

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

        day_root = selected_day_dir
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
