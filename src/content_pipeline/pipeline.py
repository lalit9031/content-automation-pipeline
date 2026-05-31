from __future__ import annotations

from dataclasses import asdict
from html import escape

from content_pipeline.bots.image import (
    gemini_image_package_plan,
    gemini_image_status,
    generate_images,
    image_provider,
    render_gemini_image_status_widget,
)
from content_pipeline.bots.blocker_agent import blocker_status, blocker_status_html
from content_pipeline.bots.blocker_agent import load_blocker_journal
from content_pipeline.bots.audio import (
    audio_status,
    render_audio_status_html,
    render_voice_status_html,
    voice_status,
    write_voice_daily_artifacts,
)
from content_pipeline.bots.infographic import render_linkedin_infographic
from content_pipeline.bots.linkedin import prepare_linkedin_post
from content_pipeline.bots.prompt import build_image_style_pack, prompt_provider
from content_pipeline.config import Settings
from content_pipeline.content_history import ContentHistory, record_history_entry
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


def run_linkedin_mvp(day: str, settings: Settings) -> dict[str, object]:
    storage = LocalDailyStorage(settings.output_dir)
    history = ContentHistory.load(settings.output_dir)
    package = prompt_provider(settings).generate(day, avoid_topics=history.recent_topics())
    prompt_path = storage.write_json(day, "prompt.json", package.as_dict())
    image_style_pack = build_image_style_pack(
        package.topic,
        subject=package.linkedin_infographic.headline,
        audience="professional audiences",
    )
    image_style_pack_path = storage.write_json(day, "image_style_pack.json", image_style_pack.as_dict())
    image_storyboard_path = storage.write_json(day, "image_storyboard_prompts.json", image_style_pack.storyboard_prompts)
    thumbnail_prompt_path = storage.write_text(day, "thumbnail_prompt.txt", image_style_pack.thumbnail_prompt)
    voice_artifacts = write_voice_daily_artifacts(settings.output_dir, settings, day=day)
    voice_status_payload = voice_status(settings.output_dir, settings, day=day)
    image_quota_plan = gemini_image_package_plan(settings, packages_requested=1)
    quota_plan_path = storage.write_json(day, "gemini_image_plan.json", image_quota_plan)
    image_files = generate_images(
        package,
        image_provider(settings),
        storage,
        max_dimension=settings.image_max_dimension,
        max_bytes=settings.image_max_bytes,
        request_delay_seconds=settings.image_request_delay_seconds,
    )
    image_quota_status = gemini_image_status(settings)
    quota_status_path = storage.write_json(day, "gemini_image_status.json", image_quota_status)
    quota_widget_path = storage.write_text(
        day,
        "gemini_image_status.html",
        render_gemini_image_status_widget(settings),
    )
    blocker_quota_status = blocker_status(settings.output_dir)
    blocker_status_path = storage.write_json(day, "blocker_status.json", blocker_quota_status)
    blocker_snapshot_path = storage.write_json(
        day,
        "blocker_journal_snapshot.json",
        load_blocker_journal(settings.output_dir),
    )
    blocker_suggestions_path = storage.write_json(
        day,
        "blocker_suggestions.json",
        blocker_quota_status.get("suggestions", []),
    )
    blocker_widget_path = storage.write_text(
        day,
        "blocker_status.html",
        blocker_status_html(settings.output_dir),
    )
    voice_widget_path = storage.write_text(
        day,
        "voice_status.html",
        render_voice_status_html(voice_status_payload),
    )
    audio_status_payload = audio_status(settings.output_dir, settings, day=day)
    audio_status_json_path = storage.write_json(day, "audio_status.json", audio_status_payload)
    audio_status_html_path = storage.write_text(
        day,
        "audio_status.html",
        render_audio_status_html(audio_status_payload),
    )
    daily_dashboard_path = storage.write_text(
        day,
        "daily_dashboard.html",
        _render_daily_dashboard_html(
            day=day,
            quota_widget=render_gemini_image_status_widget(settings),
            blocker_widget=blocker_status_html(settings.output_dir),
            voice_widget=render_voice_status_html(voice_status_payload),
            audio_status_path=str(audio_status_html_path),
            quota_plan=image_quota_plan,
            blocker_status_payload=blocker_quota_status,
            voice_status_payload=voice_status_payload,
        ),
    )
    linkedin_image = render_linkedin_infographic(package, storage)
    receipt = prepare_linkedin_post(package, linkedin_image, settings, storage)
    history_path = record_history_entry(
        settings.output_dir,
        date=day,
        kind="linkedin_post",
        topic=package.topic,
        title=package.seo_title,
        platform="linkedin",
        reference=package.seo_title,
        url=settings.youtube_channel_url,
        source="run_linkedin_mvp",
    )
    provider_mode = (
        "mock"
        if settings.prompt_provider == "mock" and settings.image_provider == "mock"
        else "live"
    )
    artifacts: dict[str, object] = {
        "prompt": str(prompt_path),
        "image_style_pack": str(image_style_pack_path),
        "image_storyboard_prompts": str(image_storyboard_path),
        "thumbnail_prompt": str(thumbnail_prompt_path),
        "voice_profile": str(voice_artifacts["voice_profile"]),
        "voice_normalization_preview": str(voice_artifacts["voice_normalization_preview"]),
        "voice_samples_manifest": str(voice_artifacts["voice_samples_manifest"]),
        "voice_samples_readme": str(voice_artifacts["voice_samples_readme"]),
        "voice_status": str(voice_artifacts["voice_status"]),
        "voice_status_widget": str(voice_widget_path),
        "audio_status": str(audio_status_json_path),
        "audio_status_widget": str(audio_status_html_path),
        "gemini_image_status": str(quota_status_path),
        "gemini_image_plan": str(quota_plan_path),
        "gemini_image_status_widget": str(quota_widget_path),
        "blocker_status": str(blocker_status_path),
        "blocker_journal_snapshot": str(blocker_snapshot_path),
        "blocker_suggestions": str(blocker_suggestions_path),
        "blocker_status_widget": str(blocker_widget_path),
        "daily_dashboard": str(daily_dashboard_path),
        "images": image_files,
        "linkedin_image": linkedin_image,
        "linkedin": "publish/linkedin_payload.json",
    }

    # Optional: render a video via Canva Autofill + Export.
    video_rel = _render_video(package, settings, storage, day)
    if video_rel:
        artifacts["canva_video"] = video_rel

    result = {
        "date": day,
        "mode": provider_mode,
        "providers": {
            "prompt": settings.prompt_provider,
            "supporting_images": settings.image_provider,
            "supporting_images_fallback": settings.image_fallback_provider,
            "linkedin_infographic": "template",
        },
        "topic": package.topic,
        "history": str(history_path),
        "artifacts": artifacts,
        "publishing": asdict(receipt),
        "next_stages": ["video_bot", "merge_bot", "youtube", "shorts", "instagram"],
    }
    storage.write_json(day, "run_manifest.json", result)
    return result


