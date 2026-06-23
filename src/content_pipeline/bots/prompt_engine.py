from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ==========================================
# MASTER CONFIGS & TEMPLATES
# ==========================================

# ---------------------------------------------------------------------------
# Dimension 6: Quality Modifiers — used in all 3 prompt types
# ---------------------------------------------------------------------------
MASTER_IMAGE_TEMPLATE = (
    "Photorealistic digital photograph. "
    "Subject: a professional {subject}, wearing {clothing}, holding {object}, "
    "with a natural, confident expression. "
    "Setting: modern high-tech office environment with glass partitions and clean white desks. "
    "Lighting: soft professional studio lighting supplemented by natural window light, "
    "neutral daylight color temperature. "
    "Shot on a full-frame digital cinema camera, shallow depth of field (f/2.8), "
    "sharp focus on subject's face and clothing details. "
    "Quality: photorealistic, 8K, hyper-detailed textures on skin and fabric, "
    "clean composition, cinematic color grading. "
    "No watermarks, no text overlays, no distorted limbs, no blurry face, no artifacts."
)

MASTER_VIDEO_TEMPLATE = (
    "Cinematic video clip shot on a digital cinema camera. "
    "Subject: a professional {subject} in a clean, brightly lit modern office. "
    "The subject is {action}. "
    "Motion: full body visible, posture natural and upright, feet firmly on the floor, "
    "arms moving with natural weight and momentum. "
    "Camera: slow gentle zoom-in toward the subject, starting from a medium wide shot. "
    "Lighting: soft professional studio lighting, even and consistent throughout the clip, "
    "no flickering, no shadow changes. "
    "Quality: photorealistic, 4K, sharp focus on subject's face and eyes at all times, "
    "smooth 24fps, cinematic color grading, no motion blur on the face. "
    "No watermarks, no text overlays, no distorted limbs, no floating feet, "
    "no sliding steps, no shaking camera, no jitter, no frame tearing."
)

# ---------------------------------------------------------------------------
# Dimension 7: Negative Anchors (expanded with motion-physics constraints)
# ---------------------------------------------------------------------------
QUALITY_CONTROL_NEGATIVE_PROMPT = (
    # Visual quality
    "blurry, low resolution, pixelated, oversaturated, contrast issues, "
    "watermark, text overlay, logo, "
    # Face & anatomy
    "distorted face, morphed anatomy, deformed hands, extra fingers, fused hands, "
    "blurry face, melted face, broken face, warped face, "
    # Motion & camera
    "shaky camera, motion blur on face, flickering, jitter, frame tearing, ghosting, "
    # Feet & limbs (critical for walking scenes)
    "floating feet, sliding feet, unnatural gait, deformed shoes, melted shoes, "
    "broken legs, extra legs, fused legs, "
    # Eye stability (critical for close-ups)
    "shaking eyes, jittery eyes, flickering eyes, "
    # Technical
    "grain, noise, artifacts, cartoonish, low quality, deformed."
)

# Pre-defined library modules for LEGO-style composition
DEFAULT_IMAGE_LIBRARY = {
    "environments": {
        "office": "modern high-tech office environment",
        "minimalist": "a high-end, minimalist architectural space, clean background",
        "cyberpunk": "a futuristic dark control room with holographic projections",
        "creative": "a vibrant co-working studio with soft natural light"
    },
    "lightings": {
        "studio": "soft professional studio lighting",
        "cinematic": "cinematic rim lighting, soft volumetric rays, high contrast",
        "warm": "warm sunset glow filtering through window glass",
        "neon": "subtle blue and purple neon accent glow"
    },
    "cameras": {
        "standard": "depth of field, sharp focus on subject, shot on 35mm lens, f/8",
        "macro": "macro close-up shot, shallow depth of field, f/2.8, sharp focal point",
        "wide": "wide cinematic master shot, deep focus, f/11, stable perspective"
    },
    "quality_levers": {
        "standard": "photorealistic, 8k, extremely detailed, clean composition",
        "ultra": "hyper-realistic, intricate textures, masterpiece, high-fidelity, unreal engine 5 render quality"
    },
    "styles": {
        "neutral": "neutral color palette",
        "pastel": "soft pastel color palette with purple and cyan highlights",
        "monochrome": "sleek monochrome tech styling with a single orange accent"
    }
}

