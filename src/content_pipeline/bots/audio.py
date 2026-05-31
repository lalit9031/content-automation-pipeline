from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from html import escape
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings


HINDI_PRONUNCIATION_TEXT = (
    "गोकुल की सुनहरी सुबह में, मैया यशोदा ने पुकारा, कान्हा! "
    "मेरे प्यारे कान्हा, कहाँ छिपे हो? नन्हे कान्हा मुस्कुराते हुए बोले, "
    "मैया, मैं यहीं हूँ।"
)
HINDI_PRONUNCIATION_INSTRUCTIONS = (
    "शुद्ध, स्वाभाविक भारतीय हिंदी में बोलें। नामों का उच्चारण विशेष ध्यान से करें: "
    "गोकुल को गो-कुल, यशोदा को य-शो-दा, कान्हा को कान्-हा उच्चारित करें। "
    "अंग्रेज़ी प्रभाव वाला उच्चारण न करें। बच्चों की कृष्ण कहानी के लिए "
    "स्नेही, भावपूर्ण और स्पष्ट कथावाचक स्वर रखें।"
)
VOICE_VARIANTS = [
    ("sample_01_marin_warm.mp3", "marin", " स्वर कोमल, मातृवत और शांत रखें।"),
    ("sample_02_cedar_storyteller.mp3", "cedar", " स्वर भारतीय दादी-नानी की कहानी जैसा गर्म और सहज रखें।"),
    ("sample_03_coral_cheerful.mp3", "coral", " स्वर थोड़ा अधिक हँसमुख और बच्चों को आकर्षित करने वाला रखें।"),
]

FREE_INDIAN_EDGE_VOICE_VARIANTS = [
    ("sample_01_prabhat_neural.mp3", "en-IN-PrabhatNeural", "Warm Indian English male voice for professional narration."),
    ("sample_02_neerja_neural.mp3", "en-IN-NeerjaNeural", "Warm Indian English female voice for clear storytelling."),
    ("sample_03_swara_neural.mp3", "hi-IN-SwaraNeural", "Clear Hindi female voice for family-friendly narration."),
]


@dataclass(frozen=True)
class VoiceEngineProfile:
    name: str
    language: str
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    style: str = ""


def generate_hindi_voice_samples(
    settings: Settings,
    destination: Path,
    *,
    engine: str = "openai",
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    if engine == "edge":
        for filename, voice, additional_instruction in FREE_INDIAN_EDGE_VOICE_VARIANTS:
            output_path = destination / filename
            _run_async(
                _write_edge_voice_sample(
                    output_path,
                    voice=voice,
                    text=HINDI_PRONUNCIATION_TEXT,
                    instructions=HINDI_PRONUNCIATION_INSTRUCTIONS + " " + additional_instruction,
                )
            )
            files.append(output_path)
        return files
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required to generate narration samples.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
    client = OpenAI(api_key=settings.openai_api_key)
    for filename, voice, additional_instruction in VOICE_VARIANTS:
        result = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=HINDI_PRONUNCIATION_TEXT,
            instructions=HINDI_PRONUNCIATION_INSTRUCTIONS + additional_instruction,
        )
        output_path = destination / filename
        output_path.write_bytes(result.read())
        files.append(output_path)
    return files


def build_voice_profile(
    *,
    provider: str = "openai",
    language: str = "hi-IN",
    voice: str = "en-IN-PrabhatNeural",
) -> VoiceEngineProfile:
    if provider == "edge":
        return VoiceEngineProfile(name="edge-tts", language=language, voice=voice, rate="+0%", pitch="+0Hz")
    return VoiceEngineProfile(name="openai-tts", language=language, voice=voice, rate="+0%", pitch="+0Hz")


def normalize_voice_text(text: str) -> str:
    replacements = [
        (r"\bAI\b", "A.I."),
        (r"\bAPI\b", "A.P.I."),
        (r"\bPM\b", "P.M."),
        (r"\bJira\b", "Jee-ra"),
        (r"\bScrum\b", "Skrum"),
        (r"\bAgile\b", "A-jile"),
    ]
    normalized = text
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"([.!?])\s+", r"\1  ", normalized)
    return normalized.strip()


def _run_async(coro: object) -> None:
    try:
        asyncio.run(coro)  # type: ignore[arg-type]
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" not in str(exc):
            raise
        raise RuntimeError(
            "edge-tts voice generation cannot run inside an existing event loop. "
            "Call it from sync code or wrap it in your own async runner."
        ) from exc


async def _write_edge_voice_sample(
    output_path: Path,
    *,
    voice: str,
    text: str,
    instructions: str = "",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Install edge-tts to generate free Indian voice samples.") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        normalize_voice_text(text),
        voice,
        rate=rate,
        pitch=pitch,
    )
    if instructions:
        # Edge TTS does not accept custom instructions, so we preserve the note in the filename workflow.
        pass
    await communicate.save(str(output_path))