def _render_daily_dashboard_html(
    *,
    day: str,
    quota_widget: str,
    blocker_widget: str,
    quota_plan: dict[str, object],
    blocker_status_payload: dict[str, object],
    voice_widget: str,
    audio_status_path: str,
    voice_status_payload: dict[str, object],
) -> str:
    plan_status = quota_plan.get("status", "unknown")
    stop_before_failure = str(quota_plan.get("stop_before_failure", False)).lower()
    open_blockers = blocker_status_payload.get("open_count", 0)
    resolved_blockers = blocker_status_payload.get("resolved_count", 0)
    voice_provider = voice_status_payload.get("provider", "unknown")
    voice_engine = voice_status_payload.get("engine", "unknown")
    voice_audio_mode = "real audio" if voice_status_payload.get("has_real_audio") else "manifest only"
    voice_samples_count = voice_status_payload.get("sample_count", 0)
    voice_generated_at = voice_status_payload.get("generated_at", "unknown")
    voice_preview_excerpt = str(voice_status_payload.get("preview_excerpt") or "No preview recorded yet.")
    recent_resolved = blocker_status_payload.get("recent_resolved", [])
    resolved_rows = []
    for entry in recent_resolved[:3]:
        issue = escape(str(entry.get("issue") or ""))
        solution = escape(str(entry.get("solution") or ""))
        source = escape(str(entry.get("source_title") or ""))
        source_note = f" <span style='color:#94a3b8;'>[{source}]</span>" if source else ""
        resolved_rows.append(
            f"<li><strong>{issue}</strong>: {solution}{source_note}</li>"
        )
    resolved_html = "".join(resolved_rows) or "<li>No resolved lessons yet.</li>"
    return f"""<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Daily Agent Dashboard - {day}</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: linear-gradient(135deg, #020617, #0f172a 45%, #111827);
      color: #e2e8f0;
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      align-items: flex-end;
      margin-bottom: 18px;
    }}
    .title {{
      font-size: 32px;
      font-weight: 900;
      margin: 0;
    }}
    .subtitle {{
      margin-top: 8px;
      color: #94a3b8;
      max-width: 720px;
      line-height: 1.5;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .stat {{
      background: rgba(15, 23, 42, 0.82);
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 14px 16px;
    }}
    .stat-label {{
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #94a3b8;
    }}
    .stat-value {{
      margin-top: 6px;
      font-size: 20px;
      font-weight: 800;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      min-width: 0;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div>
        <h1 class="title">Daily Agent Dashboard</h1>
        <div class="subtitle">
          Gemini quota and blocker memory are shown together so we can stop before failure, reuse fixes, and keep the run moving.
        </div>
      </div>
      <div style="text-align:right;color:#94a3b8;">
        <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;">Run date</div>
        <div style="font-size:22px;font-weight:800;color:#e2e8f0;">{day}</div>
      </div>
    </section>
    <section class="stats">
      <div class="stat">
        <div class="stat-label">Gemini plan</div>
        <div class="stat-value">{plan_status}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Stop before failure</div>
        <div class="stat-value">{stop_before_failure}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Open blockers</div>
        <div class="stat-value">{open_blockers}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Resolved lessons</div>
        <div class="stat-value">{resolved_blockers}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Voice mode</div>
        <div class="stat-value">{escape(str(voice_provider))} · {escape(str(voice_engine))} · {escape(voice_audio_mode)}</div>
      </div>
    </section>
    <section style="margin-bottom:16px;background:rgba(15,23,42,.8);border:1px solid #334155;border-radius:18px;padding:16px;">
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Quick links</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:12px;">
        <a href="image_style_pack.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Image style pack
        </a>
        <a href="image_storyboard_prompts.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Storyboard prompts
        </a>
        <a href="thumbnail_prompt.txt" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Thumbnail prompt
        </a>
        <a href="voice_profile.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Voice profile
        </a>
        <a href="voice_normalization_preview.txt" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Voice preview
        </a>
        <a href="indian_voice_samples/voice_samples_manifest.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Indian voice samples
        </a>
        <a href="voice_status.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Voice status JSON
        </a>
        <a href="voice_status.html" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Voice status widget
        </a>
        <a href="audio_status.html" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Audio status front door
        </a>
        <a href="gemini_image_status.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Gemini quota JSON
        </a>
        <a href="blocker_journal_snapshot.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Latest blocker journal
        </a>
        <a href="blocker_suggestions.json" style="display:block;padding:12px 14px;border-radius:14px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;">
          Suggested fix list
        </a>
      </div>
    </section>
    <section class="grid">
      <div class="panel">{quota_widget}</div>
      <div class="panel">{blocker_widget}</div>
    </section>
    <section style="margin-top:16px;background:rgba(15,23,42,.8);border:1px solid #334155;border-radius:18px;padding:16px;">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
        <div>
          <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Voice footer</div>
          <div style="margin-top:6px;font-size:20px;font-weight:800;">
            {escape(str(voice_provider))} · {escape(str(voice_engine))}
          </div>
          <div style="margin-top:4px;color:#94a3b8;">{escape(voice_audio_mode)} · {escape(str(voice_samples_count))} sample(s)</div>
          <div style="margin-top:4px;color:#94a3b8;font-size:12px;">Last generated: {escape(str(voice_generated_at))}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:flex-end;">
          <span style="display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:{'#14532d' if voice_status_payload.get('has_real_audio') else '#7c2d12'};color:#fff;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;">
            {escape('Real audio' if voice_status_payload.get('has_real_audio') else 'Manifest only')}
          </span>
          <a href="voice_status.json" style="display:inline-flex;align-items:center;padding:8px 12px;border-radius:999px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;font-size:12px;font-weight:700;">
            Voice status JSON
          </a>
          <a href="voice_status.html" style="display:inline-flex;align-items:center;padding:8px 12px;border-radius:999px;background:#111827;border:1px solid #334155;color:#e2e8f0;text-decoration:none;font-size:12px;font-weight:700;">
            Voice widget
          </a>
        </div>
      </div>
      <div style="margin-top:14px;">{voice_widget}</div>
      <div style="margin-top:12px;padding:12px;border-radius:14px;background:#0f172a;border:1px solid #334155;color:#cbd5e1;">
        <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#94a3b8;font-weight:700;">Preview snippet</div>
        <div style="margin-top:6px;line-height:1.5;">{escape(voice_preview_excerpt)}</div>
      </div>
      <div style="margin-top:10px;font-size:12px;color:#94a3b8;">Audio front door: <a href="{escape(audio_status_path)}" style="color:#7dd3fc;text-decoration:none;">{escape(audio_status_path)}</a></div>
    </section>
    <section style="margin-top:16px;background:rgba(15,23,42,.8);border:1px solid #334155;border-radius:18px;padding:16px;">
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#fca5a5;font-weight:800;">Resolved lessons</div>
      <ul style="margin:12px 0 0;padding-left:18px;color:#cbd5e1;">{resolved_html}</ul>
    </section>
  </main>
</body>
</html>"""


def _render_video(
    package: ContentPackage,
    settings: Settings,
    storage: LocalDailyStorage,
    day: str,
) -> str | None:
    """Render a video via Canva if credentials and a brand template are configured."""
    if not (
        settings.canva_brand_template_id
        and settings.canva_client_id
        and settings.canva_client_secret
        and settings.canva_refresh_token
    ):
        return None
    from content_pipeline.bots.canva import render_canva_video

    return render_canva_video(package, settings, storage)
