from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from content_pipeline.bots.audio import analyze_audio_file_for_repair
from content_pipeline.bots.blocker_agent import blocker_status
from content_pipeline.content_history import ContentHistory, normalize_topic
from content_pipeline.config import Settings


BRAINS_DIRNAME = "project_brain"
BRAINS_MEMORY_FILENAME = "project_brain_memory.json"


@dataclass(frozen=True)
class BrainScore:
    kind: str
    score: float
    verdict: str
    path: str = ""
    strengths: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrainMemoryEntry:
    generated_at: str
    latest_day: str
    overall_score: float
    summary: str
    root_causes: list[str]
    next_actions: list[str]
    content_ideas: list[dict[str, str]]
    learning_rules: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrainReport:
    generated_at: str
    latest_day: str
    overall_score: float
    verdict: str
    summary: str
    root_causes: list[str]
    next_actions: list[str]
    content_ideas: list[dict[str, str]]
    scores: list[BrainScore]
    blockers: dict[str, Any]
    history: dict[str, Any]
    web_signals: dict[str, Any]
    learning_rules: list[str]
    memory_path: str
    report_path: str
    markdown_path: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scores"] = [score.as_dict() for score in self.scores]
        return payload


def _brain_dir(output_dir: Path) -> Path:
    return output_dir / ".runtime" / BRAINS_DIRNAME


def _memory_path(output_dir: Path) -> Path:
    return _brain_dir(output_dir) / BRAINS_MEMORY_FILENAME


def _latest_daily_day(output_dir: Path) -> str | None:
    daily_root = output_dir / "daily"
    if not daily_root.exists():
        return None
    days = sorted(path.name for path in daily_root.iterdir() if path.is_dir())
    return days[-1] if days else None


def _latest_json_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_memory(output_dir: Path) -> dict[str, Any]:
    path = _memory_path(output_dir)
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("entries", [])
            return data
    except Exception:
        pass
    return {"version": 1, "entries": []}


