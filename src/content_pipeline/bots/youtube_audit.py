from __future__ import annotations

import os
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from content_pipeline.bots.telegram import send_telegram_document, send_telegram_message
from content_pipeline.bots.youtube import YOUTUBE_UPLOAD_SCOPE, get_my_video_details, list_my_uploaded_videos
from content_pipeline.bots.youtube import update_youtube_video_metadata
from content_pipeline.config import Settings


CHANNEL_PROFILES: tuple[tuple[str, str], ...] = (
    ("TechWithLalit", "techwithlalit"),
    ("Studio_MagicTales", "magictales"),
    ("LittleBubbles TV", "littlebubbles"),
)

DEFAULT_REGION_CODE = "IN"
VIEW_THRESHOLD = 500
DAYS_THRESHOLD = 30
SCHEDULED_STATUSES = {"private", "unlisted"}

TOPIC_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "and",
    "are",
    "best",
    "build",
    "channel",
    "children",
    "child",
    "code",
    "coding",
    "create",
    "daily",
    "easy",
    "episode",
    "explainer",
    "explore",
    "family",
    "featuring",
    "for",
    "from",
    "fun",
    "guide",
    "how",
    "in",
    "into",
    "kids",
    "learn",
    "little",
    "long",
    "make",
    "music",
    "new",
    "nursery",
    "official",
    "of",
    "on",
    "one",
    "out",
    "part",
    "play",
    "popular",
    "rhyme",
    "song",
    "songs",
    "story",
    "the",
    "this",
    "to",
    "top",
    "trending",
    "video",
    "videos",
    "with",
    "you",
    "your",
    "short",
    "shorts",
    "full",
    "high",
    "low",
    "mid",
    "best",
    "simple",
    "quick",
    "easy",
    "explore",
    "explored",
    "exploring",
}


@dataclass(frozen=True)
class YouTubeChannelProfile:
    channel_name: str
    channel_key: str
    token_file: Path
    secrets_file: Path

    @property
    def available(self) -> bool:
        return self.token_file.exists() and self.secrets_file.exists()


def resolve_youtube_channel_profiles(project_dir: Path) -> list[YouTubeChannelProfile]:
    profiles: list[YouTubeChannelProfile] = []
    for channel_name, channel_key in CHANNEL_PROFILES:
        profiles.append(
            YouTubeChannelProfile(
                channel_name=channel_name,
                channel_key=channel_key,
                token_file=project_dir / ".secrets" / f"youtube_token_{channel_key}.json",
                secrets_file=project_dir / "scripts" / f"client_secret_{channel_key}.json",
            )
        )
    return profiles


def _load_token_scopes(token_file: Path) -> list[str] | None:
    try:
        data = json.loads(token_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    scopes = data.get("scopes")
    if isinstance(scopes, list) and scopes:
        return [str(scope) for scope in scopes]
    return None


def _build_youtube_service(settings: Settings):
    if not settings.youtube_token_file:
        raise ValueError("YOUTUBE_TOKEN_FILE is required for YouTube diagnostics.")
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install YouTube dependencies with: pip install -e '.[youtube]'") from exc

    scopes = _load_token_scopes(Path(settings.youtube_token_file)) or list(YOUTUBE_UPLOAD_SCOPE)
    credentials = Credentials.from_authorized_user_file(settings.youtube_token_file, scopes)
    return build("youtube", "v3", credentials=credentials)


def _first_gemini_key(settings: Settings) -> str:
    if settings.gemini_api_keys:
        for key in settings.gemini_api_keys:
            if key.strip():
                return key.strip()
    return settings.gemini_api_key.strip()


def _build_gemini_client(settings: Settings):
    key = _first_gemini_key(settings)
    if not key:
        raise ValueError("GEMINI_API_KEY is required for AI metadata rewrite suggestions.")
    from google import genai

    return genai.Client(api_key=key)


def _build_openai_client(api_key: str):
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError("openai is required for metadata rewrites.") from exc
    return OpenAI(api_key=api_key)


def _generate_metadata_with_nvidia(
    settings: Settings,
    *,
    prompt: str,
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError("openai is required for NVIDIA-compatible metadata rewrites.") from exc

    preferred_model = os.getenv("NVIDIA_TEXT_MODEL", "bytedance/seed-oss-36b-instruct").strip()
    models_to_try = [preferred_model]
    if settings.nvidia_nim_model and settings.nvidia_nim_model not in models_to_try:
        models_to_try.append(settings.nvidia_nim_model)

    keys = [key.strip() for key in settings.nvidia_api_keys if key.strip()]
    if not keys:
        fallback = os.getenv("NVIDIA_API_KEY", "").strip()
        if fallback:
            keys.append(fallback)
    if not keys:
        raise ValueError("NVIDIA_API_KEY is required for NVIDIA text generation.")

    last_error: Exception | None = None
    for api_key in keys:
        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
        for model in models_to_try:
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=1.1,
                    top_p=0.95,
                    max_tokens=4096,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream=False,
                    extra_body={"thinking_budget": -1},
                )
                message = completion.choices[0].message
                content = str(getattr(message, "content", "") or "").strip()
                payload = _extract_json_object(content)
                payload["_provider"] = "nvidia"
                payload["_model"] = model
                reasoning = getattr(message, "reasoning_content", None)
                if reasoning:
                    payload["_reasoning"] = str(reasoning)
                return payload
            except Exception as exc:
                last_error = exc
                continue
    if last_error:
        raise last_error
    raise RuntimeError("NVIDIA metadata generation failed.")


def _generate_metadata_with_gemini(
    settings: Settings,
    *,
    prompt: str,
) -> dict[str, Any]:
    client = _build_gemini_client(settings)
    try:
        from google.genai import types
    except Exception as exc:
        raise RuntimeError("google-genai is required for metadata rewrites.") from exc
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )
    payload = _extract_json_object(response.text or "")
    payload["_provider"] = "gemini"
    payload["_model"] = "gemini-2.5-flash"
    return payload


