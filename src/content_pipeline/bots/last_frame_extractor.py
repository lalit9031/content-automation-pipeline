"""
last_frame_extractor.py
=======================
Extracts the last frame of a generated video clip as a PNG image.
Used for chained video generation: clip N's last frame becomes clip N+1's start image.

This gives perfect visual continuity — no jump cuts between clips.

Usage:
    from content_pipeline.bots.last_frame_extractor import LastFrameExtractor

    extractor = LastFrameExtractor()
    png_path = extractor.extract(Path("clip_01.mp4"), output_dir=Path("frames/"))
    # Returns: Path("frames/clip_01_last_frame.png")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


class LastFrameExtractor:
    """
    Extracts specific frames from a video clip using OpenCV.

    Capabilities:
    - extract()       : Extract the very last frame (for chaining)
    - extract_first() : Extract the very first frame (for QA reference)
    - extract_at()    : Extract any frame at a given second timestamp
    """

    def extract(self, video_path: Path, output_dir: Optional[Path] = None) -> Path:
        """
        Extract the LAST frame of a video as a PNG.

        Args:
            video_path:  Path to the source .mp4 video file.
            output_dir:  Directory to save the PNG. Defaults to video_path's parent.

        Returns:
            Path to the saved PNG file.

        Raises:
            FileNotFoundError: If video_path does not exist.
            RuntimeError:      If the frame cannot be read from the video.
        """
        import cv2

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        out_dir = output_dir or video_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{video_path.stem}_last_frame.png"

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        duration = total_frames / fps if fps > 0 else 0

        logging.info(
            f"[LastFrameExtractor] Video: {video_path.name} | "
            f"Frames: {total_frames} | FPS: {fps:.1f} | Duration: {duration:.2f}s"
        )

        # Jump to the last valid frame
        # We go back 3 frames from the end to avoid potentially blank final frames
        target_frame = max(0, total_frames - 3)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        ret, frame = cap.read()
        if not ret:
            # Fallback: try the very last frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
            ret, frame = cap.read()

        cap.release()

        if not ret or frame is None:
            raise RuntimeError(
                f"Failed to read last frame from video: {video_path}. "
                f"Total frames reported: {total_frames}"
            )

        cv2.imwrite(str(out_path), frame)
        logging.info(f"[LastFrameExtractor] Last frame saved: {out_path}")
        return out_path

    def extract_first(self, video_path: Path, output_dir: Optional[Path] = None) -> Path:
        """
        Extract the FIRST frame of a video as a PNG (useful for QA or comparison).
        """
        import cv2

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        out_dir = output_dir or video_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{video_path.stem}_first_frame.png"

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            raise RuntimeError(f"Failed to read first frame from video: {video_path}")

        cv2.imwrite(str(out_path), frame)
        logging.info(f"[LastFrameExtractor] First frame saved: {out_path}")
        return out_path

    def extract_at(
        self,
        video_path: Path,
        timestamp_seconds: float,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Extract a frame at a specific timestamp (in seconds).
        """
        import cv2

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        out_dir = output_dir or video_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_label = f"{timestamp_seconds:.1f}s".replace(".", "_")
        out_path = out_dir / f"{video_path.stem}_frame_{ts_label}.png"

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        target_frame = int(timestamp_seconds * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            raise RuntimeError(f"Failed to read frame at {timestamp_seconds}s from: {video_path}")

        cv2.imwrite(str(out_path), frame)
        logging.info(f"[LastFrameExtractor] Frame at {timestamp_seconds}s saved: {out_path}")
        return out_path
