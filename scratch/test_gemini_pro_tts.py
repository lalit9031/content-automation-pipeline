import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def test_gemini_pro_tts():
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
    
    for idx, key in enumerate(keys):
        print(f"\nTrying Gemini Key {idx + 1} (ends with {key[-6:] if len(key) > 6 else key})...")
        client = genai.Client(api_key=key)
        
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="Hello, this is a test of the Gemini neural TTS system.")],
            ),
        ]
        
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Rasalgethi"
                    )
                )
            ),
        )
        
        try:
            audio_buffer = bytearray()
            mime_type = "audio/L16;rate=24000"
            for chunk in client.models.generate_content_stream(
                model="gemini-2.5-pro-preview-tts",
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
                print("Status: Success!")
                print(f"Received audio bytes: {len(audio_buffer)}, MIME: {mime_type}")
                out_file = Path("scratch/test_gemini_pro_tts_output.wav")
                out_file.write_bytes(audio_buffer)
                print(f"Saved to {out_file}")
                return
            else:
                print("Gemini Neural TTS returned empty audio data buffer.")
        except Exception as e:
            print(f"Error occurred: {e}")

if __name__ == "__main__":
    test_gemini_pro_tts()
