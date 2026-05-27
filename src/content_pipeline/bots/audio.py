from __future__ import annotations

from pathlib import Path

from content_pipeline.config import Settings


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
VOICE_VARIANTS = [
    ("sample_01_marin_warm.mp3", "marin", " स्वर कोमल, मातृवत और शांत रखें।"),
    ("sample_02_cedar_storyteller.mp3", "cedar", " स्वर भारतीय दादी-नानी की कहानी जैसा गर्म और सहज रखें।"),
    ("sample_03_coral_cheerful.mp3", "coral", " स्वर थोड़ा अधिक हँसमुख और बच्चों को आकर्षित करने वाला रखें।"),
]


def generate_hindi_voice_samples(settings: Settings, destination: Path) -> list[Path]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required to generate narration samples.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install live dependencies with: pip install -e '.[live]'") from exc
    destination.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=settings.openai_api_key)
    files: list[Path] = []
    for filename, voice, additional_instruction in VOICE_VARIANTS:
        result = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=HINDI_PRONUNCIATION_TEXT,
            instructions=HINDI_PRONUNCIATION_INSTRUCTIONS + additional_instruction,
        )
        output_path = destination / filename
        output_path.write_bytes(result.read())
        files.append(output_path)
    return files
