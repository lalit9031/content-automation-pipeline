from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.bots.motion import ComfyUIMotionProvider, MotionClip, MotionPlan
from content_pipeline.bots.video_tester import VideoTesterAgent
from content_pipeline.bots.video_developer import VideoDeveloperAgent


class VideoAgentOrchestrator:
    """
    Orchestrates the feedback loop between VideoTesterAgent and VideoDeveloperAgent 
    to automatically repair video artifacts (like melting or tearing) locally.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tester = VideoTesterAgent(settings)
        self.developer = VideoDeveloperAgent(settings)
        self.provider = ComfyUIMotionProvider(settings)
        self.workflow_path = Path(settings.comfyui_video_workflow)

    def _update_workflow_file(self, motion_bucket_id: int, cfg: float) -> None:
        """
        Dynamically modifies the ComfyUI SVD workflow JSON template with updated parameters.
        """
        if not self.workflow_path.exists():
            print(f"[Orchestrator] Warning: Workflow file not found at {self.workflow_path}")
            return
            
        try:
            with open(self.workflow_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Update Node 2 (SVD_img2vid_Conditioning)
            if "2" in data and "inputs" in data["2"]:
                data["2"]["inputs"]["motion_bucket_id"] = motion_bucket_id
                
            # Update Node 3 (KSampler)
            if "3" in data and "inputs" in data["3"]:
                data["3"]["inputs"]["cfg"] = cfg
                
            with open(self.workflow_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
            print(f"[Orchestrator] Updated workflow parameters: motion_bucket_id={motion_bucket_id}, cfg={cfg:.1f}")
        except Exception as exc:
            print(f"[Orchestrator] Warning: Failed to update workflow file: {exc}")

    def run_video_generation_loop(
        self,
        clip: MotionClip,
        plan: MotionPlan,
        destination: Path,
        max_attempts: int = 3
    ) -> dict[str, Any]:
        """
        Runs the loop:
        1. Dev proposes parameters (baseline first, then corrected).
        2. Orchestrator updates workflow file.
        3. Provider renders video.
        4. Tester inspects key frames.
        5. Loops on failure up to max_attempts.
        """
        last_feedback = None
        current_clip = clip
        current_plan = plan

        for attempt in range(1, max_attempts + 1):
            print("\n" + "="*80)
            print(f"MULTI-AGENT VIDEO GENERATION LOOP - ATTEMPT {attempt}/{max_attempts}")
            print("="*80)

            # 1. Developer proposes parameters
            current_clip, current_plan = self.developer.propose_correction(
                current_clip,
                current_plan,
                last_feedback
            )

            # 2. Update the workflow JSON
            self._update_workflow_file(
                self.developer.current_motion_bucket,
                self.developer.current_cfg
            )

            # 3. Render video
            print(f"\n[Orchestrator] Triggering rendering with prompt: '{current_clip.prompt}'")
            try:
                # ComfyUIMotionProvider will generate video and save it to destination, then interpolate to 25 FPS
                result = self.provider.create_clip(current_clip, current_plan, destination)
            except Exception as render_exc:
                print(f"\n[Orchestrator] Rendering failed: {render_exc}")
                # We return failure so caller knows it failed
                raise render_exc

            # 4. Tester audits the output video
            audit_result = self.tester.audit_video(destination, current_clip.prompt, sample_count=12)
            
            if audit_result["status"] == "PASS":
                print(f"\n[Orchestrator] Success! Video passed audit on attempt {attempt}.")
                return {
                    "status": "SUCCESS",
                    "attempts_needed": attempt,
                    "video_file": str(destination),
                    "prompt_used": current_clip.prompt,
                    "motion_bucket": self.developer.current_motion_bucket,
                    "cfg": self.developer.current_cfg
                }
            
            # Save feedback for developer on next attempt
            last_feedback = audit_result

        print(f"\n[Orchestrator] Warning: Max attempts ({max_attempts}) reached. Video did not fully pass audit, returning best attempt.")
        return {
            "status": "TIMEOUT_FAIL",
            "attempts_needed": max_attempts,
            "video_file": str(destination),
            "prompt_used": current_clip.prompt,
            "motion_bucket": self.developer.current_motion_bucket,
            "cfg": self.developer.current_cfg,
            "last_error": last_feedback.get("reason")
        }