def _generate_metadata_with_openai(
    settings: Settings,
    *,
    prompt: str,
) -> dict[str, Any]:
    keys = [key.strip() for key in settings.openai_api_keys if key.strip()]
    if not keys and settings.openai_api_key.strip():
        keys = [settings.openai_api_key.strip()]
    if not keys:
        raise ValueError("OPENAI_API_KEY is required for OpenAI metadata rewrites.")
    last_error: Exception | None = None
    for api_key in keys:
        client = _build_openai_client(api_key)
        try:
            completion = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                top_p=0.95,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            content = str(completion.choices[0].message.content or "").strip()
            payload = _extract_json_object(content)
            payload["_provider"] = "openai"
            payload["_model"] = settings.openai_model
            return payload
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI metadata generation failed.")


def _generate_metadata_with_local_llm(
    settings: Settings,
    *,
    prompt: str,
) -> dict[str, Any]:
    url = f"{settings.local_llm_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.local_llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(url, json=payload, timeout=45)
    if response.status_code != 200:
        raise RuntimeError(f"Local LLM returned status {response.status_code}: {response.text}")
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    parsed_data = json.loads(content)
    if not isinstance(parsed_data, dict):
        raise ValueError("Local LLM response did not contain valid JSON.")
    parsed_data["_provider"] = "local"
    parsed_data["_model"] = settings.local_llm_model
    return parsed_data


def _rewrite_provider_order(rewrite_provider: str) -> list[str]:
    provider = (rewrite_provider or "auto").strip().lower().replace("_", " ").replace("-", " ")
    provider = " ".join(provider.split())
    if provider in {"nvidia", "gemini", "openai", "local", "local llm", "local-llm"}:
        return ["local"] if provider.startswith("local") else [provider]
    return ["nvidia", "gemini", "openai", "local"]


def _generate_metadata_payload(
    settings: Settings,
    *,
    prompt: str,
    rewrite_provider: str = "auto",
) -> dict[str, Any]:
    last_error: Exception | None = None
    for provider in _rewrite_provider_order(rewrite_provider):
        try:
            if provider == "nvidia":
                return _generate_metadata_with_nvidia(settings, prompt=prompt)
            if provider == "gemini":
                return _generate_metadata_with_gemini(settings, prompt=prompt)
            if provider == "openai":
                return _generate_metadata_with_openai(settings, prompt=prompt)
            if provider == "local":
                return _generate_metadata_with_local_llm(settings, prompt=prompt)
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("Metadata generation failed.")


