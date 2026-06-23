"""
prompt_expander.py
==================
SmartPromptExpander — converts a short raw user prompt into a rich, structured
7-dimension prompt for each of the three media types:

    • Image  — Subject + Scene + Lighting + Quality + Negative anchors
    • Video  — All 7 dimensions including Motion + Camera Motion
    • Audio  — Subject + Voice Motion + Delivery Anchors + Quality

Design principles:
    - Zero VRAM, zero latency: pure rule-based NLP (regex + keyword matching).
    - Deterministic: same input always produces the same output.
    - Consistent: image and video prompts share the same subject/scene context,
      so the generated image and its derived video always look like the same scene.
    - Backward compatible: can be used standalone or injected into QualityRefiner.

Usage:
    from content_pipeline.bots.prompt_expander import SmartPromptExpander

    expander = SmartPromptExpander()
    ctx = expander.extract_context("girl walking in rain")
    print(expander.build_image_prompt(ctx))
    print(expander.build_video_prompt(ctx))
    print(expander.build_audio_prompt(ctx))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Layer 7: Negative Anchors — always injected at the end of every prompt
# ---------------------------------------------------------------------------

_UNIVERSAL_NEGATIVE_ANCHORS = (
    "No watermarks, no text overlays, no logos. "
    "No distorted or melted limbs, no extra fingers, no fused hands. "
    "No deformed or blurry face, no shaking eyes, no flickering features. "
    "No motion blur on the face or subject. "
    "No color banding, no pixelation, no visual artifacts. "
    "No subject too small or too distant — face must be clearly visible and sharp at all times."
)

_VIDEO_NEGATIVE_ANCHORS = (
    "No frame tearing, no ghosting, no motion blur on face. "
    "No floating feet, no sliding steps, no unnatural gait. "
    "No camera shake, no jitter, no abrupt cuts. "
    "No wide establishing shots that make the subject tiny or faceless. "
    "Feet must stay firmly on the ground with each step."
)

_AUDIO_NEGATIVE_ANCHORS = (
    "No background hiss, no mechanical noise, no static. "
    "No robotic tone, no unnatural pauses, no clipping. "
    "No swallowed syllables, no mispronunciations."
)


# ---------------------------------------------------------------------------
# Keyword libraries for smart extraction and defaults
# ---------------------------------------------------------------------------

# Subject detection
_FEMALE_KEYWORDS = ["girl", "woman", "lady", "female", "she", "her", "mother", "daughter", "sister"]
_MALE_KEYWORDS = ["man", "boy", "male", "he", "his", "father", "son", "brother", "gentleman"]

# Age inference — longest phrase first for correct matching
_AGE_CONTEXT = {
    "little girl": "a young girl (age 6-10)",
    "little boy": "a young boy (age 6-10)",
    "young girl": "a teenage girl (age 14-16)",
    "young boy": "a teenage boy (age 14-16)",
    "old man": "an elderly man in his 70s",
    "old woman": "an elderly woman in her 70s",
    "toddler": "a toddler (age 2-4)",
    "baby": "an infant",
    "infant": "an infant",
    "child": "a child (age 6-10)",
    "kid": "a child (age 6-10)",
    "elderly": "an elderly person in their 70s",
    "girl": "a young woman in her mid-20s",
    "woman": "a woman in her 30s",
    "lady": "a woman in her 30s",
    "man": "a man in his 30s",
    "boy": "a teenage boy (age 14-16)",
}

# Scene / Environment detection: keyword -> (description, scene_type, scene_category)
_SCENE_KEYWORDS: dict[str, tuple[str, str, str]] = {
    "forest": (
        "a dense green forest with tall trees, mossy undergrowth, and dappled natural light",
        "outdoor", "nature"
    ),
    "jungle": (
        "a lush tropical jungle with thick hanging foliage and filtered green light",
        "outdoor", "nature"
    ),
    "park": (
        "a peaceful city park with wide green lawns, winding stone paths, and scattered trees",
        "outdoor", "urban"
    ),
    "river": (
        "a calm river bank with gently flowing water, smooth pebbled ground, and soft reed grass",
        "outdoor", "nature"
    ),
    "beach": (
        "a sandy beach with gently rolling waves, clear blue sky, and warm golden sand",
        "outdoor", "nature"
    ),
    "mountain": (
        "a rocky mountain trail with panoramic valley views and crisp alpine air",
        "outdoor", "nature"
    ),
    "rain": (
        "a rain-soaked outdoor path with visible rainfall, small puddles reflecting the grey sky, "
        "and wet leaves on surrounding trees",
        "outdoor", "nature"
    ),
    "street": (
        "a wide urban street with modern architecture, ambient pedestrian traffic, and paved sidewalks",
        "outdoor", "urban"
    ),
    "office": (
        "a modern open-plan office with glass partitions, clean white desks, and soft ceiling lights",
        "indoor", "office"
    ),
    "studio": (
        "a professional photography studio with a clean white backdrop and soft box lighting rigs",
        "indoor", "studio"
    ),
    "home": (
        "a warmly lit living room with natural wood furniture, soft area rugs, and a large window",
        "indoor", "home"
    ),
    "kitchen": (
        "a clean, well-lit modern kitchen with marble countertops and stainless steel appliances",
        "indoor", "home"
    ),
    "school": (
        "a bright school classroom with rows of wooden desks, a whiteboard, and large windows",
        "indoor", "educational"
    ),
}

# Weather / time of day: keyword -> (lighting_description, color_temp)
_WEATHER_KEYWORDS: dict[str, tuple[str, str]] = {
    "rain": (
        "soft overcast diffused daylight through dense cloud cover, rain falling visibly "
        "in the foreground, wet surfaces reflecting ambient light",
        "cool blue-grey"
    ),
    "sunny": (
        "warm golden sunlight casting crisp soft shadows, clear open sky",
        "warm golden"
    ),
    "sunset": (
        "rich golden hour light from a low angle, long stretched shadows, amber glow on surfaces",
        "deep amber-orange"
    ),
    "night": (
        "cool moonlight combined with soft ambient artificial glow, deep blue-purple shadows",
        "cool deep blue"
    ),
    "morning": (
        "soft warm morning light with gentle diffused mist, low-angle sun creating subtle long shadows",
        "warm peach-gold"
    ),
    "cloudy": (
        "even soft diffused overcast light, no harsh shadows, uniform illumination across the scene",
        "cool neutral grey"
    ),
    "snow": (
        "bright reflected white light from snow-covered ground, crisp sharp winter atmosphere",
        "cold blue-white"
    ),
}

# Clothing defaults keyed by scene keyword
_CLOTHING_DEFAULTS: dict[str, str] = {
    "rain": "a vibrant yellow raincoat over a white long-sleeve shirt, dark slim jeans, and rubber ankle boots",
    "beach": "a light floral summer dress and open leather sandals",
    "forest": "a casual outdoor jacket, comfortable cargo pants, and sturdy hiking boots",
    "jungle": "lightweight breathable outdoor clothing, cargo trousers, and trail shoes",
    "mountain": "a warm fleece jacket, waterproof hiking trousers, and heavy hiking boots",
    "office": "a tailored navy blue blazer over a crisp white dress shirt and formal dark trousers",
    "studio": "a clean solid-color fitted top and tailored trousers in neutral tones",
    "home": "a soft chunky-knit sweater and loose comfortable linen trousers",
    "park": "a casual light jacket over a simple t-shirt, fitted jeans, and clean white sneakers",
    "street": "smart casual urban clothing — a slim bomber jacket, dark jeans, and clean leather shoes",
    "school": "casual everyday school clothes — a simple top and comfortable trousers",
    "default": "casual everyday clothing in neutral tones",
}

# Motion descriptions keyed by action verb found in raw prompt
_MOTION_LIBRARY: dict[str, str] = {
    "walk": (
        "walking at a relaxed, natural pace — feet planting firmly with each step, "
        "arms swinging gently at the sides, posture upright and natural"
    ),
    "run": (
        "jogging at a steady moderate pace — feet striking the ground rhythmically, "
        "arms pumping with each stride, posture slightly forward-leaning"
    ),
    "stand": (
        "standing still in a relaxed posture — slight natural weight shift, "
        "breathing visible, gaze directed naturally forward"
    ),
    "sit": (
        "seated comfortably — upper body gently upright, hands resting naturally, "
        "subtle micro-movements from breathing"
    ),
    "dance": (
        "dancing with fluid, expressive movements — arms graceful and responsive, "
        "weight shifting rhythmically with the implied music"
    ),
    "jump": (
        "jumping lightly and landing softly — feet together, arms briefly raised, "
        "natural impact absorption on landing"
    ),
    "talk": (
        "speaking expressively — natural hand gestures accompanying words, "
        "head nodding gently, eyebrows moving naturally with speech"
    ),
    "look": (
        "standing and looking around slowly — head turning gently side to side, "
        "eyes scanning the scene with curious attention"
    ),
    "play": (
        "playing actively with dynamic, joyful movements — expressions of enthusiasm, "
        "energy and spontaneity in each motion"
    ),
    "read": (
        "seated and reading attentively — eyes moving across the page, "
        "subtle page-turn motion, slight forward lean of concentration"
    ),
    "default": (
        "moving naturally and unhurriedly through the scene — posture relaxed, "
        "movements fluid and intentional, full body visible and stable"
    ),
}

# Camera motion keyed by scene category
_CAMERA_MOTION: dict[str, str] = {
    "nature": (
        "medium shot at eye level, subject filling 60% of frame, face clearly visible and centered, "
        "very slight natural sway as if handheld on a shoulder rig, "
        "subject's face and upper body always sharp and in focus"
    ),
    "urban": (
        "medium tracking shot following the subject from 2 meters behind and slightly to the side, "
        "subject's face and upper body visible, keeping the subject filling 50% of frame throughout"
    ),
    "office": (
        "slow gentle camera zoom-in toward the subject, starting from a medium wide shot "
        "and ending on a medium close-up — subject's face centered and sharp throughout"
    ),
    "studio": (
        "perfectly static front-facing medium shot, subject's face centered and fully in frame, "
        "no camera motion — clean and professional, face sharp"
    ),
    "home": (
        "gentle slow pan following the subject's movement at medium distance, "
        "face and upper body always in frame, warm intimate framing"
    ),
    "educational": (
        "static medium shot, subject's face and upper body fully visible, "
        "slight tilt to keep face centered, background context of the room visible"
    ),
    "default": (
        "medium shot with subtle slow dolly-forward, subject's face filling 50% of frame, "
        "face sharp and centered at all times, smooth cinematic movement throughout"
    ),
}

# Voice profiles for audio generation
_VOICE_PROFILES: dict[str, dict[str, str]] = {
    "girl": {
        "persona": "Warm, clear young female voice with gentle expressiveness and natural brightness",
        "pitch": "medium-high pitch, bright and clear chest-head resonance mix",
        "pacing": "measured pace at 130 words per minute with natural breathing pauses between sentences",
        "emotion": "calm and curious, with soft rises in intonation on key words for warmth",
    },
    "woman": {
        "persona": "Professional, composed female voice with warm authority and polished delivery",
        "pitch": "medium pitch, smooth and steady full chest resonance",
        "pacing": "deliberate pace at 120 words per minute with thoughtful pauses between ideas",
        "emotion": "confident and warm, with measured expressive variation on emphasis words",
    },
    "man": {
        "persona": "Deep, measured male voice with natural gravitas and clear articulation",
        "pitch": "medium-low pitch, full chest resonance with natural overtones",
        "pacing": "steady pace at 125 words per minute with deliberate breathing pauses",
        "emotion": "calm and assured, with subtle strategic emphasis on key words",
    },
    "child": {
        "persona": "Bright, energetic young child voice full of natural curiosity and openness",
        "pitch": "high pitch, light and airy with natural child-like breathiness",
        "pacing": "faster excited pace at 145 words per minute with short natural breaths",
        "emotion": "enthusiastic and playful, with wide expressive swings between wonder and delight",
    },
    "default": {
        "persona": "Clear, neutral narrator voice with even and consistent delivery",
        "pitch": "medium pitch, balanced resonance, no affectation",
        "pacing": "steady pace at 130 words per minute with natural sentence-end pauses",
        "emotion": "calm and clear delivery, professionally neutral",
    },
}


# ---------------------------------------------------------------------------
# PromptContext — the single shared context object for all 3 media types
# ---------------------------------------------------------------------------

@dataclass
class PromptContext:
    """
    Structured 7-dimension context extracted from a raw user prompt.
    Shared between image, video, and audio prompt builders to ensure consistency.

    Dimensions:
        1. subject_anchor      — WHO (description, age, gender, clothing)
        2. scene_environment   — WHERE (location, setting type, category)
        3. motion_description  — HOW they move [video / adapted for audio]
        4. camera_motion       — HOW camera moves [video only]
        5. lighting_profile    — WHAT the light looks like
        6. quality_modifiers   — HOW detailed/sharp the output should be
        7. negative_anchors    — WHAT must NOT appear
    """
    # Raw input
    subject_raw: str = ""

    # Dimension 1: Subject
    subject_gender: str = "female"
    subject_age_desc: str = "a young woman in her mid-20s"
    subject_clothing: str = ""
    subject_expression: str = "natural, relaxed expression"

    # Dimension 2: Scene
    scene_description: str = "an outdoor natural setting with soft ambient light"
    scene_type: str = "outdoor"
    scene_category: str = "nature"

    # Dimension 3: Motion
    motion_description: str = ""

    # Dimension 4: Camera Motion
    camera_motion: str = ""

    # Dimension 5: Lighting
    lighting_description: str = "soft diffused daylight, even illumination, no harsh shadows"
    lighting_color_temp: str = "neutral"

    # Dimension 6: Quality
    quality_modifiers: str = (
        "photorealistic, 4K ultra-high resolution, hyper-detailed textures on skin and clothing, "
        "sharp focus on subject's face and eyes, cinematic color grading, professional grade output"
    )

    # Dimension 7: Negative Anchors (type-specific)
    negative_anchors_image: str = _UNIVERSAL_NEGATIVE_ANCHORS
    negative_anchors_video: str = _UNIVERSAL_NEGATIVE_ANCHORS + " " + _VIDEO_NEGATIVE_ANCHORS
    negative_anchors_audio: str = _AUDIO_NEGATIVE_ANCHORS

    # Voice profile for audio generation
    voice_profile: dict = field(default_factory=dict)

    # Internal tracking
    _scene_keyword: str = ""


# ---------------------------------------------------------------------------
# SmartPromptExpander — the main class
# ---------------------------------------------------------------------------

class SmartPromptExpander:
    """
    Converts a short raw user prompt into fully expanded 7-dimension prompts
    for image, video, and audio generation.

    Features:
    - Zero VRAM: pure rule-based extraction, runs instantly on CPU.
    - Consistent: image and video share the same subject + scene context
      (critical since every video starts from a generated image).
    - Controllable: detail_level = "minimal" | "standard" | "full"

    Example:
        expander = SmartPromptExpander()
        ctx = expander.extract_context("girl walking in rain")
        image_prompt  = expander.build_image_prompt(ctx)
        video_prompt  = expander.build_video_prompt(ctx)
        audio_prompt  = expander.build_audio_prompt(ctx)
    """

    def extract_context(self, raw_prompt: str, detail_level: str = "full") -> PromptContext:
        """
        Parse raw prompt text into a fully populated PromptContext.

        Args:
            raw_prompt:   Short user input (e.g. "girl walking in rain forest")
            detail_level: "minimal" | "standard" | "full"

        Returns:
            PromptContext with all 7 dimensions filled.
        """
        text = raw_prompt.lower().strip()
        ctx = PromptContext(subject_raw=raw_prompt)

        # --- Dimension 1: Subject ---
        ctx.subject_gender = self._detect_gender(text)
        ctx.subject_age_desc = self._detect_age(text)
        scene_kw = self._detect_scene_keyword(text)
        ctx._scene_keyword = scene_kw
        ctx.subject_clothing = _CLOTHING_DEFAULTS.get(scene_kw, _CLOTHING_DEFAULTS["default"])
        ctx.subject_expression = self._detect_expression(text)

        # --- Dimension 2: Scene ---
        scene_info = _SCENE_KEYWORDS.get(scene_kw)
        if scene_info:
            ctx.scene_description, ctx.scene_type, ctx.scene_category = scene_info
        else:
            ctx.scene_description = "an outdoor natural setting with soft ambient light"
            ctx.scene_type = "outdoor"
            ctx.scene_category = "nature"

        # --- Dimension 3: Motion ---
        ctx.motion_description = self._detect_motion(text)

        # --- Dimension 4: Camera Motion ---
        ctx.camera_motion = _CAMERA_MOTION.get(ctx.scene_category, _CAMERA_MOTION["default"])

        # --- Dimension 5: Lighting ---
        ctx.lighting_description, ctx.lighting_color_temp = self._detect_lighting(text, scene_kw)

        # --- Dimension 6: Quality ---
        ctx.quality_modifiers = self._build_quality_string(detail_level)

        # --- Voice profile for audio ---
        ctx.voice_profile = self._pick_voice_profile(ctx.subject_gender, ctx.subject_age_desc)

        return ctx

    # ------------------------------------------------------------------
    # Public prompt builders
    # ------------------------------------------------------------------

    def build_image_prompt(self, ctx: PromptContext) -> str:
        """
        Build a detailed image generation prompt (Dimensions 1, 2, 5, 6, 7).
        No motion or camera — it's a still image.
        """
        return (
            f"Photorealistic digital photograph. "
            f"Subject: {ctx.subject_age_desc}, wearing {ctx.subject_clothing}, "
            f"with a {ctx.subject_expression}. "
            f"Setting: {ctx.scene_description}. "
            f"Lighting: {ctx.lighting_description}, color temperature {ctx.lighting_color_temp}. "
            f"Shot on a full-frame digital cinema camera, shallow depth of field, "
            f"sharp focus on the subject's face and clothing detail. "
            f"Quality: {ctx.quality_modifiers}. "
            f"{ctx.negative_anchors_image}"
        )

    def build_video_prompt(self, ctx: PromptContext) -> str:
        """
        Build a detailed video generation prompt using all 7 dimensions.
        """
        return (
            f"Cinematic video clip shot on a digital cinema camera. "
            f"Subject: {ctx.subject_age_desc}, wearing {ctx.subject_clothing}, "
            f"with a {ctx.subject_expression}. "
            f"Scene: {ctx.scene_description}. "
            f"Motion: {ctx.motion_description}. "
            f"Natural weight and physics — clothing and hair move with body momentum. "
            f"Camera: {ctx.camera_motion}. "
            f"Lighting: {ctx.lighting_description}, color temperature {ctx.lighting_color_temp}. "
            f"No harsh shadows, consistent exposure throughout the clip. "
            f"Quality: {ctx.quality_modifiers}. "
            f"Smooth 24fps, sharp focus on subject's face and eyes at all times. "
            f"{ctx.negative_anchors_video}"
        )

    def build_audio_prompt(self, ctx: PromptContext) -> str:
        """
        Build a detailed audio/voice generation prompt (Dimensions 1, 3-adapted, 4-adapted, 6, 7).
        """
        vp = ctx.voice_profile
        return "\n".join([
            f"Speaker Persona: {vp.get('persona', 'Clear, neutral narrator voice')}.",
            f"Pitch & Resonance: {vp.get('pitch', 'medium pitch, balanced resonance')}.",
            f"Pacing & Delivery: {vp.get('pacing', 'steady pace at 130 words per minute')}.",
            f"Emotional Arc: {vp.get('emotion', 'calm and clear delivery')}.",
            f"Output Quality: pristine studio recording, no background hiss, "
            f"high signal-to-noise ratio, pure clean voice.",
            ctx.negative_anchors_audio,
        ])

    # ------------------------------------------------------------------
    # Internal extraction helpers
    # ------------------------------------------------------------------

    def _detect_gender(self, text: str) -> str:
        for kw in _FEMALE_KEYWORDS:
            if kw in text:
                return "female"
        for kw in _MALE_KEYWORDS:
            if kw in text:
                return "male"
        return "female"

    def _detect_age(self, text: str) -> str:
        # Sort longest phrase first to avoid partial matches ("girl" matching inside "young girl")
        for phrase, desc in sorted(_AGE_CONTEXT.items(), key=lambda x: -len(x[0])):
            if phrase in text:
                return desc
        return "a young woman in her mid-20s"

    def _detect_scene_keyword(self, text: str) -> str:
        # Priority order: specific weather/biome first
        priority = [
            "rain", "snow", "beach", "river", "jungle", "forest",
            "mountain", "park", "street", "office", "studio", "home", "kitchen", "school"
        ]
        for kw in priority:
            if kw in text:
                return kw
        return "park"

    def _detect_expression(self, text: str) -> str:
        if any(w in text for w in ["happy", "smile", "smiling", "joy", "laugh", "laughing"]):
            return "warm, genuine smile"
        if any(w in text for w in ["sad", "cry", "crying", "tears", "grief", "sorrow"]):
            return "gentle, contemplative sadness"
        if any(w in text for w in ["scared", "fear", "frightened", "panic", "terror"]):
            return "wide-eyed, alert and cautious expression"
        if any(w in text for w in ["angry", "mad", "furious", "rage"]):
            return "focused, tense and determined expression"
        if any(w in text for w in ["curious", "wonder", "amazed", "surprised"]):
            return "wide-eyed, curious and open expression"
        return "natural, relaxed and comfortable expression"

    def _detect_motion(self, text: str) -> str:
        for verb, desc in _MOTION_LIBRARY.items():
            if verb != "default" and verb in text:
                return desc
        return _MOTION_LIBRARY["default"]

    def _detect_lighting(self, text: str, scene_keyword: str) -> tuple[str, str]:
        # Check explicit weather/time-of-day keywords first
        for kw, (lighting, color) in _WEATHER_KEYWORDS.items():
            if kw in text:
                return lighting, color
        # Fall back to scene-based lighting defaults
        fallbacks: dict[str, tuple[str, str]] = {
            "forest": ("soft dappled light filtering through tree canopy, gentle leaf shadows", "cool green-tinted neutral"),
            "jungle": ("dense green-filtered canopy light, high humidity atmospheric haze", "warm green-gold"),
            "mountain": ("crisp direct alpine sunlight, clear atmosphere, sharp shadows", "cold bright white"),
            "river": ("open sky soft light reflecting off the water surface, bright and even", "cool blue-white"),
            "beach": ("bright open sky light with warm sand reflection, even high-key illumination", "warm golden-white"),
            "office": ("professional even LED ceiling lighting supplemented by window natural light", "neutral daylight white"),
            "studio": ("professional soft box studio lighting, perfectly even, shadow-free", "neutral daylight white 5500K"),
            "home": ("warm interior ambient lighting supplemented by soft window light", "warm amber 3200K"),
            "school": ("bright fluorescent ceiling light with natural window supplementation", "cool white"),
        }
        if scene_keyword in fallbacks:
            return fallbacks[scene_keyword]
        return "soft diffused daylight, even illumination, no harsh shadows", "neutral"

    def _build_quality_string(self, detail_level: str) -> str:
        if detail_level == "minimal":
            return "photorealistic, sharp focus, clean composition"
        if detail_level == "standard":
            return (
                "photorealistic, 4K resolution, sharp focus on face and eyes, "
                "clean composition, no compression artifacts"
            )
        # "full" — maximum quality specification
        return (
            "photorealistic, 4K ultra-high resolution, hyper-detailed textures on skin and clothing, "
            "razor-sharp focus on subject's face and eyes, face clearly visible and never blurry, "
            "clean composition, no compression artifacts, "
            "cinematic color grading, film-grain free, professional grade output"
        )

    def _pick_voice_profile(self, gender: str, age_desc: str) -> dict:
        age_lower = age_desc.lower()
        if any(w in age_lower for w in ["toddler", "infant", "age 2", "age 3", "age 4"]):
            return _VOICE_PROFILES["child"]
        if any(w in age_lower for w in ["child", "age 6", "age 7", "age 8", "age 9", "age 10"]):
            return _VOICE_PROFILES["child"]
        if gender == "female":
            if any(w in age_lower for w in ["young", "teen", "mid-20", "age 14", "age 16"]):
                return _VOICE_PROFILES["girl"]
            return _VOICE_PROFILES["woman"]
        if gender == "male":
            return _VOICE_PROFILES["man"]
        return _VOICE_PROFILES["default"]


# ---------------------------------------------------------------------------
# Standalone test — python -m content_pipeline.bots.prompt_expander
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    expander = SmartPromptExpander()

    test_cases = [
        "girl walking in rain",
        "young boy playing in forest",
        "woman standing in office",
        "little girl running on beach",
        "man talking in studio",
    ]

    for raw in test_cases:
        print(f"\n{'=' * 70}")
        print(f"RAW INPUT : {raw}")
        print(f"{'=' * 70}")
        ctx = expander.extract_context(raw)
        print(f"\n[IMAGE]\n{expander.build_image_prompt(ctx)}")
        print(f"\n[VIDEO]\n{expander.build_video_prompt(ctx)}")
        print(f"\n[AUDIO]\n{expander.build_audio_prompt(ctx)}")