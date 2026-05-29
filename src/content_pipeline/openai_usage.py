from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIUsageSummary:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    remaining_context_tokens: int | None
    estimated_cost_usd: float | None


def summarize_openai_usage(
    response: Any,
    *,
    context_window_tokens: int | None = None,
    prompt_rate_per_1m: float | None = None,
    completion_rate_per_1m: float | None = None,
) -> OpenAIUsageSummary:
    """Normalize token usage across OpenAI response objects."""
    usage = getattr(response, "usage", None)
    prompt_tokens = _coerce_int(
        getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
    )
    completion_tokens = _coerce_int(
        getattr(usage, "completion_tokens", None)
        or getattr(usage, "output_tokens", None)
    )
    total_tokens = _coerce_int(
        getattr(usage, "total_tokens", None) or (prompt_tokens + completion_tokens)
    )

    remaining_context_tokens: int | None = None
    if context_window_tokens is not None:
        remaining_context_tokens = max(context_window_tokens - total_tokens, 0)

    estimated_cost_usd: float | None = None
    if prompt_rate_per_1m is not None and completion_rate_per_1m is not None:
        estimated_cost_usd = (
            (prompt_tokens * prompt_rate_per_1m)
            + (completion_tokens * completion_rate_per_1m)
        ) / 1_000_000

    return OpenAIUsageSummary(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        remaining_context_tokens=remaining_context_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )


def log_openai_usage(
    response: Any,
    *,
    label: str = "OpenAI usage",
    context_window_tokens: int | None = None,
    prompt_rate_per_1m: float | None = None,
    completion_rate_per_1m: float | None = None,
) -> OpenAIUsageSummary:
    """Log a concise token usage summary and return the normalized values."""
    summary = summarize_openai_usage(
        response,
        context_window_tokens=context_window_tokens,
        prompt_rate_per_1m=prompt_rate_per_1m,
        completion_rate_per_1m=completion_rate_per_1m,
    )

    parts = [
        f"{label}: prompt={summary.prompt_tokens}",
        f"completion={summary.completion_tokens}",
        f"total={summary.total_tokens}",
    ]
    if summary.remaining_context_tokens is not None:
        parts.append(f"remaining_context={summary.remaining_context_tokens}")
    if summary.estimated_cost_usd is not None:
        parts.append(f"estimated_cost=${summary.estimated_cost_usd:.5f}")

    log.info(" | ".join(parts))
    return summary


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)