def _parse_iso8601_duration(duration: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _clean_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
    cleaned = [token for token in tokens if len(token) > 2 and token not in TOPIC_STOPWORDS]
    return cleaned


def _phrase_from_title(title: str, max_words: int = 5) -> str:
    tokens = _clean_tokens(title)
    if not tokens:
        return ""
    return " ".join(tokens[:max_words])


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidate = raw[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Gemini response did not contain valid JSON.")


def _to_utc_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except Exception:
        return None


def _video_age_days(published_at: str) -> int:
    dt = _to_utc_date(published_at)
    if dt is None:
        return 0
    return max((datetime.now(timezone.utc) - dt).days, 0)


def _fetch_channel_profile_data(profile_settings: Settings) -> dict[str, Any]:
    youtube = _build_youtube_service(profile_settings)
    response = youtube.channels().list(
        part="snippet,statistics,contentDetails,brandingSettings",
        mine=True,
    ).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel returned for the supplied token.")
    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    content_details = item.get("contentDetails", {})
    branding = item.get("brandingSettings", {}).get("channel", {})
    uploads_playlist = content_details.get("relatedPlaylists", {}).get("uploads", "")
    return {
        "channel_id": str(item.get("id", "")),
        "title": str(snippet.get("title", "")),
        "description": str(snippet.get("description", "")),
        "custom_url": str(snippet.get("customUrl", "")),
        "keywords": str(branding.get("keywords", "")),
        "subscriber_count": _safe_int(statistics.get("subscriberCount")),
        "view_count": _safe_int(statistics.get("viewCount")),
        "video_count": _safe_int(statistics.get("videoCount")),
        "hidden_subscriber_count": bool(statistics.get("hiddenSubscriberCount", False)),
        "uploads_playlist_id": uploads_playlist,
    }


def _fetch_recent_videos(profile_settings: Settings, max_videos: int) -> list[dict[str, Any]]:
    uploaded = list_my_uploaded_videos(profile_settings, max_results=max_videos)
    video_ids = [item["video_id"] for item in uploaded if item.get("video_id")]
    details = {item["video_id"]: item for item in get_my_video_details(profile_settings, video_ids)}
    videos: list[dict[str, Any]] = []
    for item in uploaded:
        video_id = item.get("video_id", "")
        detail = details.get(video_id, {})
        duration_seconds = _parse_iso8601_duration(str(detail.get("duration", "")))
        videos.append(
            {
                "video_id": video_id,
                "title": str(detail.get("title", item.get("title", ""))),
                "description": str(detail.get("description", "")),
                "published_at": str(detail.get("published_at", item.get("published_at", ""))),
                "publish_at": str(detail.get("publish_at", "")),
                "privacy_status": str(detail.get("privacy_status", "")),
                "duration_seconds": duration_seconds,
                "view_count": _safe_int(detail.get("view_count")),
                "like_count": _safe_int(detail.get("like_count")),
                "comment_count": _safe_int(detail.get("comment_count")),
                "tags": list(detail.get("tags", []) or []),
                "age_days": _video_age_days(str(detail.get("published_at", item.get("published_at", "")))),
            }
        )
    return videos


def _fetch_trending_videos(profile_settings: Settings, region_code: str, limit: int) -> list[dict[str, Any]]:
    youtube = _build_youtube_service(profile_settings)
    response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        chart="mostPopular",
        regionCode=region_code,
        maxResults=min(max(limit, 1), 25),
    ).execute()
    results: list[dict[str, Any]] = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        results.append(
            {
                "video_id": str(item.get("id", "")),
                "title": str(snippet.get("title", "")),
                "channel_title": str(snippet.get("channelTitle", "")),
                "published_at": str(snippet.get("publishedAt", "")),
                "view_count": _safe_int(statistics.get("viewCount")),
                "like_count": _safe_int(statistics.get("likeCount")),
                "comment_count": _safe_int(statistics.get("commentCount")),
                "duration_seconds": _parse_iso8601_duration(str(content_details.get("duration", ""))),
            }
        )
    return results


def _fetch_related_popular_videos(
    profile_settings: Settings,
    queries: list[str],
    region_code: str,
    per_query_limit: int = 5,
) -> list[dict[str, Any]]:
    if not queries:
        return []
    youtube = _build_youtube_service(profile_settings)
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for query in queries:
        if not query.strip():
            continue
        search_response = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            order="viewCount",
            regionCode=region_code,
            maxResults=min(max(per_query_limit, 1), 10),
        ).execute()
        video_ids = []
        for item in search_response.get("items", []):
            video_id = str(item.get("id", {}).get("videoId", ""))
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                video_ids.append(video_id)
        if not video_ids:
            continue
        details = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
            maxResults=len(video_ids),
        ).execute()
        for item in details.get("items", []):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content_details = item.get("contentDetails", {})
            collected.append(
                {
                    "query": query,
                    "video_id": str(item.get("id", "")),
                    "title": str(snippet.get("title", "")),
                    "channel_title": str(snippet.get("channelTitle", "")),
                    "published_at": str(snippet.get("publishedAt", "")),
                    "view_count": _safe_int(statistics.get("viewCount")),
                    "like_count": _safe_int(statistics.get("likeCount")),
                    "comment_count": _safe_int(statistics.get("commentCount")),
                    "duration_seconds": _parse_iso8601_duration(str(content_details.get("duration", ""))),
                }
            )
    collected.sort(key=lambda item: item.get("view_count", 0), reverse=True)
    return collected


def _recent_topic_queries(recent_videos: list[dict[str, Any]], limit: int) -> list[str]:
    ordered = sorted(recent_videos, key=lambda item: item.get("view_count", 0), reverse=True)
    queries: list[str] = []
    for video in ordered:
        phrase = _phrase_from_title(str(video.get("title", "")), max_words=5)
        if len(phrase.split()) < 2:
            continue
        if phrase not in queries:
            queries.append(phrase)
        if len(queries) >= limit:
            break
    return queries