DEFAULT_AUDIO_LIBRARY = {
    "personas": {
        "corporate_male": "Professional corporate male speaker with a mature deep tone.",
        "corporate_female": "Warm, professional corporate female speaker with clear delivery.",
        "story_female": "Warm, maternal, soothing female story narrator.",
        "story_male": "Deep charismatic male storyteller voice with steady resonance.",
        "toddler_excited": "Excited, high-energy young toddler voice."
    },
    "pitch_prosody": {
        "stable": "even pitch, stable vocal resonance",
        "dynamic": "expressive intonation, natural inflection peaks",
        "deep": "deep baritone pitch, slower cadence"
    },
    "pacing_rules": {
        "calm": "measured speaking pace, 130 words per minute, deliberate pauses for clarity",
        "energetic": "upbeat, fast-paced speech, brief natural breaths",
        "dramatic": "slowed storyteller cadence, meaningful breaks between sentences"
    },
    "pronunciation_rules": {
        "precise": "clean pronunciation of technical terms, no swallowed syllables, standard accentuation",
        "hindi_focused": "pure Hindi pronunciation, correct sounds for Go-kul, Ya-sho-da, and Kan-ha"
    },
    "output_cleaning": {
        "studio": "pristine studio recording quality, no background hiss, high signal-to-noise ratio, pure clean voice"
    }
}

@dataclass
class ImagePromptBlueprint:
    core_subject: str
    environment: str = "modern high-tech office environment"
    lighting: str = "soft professional studio lighting"
    camera: str = "depth of field, sharp focus on subject, shot on 35mm lens, f/8"
    quality_levers: str = "photorealistic, 8k, extremely detailed, clean composition"
    style: str = "neutral color palette"

    def assemble(self) -> str:
        parts = [
            self.core_subject.strip(),
            self.environment.strip(),
            self.lighting.strip(),
            self.camera.strip(),
            self.quality_levers.strip(),
            self.style.strip()
        ]
        return ", ".join(p for p in parts if p) + "."

@dataclass
class VideoPromptBlueprint:
    core_subject: str
    environment: str = "clean, brightly lit modern office"
    action: str = "standing still"
    motion: str = "slow, smooth camera zoom-in toward the subject"
    visual_anchors: str = "glowing data visualizations on the screen are subtly pulsing"
    camera: str = "consistent lighting, smooth frame transitions, stable focus"
    quality: str = "photorealistic, high fidelity, 4k, no motion blur"

    def assemble(self) -> str:
        return (
            f"Cinematic, stable 4-second video. A professional {self.core_subject.strip()} "
            f"standing in {self.environment.strip()}. The subject is {self.action.strip()}. "
            f"The only movement is {self.motion.strip()}. {self.visual_anchors.strip()}. "
            f"{self.camera.strip()}, {self.quality.strip()}."
        )

@dataclass
class AudioPromptBlueprint:
    persona: str
    pitch_prosody: str = "even pitch, stable vocal resonance"
    pacing_rules: str = "measured speaking pace, 130 words per minute, deliberate pauses for clarity"
    pronunciation_rules: str = "clean pronunciation of technical terms, no swallowed syllables, standard accentuation"
    output_cleaning: str = "pristine studio recording quality, no background hiss, high signal-to-noise ratio, pure clean voice"

    def assemble(self) -> str:
        parts = [
            f"Speaker Persona: {self.persona}",
            f"Pitch & Prosody: {self.pitch_prosody}",
            f"Pacing & Delivery: {self.pacing_rules}",
            f"Pronunciation Rules: {self.pronunciation_rules}",
            f"Output Quality: {self.output_cleaning}"
        ]
        return "\n".join(parts)

