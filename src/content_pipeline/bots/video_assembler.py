"""
video_assembler.py
==================
Stitches multiple video clips into a single long-form video using ffmpeg.
Applies smooth crossfade transitions between clips.
Audio mixing is wired but kept aside until audio pipeline is ready.

Usage:
    from content_pipeline.bots.video_assembler import VideoAssembler

    assembler = VideoAssembler()
    output = assembler.assemble(
        clip_paths=[Path("clip_01.mp4"), Path("clip_02.mp4"), Path("clip_03.mp4")],
        output_path=Path("output/final_30s_video.mp4"),
        crossfade_seconds=0.5,
    )
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# ffmpeg discovery — uses imageio_ffmpeg (bundled) or system ffmpeg
# ---------------------------------------------------------------------------

def _find_ffmpeg() -> str:
    """Find ffmpeg executable. Raises RuntimeError if not found."""
    # Try imageio_ffmpeg first (bundled with ComfyUI environment)
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe:
            return exe
    except ImportError:
        pass

    # Try system ffmpeg
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # Try ComfyUI embedded ffmpeg
    embedded = Path(r"C:\ComfyUI\python_embeded\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe")
    if embedded.exists():
        return str(embedded)

    raise RuntimeError(
        "ffmpeg not found. Install imageio_ffmpeg or add ffmpeg to PATH. "
        "Try: pip install imageio-ffmpeg"
    )


class VideoAssembler:
    """
    Stitches multiple MP4 clips into a single long-form video.

    Strategy:
    - Uses ffmpeg concat demuxer for lossless stitch (fastest, no re-encode)
    - Optionally applies xfade crossfade transitions between clips
    - Output is H.264 MP4 at 1920x1080, ready for YouTube upload

    Audio:
    - Wired but PARKED — audio_path parameter is accepted but not active yet
    - Will be activated when audio pipeline is stable
    """

    def assemble(
        self,
        clip_paths: list[Path],
        output_path: Path,
        crossfade_seconds: float = 0.5,
        audio_path: Optional[Path] = None,   # PARKED — audio pipeline coming soon
        target_resolution: str = "1920x1080",
    ) -> Path:
        """
        Stitch multiple video clips into one output video.

        Args:
            clip_paths:          List of .mp4 clip paths in order.
            output_path:         Destination for the final assembled video.
            crossfade_seconds:   Duration of crossfade between clips (0 = hard cut).
            audio_path:          (PARKED) Future: path to narration/music audio.
            target_resolution:   Output resolution (default 1920x1080).

        Returns:
            Path to the assembled output video.
        """
        if not clip_paths:
            raise ValueError("No clip paths provided to VideoAssembler.")
        if len(clip_paths) == 1:
            # Nothing to stitch — just copy the single clip
            logging.info("[VideoAssembler] Only 1 clip — copying directly to output.")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(clip_paths[0], output_path)
            return output_path

        ffmpeg = _find_ffmpeg()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logging.info(
            f"[VideoAssembler] Assembling {len(clip_paths)} clips "
            f"into {output_path.name} (crossfade={crossfade_seconds}s)"
        )

        if crossfade_seconds > 0:
            return self._assemble_with_crossfade(
                ffmpeg, clip_paths, output_path, crossfade_seconds, target_resolution
            )
        else:
            return self._assemble_concat(ffmpeg, clip_paths, output_path, target_resolution)

    def _assemble_concat(
        self,
        ffmpeg: str,
        clip_paths: list[Path],
        output_path: Path,
        target_resolution: str,
    ) -> Path:
        """
        Fast hard-cut assembly using ffmpeg concat demuxer.
        All clips must be the same resolution and codec.
        """
        w, h = target_resolution.split("x")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            concat_file = Path(f.name)
            for clip in clip_paths:
                f.write(f"file '{clip.as_posix()}'\n")

        try:
            cmd = [
                ffmpeg, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-vf", f"scale={w}:{h}:flags=lanczos",
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",                          # No audio (parked)
                str(output_path),
            ]
            logging.info(f"[VideoAssembler] Running concat: {' '.join(cmd[:6])}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr[-1000:]}")
        finally:
            concat_file.unlink(missing_ok=True)

        logging.info(f"[VideoAssembler] Assembled video saved: {output_path}")
        return output_path

    def _assemble_with_crossfade(
        self,
        ffmpeg: str,
        clip_paths: list[Path],
        output_path: Path,
        crossfade_seconds: float,
        target_resolution: str,
    ) -> Path:
        """
        Smooth crossfade assembly using ffmpeg xfade filter.

        Strategy: Build a filter_complex chain that crossfades each pair of clips.
        For N clips: we need N-1 xfade transitions.
        """
        w, h = target_resolution.split("x")
        n = len(clip_paths)

        # Collect clip durations
        clip_durations = []
        for clip in clip_paths:
            dur = self._get_clip_duration(ffmpeg, clip)
            clip_durations.append(dur)
            logging.info(f"[VideoAssembler] Clip {clip.name}: {dur:.2f}s")

        # Build ffmpeg command
        cmd = [ffmpeg, "-y"]

        # Input files (each clip normalized to target resolution first)
        for clip in clip_paths:
            cmd += ["-i", str(clip)]

        # Build filter_complex for xfade chain
        # Each xfade needs: offset = sum of previous clip durations - crossfade overlap
        filter_parts = []
        labels = []

        # First: normalize all clips to the same resolution and fps
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]scale={w}:{h}:flags=lanczos,fps=24,format=yuv420p[v{i}]"
            )

        # Then: chain xfade transitions
        cumulative_offset = 0.0
        prev_label = "v0"
        for i in range(1, n):
            cumulative_offset += clip_durations[i - 1] - crossfade_seconds
            out_label = f"xf{i}" if i < n - 1 else "vout"
            filter_parts.append(
                f"[{prev_label}][v{i}]xfade="
                f"transition=dissolve:"
                f"duration={crossfade_seconds}:"
                f"offset={cumulative_offset:.3f}"
                f"[{out_label}]"
            )
            prev_label = out_label

        filter_complex = ";".join(filter_parts)

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",          # No audio (parked)
            str(output_path),
        ]

        logging.info(f"[VideoAssembler] Running xfade assembly for {n} clips...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if result.returncode != 0:
                logging.warning(
                    f"[VideoAssembler] xfade failed, falling back to concat.\n"
                    f"Error: {result.stderr[-500:]}"
                )
                return self._assemble_concat(ffmpeg, clip_paths, output_path, target_resolution)
        except subprocess.TimeoutExpired:
            logging.warning("[VideoAssembler] xfade timed out, falling back to concat.")
            return self._assemble_concat(ffmpeg, clip_paths, output_path, target_resolution)

        logging.info(f"[VideoAssembler] Crossfade assembled video saved: {output_path}")
        return output_path

    def _get_clip_duration(self, ffmpeg: str, clip_path: Path) -> float:
        """
        Get the duration of a video clip in seconds using ffprobe.
        Falls back to 6.0s if ffprobe is not available.
        """
        ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
        if not Path(ffprobe).exists():
            ffprobe_sys = shutil.which("ffprobe")
            if ffprobe_sys:
                ffprobe = ffprobe_sys
            else:
                return 6.0  # Safe default

        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(clip_path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logging.warning(f"[VideoAssembler] ffprobe failed for {clip_path.name}: {e}")

        return 6.0  # Safe default