def _score_channel(
    profile: dict[str, Any],
    recent_videos: list[dict[str, Any]],
    trending_videos: list[dict[str, Any]],
    related_videos: list[dict[str, Any]],
) -> tuple[int, list[str], list[str], list[str]]:
    score = 100
    warnings: list[str] = []
    strengths: list[str] = []
    recommendations: list[str] = []

    if profile.get("hidden_subscriber_count"):
        warnings.append("Subscriber count is hidden, so the audit cannot compare growth publicly.")
    else:
        strengths.append(f"Public subscriber count is visible: {profile.get('subscriber_count', 0):,}.")

    if not recent_videos:
        score -= 35
        recommendations.append("No recent uploads were found. Publish a fresh batch and keep the channel active.")
        return max(score, 0), strengths, warnings, recommendations

    avg_title_len = sum(len(v["title"]) for v in recent_videos) / len(recent_videos)
    avg_desc_len = sum(len(v["description"]) for v in recent_videos) / len(recent_videos)
    avg_views = sum(v["view_count"] for v in recent_videos) / len(recent_videos)
    shorts_count = sum(1 for v in recent_videos if v.get("duration_seconds", 0) and v["duration_seconds"] <= 75)
    shorts_ratio = shorts_count / len(recent_videos)
    latest_upload = max((_to_utc_date(v.get("published_at", "")) for v in recent_videos), default=None)
    oldest_upload = min((_to_utc_date(v.get("published_at", "")) for v in recent_videos), default=None)

    if avg_title_len < 28:
        score -= 8
        recommendations.append("Make titles a little more descriptive; aim for 35-60 characters.")
    elif avg_title_len > 72:
        score -= 10
        recommendations.append("Shorten titles. Long titles often bury the hook before the click.")
    else:
        strengths.append("Title length is in a healthy range for search and suggested traffic.")

    if avg_desc_len < 120:
        score -= 8
        recommendations.append("Expand descriptions with a clear promise, 2-3 keywords, and a CTA.")
    else:
        strengths.append("Descriptions are giving YouTube more context to work with.")

    if latest_upload is not None and oldest_upload is not None:
        spread = max((latest_upload - oldest_upload).days, 0)
        if spread >= 30 and len(recent_videos) < 6:
            score -= 10
            recommendations.append("Upload more consistently. The channel looks quiet relative to its recent history.")

    if shorts_ratio < 0.5:
        score -= 6
        recommendations.append("Increase Shorts share if you want faster discovery and more browse traffic.")
    else:
        strengths.append("Short-form output is already part of the mix.")

    if avg_views < 1000 and profile.get("video_count", 0) > 0:
        score -= 8
        recommendations.append("A few more clickworthy titles and thumbnails should help lift early discovery.")

    recent_keywords = Counter()
    for video in recent_videos:
        recent_keywords.update(_clean_tokens(video["title"]))
    trending_keywords = Counter()
    for video in trending_videos:
        trending_keywords.update(_clean_tokens(video["title"]))
    related_keywords = Counter()
    for video in related_videos:
        related_keywords.update(_clean_tokens(video["title"]))

    overlap = set(recent_keywords) & set(trending_keywords)
    if not overlap and trending_keywords:
        score -= 12
        recommendations.append("Your current titles are not overlapping with the public trend vocabulary. Shift a few upcoming topics toward the live trend terms.")
    elif len(overlap) <= 2:
        score -= 4
        recommendations.append("There is only a small overlap with the trend space. Try one trend-adjacent upload series.")
    else:
        strengths.append(f"Trend vocabulary overlap found: {', '.join(sorted(overlap)[:5])}.")

    if related_keywords:
        strengths.append(f"Popular related words from nearby videos: {', '.join(word for word, _ in related_keywords.most_common(6))}.")

    return max(score, 0), strengths, warnings, recommendations


