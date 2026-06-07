import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def test_prompt_instructions():
    settings = Settings.from_environment()
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    
    keys = [k for k in keys if k]
    if not keys:
        print("No GEMINI_API_KEY found!")
        sys.exit(1)
        
    key = keys[1] if len(keys) > 1 else keys[0] # use Key 2
    client = genai.Client(api_key=key)
    
    instructions = (
        "You are an expert native Indian playback singer. "
        "You must speak and chant with a 100% authentic Indian accent. "
        "Strictly adhere to Hindi phonetics: use soft dental sounds for 'त' and 'द', "
        "and proper retroflex sounds for 'ट' and 'ड'. Do not truncate trailing vowels. "
        "Match your vocal pacing, emotional weight, and cadence perfectly. "
        "Here is the text to speak:\n"
    )
    
    prompt = instructions + "[excitedly] गाड़ी में अपनी तू बैठ जा... आज रात का सीन ऑन है..."
    
    models = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
    
    for model in models:
        print(f"\nTesting {model} with prompt-level instructions...")
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
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
                data = audio_parts[0].inline_data.data
                print(f"Received audio bytes: {len(data)}")
                out_file = Path(f"scratch/test_{model.replace('-', '_')}_prompt_instructions.wav")
                out_file.write_bytes(data)
                print(f"Saved to {out_file}")
            else:
                print("No audio part found.")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    test_prompt_instructions()
