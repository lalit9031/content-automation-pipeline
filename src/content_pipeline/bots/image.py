from __future__ import annotations

import base64
import json
import re
import struct
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Callable, Protocol

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


@dataclass(frozen=True)
class ImageVariant:
    aspect_ratio: str
    width: int
    height: int
    filename: str


VARIANTS = [
    ImageVariant("1:1", 1080, 1080, "images/image_square"),
    ImageVariant("16:9", 1280, 720, "images/image_landscape"),
    ImageVariant("9:16", 1080, 1920, "images/image_portrait"),
]


class ImageProvider(Protocol):
    extension: str

    def create(self, prompt: str, variant: ImageVariant) -> bytes: ...


class MockImageProvider:
    extension = ".svg"

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        title = escape(
            _prompt_field(prompt, "Renderer-only headline")
            or _prompt_field(prompt, "Main headline text")
            or _prompt_topic(prompt)
            or "THE PM AI QUESTION"
        )
        hook = escape(
            _prompt_field(prompt, "Renderer-only hook")
            or _prompt_field(prompt, "Opening hook text")
            or "Practical PM AI playbook"
        )
        concepts = _prompt_concepts(prompt)
        concept_rows = "\n".join(
            f"""    <g transform="translate(0 {index * 82})">
      <rect x="0" y="0" width="310" height="62" rx="22" fill="#111827" fill-opacity="0.76" stroke="{color}" stroke-width="2"/>
      <circle cx="34" cy="31" r="11" fill="{color}"/>
      <text x="58" y="39" fill="#f8fafc" font-family="Arial, sans-serif" font-size="24" font-weight="800">{escape(label)}</text>
    </g>"""
            for index, (label, color) in enumerate(zip(concepts, ("#38bdf8", "#f59e0b", "#a3e635")))
        )
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{variant.width}" height="{variant.height}" viewBox="0 0 {variant.width} {variant.height}">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop stop-color="#030712"/>
      <stop offset="0.52" stop-color="#07152f"/>
      <stop offset="1" stop-color="#301308"/>
    </linearGradient>
    <radialGradient id="aiGlow" cx="73%" cy="42%" r="35%">
      <stop stop-color="#38bdf8" stop-opacity="0.9"/>
      <stop offset="0.36" stop-color="#0ea5e9" stop-opacity="0.34"/>
      <stop offset="1" stop-color="#020617" stop-opacity="0"/>
    </radialGradient>
    <filter id="shadow"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000000" flood-opacity="0.45"/></filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#aiGlow)"/>
  <path d="M0 610 C250 500 430 700 670 590 C900 485 1040 540 1280 435" stroke="#38bdf8" stroke-opacity="0.32" stroke-width="8" fill="none"/>
  <path d="M0 650 C250 555 450 730 700 625 C930 528 1100 605 1280 485" stroke="#f59e0b" stroke-opacity="0.42" stroke-width="7" fill="none"/>
  <g opacity="0.15" stroke="#94a3b8" stroke-width="1">
    {"".join(f'<line x1="{x}" y1="0" x2="{x}" y2="{variant.height}"/>' for x in range(0, variant.width + 1, 64))}
    {"".join(f'<line x1="0" y1="{y}" x2="{variant.width}" y2="{y}"/>' for y in range(0, variant.height + 1, 64))}
  </g>
  <g transform="translate(70 58)">
    <rect width="285" height="46" rx="23" fill="#f59e0b" filter="url(#shadow)"/>
    <text x="28" y="31" fill="#111827" font-family="Arial, sans-serif" font-size="24" font-weight="900">LEARN WITH LALIT</text>
    <rect x="330" width="190" height="46" rx="23" fill="#111827" stroke="#a855f7" stroke-width="2"/>
    <text x="360" y="31" fill="#ffffff" font-family="Arial, sans-serif" font-size="23" font-weight="900">AI FOR PMS</text>
  </g>
  <g transform="translate(70 170)" filter="url(#shadow)">
    <text x="0" y="0" fill="#ffffff" font-family="Arial, sans-serif" font-size="{max(46, variant.width // 14)}" font-weight="900">{title}</text>
    <text x="2" y="76" fill="#93c5fd" font-family="Arial, sans-serif" font-size="{max(34, variant.width // 22)}" font-weight="900">{hook}</text>
  </g>
  <g transform="translate(78 370)">
    <rect x="0" y="0" width="570" height="170" rx="34" fill="#0f172a" fill-opacity="0.74" stroke="#38bdf8" stroke-width="2"/>
    <text x="38" y="58" fill="#e5e7eb" font-family="Arial, sans-serif" font-size="28" font-weight="800">Local renderer baseline</text>
    <text x="38" y="100" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="23">Clean text, deterministic layout,</text>
    <text x="38" y="134" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="23">no API cost, less cinematic realism.</text>
  </g>
  <g transform="translate(780 190)" filter="url(#shadow)">
    <circle cx="210" cy="155" r="142" fill="#020617" stroke="#38bdf8" stroke-width="3"/>
    <path d="M115 155 C145 72 275 74 307 155 C280 245 148 244 115 155Z" fill="none" stroke="#38bdf8" stroke-width="8"/>
    <circle cx="210" cy="155" r="42" fill="#38bdf8" fill-opacity="0.2" stroke="#93c5fd" stroke-width="5"/>
    <path d="M210 30 L210 0 M210 310 L210 280 M65 155 L25 155 M395 155 L355 155" stroke="#93c5fd" stroke-width="5"/>
  </g>
  <g transform="translate(820 472)">
{concept_rows}
  </g>
  <text x="70" y="{variant.height - 48}" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="22" font-weight="800">PMP • SCRUM • AGILE • SAFE • JIRA • COPILOT • PMO</text>