def audit_single_channel(
    profile: YouTubeChannelProfile,
    settings: Settings,
    *,
    region_code: str = DEFAULT_REGION_CODE,
    max_videos: int = 15,
    related_topic_limit: int = 3,
    trending_limit: int = 15,
) -> dict[str, Any]:
    if not profile.available:
        return {
            "channel_name": profile.channel_name,
            "channel_key": profile.channel_key,
            "status": "skipped",
            "reason": "Token or client secret file missing for this channel.",
            "token_file": str(profile.token_file),
            "secrets_file": str(profile.secrets_file),
        }

    profile_settings = replace(
        settings,
        youtube_token_file=str(profile.token_file),
        youtube_client_secrets_file=str(profile.secrets_file),
    )

    channel_profile = _fetch_channel_profile_data(profile_settings)
    recent_videos = _fetch_recent_videos(profile_settings, max_videos=max_videos)
    trending_videos = _fetch_trending_videos(profile_settings, region_code=region_code, limit=trending_limit)
    topic_queries = _recent_topic_queries(recent_videos, limit=related_topic_limit)
    related_videos = _fetch_related_popular_videos(
        profile_settings,
        queries=topic_queries,
        region_code=region_code,
        per_query_limit=5,
    )

    score, strengths, warnings, recommendations = _score_channel(
        channel_profile,
        recent_videos,
        trending_videos,
        related_videos,
    )

    top_recent = sorted(recent_videos, key=lambda item: item.get("view_count", 0), reverse=True)[:5]
    top_trending = trending_videos[:5]
    top_related = related_videos[:8]
    low_view_videos = _low_view_old_videos({"recent_videos": recent_videos})
    scheduled_videos = _scheduled_or_upcoming_videos({"recent_videos": recent_videos})
    if low_view_videos:
        warnings.append(
            f"{len(low_view_videos)} old videos are below {VIEW_THRESHOLD} views and should be refreshed."
        )
        score = max(score - min(10, len(low_view_videos) * 2), 0)
    if scheduled_videos:
        warnings.append(
            f"{len(scheduled_videos)} scheduled or upcoming videos can be cleaned up before release."
        )

    return {
        "channel_name": profile.channel_name,
        "channel_key": profile.channel_key,
        "status": "audited",
        "score": score,
        "profile": channel_profile,
        "recent_videos": recent_videos,
        "top_recent_videos": top_recent,
        "trending_videos": top_trending,
        "related_videos": top_related,
        "topic_queries": topic_queries,
        "strengths": strengths,
        "warnings": warnings,
        "recommendations": recommendations,
        "low_view_videos": low_view_videos[:10],
        "scheduled_videos": scheduled_videos[:10],
        "summary": {
            "avg_title_length": round(sum(len(v["title"]) for v in recent_videos) / len(recent_videos), 1) if recent_videos else 0,
            "avg_description_length": round(sum(len(v["description"]) for v in recent_videos) / len(recent_videos), 1) if recent_videos else 0,
            "avg_views": round(sum(v["view_count"] for v in recent_videos) / len(recent_videos), 1) if recent_videos else 0,
            "recent_uploads": len(recent_videos),
            "shorts_ratio": round(sum(1 for v in recent_videos if v.get("duration_seconds", 0) and v["duration_seconds"] <= 75) / len(recent_videos), 2) if recent_videos else 0,
            "low_view_count": len(low_view_videos),
            "scheduled_count": len(scheduled_videos),
        },
    }


def audit_youtube_channels(
    settings: Settings,
    project_dir: Path,
    *,
    region_code: str = DEFAULT_REGION_CODE,
    max_videos: int = 15,
    related_topic_limit: int = 3,
    trending_limit: int = 15,
) -> dict[str, Any]:
    profiles = resolve_youtube_channel_profiles(project_dir)
    results = [
        audit_single_channel(
            profile,
            settings,
            region_code=region_code,
            max_videos=max_videos,
            related_topic_limit=related_topic_limit,
            trending_limit=trending_limit,
        )
        for profile in profiles
    ]
    audited = [item for item in results if item.get("status") == "audited"]
    skipped = [item for item in results if item.get("status") != "audited"]
    avg_score = round(sum(item.get("score", 0) for item in audited) / len(audited), 1) if audited else 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region_code": region_code,
        "average_score": avg_score,
        "channels": results,
        "audited_channels": len(audited),
        "skipped_channels": len(skipped),
    }


