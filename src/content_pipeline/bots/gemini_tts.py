from __future__ import annotations

import mimetypes
import os
import re
import struct
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from content_pipeline.config import Settings


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Generates a WAV file header for the given audio data and parameters.

    Args:
        audio_data: The raw audio data as a bytes object.
        mime_type: Mime type of the audio data.

    Returns:
        A bytes object representing the WAV file header.
    """
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"] or 16
    sample_rate = parameters["rate"] or 24000
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size  # 36 bytes for header fields before data chunk size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",          # ChunkID
        chunk_size,       # ChunkSize (total file size - 8 bytes)
        b"WAVE",          # Format
        b"fmt ",          # Subchunk1ID
        16,               # Subchunk1Size (16 for PCM)
        1,                # AudioFormat (1 for PCM)
        num_channels,     # NumChannels
        sample_rate,      # SampleRate
        byte_rate,        # ByteRate
        block_align,      # BlockAlign
        bits_per_sample,  # BitsPerSample
        b"data",          # Subchunk2ID
        data_size         # Subchunk2Size (size of audio data)
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
    """Parses bits per sample and rate from an audio MIME type string.

    Assumes bits per sample is encoded like "L16" and rate as "rate=xxxxx".

    Args:
        mime_type: The audio MIME type string (e.g., "audio/L16;rate=24000").

    Returns:
        A dictionary with "bits_per_sample" and "rate" keys. Values will be
        integers if found, otherwise None.
    """
    bits_per_sample = 16
    rate = 24000

    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate_str = param.split("=", 1)[1]
                rate = int(rate_str)
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass

    return {"bits_per_sample": bits_per_sample, "rate": rate}


def generate_gemini_voiceover(
    text: str,
    output_path: Path,
    voice_name: str,
    settings: Settings,
) -> Path:
    """Generates speech audio using Google's Gemini TTS models (Flash/Pro preview tts).

    Cycles through available API keys and models to ensure high resilience.
    """
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]

    # Ensure any direct env values are pooled
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))

    # Keep all configured keys (including those starting with 'AQ.')
    keys = [k for k in keys if k]
    if not keys:
        raise ValueError("At least one valid GEMINI_API_KEY is required for Gemini Neural TTS.")

    # Determine voice config
    # Default to single speaker unless Speaker tags are found
    is_multi_speaker = any(tag in text for tag in ("Speaker 1:", "Speaker 2:", "Speaker 3:"))
    
    if is_multi_speaker:
        # Standard Multi-speaker configuration for kids animations
        speech_config = types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(
                        speaker="Speaker 1",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Rasalgethi"  # Smooth Authoritative
                            )
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker="Speaker 2",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Puck"  # Youthful energetic
                            )
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker="Speaker 3",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Charon"  # Quick/Technical
                            )
                        ),
                    ),
                ]
            ),
        )
    else:
        # Single-speaker prebuilt voice config
        # Use voice_name as the prebuilt voice, e.g. "Rasalgethi"
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name if voice_name else "Rasalgethi"
                )
            )
        )

    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        response_modalities=["audio"],
        speech_config=speech_config,
    )

    models_to_try = [
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
    ]

    last_error: Exception | None = None
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect if text contains Hindi characters
    is_hindi = any("\u0900" <= char <= "\u097f" for char in text)

    for idx, key in enumerate(keys):
        client = genai.Client(api_key=key)
        for model in models_to_try:
            try:
                # Prompt prepending for Hindi pronunciation guidelines (required because system_instructions is not supported on Flash TTS models)
                prompt_text = text
                if is_hindi:
                    accent_instructions = (
                        "You are a native Indian professional playback singer.\n"
                        "You must speak and chant with a 100% authentic, clear Indian accent.\n"
                        "Strictly avoid any Western or Americanized vowel sounds.\n"
                        "Pronounce the short 'अ' sound cleanly (e.g., 'जय' must sound like 'J-uh-ye' or a short 'Jai' (जइ), not 'Jye' or 'Jaye').\n"
                        "Pronounce 'ज्ञान' (Gyan) with a rounded, deep vowel sound, never a flat Western 'a' sound (like in 'cat' or 'cab').\n"
                        "Ensure retroflex consonants like 'ट' and 'ड' are sharp and hit hard (curling your tongue backward against the roof of the mouth),\n"
                        "while dental consonants like 'त' and 'द' are completely soft (tongue touching the front teeth).\n"
                        "Do not over-enunciate the letter 'H' in words like 'Hanuman' or 'Mahavir' with an airy, Western sigh; keep it solid and throat-vocalized.\n"
                        "Maintain a musical, flowing cadence without robotic clipping.\n\n"
                        "Here is the text to speak:\n"
                    )
                    prompt_text = accent_instructions + text

                contents = [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt_text)],
                    ),
                ]

                audio_buffer = bytearray()
                mime_type = "audio/L16;rate=24000"

                # Pull and stream audio chunks
                for chunk in client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                ):
                    if chunk.parts is None:
                        continue
                    if chunk.parts[0].inline_data and chunk.parts[0].inline_data.data:
                        inline_data = chunk.parts[0].inline_data
                        audio_buffer.extend(inline_data.data)
                        if inline_data.mime_type:
                            mime_type = inline_data.mime_type

                if audio_buffer:
                    wav_bytes = convert_to_wav(bytes(audio_buffer), mime_type)
                    output_path.write_bytes(wav_bytes)
                    return output_path
            except Exception as e:
                last_error = e

    if last_error is not None:
        raise last_error
    raise RuntimeError("Gemini Neural TTS generation failed after cycling all API key slots and models.")


import logging
logger = logging.getLogger(__name__)

def transliterate_to_devanagari(text: str, settings: Settings) -> str:
    """Transliterates Romanized Hinglish/Hindi text into standard Devanagari script using Gemini 2.5 Flash."""
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    keys = [k for k in keys if k]
    if not keys:
        logger.warning("No Gemini API key available for transliteration.")
        return text

    prompt = (
        "You are a professional Hindi translator.\n"
        "Convert the following Romanized Hindi/Hinglish text into standard native Devanagari script.\n"
        "Maintain all punctuation and bracketed emotion/formatting tags (like [excitedly], [very slow]) exactly as they are.\n"
        "Output ONLY the final Devanagari text. Do not add any explanation, notes, or markdown formatting.\n\n"
        f"Text to convert:\n{text}"
    )

    for key in keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            res_text = response.text.strip()
            if res_text:
                return res_text
        except Exception as e:
            logger.warning(f"Gemini transliteration attempt failed: {e}")
            
    return text


from datetime import date
import json

class GeminiAudioLimiter:
    def __init__(self, state_path: Path, daily_budget: int = 15):
        self.state_path = state_path
        self.daily_budget = daily_budget

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def _reset_daily_if_needed(self, state: dict[str, Any]) -> None:
        today = date.today().isoformat()
        current_date = state.get("usage_date", "")
        if current_date != today:
            yesterday_rollover = state.get("rollover", 0)
            yesterday_limit = self.daily_budget + yesterday_rollover
            yesterday_generated = state.get("daily_generated", 0)
            unused = max(0, yesterday_limit - yesterday_generated)
            
            state["usage_date"] = today
            state["daily_generated"] = 0
            state["rollover"] = unused

    def get_remaining_and_increment(self) -> tuple[int, bool]:
        """Returns (remaining, limit_just_hit) and increments if under budget."""
        state = self._load_state()
        self._reset_daily_if_needed(state)
        
        used = state.get("daily_generated", 0)
        rollover = state.get("rollover", 0)
        total_limit = self.daily_budget + rollover
        
        if used >= total_limit:
            return 0, False
            
        state["daily_generated"] = used + 1
        self._save_state(state)
        
        remaining = total_limit - (used + 1)
        limit_just_hit = (remaining == 0)
        return remaining, limit_just_hit
        
    def get_current_status(self) -> dict[str, Any]:
        state = self._load_state()
        self._reset_daily_if_needed(state)
        
        used = state.get("daily_generated", 0)
        rollover = state.get("rollover", 0)
        total_limit = self.daily_budget + rollover
        remaining = max(0, total_limit - used)
        return {
            "used": used,
            "remaining": remaining,
            "daily_budget": self.daily_budget,
            "rollover": rollover,
            "total_limit": total_limit,
            "limit_reached": used >= total_limit
        }

