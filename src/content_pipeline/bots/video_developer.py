from __future__ import annotations

import random
from typing import Any
import dataclasses

from content_pipeline.config import Settings
from content_pipeline.bots.motion import MotionClip, MotionPlan


class VideoDeveloperAgent:
    """
    Developer Agent that dynamically reduces motion intensity (motion bucket ID)
    to prevent character melting and structural deforming in the SVD video.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.attempt = 0
        # Tracks current values that we adjust.
        # Initialize at 50 for stable, cinematic camera movement.
        self.current_motion_bucket = 50
        self.current_cfg = 2.2

    def propose_correction(self, clip: MotionClip, plan: MotionPlan, last_feedback: dict[str, Any] | None) -> tuple[MotionClip, MotionPlan]:
        """
        Takes the original clip and plan, plus any audit failure feedback,
        and returns updated settings focusing strictly on reducing movement.
        """
        self.attempt += 1
        
        # 1. On first attempt, initialize baseline settings
        if not last_feedback:
            print(f"\n[Developer Agent] Initializing baseline video parameters (Attempt {self.attempt})...")
            print(f"[Developer Agent] Starting with optimal motion: motion_bucket_id={self.current_motion_bucket}")
            return clip, plan

        print(f"\n[Developer Agent] Analyzing failure feedback: {last_feedback['reason']}")
        
        # 2. Reduce Motion Bucket ID to decrease girl movement
        if self.current_motion_bucket > 35:
            self.current_motion_bucket -= 15
        elif self.current_motion_bucket > 20:
            self.current_motion_bucket -= 15
        elif self.current_motion_bucket > 5:
            self.current_motion_bucket = 5
        else:
            self.current_motion_bucket = 1 # Absolute minimal motion

        print(f"[Developer Agent] Correcting parameters: Reducing motion_bucket_id to {self.current_motion_bucket} to limit movement.")

        # 3. Generate a new seed and update prompt with stability tags
        new_seed = random.randint(1, 1125899906842624)
        print(f"[Developer Agent] Selecting a new random seed: {new_seed}")

        stability_modifiers = "extremely stable, steady camera, highly consistent details, no morphing, no warping, slow motion"
        if stability_modifiers not in clip.prompt:
            clip = dataclasses.replace(clip, prompt=f"{clip.prompt}, {stability_modifiers}")
            print(f"[Developer Agent] Appended stability modifiers to prompt: '{clip.prompt}'")

        return clip, plan