class QualityRefiner:
    """
    Manages structured prompt construction, expands minimal inputs,
    enforces consistency across models, and detects actions for routing.
    """
    def __init__(self, config_path: Path | None = None) -> None:
        self.image_lib = DEFAULT_IMAGE_LIBRARY
        self.audio_lib = DEFAULT_AUDIO_LIBRARY

    def _verify_detail(self, subject: str) -> str:
        """
        Ensures the subject has descriptive qualifiers.
        """
        cleaned = subject.strip()
        known_roles = {"scrum master", "project manager", "product owner", "agile coach", "delivery lead"}
        if cleaned.lower() in known_roles:
            return cleaned
        words = cleaned.split()
        if len(words) < 3:
            # Underspecified: inject default details
            return f"professional, highly detailed, photorealistic {cleaned}"
        return cleaned

    def detect_action_and_route(self, prompt_text: str) -> dict[str, Any]:
        """
        Decision Tree checking if the prompt has active actions.
        Routes to Standard Image or Image-to-Video generation pipeline.
        Note: Every video starts with an image — this routes to video when action detected.
        """
        action_pattern = r"\b(walk|run|smil|turn|hold|point|talk|speak|spok|mov|wav|gestur|look|typ|gaz|writ|present|danc|jump|play|sit|stand)\w*"
        has_action = bool(re.search(action_pattern, prompt_text.lower()))

        return {
            "has_action": has_action,
            "recommended_mode": "video" if has_action else "image",
            "reason": "Action detected — image will be generated first, then video." if has_action else "Static subject — image only."
        }

    def refine_image_prompt(
        self,
        subject: str,
        clothing: str = "a navy blue blazer",
        obj: str = "a digital tablet showing an AI data dashboard",
        env_key: str = "office",
        light_key: str = "studio",
        camera_key: str = "standard",
        quality_key: str = "standard",
        style_key: str = "neutral",
        expanded_context: Optional[Any] = None,
    ) -> str:
        """
        Builds a rich image prompt.
        If expanded_context (PromptContext) is provided, uses the 7-dimension
        system from SmartPromptExpander for maximum detail and consistency.
        Falls back to template token-swapping when no context is given.
        """
        # If a SmartPromptExpander context is available, use it (highest quality path)
        if expanded_context is not None:
            try:
                from content_pipeline.bots.prompt_expander import SmartPromptExpander
                expander = SmartPromptExpander()
                return expander.build_image_prompt(expanded_context)
            except Exception:
                pass  # Fallback to template below

        subject = self._verify_detail(subject)

        # If clothing and obj are provided, we use the MASTER_IMAGE_TEMPLATE
        if clothing or obj:
            return MASTER_IMAGE_TEMPLATE.format(
                subject=subject,
                clothing=clothing,
                object=obj
            )

        # Otherwise, fall back to Lego-style assembly using keys
        env = self.image_lib["environments"].get(env_key, self.image_lib["environments"]["office"])
        light = self.image_lib["lightings"].get(light_key, self.image_lib["lightings"]["studio"])
        cam = self.image_lib["cameras"].get(camera_key, self.image_lib["cameras"]["standard"])
        qual = self.image_lib["quality_levers"].get(quality_key, self.image_lib["quality_levers"]["standard"])
        sty = self.image_lib["styles"].get(style_key, self.image_lib["styles"]["neutral"])

        blueprint = ImagePromptBlueprint(
            core_subject=subject,
            environment=env,
            lighting=light,
            camera=cam,
            quality_levers=qual,
            style=sty
        )
        return blueprint.assemble()

    def refine_video_prompt(
        self,
        subject: str,
        action: str = "holding a digital tablet showing glowing visualizations",
        env: str = "clean, brightly lit modern office",
        expanded_context: Optional[Any] = None,
    ) -> str:
        """
        Builds a rich video prompt anchored for motion stability.
        If expanded_context (PromptContext) is provided, uses the full 7-dimension
        system from SmartPromptExpander — the highest quality path.
        Falls back to MASTER_VIDEO_TEMPLATE for backward compatibility.
        """
        # Highest quality path: use SmartPromptExpander context if available
        if expanded_context is not None:
            try:
                from content_pipeline.bots.prompt_expander import SmartPromptExpander
                expander = SmartPromptExpander()
                return expander.build_video_prompt(expanded_context)
            except Exception:
                pass  # Fallback to template below

        subject = self._verify_detail(subject)
        return MASTER_VIDEO_TEMPLATE.format(
            subject=subject,
            action=action
        )

    def refine_audio_prompt(
        self,
        preset_key: str,
        persona_override: str = "",
        pitch_key: str = "stable",
        pacing_key: str = "calm",
        pron_key: str = "precise",
        expanded_context: Optional[Any] = None,
    ) -> str:
        """
        Builds standardized voice constraints using modular blocks.
        If expanded_context (PromptContext) is provided, uses the full
        voice profile from SmartPromptExpander for maximum character consistency.
        Falls back to audio library presets for backward compatibility.
        """
        # Highest quality path: use SmartPromptExpander context if available
        if expanded_context is not None:
            try:
                from content_pipeline.bots.prompt_expander import SmartPromptExpander
                expander = SmartPromptExpander()
                return expander.build_audio_prompt(expanded_context)
            except Exception:
                pass  # Fallback to presets below

        persona = persona_override if persona_override else self.audio_lib["personas"].get(preset_key, self.audio_lib["personas"]["corporate_male"])
        pitch = self.audio_lib["pitch_prosody"].get(pitch_key, self.audio_lib["pitch_prosody"]["stable"])
        pacing = self.audio_lib["pacing_rules"].get(pacing_key, self.audio_lib["pacing_rules"]["calm"])
        pron = self.audio_lib["pronunciation_rules"].get(pron_key, self.audio_lib["pronunciation_rules"]["precise"])
        cleaning = self.audio_lib["output_cleaning"]["studio"]

        blueprint = AudioPromptBlueprint(
            persona=persona,
            pitch_prosody=pitch,
            pacing_rules=pacing,
            pronunciation_rules=pron,
            output_cleaning=cleaning
        )
        return blueprint.assemble()

    @staticmethod
    def get_negative_prompt() -> str:
        """
        Returns the standardized Quality Control Negative Prompt.
        """
        return QUALITY_CONTROL_NEGATIVE_PROMPT
