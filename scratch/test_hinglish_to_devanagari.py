import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def test_transliteration_and_audio():
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
        
    key = keys[1] if len(keys) > 1 else keys[0] # use Key 2
    client = genai.Client(api_key=key)
    
    # 1. Transliterate Romanized Hinglish to Devanagari
    original_text = "[rhythmic, chanting tone] Jai Hanuman Gyan Gun Sagar, Jai Kapis Tihun Lok Ujagar"
    print(f"Original Romanized text:\n{original_text}")
    
    prompt = (
        "You are a professional Hindi translator.\n"
        "Convert the following Romanized Hindi/Hinglish text into standard native Devanagari script.\n"
        "Maintain all punctuation and bracketed emotion/formatting tags (like [excitedly], [very slow]) exactly as they are.\n"
        "Output ONLY the final Devanagari text. Do not add any explanation, notes, or markdown formatting.\n\n"
        f"Text to convert:\n{original_text}"
    )
    
    print("\nTransliterating using Gemini...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        devanagari_text = response.text.strip()
        print(f"Devanagari text result:\n{devanagari_text}")
    except Exception as e:
        print(f"Transliteration failed: {e}")
        sys.exit(1)
        
    # 2. Generate audio using the transliterated Devanagari text
    print("\nGenerating audio with gemini-3.1-flash-tts-preview...")
    
    # Prepend master accent instructions
    accent_instructions = (
        "You are a native Indian playback singer from Mumbai/Delhi performing traditional music. "
        "You speak and chant with a 100% authentic, clear Indian accent. "
        "Strictly follow Hindi phonetic rules: pronounce 'त' and 'द' as soft dental sounds "
        "(tongue touching the front teeth), and 'ट' and 'ड' as clean retroflex sounds. "
        "Never use Americanized vowel sounds like 'man' for 'मान' or 'say' for 'सा'. "
        "Maintain a resonant, deep chest voice and slightly elongate the vowels to match a musical cadence.\n\n"
        "Here is the text to speak:\n"
    )
    
    full_prompt = accent_instructions + devanagari_text
    
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-tts-preview",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["audio"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                    )
                )
            )
        )
        print("Status: Success!")
        audio_parts = [p for p in response.candidates[0].content.parts if p.inline_data]
        if audio_parts:
            print(f"Received audio bytes: {len(audio_parts[0].inline_data.data)}")
            out_file = Path("scratch/test_hanuman_chalisa_accent.wav")
            out_file.write_bytes(audio_parts[0].inline_data.data)
            print(f"Saved to {out_file}")
        else:
            print("No audio part found.")
    except Exception as e:
        print(f"Audio generation failed: {e}")

if __name__ == "__main__":
    test_transliteration_and_audio()
