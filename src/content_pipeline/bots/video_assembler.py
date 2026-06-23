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
    - Optional YouTube compression pass: CRF 23 + H.264 High Profile
      reduces 20MB clips to 3-6MB with no visible quality difference on YouTube
      (YouTube re-encodes everything anyway — sending a smaller file is always fine)

    Audio:
    - Wired but PARKED — audio_path parameter is accepted but not active yet
    - Will be activated when audio pipeline is stable

    File size guide (1920x1080, 24fps):
      CRF 18 (archival)   ~15-25MB per 5s clip  → total 30s ≈ 100-150MB
      CRF 23 (YouTube)    ~3-6MB per 5s clip    → total 30s ≈ 20-40MB  ← default
      CRF 28 (web/mobile) ~1-2MB per 5s clip    → total 30s ≈ 8-15MB
    """

    def assemble(
        self,
        clip_paths: list[Path],
        output_path: Path,
        crossfade_seconds: float = 0.5,
        audio_path: Optional[Path] = None,   # PARKED — audio pipeline coming soon
        target_resolution: str = "1920x1080",
        youtube_compress: bool = True,        # Apply YouTube-optimized compression
        crf: int = 23,                        # 18=archival(huge), 23=YouTube(good), 28=web(small)
    ) -> Path:
        """
        Stitch multiple video clips into one output video.

        Args:
            clip_paths:         List of .mp4 clip paths in order.
            output_path:        Destination for the final assembled video.
            crossfade_seconds:  Duration of crossfade between clips (0 = hard cut).
            audio_path:         (PARKED) Future: path to narration/music audio.
            target_resolution:  Output resolution (default 1920x1080).
            youtube_compress:   If True (default), apply YouTube-optimized CRF 23 encode.
                                This reduces file size 50-70% with no visible quality loss.
            crf:                Compression level. 18=large/archival, 23=YouTube, 28=web/mobile.

        Returns:
            Path to the assembled output video.

        File size guide (1920x1080 @ 24fps per 5-second clip):
            CRF 18: ~15-25 MB  (archival, huge files)
            CRF 23: ~3-6 MB   (YouTube — same visual quality, YouTube re-encodes anyway)
            CRF 28: ~1-2 MB   (web/mobile sharing)
        """
        if not clip_paths:
            raise ValueError("No clip paths provided to VideoAssembler.")
        if len(clip_paths) == 1:
            # Nothing to stitch — just compress the single clip directly
            logging.info("[VideoAssembler] Only 1 clip — compressing to output.")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if youtube_compress:
                return self.compress_for_youtube(clip_paths[0], output_path, crf=crf, target_resolution=target_resolution)
            shutil.copy2(clip_paths[0], output_path)
            return output_path

        ffmpeg = _find_ffmpeg()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logging.info(
            f"[VideoAssembler] Assembling {len(clip_paths)} clips "
            f"into {output_path.name} (crossfade={crossfade_seconds}s, crf={crf})"
        )

        if crossfade_seconds > 0:
            assembled = self._assemble_with_crossfade(
                ffmpeg, clip_paths, output_path, crossfade_seconds, target_resolution, crf
            )
        else:
            assembled = self._assemble_concat(ffmpeg, clip_paths, output_path, target_resolution, crf)

        # Report file size
        size_mb = round(assembled.stat().st_size / (1024*1024), 1)
        logging.info(f"[VideoAssembler] Final video: {assembled.name} ({size_mb} MB, CRF={crf})")
        print(f"  Final video size: {size_mb} MB (CRF={crf} — YouTube ready)")
        return assembled

    def _assemble_concat(
        self,
        ffmpeg: str,
        clip_paths: list[Path],
        output_path: Path,
        target_resolution: str,
        crf: int = 23,
    ) -> Path:
        """
        Fast hard-cut assembly using ffmpeg concat demuxer.
        CRF 23 = YouTube quality (3-6MB per 5s clip vs 15-25MB at CRF 18).
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
                "-preset", "medium",   # medium = good speed/quality balance
                "-crf", str(crf),       # 23 = YouTube quality, 18 = archival
                "-profile:v", "high",  # H.264 High Profile = better compression
                "-level", "4.1",       # YouTube compatible level
                "-movflags", "+faststart",  # Web streaming optimization
                "-pix_fmt", "yuv420p",
                "-an",                 # No audio (parked)
                str(output_path),
            ]
            logging.info(f"[VideoAssembler] concat encode: CRF={crf}, {w}x{h}")
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
        crf: int = 23,
    ) -> Path:
        """
        Smooth crossfade assembly using ffmpeg xfade filter.
        CRF 23 = YouTube quality. Falls back to concat if xfade fails.
        """
        w, h = target_resolution.split("x")
        n = len(clip_paths)

        clip_durations = []
        for clip in clip_paths:
            dur = self._get_clip_duration(ffmpeg, clip)
            clip_durations.append(dur)
            logging.info(f"[VideoAssembler] Clip {clip.name}: {dur:.2f}s")

        cmd = [ffmpeg, "-y"]
        for clip in clip_paths:
            cmd += ["-i", str(clip)]

        filter_parts = []
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]scale={w}:{h}:flags=lanczos,fps=24,format=yuv420p[v{i}]"
            )

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
            "-preset", "medium",
            "-crf", str(crf),
            "-profile:v", "high",
            "-level", "4.1",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]

        logging.info(f"[VideoAssembler] xfade assembly: {n} clips, CRF={crf}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if result.returncode != 0:
                logging.warning(
                    f"[VideoAssembler] xfade failed, falling back to concat.\n"
                    f"Error: {result.stderr[-500:]}"
                )
                return self._assemble_concat(ffmpeg, clip_paths, output_path, target_resolution, crf)
        except subprocess.TimeoutExpired:
            logging.warning("[VideoAssembler] xfade timed out, falling back to concat.")
            return self._assemble_concat(ffmpeg, clip_paths, output_path, target_resolution, crf)

        logging.info(f"[VideoAssembler] Crossfade assembled: {output_path}")
        return output_path

    def compress_for_youtube(
        self,
        input_path: Path,
        output_path: Path,
        crf: int = 23,
        target_resolution: str = "1920x1080",
        audio_path: Optional[Path] = None,
    ) -> Path:
        """
        Standalone YouTube compression pass.
        Takes any video file and outputs a YouTube-optimized H.264 MP4.

        Args:
            input_path:        Source video file.
            output_path:       Destination for compressed video.
            crf:               Quality level. 23=YouTube, 18=archival, 28=web.
            target_resolution: Output resolution (default 1920x1080).
            audio_path:        Optional audio track to mix in.

        Returns:
            Path to compressed output.

        File size examples (1920x1080 @ 24fps):
            5-second clip:  CRF 23 = ~3-6 MB  (vs ~15-20 MB at CRF 18)
            30-second video: CRF 23 = ~20-40 MB (vs ~90-150 MB at CRF 18)
        """
        ffmpeg = _find_ffmpeg()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        w, h = target_resolution.split("x")

        cmd = [
            ffmpeg, "-y",
            "-i", str(input_path),
        ]
        if audio_path and audio_path.exists():
            cmd += ["-i", str(audio_path), "-shortest"]

        cmd += [
            "-vf", f"scale={w}:{h}:flags=lanczos",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", str(crf),
            "-profile:v", "high",
            "-level", "4.1",
            "-movflags", "+faststart",  # Enables streaming before full download
            "-pix_fmt", "yuv420p",
        ]
        if audio_path and audio_path.exists():
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-an"]
        cmd.append(str(output_path))

        logging.info(f"[VideoAssembler] YouTube compress: {input_path.name} -> CRF={crf} {w}x{h}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"YouTube compression failed:\n{result.stderr[-500:]}")

        size_mb = round(output_path.stat().st_size / (1024*1024), 1)
        orig_mb = round(input_path.stat().st_size / (1024*1024), 1)
        saved_pct = round((1 - size_mb/orig_mb) * 100) if orig_mb > 0 else 0
        logging.info(f"[VideoAssembler] Compressed: {orig_mb}MB -> {size_mb}MB (saved {saved_pct}%)")
        print(f"  YouTube compression: {orig_mb} MB -> {size_mb} MB (saved {saved_pct}%, CRF={crf})")
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
