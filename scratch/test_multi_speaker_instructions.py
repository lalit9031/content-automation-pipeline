import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def test_multi_speaker_instructions():
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
    
    speech_config = types.SpeechConfig(
        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
            speaker_voice_configs=[
                types.SpeakerVoiceConfig(
                    speaker="Speaker 1",
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Rasalgethi"
                        )
                    ),
                ),
                types.SpeakerVoiceConfig(
                    speaker="Speaker 2",
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Puck"
                        )
                    ),
                ),
            ]
        ),
    )
    
    instructions = (
        "You must speak and chant with a 100% authentic Indian accent.\n"
        "Strictly adhere to Hindi phonetics: use soft dental sounds for 'त' and 'द', "
        "and proper retroflex sounds for 'ट' and 'ड'. Do not truncate trailing vowels.\n"
        "Here is the dialogue to speak:\n"
    )
    
    prompt = instructions + "Speaker 1: [excitedly] चलो बच्चों, शुरू करते हैं। Speaker 2: हाँ, बहुत मज़ा आएगा!"
    
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-tts-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["audio"],
                speech_config=speech_config
            )
        )
        print("Multi-speaker with instructions Status: Success!")
        audio_parts = [p for p in response.candidates[0].content.parts if p.inline_data]
        if audio_parts:
            print(f"Received audio bytes: {len(audio_parts[0].inline_data.data)}")
            out_file = Path("scratch/test_multi_speaker_instructions_output.wav")
            out_file.write_bytes(audio_parts[0].inline_data.data)
            print(f"Saved to {out_file}")
        else:
            print("No audio part found.")
    except Exception as e:
        print(f"Multi-speaker with instructions failed: {e}")

if __name__ == "__main__":
    test_multi_speaker_instructions()