</svg>
"""
        return svg.encode("utf-8")


class ImagenProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        if not settings.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID is required for IMAGE_PROVIDER=imagen")
        try:
            from google import genai
            from google.genai.types import GenerateImagesConfig
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.generate_images_config = GenerateImagesConfig
        self.client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        self.model = settings.imagen_model
        if self.model == "imagen-3.0-generate-002":
            self.model = "imagen-4.0-generate-001"
        self.fallback_provider = MockImageProvider()

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        try:
            config = self.generate_images_config(
                number_of_images=1,
                aspect_ratio=variant.aspect_ratio,
                output_mime_type="image/png",
            )
            response = self.client.models.generate_images(
                model=self.model,
                prompt=prompt,
                config=config,
            )
            return response.generated_images[0].image.image_bytes
        except Exception:
            return self.fallback_provider.create(prompt, variant)


class GeminiImageProvider:
    extension = ".png"

    def __init__(
        self,
        settings: Settings,
        *,
        clients: list[object] | None = None,
        limiter: "GeminiImageLimiter" | None = None,
        now_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        if not settings.gemini_api_key and not clients:
            raise ValueError("GEMINI_API_KEY is required for IMAGE_PROVIDER=gemini")
        if clients is None:
            try:
                from google import genai
                from google.genai.types import GenerateImagesConfig
            except ImportError as exc:
                raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
            self.generate_images_config = GenerateImagesConfig
            clients = [genai.Client(api_key=key) for key in (settings.gemini_api_keys or (settings.gemini_api_key,))]
        else:
            self.generate_images_config = None
        self.settings = settings
        self.clients = clients
        self.model = settings.imagen_model
        if self.model == "imagen-3.0-generate-002":
            self.model = "imagen-4.0-generate-001"
        self.fallback_provider = _fallback_image_provider(settings)
        state_path = settings.output_dir / ".runtime" / "gemini_image_rate_limit.json"
        self.limiter = limiter or GeminiImageLimiter(
            key_count=len(self.clients),
            daily_budget=settings.gemini_image_daily_budget,
            min_interval_seconds=settings.gemini_image_min_interval_seconds,
            max_attempts=settings.gemini_image_max_attempts,
            retry_backoff_seconds=settings.gemini_image_retry_backoff_seconds,
            state_path=state_path,
            now_fn=now_fn or time.time,
            sleep_fn=sleep_fn or time.sleep,
        )

    def ensure_capacity(self, count: int) -> None:
        self.limiter.ensure_capacity(count)

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        try:
            self.ensure_capacity(1)
        except RuntimeError as exc:
            if _is_budget_exhausted(exc):
                return self.fallback_provider.create(prompt, variant)
            raise
        last_error: Exception | None = None
        for _ in range(self.limiter.max_attempts):
            client_index = self.limiter.acquire_key(max_wait_seconds=max(5.0, self.limiter.min_interval_seconds))
            if client_index is None:
                return self.fallback_provider.create(prompt, variant)
            client = self.clients[client_index]
            try:
                config = None
                if self.generate_images_config is not None:
                    config = self.generate_images_config(
                        number_of_images=1,
                        aspect_ratio=variant.aspect_ratio,
                        output_mime_type="image/png",
                    )
                response = client.models.generate_images(
                    model=self.model,
                    prompt=prompt,
                    config=config,
                )
                image_bytes = _response_image_bytes(response)
                if image_bytes is None:
                    raise RuntimeError("Gemini image generation did not return an image asset.")
                self.limiter.record_success(client_index)
                return image_bytes
            except Exception as exc:
                last_error = exc
                if not self.limiter.is_retryable(exc):
                    self.limiter.record_failure(client_index, exc, retryable=False)
                    return self.fallback_provider.create(prompt, variant)
                self.limiter.record_failure(client_index, exc, retryable=True)
        if last_error is not None and self.limiter.is_retryable(last_error):
            return self.fallback_provider.create(prompt, variant)
        raise RuntimeError(
            "Gemini image generation failed after exhausting the configured keys and retries: "
            f"{last_error}"
        )


@dataclass
class _GeminiKeyState:
    next_available_at: float = 0.0
    cooldown_until: float = 0.0
    consecutive_failures: int = 0
    usage_date: str = ""
    daily_generated: int = 0


class GeminiImageLimiter:
    def __init__(
        self,
        *,
        key_count: int,
        daily_budget: int,
        min_interval_seconds: float,
        max_attempts: int,
        retry_backoff_seconds: float,
        state_path: Path | None = None,
        now_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if key_count <= 0:
            raise ValueError("key_count must be positive")
        self.max_attempts = max(1, max_attempts)
        self.daily_budget = max(0, daily_budget)
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.state_path = state_path
        self._now = now_fn
        self._sleep = sleep_fn
        self._lock = threading.RLock()
        self._states = [_GeminiKeyState() for _ in range(key_count)]
        self._usage_date = self._today()
        self._load()

    def ensure_capacity(self, count: int) -> None:
        if count <= 0 or self.daily_budget <= 0:
            return
        remaining = self.remaining_daily_images()
        if remaining < count:
            next_allowed_at = self._next_daily_reset()
            raise RuntimeError(
                "Gemini image daily budget exhausted "
                f"({self.daily_budget} per UTC day, {remaining} remaining). "
                f"Next request allowed at {datetime.fromtimestamp(next_allowed_at, tz=timezone.utc).isoformat()}."
            )

    def acquire_key(self, *, max_wait_seconds: float | None = 5.0) -> int | None:
        while True:
            with self._lock:
                self._reset_daily_if_needed()
                now = self._now()
                index, available_at = self._next_key(now)
                wait_seconds = available_at - now
                if wait_seconds <= 0:
                    state = self._states[index]
                    state.next_available_at = now + self.min_interval_seconds
                    self._save_locked()
                    return index
                if max_wait_seconds is not None and wait_seconds > max_wait_seconds:
                    return None
            self._sleep(wait_seconds)

    def record_success(self, index: int) -> None:
        with self._lock:
            self._reset_daily_if_needed()
            state = self._states[index]
            state.consecutive_failures = 0
            state.cooldown_until = 0.0
            state.daily_generated += 1
            state.usage_date = self._usage_date
            self._save_locked()

    def record_failure(self, index: int, exc: Exception, *, retryable: bool) -> None:
        with self._lock:
            self._reset_daily_if_needed()
            state = self._states[index]
            now = self._now()
            if retryable:
                state.consecutive_failures += 1
                backoff = min(
                    self.retry_backoff_seconds,
                    max(self.min_interval_seconds, self.min_interval_seconds * (2 ** (state.consecutive_failures - 1))),
                )
                state.cooldown_until = max(state.cooldown_until, now + backoff)
                state.next_available_at = max(state.next_available_at, now + self.min_interval_seconds)
            else:
                state.consecutive_failures = 0
            self._save_locked()

    def is_retryable(self, exc: Exception) -> bool:
        message = f"{exc.__class__.__name__}: {exc}".lower()
        retryable_markers = (
            "429",
            "too many requests",
            "rate limit",
            "rate limited",
            "resource exhausted",
            "quota exceeded",
            "temporarily unavailable",
            "deadline exceeded",
            "unavailable",
            "service unavailable",
        )
        return any(marker in message for marker in retryable_markers)

    def _next_key(self, now: float) -> tuple[int, float]:
        best_index = 0
        best_available = self._available_at(self._states[0], now)
        for index in range(1, len(self._states)):
            available_at = self._available_at(self._states[index], now)
            if available_at < best_available:
                best_index = index
                best_available = available_at
        return best_index, best_available

    def _available_at(self, state: _GeminiKeyState, now: float) -> float:
        return max(state.next_available_at, state.cooldown_until, now)

    def _load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        raw_states = data.get("keys", [])
        if not isinstance(raw_states, list):
            return
        for index, raw_state in enumerate(raw_states[: len(self._states)]):
            if not isinstance(raw_state, dict):
                continue
            state = self._states[index]
            state.next_available_at = float(raw_state.get("next_available_at", 0.0))
            state.cooldown_until = float(raw_state.get("cooldown_until", 0.0))
            state.consecutive_failures = int(raw_state.get("consecutive_failures", 0))
            state.usage_date = str(raw_state.get("usage_date", ""))
            state.daily_generated = int(raw_state.get("daily_generated", 0))
        self._usage_date = str(data.get("usage_date", self._today()))
        self._reset_daily_if_needed()

    def _save_locked(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": self._now(),
            "usage_date": self._usage_date,
            "keys": [
                {
                    "next_available_at": state.next_available_at,
                    "cooldown_until": state.cooldown_until,
                    "consecutive_failures": state.consecutive_failures,
                    "usage_date": state.usage_date,
                    "daily_generated": state.daily_generated,
                }
                for state in self._states
            ],
        }
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def current_daily_generated(self) -> int:
        self._reset_daily_if_needed()
        return sum(state.daily_generated for state in self._states if state.usage_date == self._usage_date)

    def remaining_daily_images(self) -> int | None:
        if self.daily_budget <= 0:
            return None
        used = self.current_daily_generated()
        return max(self.daily_budget - used, 0)

    def _reset_daily_if_needed(self) -> None:
        with self._lock:
            today = self._today()
            if self._usage_date == today:
                return
            self._usage_date = today
            for state in self._states:
                state.daily_generated = 0
                state.usage_date = today
            self._save_locked()

    def _today(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).date().isoformat()

    def _next_daily_reset(self) -> float:
        now_dt = datetime.fromtimestamp(self._now(), tz=timezone.utc)
        next_day = (now_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        return next_day.timestamp()


def gemini_image_status(settings: Settings, now: float | None = None) -> dict[str, object]:
    now = time.time() if now is None else now
    slots = [
        ("GEMINI_API_KEY", settings.gemini_api_key),
        ("GEMINI_API_KEY_2", settings.gemini_api_keys[1] if len(settings.gemini_api_keys) > 1 else ""),
        ("GEMINI_API_KEY_3", settings.gemini_api_keys[2] if len(settings.gemini_api_keys) > 2 else ""),
        ("GEMINI_API_KEY_4", settings.gemini_api_keys[3] if len(settings.gemini_api_keys) > 3 else ""),
    ]
    configured_slots = [
        {"slot": index + 1, "env_var": env_var, "configured": bool(value)}
        for index, (env_var, value) in enumerate(slots)
    ]
    state_path = settings.output_dir / ".runtime" / "gemini_image_rate_limit.json"
    raw_state: dict[str, object] = {}
    if state_path.exists():
        try:
            raw_state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            raw_state = {}
    raw_keys = raw_state.get("keys", [])
    key_states: list[dict[str, object]] = []
    cooling_down_slots: list[int] = []
    next_allowed_at: float | None = None
    daily_usage = 0
    daily_remaining: int | None = settings.gemini_image_daily_budget if settings.gemini_image_daily_budget > 0 else None
    daily_limit_reached = False
    next_daily_reset_at: float | None = None
    for index, slot in enumerate(configured_slots):
        state = raw_keys[index] if isinstance(raw_keys, list) and index < len(raw_keys) and isinstance(raw_keys[index], dict) else {}
        next_available_at = _float_value(state.get("next_available_at"), default=0.0)
        cooldown_until = _float_value(state.get("cooldown_until"), default=0.0)
        consecutive_failures = int(_float_value(state.get("consecutive_failures"), default=0.0))
        daily_generated = int(_float_value(state.get("daily_generated"), default=0.0))
        usage_date = str(state.get("usage_date", ""))
        available_at = max(next_available_at, cooldown_until, now)
        available_in_seconds = max(0.0, available_at - now) if slot["configured"] else None
        if slot["configured"] and available_in_seconds is not None and available_in_seconds > 0:
            cooling_down_slots.append(slot["slot"])
        if slot["configured"]:
            next_allowed_at = available_at if next_allowed_at is None else min(next_allowed_at, available_at)
        if usage_date == datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat():
            daily_usage += daily_generated
        key_states.append(
            {
                **slot,
                "cooling_down": bool(available_in_seconds and available_in_seconds > 0),
                "available_in_seconds": round(available_in_seconds, 2) if available_in_seconds is not None else None,
                "available_at": (
                    datetime.fromtimestamp(available_at, tz=timezone.utc).isoformat()
                    if available_in_seconds is not None
                    else None
                ),
                "consecutive_failures": consecutive_failures,
                "daily_generated": daily_generated,
                "usage_date": usage_date or None,
            }
        )
    if settings.gemini_image_daily_budget > 0:
        daily_remaining = max(settings.gemini_image_daily_budget - daily_usage, 0)
        daily_limit_reached = daily_remaining == 0
        next_daily_reset_at = (
            datetime.fromtimestamp(now, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        ).timestamp()
        if daily_limit_reached:
            next_allowed_at = next_daily_reset_at
    return {
        "configured": any(slot["configured"] for slot in configured_slots),
        "configured_key_count": sum(1 for slot in configured_slots if slot["configured"]),
        "model": settings.imagen_model,
        "daily_budget": settings.gemini_image_daily_budget,
        "daily_generated": daily_usage,
        "daily_remaining": daily_remaining,
        "daily_limit_reached": daily_limit_reached,
        "next_daily_reset_at": (
            datetime.fromtimestamp(next_daily_reset_at, tz=timezone.utc).isoformat()
            if next_daily_reset_at is not None
            else None
        ),
        "min_interval_seconds": settings.gemini_image_min_interval_seconds,
        "max_attempts": settings.gemini_image_max_attempts,
        "retry_backoff_seconds": settings.gemini_image_retry_backoff_seconds,
        "state_path": str(state_path),
        "next_request_allowed_at": (
            datetime.fromtimestamp(next_allowed_at, tz=timezone.utc).isoformat()
            if next_allowed_at is not None
            else None
        ),
        "next_request_allowed_in_seconds": (
            round(max(0.0, next_allowed_at - now), 2) if next_allowed_at is not None else None
        ),
        "cooling_down_slots": cooling_down_slots,
        "key_states": key_states,
    }


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def gemini_image_package_plan(
    settings: Settings,
    *,
    packages_requested: int = 1,
    now: float | None = None,
) -> dict[str, object]:
    status = gemini_image_status(settings, now=now)
    images_per_package = len(VARIANTS)
    daily_remaining = status["daily_remaining"]
    if daily_remaining is None:
        full_packages_remaining: int | None = None
        can_complete_requested = True
    else:
        full_packages_remaining = int(daily_remaining) // images_per_package
        can_complete_requested = full_packages_remaining >= packages_requested
    fallback_provider = _safe_fallback_provider_name(settings.image_fallback_provider)
    recommended_provider = settings.image_provider
    stop_before_failure = False
    if settings.image_provider == "gemini" and daily_remaining is not None:
        stop_before_failure = not can_complete_requested or int(daily_remaining) < images_per_package
        if stop_before_failure:
            recommended_provider = fallback_provider
    return {
        "requested_packages": packages_requested,
        "images_per_package": images_per_package,
        "daily_remaining_images": daily_remaining,
        "full_packages_remaining": full_packages_remaining,
        "can_complete_requested_packages": can_complete_requested,
        "recommended_provider": recommended_provider,
        "fallback_provider": fallback_provider,
        "stop_before_failure": stop_before_failure,
        "status": "safe" if can_complete_requested else "fallback_recommended",
    }


def render_gemini_image_status_widget(settings: Settings, now: float | None = None) -> str:
    status = gemini_image_status(settings, now=now)
    plan = gemini_image_package_plan(settings, now=now)
    remaining = "unlimited" if status["daily_remaining"] is None else str(status["daily_remaining"])
    cooling = ", ".join(f"slot {slot}" for slot in status["cooling_down_slots"]) or "none"
    next_request = (
        "ready now"
        if status["next_request_allowed_in_seconds"] is None
        else f'{status["next_request_allowed_in_seconds"]} s'
    )
    return f"""<section style="background:#0f172a;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
    <div>
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Gemini image quota</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px;">{status["configured_key_count"]} key(s) configured</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:12px;color:#94a3b8;">Next request</div>
      <div style="font-size:18px;font-weight:700;">{next_request}</div>
    </div>
  </div>
  <p style="margin:12px 0 0;color:#cbd5e1;">Daily remaining: <strong>{remaining}</strong> · Cooling: <strong>{cooling}</strong> · Fallback: <strong>{plan["recommended_provider"]}</strong></p>
  <p style="margin:8px 0 0;color:#94a3b8;font-size:13px;">Full packages remaining: {plan["full_packages_remaining"] if plan["full_packages_remaining"] is not None else "unlimited"} · Stop before failure: {str(plan["stop_before_failure"]).lower()}</p>