def _metadata_targets(channel_report: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    recent_videos = list(channel_report.get("recent_videos", []))
    if not recent_videos:
        return []
    avg_views = channel_report.get("summary", {}).get("avg_views", 0) or 0
    ordered = sorted(
        recent_videos,
        key=lambda item: (
            item.get("view_count", 0) <= avg_views,
            item.get("view_count", 0),
            item.get("published_at", ""),
        ),
        reverse=False,
    )
    return ordered[: max(1, limit)]


def _low_view_old_videos(channel_report: dict[str, Any]) -> list[dict[str, Any]]:
    videos = []
    for video in channel_report.get("recent_videos", []):
        if video.get("age_days", 0) >= DAYS_THRESHOLD and video.get("view_count", 0) < VIEW_THRESHOLD:
            videos.append(video)
    videos.sort(key=lambda item: (item.get("view_count", 0), -item.get("age_days", 0)))
    return videos


def _scheduled_or_upcoming_videos(channel_report: dict[str, Any]) -> list[dict[str, Any]]:
    videos = []
    now = datetime.now(timezone.utc)
    for video in channel_report.get("recent_videos", []):
        privacy = str(video.get("privacy_status", "")).lower()
        publish_at = _to_utc_date(str(video.get("publish_at", "")))
        if privacy in SCHEDULED_STATUSES or publish_at is not None:
            if publish_at is None or publish_at >= now or privacy in SCHEDULED_STATUSES:
                videos.append(video)
    videos.sort(key=lambda item: item.get("publish_at", ""))
    return videos


def suggest_video_metadata_rewrite(
    settings: Settings,
    *,
    channel_report: dict[str, Any],
    video: dict[str, Any],
    video_state: str,
    trend_terms: list[str],
    related_terms: list[str],
    rewrite_provider: str = "auto",
) -> dict[str, Any]:
    prompt = f"""
You are a YouTube growth strategist. Rewrite the metadata for one video to improve click-through rate and search relevance without misleading the viewer.

Return strict JSON only with this schema:
{{
  "title": "optimized title under 70 characters",
  "description_paragraph": "2-3 sentence SEO paragraph",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10"],
  "reason": "short explanation",
  "focus_keywords": ["keyword1", "keyword2", "keyword3"]
}}

Constraints:
- Keep the topic honest and relevant to the original video.
- Use words aligned with the channel and current trend vocabulary.
- Make the title click-friendly but not spammy.
- Tags must be specific, not generic.
- If the video is for kids, keep everything family-safe and playful.
- Preserve any mandatory branding phrases already present in the current description.

Channel name: {channel_report.get("profile", {}).get("title", "")}
Channel description: {channel_report.get("profile", {}).get("description", "")}
Video state: {video_state}
Current title: {video.get("title", "")}
Current description: {video.get("description", "")}
Published at: {video.get("published_at", "")}
Age in days: {video.get("age_days", 0)}
Views: {video.get("view_count", 0)}
Trend vocabulary: {", ".join(trend_terms[:12])}
Related popular terms: {", ".join(related_terms[:12])}
Topic queries: {", ".join(channel_report.get("topic_queries", []))}
"""
    payload = _generate_metadata_payload(
        settings,
        prompt=prompt,
        rewrite_provider=rewrite_provider,
    )
    provider = str(payload.pop("_provider", ""))
    model_name = str(payload.pop("_model", ""))
    payload.pop("_reasoning", None)
    title = str(payload.get("title", video.get("title", ""))).strip()
    description_paragraph = str(payload.get("description_paragraph", "")).strip()
    tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()]
    focus_keywords = [str(item).strip() for item in payload.get("focus_keywords", []) if str(item).strip()]
    reason = str(payload.get("reason", "")).strip()
    if len(title) > 100:
        title = title[:100].rstrip()
    if len(description_paragraph) > 600:
        description_paragraph = description_paragraph[:600].rstrip()
    if not tags:
        tags = list(video.get("tags", []) or [])
    tags = list(dict.fromkeys(tags))[:12]
    return {
        "status": "ok",
        "provider": provider,
        "model": model_name,
        "video_id": video.get("video_id", ""),
        "current_title": video.get("title", ""),
        "suggested_title": title,
        "suggested_description_paragraph": description_paragraph,
        "suggested_tags": tags,
        "focus_keywords": focus_keywords[:5],
        "reason": reason,
    }


def optimize_channel_metadata(
    settings: Settings,
    *,
    channel_report: dict[str, Any],
    update_limit: int = 2,
    apply_updates: bool = False,
    rewrite_provider: str = "auto",
) -> dict[str, Any]:
    if channel_report.get("status") != "audited":
        return {
            "channel_name": channel_report.get("channel_name", ""),
            "status": "skipped",
            "reason": "Channel was not audited.",
            "updates": [],
        }

    low_view_candidates = _low_view_old_videos(channel_report)
    scheduled_candidates = _scheduled_or_upcoming_videos(channel_report)
    fallback_candidates = _metadata_targets(channel_report, update_limit)

    candidate_items: list[tuple[dict[str, Any], str]] = []
    seen_ids: set[str] = set()
    for video in low_view_candidates:
        video_id = str(video.get("video_id", ""))
        if video_id and video_id not in seen_ids:
            seen_ids.add(video_id)
            candidate_items.append((video, "low_view_old"))
        if len(candidate_items) >= update_limit:
            break
    if len(candidate_items) < update_limit:
        for video in scheduled_candidates:
            video_id = str(video.get("video_id", ""))
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                candidate_items.append((video, "scheduled_upcoming"))
            if len(candidate_items) >= update_limit:
                break
    if not candidate_items:
        for video in fallback_candidates:
            video_id = str(video.get("video_id", ""))
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                candidate_items.append((video, "recent_performer"))
            if len(candidate_items) >= update_limit:
                break
    if not candidate_items:
        return {
            "channel_name": channel_report.get("channel_name", ""),
            "status": "skipped",
            "reason": "No recent videos found for metadata optimization.",
            "updates": [],
        }

    trend_terms = []
    for item in channel_report.get("trending_videos", []):
        trend_terms.extend(_clean_tokens(str(item.get("title", ""))))
    related_terms = []
    for item in channel_report.get("related_videos", []):
        related_terms.extend(_clean_tokens(str(item.get("title", ""))))
    trend_terms = list(dict.fromkeys(trend_terms))
    related_terms = list(dict.fromkeys(related_terms))

    updates: list[dict[str, Any]] = []
    for video, video_state in candidate_items:
        try:
            suggestion = suggest_video_metadata_rewrite(
                settings,
                channel_report=channel_report,
                video=video,
                video_state=video_state,
                trend_terms=trend_terms,
                related_terms=related_terms,
                rewrite_provider=rewrite_provider,
            )
        except Exception as exc:
            suggestion = {
                "status": "skipped",
                "error": str(exc),
                "video_id": video.get("video_id", ""),
                "current_title": video.get("title", ""),
                "suggested_title": video.get("title", ""),
                "suggested_description_paragraph": "",
                "suggested_tags": list(video.get("tags", []) or []),
                "focus_keywords": [],
                "reason": str(exc),
            }
        update_result: dict[str, Any] | None = None
        if apply_updates and suggestion.get("status") == "ok":
            new_description = str(video.get("description", "")).strip()
            paragraph = str(suggestion.get("suggested_description_paragraph", "")).strip()
            if paragraph:
                new_description = f"{paragraph}\n\n{new_description}".strip()
            update_result = update_youtube_video_metadata(
                settings,
                str(video.get("video_id", "")),
                title=suggestion.get("suggested_title", video.get("title", "")),
                description=new_description,
                tags=list(suggestion.get("suggested_tags", [])),
            )
        updates.append(
            {
                "video_id": video.get("video_id", ""),
                "video_title": video.get("title", ""),
                "view_count": video.get("view_count", 0),
                "video_state": video_state,
                "provider": suggestion.get("provider", ""),
                "model": suggestion.get("model", ""),
                "suggestion": suggestion,
                "applied": bool(update_result),
                "youtube_response": update_result or {},
            }
        )

    return {
        "channel_name": channel_report.get("channel_name", ""),
        "status": "optimized",
        "apply_updates": apply_updates,
        "updates": updates,
    }


