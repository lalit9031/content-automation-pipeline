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
    ImageVariant("16:9", 2560, 1440, "images/image_landscape"),
    ImageVariant("9:16", 1080, 1920, "images/image_portrait"),
]


class ImageProvider(Protocol):
    extension: str

    def create(self, prompt: str, variant: ImageVariant) -> bytes: ...


class MockImageProvider:
    extension = ".svg"

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        safe_prompt = escape(prompt[:220])
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{variant.width}" height="{variant.height}" viewBox="0 0 {variant.width} {variant.height}">
  <rect width="100%" height="100%" fill="#0f172a"/>
  <rect x="40" y="40" width="{max(1, variant.width - 80)}" height="{max(1, variant.height - 80)}" rx="24" fill="#1e293b" stroke="#38bdf8" stroke-width="4"/>
  <text x="72" y="120" fill="#e2e8f0" font-family="Arial, sans-serif" font-size="44" font-weight="700">THE PM AI QUESTION</text>
  <text x="72" y="160" fill="#7dd3fc" font-family="Arial, sans-serif" font-size="24">Mock image placeholder, no API cost</text>
  <text x="72" y="190" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="28">{safe_prompt}</text>
</svg>""".encode("utf-8")


class ImagenProvider:
    extension = ".png"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
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
            http_options={"timeout": 120.0},
        )
        self.model = settings.imagen_model
        if self.model == "imagen-3.0-generate-002":
            self.model = "imagen-4.0-generate-001"

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
            fallback = _fallback_image_provider(self.settings)
            return fallback.create(prompt, variant)


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
            clients = [genai.Client(api_key=key, http_options={"timeout": 120.0}) for key in (settings.gemini_api_keys or (settings.gemini_api_key,))]
        else:
            self.generate_images_config = None
        self.settings = settings
        self.clients = clients
        self.model = settings.imagen_model
        if self.model in ("imagen-4.0-generate-001", "imagen-3.0-generate-002"):
            # Use the widely supported imagen-3.0-generate-002 model for developer keys
            self.model = "imagen-3.0-generate-002"

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
                continue
            client = self.clients[client_index]
            try:
                config = None
                if self.generate_images_config is not None:
                    config = self.generate_images_config(
                        number_of_images=1,
                        aspect_ratio=variant.aspect_ratio,
                        output_mime_type="image/png",
                    )
                try:
                    response = client.models.generate_images(
                        model=self.model,
                        prompt=prompt,
                        config=config,
                    )
                except Exception as model_exc:
                    msg = str(model_exc).lower()
                    if "not found" in msg or "not supported" in msg or "404" in msg:
                        if self.model != "imagen-3.0-generate-002":
                            import logging
                            logging.warning(f"Model {self.model} failed or is not found. Retrying with imagen-3.0-generate-002...")
                            response = client.models.generate_images(
                                model="imagen-3.0-generate-002",
                                prompt=prompt,
                                config=config,
                            )
                        else:
                            raise
                    else:
                        raise
                image_bytes = _response_image_bytes(response)
                if image_bytes is None:
                    raise RuntimeError("Gemini image generation did not return an image asset.")
                self.limiter.record_success(client_index)

                # Process the image to ensure high-fidelity Lanczos upscaling to the exact QHD dimension and save as lossless PNG
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(image_bytes))
                    if img.width < variant.width or img.height < variant.height:
                        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                        img = img.resize((variant.width, variant.height), resample=resample_filter)
                    out_buffer = io.BytesIO()
                    img.save(out_buffer, format="PNG")
                    image_bytes = out_buffer.getvalue()
                except Exception:
                    pass

                return image_bytes
            except Exception as exc:
                last_error = exc
                if not self.limiter.is_retryable(exc):
                    self.limiter.record_failure(client_index, exc, retryable=False)
                else:
                    self.limiter.record_failure(client_index, exc, retryable=True)
        if last_error is not None:
            import logging
            logging.warning(f"Gemini image generation exhausted all keys. Last error: {last_error}")
        return self.fallback_provider.create(prompt, variant)


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
        self.rollover = 0
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
        loaded_daily_budget = int(data.get("daily_budget", self.daily_budget))
        self.rollover = int(data.get("rollover", 0)) if loaded_daily_budget == self.daily_budget else 0
        self._reset_daily_if_needed()

    def _save_locked(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": self._now(),
            "usage_date": self._usage_date,
            "daily_budget": self.daily_budget,
            "rollover": self.rollover,
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
        total_limit = self.daily_budget + getattr(self, "rollover", 0)
        return max(total_limit - used, 0)

    def _reset_daily_if_needed(self) -> None:
        with self._lock:
            today = self._today()
            if self._usage_date == today:
                return
            
            yesterday_limit = self.daily_budget
            yesterday_generated = sum(state.daily_generated for state in self._states)
            unused = max(0, yesterday_limit - yesterday_generated)
            self.rollover = unused
            
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
    rollover = int(raw_state.get("rollover", 0))
    daily_remaining: int | None = (settings.gemini_image_daily_budget + rollover) if settings.gemini_image_daily_budget > 0 else None
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
        daily_remaining = max((settings.gemini_image_daily_budget + rollover) - daily_usage, 0)
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


def _redact_provider_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"([?&]key=)[^&\\s)'\"]+", r"\1[REDACTED]", message)
    message = re.sub(r"(Bearer\\s+)[A-Za-z0-9._\\-]+", r"\1[REDACTED]", message)
    return message


def _safe_fallback_provider_name(name: str) -> str:
    fallback = (name or "imagen").strip().lower()
    if fallback in {"gemini", "google", "google-genai"}:
        return "pollinations"
    if fallback == "auto":
        return "imagen"
    return fallback


def _fallback_image_provider(settings: Settings) -> ImageProvider:
    fallback_name = _safe_fallback_provider_name(settings.image_fallback_provider)
    candidates = [fallback_name]
    if fallback_name not in {"pollinations", "mock"}:
        candidates.append("pollinations")
    if "mock" not in candidates:
        candidates.append("mock")
    for provider_name in candidates:
        try:
            if provider_name == "mock":
                return MockImageProvider()
            if provider_name == "pollinations":
                return PollinationsImageProvider(settings)
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
                # We do not pass response_format explicitly to support a wider range of custom and legacy endpoints.
                # Standard OpenAI endpoints return a temporary URL by default, which we download securely.
                result = client.images.generate(
                    model=self.model,
                    prompt=prompt,
                    size=_openai_size_for(variant),
                    timeout=90,
                )
                image_base64 = getattr(result.data[0], "b64_json", None)
                if image_base64:
                    image_bytes = base64.b64decode(image_base64)
                else:
                    image_url = getattr(result.data[0], "url", None)
                    if not image_url:
                        raise RuntimeError("OpenAI image generation did not return an image asset.")
                    import requests
                    response = requests.get(image_url, timeout=90)
                    response.raise_for_status()
                    image_bytes = response.content

                # Process the image to ensure high-fidelity Lanczos upscaling to the exact QHD dimension and save as lossless PNG
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(image_bytes))
                    if img.width < variant.width or img.height < variant.height:
                        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                        img = img.resize((variant.width, variant.height), resample=resample_filter)
                    out_buffer = io.BytesIO()
                    img.save(out_buffer, format="PNG")
                    image_bytes = out_buffer.getvalue()
                except Exception:
                    pass

                return image_bytes
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"OpenAI image generation failed for all configured keys: {last_error}")


class NvidiaQwenImageProvider:
    """Qwen-Image provider with three-path fallback strategy:

    Path 1 (primary): Together.ai — api.together.xyz
      - $0.0058 per image, serverless, OpenAI-compatible
      - Requires TOGETHER_API_KEY from api.together.ai
      - Model: Qwen/Qwen-Image  →  response.data[0].b64_json

    Path 2: NVIDIA NIM cloud — nim.api.nvidia.com/v1/genai/qwen/qwen-image
      - Uses Visual GenAI NIM endpoint (artifacts[0].base64 response format)
      - Requires NVIDIA_API_KEY from build.nvidia.com/qwen/qwen-image

    Path 3 (fallback): HuggingFace fal-ai router
      - Uses HF_TOKEN with provider='fal-ai'
      - Requires HuggingFace Pro or paid fal-ai credits
    """

    extension = ".png"

    TOGETHER_BASE_URL = "https://api.together.xyz/v1"
    TOGETHER_MODEL    = "Qwen/Qwen-Image"
    NVIDIA_NIM_URL    = "https://nim.api.nvidia.com/v1/genai/qwen/qwen-image"
    HF_MODEL          = "Qwen/Qwen-Image"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.together_api_keys = self._dedupe_keys(
            list(getattr(settings, "together_api_keys", ()) or ([getattr(settings, "together_api_key", "")] if getattr(settings, "together_api_key", "") else []))
        )
        self.nvidia_api_keys = self._dedupe_keys(list(settings.nvidia_api_keys or ([settings.nvidia_api_key] if settings.nvidia_api_key else [])))
        self.hf_tokens = self._dedupe_keys(list(getattr(settings, "hf_token_keys", ()) or ([settings.hf_token] if settings.hf_token else [])))
        self.gemini_api_keys = self._dedupe_keys(list(settings.gemini_api_keys or ([settings.gemini_api_key] if settings.gemini_api_key else [])))
        nim_model = (settings.nvidia_image_model or "").strip().lower()
        self.nim_url = (
            self.NVIDIA_NIM_URL if nim_model in ("", "qwen/qwen-image", "qwen-image")
            else f"https://nim.api.nvidia.com/v1/genai/{nim_model}"
        )

    @staticmethod
    def _dedupe_keys(keys: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for key in keys:
            key = (key or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(key)
        return ordered

    # ── Path 1: Together.ai ────────────────────────────────────────────────
    def _try_together(self, prompt: str) -> bytes | None:
        """Generate via Together.ai ($0.0058/image, OpenAI-compatible API)."""
        if not self.together_api_keys:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        for idx, api_key in enumerate(self.together_api_keys, start=1):
            try:
                print(f"[Qwen/Together] trying key slot {idx}...")
                client = OpenAI(
                    api_key=api_key,
                    base_url=self.TOGETHER_BASE_URL,
                )
                response = client.images.generate(
                    model=self.TOGETHER_MODEL,
                    prompt=prompt,
                    n=1,
                    response_format="b64_json",
                )
                b64 = getattr(response.data[0], "b64_json", None)
                if b64:
                    return base64.b64decode(b64)
                url = getattr(response.data[0], "url", None)
                if url:
                    import urllib.request
                    with urllib.request.urlopen(url, timeout=60) as r:
                        return r.read()
            except Exception as exc:
                print(f"[Qwen/Together] key slot {idx} error: {exc}")
        return None

    # ── Path 2: NVIDIA NIM cloud ───────────────────────────────────────────
    def _try_nvidia_nim(self, prompt: str) -> bytes | None:
        """Call NVIDIA NIM cloud endpoint (artifacts[0].base64 format)."""
        if not self.nvidia_api_keys:
            return None
        import urllib.request, urllib.error, json as _json
        payload = {"prompt": prompt, "seed": 0}
        for idx, api_key in enumerate(self.nvidia_api_keys, start=1):
            req = urllib.request.Request(
                self.nim_url,
                data=_json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            try:
                print(f"[Qwen/NIM] trying key slot {idx}...")
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = _json.loads(res.read())
                    artifacts = data.get("artifacts", [])
                    if artifacts and artifacts[0].get("base64"):
                        return base64.b64decode(artifacts[0]["base64"])
                    img_data = (data.get("data") or [{}])[0]
                    if img_data.get("b64_json"):
                        return base64.b64decode(img_data["b64_json"])
                    if img_data.get("url"):
                        import urllib.request as _ur
                        with _ur.urlopen(img_data["url"], timeout=60) as r:
                            return r.read()
            except urllib.error.HTTPError as e:
                body = ""
                try: body = e.read().decode()[:200]
                except: pass
                print(f"[Qwen/NIM] key slot {idx} HTTP {e.code}: {body}")
            except Exception as exc:
                print(f"[Qwen/NIM] key slot {idx} error: {exc}")
        return None

    # ── Path 3: HuggingFace Space ──────────────────────────────────────────
    def _try_hf_space(self, prompt: str, variant: ImageVariant) -> bytes | None:
        """Call official FLUX.1-dev Space via gradio_client utilizing user's ZeroGPU Pro quota."""
        if not self.hf_tokens:
            return None
        try:
            from gradio_client import Client
        except ImportError:
            import subprocess, sys
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "gradio_client"])
                from gradio_client import Client
            except:
                return None

        w = max(256, min(2048, variant.width))
        h = max(256, min(2048, variant.height))
        
        for idx, token in enumerate(self.hf_tokens, start=1):
            try:
                print(f"[Qwen/HF-Space] trying slot {idx}...")
                client = Client("black-forest-labs/FLUX.1-dev", token=token)
                result = client.predict(
                    prompt=prompt,
                    seed=0,
                    randomize_seed=True,
                    width=w,
                    height=h,
                    guidance_scale=3.5,
                    num_inference_steps=24,
                    api_name="/infer"
                )
                if result:
                    image_path = result[0] if isinstance(result, tuple) else result
                    with open(image_path, "rb") as f:
                        print(f"✅ [Qwen/HF-Space] generated successfully using slot {idx}")
                        return f.read()
            except Exception as exc:
                print(f"[Qwen/HF-Space] slot {idx} failed: {exc}")
        return None

    # ── Path 2.5: Pollinations ─────────────────────────────────────────────
    def _try_pollinations(self, prompt: str, variant: ImageVariant) -> bytes | None:
        """Call Pollinations.ai free image generation API as fallback."""
        import urllib.parse, os, base64
        try:
            import requests
        except ImportError:
            return None
            
        encoded_prompt = urllib.parse.quote(prompt)
        request_width = min(1024, variant.width)
        request_height = min(1024, variant.height)

        p_key = getattr(self.settings, "pollinations_api_key", "") or os.environ.get("POLLINATIONS_API_KEY", "")
        if p_key:
            try:
                print("[Qwen/Pollinations] trying authenticated...")
                payload = {
                    "prompt": prompt,
                    "model": "flux",
                    "width": request_width,
                    "height": request_height,
                    "n": 1,
                    "response_format": "b64_json"
                }
                headers = {
                    "Authorization": f"Bearer {p_key}",
                    "Content-Type": "application/json"
                }
                r = requests.post("https://gen.pollinations.ai/v1/images/generations", headers=headers, json=payload, timeout=60)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    if data and "b64_json" in data[0]:
                        img_bytes = base64.b64decode(data[0]["b64_json"])
                        if len(img_bytes) > 5000:
                            print("✅ [Qwen/Pollinations] generated successfully (authenticated)")
                            return img_bytes
            except Exception as exc:
                print(f"[Qwen/Pollinations] authenticated failed: {exc}")

        for p_model in ["flux", "sana", "turbo"]:
            for seed in [42, 1337, 999]:
                try:
                    print(f"[Qwen/Pollinations] trying unauthenticated {p_model} seed={seed}...")
                    p_url = (
                        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                        f"?width={request_width}&height={request_height}"
                        f"&model={p_model}&nologo=true&seed={seed}"
                    )
                    r = requests.get(p_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200 and len(r.content) > 5000:
                        print(f"✅ [Qwen/Pollinations] generated successfully ({p_model})")
                        return r.content
                except Exception as exc:
                    print(f"[Qwen/Pollinations] unauthenticated {p_model} failed: {exc}")
        return None

    # ── Path 5: Gemini REST API ────────────────────────────────────────────
    def _try_gemini(self, prompt: str) -> bytes | None:
        """Call Gemini REST API as a reliable fallback."""
        if not self.gemini_api_keys:
            return None
        import requests, base64, os
        gemini_model = getattr(self.settings, "gemini_image_model", None) or "gemini-2.5-flash-image"
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
        
        for idx, key in enumerate(self.gemini_api_keys, start=1):
            try:
                print(f"[Qwen/Gemini] trying key slot {idx}...")
                r = requests.post(
                    gemini_url,
                    params={"key": key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
                    },
                    timeout=45,
                )
                if r.status_code == 200:
                    cands = r.json().get("candidates", [{}])
                    parts = cands[0].get("content", {}).get("parts", []) if cands else []
                    for part in parts:
                        raw = part.get("inlineData", {}).get("data", "")
                        if raw:
                            img_bytes = base64.b64decode(raw)
                            if img_bytes and len(img_bytes) > 5000:
                                print(f"✅ [Qwen/Gemini] generated successfully using slot {idx}")
                                return img_bytes
                else:
                    print(f"[Qwen/Gemini] slot {idx} HTTP {r.status_code}: {r.text[:200]}")
            except Exception as exc:
                print(f"[Qwen/Gemini] slot {idx} failed: {exc}")
        return None

    # ── Main entry ─────────────────────────────────────────────────────────
    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        # 1. NVIDIA NIM cloud (using all nvidia keys 1 by 1)
        print("[Qwen] Trying NVIDIA NIM...")
        image_bytes = self._try_nvidia_nim(prompt)

        # 2. Pollinations
        if image_bytes is None:
            print("[Qwen] NVIDIA NIM unavailable, trying Pollinations...")
            image_bytes = self._try_pollinations(prompt, variant)

        # 3. HuggingFace Space (utilizing ZeroGPU Pro quota)
        if image_bytes is None:
            print("[Qwen] Pollinations unavailable, trying HuggingFace Space...")
            image_bytes = self._try_hf_space(prompt, variant)

        # 4. Together.ai (as fallback if configured)
        if image_bytes is None and self.together_api_keys:
            print("[Qwen] HF Space unavailable, trying Together.ai...")
            image_bytes = self._try_together(prompt)

        # 5. Gemini REST API (reliable fallback using Gemini keys)
        if image_bytes is None:
            print("[Qwen] Together.ai unavailable, trying Gemini REST API...")
            image_bytes = self._try_gemini(prompt)

        if image_bytes is None:
            prompt_len = len((prompt or "").strip())
            prompt_head = (prompt or "").strip()[:220]
            raise RuntimeError(
                "Qwen-Image generation failed on all providers.\n"
                "  - NVIDIA NIM: check NVIDIA_API_KEY (nim.api.nvidia.com)\n"
                "  - Pollinations: check pollinations.ai status\n"
                "  - HuggingFace Space: check HF_TOKEN / ZeroGPU quota status\n"
                "  - Together.ai: set TOGETHER_API_KEY in .env (get free key at api.together.ai)\n"
                "  - Gemini REST API: check GEMINI_API_KEY / Google AI Studio quota\n"
                f"  - Prompt length: {prompt_len} chars\n"
                f"  - Prompt preview: {prompt_head}"
            )

        # Bicubic resize to exact requested dimensions
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            if img.width != variant.width or img.height != variant.height:
                resample_filter = getattr(Image, "Resampling", Image).BICUBIC
                img = img.resize((variant.width, variant.height), resample=resample_filter)
                out_buffer = io.BytesIO()
                img.save(out_buffer, format="PNG")
                image_bytes = out_buffer.getvalue()
        except Exception:
            pass

        return image_bytes


class PollinationsImageProvider:
    extension = ".png"

    def __init__(self, settings: Settings, skip_nvidia: bool = False) -> None:
        self.settings = settings
        self._skip_nvidia = skip_nvidia

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        import requests, time, urllib.parse, os, base64

        errors: dict[str, str] = {}

        # ── Tier 1: NVIDIA FLUX  (fastest, free 25 req/day per key) ──────────
        if not self._skip_nvidia:
            try:
                nvidia_provider = NvidiaFluxImageProvider(self.settings)
                # Call NVIDIA directly — don't use its own fallback (which loops back here)
                import urllib.request, urllib.error, json as _json
                flux_w, flux_h = nvidia_provider._map_flux_dimensions(variant.width, variant.height)
                for attempt in range(len(nvidia_provider.api_keys)):
                    api_key = nvidia_provider._next_key()
                    payload = {
                        "prompt": prompt, "seed": 0,
                        "steps": nvidia_provider.steps,
                        "width": flux_w, "height": flux_h,
                        **({"cfg_scale": 3.5} if "dev" in nvidia_provider.model_key else {}),
                    }
                    req = urllib.request.Request(
                        nvidia_provider.url,
                        data=_json.dumps(payload).encode(),
                        headers={"Authorization": f"Bearer {api_key}",
                                 "Content-Type": "application/json",
                                 "Accept": "application/json"},
                        method="POST",
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=120) as res:
                            data = _json.loads(res.read())
                            image_bytes = nvidia_provider._extract_image_bytes(data)
                            if image_bytes and len(image_bytes) > 5000:
                                print(f"\u2705 [Image] NVIDIA FLUX/{nvidia_provider.model_key}")
                                return self._process_image(image_bytes, variant)
                            else:
                                errors[f"nvidia/{nvidia_provider.model_key}"] = f"No image in response: {_json.dumps(data)[:200]}"
                    except urllib.error.HTTPError as e:
                        body = ""
                        try: body = e.read().decode()[:200]
                        except: pass
                        errors[f"nvidia/{nvidia_provider.model_key}/key{attempt}"] = f"HTTP {e.code}: {body}"
                        if e.code in (429, 503):
                            continue
                        break
                    except Exception as exc:
                        errors[f"nvidia/{nvidia_provider.model_key}"] = _redact_provider_error(exc)
                        break
            except Exception as exc:
                errors["nvidia_init"] = _redact_provider_error(exc)

        # ── Tier 2: Hugging Face Inference Providers (FLUX + Dreamshaper/SD) ──
        if self.settings.hf_token:
            try:
                from huggingface_hub import InferenceClient
            except Exception as exc:
                errors["hf_import"] = _redact_provider_error(exc)
            else:
                hf_models = [
                    "black-forest-labs/FLUX.1-schnell",
                    "black-forest-labs/FLUX.1-dev",
                    "Lykon/dreamshaper-8",
                    "runwayml/stable-diffusion-v1-5",
                ]
                client = InferenceClient(api_key=self.settings.hf_token)
                for model in hf_models:
                    try:
                        image = client.text_to_image(prompt=prompt, model=model)
                        if image is None:
                            continue
                        import io
                        from PIL import Image

                        buffer = io.BytesIO()
                        if hasattr(image, "save"):
                            image.save(buffer, format="PNG")
                        else:
                            Image.open(io.BytesIO(image)).save(buffer, format="PNG")
                        image_bytes = buffer.getvalue()
                        if len(image_bytes) > 5000:
                            print(f"\u2705 [Image] HF/{model}")
                            return self._process_image(image_bytes, variant)
                    except Exception as exc:
                        errors[f"hf/{model}"] = _redact_provider_error(exc)

        # Tier 2b: raw HTTP fallback for HF if the client is unavailable.
        hf_headers = {"Accept": "image/png", "X-Wait-For-Model": "true"}
        if self.settings.hf_token:
            hf_headers["Authorization"] = f"Bearer {self.settings.hf_token}"
        for free_model in ["black-forest-labs/FLUX.1-schnell", "Lykon/dreamshaper-8", "runwayml/stable-diffusion-v1-5"]:
            hf_url = f"https://router.huggingface.co/hf-inference/models/{free_model}"
            for attempt in range(3):
                try:
                    r = requests.post(hf_url, headers=hf_headers, json={"inputs": prompt}, timeout=120)
                    if r.status_code == 200 and len(r.content) > 5000:
                        print(f"\u2705 [Image] HF-HTTP/{free_model.split('/')[-1]}")
                        return self._process_image(r.content, variant)
                    if r.status_code in (503, 529):
                        time.sleep(min(20.0, 5.0 * (attempt + 1)))
                        continue
                    break
                except Exception as exc:
                    errors[f"hf_http/{free_model}"] = _redact_provider_error(exc)
                    break

        # ── Tier 3: Pollinations.ai  (free, throttled on some IPs) ────────────
        encoded_prompt = urllib.parse.quote(prompt)
        request_width = min(1024, variant.width)
        request_height = min(1024, variant.height)
        
        # Try authenticated OpenAI-compatible Pollinations API if key is present
        p_key = getattr(self.settings, "pollinations_api_key", None) or os.environ.get("POLLINATIONS_API_KEY", "")
        if p_key:
            try:
                payload = {
                    "prompt": prompt,
                    "model": "flux",
                    "width": request_width,
                    "height": request_height,
                    "n": 1,
                    "response_format": "b64_json"
                }
                headers = {
                    "Authorization": f"Bearer {p_key}",
                    "Content-Type": "application/json"
                }
                r = requests.post("https://gen.pollinations.ai/v1/images/generations", headers=headers, json=payload, timeout=60)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    if data and "b64_json" in data[0]:
                        img_bytes = base64.b64decode(data[0]["b64_json"])
                        if len(img_bytes) > 5000:
                            print("✅ [Image] Pollinations (authenticated)")
                            return self._process_image(img_bytes, variant)
                else:
                    errors["pollinations_auth"] = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:
                errors["pollinations_auth"] = _redact_provider_error(exc)

        for p_model in ["flux", "sana", "turbo"]:
            for seed in [42, 1337, 999]:
                try:
                    p_url = (
                        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                        f"?width={request_width}&height={request_height}"
                        f"&model={p_model}&nologo=true&seed={seed}"
                    )
                    r = requests.get(p_url, timeout=60,
                                     headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200 and len(r.content) > 5000:
                        print(f"\u2705 [Image] Pollinations/{p_model} seed={seed}")
                        return self._process_image(r.content, variant)
                    if r.status_code == 402:
                        time.sleep(5)
                        break
                except Exception as exc:
                    errors[f"pollinations/{p_model}"] = _redact_provider_error(exc)

        # ── Tier 4: Gemini REST API  (last resort, can be slow) ──────────────
        gemini_slots = [
            "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
            "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6",
        ]
        gemini_model = (
            getattr(self.settings, "gemini_image_model", None)
            or "gemini-2.5-flash-image"
        )
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"/{gemini_model}:generateContent"
        )
        for slot in gemini_slots:
            key = os.environ.get(slot, "")
            if not key:
                continue
            try:
                r = requests.post(
                    gemini_url,
                    params={"key": key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
                    },
                    timeout=45,
                )
                if r.status_code == 200:
                    cands = r.json().get("candidates", [{}])
                    parts = cands[0].get("content", {}).get("parts", []) if cands else []
                    for part in parts:
                        raw = part.get("inlineData", {}).get("data", "")
                        if raw:
                            img_bytes = (
                                raw if isinstance(raw, bytes)
                                else base64.b64decode(raw)
                            )
                            if len(img_bytes) > 5000:
                                print(f"\u2705 [Image] Gemini/{gemini_model} ({slot})")
                                return self._process_image(img_bytes, variant)
                elif r.status_code == 429:
                    time.sleep(10)
                    continue
                elif r.status_code in (401, 403):
                    continue
            except Exception as exc:
                errors[f"gemini/{slot}"] = _redact_provider_error(exc)

        # ── Tier 5: SVG placeholder  (compilation never hard-crashes) ─────────────
        import logging
        logging.warning(
            f"All image providers failed for: {prompt[:80]!r}. Errors: {errors}"
        )
        return MockImageProvider().create(prompt, variant)

    def _create_placeholder_image(self, prompt: str, variant: ImageVariant) -> bytes:
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.new("RGB", (variant.width, variant.height), color="#1e293b")
            draw = ImageDraw.Draw(img)
            draw.text((40, 40), f"Asset Placeholder\nPrompt: {prompt[:60]}...", fill="#cbd5e1")
            out_buffer = io.BytesIO()
            img.save(out_buffer, format="PNG")
            return out_buffer.getvalue()
        except Exception:
            return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'

    def _process_image(self, image_bytes: bytes, variant: ImageVariant) -> bytes:
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            if img.width < variant.width or img.height < variant.height:
                resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                img = img.resize((variant.width, variant.height), resample=resample_filter)
            out_buffer = io.BytesIO()
            img.save(out_buffer, format="PNG")
            image_bytes = out_buffer.getvalue()
        except Exception:
            pass
        return image_bytes


class NvidiaFluxImageProvider:
    """FLUX image generation via NVIDIA's free cloud genai API.

    Available models (all FREE, ai.api.nvidia.com/v1/genai/):
      - flux.2-klein-4b  → 1.8s, steps=4  (FASTEST, default)
      - flux.1-schnell   → 2.2s, steps=4
      - flux.1-dev       → 4-10s, steps=20 (highest quality)

    Each key gets 25 free requests/day. Multiple keys are rotated automatically.
    Keys from: build.nvidia.com/black-forest-labs/<model> → Get API Key
    Response: {artifacts: [{base64: "...", seed: 0}]}
    """

    extension = ".jpg"

    FLUX_URLS = {
        "flux.2-klein-4b": ("https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b", 4),
        "flux.1-schnell":  ("https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell",  4),
        "flux.1-dev":      ("https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev",      20),
    }
    DEFAULT_MODEL = "flux.1-schnell"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_keys = list(settings.nvidia_api_keys or ([settings.nvidia_api_key] if settings.nvidia_api_key else []))
        # De-duplicate while preserving order
        seen = set()
        self.api_keys = [k for k in self.api_keys if k and not (k in seen or seen.add(k))]
        if not self.api_keys:
            raise ValueError("NVIDIA_API_KEY is required for IMAGE_PROVIDER=nvidia-flux")
        # Pick model from NVIDIA_IMAGE_MODEL env (e.g. 'flux.1-dev')
        model_key = (settings.nvidia_image_model or self.DEFAULT_MODEL).lower().strip()
        if model_key not in self.FLUX_URLS:
            # Try fuzzy match (e.g. 'schnell' → 'flux.1-schnell')
            for k in self.FLUX_URLS:
                if model_key in k:
                    model_key = k
                    break
            else:
                model_key = self.DEFAULT_MODEL
        self.url, self.steps = self.FLUX_URLS[model_key]
        self.model_key = model_key
        self._key_index = 0

    def _next_key(self) -> str:
        key = self.api_keys[self._key_index % len(self.api_keys)]
        self._key_index += 1
        return key

    def _map_flux_dimensions(self, width: int, height: int) -> tuple[int, int]:
        supported = [768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344]
        target_ratio = width / height
        best_w, best_h = 1024, 1024
        min_diff = float("inf")
        max_area = 0
        for w_candidate in supported:
            for h_candidate in supported:
                if w_candidate * h_candidate > 1050000:
                    continue
                ratio = w_candidate / h_candidate
                diff = abs(ratio - target_ratio)
                if diff < min_diff - 1e-4:
                    min_diff = diff
                    best_w = w_candidate
                    best_h = h_candidate
                    max_area = w_candidate * h_candidate
                elif abs(diff - min_diff) < 1e-4:
                    area = w_candidate * h_candidate
                    if area > max_area:
                        best_w = w_candidate
                        best_h = h_candidate
                        max_area = area
        return best_w, best_h

    def create(self, prompt: str, variant: ImageVariant) -> bytes:
        import urllib.request, urllib.error, json as _json
        last_error: Exception | None = None

        flux_w, flux_h = self._map_flux_dimensions(variant.width, variant.height)

        for attempt in range(len(self.api_keys)):
            api_key = self._next_key()
            payload = {
                "prompt": prompt,
                "seed": 0,
                "steps": self.steps,
                "width": flux_w,
                "height": flux_h,
                # cfg_scale only for dev model
                **({
                    "cfg_scale": 3.5,
                } if "dev" in self.model_key else {}),
            }
            req = urllib.request.Request(
                self.url,
                data=_json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = _json.loads(res.read())
                    image_bytes = self._extract_image_bytes(data)
                    if image_bytes is None:
                        raise RuntimeError(f"No image in response: {list(data.keys())} -> {_json.dumps(data)}")

                    # Resize to exact dimensions if needed
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(image_bytes))
                        if img.width != variant.width or img.height != variant.height:
                            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                            img = img.resize((variant.width, variant.height), resample=resample_filter)
                            out_buffer = io.BytesIO()
                            img.save(out_buffer, format="JPEG", quality=95)
                            image_bytes = out_buffer.getvalue()
                    except Exception:
                        pass

                    return image_bytes
            except urllib.error.HTTPError as e:
                body = ""
                try: body = e.read().decode()[:200]
                except: pass
                last_error = RuntimeError(f"HTTP {e.code}: {body}")
                if e.code in (429, 503):  # rate limit — try next key
                    continue
                break
            except Exception as exc:
                last_error = exc
                break

        import logging
        logging.warning(f"FLUX ({self.model_key}) generation failed: {last_error}. Falling back to PollinationsImageProvider.")
        try:
            return PollinationsImageProvider(self.settings, skip_nvidia=True).create(prompt, variant)
        except Exception as fallback_exc:
            raise RuntimeError(f"FLUX ({self.model_key}) generation failed and fallback also failed: {fallback_exc}") from last_error

    def _extract_image_bytes(self, data: object) -> bytes | None:
        if not isinstance(data, dict):
            return None

        def _decode_candidate(candidate: object) -> bytes | None:
            if candidate is None:
                return None
            if isinstance(candidate, bytes):
                return candidate if candidate else None
            if isinstance(candidate, str):
                if not candidate.strip():
                    return None
                if candidate.startswith("data:image/") and "base64," in candidate:
                    candidate = candidate.split("base64,", 1)[1]
                try:
                    decoded = base64.b64decode(candidate)
                    return decoded if decoded else None
                except Exception:
                    return None
            if isinstance(candidate, dict):
                for key in ("base64", "b64_json", "image", "image_base64", "base64_image"):
                    decoded = _decode_candidate(candidate.get(key))
                    if decoded is not None:
                        return decoded
                url = candidate.get("url")
                if isinstance(url, str) and url:
                    try:
                        import urllib.request
                        with urllib.request.urlopen(url, timeout=60) as r:
                            return r.read()
                    except Exception:
                        return None
            return None

        for key in ("artifacts", "data", "images", "output"):
            items = data.get(key)
            if isinstance(items, list):
                for item in items:
                    decoded = _decode_candidate(item)
                    if decoded is not None:
                        return decoded
            else:
                decoded = _decode_candidate(items)
                if decoded is not None:
                    return decoded

        for key in ("base64", "b64_json", "image", "image_base64", "base64_image"):
            decoded = _decode_candidate(data.get(key))
            if decoded is not None:
                return decoded

        return None


def image_provider(settings: Settings) -> ImageProvider:
    provider_name = _resolved_image_provider_name(settings)
    if provider_name == "mock":
        return MockImageProvider()
    if provider_name in {"free-ai", "pollinations"}:
        return PollinationsImageProvider(settings)
    if provider_name in {"flux", "nvidia-flux", "flux-dev", "flux-schnell"}:
        return NvidiaFluxImageProvider(settings)
    if provider_name == "imagen":
        return ImagenProvider(settings)
    if provider_name == "gemini":
        if not settings.gemini_api_key and not settings.gcp_project_id:
            return MockImageProvider()
        return GeminiImageProvider(settings)
    if provider_name in {"openai", "chatgpt", "gpt-image"}:
        return OpenAIImageProvider(settings)
    if provider_name in {"nvidia", "qwen", "nvidia-qwen"}:
        return NvidiaQwenImageProvider(settings)
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
    max_dimension: int = 4096,
    max_bytes: int = 5 * 1024 * 1024,
    request_delay_seconds: float = 0.0,
) -> list[str]:
    files: list[str] = []
    batch_provider = provider
    budget_exhausted_fallback = False
    if isinstance(provider, GeminiImageProvider):
        plan = gemini_image_package_plan(
            provider.settings,
            packages_requested=1,
        )
        if plan["recommended_provider"] != "gemini":
            batch_provider = provider.fallback_provider
            budget_exhausted_fallback = True
        else:
            try:
                provider.ensure_capacity(len(VARIANTS))
            except RuntimeError as exc:
                if _is_budget_exhausted(exc):
                    batch_provider = provider.fallback_provider
                    budget_exhausted_fallback = True
                else:
                    raise

    if budget_exhausted_fallback:
        import os
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            try:
                from content_pipeline.bots.telegram import send_telegram_message
                send_telegram_message(bot_token, chat_id, "⚠️ Daily Gemini Image budget (90 images) hit! Swapping to free Pollinations (Flux) engine.")
            except Exception:
                pass

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
    if len(image_bytes) >= 24 and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        if image_bytes[12:16] == b"IHDR":
            width = struct.unpack(">I", image_bytes[16:20])[0]
            height = struct.unpack(">I", image_bytes[20:24])[0]
            return width, height
    # Fallback to Pillow (PIL) for other formats (e.g. JPEGs returned from Pollinations)
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(image_bytes))
        return img.width, img.height
    except Exception:
        raise ValueError("Image bytes were not valid and could not be parsed.")


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
        return "1792x1024"
    if variant.aspect_ratio == "9:16":
        return "1024x1792"
    return "1024x1024"


def _prompt_field(prompt: str, field: str) -> str:
    pattern = rf'{re.escape(field)}:\s*"?([^"\n]+)"?'
    match = re.search(pattern, prompt, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _prompt_topic(prompt: str) -> str:
    match = re.search(r"Topic:\s*([^\n]+)", prompt, flags=re.IGNORECASE)
    return match.group(1).strip().upper() if match else ""


def _prompt_concepts(prompt: str) -> list[str]:
    match = re.search(r'Renderer-only concepts:\s*"([^"\n]+)"', prompt, flags=re.IGNORECASE)
    if match:
        return [c.strip() for c in match.group(1).split(",")]

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
