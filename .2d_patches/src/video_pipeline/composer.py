from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def stitch_scene_segments_procedurally(input_dir: str, output_file: str) -> None:
    """
    Shadow stitcher that filters macOS AppleDouble sidecar files and only
    concatenates real scene MP4 segments.

    This keeps the external pipeline stable without changing the upstream
    composer implementation directly.
    """
    scene_dir = Path(input_dir)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    candidates = []
    for path in sorted(scene_dir.glob("*.mp4")):
        if path.name.startswith("._"):
            continue
        if path.stat().st_size <= 0:
            continue
        candidates.append(path)

    if not candidates:
        raise FileNotFoundError(f"No valid scene segments found in {scene_dir}")

    concat_list = scene_dir / "concat_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{path.resolve().as_posix()}'" for path in candidates) + "\n",
        encoding="utf-8",
    )

    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        subprocess.run(ffmpeg_command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"FFmpeg stitching failed: {error.stderr}") from error
    finally:
        if concat_list.exists():
            concat_list.unlink()