def _telegram_summary_for_weekly_run(report: dict[str, Any], optimizations: list[dict[str, Any]]) -> str:
    audited = report.get("audited_channels", 0)
    avg_score = report.get("average_score", 0)
    lines = [
        "YouTube weekly audit complete.",
        f"Audited channels: {audited}",
        f"Average score: {avg_score}",
    ]
    for channel in report.get("channels", []):
        if channel.get("status") != "audited":
            lines.append(f"- {channel.get('channel_name', 'Channel')}: skipped")
            continue
        lines.append(
            f"- {channel.get('channel_name', 'Channel')}: score {channel.get('score', 0)}, "
            f"{len(channel.get('recommendations', []))} fixes, "
            f"{len(channel.get('low_view_videos', []))} low-view, "
            f"{len(channel.get('scheduled_videos', []))} scheduled"
        )
    if optimizations:
        lines.append("")
        lines.append("Metadata rewrites:")
        for item in optimizations:
            updates = item.get("updates", [])
            if not updates:
                continue
            for update in updates:
                suggestion = update.get("suggestion", {})
                lines.append(
                    f"- {item.get('channel_name', '')}: {update.get('video_title', '')} -> {suggestion.get('suggested_title', '')}"
                )
    lines.append("")
    lines.append("Reply inside the app to inspect the full markdown report.")
    return "\n".join(lines).strip()


