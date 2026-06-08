from __future__ import annotations

import asyncio
import json
import math
import struct
import re
import wave
from dataclasses import asdict, dataclass
from html import escape
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.bots.gemini_tts import generate_gemini_voiceover
from pydub import AudioSegment
import numpy as np
import scipy.signal as signal


def is_vocal_track(filename: str) -> bool:
    """Checks if a reference track is known to contain vocals/singing."""
    fn_lower = filename.lower()
    # If the file contains 'instrumental' or 'bgm' or 'beat', it is vocal-free
    if any(x in fn_lower for x in ["instrumental", "bgm", "beat", "karaoke"]):
        return False
    # By default, assume reference files contain vocals unless they are explicitly marked as instrumental
    return True


HINDI_PRONUNCIATION_TEXT = (
    "गोकुल की सुनहरी सुबह में, मैया यशोदा ने पुकारा, कान्हा! "
    "मेरे प्यारे कान्हा, कहाँ छिपे हो? नन्हे कान्हा मुस्कुराते हुए बोले, "
    "मैया, मैं यहीं हूँ।"
)
HINDI_PRONUNCIATION_INSTRUCTIONS = (
    "शुद्ध, स्वाभाविक भारतीय हिंदी में बोलें। नामों का उच्चारण विशेष ध्यान से करें: "
    "गोकुल को गो-कुल, यशोदा को य-शो-दा, कान्हा को कान्-हा उच्चारित करें। "
    "अंग्रेज़ी प्रभाव वाला उच्चारण न करें। बच्चों की कृष्ण कहानी के लिए "
    "स्नेही, भावपूर्ण और स्पष्ट कथावाचक स्वर रखें।"
)
FREE_INDIAN_EDGE_VOICE_VARIANTS = [
    ("sample_01_prabhat_neural.mp3", "en-IN-PrabhatNeural", "Warm Indian English male voice for professional narration."),
    ("sample_02_neerja_neural.mp3", "en-IN-NeerjaNeural", "Warm Indian English female voice for clear storytelling."),
    ("sample_03_swara_neural.mp3", "hi-IN-SwaraNeural", "Clear Hindi female voice for family-friendly narration."),
    ("sample_04_madhur_neural.mp3", "hi-IN-MadhurNeural", "Clear Hindi male voice for stronger Hindi narration."),
]

MUSIC_PRESETS: dict[str, tuple[list[float], float]] = {
    "cinematic": ([174.0, 261.63, 392.0], 0.18),
    "focus": ([196.0, 246.94, 293.66], 0.14),
    "warm": ([164.81, 220.0, 261.63], 0.12),
    "uplift": ([220.0, 329.63, 392.0], 0.16),
    "ambient": ([130.81, 196.0, 261.63], 0.10),
    "nursery": ([523.25, 659.25, 783.99, 1046.50], 0.15),
}


SOUNDSCAPE_PRESETS: dict[str, dict[str, Any]] = {
    "Meditative Acoustic (Shekhar Style)": {
        "style_description": "Pure instrumental. Soft fingerpicked acoustic guitar arpeggios, deep warm bass guitar, airy ambient synthesizer pads, soulful solo bansuri flute, gentle meditative pace, 65 BPM, sacred hall acoustics.",
        "temperature": 0.30,
        "genre": "Auto"
    },
    "Epic Classical Cinematic": {
        "style_description": "Pure instrumental. Booming traditional dhol and taiko percussion layers, heavy dramatic orchestral string sections, deep brass swells, rhythmic sitar strabs, massive stadium echo, fast tempo, 115 BPM.",
        "temperature": 0.35,
        "genre": "Auto"
    },
    "Soulful Sufi / Ghazal Studio": {
        "style_description": "Pure instrumental. Traditional hand-pumped wooden harmonium sweeps, organic acoustic tabla loops, calm acoustic sarangi strokes, slow steady studio recording, 80 BPM, clean proximity environment.",
        "temperature": 0.30,
        "genre": "Auto"
    }
}


@dataclass(frozen=True)
class VoiceEngineProfile:
    name: str
    language: str
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    style: str = ""


@dataclass(frozen=True)
class VoicePreviewPreset:
    key: str
    label: str
    description: str
    provider: str
    voice: str
    language: str
    gender: str
    sample_text: str
    rate: str = "+0%"
    pitch: str = "+0Hz"


@dataclass(frozen=True)
class ReferenceAudioSample:
    collection: str
    language: str
    path: str
    source_label: str


def humanize_child_pacing_punctuation(text: str) -> str:
    """
    Injects realistic toddler breathing pauses using punctuation (ellipses and spaces)
    instead of XML break tags, which the service rejects.
    """
    processed = text.strip()
    processed = re.sub(r"!\s*", "...!  ", processed)
    processed = re.sub(r",\s*", ", ...  ", processed)
    processed = re.sub(r"\.\s*", "...  ", processed)
    processed = re.sub(r"\?\s*", "...?  ", processed)
    return processed


def inject_dramatic_story_pauses_punctuation(text: str) -> str:
    """
    Translates dramatic storytelling XML pauses into natural punctuation pacing
    (ellipses, commas, and extra spaces) to safely bypass Microsoft's tag block.
    """
    processed = text.strip()
    processed = re.sub(r",\s*", ", ...  ", processed)
    processed = re.sub(r"\.\s*", ". ...   ", processed)
    processed = re.sub(r"\?\s*", "? ...   ", processed)
    return processed


