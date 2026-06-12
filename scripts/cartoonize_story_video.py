from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from generate_nvidia_story_video import (
    _concat_segments,
    _duration_seconds,
    _mux_audio,
    _render_zoom_segment,
)


FINAL_SIZE = (2048, 1152)


def _cartoonize(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGB").resize(FINAL_SIZE, Image.Resampling.LANCZOS)
    base = img.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.SMOOTH_MORE)
    base = ImageEnhance.Color(base).enhance(1.28)
    base = ImageEnhance.Contrast(base).enhance(1.10)
    base = ImageEnhance.Sharpness(base).enhance(1.12)
    base = ImageOps.posterize(base, 6)

    edges = img.filter(ImageFilter.FIND_EDGES).convert("L")
    edges = ImageOps.invert(edges)
    edges = ImageEnhance.Contrast(edges).enhance(1.55)
    edge_rgb = Image.merge("RGB", (edges, edges, edges))

    output = ImageChops.multiply(base, edge_rgb)
    dst.parent.mkdir(parents=True, exist_ok=True)
    output.save(dst, format="PNG", optimize=True)


def main() -> int:
    root = Path("output/youtube_assets/deepak_jugnu_nvidia_cartoonized_continuity")
    image_dir = root / "images"
    segment_dir = root / "segments"
    image_dir.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)

    audio = Path("output/final_story_audio/FINAL_Deepak_Aur_Jugnu_Hindi_Story_Audible_Music.mp3")
    source_root = Path("output/youtube_assets/deepak_jugnu_nvidia_consistent_v4/images_selected")
    sequence = [
        ("01_key6_walk_with_calf", source_root / "02_walk_with_calf_key6_2k.png", 6, "in"),
        ("02_key2_wide_path", source_root / "01_wide_path_key2_2k.png", 2, "out"),
        ("03_key2_hand_hold", source_root / "03_hand_hold_key2_2k.png", 2, "in"),
        ("04_key6_calf_help", source_root / "04_calf_help_key6_2k.png", 6, "out"),
        ("05_key6_walk_detail", source_root / "02_walk_with_calf_key6_2k.png", 6, "in"),
        ("06_key6_calf_close", source_root / "04_calf_help_key6_2k.png", 6, "out"),
    ]

    images: list[dict[str, object]] = []
    for index, (slug, src, original_slot, zoom) in enumerate(sequence, start=1):
        dst = image_dir / f"{index:02d}_{slug}_cartoon_2k.png"
        _cartoonize(src, dst)
        images.append(
            {
                "path": str(dst),
                "source": str(src),
                "original_key_slot": original_slot,
                "zoom": zoom,
            }
        )

    audio_duration = _duration_seconds(audio)
    segment_duration = audio_duration / len(images)
    segments: list[Path] = []
    for index, image in enumerate(images, start=1):
        zoom = str(image["zoom"])
        segment = segment_dir / f"segment_{index:02d}_{zoom}.mp4"
        _render_zoom_segment(
            Path(str(image["path"])),
            segment,
            duration=segment_duration,
            zoom_mode=zoom,
        )
        segments.append(segment)

    silent = root / "Deepak_Aur_Jugnu_NVIDIA_Cartoon_Continuity_2K_silent.mp4"
    final = root / "Deepak_Aur_Jugnu_NVIDIA_Cartoon_Continuity_2K_KenBurns.mp4"
    _concat_segments(segments, silent)
    _mux_audio(silent, audio, final)

    manifest = {
        "mode": "local-cartoonized-from-continuity-safe-nvidia-images",
        "audio": str(audio),
        "audio_duration_seconds": audio_duration,
        "output_video": str(final),
        "requested_first_key_slot": 6,
        "images": images,
        "segments": [str(path) for path in segments],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
