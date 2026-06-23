"""
script_engine.py
================
Breaks a raw user prompt into a structured sequence of scenes for long-form
video generation. Each scene has its own expanded prompt, duration, and
scene-specific variation to prevent visual repetition.

No LLM required — pure rule-based narrative progression.
Zero VRAM, instant execution.

Usage:
    from content_pipeline.bots.script_engine import ScriptEngine

    engine = ScriptEngine()
    scenes = engine.build_scene_list("girl walking in rain forest", target_seconds=30)
    for scene in scenes:
        print(scene.scene_number, scene.raw_prompt, scene.duration_seconds)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Scene narrative progression templates
# These define how the story naturally evolves across N scenes.
# Each template is (action_modifier, camera_modifier, detail_note).
# ---------------------------------------------------------------------------

_NARRATIVE_ARC: list[tuple[str, str, str]] = [
    # Scene 1 — Establishing shot: wide, slow intro
    (
        "approaching from a distance, walking slowly",
        "wide establishing shot, static camera, subject entering frame from the far left",
        "First look at the scene — environment is the focus, subject small in frame."
    ),
    # Scene 2 — Subject in environment: mid-distance, steady motion
    (
        "walking at a natural pace, looking ahead with calm focus",
        "medium wide shot following the subject from behind at 4 meters, slow dolly forward",
        "Subject is comfortable in the environment, natural gait."
    ),
    # Scene 3 — Close-up movement: tighter framing, face visible
    (
        "walking steadily, glancing around at the surroundings with curiosity",
        "medium close-up side profile shot, camera tracking alongside the subject",
        "Character expression and emotion visible — curiosity and wonder."
    ),
    # Scene 4 — Environmental detail: subject pauses or slows
    (
        "slowing down, looking around the scene thoughtfully, breathing visible",
        "slightly low angle shot looking up at the subject, static camera with gentle push-in",
        "Moment of pause and reflection — subject connects with the environment."
    ),
    # Scene 5 — Continuation / progression: forward momentum
    (
        "walking confidently forward, moving deeper into the scene",
        "tracking shot from slightly behind and above, gentle crane-down motion",
        "Story progresses — subject is moving toward a goal or destination."
    ),
    # Scene 6 — Arrival / destination: subject reaches point of interest
    (
        "arriving at the destination, slowing to a stop, looking forward",
        "front-facing medium shot, camera slowly zooming in toward subject's face",
        "Emotional payoff — subject has arrived, face visible and clear."
    ),
]

# Scene-specific environment variations for visual variety
_SCENE_ENVIRONMENT_VARIATIONS: dict[str, list[str]] = {
    "rain": [
        "heavy rain visible in foreground, puddles forming on the path",
        "rain beginning to lighten, puddles reflecting grey sky",
        "raindrops visible on leaves and surfaces around the subject",
        "rain creating a misty atmosphere in the background distance",
        "last of the rain, wet environment, shafts of light breaking through clouds",
        "rain has stopped, environment glistening with water droplets on every surface",
    ],
    "forest": [
        "dense forest with towering trees, dappled morning light",
        "forest path with moss-covered stones and ancient roots",
        "forest opening up slightly, more light filtering through canopy",
        "forest floor with scattered autumn leaves and soft undergrowth",
        "trees thinning ahead, hint of open space visible",
        "forest edge reached, open clearing visible beyond the trees",
    ],
    "beach": [
        "quiet beach, early morning light, gentle surf in distance",
        "walking along the shoreline, small waves visible at the feet",
        "beach with golden wet sand, seagulls in the distance",
        "closer to the water's edge, cool ocean breeze evident",
        "standing at the water's edge, horizon stretching ahead",
        "looking out at the ocean, peaceful expression on face",
    ],
    "park": [
        "park entrance, tree-lined path stretching ahead",
        "park pathway with dappled sunlight through branches",
        "open park lawn with scattered benches visible",
        "park fountain or landmark visible in the distance",
        "quieter corner of the park, more intimate and peaceful",
        "park bench area, sitting spot reached",
    ],
    "default": [
        "in the environment, natural light",
        "moving through the scene, ambient details visible",
        "mid-scene, character engaged with surroundings",
        "pausing briefly, taking in the environment",
        "continuing forward, destination ahead",
        "reaching the scene's focal point",
    ],
}


@dataclass
class SceneDescription:
    """Represents one scene in a long-form video storyboard."""
    scene_number: int        # 1-indexed
    total_scenes: int        # Total scenes in this video
    raw_prompt: str          # Expanded raw prompt for this scene
    duration_seconds: int    # How long this clip should be (5 or 6)
    action_modifier: str     # What the subject is doing in this scene
    camera_modifier: str     # How the camera is positioned/moving
    environment_detail: str  # Scene-specific environment variation
    narrative_note: str      # Internal note for what this scene accomplishes
    is_first: bool = False   # True for scene 1 (uses generated image, not last frame)
    is_last: bool = False    # True for the final scene


class ScriptEngine:
    """
    Breaks a raw user prompt into a structured sequence of scenes
    for long-form video generation.

    Design:
    - Minimum clip duration: 5 seconds (LTXV sweet spot for quality)
    - Maximum clip duration: 6 seconds (VRAM limit before quality drops)
    - For any duration, automatically calculates the right number of scenes
    - Applies a narrative arc: establishing → mid-scene → close-up → arrival
    - Varies environment details across scenes to prevent visual repetition

    Example:
        engine = ScriptEngine()
        scenes = engine.build_scene_list("girl walking in rain", target_seconds=30)
        # Returns 5 scenes of 6 seconds each
    """

    CLIP_DURATION_SECONDS: int = 6  # Sweet spot: good quality, fits in VRAM

    def build_scene_list(
        self,
        raw_prompt: str,
        target_seconds: int = 30,
        clip_duration: Optional[int] = None,
    ) -> list[SceneDescription]:
        """
        Generate a list of SceneDescriptions for a target video duration.

        Args:
            raw_prompt:      The base user prompt (e.g. "girl walking in rain forest")
            target_seconds:  Total desired video duration in seconds
            clip_duration:   Override clip duration. Defaults to CLIP_DURATION_SECONDS (6s)

        Returns:
            List of SceneDescription objects, one per clip.
        """
        clip_dur = clip_duration or self.CLIP_DURATION_SECONDS
        # Calculate number of clips needed (round up to cover target duration)
        num_scenes = max(1, -(-target_seconds // clip_dur))  # ceiling division

        logging.info(
            f"[ScriptEngine] Building {num_scenes} scenes × {clip_dur}s "
            f"= {num_scenes * clip_dur}s for prompt: '{raw_prompt}'"
        )

        # Detect the scene keyword for environment variations
        text_lower = raw_prompt.lower()
        scene_kw = self._detect_scene_keyword(text_lower)
        env_variations = _SCENE_ENVIRONMENT_VARIATIONS.get(scene_kw, _SCENE_ENVIRONMENT_VARIATIONS["default"])

        scenes: list[SceneDescription] = []
        for i in range(num_scenes):
            # Select the narrative arc step — cycle if more scenes than arc entries
            arc_idx = min(i, len(_NARRATIVE_ARC) - 1) if num_scenes <= len(_NARRATIVE_ARC) else i % len(_NARRATIVE_ARC)
            action_mod, camera_mod, narrative_note = _NARRATIVE_ARC[arc_idx]

            # Select environment variation — cycle through available variations
            env_detail = env_variations[i % len(env_variations)]

            # Build the scene-specific expanded prompt
            scene_prompt = self._build_scene_prompt(
                base_prompt=raw_prompt,
                action_modifier=action_mod,
                environment_detail=env_detail,
                scene_number=i + 1,
                total_scenes=num_scenes,
            )

            scene = SceneDescription(
                scene_number=i + 1,
                total_scenes=num_scenes,
                raw_prompt=scene_prompt,
                duration_seconds=clip_dur,
                action_modifier=action_mod,
                camera_modifier=camera_mod,
                environment_detail=env_detail,
                narrative_note=narrative_note,
                is_first=(i == 0),
                is_last=(i == num_scenes - 1),
            )
            scenes.append(scene)

        return scenes

    def _build_scene_prompt(
        self,
        base_prompt: str,
        action_modifier: str,
        environment_detail: str,
        scene_number: int,
        total_scenes: int,
    ) -> str:
        """
        Build a scene-specific variation of the base prompt.
        Keeps the subject/setting consistent while varying action and environment.
        """
        return (
            f"{base_prompt.strip()}. "
            f"Action: {action_modifier}. "
            f"Environment detail: {environment_detail}. "
            f"Scene {scene_number} of {total_scenes}."
        )

    def _detect_scene_keyword(self, text: str) -> str:
        """Detect dominant scene keyword from the prompt text."""
        keywords = ["rain", "beach", "forest", "jungle", "mountain", "park", "river", "street", "office"]
        for kw in keywords:
            if kw in text:
                return kw
        return "default"

    def describe_plan(self, scenes: list[SceneDescription]) -> str:
        """Return a human-readable plan summary."""
        total = sum(s.duration_seconds for s in scenes)
        lines = [
            f"VIDEO PLAN: {len(scenes)} clips × {scenes[0].duration_seconds}s = {total}s total",
            f"{'─' * 60}",
        ]
        for s in scenes:
            status = "START (from generated image)" if s.is_first else "CHAIN (from previous clip's last frame)"
            lines.append(
                f"Scene {s.scene_number:02d}/{s.total_scenes:02d} | {s.duration_seconds}s | {status}"
            )
            lines.append(f"  Action  : {s.action_modifier[:70]}")
            lines.append(f"  Camera  : {s.camera_modifier[:70]}")
            lines.append(f"  Env     : {s.environment_detail[:70]}")
        lines.append(f"{'─' * 60}")
        return "\n".join(lines)
