from __future__ import annotations

import argparse
import base64
import json
import math
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from content_pipeline.config import Settings


NVIDIA_FLUX_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"
FINAL_WIDTH = 2048
FINAL_HEIGHT = 1152
FPS = 30


@dataclass(frozen=True)
class ShotSpec:
    slug: str
    title: str
    prompt: str
    seed: int
    zoom: str


def _extract_image_bytes(data: object) -> bytes | None:
    if not isinstance(data, dict):
        return None

    def decode_candidate(candidate: object) -> bytes | None:
        if isinstance(candidate, str) and candidate.strip():
            if candidate.startswith("data:image/") and "base64," in candidate:
                candidate = candidate.split("base64,", 1)[1]
            try:
                decoded = base64.b64decode(candidate)
                return decoded if decoded else None
            except Exception:
                return None
        if isinstance(candidate, dict):
            for key in ("base64", "b64_json", "image", "image_base64", "base64_image"):
                decoded = decode_candidate(candidate.get(key))
                if decoded:
                    return decoded
        return None

    for key in ("artifacts", "data", "images", "output"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                decoded = decode_candidate(item)
                if decoded:
                    return decoded
        else:
            decoded = decode_candidate(value)
            if decoded:
                return decoded
    return None


def _nvidia_generate(
    api_key: str,
    prompt: str,
    *,
    seed: int,
    width: int,
    height: int,
) -> bytes:
    payload = {
        "prompt": prompt,
        "seed": seed,
        "steps": 4,
        "width": width,
        "height": height,
    }
    request = urllib.request.Request(
        NVIDIA_FLUX_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    image_bytes = _extract_image_bytes(data)
    if not image_bytes:
        raise RuntimeError(f"NVIDIA response had no image bytes: {list(data.keys())}")
    return image_bytes


def _save_2k_png(image_bytes: bytes, output_path: Path) -> None:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    if img.size != (FINAL_WIDTH, FINAL_HEIGHT):
        resample = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize((FINAL_WIDTH, FINAL_HEIGHT), resample=resample)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)


def _nvidia_key_slots_from_env(total_slots: int = 20) -> list[tuple[int, str]]:
    slots: list[tuple[int, str]] = []
    primary = os.getenv("NVIDIA_API_KEY", "").strip()
    if primary:
        slots.append((1, primary))
    for slot in range(2, total_slots + 1):
        key = os.getenv(f"NVIDIA_API_KEY_{slot}", "").strip()
        if key:
            slots.append((slot, key))
    if not slots:
        fallback = os.getenv("NVIDIA_NIM_API_KEY", "").strip()
        if fallback:
            slots.append((1, fallback))
    return slots


def _select_key_slots(
    configured_slots: list[tuple[int, str]],
    requested_slots_csv: str,
) -> list[tuple[int, str]]:
    if not requested_slots_csv.strip():
        return configured_slots

    by_slot = {slot: key for slot, key in configured_slots}
    requested_slots = [
        int(slot.strip())
        for slot in requested_slots_csv.split(",")
        if slot.strip()
    ]
    missing = [slot for slot in requested_slots if slot not in by_slot]
    if missing:
        raise RuntimeError(f"NVIDIA_API_KEY slots not configured: {missing}")
    return [(slot, by_slot[slot]) for slot in requested_slots]


def _generate_shot_with_key_pool(
    key_slots: list[tuple[int, str]],
    shot: ShotSpec,
    output_path: Path,
) -> dict[str, object]:
    last_error = ""
    request_sizes = [(FINAL_WIDTH, FINAL_HEIGHT), (1344, 768), (1216, 704), (1024, 576)]
    for size_index, (request_width, request_height) in enumerate(request_sizes):
        for pool_index, (original_slot, api_key) in enumerate(key_slots):
            try:
                image_bytes = _nvidia_generate(
                    api_key,
                    shot.prompt,
                    seed=shot.seed + size_index,
                    width=request_width,
                    height=request_height,
                )
                _save_2k_png(image_bytes, output_path)
                return {
                    "status": "created",
                    "provider": "nvidia-flux",
                    "model": "flux.2-klein-4b",
                    "key_pool_position": pool_index + 1,
                    "original_key_slot": original_slot,
                    "requested_size": [request_width, request_height],
                    "final_size": [FINAL_WIDTH, FINAL_HEIGHT],
                    "path": str(output_path),
                }
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8")[:220]
                except Exception:
                    pass
                last_error = f"HTTP {exc.code}: {body}"
                if exc.code in (401, 403):
                    break
                continue
            except Exception as exc:
                last_error = str(exc)[:220]
                continue
    return {
        "status": "failed",
        "provider": "nvidia-flux",
        "model": "flux.2-klein-4b",
        "error": last_error,
        "path": str(output_path),
    }


def _ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required.")
    return executable


def _duration_seconds(audio_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 72.0
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _render_zoom_segment(
    image_path: Path,
    output_path: Path,
    *,
    duration: float,
    zoom_mode: str,
) -> None:
    frames = max(1, int(math.ceil(duration * FPS)))
    if zoom_mode == "out":
        zoom_expr = f"if(eq(on,0),1.10,max(1.0,zoom-0.000055))"
    else:
        zoom_expr = f"min(1.10,1.0+on*0.000055)"
    zoompan = (
        f"zoompan=z='{zoom_expr}':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={FINAL_WIDTH}x{FINAL_HEIGHT}:fps={FPS},format=yuv420p"
    )
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            zoompan,
            "-frames:v",
            str(frames),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-an",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _concat_segments(segment_paths: list[Path], output_path: Path) -> None:
    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text(
        "".join(f"file '{segment.resolve()}'\n" for segment in segment_paths),
        encoding="utf-8",
    )
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    concat_file.unlink(missing_ok=True)


def _mux_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _shots() -> list[ShotSpec]:
    character_bible = (
        "Character lock: Deepak=8yo Indian boy, short black hair, sky-blue kurta, beige knee shorts, "
        "barefoot, shorts visible, never sari/girl/dress. Grandmother=elderly Indian woman, silver bun, purple sari, cream shawl. "
        "Cow calf=small brown-white baby cow, hooves, cow ears, bovine muzzle, compact body, short neck; no dog/puppy. "
    )
    shared = (
        "Outdoor kids animated film frame, rounded 3D cartoon look, full village background, no studio. "
        f"{character_bible}"
        "Rainy night Indian village, farms, green hills, golden fireflies, magical safe mood. "
        "Real scene, not book/page. No text, title, signs, logo, watermark, signature."
    )
    return [
        ShotSpec(
            "01_wide_path",
            "Wide village path",
            f"Wide horizontal scene. {shared} Deepak walks beside grandmother on winding muddy path; visible cow calf beside them, compact body. Fireflies light fields.",
            1101,
            "in",
        ),
        ShotSpec(
            "02_low_fireflies",
            "Low firefly angle",
            f"Low horizontal angle near glowing fireflies. {shared} Fireflies foreground; Deepak and grandmother walk mid-distance; visible cow calf beside them.",
            2202,
            "out",
        ),
        ShotSpec(
            "03_emotional_close",
            "Emotional close angle",
            f"Medium close scene. {shared} Deepak gently holds grandmother's hand; visible cow calf at their feet; caring faces in soft firefly light.",
            3303,
            "in",
        ),
        ShotSpec(
            "04_calf_reunion",
            "Calf reunion side angle",
            f"Side horizontal scene. {shared} Deepak comforts visible small brown-white cow calf near banyan tree; grandmother kneels. Calf short neck.",
            4404,
            "out",
        ),
        ShotSpec(
            "05_firefly_magic",
            "Firefly magic angle",
            f"High three-quarter scene. {shared} Deepak smiles as fireflies form glowing path; grandmother points; visible cow calf watches, compact body.",
            5505,
            "in",
        ),
        ShotSpec(
            "06_home_return",
            "Home return closing angle",
            f"Warm closing scene. {shared} Deepak, grandmother, and visible cow calf reach cozy village home; fireflies glow at doorway, happy ending.",
            6606,
            "out",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate NVIDIA 2K story images and Ken Burns YouTube video.")
    parser.add_argument(
        "--audio",
        type=Path,
        default=Path("output/final_story_audio/FINAL_Deepak_Aur_Jugnu_Hindi_Story_Audible_Music.mp3"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/youtube_assets/deepak_jugnu_nvidia"),
    )
    parser.add_argument(
        "--key-slots",
        default="",
        help="Comma-separated original NVIDIA_API_KEY slots to use as a retry pool, for example 2,6.",
    )
    parser.add_argument(
        "--shot-key-slots",
        default="",
        help="Comma-separated original NVIDIA_API_KEY slots to use per shot, for example 6,2,3,4,5,6.",
    )
    args = parser.parse_args()

    Settings.from_environment(Path.cwd())
    configured_key_slots = _nvidia_key_slots_from_env()
    retry_key_slots = _select_key_slots(configured_key_slots, args.key_slots)
    per_shot_key_slots = _select_key_slots(configured_key_slots, args.shot_key_slots)
    if not retry_key_slots:
        raise RuntimeError("No NVIDIA_API_KEY slots are configured.")
    if args.shot_key_slots.strip() and len(per_shot_key_slots) != len(_shots()):
        raise RuntimeError("--shot-key-slots must provide exactly one slot per shot.")
    if not args.audio.exists():
        raise FileNotFoundError(args.audio)

    root = args.output_dir
    image_dir = root / "images"
    segment_dir = root / "segments"
    root.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)

    image_results = []
    for index, shot in enumerate(_shots(), start=1):
        path = image_dir / f"{shot.slug}_2k.png"
        print(f"Generating NVIDIA image {index}: {shot.title}")
        key_slots_for_shot = [per_shot_key_slots[index - 1]] if args.shot_key_slots.strip() else retry_key_slots
        image_results.append(_generate_shot_with_key_pool(key_slots_for_shot, shot, path))

    failed = [result for result in image_results if result.get("status") != "created"]
    if failed:
        raise RuntimeError(f"NVIDIA image generation failed: {failed}")

    audio_duration = _duration_seconds(args.audio)
    segment_duration = audio_duration / len(image_results)
    segment_paths = []
    for index, (shot, result) in enumerate(zip(_shots(), image_results), start=1):
        segment_path = segment_dir / f"segment_{index:02d}_{shot.zoom}.mp4"
        print(f"Rendering slow zoom {shot.zoom}: {segment_path.name}")
        _render_zoom_segment(
            Path(str(result["path"])),
            segment_path,
            duration=segment_duration,
            zoom_mode=shot.zoom,
        )
        segment_paths.append(segment_path)

    silent_video = root / "Deepak_Aur_Jugnu_NVIDIA_2K_silent.mp4"
    final_video = root / "Deepak_Aur_Jugnu_NVIDIA_2K_KenBurns.mp4"
    _concat_segments(segment_paths, silent_video)
    _mux_audio(silent_video, args.audio, final_video)

    manifest = {
        "provider": "nvidia-flux",
        "model": "flux.2-klein-4b",
        "audio": str(args.audio),
        "audio_duration_seconds": audio_duration,
        "output_video": str(final_video),
        "requested_retry_key_slots": [slot for slot, _key in retry_key_slots],
        "requested_per_shot_key_slots": [slot for slot, _key in per_shot_key_slots]
        if args.shot_key_slots.strip()
        else [],
        "image_results": image_results,
        "segments": [str(path) for path in segment_paths],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