VOICE_PREVIEW_PRESETS: tuple[VoicePreviewPreset, ...] = (
    VoicePreviewPreset(
        key="indian_english_corporate_male",
        label="Professional Corporate Man (Mature Deep Tone)",
        description="Warm, mature corporate male voice with authoritative pacing and senior resonance.",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        language="en-IN",
        gender="male",
        sample_text=(
            "Good morning, and welcome to this comprehensive industry analysis. "
            "Today, we are examining a critical market paradigm shift: "
            "How the next generation of freshers is leveraging artificial intelligence to outpace traditional career trajectories."
        ),
        rate="-6%",
        pitch="-4Hz",
    ),
    VoicePreviewPreset(
        key="toddler_girl",
        label="3-4 Year Old Little Girl (Common English/Hindi)",
        description="Cute, native 3-year-old female child voice with natural toddler breathing pacing.",
        provider="edge",
        voice="en-US-AnaNeural",
        language="all",
        gender="female",
        sample_text=(
            "Look look! A friendly robot is here! It is holding my hand and helping me win the career race! Yay!"
        ),
        rate="+8%",
        pitch="+3Hz",
    ),
    VoicePreviewPreset(
        key="toddler_boy",
        label="3-4 Year Old Little Boy (Common English/Hindi)",
        description="Cute, native 4-year-old male child voice with natural toddler breathing pacing.",
        provider="edge",
        voice="en-US-AnaNeural",
        language="all",
        gender="male",
        sample_text=(
            "Wow! See that big shiny computer? The robot is typing so fast! Zoom zoom! We are running very fast!"
        ),
        rate="+2%",
        pitch="-3Hz",
    ),
    VoicePreviewPreset(
        key="story_female",
        label="Soothing Female Storyteller (Common English/Hindi)",
        description="Calm, maternal, soothing story narration voice for bedside or educational tellings.",
        provider="edge",
        voice="en-IN-NeerjaNeural",
        language="all",
        gender="female",
        sample_text=(
            "Once upon a time, in a world moving faster than light, a young fresher stood at the edge of a massive career race. "
            "The stadium was filled with heavy competition, and the old corporate walls looked impossibly tall."
        ),
        rate="-12%",
        pitch="-2Hz",
    ),
    VoicePreviewPreset(
        key="story_male",
        label="Deep Charismatic Male Storyteller (Common English/Hindi)",
        description="Deep, grandfatherly baritone storyteller pacing for documentaries and motivational clips.",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        language="all",
        gender="male",
        sample_text=(
            "Once upon a time, in a world moving faster than light, a young fresher stood at the edge of a massive career race. "
            "The stadium was filled with heavy competition, and the old corporate walls looked impossibly tall."
        ),
        rate="-15%",
        pitch="-4Hz",
    ),
    VoicePreviewPreset(
        key="english_explainer",
        label="Both (English-Hindi) explainer",
        description="Clear English-Hindi mix narration for tutorials and walkthroughs.",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        language="en-IN",
        gender="male",
        sample_text=(
            "Let's break this workflow into simple steps. Hum dynamic presets use karenge and then we will explain the code flow clearly."
        ),
    ),
    VoicePreviewPreset(
        key="storyteller_common",
        label="Storyteller (Common English/Hindi)",
        description="A warm storytelling voice, common for both English and Hindi narration.",
        provider="edge",
        voice="en-IN-NeerjaNeural",
        language="all",
        gender="female",
        sample_text=(
            "Once upon a time, Ek pyaare se workflow mein, a small team learned to trust its process, refine every step, and ship with confidence."
        ),
    ),
    VoicePreviewPreset(
        key="hindi_devotional",
        label="Hindi devotional",
        description="Gentle Hindi narration for spiritual, devotional, or cultural scripts.",
        provider="edge",
        voice="hi-IN-SwaraNeural",
        language="hi-IN",
        gender="female",
        sample_text=(
            "वृंदावन की पवित्र गलियों में, श्यामसुंदर की लीलाएँ हर मन को भक्ति और शांति से भर देती हैं।"
        ),
    ),
    VoicePreviewPreset(
        key="hindi_bulletin",
        label="Hindi bulletin",
        description="Crisp Hindi narration for announcements and short updates.",
        provider="edge",
        voice="hi-IN-SwaraNeural",
        language="hi-IN",
        gender="female",
        sample_text=(
            "आज की मुख्य खबर यह है कि टीम ने अपने सभी लक्ष्य समय पर पूरे कर लिए हैं और अगला चरण शुरू हो चुका है।"
        ),
    ),
    VoicePreviewPreset(
        key="hinglish_teacher",
        label="Both (Hinglish) teacher",
        description="Friendly Hindi-English mix for learning content.",
        provider="edge",
        voice="en-IN-NeerjaNeural",
        language="en-IN",
        gender="female",
        sample_text=(
            "Aaj hum simple steps mein samjhenge kaise AI, Jira, aur Scrum ko smart way se use karte hain."
        ),
    ),
    VoicePreviewPreset(
        key="hindi_explainer",
        label="Hindi explainer",
        description="Professional Hindi narration with a calm teaching tone.",
        provider="edge",
        voice="hi-IN-SwaraNeural",
        language="hi-IN",
        gender="female",
        sample_text=(
            "आज हम इस विषय को सरल और स्पष्ट तरीके से समझेंगे, ताकि हर कदम आसानी से याद रहे।"
        ),
    ),
    VoicePreviewPreset(
        key="hindi_explainer_male",
        label="Hindi explainer male (Standard)",
        description="Professional Hindi-style narration with a steadier male tone.",
        provider="edge",
        voice="hi-IN-MadhurNeural",
        language="hi-IN",
        gender="male",
        sample_text=(
            "आज हम इस विषय को सरल और स्पष्ट तरीके से समझेंगे, ताकि हर कदम आसानी से याद रहे।"
        ),
        rate="+0%",
        pitch="+0Hz",
    ),
    VoicePreviewPreset(
        key="hindi_wisdom_narrator",
        label="Hindi philosophical narrator (Your Shared Tone)",
        description="A calm, composed, and standard Hindi male voice matching your shared audio samples perfectly.",
        provider="edge",
        voice="hi-IN-MadhurNeural",
        language="hi-IN",
        gender="male",
        sample_text=(
            "व्यक्ति को मात्र इसलिए कि वह ज्ञानी है स्वीकार करने की अनुमति नहीं, बल्कि उसके आचरण और व्यवहार को भी देखना आवश्यक है।"
        ),
        rate="+5%",
        pitch="+0Hz",
    ),
    VoicePreviewPreset(
        key="hindi_energetic_male",
        label="Hindi energetic male",
        description="Upbeat and fast-paced Hindi male narration, perfect for technology, marketing, and dynamic explainers.",
        provider="edge",
        voice="hi-IN-MadhurNeural",
        language="hi-IN",
        gender="male",
        sample_text=(
            "आज का क्विक टिप बिल्कुल सिंपल है: प्लानिंग को छोटा रखें, एक्सेक्यूशन को शार्प रखें, और हर कदम पर क्लैरिटी बनाए रखें।"
        ),
        rate="+14%",
        pitch="+0Hz",
    ),
    VoicePreviewPreset(
        key="hindi_deep_narrator",
        label="Hindi deep narrator",
        description="A slowed-down, deep-pitched male voice suitable for storytelling, spiritual, and dramatic content.",
        provider="edge",
        voice="hi-IN-MadhurNeural",
        language="hi-IN",
        gender="male",
        sample_text=(
            "समय की गति को धीमा करके, जब हम अपने भीतर की आवाज़ सुनते हैं, तो हर मुश्किल का हल अपने आप मिल जाता है।"
        ),
        rate="-8%",
        pitch="-3Hz",
    ),
    VoicePreviewPreset(
        key="hinglish_guru_male",
        label="Both (Hinglish) tech-guru male",
        description="Conversational Hinglish (Hindi-English blend) male voice, ideal for tutorial presentations.",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        language="en-IN",
        gender="male",
        sample_text=(
            "Hey techies! Aaj hum simple steps mein samjhenge ki kaise hum workflow ko organize aur automatically deploy kar sakte hain."
        ),
        rate="+0%",
        pitch="+0Hz",
    ),
    VoicePreviewPreset(
        key="hinglish_pitch_male",
        label="Both (Hinglish) high-energy pitch",
        description="High-impact, fast Hinglish male voice perfect for startup pitches, ads, and short-form video formats.",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        language="en-IN",
        gender="male",
        sample_text=(
            "Chalo fast flow maintain karte hain! Planning ko simplify karo, execution ko full-speed push karo, aur team ko lead karo."
        ),
        rate="+12%",
        pitch="+1Hz",
    ),
    VoicePreviewPreset(
        key="hindi_corporate_male",
        label="Hindi corporate executive",
        description="A formal, slow, and authoritative Hindi male narration for corporate, training, and executive modules.",
        provider="edge",
        voice="hi-IN-MadhurNeural",
        language="hi-IN",
        gender="male",
        sample_text=(
            "संगठन की सफलता हमारी प्रतिबद्धता और व्यवस्थित कार्यप्रणाली पर निर्भर करती है। आज हम इसके मुख्य सिद्धांतों की समीक्षा करेंगे।"
        ),
        rate="-5%",
        pitch="+1Hz",
    ),
    VoicePreviewPreset(
        key="motivation_boost",
        label="Motivation boost (Both English/Hindi)",
        description="Bright, energetic delivery for motivational clips, blending English and Hindi.",
        provider="edge",
        voice="en-IN-PrabhatNeural",
        language="en-IN",
        gender="male",
        sample_text=(
            "This is your reminder to keep going. Har din thoda aur hard work karo, small improvements lead to a powerful result!"
        ),
        rate="+5%",
        pitch="+0Hz",
    ),
    VoicePreviewPreset(
        key="gemini_rasalgethi",
        label="Gemini Captain (Rasalgethi - High-Energy Sci-Fi)",
        description="A smooth, premium authoritative commercial voice from Gemini 2.5 TTS.",
        provider="gemini",
        voice="Rasalgethi",
        language="en-US",
        gender="male",
        sample_text=(
            "[Sound: Loud, frantic alarm buzzing] Everyone, report to stations! The ship is shaking! [Excited] We’re entering the Nebula of Floating Fun!"
        ),
    ),
    VoicePreviewPreset(
        key="gemini_puck",
        label="Gemini Pilot (Puck - Youthful & Energetic)",
        description="A bright, energetic, and highly expressive youthful voice from Gemini 2.5 TTS.",
        provider="gemini",
        voice="Puck",
        language="en-US",
        gender="male",
        sample_text=(
            "[Sound: Whoosh of air] Whoa! [Surprised] Captain! My controls are going wild! Everything is starting to float—my snacks, my tablet, even my seat!"
        ),
    ),
    VoicePreviewPreset(
        key="gemini_charon",
        label="Gemini Tech Specialist (Charon - Quick & Smart)",
        description="A quick, tech-sounding deep voice from Gemini 2.5 TTS, ideal for narration or tech dialogue.",
        provider="gemini",
        voice="Charon",
        language="en-US",
        gender="male",
        sample_text=(
            "[Sound: Electronic beeping and sparking] I’m on it! I'm recalibrating the gravity drive now! [Determined] Hold on tight, team, we’re going to steady this ship!"
        ),
    ),
    VoicePreviewPreset(
        key="gemini_kore",
        label="Gemini Kore (Warm Storytelling Voice)",
        description="A warm, clear, and reassuring female storytelling voice from Gemini 2.5 TTS.",
        provider="gemini",
        voice="Kore",
        language="en-US",
        gender="female",
        sample_text=(
            "Once upon a time, deep within the heart of a cosmic nebula, a crew of brave children discovered a mystery that would change space travel forever."
        ),
    ),
    VoicePreviewPreset(
        key="gemini_fenrir",
        label="Gemini Fenrir (Bold Corporate Tone)",
        description="A bold, authoritative, and direct masculine voice from Gemini 2.5 TTS.",
        provider="gemini",
        voice="Fenrir",
        language="en-US",
        gender="male",
        sample_text=(
            "System update complete. Atmospheric pressure is stable, but gravity coordinates require a manual override."
        ),
    ),
    VoicePreviewPreset(
        key="gemini_aoede",
        label="Gemini Aoede (Gentle Conversational Voice)",
        description="A gentle, conversational, and highly friendly female voice from Gemini 2.5 TTS.",
        provider="gemini",
        voice="Aoede",
        language="en-US",
        gender="female",
        sample_text=(
            "Don't worry, everyone. Keep your safety harnesses secured. The gravity drive will be back online in just a moment."
        ),
    ),
)


def generate_hindi_voice_samples(
    settings: Settings,
    destination: Path,
    *,
    engine: str = "edge",
) -> list[Path]:
    engine = (engine or "edge").strip().lower()
    if engine != "edge":
        raise ValueError("Edge TTS is the only supported engine for narration samples.")
    destination.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for filename, voice, additional_instruction in FREE_INDIAN_EDGE_VOICE_VARIANTS:
        output_path = destination / filename
        _run_async(
            _write_edge_voice_sample(
                output_path,
                voice=voice,
                text=HINDI_PRONUNCIATION_TEXT,
                instructions=HINDI_PRONUNCIATION_INSTRUCTIONS + " " + additional_instruction,
            )
        )
        files.append(output_path)
    return files


def build_voice_profile(
    *,
    provider: str = "edge",
    language: str = "hi-IN",
    voice: str = "en-IN-PrabhatNeural",
) -> VoiceEngineProfile:
    provider = (provider or "edge").strip().lower()
    engine_name = "edge-tts" if provider == "edge" else "manifest-only"
    return VoiceEngineProfile(
        name=engine_name,
        language=language,
        voice=voice,
        rate="+0%",
        pitch="+0Hz",
    )


def _voice_gender(provider: str, voice: str) -> str:
    provider = (provider or "").strip().lower()
    voice = (voice or "").strip()
    gender_map = {
        "edge": {
            "en-IN-PrabhatNeural": "male",
            "en-IN-NeerjaNeural": "female",
            "hi-IN-SwaraNeural": "female",
            "hi-IN-MadhurNeural": "male",
            "hi-IN-AaravNeural": "male",
            "en-US-AnaNeural": "female",
            "en-US-EricNeural": "male",
        },
    }
    return gender_map.get(provider, {}).get(voice, "neutral")


def available_voice_options(provider: str, gender: str = "all") -> list[tuple[str, str]]:
    provider = (provider or "edge").strip().lower()
    if provider != "edge":
        raise ValueError("Voice options are available for provider='edge' only.")
    gender = (gender or "all").strip().lower()
    options = [(voice, f"{voice} - {description}") for _, voice, description in FREE_INDIAN_EDGE_VOICE_VARIANTS]
    if gender == "all":
        return options
    return [option for option in options if _voice_gender(provider, option[0]) == gender]


def voice_preview_presets() -> tuple[VoicePreviewPreset, ...]:
    return VOICE_PREVIEW_PRESETS


def voice_gender_options() -> tuple[tuple[str, str], ...]:
    return (
        ("all", "All voices"),
        ("male", "Male voices"),
        ("female", "Female voices"),
        ("neutral", "Neutral voices"),
    )


def filter_voice_preview_presets(
    presets: tuple[VoicePreviewPreset, ...],
    *,
    language: str = "all",
    gender: str = "all",
) -> tuple[VoicePreviewPreset, ...]:
    language = (language or "all").strip().lower()
    gender = (gender or "all").strip().lower()
    filtered = []
    for preset in presets:
        preset_lang = preset.language.strip().lower()
        preset_gender = preset.gender.strip().lower()
        
        # Match language
        if language == "all" or preset_lang == "all":
            lang_match = True
        elif language == "en-us":  # "English" filter: matches en-us, en-in, and all
            lang_match = preset_lang in ("en-us", "en-in")
        elif language == "en-in":  # "Both" filter: matches en-in (Hinglish) and all
            lang_match = preset_lang == "en-in"
        elif language == "hi-in":  # "Hindi" filter: matches hi-in and all
            lang_match = preset_lang == "hi-in"
        else:
            lang_match = (preset_lang == language)
            
        # Match gender
        gender_match = (
            gender == "all"
            or preset_gender == "all"
            or preset_gender == gender
        )
        if lang_match and gender_match:
            filtered.append(preset)
    return tuple(filtered)


def voice_preview_language_options() -> tuple[tuple[str, str], ...]:
    return (
        ("all", "All languages"),
        ("en-US", "English"),
        ("hi-IN", "Hindi"),
        ("en-IN", "Both"),
    )


def reference_audio_language_options(languages: list[str] | None = None) -> tuple[tuple[str, str], ...]:
    labels = {
        "all": "All languages",
        "bengali": "Bengali",
        "gujarati": "Gujarati",
        "hindi": "Hindi",
        "kannada": "Kannada",
        "malayalam": "Malayalam",
        "marathi": "Marathi",
        "punjabi": "Punjabi",
        "tamil": "Tamil",
        "telugu": "Telugu",
        "urdu": "Urdu",
    }
    if languages is None:
        languages = [
            "bengali",
            "gujarati",
            "hindi",
            "kannada",
            "malayalam",
            "marathi",
            "punjabi",
            "tamil",
            "telugu",
            "urdu",
        ]
    ordered = ["all", *[language for language in languages if language != "all"]]
    seen: list[str] = []
    for language in ordered:
        if language not in seen:
            seen.append(language)
    return tuple((language, labels.get(language, language.title())) for language in seen)


