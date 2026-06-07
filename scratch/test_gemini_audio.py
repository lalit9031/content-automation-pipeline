import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

# Add src to path to import Settings
sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def test_gemini_audio():
    settings = Settings.from_environment()
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    
    keys = [k for k in keys if k]
    if not keys:
        print("No GEMINI_API_KEY found!")
        sys.exit(1)
        
    print(f"Loaded {len(keys)} Gemini keys from settings.")
    
    models_to_test = [
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts"
    ]
    
    for idx, key in enumerate(keys):
        print(f"\n==========================================")
        print(f"Trying Gemini Key {idx + 1} (ends with {key[-6:] if len(key) > 6 else key})...")
        client = genai.Client(api_key=key)
        
        for model in models_to_test:
            print(f"\n--- Testing model: {model} ---")
            
            # Try 1: with system instruction
            print("Try 1: With system instruction...")
            system_instruction = (
                "You are an expert native Indian playback singer. "
                "You must speak and chant with a 100% authentic Indian accent. "
                "Strictly adhere to Hindi phonetics: use soft dental sounds for 'त' and 'द', "
                "and proper retroflex sounds for 'ट' and 'ड'."
            )
            prompt = "[excitedly] गाड़ी में अपनी तू बैठ जा..."
            
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
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
                    out_file = Path(f"scratch/test_{model.replace('-', '_')}_sys.wav")
                    out_file.write_bytes(audio_parts[0].inline_data.data)
                    print(f"Saved to {out_file}")
                    # Keep trying other things to see all combinations
                else:
                    print("No audio part found.")
            except Exception as e:
                print(f"Try 1 failed: {e}")
                
            # Try 2: without system instruction
            print("Try 2: Without system instruction...")
            try:
                response = client.models.generate_content(
                    model=model,
                    contents="जय हनुमान ज्ञान गुन सागर।",
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
                    out_file = Path(f"scratch/test_{model.replace('-', '_')}_nosys.wav")
                    out_file.write_bytes(audio_parts[0].inline_data.data)
                    print(f"Saved to {out_file}")
                else:
                    print("No audio part found.")
            except Exception as e:
                print(f"Try 2 failed: {e}")

if __name__ == "__main__":
    test_gemini_audio()

