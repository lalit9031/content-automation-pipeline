from __future__ import annotations

import cv2
import logging
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.bots.qa_auditor import QAVisualAuditor


class VideoTesterAgent:
    """
    Tester Agent that extracts key frames from a generated MP4 video and 
    audits them using the local Vision model (Ollama qwen2.5vl) for structural deforming or melting defects.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.auditor = QAVisualAuditor(settings)

    def audit_video(self, video_path: Path, prompt: str, sample_count: int = 5) -> dict[str, Any]:
        """
        Audits a video file by sampling key frames.
        Returns a dict indicating PASS/FAIL, list of frame failures, and correction feedback.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found at {video_path}")

        print(f"\n[Tester Agent] Opening video file {video_path.name} for frame-by-frame audit...")
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file with OpenCV: {video_path}")

        # Get total frame count
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = total_frames / fps if fps > 0 else 0
        print(f"[Tester Agent] Total frames: {total_frames}, FPS: {fps:.2f}, Duration: {duration:.2f}s")

        if total_frames <= 0:
            cap.release()
            return {"status": "FAIL", "reason": "Video has zero frames.", "failures": []}

        # Select frames to sample (evenly distributed)
        sample_indices = []
        if total_frames <= sample_count:
            sample_indices = list(range(total_frames))
        else:
            # Avoid the very first frame if it's completely blank, but frame 0 is usually the reference image
            # Sample evenly from 0 to total_frames - 1
            step = (total_frames - 1) / (sample_count - 1) if sample_count > 1 else 1
            sample_indices = [int(round(i * step)) for i in range(sample_count)]

        print(f"[Tester Agent] Sampling frames at indices: {sample_indices}")

        failures = []
        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                logging.warning(f"Failed to read frame at index {frame_idx}")
                continue

            # Encode frame as PNG
            success, buffer = cv2.imencode(".png", frame)
            if not success:
                logging.warning(f"Failed to encode frame {frame_idx} as PNG")
                continue

            frame_bytes = buffer.tobytes()
            print(f"[Tester Agent] Auditing frame {frame_idx}...")
            
            # Run image audit
            audit_result = self.auditor.audit_image(frame_bytes, prompt)
            
            # Process failures
            if audit_result.get("status") == "FAIL":
                reason = audit_result.get("reason", "Unknown defect")
                defect_type = audit_result.get("defect_type", "structural_damage")
                bbox = audit_result.get("bounding_box")
                print(f"  -> FAILURE on Frame {frame_idx}: {reason} ({defect_type})")
                failures.append({
                    "frame_index": frame_idx,
                    "reason": reason,
                    "defect_type": defect_type,
                    "bounding_box": bbox
                })

        cap.release()

        if failures:
            # Summarize the failures for the developer
            reasons = "; ".join(f"Frame {f['frame_index']}: {f['reason']}" for f in failures)
            feedback = (
                f"Video failed audit due to visual breaking/melting. "
                f"Issues detected: {reasons}."
            )
            return {
                "status": "FAIL",
                "reason": feedback,
                "failures": failures
            }

        print("[Tester Agent] All sampled frames PASSED the quality audit!")
        return {"status": "PASS", "reason": "All frames passed visual checks.", "failures": []}