def scan_reference_audio_library(root: Path, *, default_language: str = "unknown") -> list[ReferenceAudioSample]:
    if not root.exists():
        return []
    samples: list[ReferenceAudioSample] = []
    files = [path for path in root.rglob("*") if path.is_file()]
    flat_collection = bool(files) and all(path.parent == root for path in files)
    for path in sorted(files):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = path
        collection = relative.parts[0] if len(relative.parts) > 1 else root.name
        collection = collection.strip().lower() or "unknown"
        language = relative.parts[0] if len(relative.parts) > 1 else default_language
        language = language.strip().lower() or "unknown"
        source_label = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
        samples.append(
            ReferenceAudioSample(
                collection=collection,
                language=language,
                path=str(path),
                source_label=source_label,
            )
        )
    if flat_collection:
        samples = [
            ReferenceAudioSample(
                collection=root.name.lower() or "reference_audio",
                language=(default_language or "unknown").strip().lower() or "unknown",
                path=sample.path,
                source_label=sample.source_label,
            )
            for sample in samples
        ]
    return samples


def curate_reference_audio_bank(
    samples: list[ReferenceAudioSample],
    *,
    limit: int = 24,
) -> list[ReferenceAudioSample]:
    if limit <= 0 or len(samples) <= limit:
        return samples
    if limit == 1:
        return [samples[len(samples) // 2]]
    step = (len(samples) - 1) / (limit - 1)
    indexes: list[int] = []
    for index in range(limit):
        candidate = round(index * step)
        if candidate not in indexes:
            indexes.append(candidate)
    while len(indexes) < limit:
        candidate = len(indexes)
        if candidate not in indexes:
            indexes.append(candidate)
    indexes = sorted(set(indexes))
    if len(indexes) > limit:
        indexes = indexes[:limit]
    return [samples[index] for index in indexes]


def normalize_voice_text(text: str) -> str:
    replacements = [
        (r"\bAI\b", "A.I."),
        (r"\bAPI\b", "A.P.I."),
        (r"\bPM\b", "P.M."),
        (r"\bJira\b", "Jee-ra"),
        (r"\bScrum\b", "Skrum"),
        (r"\bAgile\b", "A-jile"),
    ]
    normalized = text
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"([.!?])\s+", r"\1  ", normalized)
    return normalized.strip()


def _run_async(coro: object) -> None:
    try:
        asyncio.run(coro)  # type: ignore[arg-type]
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" not in str(exc):
            raise
        raise RuntimeError(
            "edge-tts voice generation cannot run inside an existing event loop. "
            "Call it from sync code or wrap it in your own async runner."
        ) from exc


async def _write_edge_voice_sample(
    output_path: Path,
    *,
    voice: str,
    text: str,
    instructions: str = "",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Install edge-tts to generate free Indian voice samples.") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        normalize_voice_text(text),
        voice,
        rate=rate,
        pitch=pitch,
    )
    if instructions:
        # Edge TTS does not accept custom instructions, so we preserve the note in the filename workflow.
        pass
    await communicate.save(str(output_path))


def check_is_hindi(text: str, voice: str) -> bool:
    """Checks if the language or voice is Hindi."""
    if any("\u0900" <= char <= "\u097f" for char in text):
        return True
    if voice.startswith("hi-IN") or "swara" in voice.lower() or "madhur" in voice.lower():
        return True
    try:
        import streamlit as st
        if st.session_state.get("voice_library_language_filter") == "hi-in":
            return True
        if st.session_state.get("music_studio_language") in ["Hindi", "Hinglish"]:
            return True
        if st.session_state.get("kids_studio_language") in ["Hindi", "Hinglish"]:
            return True
    except Exception:
        pass
    return False


def generate_indian_voiceover(
    text: str,
    output_path: Path,
    *,
    voice: str = "en-IN-PrabhatNeural",
    rate: str | None = None,
    pitch: str | None = None,
) -> Path:
    # Resolve rate and pitch dynamically based on the active preset
    selected_preset = None
    
    # 1. Try to read active preset choice if in streamlit context
    try:
        import streamlit as st
        if "voice_preset_choice" in st.session_state:
            choice = st.session_state["voice_preset_choice"]
            for p in VOICE_PREVIEW_PRESETS:
                if p.key == choice:
                    selected_preset = p
                    break
    except Exception:
        pass
        
    # 2. Bypassing Streamlit: Fallback to reading the studio state JSON in background compiles
    if selected_preset is None:
        try:
            # Walk up output_path or search in Path.cwd() to locate .runtime/studio_state.json
            state_path = None
            for parent in [output_path.parent] + list(output_path.parents):
                candidate = parent / ".runtime" / "studio_state.json"
                if candidate.exists():
                    state_path = candidate
                    break
            if not state_path:
                candidate = Path.cwd() / "output" / ".runtime" / "studio_state.json"
                if candidate.exists():
                    state_path = candidate
            
            if state_path and state_path.exists():
                import json
                state_data = json.loads(state_path.read_text(encoding="utf-8"))
                choice = state_data.get("voice_preset_choice")
                if choice:
                    for p in VOICE_PREVIEW_PRESETS:
                        if p.key == choice:
                            selected_preset = p
                            break
        except Exception:
            pass
            
    # 3. Fall back to matching by voice name if no active preset session/JSON state is found
    if selected_preset is None or (selected_preset.voice != voice and voice != "en-IN-PrabhatNeural"):
        # If the loaded preset doesn't match the voice (and it's not the default), fallback to voice matching
        for p in VOICE_PREVIEW_PRESETS:
            if p.voice == voice:
                selected_preset = p
                break
                
    if selected_preset is not None:
        # Check if text contains Devanagari characters or if language filter is Hindi
        is_hindi = False
        try:
            import streamlit as st
            if st.session_state.get("voice_library_language_filter") == "hi-in":
                is_hindi = True
        except Exception:
            pass
        if not is_hindi:
            is_hindi = any("\u0900" <= char <= "\u097f" for char in text)

        # Override the voice name dynamically for common presets
        voice = selected_preset.voice
        if is_hindi:
            if selected_preset.key in ("toddler_girl", "toddler_boy"):
                voice = "hi-IN-SwaraNeural"
            elif selected_preset.key in ("story_female", "storyteller_common"):
                voice = "hi-IN-SwaraNeural"
            elif selected_preset.key == "story_male":
                voice = "hi-IN-MadhurNeural"
        else:
            if selected_preset.key in ("toddler_girl", "toddler_boy"):
                voice = "en-US-AnaNeural"
            elif selected_preset.key in ("story_female", "storyteller_common"):
                voice = "en-IN-NeerjaNeural"
            elif selected_preset.key == "story_male":
                voice = "en-IN-PrabhatNeural"

        if rate is None:
            rate = selected_preset.rate
        if pitch is None:
            pitch = selected_preset.pitch
            
        # Apply specialized breathing and dramatic pacing filters if applicable!
        if selected_preset.key in ("toddler_girl", "toddler_boy"):
            text = humanize_child_pacing_punctuation(text)
        elif selected_preset.key in ("story_female", "story_male", "storyteller_common"):
            text = inject_dramatic_story_pauses_punctuation(text)
    else:
        if rate is None:
            rate = "+0%"
        if pitch is None:
            pitch = "+0Hz"

    # Determine if text is Hindi or if a Hindi voice is requested
    is_hindi = check_is_hindi(text, voice)
    
    if is_hindi:
        # Hindi: Use Gemini TTS (if under budget), else fall back to Edge TTS Hindi (free)
        from content_pipeline.bots.gemini_tts import GeminiAudioLimiter, generate_gemini_voiceover, transliterate_to_devanagari
        from content_pipeline.config import Settings
        import os
        
        settings = Settings.from_environment()
        
        # Transliterate Hinglish to native Devanagari script if Devanagari characters are missing
        if not any("\u0900" <= char <= "\u097f" for char in text):
            text = transliterate_to_devanagari(text, settings)
            
        state_path = settings.output_dir / ".runtime" / "gemini_audio_rate_limit.json"
        limiter = GeminiAudioLimiter(state_path, daily_budget=50)
        status = limiter.get_current_status()
        
        generated_ok = False
        if not status["limit_reached"]:
            # We are under budget! Use Gemini TTS
            voice_to_use = "Kore" if "Swara" in voice or "female" in voice.lower() else "Rasalgethi"
            if voice in ("Rasalgethi", "Puck", "Charon", "Kore", "Fenrir", "Aoede"):
                voice_to_use = voice
            try:
                # Increment and generate
                remaining, limit_just_hit = limiter.get_remaining_and_increment()
                if limit_just_hit:
                    # Send telegram alert that limit is reached
                    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
                    if bot_token and chat_id:
                        try:
                            from content_pipeline.bots.telegram import send_telegram_message
                            send_telegram_message(bot_token, chat_id, "⚠️ Daily Gemini Hindi Audio budget (50 audios) hit! Swapping to free Edge TTS Hindi engine.")
                        except Exception:
                            pass
                generate_gemini_voiceover(text=text, output_path=output_path, voice_name=voice_to_use, settings=settings)
                generated_ok = True
            except Exception as e:
                print(f"❌ SYSTEM ERROR: Gemini Voiceover generation failed: {e}. Falling back to Edge-TTS.")
                
        if not generated_ok:
            # Budget Exhausted / Fallback: Use Edge TTS Hindi
            fallback_voice = "hi-IN-SwaraNeural" if "Swara" in voice or "female" in voice.lower() or "Kore" in voice or "Aoede" in voice else "hi-IN-MadhurNeural"
            _run_async(_write_edge_voice_sample(output_path, voice=fallback_voice, text=text, rate=rate, pitch=pitch))
            
        # Apply vocal post-processing if pydub is available
        try:
            from pydub import AudioSegment
            if output_path.exists():
                vocals = AudioSegment.from_file(str(output_path))
                # Shift sample rate slightly for a warmer, deeper chest resonance
                deeper_vocals = vocals._spawn(vocals.raw_data, overrides={
                    "frame_rate": int(vocals.frame_rate * 0.94)
                }).set_frame_rate(vocals.frame_rate)
                
                # Export the processed vocals back to the output path
                fmt = output_path.suffix.lstrip(".").lower() or "mp3"
                deeper_vocals.export(str(output_path), format=fmt)
        except Exception as pydub_err:
            pass
            
        return output_path
        
    else:
        # English: Use the free option directly (Edge TTS)
        # Determine voice name
        english_voice = "en-IN-PrabhatNeural"
        if voice in ("en-IN-PrabhatNeural", "en-IN-NeerjaNeural", "en-US-AnaNeural"):
            english_voice = voice
        elif selected_preset is not None and selected_preset.voice in ("en-IN-PrabhatNeural", "en-IN-NeerjaNeural", "en-US-AnaNeural"):
            english_voice = selected_preset.voice
            
        _run_async(_write_edge_voice_sample(output_path, voice=english_voice, text=text, rate=rate, pitch=pitch))
        return output_path



def generate_voice_preview(
    text: str,
    output_path: Path,
    *,
    provider: str,
    voice: str,
    openai_api_key: str = "",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Path:
    provider = (provider or "edge").strip().lower()
    _ = openai_api_key
    if provider not in ("edge", "gemini"):
        raise ValueError("Voice preview generation supports provider='edge' or 'gemini'.")
    return generate_indian_voiceover(text, output_path, voice=voice, rate=rate, pitch=pitch)


def generate_music_preview(output_path: Path, mood: str, *, duration_seconds: int = 8) -> Path:
    duration_seconds = max(4, min(int(duration_seconds), 15))
    sample_rate = 44100
    total_samples = duration_seconds * sample_rate
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    is_nursery = (mood == "nursery")
    
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        
        frequencies, amplitude = MUSIC_PRESETS.get(mood, MUSIC_PRESETS["cinematic"])
        
        for index in range(total_samples):
            t = index / sample_rate
            fade_in = min(1.0, t / 0.75)
            fade_out = min(1.0, max(0.0, (duration_seconds - t) / 0.75))
            global_envelope = fade_in * fade_out
            
            if is_nursery:
                # Trigger a note every 1.5 seconds to simulate a warm music box melody
                note_period = 1.5
                note_index = int(t / note_period)
                time_in_note = t % note_period
                
                # Nursery melody notes - warm octave lower C4-E4-G4-C5
                progression = [
                    [261.63, 329.63, 392.00, 261.63],    # C major notes
                    [349.23, 440.00, 523.25, 349.23],    # F major notes
                    [392.00, 493.88, 587.33, 392.00],    # G major notes
                    [523.25, 392.00, 329.63, 261.63]     # C major resolve
                ]
                
                prog_index = (note_index // 4) % len(progression)
                step_index = note_index % 4
                freq = progression[prog_index][step_index]
                
                # Soft bell strike with gentle decay (no harsh high overtones)
                fundamental = math.sin(2 * math.pi * freq * t) * math.exp(-3.0 * time_in_note)
                # Extremely soft overtone to avoid sharpness
                overtone = math.sin(2 * math.pi * (2.0 * freq) * t) * math.exp(-8.0 * time_in_note) * 0.1
                bell_sample = fundamental + overtone
                
                # Deep, warm bass pad (similar to storytelling, but follows chord progression)
                # C2/F2/G2 sub-bass support
                pad_freqs = [65.41, 130.81, 196.00]
                if prog_index == 1: # F major pad
                    pad_freqs = [87.31, 130.81, 174.61]
                elif prog_index == 2: # G major pad
                    pad_freqs = [98.00, 146.83, 196.00]
                    
                pad_sample = sum(math.sin(2 * math.pi * pf * t) for pf in pad_freqs) / len(pad_freqs)
                
                # Blend: 30% soft warm chime + 70% deep bassy pad (feels warm and soft to the ear)
                sample = (bell_sample * 0.30 + pad_sample * 0.70)
                sample *= amplitude * global_envelope
            else:
                sample = sum(math.sin(2 * math.pi * frequency * t) for frequency in frequencies) / len(frequencies)
                sample *= amplitude * global_envelope
                
            frames.extend(struct.pack("<h", int(sample * 32767)))
        wav_file.writeframes(bytes(frames))
    return output_path


def voice_status(output_dir: Path, settings: Settings, *, day: str | None = None) -> dict[str, Any]:
    day = day or date.today().isoformat()
    daily_dir = output_dir / "daily" / day
    status_path = daily_dir / "voice_status.json"
    if status_path.exists():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            return loaded
    return _build_voice_status_payload(
        output_dir,
        settings,
        day=day,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_voice_status_html(status: dict[str, Any]) -> str:
    sample_rows = "".join(
        f"<li>{escape(str(path))}</li>" for path in status.get("sample_files", [])
    )
    if not sample_rows:
        sample_rows = "<li>No sample audio files generated yet.</li>"
    missing_audio_notice = ""
    if status.get("missing_sample_files") or not status.get("sample_files"):
        missing_audio_notice = (
            '<div style="margin-top:10px;color:#fca5a5;font-size:12px;font-weight:700;">'
            "Missing sample audio"
            "</div>"
        )
    audio_mode = "real audio" if status.get("has_real_audio") else "manifest only"
    preview_excerpt = escape(str(status.get("preview_excerpt") or ""))
    generated_at = escape(str(status.get("generated_at") or "unknown"))
    return f"""<section style="background:#111827;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
    <div>
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Voice status</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px;">{escape(str(status.get('provider') or 'unknown'))} · {escape(str(status.get('voice') or 'unknown'))}</div>
      <div style="margin-top:4px;color:#94a3b8;font-size:12px;">Last generated: {generated_at}</div>
    </div>
    <div style="font-size:12px;color:#94a3b8;text-align:right;">
      <div>Engine: {escape(str(status.get('engine') or 'unknown'))}</div>
      <div>Mode: {escape(audio_mode)}</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:14px;">
    <div style="background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Profile</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(status.get('profile_path') or ''))}</div>
    </div>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Preview</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(status.get('preview_path') or ''))}</div>
    </div>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Samples</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(status.get('sample_count') or 0))}</div>
    </div>
  </div>
  <div style="margin-top:14px;">
    <div style="font-weight:700;color:#fca5a5;margin-bottom:6px;">Sample files</div>
    <ul style="margin:0;padding-left:18px;color:#cbd5e1;">{sample_rows}</ul>
    {missing_audio_notice}
  </div>
  <div style="margin-top:14px;background:#0f172a;border:1px solid #334155;border-radius:14px;padding:12px;">
    <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Pronunciation preview</div>
    <div style="margin-top:6px;color:#e2e8f0;line-height:1.5;">{preview_excerpt or 'No preview recorded yet.'}</div>
  </div>
</section>"""


def write_voice_daily_artifacts(output_dir: Path, settings: Settings, *, day: str) -> dict[str, Path]:
    daily_dir = output_dir / "daily" / day
    daily_dir.mkdir(parents=True, exist_ok=True)

    preview_text = normalize_voice_text(
        "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm."
    )
    base_status = _build_voice_status_payload(
        output_dir,
        settings,
        day=day,
        generated_at=datetime.now(timezone.utc).isoformat(),
        preview_text=preview_text,
    )

    profile_path = daily_dir / "voice_profile.json"
    profile_path.write_text(
        json.dumps(base_status["voice_profile"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    preview_path = daily_dir / "voice_normalization_preview.txt"
    preview_path.write_text(preview_text + "\n", encoding="utf-8")

    samples_dir = daily_dir / "indian_voice_samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = samples_dir / "voice_samples_manifest.json"
    manifest_path.write_text(
        json.dumps(base_status["samples_manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readme_path = samples_dir / "README.md"
    readme_path.write_text(
        "# Indian Voice Samples\n\n"
        "This directory stores the daily voice manifest and, when enabled, the free Indian sample audio files.\n",
        encoding="utf-8",
    )

    written = {
        "voice_profile": profile_path,
        "voice_normalization_preview": preview_path,
        "voice_samples_manifest": manifest_path,
        "voice_samples_readme": readme_path,
    }

    sample_generation_error = ""
    if settings.voice_provider == "edge":
        try:
            generated = generate_hindi_voice_samples(settings, samples_dir, engine="edge")
        except Exception as exc:
            generated = []
            sample_generation_error = str(exc)
        for path in generated:
            written[path.stem] = path

    status = _build_voice_status_payload(
        output_dir,
        settings,
        day=day,
        generated_at=datetime.now(timezone.utc).isoformat(),
        preview_text=preview_text,
    )
    if sample_generation_error:
        status["sample_generation_error"] = sample_generation_error
        status["samples_manifest"]["note"] = (
            f"{status['samples_manifest']['note']} Edge sample generation fallback: {sample_generation_error}"
        )
    status_path = daily_dir / "voice_status.json"
    status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    status_html_path = daily_dir / "voice_status.html"
    status_html_path.write_text(render_voice_status_html(status), encoding="utf-8")
    written["voice_status"] = status_path
    written["voice_status_html"] = status_html_path

    return written


def _build_voice_status_payload(
    output_dir: Path,
    settings: Settings,
    *,
    day: str,
    generated_at: str,
    preview_text: str | None = None,
) -> dict[str, Any]:
    profile = build_voice_profile(provider=settings.voice_provider, voice=settings.indian_tts_voice)
    daily_dir = output_dir / "daily" / day
    profile_path = daily_dir / "voice_profile.json"
    preview_path = daily_dir / "voice_normalization_preview.txt"
    samples_dir = daily_dir / "indian_voice_samples"
    manifest_path = samples_dir / "voice_samples_manifest.json"
    sample_files = sorted(samples_dir.glob("sample_*.mp3"))
    expected_sample_files = [str(samples_dir / filename) for filename, _, _ in FREE_INDIAN_EDGE_VOICE_VARIANTS]
    expected_sample_names = [filename for filename, _, _ in FREE_INDIAN_EDGE_VOICE_VARIANTS]
    missing_sample_files = [
        str(samples_dir / filename)
        for filename in expected_sample_names
        if not (samples_dir / filename).exists()
    ]
    preview_text = preview_text or normalize_voice_text(
        "AI for PM teams using Jira and Scrum. The A.I. flow should sound clear and calm."
    )
    return {
        "provider": settings.voice_provider,
        "voice": settings.indian_tts_voice,
        "engine": "edge" if settings.voice_provider == "edge" else "manifest-only",
        "day": day,
        "generated_at": generated_at,
        "daily_dir": str(daily_dir),
        "profile_path": str(profile_path),
        "preview_path": str(preview_path),
        "preview_excerpt": preview_text,
        "samples_dir": str(samples_dir),
        "samples_manifest_path": str(manifest_path),
        "has_real_audio": bool(sample_files),
        "sample_count": len(sample_files),
        "sample_files": [str(path) for path in sample_files],
        "expected_sample_files": expected_sample_files,
        "missing_sample_files": missing_sample_files,
        "voice_profile": asdict(profile),
        "samples_manifest": {
            "provider": settings.voice_provider,
            "voice": settings.indian_tts_voice,
            "engine": "edge" if settings.voice_provider == "edge" else "manifest-only",
            "samples": [
                {
                    "filename": filename,
                    "voice": voice,
                    "description": description,
                }
                for filename, voice, description in FREE_INDIAN_EDGE_VOICE_VARIANTS
            ],
            "note": (
                "Real sample audio is generated when VOICE_PROVIDER=edge. "
                "Otherwise this directory keeps the manifest for the selected Indian voice path."
            ),
        },
    }


def audio_status(output_dir: Path, settings: Settings, *, day: str | None = None) -> dict[str, Any]:
    day = day or date.today().isoformat()
    daily_voice_status = voice_status(output_dir, settings, day=day)
    science_manifests = _load_audio_manifests(output_dir, "science_stories/*/audio/audio_manifest.json")
    pm_manifests = sorted(
        [
            *_load_audio_manifests(output_dir, "shorts/*/*/audio/reference/audio_manifest.json"),
            *_load_audio_manifests(output_dir, "youtubeVideo/*/*/audio/reference/audio_manifest.json"),
        ],
        key=lambda item: item.get("mtime", 0),
        reverse=True,
    )
    return {
        "day": day,
        "daily_voice_status": daily_voice_status,
        "science_audio": {
            "count": len(science_manifests),
            "latest": science_manifests[0] if science_manifests else None,
            "manifests": science_manifests,
        },
        "pm_audio": {
            "count": len(pm_manifests),
            "latest": pm_manifests[0] if pm_manifests else None,
            "manifests": pm_manifests,
        },
        "summary": {
            "has_daily_voice": bool(daily_voice_status),
            "has_science_audio": bool(science_manifests),
            "has_pm_audio": bool(pm_manifests),
        },
    }


def render_audio_status_html(status: dict[str, Any]) -> str:
    daily = status.get("daily_voice_status", {})
    science = status.get("science_audio", {})
    pm = status.get("pm_audio", {})
    missing_samples = daily.get("missing_sample_files", [])
    missing_audio_text = ""
    if missing_samples:
        missing_audio_text = (
            f'<div style="margin-top:8px;color:#fca5a5;font-size:12px;">'
            f'Missing sample audio: {escape(", ".join(str(path) for path in missing_samples))}'
            f'</div>'
        )
    return f"""<section style="background:#0f172a;border:1px solid #334155;border-radius:18px;padding:16px;color:#e2e8f0;">
  <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;font-weight:800;">Audio status</div>
  <div style="margin-top:6px;font-size:20px;font-weight:800;">{escape(str(status.get('day') or 'unknown'))}</div>
  <div style="margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;">
    <div style="background:#111827;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Daily voice</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(daily.get('provider') or 'unknown'))} · {escape(str(daily.get('voice') or 'unknown'))}</div>
      <div style="margin-top:4px;color:#94a3b8;">{escape('real audio' if daily.get('has_real_audio') else 'manifest only')}</div>
      <div style="margin-top:4px;color:#94a3b8;">Last generated: {escape(str(daily.get('generated_at') or 'unknown'))}</div>
      {missing_audio_text}
    </div>
    <div style="background:#111827;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">Science audio</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(science.get('count') or 0))} manifest(s)</div>
      <div style="margin-top:4px;color:#94a3b8;">Latest: {escape(str((science.get('latest') or {}).get('path') or 'none'))}</div>
    </div>
    <div style="background:#111827;border:1px solid #334155;border-radius:14px;padding:12px;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;">PM audio</div>
      <div style="margin-top:6px;font-weight:700;">{escape(str(pm.get('count') or 0))} manifest(s)</div>
      <div style="margin-top:4px;color:#94a3b8;">Latest: {escape(str((pm.get('latest') or {}).get('path') or 'none'))}</div>
    </div>
  </div>
</section>"""


def _load_audio_manifests(output_dir: Path, pattern: str) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in output_dir.glob(pattern):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload["path"] = str(path)
        payload["mtime"] = path.stat().st_mtime
        manifests.append(payload)
    manifests.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return manifests


def prepare_singing_lyrics(lyrics: str) -> str:
    """
    Cleans structural markers and strips artificial character elongation.
    Ensures 100% clean Devanagari is passed to prevent token fragmentation
    and completely eliminate background ghost voice anomalies.
    """
    # Remove standard punctuation boundaries
    clean_text = lyrics.replace("।", "").replace("॥", "")
    
    # Regex filter to deduplicate accidentally repeated Devanagari vowel signs
    # This prevents the model from synthesizing secondary harmonic tracking whispers
    clean_text = re.sub(r'([\u093e-\u094c])\1+', r'\1', clean_text)
    clean_text = re.sub(r'([\u0a00-\u0a7f])\1+', r'\1', clean_text)
    
    return clean_text.strip()


def apply_studio_stereo_doubling(vocal_segment: AudioSegment) -> AudioSegment:
    """
    Simulates a professional dual-mic studio tracking setup. Splits a mono 
    vocal stem, pans channels wide, and adds a micro-delay for immersive stereo width.
    """
    print("🎛️ Studio Suite: Applying Stereo Vocal Doubling...")
    # Pan channels left and right to open the audio soundstage
    left_channel = vocal_segment.pan(-0.22)
    right_channel = vocal_segment.pan(0.22)
    
    # Introduce a microscopic 20ms delay to the right channel to simulate human variance
    delayed_right = AudioSegment.silent(duration=20) + right_channel
    
    # Overlay the channels back into a single wide stereo vocal stem
    widened_vocals = left_channel.overlay(delayed_right, position=0)
    return widened_vocals

def apply_ambient_reverb_space(vocal_segment: AudioSegment, decay_db=14, delay_ms=110) -> AudioSegment:
    """
    Blends the singer into a natural, warm studio hall reflection space,
    glueing the vocals seamlessly INSIDE the acoustic backing instruments.
    """
    print("✨ Studio Suite: Diffusing Plate Reverb Reflection...")
    reverb_tail = vocal_segment - decay_db
    delayed_tail = AudioSegment.silent(duration=delay_ms) + reverb_tail
    
    # Layer the clean vocal stem with its natural environmental decay tail
    spatial_vocals = vocal_segment.overlay(delayed_tail, position=0)
    return spatial_vocals


def apply_vocal_sidechain_carving(beat_segment: AudioSegment, vocal_segment: AudioSegment) -> AudioSegment:
    """
    Dynamically ducks the mid-range frequencies of the backing track 
    whenever vocal energy is detected, carving an acoustic pocket for the singer.
    """
    print("🎛️ Mastering Suite: Executing Dynamic Mid-Side Sidechain Carving...")
    
    # Export segments to raw sample arrays
    sample_rate = beat_segment.frame_rate
    beat_channels = beat_segment.channels
    vocal_channels = vocal_segment.channels
    
    beat_samples = np.array(beat_segment.get_array_of_samples(), dtype=np.float32)
    vocal_samples = np.array(vocal_segment.get_array_of_samples(), dtype=np.float32)
    
    # Calculate localized root-mean-square (RMS) energy of the vocals
    try:
        vocal_envelope = np.abs(signal.hilbert(vocal_samples))
    except Exception:
        vocal_envelope = np.abs(vocal_samples)
        
    vocal_envelope = signal.medfilt(vocal_envelope, kernel_size=101) # Smooth envelope
    
    # Normalize envelope to create a dynamic attenuation curve
    max_env = np.max(vocal_envelope) if np.max(vocal_envelope) > 0 else 1.0
    vocal_attenuation = 0.30 * (vocal_envelope / max_env) # Max 3dB mid-duck
    
    # Align frame channels
    vocal_frames = len(vocal_samples) // vocal_channels
    beat_frames = len(beat_samples) // beat_channels
    
    if vocal_channels == 2:
        frame_attenuation = 0.5 * (vocal_attenuation[0::2] + vocal_attenuation[1::2])
    else:
        frame_attenuation = vocal_attenuation
        
    if len(frame_attenuation) < beat_frames:
        pad_width = beat_frames - len(frame_attenuation)
        frame_attenuation = np.pad(frame_attenuation, (0, pad_width), mode='constant', constant_values=0.0)
    else:
        frame_attenuation = frame_attenuation[:beat_frames]
        
    if beat_channels == 2:
        attenuation_curve = 1.0 - np.repeat(frame_attenuation, 2)
    else:
        attenuation_curve = 1.0 - frame_attenuation
    
    # Apply bandpass filter to isolate the vocal presence pocket (1kHz to 2.5kHz) in the beat
    nyquist = sample_rate / 2.0
    b, a = signal.butter(2, [1000.0 / nyquist, 2500.0 / nyquist], btype='band')
    beat_mids = signal.lfilter(b, a, beat_samples)
    
    # Dynamically attenuate only the clashing mid-frequencies based on vocal presence
    carved_mids = beat_mids * attenuation_curve
    
    # Re-combine the carved mids back into the original beat track
    processed_beat_samples = (beat_samples - beat_mids) + carved_mids
    processed_beat_samples = np.clip(processed_beat_samples, -32768, 32767)
    processed_beat_samples = processed_beat_samples.astype(np.int16)
    
    return beat_segment._spawn(processed_beat_samples.tobytes())


def compile_glued_studio_master(vocal_stereo_stem: AudioSegment, beat_stem: AudioSegment, output_path: str, mode: str = "Poem/Rhyme"):
    """
    Calibrates the final mixing matrix ratios to glue the wide stereo vocals 
    natively inside the backing score, preventing the voice from floating loosely on top.
    """
    import gc
    
    print("🎛️ Final Mixdown: Applying Studio Glue Leveling & Limiter Matrix...")
    
    # 1. Calibrate professional mixing headroom ratios depending on mode
    if mode == "Storytelling":
        calibrated_beat = beat_stem - 12.0   # Extremely soft background ambient cushion
        calibrated_vocals = vocal_stereo_stem + 4.5 # Prominent upfront narration vocals
    elif mode == "Poem/Rhyme":
        calibrated_beat = beat_stem - 9.0    # Balanced nursery rhythm backing track
        calibrated_vocals = vocal_stereo_stem + 4.0 # Boosted upfront nursery vocals
    else:
        # Tighten the separation from 10dB down to an integrated 5.5dB studio gap
        calibrated_beat = beat_stem - 4.5
        calibrated_vocals = vocal_stereo_stem + 1.0
    
    # 1.5 Apply dynamic mid-side sidechain carving to the beat based on vocal presence
    carved_beat = apply_vocal_sidechain_carving(calibrated_beat, calibrated_vocals)
    
    # 2. Overlay the spatial vocal tracks cleanly over the background instruments
    final_mix = carved_beat.overlay(calibrated_vocals, position=0)
    
    # 3. Apply a software peak limiter threshold to prevent digital clipping
    mastered_mix = final_mix.apply_gain(0.0).compress_dynamic_range(
        threshold=-2.0,
        attack=2.0,
        release=50.0,
        ratio=12.0  # Brickwall limiter protection
    )
    
    # 4. Export the polished track
    mastered_mix.export(output_path, format="mp3", bitrate="192k")
    
    # 5. Local Hardware Garbage Collection: Crucial for local 8GB M1 memory allocation
    gc.collect()
        
    print(f"✨ Master Recording successfully compiled and cached at: {output_path}")
    return output_path


def clean_and_master_pop_vocals(vocal_segment: AudioSegment) -> AudioSegment:
    """
    Carves away low-end mud, amplifies high-end air clarity, and applies 
    tight range compression to match modern commercial acoustic pop profiles.
    """
    print("🎛️ Mastering Suite: Executing Pop Vocal Calibration Matrix...")
    from pydub.effects import compress_dynamic_range
    
    # Force mono conversion for raw signal array processing layout consistency
    mono_vocals = vocal_segment.set_channels(1)
    sample_rate = mono_vocals.frame_rate
    samples = np.array(mono_vocals.get_array_of_samples(), dtype=np.float32)
    
    # STEP A: Cut the 400Hz boxy/heavy room rumble chamber (Quality Factor = 2.0)
    notch_freq = 400.0  
    b, a = signal.iirnotch(notch_freq, 2.0, sample_rate)
    clean_samples = signal.lfilter(b, a, samples)
    
    # STEP B: High-pass filter above 2500Hz to capture clean, crisp pop air clarity
    b_hp, a_hp = signal.butter(2, 2500.0 / (sample_rate / 2.0), btype='high')
    air_samples = signal.lfilter(b_hp, a_hp, clean_samples)
    
    # STEP C: Blend 82% clean signal with an 18% high-end presence boost
    mastered_samples = (clean_samples * 0.82) + (air_samples * 0.18)
    mastered_samples = mastered_samples.clip(-32768, 32767).astype(np.int16)
    mastered_vocals = mono_vocals._spawn(mastered_samples.tobytes())
    
    # STEP D: Dynamic Range Compression
    # Flattens audio peaks and boosts soft consonants so it sounds like a record
    compressed_vocals = compress_dynamic_range(
        mastered_vocals,
        threshold=-15.0,
        attack=10.0,
        release=100.0,
        ratio=3.5
    )
    
    return compressed_vocals


def apply_studio_warmth_eq(audio_samples: np.ndarray, sr: int) -> np.ndarray:
    """
    Applies a studio-grade low-shelf boost to add bass warmth to the vocals
    and a high-cut attenuation to eliminate the sharp, piercing treble frequencies.
    """
    print("🎛️ EQ Master: Injecting chest resonance and smoothing high-end sharpness...")
    import math
    import scipy.signal as signal
    
    # Custom low-shelf design to boost the bass (frequencies under 200Hz)
    def design_biquad_lowshelf(f0, sr, db_gain):
        A = math.pow(10.0, db_gain / 40.0)
        omega = 2.0 * math.pi * f0 / sr
        alpha = math.sin(omega) / 2.0 * math.sqrt(2.0)
        cos_w = math.cos(omega)
        two_sqrt_A_alpha = 2.0 * math.sqrt(A) * alpha

        b0 = A * ((A + 1) - (A - 1) * cos_w + two_sqrt_A_alpha)
        b1 = 2 * A * ((A - 1) - (A + 1) * cos_w)
        b2 = A * ((A + 1) - (A - 1) * cos_w - two_sqrt_A_alpha)
        
        a0 = (A + 1) + (A - 1) * cos_w + two_sqrt_A_alpha
        a1 = -2 * ((A - 1) + (A + 1) * cos_w)
        a2 = (A + 1) + (A - 1) * cos_w - two_sqrt_A_alpha
        return [b0/a0, b1/a0, b2/a0], [1.0, a1/a0, a2/a0]

    # Custom high-shelf design to smooth out sharpness (frequencies above 4500Hz)
    def design_biquad_highshelf(f0, sr, db_gain):
        A = math.pow(10.0, db_gain / 40.0)
        omega = 2.0 * math.pi * f0 / sr
        alpha = math.sin(omega) / 2.0 * math.sqrt(2.0)
        cos_w = math.cos(omega)
        two_sqrt_A_alpha = 2.0 * math.sqrt(A) * alpha

        b0 = A * ((A + 1) + (A - 1) * cos_w + two_sqrt_A_alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * cos_w)
        b2 = A * ((A + 1) + (A - 1) * cos_w - two_sqrt_A_alpha)
        
        a0 = (A + 1) - (A - 1) * cos_w + two_sqrt_A_alpha
        a1 = 2 * ((A - 1) - (A + 1) * cos_w)
        a2 = (A + 1) - (A - 1) * cos_w - two_sqrt_A_alpha
        return [b0/a0, b1/a0, b2/a0], [1.0, a1/a0, a2/a0]

    # +3.5 dB boost at 200 Hz for warm lows
    b_bass, a_bass = design_biquad_lowshelf(200.0, sr, 3.5)
    warmed_audio = signal.lfilter(b_bass, a_bass, audio_samples)
    
    # -4.0 dB attenuation at 4500 Hz for smooth highs
    b_treble, a_treble = design_biquad_highshelf(4500.0, sr, -4.0)
    smoothed_audio = signal.lfilter(b_treble, a_treble, warmed_audio)
    
    return smoothed_audio


def process_studio_vocal_resonance(raw_vocal_path: Path, genre_preset: str, voice_gender: str) -> AudioSegment:
    """
    Gives vocals deep playback resonance without over-compressing 
    or altering natural mouth and throat shapes (formants).
    """
    from pydub import AudioSegment
    vocals = AudioSegment.from_file(str(raw_vocal_path))
    
    # Soft, light calibrations that do not introduce nasal/stuffy artifacts
    pitch_factor = 0.97 if voice_gender.lower() == "male" else 0.99
    
    processed_vocals = vocals._spawn(vocals.raw_data, overrides={
        "frame_rate": int(vocals.frame_rate * pitch_factor)
    }).set_frame_rate(vocals.frame_rate)
    
    # Run through the Pop Mastering filter
    return clean_and_master_pop_vocals(processed_vocals)





def prepare_singing_lyrics_old(lyrics: str) -> str:
    import re
    # 1. First, split the lyrics into lines
    lines = lyrics.splitlines()
    processed_lines = []
    
    # Prepend global singing style block
    processed_lines.append("[style: traditional north indian classical chant, tempo: slow, mood: highly reverent]")
    processed_lines.append("")
    
    # Dynamic matra elongation mapping helper
    def elongate_line(line_str: str) -> str:
        replacements = {
            'ा': 'ाा',
            'ी': 'ीी',
            'ू': 'ूू',
            'ो': 'ोो',
            'ु': 'ुु',
            'े': 'ेे',
            'ै': 'ैै',
            'ं': 'ंं',
        }
        word_map = {
            "जय": "जय्य",
            "हनुमान": "हनुमाान",
            "ज्ञान": "ग्याान",
            "गुन": "गुुन",
            "सागर": "साागर",
            "कपीस": "कपीीस",
            "लोक": "लोोक",
            "उजागर": "उजाागर",
            "राम": "रााम",
            "दूत": "दूूत",
            "अतुलित": "अतुुलित",
            "अंजनि": "अंंजनि",
            "पुत्र": "पुुत्र",
            "पवनसुत": "पवनसुुत",
            "नामा": "नाामाा",
        }
        
        words = line_str.split()
        processed_words = []
        for word in words:
            # Clean word from punctuation for lookup
            clean_word = re.sub(r'[।॥\s,.]', '', word)
            if clean_word in word_map:
                punc = word.replace(clean_word, '')
                processed_words.append(word_map[clean_word] + punc)
                continue
            
            new_word = word
            for char, rep in replacements.items():
                new_word = new_word.replace(char, rep)
            processed_words.append(new_word)
        return " ".join(processed_words)

    # 2. Iterate through lines and insert directives
    directive_index = 0
    directives = [
        "[singing voice, chest resonance, sustain vowels]",
        "[melodic rise, elongate ending]",
        "[deep breath, smooth transition]"
    ]
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
        # If the line is already a bracketed tag, skip
        if line_strip.startswith("[") and line_strip.endswith("]"):
            continue
            
        # Add a dynamic directive before every line (cycling through them)
        if directive_index % 2 == 0:
            directive = directives[min(directive_index // 2, len(directives) - 1)]
            processed_lines.append(directive)
            
        elongated = elongate_line(line_strip)
        processed_lines.append(elongated)
        directive_index += 1
        
    return "\n".join(processed_lines)


def generate_edge_tts_song_fallback(
    lyrics: str,
    output_path: Path,
    singer_gender: str = "Male",
    selected_ref: str = "None (Text-only)",
    singer_key: str = "arijit_singh",
    mode: str = "Poem/Rhyme",
) -> Path:
    """Fallback generator for song creation using Edge-TTS + Background Beat mix.
    Used when Hugging Face song generation fails or rate-limits.
    """
    import re
    import math
    import os
    from pydub import AudioSegment
    from content_pipeline.config import Settings
    from content_pipeline.bots.gemini_tts import transliterate_to_devanagari
    
    settings = Settings.from_environment()
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    
    # 1. Ensure lyrics are in standard Devanagari script for perfect native accent
    is_devanagari = any("\u0900" <= char <= "\u097f" for char in lyrics)
    devanagari_lyrics = lyrics
    if not is_devanagari and not singer_key.startswith("en_"):
        devanagari_lyrics = transliterate_to_devanagari(lyrics, settings)
    
    if mode == "Storytelling":
        from content_pipeline.bots.kids_studio_core import preprocess_storytelling_script
        devanagari_lyrics = preprocess_storytelling_script(devanagari_lyrics)
        # For spoken storytelling, replace [pause] with punctuation or ellipsis to force natural pauses
        clean_lyrics = re.sub(r"\[pause\]", "... ", devanagari_lyrics, flags=re.IGNORECASE)
        # Strip all other bracketed tags
        clean_lyrics = re.sub(r"\[.*?\]", "", clean_lyrics).strip()
    else:
        # Prepare singing-optimized lyrics with vowel elongation
        singing_lyrics = prepare_singing_lyrics(devanagari_lyrics)
        # For Edge-TTS, we must strip the bracketed directives since it cannot interpret them
        clean_lyrics = re.sub(r"\[.*?\]", "", singing_lyrics).strip()
    
    is_kids_mode = mode in ["Storytelling", "Poem/Rhyme"]
    # 2. Determine voice based on singer_key or gender
    if is_kids_mode:
        from content_pipeline.bots.kids_studio_core import configure_absolute_storyteller_vocal_chain
        chain_config = configure_absolute_storyteller_vocal_chain(mode)
        voice = chain_config["base_tts_voice"]
        if singer_key == "en_kids_ana":
            voice = "en-US-AnaNeural"
        elif singer_key == "hi_kids_madhur":
            voice = "hi-IN-MadhurNeural"
        elif singer_key == "hi_kids_ananya":
            voice = "hi-IN-SwaraNeural"
    else:
        if singer_key == "hi_kids_ananya":
            voice = "hi-IN-SwaraNeural"
        elif singer_key == "en_kids_ana":
            voice = "en-US-AnaNeural"
        elif singer_key == "hi_kids_madhur":
            voice = "hi-IN-MadhurNeural"
        else:
            voice = "hi-IN-MadhurNeural"
            if singer_gender.strip().lower() == "female":
                voice = "hi-IN-SwaraNeural"
        
    temp_dir = settings.output_dir / ".runtime"
    temp_dir.mkdir(parents=True, exist_ok=True)
    raw_vocals_file = temp_dir / "edge_raw_vocals_song.mp3"
    
    # Generate raw vocals using Edge-TTS
    _run_async(_write_edge_voice_sample(
        raw_vocals_file,
        voice=voice,
        text=clean_lyrics,
        rate="+0%",
        pitch="+0Hz"
    ))
    
    # 3. Load vocals and beat
    vocals = AudioSegment.from_file(str(raw_vocals_file))
    
    # Determine the background beat file
    beat_path = None
    if selected_ref != "None (Text-only)":
        ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / selected_ref
        if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
            ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / selected_ref
        if ref_full_path.exists() and not is_vocal_track(selected_ref):
            beat_path = ref_full_path
            
    if not beat_path:
        beat_path = temp_dir / "fallback_beat.wav"
        if mode == "Storytelling":
            # Generate drumless 0 BPM ambient pad matching vocal duration
            generate_storytelling_ambient_pad(beat_path, duration_seconds=int(vocals.duration_seconds + 5))
        else:
            fallback_preset = "nursery" if mode == "Poem/Rhyme" else "ambient"
            generate_music_preview(beat_path, fallback_preset, duration_seconds=int(vocals.duration_seconds + 5))
            
    # Load beat
    beat = AudioSegment.from_file(str(beat_path))
        
    # Ensure beat is long enough to fit the vocals
    if beat.duration_seconds < vocals.duration_seconds:
        # Loop beat to match vocals duration
        loops = math.ceil(vocals.duration_seconds / beat.duration_seconds)
        beat = beat * loops
        
    # Crop beat to match vocals + 3 seconds of buffer
    beat = beat[:int((vocals.duration_seconds + 3) * 1000)]
    
    # 4. Deepen/Brighten voice depending on whether it is a kids profile
    if is_kids_mode:
        if mode == "Storytelling":
            pitch_shift_factor = 0.95  # Deepen slightly for storytelling warmth
        else:
            pitch_shift_factor = 1.05  # Brightening pitch override for Poem/Rhyme
    else:
        is_kids_voice = (singer_key in ["hi_kids_ananya", "en_kids_ana", "hi_kids_madhur"])
        if is_kids_voice:
            pitch_shift_factor = 1.05
        else:
            pitch_shift_factor = 0.95  # Deepen voice for Bollywood chest resonance
        
    processed_vocals = vocals._spawn(vocals.raw_data, overrides={
        "frame_rate": int(vocals.frame_rate * pitch_shift_factor)
    }).set_frame_rate(vocals.frame_rate)
    
    # Drop the beat volume to ensure dental consonants cut through smoothly
    if mode == "Storytelling":
        softer_beat = beat - 12.0
        vocals_boosted = processed_vocals + 4.5
    else:
        softer_beat = beat - 7.0
        vocals_boosted = processed_vocals + 3.0
    
    # Overlay the processed vocals onto the background track
    final_mix = softer_beat.overlay(vocals_boosted, position=0)
    
    # Export the final product
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_mix.export(str(output_path), format="mp3")
    
    # Clean up temp raw vocals
    try:
        if raw_vocals_file.exists():
            os.remove(raw_vocals_file)
    except Exception:
        pass
        
    return output_path


def generate_hindi_song_via_native_audio(
    lyrics: str,
    output_path: Path,
    singer_gender: str = "Male",
    selected_ref: str = "None (Text-only)",
    hf_token: str = "",
    genre: str = "Folk",
    temperature: float = 0.40,
    cfg_coef: float = 1.8,
    style_description: str = "",
    singer_key: str = "arijit_singh",
    mode: str = "Poem/Rhyme",
) -> Path:
    """Unified Hindi Song Generator:
    Bypasses Hugging Face Space for vocals, but dynamically generates
    an instrumental-only backing track using tencent/SongGeneration.
    1. Try generating an instrumental-only backing track using tencent/SongGeneration.
    2. Try Gemini TTS (under budget) with Puck (male) or Aoede/Kore (female) for vocals.
    3. Fall back to Edge-TTS (hi-IN-MadhurNeural or hi-IN-SwaraNeural) if Gemini TTS fails/over budget.
    4. Mix vocals with background beat (ducked by -6dB, vocal deepened by 0.94x, boosted by +2dB).
    """
    import re
    import math
    import os
    from pydub import AudioSegment
    from content_pipeline.config import Settings
    from content_pipeline.bots.gemini_tts import GeminiAudioLimiter, generate_gemini_voiceover, transliterate_to_devanagari

    settings = Settings.from_environment()
    
    # Resolve gender and config from the artist manifest
    from content_pipeline.bots.singer_manifest import SINGER_MANIFEST
    resolved_singer_key = singer_key
    if resolved_singer_key == "arijit_singn":
        resolved_singer_key = "arijit_singh"
        
    if resolved_singer_key in SINGER_MANIFEST:
        manifest_gender = SINGER_MANIFEST[resolved_singer_key]["gender"]
        singer_gender = manifest_gender.capitalize()  # Override with manifest gender ("Male" or "Female")
        print(f"🎤 Manifest Lookup: Resolved singer '{resolved_singer_key}' -> Gender: {singer_gender}")
    
    # Explicit API key validation right at launch/call
    active_key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key or os.environ.get("GOOGLE_API_KEY")
    if not active_key:
        print("⚠️ SYSTEM WARNING: No active GEMINI_API_KEY found in settings or environment for Hindi Song generation!")
    else:
        masked_key = active_key[:6] + "..." + active_key[-4:] if len(active_key) > 10 else "..."
        print(f"🔑 SYSTEM CHECK: Gemini API layer initialized. Active key: {masked_key}")
        
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

    # 1. Ensure lyrics are in standard Devanagari script for perfect native accent
    is_devanagari = any("\u0900" <= char <= "\u097f" for char in lyrics)
    devanagari_lyrics = lyrics
    if not is_devanagari:
        devanagari_lyrics = transliterate_to_devanagari(lyrics, settings)

    if mode == "Storytelling":
        from content_pipeline.bots.kids_studio_core import preprocess_storytelling_script
        devanagari_lyrics = preprocess_storytelling_script(devanagari_lyrics)
        clean_lyrics_gemini = devanagari_lyrics
        # For Edge-TTS, we must strip the bracketed directives and replace [pause] with "... " to inject pauses
        clean_lyrics_edge = re.sub(r"\[pause\]", "... ", devanagari_lyrics, flags=re.IGNORECASE)
        clean_lyrics_edge = re.sub(r"\[.*?\]", "", clean_lyrics_edge).strip()
    else:
        # Prepare singing-optimized lyrics with vowel elongation
        singing_lyrics = prepare_singing_lyrics(devanagari_lyrics)
        clean_lyrics_gemini = singing_lyrics
        # For Edge-TTS, we must strip the bracketed directives since it cannot interpret them
        clean_lyrics_edge = re.sub(r"\[.*?\]", "", singing_lyrics).strip()

    is_kids_mode = mode in ["Storytelling", "Poem/Rhyme"]

    # 2. Setup paths
    temp_dir = settings.output_dir / ".runtime"
    temp_dir.mkdir(parents=True, exist_ok=True)
    raw_vocals_file = temp_dir / "hindi_raw_vocals_song.wav"

    generated_ok = False
    gender_lower = singer_gender.strip().lower()
    voice_to_use = "Puck" if gender_lower == "male" else "Aoede"

    state_path = settings.output_dir / ".runtime" / "gemini_audio_rate_limit.json"
    limiter = GeminiAudioLimiter(state_path, daily_budget=50)
    status = limiter.get_current_status()

    st_write_func = None
    try:
        import streamlit as st
        st_write_func = st.write
    except Exception:
        pass

    if not status["limit_reached"] and not is_kids_mode:

        try:
            # Increment and generate
            remaining, limit_just_hit = limiter.get_remaining_and_increment()
            if limit_just_hit:
                # Send telegram alert that limit is reached
                bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
                if bot_token and chat_id:
                    try:
                        from content_pipeline.bots.telegram import send_telegram_message
                        send_telegram_message(bot_token, chat_id, "⚠️ Daily Gemini Hindi Song Audio budget (50 audios) hit! Swapping to free Edge TTS Hindi engine.")
                    except Exception:
                        pass
            
            if mode == "Storytelling":
                song_instruction = (
                    "You are an elite children's audio-book narrator and storyteller for YouTube animation channels. "
                    "Deliver the text with warm, expressive, and friendly spoken tones. "
                    "Adjust your pitch and expression dynamically based on the narrator and character tags. "
                    "Pause briefly at [pause] tags. Strictly do not sing or hum."
                )
            else:
                song_instruction = (
                    "You are a professional Bollywood studio playback singer performing in a clear, expressive pop style.\n"
                    "Deliver the text as a fluid, continuous legato melody. Strictly avoid word-by-word reading, mechanical prose cadences, and any background tracking voices, echo effects, or harmonic duplication whispers."
                )
            
            # Write to raw_vocals_file
            generate_gemini_voiceover(
                text=clean_lyrics_gemini,
                output_path=raw_vocals_file,
                voice_name=voice_to_use,
                settings=settings,
                system_instruction=song_instruction
            )
            generated_ok = True
        except Exception as e:
            print(f"❌ SYSTEM ERROR: Gemini Song Vocal generation failed: {e}. Falling back to Edge-TTS.")

    if not generated_ok:
        # Budget Exhausted / Fallback: Use Edge TTS Hindi
        if is_kids_mode:
            from content_pipeline.bots.kids_studio_core import configure_absolute_storyteller_vocal_chain
            chain_config = configure_absolute_storyteller_vocal_chain(mode)
            fallback_voice = chain_config["base_tts_voice"]
            if singer_key == "en_kids_ana":
                fallback_voice = "en-US-AnaNeural"
            elif singer_key == "hi_kids_madhur":
                fallback_voice = "hi-IN-MadhurNeural"
            elif singer_key == "hi_kids_ananya":
                fallback_voice = "hi-IN-SwaraNeural"
        else:
            fallback_voice = "hi-IN-MadhurNeural" if gender_lower == "male" else "hi-IN-SwaraNeural"
            if singer_key == "hi_kids_ananya":
                fallback_voice = "hi-IN-SwaraNeural"
            elif singer_key == "en_kids_ana":
                fallback_voice = "en-US-AnaNeural"
            elif singer_key == "hi_kids_madhur":
                fallback_voice = "hi-IN-MadhurNeural"
            
        edge_raw_vocals = temp_dir / "edge_raw_vocals_song.mp3"
        try:
            _run_async(_write_edge_voice_sample(
                edge_raw_vocals,
                voice=fallback_voice,
                text=clean_lyrics_edge,
                rate="+0%",
                pitch="+0Hz"
            ))
            # Convert edge mp3 to wav format
            edge_wav = temp_dir / "edge_raw_vocals_song.wav"
            AudioSegment.from_file(str(edge_raw_vocals)).export(str(edge_wav), format="wav")
            raw_vocals_file = edge_wav
            generated_ok = True
        except Exception as edge_err:
            raise RuntimeError(f"Both Gemini TTS and Edge-TTS failed for Hindi song generation. Edge err: {edge_err}")

    # 3. Load and process vocals with dynamic voice conversion (RVC) and genre-aware resonance filter
    from content_pipeline.bots.singing_synthesis import orchestrate_dynamic_vocal_pipeline, convert_speech_to_melodic_singing
    from content_pipeline.bots.melody_generator import generate_synthetic_melody_guide
    
    # Get configuration from orchestrator
    model_filename, pitch_shift = orchestrate_dynamic_vocal_pipeline(singer_key)
    
    # Check if a vocal reference track is selected
    use_vocal_ref_as_guide = False
    ref_full_path = None
    if selected_ref != "None (Text-only)":
        ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / selected_ref
        if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
            ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / selected_ref
        
        if ref_full_path.exists() and is_vocal_track(selected_ref):
            use_vocal_ref_as_guide = True

    melody_guide_path = None
    created_temp_melody_guide = False

    if mode in ["Storytelling", "Poem/Rhyme"]:
        # Kids Studio Storytelling and Poem/Rhyme: Bypassing melody guide to preserve natural voiceover pitch
        print(f"🎵 RVC Pitch Guide: {mode} mode. Bypassing melody guide to preserve natural voiceover pitch.")
    elif use_vocal_ref_as_guide:
        # Use vocal reference track directly as the pitch guide
        print(f"🎵 RVC Pitch Guide: Using vocal reference track directly: {ref_full_path}")
        melody_guide_path = ref_full_path
        created_temp_melody_guide = False
    else:
        # Generate the reference melody guide WAV file based on the duration of raw vocals
        print("🎵 RVC Pitch Guide: Generating synthetic melody guide fallback...")
        vocals_temp_segment = AudioSegment.from_file(str(raw_vocals_file))
        vocals_duration = vocals_temp_segment.duration_seconds
        melody_guide_path = raw_vocals_file.parent / "temp_melody_guide.wav"
        generate_synthetic_melody_guide(duration_seconds=vocals_duration, tempo_bpm=65, output_path=str(melody_guide_path))
        created_temp_melody_guide = True

    if mode == "Storytelling":
        from content_pipeline.bots.kids_studio_core import get_storyteller_production_flags, configure_absolute_storyteller_vocal_chain
        flags = get_storyteller_production_flags()
        chain_config = configure_absolute_storyteller_vocal_chain(mode)
        
        rvc_index_rate = flags["index_rate"]
        rvc_protect = flags["protect"]
        rvc_filter_radius = flags["filter_radius"]
        
        pitch_shift = chain_config["pitch_change"]
        rvc_formant_shift = chain_config["formant_shift"]
        rvc_rms_mix_rate = chain_config["rms_mix_rate"]
    elif mode == "Poem/Rhyme":
        from content_pipeline.bots.kids_studio_core import configure_absolute_storyteller_vocal_chain
        chain_config = configure_absolute_storyteller_vocal_chain(mode)
        
        rvc_index_rate = 0.35
        rvc_protect = 0.33
        rvc_filter_radius = 3
        
        pitch_shift = chain_config["pitch_change"]
        rvc_formant_shift = chain_config["formant_shift"]
        rvc_rms_mix_rate = chain_config["rms_mix_rate"]
    else:
        rvc_index_rate = 0.35
        rvc_protect = 0.33
        rvc_rms_mix_rate = 0.25
        rvc_filter_radius = 3
        rvc_formant_shift = 1.0

    # Morph spoken TTS stem into a singing voice stem using RVC guided by the melody guide
    singing_vocals_file = convert_speech_to_melodic_singing(
        raw_vocals_file, 
        model_filename, 
        melody_path=melody_guide_path,
        pitch_shift=pitch_shift,
        index_rate=rvc_index_rate,
        protect=rvc_protect,
        rms_mix_rate=rvc_rms_mix_rate,
        filter_radius=rvc_filter_radius,
        formant_shift=rvc_formant_shift
    )
    
    # Master the singing vocals using formant-protected resonance and pop mastering EQ
    vocals_clean = process_studio_vocal_resonance(singing_vocals_file, genre_preset=genre, voice_gender=singer_gender)
    
    if mode in ["Storytelling", "Poem/Rhyme"]:
        # Apply the low-shelf warmth boost and high-cut smoothing filter to add chest resonance
        sample_rate = vocals_clean.frame_rate
        samples = np.array(vocals_clean.get_array_of_samples(), dtype=np.float32)
        eq_samples = apply_studio_warmth_eq(samples, sample_rate)
        eq_samples = eq_samples.clip(-32768, 32767).astype(np.int16)
        vocals_clean = vocals_clean._spawn(eq_samples.tobytes())
        
        # Apply extra tight dynamic range compression to bring vocals upfront and closer to the mic
        from pydub.effects import compress_dynamic_range
        vocals_clean = compress_dynamic_range(
            vocals_clean,
            threshold=-18.0,
            attack=5.0,
            release=80.0,
            ratio=4.0
        )

    if mode in ["Storytelling", "Poem/Rhyme"]:
        # Keep storytelling and nursery vocals dry and centered to avoid a 'big empty room' echo sound
        vocals = vocals_clean
    else:
        # Apply spatial mastering suite: stereo doubler and ambient reverb tail
        vocals_doubled = apply_studio_stereo_doubling(vocals_clean)
        vocals = apply_ambient_reverb_space(vocals_doubled)


    # 4. Determine background beat file (Decoupled Pipeline using Lyria instrumental)
    beat_path = None

    if mode == "Storytelling":
        print("🎵 Storytelling Background: Using soft drumless ambient string pad...")
    else:
        # Try generating dynamic instrumental backing track using Lyria
        try:
            from gradio_client import Client, handle_file
            
            # Determine prompt_audio_param for style references
            prompt_audio_param = None
            if selected_ref != "None (Text-only)" and not is_vocal_track(selected_ref):
                ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / selected_ref
                if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                    ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / selected_ref
                
                if ref_full_path.exists():
                    # Crop reference audio to 15 seconds for Lyria style reference input
                    cropped_ref_path = temp_dir / "hindi_ref_cropped.mp3"
                    start_time = "0"
                    if ref_full_path.name == "बार्नबी गिलहरी की व्यर्थ खोज.mp3":
                        start_time = "4.5"
                        
                    import subprocess
                    cmd = [
                        "ffmpeg", "-y", "-i", str(ref_full_path),
                        "-ss", start_time, "-t", "15",
                        "-codec:a", "libmp3lame", "-b:a", "128k",
                        str(cropped_ref_path)
                    ]
                    subprocess.run(cmd, capture_output=True)
                    if cropped_ref_path.exists():
                        prompt_audio_param = handle_file(str(cropped_ref_path))

            if st_write_func:
                st_write_func("🎵 Generating dynamic instrumental backing track using Hugging Face Lyria (vocals disabled)...")
            else:
                print("Generating dynamic instrumental backing track using Hugging Face Lyria...")

            client = Client("tencent/SongGeneration", token=hf_token, httpx_kwargs={"timeout": 600.0})
            
            # Enforce positive instrumental description, avoiding negation words that trigger vocals
            raw_desc = style_description or "traditional north indian music, pure instrumental, solo sitar and bansuri flute melody, acoustic tabla rhythm, studio recording"
            
            # Split by clause/sentence boundaries to filter out vocal references without losing instrumental details
            clauses = re.split(r'([.,!?])', raw_desc)
            filtered_clauses = []
            vocal_terms_regex = re.compile(
                r"\b(vocals?|singing|voices?|singers?|vocalists?|lyrics?|chanting|backing vocals)\b", 
                re.IGNORECASE
            )
            for i in range(0, len(clauses), 2):
                clause = clauses[i]
                punct = clauses[i+1] if i+1 < len(clauses) else ""
                if not vocal_terms_regex.search(clause):
                    filtered_clauses.append(clause + punct)
            inst_desc = "".join(filtered_clauses).strip()
            # Clean up double punctuation resulting from filtering
            inst_desc = re.sub(r'\s*,\s*,', ',', inst_desc)
            inst_desc = re.sub(r'\s*\.\s*\.', '.', inst_desc)
            inst_desc = re.sub(r',\s*\.', '.', inst_desc)
            inst_desc = re.sub(r'\.\s*,', '.', inst_desc)
            inst_desc = re.sub(r'\s+', ' ', inst_desc).strip()
            
            # Ensure we have "Pure instrumental" at the start
            if "instrumental" not in inst_desc.lower():
                inst_desc = "Pure instrumental. " + inst_desc
                
            # Call prediction with instrumental lyric placeholder
            inst_lyric = "[intro-medium]\n\n[verse]\n[silence]\n\n[outro-medium]"
            
            # Force a valid genre and lower temperature for traditional Indian feel
            valid_genres = ['Auto', 'Pop', 'Latin', 'Rock', 'Electronic', 'Metal', 'Country', 'R&B/Soul', 'Ballad', 'Jazz', 'World', 'Hip-Hop', 'Funk', 'Soundtrack']
            active_genre = genre if genre in valid_genres else "World"
            active_temp = min(temperature, 0.40) # Lower temp to prevent Western deviations
            
            result_path, info = client.predict(
                lyric=inst_lyric,
                description=inst_desc,
                prompt_audio=prompt_audio_param,
                genre=active_genre,
                cfg_coef=cfg_coef,
                temperature=active_temp,
                api_name="/generate_song"
            )
            
            if result_path and str(result_path).strip().lower() != "none" and Path(result_path).exists():
                beat_path = Path(result_path)
                if st_write_func:
                    st_write_func("✅ Dynamic instrumental backing track generated successfully.")
            else:
                raise ValueError("Lyria did not return a valid audio path for the backing track.")
                
        except Exception as lyria_err:
            if st_write_func:
                st_write_func(f"⚠️ Lyria instrumental generation failed: {lyria_err}. Falling back to default beats/ambient...")
            else:
                print(f"Lyria instrumental generation failed: {lyria_err}")

    # Fallback to local files if Lyria fails or is bypassed
    if not beat_path:
        if mode == "Storytelling":
            # Generate drumless 0 BPM ambient pad matching vocal duration
            beat_path = temp_dir / "fallback_beat.wav"
            generate_storytelling_ambient_pad(beat_path, duration_seconds=int(vocals.duration_seconds + 5))
        else:
            if selected_ref != "None (Text-only)":
                ref_full_path = PROJECT_ROOT / "output" / "reference_audio" / selected_ref
                if not ref_full_path.exists() and Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio").exists():
                    ref_full_path = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio") / selected_ref
                if ref_full_path.exists() and not is_vocal_track(selected_ref):
                    beat_path = ref_full_path

            if not beat_path:
                # Fallback to generating a clean, vocal-free ambient synth background track
                beat_path = temp_dir / "fallback_beat.wav"
                fallback_preset = "nursery" if mode == "Poem/Rhyme" else "ambient"
                generate_music_preview(beat_path, fallback_preset, duration_seconds=int(vocals.duration_seconds + 5))

    # Load beat
    beat = AudioSegment.from_file(str(beat_path))

    # Ensure beat is long enough to fit the vocals
    if beat.duration_seconds < vocals.duration_seconds:
        # Loop beat to match vocals duration
        loops = math.ceil(vocals.duration_seconds / beat.duration_seconds)
        beat = beat * loops

    # Crop beat to match vocals + 3 seconds of buffer
    beat = beat[:int((vocals.duration_seconds + 3) * 1000)]

    # Use compile_glued_studio_master to blend, limit, and export the song
    compile_glued_studio_master(vocals, beat, str(output_path), mode=mode)

    # Clean up temp raw vocals and melody guide
    try:
        if raw_vocals_file.exists():
            os.remove(raw_vocals_file)
    except Exception:
        pass

    try:
        if 'created_temp_melody_guide' in locals() and created_temp_melody_guide and melody_guide_path and melody_guide_path.exists():
            os.remove(melody_guide_path)
    except Exception:
        pass

    return output_path


def generate_storytelling_ambient_pad(output_path: Path, duration_seconds: int = 8) -> Path:
    """Generates a drumless, low-volume C-major ambient pad for storytelling narration background score."""
    import wave
    import struct
    import math
    
    # C-major triad frequencies: C3, E3, G3, C4
    frequencies = [130.81, 164.81, 196.00, 261.63]
    amplitude = 0.08  # Low volume
    sample_rate = 44100
    total_samples = duration_seconds * sample_rate
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(total_samples):
            t = index / sample_rate
            # Smooth fade in and fade out over 1.5 seconds
            fade_in = min(1.0, t / 1.5)
            fade_out = min(1.0, max(0.0, (duration_seconds - t) / 1.5))
            envelope = fade_in * fade_out
            sample = sum(math.sin(2 * math.pi * frequency * t) for frequency in frequencies) / len(frequencies)
            sample *= amplitude * envelope
            frames.extend(struct.pack("<h", int(sample * 32767)))
        wav_file.writeframes(bytes(frames))
    return output_path