def generate_indian_voiceover(
    text: str,
    output_path: Path,
    *,
    voice: str = "en-IN-PrabhatNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Path:
    _run_async(_write_edge_voice_sample(output_path, voice=voice, text=text, rate=rate, pitch=pitch))
    return output_path


def voice_status(output_dir: Path, settings: Settings, *, day: str | None = None) -> dict[str, Any]:
    day = day or date.today().isoformat()
    daily_dir = output_dir / "daily" / day
    status_path = daily_dir / "voice_status.json"
    if status_path.exists():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            return loaded
    return _build_voice_status_payload(
        output_dir,
        settings,
        day=day,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_voice_status_html(status: dict[str, Any]) -> str:
    sample_rows = "".join(
        f"<li>{escape(str(path))}</li>" for path in status.get("sample_files", [])
    )
    if not sample_rows:
        sample_rows = "<li>No sample audio files generated yet.</li>"
    audio_mode = "real audio" if status.get("has_real_audio") else "manifest only"
    preview_excerpt = escape(str(status.get("preview_excerpt") or ""))
    generated_at = escape(str(status.get("generated_at") or "unknown"))
    return f"""<section style="background:#111827;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
    <div>
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Voice status</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px;">{escape(str(status.get('provider') or 'unknown'))} · {escape(str(status.get('voice') or 'unknown'))}</div>
      <div style="margin-top:4px;color:#94a3b8;font-size:12px;">Last generated: {generated_at}</div>
    </div>
    <div style="font-size:12px;color:#94a3b8;text-align:right;">
      <div>Engine: {escape(str(status.get('engine') or 'unknown'))}</div>
      <div>Mode: {escape(audio_mode)}</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:14px;">
    <div style="background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Profile</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(status.get('profile_path') or ''))}</div>
    </div>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Preview</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(status.get('preview_path') or ''))}</div>
    </div>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Samples</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(status.get('sample_count') or 0))}</div>
    </div>
  </div>
  <div style="margin-top:14px;">
    <div style="font-weight:700;color:#fca5a5;margin-bottom:6px;">Sample files</div>
    <ul style="margin:0;padding-left:18px;color:#cbd5e1;">{sample_rows}</ul>
  </div>
  <div style="margin-top:14px;background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
    <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Pronunciation preview</div>
    <div style="margin-top:6px;color:#e2e8f0;line-height:1.5;">{preview_excerpt or 'No preview recorded yet.'}</div>
  </div>
</section>"""


def write_voice_daily_artifacts(output_dir: Path, settings: Settings, *, day: str) -> dict[str, Path]:
    daily_dir = output_dir / "daily" / day
    daily_dir.mkdir(parents=True, exist_ok=True)

    preview_text = normalize_voice_text(
        "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm."
    )
    base_status = _build_voice_status_payload(
        output_dir,
        settings,
        day=day,
        generated_at=datetime.now(timezone.utc).isoformat(),
        preview_text=preview_text,
    )

    profile_path = daily_dir / "voice_profile.json"
    profile_path.write_text(
        json.dumps(base_status["voice_profile"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    preview_path = daily_dir / "voice_normalization_preview.txt"
    preview_path.write_text(preview_text + "\n", encoding="utf-8")

    samples_dir = daily_dir / "indian_voice_samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = samples_dir / "voice_samples_manifest.json"
    manifest_path.write_text(
        json.dumps(base_status["samples_manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readme_path = samples_dir / "README.md"
    readme_path.write_text(
        "# Indian Voice Samples\n\n"
        "This directory stores the daily voice manifest and, when enabled, the free Indian sample audio files.\n",
        encoding="utf-8",
    )

    written = {
        "voice_profile": profile_path,
        "voice_normalization_preview": preview_path,
        "voice_samples_manifest": manifest_path,
        "voice_samples_readme": readme_path,
    }

    if settings.voice_provider == "edge":
        generated = generate_hindi_voice_samples(settings, samples_dir, engine="edge")
        for path in generated:
            written[path.stem] = path

    status = _build_voice_status_payload(
        output_dir,
        settings,
        day=day,
        generated_at=datetime.now(timezone.utc).isoformat(),
        preview_text=preview_text,
    )
    status_path = daily_dir / "voice_status.json"
    status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    status_html_path = daily_dir / "voice_status.html"
    status_html_path.write_text(render_voice_status_html(status), encoding="utf-8")
    written["voice_status"] = status_path
    written["voice_status_html"] = status_html_path

    return written


def _build_voice_status_payload(
    output_dir: Path,
    settings: Settings,
    *,
    day: str,
    generated_at: str,
    preview_text: str | None = None,
) -> dict[str, Any]:
    profile = build_voice_profile(provider=settings.voice_provider, voice=settings.indian_tts_voice)
    daily_dir = output_dir / "daily" / day
    profile_path = daily_dir / "voice_profile.json"
    preview_path = daily_dir / "voice_normalization_preview.txt"
    samples_dir = daily_dir / "indian_voice_samples"
    manifest_path = samples_dir / "voice_samples_manifest.json"
    sample_files = sorted(samples_dir.glob("sample_*.mp3"))
    preview_text = preview_text or normalize_voice_text(
        "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm."
    )
    return {
        "provider": settings.voice_provider,
        "voice": settings.indian_tts_voice,
        "engine": "edge" if settings.voice_provider == "edge" else "manifest-only",
        "day": day,
        "generated_at": generated_at,
        "daily_dir": str(daily_dir),
        "profile_path": str(profile_path),
        "preview_path": str(preview_path),
        "preview_excerpt": preview_text,
        "samples_dir": str(samples_dir),
        "samples_manifest_path": str(manifest_path),
        "has_real_audio": bool(sample_files),
        "sample_count": len(sample_files),
        "sample_files": [str(path) for path in sample_files],
        "voice_profile": asdict(profile),
        "samples_manifest": {
            "provider": settings.voice_provider,
            "voice": settings.indian_tts_voice,
            "engine": "edge" if settings.voice_provider == "edge" else "manifest-only",
            "samples": [
                {
                    "filename": filename,
                    "voice": voice,
                    "description": description,
                }
                for filename, voice, description in FREE_INDIAN_EDGE_VOICE_VARIANTS
            ],
            "note": (
                "Real sample audio is generated when VOICE_PROVIDER=edge. "
                "Otherwise this directory keeps the manifest for the selected Indian voice path."
            ),
        },
    }


def audio_status(output_dir: Path, settings: Settings, *, day: str | None = None) -> dict[str, Any]:
    day = day or date.today().isoformat()
    daily_voice_status = voice_status(output_dir, settings, day=day)
    science_manifests = _load_audio_manifests(output_dir, "science_stories/*/audio/audio_manifest.json")
    pm_manifests = sorted(
        [
            *_load_audio_manifests(output_dir, "shorts/*/*/audio/reference/audio_manifest.json"),
            *_load_audio_manifests(output_dir, "youtubeVideo/*/*/audio/reference/audio_manifest.json"),
        ],
        key=lambda item: item.get("mtime", 0),
        reverse=True,
    )
    return {
        "day": day,
        "daily_voice_status": daily_voice_status,
        "science_audio": {
            "count": len(science_manifests),
            "latest": science_manifests[0] if science_manifests else None,
            "manifests": science_manifests,
        },
        "pm_audio": {
            "count": len(pm_manifests),
            "latest": pm_manifests[0] if pm_manifests else None,
            "manifests": pm_manifests,
        },
        "summary": {
            "has_daily_voice": bool(daily_voice_status),
            "has_science_audio": bool(science_manifests),
            "has_pm_audio": bool(pm_manifests),
        },
    }


def render_audio_status_html(status: dict[str, Any]) -> str:
    daily = status.get("daily_voice_status", {})
    science = status.get("science_audio", {})
    pm = status.get("pm_audio", {})
    return f"""<section style="background:#0f172a;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Audio status</div>
  <div style="margin-top:6px;font-size:20px;font-weight:800;">{escape(str(status.get('day') or 'unknown'))}</div>
  <div style="margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;">
    <div style="background:#111827;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Daily voice</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(daily.get('provider') or 'unknown'))} · {escape(str(daily.get('voice') or 'unknown'))}</div>
      <div style="margin-top:4px;color:#94a3b8;">{escape('real audio' if daily.get('has_real_audio') else 'manifest only')}</div>
      <div style="margin-top:4px;color:#94a3b8;">Last generated: {escape(str(daily.get('generated_at') or 'unknown'))}</div>
    </div>
    <div style="background:#111827;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Science audio</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(science.get('count') or 0))} manifest(s)</div>
      <div style="margin-top:4px;color:#94a3b8;">Latest: {escape(str((science.get('latest') or {}).get('path') or 'none'))}</div>
    </div>
    <div style="background:#111827;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">PM audio</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(pm.get('count') or 0))} manifest(s)</div>
      <div style="margin-top:4px;color:#94a3b8;">Latest: {escape(str((pm.get('latest') or {}).get('path') or 'none'))}</div>
    </div>
  </div>
</section>"""


def _load_audio_manifests(output_dir: Path, pattern: str) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in output_dir.glob(pattern):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload["path"] = str(path)
        payload["mtime"] = path.stat().st_mtime
        manifests.append(payload)
    manifests.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return manifests
