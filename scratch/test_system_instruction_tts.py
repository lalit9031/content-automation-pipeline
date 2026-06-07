import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def test_system_instruction():
    settings = Settings.from_environment()
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    keys = [k for k in keys if k]
    
    if not keys:
        print("No keys found!")
        sys.exit(1)
        
    lyrics = "जय हनुमान ज्ञान गुण सागर, जय कपीस तिहुँ लोक उजागर"
    
    system_instruction = (
        "You are a native Indian professional playback singer. "
        "You must speak and chant with a 100% authentic, clear Indian accent. "
        "Strictly avoid any Western or Americanized vowel sounds. "
        "Pronounce the short 'अ' sound cleanly (e.g., 'जय' must sound like 'J-uh-ye', not 'Jaye'). "
        "Ensure retroflex consonants like 'ट' and 'ड' are sharp and hit hard, "
        "while dental consonants like 'त' and 'द' are completely soft. "
        "Maintain a musical, flowing cadence without robotic clipping."
    )
    
    for idx, key in enumerate(keys):
        print(f"\n--- Testing with Key {idx+1} ---")
        client = genai.Client(api_key=key)
        
        print("Testing gemini-3.1-flash-tts-preview...")
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-tts-preview",
                contents=lyrics,
                config=types.GenerateContentConfig(
                    response_modalities=["audio"],
                    system_instruction=system_instruction,
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                        )
                    )
                )
            )
            print("Status: Success with gemini-3.1-flash-tts-preview!")
            audio_parts = [p for p in response.candidates[0].content.parts if p.inline_data]
            if audio_parts:
                print(f"Received audio bytes: {len(audio_parts[0].inline_data.data)}")
            else:
                print("No audio part found.")
        except Exception as e:
            print(f"Failed with gemini-3.1-flash-tts-preview: {e}")

        print("Testing gemini-2.5-flash-preview-tts...")
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=lyrics,
                config=types.GenerateContentConfig(
                    response_modalities=["audio"],
                    system_instruction=system_instruction,
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                        )
                    )
                )
            )
            print("Status: Success with gemini-2.5-flash-preview-tts!")
            audio_parts = [p for p in response.candidates[0].content.parts if p.inline_data]
            if audio_parts:
                print(f"Received audio bytes: {len(audio_parts[0].inline_data.data)}")
            else:
                print("No audio part found.")
        except Exception as e:
            print(f"Failed with gemini-2.5-flash-preview-tts: {e}")

if __name__ == "__main__":
    test_system_instruction()