def _save_memory(output_dir: Path, entry: BrainMemoryEntry) -> Path:
    path = _memory_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    memory = _load_memory(output_dir)
    entries = [item for item in memory.get("entries", []) if isinstance(item, dict)]
    entries.append(entry.as_dict())
    path.write_text(
        json.dumps({"version": 1, "entries": entries[-200:]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _audio_score_for_path(path: Path) -> BrainScore:
    if not path.exists():
        return BrainScore(
            kind="audio",
            path=str(path),
            score=0.0,
            verdict="missing",
            issues=["audio file missing"],
            recommendations=["Generate the audio artifact before scoring it."],
        )
    try:
        analysis = analyze_audio_file_for_repair(path)
        issues = [str(item) for item in analysis.get("issues", [])]
        score = 100.0
        score -= len(issues) * 10.0
        score -= max(0.0, abs(float(analysis.get("mean_dbfs", -18.0)) + 18.0) * 2.0)
        score -= max(0.0, float(analysis.get("dynamic_swing_db", 0.0)) - 24.0)
        score -= max(0.0, float(analysis.get("longest_silence_ms", 0)) - 900) / 80.0
        score = max(0.0, min(100.0, score))
        strengths = []
        if not issues:
            strengths.append("audio metrics are balanced")
        if analysis.get("longest_silence_ms", 0) <= 900:
            strengths.append("no long gap detected")
        if analysis.get("peak_dbfs", -99) <= -1.0:
            strengths.append("peak is safely below clipping")
        recommendations = []
        if any("too loud" in issue or "too hot" in issue for issue in issues):
            recommendations.append("Reduce gain and re-run the master pass.")
        if any("too quiet" in issue for issue in issues):
            recommendations.append("Lift the vocal/music balance a little.")
        if any("long gap" in issue for issue in issues):
            recommendations.append("Fill the silent gap or shorten the hold.")
        verdict = "excellent" if score >= 90 else "good" if score >= 75 else "watch" if score >= 55 else "needs_work"
        return BrainScore(
            kind="audio",
            path=str(path),
            score=round(score, 1),
            verdict=verdict,
            strengths=strengths,
            issues=issues,
            recommendations=recommendations,
            signals={
                "duration_ms": analysis.get("duration_ms"),
                "mean_dbfs": analysis.get("mean_dbfs"),
                "peak_dbfs": analysis.get("peak_dbfs"),
                "dynamic_swing_db": analysis.get("dynamic_swing_db"),
                "longest_silence_ms": analysis.get("longest_silence_ms"),
            },
        )
    except Exception as exc:
        return BrainScore(
            kind="audio",
            path=str(path),
            score=0.0,
            verdict="error",
            issues=[str(exc)],
            recommendations=["Rebuild the audio artifact and inspect the render log."],
        )


def _story_mix_score_for_path(path: Path) -> BrainScore:
    if not path.exists():
        return BrainScore(kind="audio_mix", path=str(path), score=0.0, verdict="missing")
    try:
        repair = analyze_audio_file_for_repair(path)
        issues = [str(item) for item in repair.get("issues", [])]
        score = 100.0 - len(issues) * 12.0
        score -= max(0.0, abs(float(repair.get("mean_dbfs", -18.0)) + 18.0) * 1.5)
        score = max(0.0, min(100.0, score))
        recommendations = []
        if issues:
            recommendations.append("Review the mix report and re-master the audio.")
        return BrainScore(
            kind="audio_mix",
            path=str(path),
            score=round(score, 1),
            verdict="excellent" if score >= 90 else "good" if score >= 75 else "watch" if score >= 55 else "needs_work",
            strengths=["mix file exists"],
            issues=issues,
            recommendations=recommendations,
            signals={"repair": repair},
        )
    except Exception as exc:
        return BrainScore(
            kind="audio_mix",
            path=str(path),
            score=0.0,
            verdict="error",
            issues=[str(exc)],
            recommendations=["Inspect the mix generation logs and recreate the file."],
        )


def _image_score_for_path(path: Path) -> BrainScore:
    if not path.exists():
        return BrainScore(
            kind="image",
            path=str(path),
            score=0.0,
            verdict="missing",
            issues=["image file missing"],
            recommendations=["Generate the image artifact before scoring it."],
        )
    suffix = path.suffix.lower()
    if suffix == ".svg":
        text = path.read_text(encoding="utf-8", errors="ignore")
        score = 70.0
        issues = []
        if "<text" in text.lower():
            score -= 20.0
            issues.append("SVG contains text nodes")
        if len(text) < 500:
            score -= 10.0
            issues.append("SVG is very small")
        return BrainScore(
            kind="image",
            path=str(path),
            score=max(0.0, min(100.0, score)),
            verdict="excellent" if score >= 90 else "good" if score >= 75 else "watch" if score >= 55 else "needs_work",
            strengths=["vector image available"],
            issues=issues,
            recommendations=["If this is a final image, check for any embedded text or layout noise."],
            signals={"file_size": path.stat().st_size, "format": "svg"},
        )
    try:
        from PIL import Image, ImageStat
    except Exception as exc:
        return BrainScore(
            kind="image",
            path=str(path),
            score=0.0,
            verdict="error",
            issues=[f"PIL unavailable: {exc}"],
            recommendations=["Install Pillow to enable image scoring."],
        )

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            width, height = img.size
            stat = ImageStat.Stat(img)
            brightness = mean(stat.mean)
            variance = mean(stat.var)
            aspect = width / max(height, 1)
            score = 100.0
            issues: list[str] = []
            strengths: list[str] = []
            if min(width, height) < 768:
                score -= 15.0
                issues.append("image is smaller than standard delivery size")
            if brightness < 35 or brightness > 220:
                score -= 12.0
                issues.append("image brightness is extreme")
            else:
                strengths.append("brightness is within a usable band")
            if variance < 120:
                score -= 18.0
                issues.append("image looks flat or low-contrast")
            else:
                strengths.append("image has healthy variation")
            if aspect < 1.2 or aspect > 2.0:
                score -= 10.0
                issues.append("aspect ratio is unusual for social video/image use")
            if path.stat().st_size < 20_000:
                score -= 8.0
                issues.append("file size is unusually small")
            score = max(0.0, min(100.0, score))
            recommendations = []
            if any("flat" in issue for issue in issues):
                recommendations.append("Add stronger foreground contrast or a clearer focal subject.")
            if any("brightness" in issue for issue in issues):
                recommendations.append("Rebalance exposure so the subject reads cleanly on mobile.")
            if any("smaller" in issue for issue in issues):
                recommendations.append("Render at a higher resolution for delivery.")
            return BrainScore(
                kind="image",
                path=str(path),
                score=round(score, 1),
                verdict="excellent" if score >= 90 else "good" if score >= 75 else "watch" if score >= 55 else "needs_work",
                strengths=strengths,
                issues=issues,
                recommendations=recommendations,
                signals={
                    "width": width,
                    "height": height,
                    "aspect_ratio": round(aspect, 3),
                    "brightness": round(brightness, 2),
                    "variance": round(variance, 2),
                    "file_size": path.stat().st_size,
                },
            )
    except Exception as exc:
        return BrainScore(
            kind="image",
            path=str(path),
            score=0.0,
            verdict="error",
            issues=[str(exc)],
            recommendations=["Re-render the image and inspect the render log."],
        )


def _metadata_score(report: dict[str, Any]) -> BrainScore:
    if not report:
        return BrainScore(
            kind="metadata",
            score=0.0,
            verdict="missing",
            issues=["no metadata audit report found"],
            recommendations=["Run the YouTube audit to score titles, descriptions, and tags."],
        )
    try:
        average_score = float(report.get("average_score", 0) or 0)
    except Exception:
        average_score = 0.0
    issues: list[str] = []
    recommendations: list[str] = []
    if average_score < 70:
        issues.append("channel metadata quality is below target")
        recommendations.append("Rewrite title and description for the weakest videos.")
    if report.get("optimizations"):
        low_quality_updates = [
            item for item in report.get("optimizations", []) if item.get("status") == "optimized"
        ]
        if low_quality_updates:
            recommendations.append("Apply the rewrite suggestions to the next batch and compare lift.")
    return BrainScore(
        kind="metadata",
        score=round(average_score, 1),
        verdict="excellent" if average_score >= 90 else "good" if average_score >= 75 else "watch" if average_score >= 55 else "needs_work",
        issues=issues,
        recommendations=recommendations,
        signals={
            "audited_channels": report.get("audited_channels"),
            "average_score": report.get("average_score"),
            "regions": report.get("region_code"),
        },
    )


def _novelty_score(history: ContentHistory, topic: str) -> BrainScore:
    normalized = normalize_topic(topic)
    if not normalized:
        return BrainScore(
            kind="novelty",
            score=0.0,
            verdict="missing",
            issues=["no topic available to assess novelty"],
            recommendations=["Provide a topic so novelty can be compared against history."],
        )
    recent = history.recent_topics(limit=30)
    repeated = [item for item in recent if item == normalized or normalized in item or item in normalized]
    score = 100.0 - len(repeated) * 25.0
    if repeated:
        score -= 10.0
    score = max(0.0, min(100.0, score))
    issues = []
    recommendations = []
    if repeated:
        issues.append("topic is repeating from recent history")
        recommendations.append("Change the emotional angle, setting, or hero subject before regenerating.")
    if score < 70:
        recommendations.append("Use a fresh perspective such as genre swap, location swap, or character-role swap.")
    return BrainScore(
        kind="novelty",
        score=round(score, 1),
        verdict="excellent" if score >= 90 else "good" if score >= 75 else "watch" if score >= 55 else "needs_work",
        issues=issues,
        recommendations=recommendations,
        signals={"recent_topics": recent[-10:], "repeated_hits": repeated},
    )


def _find_latest_artifacts(output_dir: Path, latest_day: str | None) -> dict[str, Path | None]:
    latest_day_root = output_dir / "daily" / latest_day if latest_day else None
    latest_audio_mix: Path | None = None
    latest_image: Path | None = None
    if latest_day_root and latest_day_root.exists():
        for pattern in ("**/*mix*.mp3", "**/*final*.mp3", "**/*master*.mp3", "**/*review*.mp3"):
            candidate = _latest_json_file(latest_day_root, pattern)
            if candidate:
                latest_audio_mix = candidate
                break
        for pattern in ("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp", "**/*.svg"):
            candidate = _latest_json_file(latest_day_root, pattern)
            if candidate:
                latest_image = candidate
                break
    if latest_image is None:
        brain_root = output_dir / ".runtime" / "image_previews"
        candidate = _latest_json_file(brain_root, "*.png") or _latest_json_file(brain_root, "*.svg")
        if candidate:
            latest_image = candidate
    if latest_audio_mix is None:
        mixed_root = output_dir / "story_mixes"
        candidate = _latest_json_file(mixed_root, "*.mp3")
        if candidate:
            latest_audio_mix = candidate
    return {
        "latest_day_root": latest_day_root,
        "latest_audio_mix": latest_audio_mix,
        "latest_image": latest_image,
    }


def _render_idea(topic: str, angle: str, reason: str) -> dict[str, str]:
    return {"topic": topic.strip(), "angle": angle.strip(), "reason": reason.strip()}


def _heuristic_next_actions(scores: list[BrainScore], history: ContentHistory, latest_day: str | None) -> tuple[list[str], list[dict[str, str]], list[str]]:
    actions: list[str] = []
    ideas: list[dict[str, str]] = []
    watchouts: list[str] = []
    audio = next((score for score in scores if score.kind in {"audio", "audio_mix"}), None)
    image = next((score for score in scores if score.kind == "image"), None)
    metadata = next((score for score in scores if score.kind == "metadata"), None)
    novelty = next((score for score in scores if score.kind == "novelty"), None)

    if audio and audio.score < 75:
        actions.append("Rebuild audio first and compare the repaired master against the previous attempt.")
        watchouts.append("Audio is the easiest source of user dissatisfaction because it affects the whole video.")
    if image and image.score < 75:
        actions.append("Regenerate the hero image with stronger subject separation and safer exposure.")
        watchouts.append("Low-contrast art will look weaker on mobile and Shorts.")
    if metadata and metadata.score < 75:
        actions.append("Rewrite the title, description, and tags around the strongest keyword angle.")
    if novelty and novelty.score < 80:
        actions.append("Switch the emotional angle, camera angle, or story framing before generating the next idea.")

    recent_topics = history.recent_topics(limit=8)
    repeated_topic = recent_topics[-1] if recent_topics else ""
    if repeated_topic:
        ideas.extend([
            _render_idea(repeated_topic, "same topic, different emotional angle", "Preserves audience intent but changes the feeling."),
            _render_idea(repeated_topic, "same topic, different setting", "Moves the story into a fresh place or season."),
            _render_idea(repeated_topic, "same topic, different character focus", "Keeps the core idea but changes the hero."),
        ])
    else:
        ideas.extend([
            _render_idea("fresh love song", "soft acoustic confession", "Warm and intimate, good when you want emotional sincerity."),
            _render_idea("fresh love song", "playful first-crush angle", "Keeps the theme but changes the energy."),
            _render_idea("fresh love song", "long-distance longing", "Adds distance, tension, and contrast."),
        ])

    if latest_day:
        actions.append(f"Use the latest day ({latest_day}) as the default baseline for comparison.")
    return actions, ideas, watchouts


def _brain_prompt(report_payload: dict[str, Any]) -> str:
    return (
        "You are the project brain for a content automation studio. Review the JSON payload and "
        "return only valid JSON with this schema:\n"
        "{\n"
        '  "summary": "short human summary",\n'
        '  "root_causes": ["cause 1", "cause 2"],\n'
        '  "next_actions": ["action 1", "action 2"],\n'
        '  "content_ideas": [{"topic": "topic", "angle": "angle", "reason": "reason"}],\n'
        '  "watchouts": ["risk 1", "risk 2"],\n'
        '  "learning_rules": ["rule 1", "rule 2"]\n'
        "}\n"
        "Prefer practical root causes, concise actions, and topic-diversification rules.\n\n"
        f"Payload:\n{json.dumps(report_payload, indent=2, ensure_ascii=False)}"
    )


def _unique_key_pool(values: list[str], fallback: str = "") -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    fallback = fallback.strip()
    if not ordered and fallback:
        ordered.append(fallback)
    return ordered


def _openai_pool(settings: Settings) -> list[str]:
    return _unique_key_pool(list(settings.openai_api_keys), settings.openai_api_key)


def _nvidia_pool(settings: Settings) -> list[str]:
    return _unique_key_pool(list(settings.nvidia_api_keys), settings.nvidia_api_key)


def _gemini_pool(settings: Settings) -> list[str]:
    return _unique_key_pool(list(settings.gemini_api_keys), settings.gemini_api_key)


def _local_brain_client(settings: Settings):
    from openai import OpenAI

    return OpenAI(api_key="local", base_url=settings.local_llm_url)


def _llm_brain_analysis(settings: Settings, report_payload: dict[str, Any]) -> dict[str, Any] | None:
    prompt = _brain_prompt(report_payload)
    providers = ["openai", "nvidia", "gemini", "local"]
    last_error: Exception | None = None
    for provider in providers:
        try:
            if provider == "openai":
                keys = _openai_pool(settings)
                if not keys:
                    continue
                for key in keys:
                    from openai import OpenAI

                    client = OpenAI(api_key=key)
                    response = client.responses.create(
                        model=settings.openai_model,
                        instructions="Output only valid JSON.",
                        input=prompt,
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "project_brain_report",
                                "strict": True,
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "summary",
                                        "root_causes",
                                        "next_actions",
                                        "content_ideas",
                                        "watchouts",
                                        "learning_rules",
                                    ],
                                    "properties": {
                                        "summary": {"type": "string"},
                                        "root_causes": {"type": "array", "items": {"type": "string"}},
                                        "next_actions": {"type": "array", "items": {"type": "string"}},
                                        "content_ideas": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["topic", "angle", "reason"],
                                                "properties": {
                                                    "topic": {"type": "string"},
                                                    "angle": {"type": "string"},
                                                    "reason": {"type": "string"},
                                                },
                                            },
                                        },
                                        "watchouts": {"type": "array", "items": {"type": "string"}},
                                        "learning_rules": {"type": "array", "items": {"type": "string"}},
                                    },
                                },
                            }
                        },
                    )
                    return json.loads(response.output_text)
            elif provider == "nvidia":
                keys = _nvidia_pool(settings)
                if not keys:
                    continue
                for key in keys:
                    from openai import OpenAI

                    client = OpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")
                    completion = client.chat.completions.create(
                        model=os.getenv("NVIDIA_TEXT_MODEL", settings.nvidia_nim_model),
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        top_p=0.95,
                        max_tokens=2048,
                        stream=False,
                        extra_body={"thinking_budget": -1},
                    )
                    return _safe_json_from_text(str(completion.choices[0].message.content or ""))
            elif provider == "gemini":
                keys = _gemini_pool(settings)
                if not keys:
                    continue
                from google import genai
                from google.genai import types

                for key in keys:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2,
                        ),
                    )
                    return _safe_json_from_text(response.text or "")
            elif provider == "local":
                client = _local_brain_client(settings)
                completion = client.chat.completions.create(
                    model=settings.local_llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    top_p=0.95,
                    max_tokens=2048,
                    stream=False,
                    response_format={"type": "json_object"},
                )
                return _safe_json_from_text(str(completion.choices[0].message.content or ""))
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        return None
    return None


