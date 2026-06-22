from __future__ import annotations

import argparse
import base64
import os
import urllib.parse
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from content_pipeline.config import Settings


@dataclass(frozen=True)
class GeneratedAsset:
    label: str
    provider: str
    actual_provider: str
    key_name: str
    path: Path
    status: str
    error: str = ""


DEFAULT_PROMPT = (
    "A warm storybook illustration of an elderly grandmother with gray hair in a bun, "
    "standing outside a rustic stone cottage with a thatched roof in a sunny countryside. "
    "She is gently sorting a basket of fresh produce into burlap sacks on the doorstep. "
    "The scene has ivy climbing the walls, blooming flowers, a winding dirt path, soft "
    "golden morning light, and a whimsical hand-drawn watercolor-and-pencil texture. "
    "Highly detailed, charming, cozy children's book style, no text, no watermark."
)

GEMINI_SLOTS = [
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_2",
    "GEMINI_API_KEY_3",
    "GEMINI_API_KEY_4",
    "GEMINI_API_KEY_5",
    "GEMINI_API_KEY_6",
]


def _ensure_square_2k(image_bytes: bytes, size: int) -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    if img.width != size or img.height != size:
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize((size, size), resample=resample_filter)
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _save_png(path: Path, image_bytes: bytes, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_ensure_square_2k(image_bytes, size))
    return path


def _gemini_image_bytes(key: str, prompt: str, model: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(
        url,
        params={"key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        },
        timeout=90,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:220]}")
    candidates = response.json().get("candidates", [])
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts", [])
        for part in parts:
            raw = part.get("inlineData", {}).get("data")
            if not raw:
                continue
            return raw if isinstance(raw, bytes) else base64.b64decode(raw)
    raise RuntimeError("Gemini response did not include image bytes.")


def _nvidia_image_bytes(key: str, prompt: str, url: str, steps: int, width: int, height: int) -> bytes:
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "prompt": prompt,
            "seed": 0,
            "steps": steps,
            "width": width,
            "height": height,
        },
        timeout=120,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:220]}")
    data = response.json()
    artifacts = data.get("artifacts", [])
    if artifacts and artifacts[0].get("base64"):
        return base64.b64decode(artifacts[0]["base64"])
    raise RuntimeError(f"NVIDIA response did not include image bytes: {list(data.keys())}")


def _pollinations_image_bytes(prompt: str, width: int, height: int) -> bytes:
    encoded_prompt = urllib.parse.quote(prompt)
    for model in ("flux", "sana", "turbo"):
        for seed in (42, 1337, 999):
            response = requests.get(
                f"https://image.pollinations.ai/prompt/{encoded_prompt}",
                params={
                    "width": width,
                    "height": height,
                    "model": model,
                    "seed": seed,
                    "nologo": "true",
                    "private": "true",
                },
                timeout=120,
            )
            if response.status_code == 200 and response.content:
                return response.content
    raise RuntimeError("Pollinations did not return image bytes.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a small gallery of free-key image tests.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output-dir", type=Path, default=Path("output/free_key_gallery"))
    parser.add_argument("--size", type=int, default=2048)
    args = parser.parse_args()

    Settings.from_environment(Path.cwd())
    args.output_dir.mkdir(parents=True, exist_ok=True)

    items: list[GeneratedAsset] = []
    for index, slot_name in enumerate(GEMINI_SLOTS, start=1):
        key = os.getenv(slot_name, "").strip()
        if not key:
            items.append(
                GeneratedAsset(
                    label=f"gemini-{index}",
                    provider="gemini",
                    actual_provider="gemini",
                    key_name=slot_name,
                    path=args.output_dir / f"{slot_name.lower()}.png",
                    status="missing",
                    error="missing key",
                )
            )
            continue
        path = args.output_dir / f"{slot_name.lower()}.png"
        try:
            image_bytes = _gemini_image_bytes(key, args.prompt, "gemini-2.5-flash-image")
            _save_png(path, image_bytes, args.size)
            items.append(
                GeneratedAsset(
                    label=f"gemini-{index}",
                    provider="gemini",
                    actual_provider="gemini",
                    key_name=slot_name,
                    path=path,
                    status="created",
                )
            )
        except Exception as exc:
            items.append(
                GeneratedAsset(
                    label=f"gemini-{index}",
                    provider="gemini",
                    actual_provider="gemini",
                    key_name=slot_name,
                    path=path,
                    status="failed",
                    error=str(exc)[:220],
                )
            )

    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if nvidia_key:
        path = args.output_dir / "nvidia_flux.png"
        try:
            image_bytes = _nvidia_image_bytes(
                nvidia_key,
                args.prompt,
                "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b",
                4,
                args.size,
                args.size,
            )
            _save_png(path, image_bytes, args.size)
            items.append(
                GeneratedAsset(
                    label="nvidia",
                    provider="nvidia",
                    actual_provider="nvidia",
                    key_name="NVIDIA_API_KEY",
                    path=path,
                    status="created",
                )
            )
        except Exception as exc:
            items.append(
                GeneratedAsset(
                    label="nvidia",
                    provider="nvidia",
                    actual_provider="nvidia",
                    key_name="NVIDIA_API_KEY",
                    path=path,
                    status="failed",
                    error=str(exc)[:220],
                )
            )

    try:
        path = args.output_dir / "pollinations.png"
        image_bytes = _pollinations_image_bytes(args.prompt, args.size, args.size)
        _save_png(path, image_bytes, args.size)
        items.append(
            GeneratedAsset(
                label="pollinations",
                provider="pollinations",
                actual_provider="pollinations",
                key_name="free",
                path=path,
                status="created",
            )
        )
    except Exception as exc:
        items.append(
            GeneratedAsset(
                label="pollinations",
                provider="pollinations",
                actual_provider="pollinations",
                key_name="free",
                path=args.output_dir / "pollinations.png",
                status="failed",
                error=str(exc)[:220],
            )
        )

    manifest = [
        {
            "label": item.label,
            "provider": item.provider,
            "actual_provider": item.actual_provider,
            "key_name": item.key_name,
            "path": str(item.path),
            "status": item.status,
            "error": item.error,
        }
        for item in items
    ]
    (args.output_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(__import__("json").dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