def run_weekly_youtube_review(
    settings: Settings,
    project_dir: Path,
    *,
    region_code: str = DEFAULT_REGION_CODE,
    max_videos: int = 15,
    related_topic_limit: int = 3,
    trending_limit: int = 15,
    update_limit: int = 2,
    apply_updates: bool = False,
    rewrite_provider: str = "auto",
    notify_telegram: bool = True,
    telegram_bot_token: str = "",
    telegram_chat_id: str = "",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    report = audit_youtube_channels(
        settings,
        project_dir,
        region_code=region_code,
        max_videos=max_videos,
        related_topic_limit=related_topic_limit,
        trending_limit=trending_limit,
    )
    optimizations: list[dict[str, Any]] = []
    for channel in report.get("channels", []):
        optimizations.append(
            optimize_channel_metadata(
                settings,
                channel_report=channel,
                update_limit=update_limit,
                apply_updates=apply_updates,
                rewrite_provider=rewrite_provider,
            )
        )

    merged = {
        "generated_at": report.get("generated_at"),
        "region_code": report.get("region_code"),
        "average_score": report.get("average_score"),
        "channels": report.get("channels", []),
        "optimizations": optimizations,
        "apply_updates": apply_updates,
        "rewrite_provider": rewrite_provider,
    }
    out_dir = output_dir or (settings.output_dir / "youtube_audits")
    paths = write_youtube_audit_report(merged, out_dir)
    merged["report_paths"] = {key: str(path) for key, path in paths.items()}

    if notify_telegram:
        bot_token = (telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        chat_id = (telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        if bot_token and chat_id:
            message = _telegram_summary_for_weekly_run(report, optimizations)
            send_telegram_message(bot_token, chat_id, message[:3900])
            try:
                send_telegram_document(bot_token, chat_id, paths["markdown"], caption="YouTube weekly audit report")
            except Exception:
                pass
            merged["telegram_sent"] = True
        else:
            merged["telegram_sent"] = False
    return merged


def render_youtube_audit_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# YouTube Channel Audit")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at', '')}`")
    lines.append(f"- Region: `{report.get('region_code', '')}`")
    lines.append(f"- Average score: `{report.get('average_score', 0)}`")
    if report.get("rewrite_provider"):
        lines.append(f"- Rewrite provider: `{report.get('rewrite_provider', '')}`")
    lines.append("")

    for channel in report.get("channels", []):
        status = channel.get("status", "")
        lines.append(f"## {channel.get('channel_name', 'Channel')}")
        lines.append(f"- Status: `{status}`")
        if status != "audited":
            lines.append(f"- Reason: {channel.get('reason', 'Unavailable')}")
            lines.append("")
            continue
        lines.append(f"- Score: `{channel.get('score', 0)}`")
        profile = channel.get("profile", {})
        summary = channel.get("summary", {})
        lines.append(f"- Subscribers: `{profile.get('subscriber_count', 0):,}`")
        lines.append(f"- Recent uploads inspected: `{summary.get('recent_uploads', 0)}`")
        lines.append(f"- Avg title length: `{summary.get('avg_title_length', 0)}`")
        lines.append(f"- Avg description length: `{summary.get('avg_description_length', 0)}`")
        lines.append(f"- Avg views: `{summary.get('avg_views', 0)}`")
        lines.append(f"- Shorts ratio: `{summary.get('shorts_ratio', 0)}`")
        lines.append(f"- Old low-view videos: `{summary.get('low_view_count', 0)}`")
        lines.append(f"- Scheduled/upcoming videos: `{summary.get('scheduled_count', 0)}`")
        if channel.get("topic_queries"):
            lines.append(f"- Topic queries: {', '.join(f'`{q}`' for q in channel['topic_queries'])}")
        if channel.get("strengths"):
            lines.append("- Strengths:")
            for item in channel["strengths"][:5]:
                lines.append(f"  - {item}")
        if channel.get("warnings"):
            lines.append("- Warnings:")
            for item in channel["warnings"][:5]:
                lines.append(f"  - {item}")
        if channel.get("recommendations"):
            lines.append("- Fixes:")
            for item in channel["recommendations"][:8]:
                lines.append(f"  - {item}")
        if channel.get("top_recent_videos"):
            lines.append("- Best recent uploads:")
            for video in channel["top_recent_videos"][:3]:
                lines.append(
                    f"  - {video.get('title', '')} | {video.get('view_count', 0):,} views | {video.get('duration_seconds', 0)}s"
                )
        if channel.get("trending_videos"):
            lines.append("- Trending videos in region:")
            for video in channel["trending_videos"][:3]:
                lines.append(
                    f"  - {video.get('title', '')} | {video.get('view_count', 0):,} views | {video.get('channel_title', '')}"
                )
        if channel.get("related_videos"):
            lines.append("- Related popular videos:")
            for video in channel["related_videos"][:3]:
                lines.append(
                    f"  - [{video.get('query', '')}] {video.get('title', '')} | {video.get('view_count', 0):,} views"
                )
        if channel.get("low_view_videos"):
            lines.append("- Low-view videos ready for refresh:")
            for video in channel["low_view_videos"][:3]:
                lines.append(
                    f"  - {video.get('title', '')} | {video.get('view_count', 0):,} views | {video.get('age_days', 0)} days old"
                )
        if channel.get("scheduled_videos"):
            lines.append("- Scheduled/upcoming videos:")
            for video in channel["scheduled_videos"][:3]:
                lines.append(
                    f"  - {video.get('title', '')} | {video.get('privacy_status', '')} | publishAt {video.get('publish_at', '')}"
                )
        lines.append("")

    if report.get("optimizations"):
        lines.append("## Metadata Optimizations")
        lines.append("")
        lines.append(f"- Apply updates: `{report.get('apply_updates', False)}`")
        for item in report.get("optimizations", []):
            lines.append(f"### {item.get('channel_name', 'Channel')}")
            lines.append(f"- Status: `{item.get('status', '')}`")
            for update in item.get("updates", [])[:5]:
                suggestion = update.get("suggestion", {})
                lines.append(f"- State: `{update.get('video_state', '')}`")
                if update.get("provider") or update.get("model"):
                    lines.append(
                        f"  - Provider: `{update.get('provider', '')}` / `{update.get('model', '')}`"
                    )
                lines.append(
                    f"- `{update.get('video_title', '')}` -> `{suggestion.get('suggested_title', '')}`"
                )
                if suggestion.get("reason"):
                    lines.append(f"  - Reason: {suggestion.get('reason')}")
                if suggestion.get("suggested_description_paragraph"):
                    lines.append(f"  - Description paragraph: {suggestion.get('suggested_description_paragraph')}")
                if suggestion.get("focus_keywords"):
                    lines.append(
                        f"  - Focus keywords: {', '.join(str(x) for x in suggestion.get('focus_keywords', []))}"
                    )
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_youtube_audit_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"youtube_audit_{timestamp}.json"
    md_path = output_dir / f"youtube_audit_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_youtube_audit_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