def _safe_json_from_text(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def build_project_brain_report(
    settings: Settings,
    *,
    refresh_web: bool = False,
    trend_region: str = "IN",
    output_dir: Path | None = None,
) -> BrainReport:
    output_dir = output_dir or settings.output_dir
    latest_day = _latest_daily_day(output_dir)
    history = ContentHistory.load(output_dir)
    blockers = blocker_status(output_dir)
    latest_audit = _load_json(_latest_json_file(output_dir / "youtube_audits", "youtube_audit_*.json"))
    if refresh_web:
        try:
            from content_pipeline.bots.youtube_audit import audit_youtube_channels

            latest_audit = audit_youtube_channels(
                settings,
                output_dir,
                region_code=trend_region,
                max_videos=15,
                related_topic_limit=3,
                trending_limit=15,
            )
        except Exception:
            pass

    artifacts = _find_latest_artifacts(output_dir, latest_day)
    scores: list[BrainScore] = []
    audio_mix_score = _story_mix_score_for_path(artifacts["latest_audio_mix"]) if artifacts["latest_audio_mix"] else None
    if audio_mix_score:
        scores.append(audio_mix_score)
    if artifacts["latest_audio_mix"] is not None:
        scores.append(_audio_score_for_path(artifacts["latest_audio_mix"]))
    if artifacts["latest_image"] is not None:
        scores.append(_image_score_for_path(artifacts["latest_image"]))
    scores.append(_metadata_score(latest_audit))

    topic_for_novelty = ""
    if history.entries:
        topic_for_novelty = history.entries[-1].topic
    scores.append(_novelty_score(history, topic_for_novelty))

    numeric_scores = [score.score for score in scores if score.score > 0]
    overall_score = round(mean(numeric_scores), 1) if numeric_scores else 0.0
    verdict = "excellent" if overall_score >= 90 else "good" if overall_score >= 75 else "watch" if overall_score >= 55 else "needs_work"

    heuristic_actions, heuristic_ideas, heuristic_watchouts = _heuristic_next_actions(scores, history, latest_day)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_day": latest_day,
        "overall_score": overall_score,
        "verdict": verdict,
        "scores": [score.as_dict() for score in scores],
        "blockers": blockers,
        "history": {
            "total_entries": len(history.entries),
            "recent_topics": history.recent_topics(limit=12),
        },
        "web_signals": {
            "latest_audit": latest_audit,
            "trend_region": trend_region,
        },
        "heuristic_actions": heuristic_actions,
        "heuristic_ideas": heuristic_ideas,
        "heuristic_watchouts": heuristic_watchouts,
    }
    llm_review = _llm_brain_analysis(settings, payload)
    summary = ""
    root_causes: list[str] = []
    next_actions: list[str] = heuristic_actions[:]
    content_ideas: list[dict[str, str]] = heuristic_ideas[:]
    watchouts: list[str] = heuristic_watchouts[:]
    learning_rules: list[str] = []
    if llm_review:
        summary = str(llm_review.get("summary", "")).strip()
        root_causes = [str(item).strip() for item in llm_review.get("root_causes", []) if str(item).strip()]
        next_actions = [
            str(item).strip() for item in llm_review.get("next_actions", []) if str(item).strip()
        ] or next_actions
        content_ideas = [
            {
                "topic": str(item.get("topic", "")).strip(),
                "angle": str(item.get("angle", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
            }
            for item in llm_review.get("content_ideas", [])
            if isinstance(item, dict)
        ] or content_ideas
        watchouts = [str(item).strip() for item in llm_review.get("watchouts", []) if str(item).strip()] or watchouts
        learning_rules = [
            str(item).strip() for item in llm_review.get("learning_rules", []) if str(item).strip()
        ]

    if not summary:
        summary = (
            f"Overall score {overall_score}/100. The strongest signal is "
            f"{max(scores, key=lambda item: item.score).kind if scores else 'none'}, "
            f"and the lowest signal needs attention first."
        )
    if not root_causes:
        root_causes = [
            item
            for item in (
                "artifact repetition from recent history" if scores and any(score.kind == "novelty" and score.score < 80 for score in scores) else "",
                "audio consistency needs attention" if any(score.kind in {"audio", "audio_mix"} and score.score < 75 for score in scores) else "",
                "metadata needs stronger click-through framing" if any(score.kind == "metadata" and score.score < 75 for score in scores) else "",
            )
            if item
        ]
    if not learning_rules:
        learning_rules = [
            "Never regenerate the same topic without changing the emotional angle or the hero subject.",
            "If an artifact scores below 75, fix that artifact before generating the next layer.",
            "Capture successful topics, hooks, and structure choices in history so the next run can diversify automatically.",
        ]

    report = BrainReport(
        generated_at=payload["generated_at"],
        latest_day=latest_day or "",
        overall_score=overall_score,
        verdict=verdict,
        summary=summary,
        root_causes=root_causes[:6],
        next_actions=next_actions[:8],
        content_ideas=content_ideas[:8],
        scores=scores,
        blockers=blockers,
        history=payload["history"],
        web_signals=payload["web_signals"],
        learning_rules=learning_rules,
        memory_path="",
        report_path="",
        markdown_path="",
    )
    brain_dir = _brain_dir(output_dir)
    brain_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = brain_dir / f"project_brain_{timestamp}.json"
    md_path = brain_dir / f"project_brain_{timestamp}.md"
    memory_path = _save_memory(
        output_dir,
        BrainMemoryEntry(
            generated_at=report.generated_at,
            latest_day=report.latest_day,
            overall_score=report.overall_score,
            summary=report.summary,
            root_causes=report.root_causes,
            next_actions=report.next_actions,
            content_ideas=report.content_ideas,
            learning_rules=learning_rules,
        ),
    )
    final_report = replace(
        report,
        memory_path=str(memory_path),
        report_path=str(json_path),
        markdown_path=str(md_path),
    )
    json_path.write_text(json.dumps(final_report.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_project_brain_markdown(final_report, learning_rules=learning_rules), encoding="utf-8")
    return final_report


def _report_from_payload(payload: dict[str, Any]) -> BrainReport | None:
    try:
        scores = [
            BrainScore(
                kind=str(item.get("kind", "")),
                score=float(item.get("score", 0.0) or 0.0),
                verdict=str(item.get("verdict", "")),
                path=str(item.get("path", "")),
                strengths=[str(value) for value in item.get("strengths", []) if str(value).strip()],
                issues=[str(value) for value in item.get("issues", []) if str(value).strip()],
                recommendations=[str(value) for value in item.get("recommendations", []) if str(value).strip()],
                signals=item.get("signals", {}) if isinstance(item.get("signals", {}), dict) else {},
            )
            for item in payload.get("scores", [])
            if isinstance(item, dict)
        ]
        return BrainReport(
            generated_at=str(payload.get("generated_at", "")),
            latest_day=str(payload.get("latest_day", "")),
            overall_score=float(payload.get("overall_score", 0.0) or 0.0),
            verdict=str(payload.get("verdict", "")),
            summary=str(payload.get("summary", "")),
            root_causes=[str(value) for value in payload.get("root_causes", []) if str(value).strip()],
            next_actions=[str(value) for value in payload.get("next_actions", []) if str(value).strip()],
            content_ideas=[
                {
                    "topic": str(item.get("topic", "")).strip(),
                    "angle": str(item.get("angle", "")).strip(),
                    "reason": str(item.get("reason", "")).strip(),
                }
                for item in payload.get("content_ideas", [])
                if isinstance(item, dict)
            ],
            scores=scores,
            blockers=payload.get("blockers", {}) if isinstance(payload.get("blockers", {}), dict) else {},
            history=payload.get("history", {}) if isinstance(payload.get("history", {}), dict) else {},
            web_signals=payload.get("web_signals", {}) if isinstance(payload.get("web_signals", {}), dict) else {},
            learning_rules=[str(value) for value in payload.get("learning_rules", []) if str(value).strip()],
            memory_path=str(payload.get("memory_path", "")),
            report_path=str(payload.get("report_path", "")),
            markdown_path=str(payload.get("markdown_path", "")),
        )
    except Exception:
        return None


def load_latest_project_brain_report(output_dir: Path) -> BrainReport | None:
    brain_dir = _brain_dir(output_dir)
    latest = _latest_json_file(brain_dir, "project_brain_*.json")
    payload = _load_json(latest)
    if not payload:
        return None
    report = _report_from_payload(payload)
    if report is None:
        return None
    md_path = latest.with_suffix(".md") if latest else Path(report.markdown_path or "")
    memory_path = _memory_path(output_dir)
    return replace(
        report,
        report_path=str(latest) if latest else report.report_path,
        markdown_path=str(md_path) if md_path else report.markdown_path,
        memory_path=str(memory_path),
    )


def render_project_brain_markdown(report: BrainReport, learning_rules: list[str] | None = None) -> str:
    lines: list[str] = []
    lines.append("# Project Brain")
    lines.append("")
    lines.append(f"- Generated at: `{report.generated_at}`")
    lines.append(f"- Latest day: `{report.latest_day or 'none yet'}`")
    lines.append(f"- Overall score: `{report.overall_score}`")
    lines.append(f"- Verdict: `{report.verdict}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(report.summary)
    lines.append("")
    lines.append("## Scores")
    for score in report.scores:
        lines.append(f"- **{score.kind}**: `{score.score}` ({score.verdict})")
        if score.issues:
            lines.append(f"  - Issues: {', '.join(score.issues)}")
        if score.recommendations:
            lines.append(f"  - Recommendations: {', '.join(score.recommendations)}")
    lines.append("")
    if report.root_causes:
        lines.append("## Root Causes")
        for item in report.root_causes:
            lines.append(f"- {item}")
        lines.append("")
    if report.next_actions:
        lines.append("## Next Actions")
        for item in report.next_actions:
            lines.append(f"- {item}")
        lines.append("")
    if report.content_ideas:
        lines.append("## Idea Backlog")
        for item in report.content_ideas:
            lines.append(f"- {item.get('topic', '')}: {item.get('angle', '')} — {item.get('reason', '')}")
        lines.append("")
    if report.blockers.get("open_count") or report.blockers.get("resolved_count"):
        lines.append("## Blockers")
        lines.append(f"- Open: `{report.blockers.get('open_count', 0)}`")
        lines.append(f"- Resolved: `{report.blockers.get('resolved_count', 0)}`")
        lines.append("")
    if report.web_signals.get("latest_audit"):
        audit = report.web_signals["latest_audit"]
        lines.append("## Web Signals")
        lines.append(f"- Audited channels: `{audit.get('audited_channels', 0)}`")
        lines.append(f"- Average channel score: `{audit.get('average_score', 0)}`")
        lines.append("")
    if learning_rules is None:
        learning_rules = report.learning_rules
    if learning_rules:
        lines.append("## Learning Rules")
        for item in learning_rules:
            lines.append(f"- {item}")
        lines.append("")
    lines.append(f"- Memory: `{report.memory_path}`")
    lines.append(f"- JSON: `{report.report_path}`")
    lines.append(f"- Markdown: `{report.markdown_path}`")
    return "\n".join(lines).strip() + "\n"


def run_project_brain_daemon(
    settings: Settings,
    *,
    refresh_web: bool = False,
    trend_region: str = "IN",
    interval_minutes: int = 360,
) -> None:
    import time

    while True:
        report = build_project_brain_report(
            settings,
            refresh_web=refresh_web,
            trend_region=trend_region,
        )
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        time.sleep(max(5, interval_minutes) * 60)