</section>"""


def _is_budget_exhausted(exc: Exception) -> bool:
    message = str(exc).lower()
    return "daily budget exhausted" in message or "quota exhausted" in message


def _safe_fallback_provider_name(name: str) -> str:
    fallback = (name or "imagen").strip().lower()
    if fallback in {"gemini", "google", "google-genai"}:
        return "mock"
    if fallback == "auto":
        return "imagen"
    return fallback


def _fallback_image_provider(settings: Settings) -> ImageProvider:
    fallback_name = _safe_fallback_provider_name(settings.image_fallback_provider)
    candidates = [fallback_name]
    if fallback_name != "mock":
        candidates.append("mock")
    for provider_name in candidates:
        try:
            if provider_name == "mock":
                return MockImageProvider()
            if provider_name == "imagen":
                return ImagenProvider(replace(settings, image_provider="imagen"))
            if provider_name == "openai":
                return OpenAIImageProvider(replace(settings, image_provider="openai"))
        except Exception:
            continue
    return MockImageProvider()


class OpenAIImageProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for IMAGE_PROVIDER=openai")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
        self.clients = [OpenAI(api_key=key) for key in (settings.openai_api_keys or (settings.openai_api_key,))]
        self.model = settings.openai_image_model

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        last_error: Exception | None = None
        for client in self.clients:
            try:
                result = client.images.generate(
                    model=self.model,
                    prompt=prompt,
                    size=_openai_size_for(variant),
                    quality="low",
                )
                image_base64 = result.data[0].b64_json
                if not image_base64:
                    raise RuntimeError("OpenAI image generation did not return an image asset.")
                return base64.b64decode(image_base64)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"OpenAI image generation failed for all configured keys: {last_error}")


class PollinationsImageProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fallback_provider = MockImageProvider()

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        import urllib.parse
        import requests

        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={variant.width}&height={variant.height}&nologo=true&private=true"
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception:
            return self.fallback_provider.create(prompt, variant)


def image_provider(settings: Settings) -> ImageProvider:
    provider_name = _resolved_image_provider_name(settings)
    if provider_name == "mock":
        return MockImageProvider()
    if provider_name in {"free-ai", "pollinations"}:
        return PollinationsImageProvider(settings)
    if provider_name == "imagen":
        return ImagenProvider(settings)
    if provider_name == "gemini":
        return GeminiImageProvider(settings)
    if provider_name in {"openai", "chatgpt", "gpt-image"}:
        return OpenAIImageProvider(settings)
    raise ValueError(f"Unsupported IMAGE_PROVIDER: {settings.image_provider}")


def _resolved_image_provider_name(settings: Settings) -> str:
    provider_name = (settings.image_provider or "").strip().lower()
    if provider_name == "gemini" and settings.gcp_project_id:
        return "imagen"
    return provider_name


def generate_images(
    package: ContentPackage,
    provider: ImageProvider,
    storage: LocalDailyStorage,
    *,
    max_dimension: int = 2048,
    max_bytes: int = 5 * 1024 * 1024,
    request_delay_seconds: float = 0.0,
) -> list[str]:
    files: list[str] = []
    batch_provider = provider
    if isinstance(provider, GeminiImageProvider):
        plan = gemini_image_package_plan(
            provider.settings,
            packages_requested=1,
        )
        if plan["recommended_provider"] != "gemini":
            batch_provider = provider.fallback_provider
        else:
            try:
                provider.ensure_capacity(len(VARIANTS))
            except RuntimeError as exc:
                if _is_budget_exhausted(exc):
                    batch_provider = provider.fallback_provider
                else:
                    raise
    for index, variant in enumerate(VARIANTS):
        filename = variant.filename + batch_provider.extension
        image_bytes = batch_provider.create(package.image_prompt, variant)
        _assert_image_limits(image_bytes, batch_provider.extension, filename, max_dimension, max_bytes)
        storage.write_bytes(package.date, filename, image_bytes)
        files.append(filename)
        if request_delay_seconds > 0 and index + 1 < len(VARIANTS):
            time.sleep(request_delay_seconds)
    return files


def _assert_image_limits(
    image_bytes: bytes,
    extension: str,
    filename: str,
    max_dimension: int,
    max_bytes: int,
) -> None:
    if len(image_bytes) > max_bytes:
        raise ValueError(
            f"Generated image {filename} exceeds the {max_bytes} byte limit. "
            "Ask the agent to simplify the composition or reduce detail."
        )
    if extension.lower() != ".png":
        return
    width, height = _png_dimensions(image_bytes)
    if width > max_dimension or height > max_dimension:
        raise ValueError(
            f"Generated image {filename} is {width}x{height}, which exceeds the "
            f"{max_dimension}px limit. Regenerate a smaller asset."
        )


def _png_dimensions(image_bytes: bytes) -> tuple[int, int]:
    if len(image_bytes) < 24 or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG image bytes were not valid.")
    if image_bytes[12:16] != b"IHDR":
        raise ValueError("PNG image bytes are missing IHDR metadata.")
    width = struct.unpack(">I", image_bytes[16:20])[0]
    height = struct.unpack(">I", image_bytes[20:24])[0]
    return width, height


def _response_image_bytes(response: object) -> bytes | None:
    generated_images = getattr(response, "generated_images", None)
    if generated_images:
        for generated_image in generated_images:
            image = getattr(generated_image, "image", None)
            if image is None:
                continue
            image_bytes = getattr(image, "image_bytes", None)
            if image_bytes:
                return bytes(image_bytes)
    candidates = []
    parts = getattr(response, "parts", None)
    if parts:
        candidates.extend(parts)
    responses = getattr(response, "candidates", None)
    if responses:
        for candidate in responses:
            content = getattr(candidate, "content", None)
            if content is not None:
                candidate_parts = getattr(content, "parts", None)
                if candidate_parts:
                    candidates.extend(candidate_parts)
    for part in candidates:
        inline_data = getattr(part, "inline_data", None)
        if inline_data is not None:
            data = getattr(inline_data, "data", None)
            if data:
                return bytes(data)
        as_image = getattr(part, "as_image", None)
        if callable(as_image):
            image = as_image()
            if image is not None:
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue()
    return None


def _openai_size_for(variant: ImageVariant) -> str:
    if variant.aspect_ratio == "16:9":
        return "1536x1024"
    if variant.aspect_ratio == "9:16":
        return "1024x1536"
    return "1024x1024"


def _prompt_field(prompt: str, field: str) -> str:
    pattern = rf'{re.escape(field)}:\s*"?([^"\n]+)"?'
    match = re.search(pattern, prompt, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _prompt_topic(prompt: str) -> str:
    match = re.search(r"Topic:\s*([^\n]+)", prompt, flags=re.IGNORECASE)
    return match.group(1).strip().upper() if match else ""


def _prompt_concepts(prompt: str) -> list[str]:
    known = [
        "Cycle Time",
        "Escaped Defects",
        "Delivery Confidence",
        "Risk Visibility",
        "Flow Faster",
        "Review Human",
    ]
    found = [concept for concept in known if concept.lower() in prompt.lower()]
    return (found + ["Risk Visible", "Flow Faster", "Review Human"])[:3]
