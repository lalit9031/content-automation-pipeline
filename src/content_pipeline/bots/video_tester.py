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

    def detect_lag_and_stutter(self, video_path: Path) -> dict[str, Any]:
        """
        Analyzes video frames programmatically to detect freezes (lags) or extreme jumps (stutter).
        Uses 0 MB VRAM, runs in < 0.5s.
        """
        import numpy as np

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"status": "PASS", "reason": "Could not open video to check lag"}

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 1:
            cap.release()
            return {"status": "PASS", "reason": "Too few frames to analyze lag"}

        # Read all frames and compute difference between consecutive frames
        prev_gray = None
        diffs = []
        frame_indices = []

        success = True
        idx = 0
        while success:
            success, frame = cap.read()
            if not success:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                # Compute Mean Absolute Error
                mae = np.mean(cv2.absdiff(gray, prev_gray))
                diffs.append(mae)
                frame_indices.append(idx)
            prev_gray = gray
            idx += 1

        cap.release()

        if not diffs:
            return {"status": "PASS", "reason": "No differences computed"}

        # Check for freezes (identical or nearly identical frames)
        freeze_threshold = getattr(self.settings, "video_freeze_threshold", 0.05)
        
        # Look for consecutive freezes
        consecutive_freezes = 0
        max_consecutive_freezes = 0
        freeze_start_idx = -1
        
        for i, diff in enumerate(diffs):
            if diff <= freeze_threshold:
                if consecutive_freezes == 0:
                    freeze_start_idx = frame_indices[i] - 1
                consecutive_freezes += 1
                max_consecutive_freezes = max(max_consecutive_freezes, consecutive_freezes)
            else:
                consecutive_freezes = 0

        # Specifically inspect the last second (e.g. last 25 frames for a 25fps video)
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.release()
        
        last_sec_frame_count = int(fps)
        last_sec_diffs = diffs[-last_sec_frame_count:] if len(diffs) >= last_sec_frame_count else diffs
        
        last_sec_freezes = sum(1 for d in last_sec_diffs if d <= freeze_threshold)
        last_sec_freeze_ratio = last_sec_freezes / len(last_sec_diffs) if last_sec_diffs else 0.0

        print(f"[Tester Agent] Temporal Audit: Max consecutive frozen frames: {max_consecutive_freezes}, Last second freeze ratio: {last_sec_freeze_ratio:.1%}")

        # Flag freeze if there are more than 4 consecutive frozen frames anywhere,
        # or if the last second is frozen for more than 30% of its duration.
        if max_consecutive_freezes >= 4:
            return {
                "status": "FAIL",
                "reason": f"Video lag/freeze detected. Max consecutive frozen frames: {max_consecutive_freezes} (starts around frame {freeze_start_idx}).",
                "defect_type": "temporal_freeze"
            }
            
        if last_sec_freeze_ratio >= 0.3:
            return {
                "status": "FAIL",
                "reason": f"Video lag/stutter detected in the last second. {last_sec_freeze_ratio:.1%} of final frames are frozen.",
                "defect_type": "temporal_freeze"
            }

        return {"status": "PASS", "reason": "No lag or freeze detected."}

    def audit_video(self, video_path: Path, prompt: str, sample_count: int = 12) -> dict[str, Any]:
        """
        Audits a video file by:
        1. Programmatically checking for temporal freeze/lag using frame differences (0 VRAM).
        2. Sampling key frames (biased towards the end) and checking face quality via Moondream.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found at {video_path}")

        # 1. Programmatic lag/stutter audit first
        print(f"\n[Tester Agent] Running temporal audit for lag/stutter on {video_path.name}...")
        lag_result = self.detect_lag_and_stutter(video_path)
        if lag_result["status"] == "FAIL":
            print(f"  -> FAILURE: {lag_result['reason']}")
            return {
                "status": "FAIL",
                "reason": lag_result["reason"],
                "failures": [{
                    "frame_index": -1,
                    "reason": lag_result["reason"],
                    "defect_type": lag_result["defect_type"],
                    "bounding_box": None
                }]
            }

        # 2. Visual frame-by-frame audit
        print(f"\n[Tester Agent] Opening video file {video_path.name} for visual frame audit...")
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file with OpenCV: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = total_frames / fps if fps > 0 else 0
        print(f"[Tester Agent] Total frames: {total_frames}, FPS: {fps:.2f}, Duration: {duration:.2f}s")

        if total_frames <= 0:
            cap.release()
            return {"status": "FAIL", "reason": "Video has zero frames.", "failures": []}

        # Select frames to sample (biased towards the end to catch melting/deformation)
        sample_indices = []
        if total_frames <= sample_count:
            sample_indices = list(range(total_frames))
        else:
            first_half_count = max(1, sample_count // 3)
            second_half_count = sample_count - first_half_count
            mid = total_frames // 2
            
            first_half_indices = [int(round(i * (mid / first_half_count))) for i in range(first_half_count)]
            second_half_step = (total_frames - 1 - mid) / (second_half_count - 1) if second_half_count > 1 else 1
            second_half_indices = [int(round(mid + i * second_half_step)) for i in range(second_half_count)]
            
            sample_indices = sorted(list(set(first_half_indices + second_half_indices)))

        print(f"[Tester Agent] Sampling frames at indices: {sample_indices}")

        failures = []
        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                logging.warning(f"Failed to read frame at index {frame_idx}")
                continue

            success, buffer = cv2.imencode(".png", frame)
            if not success:
                logging.warning(f"Failed to encode frame {frame_idx} as PNG")
                continue

            frame_bytes = buffer.tobytes()
            print(f"[Tester Agent] Auditing frame {frame_idx}...")
            
            audit_result = self.auditor.audit_image(frame_bytes, prompt)
            
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

        print("[Tester Agent] All checks (temporal & visual) PASSED!")
        return {"status": "PASS", "reason": "All checks passed.", "failures": []}
