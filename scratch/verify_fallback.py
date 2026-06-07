import os
import sys
import shutil
from pathlib import Path

# Add src to path to import content_pipeline
sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.bots.audio import generate_indian_voiceover
from content_pipeline.config import Settings

def test_audio_pipeline():
    print("Starting verification of audio generation pipeline...")
    
    settings = Settings.from_environment()
    
    # Ensure scratch outputs directory exists
    out_dir = Path("scratch/verify_outputs")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Test Gemini TTS success path
    print("\n--- Test 1: Gemini TTS Generation ---")
    gemini_out = out_dir / "gemini_voice.wav"
    try:
        path = generate_indian_voiceover(
            text="मैया, मैं यहाँ हूँ।",
            output_path=gemini_out,
            voice="Puck"
        )
        print(f"Success! Output path: {path}")
        if path.exists() and path.stat().st_size > 1000:
            print(f"File generated successfully, size: {path.stat().st_size} bytes")
        else:
            print("ERROR: File is empty or does not exist!")
    except Exception as e:
        print(f"Failed Test 1: {e}")

    # 2. Test Edge-TTS Failover path
    print("\n--- Test 2: Edge-TTS Failover (Gemini failure simulation) ---")
    failover_out = out_dir / "failover_voice.wav"
    
    # We create a settings object with invalid keys to force Gemini TTS to fail
    invalid_settings = Settings(
        output_dir=settings.output_dir,
        gemini_api_key="invalid_key_to_force_failure",
        gemini_api_keys=("invalid_key_1", "invalid_key_2"),
        voice_provider="edge",
        indian_tts_voice="hi-IN-MadhurNeural"
    )
    
    # We temporarily mock settings.from_environment or pass invalid settings context if we can.
    # Wait, generate_indian_voiceover reads settings using Settings.from_environment() internally!
    # So to force failure, we can temporarily clear the env variables:
    old_keys = {}
    for k, v in list(os.environ.items()):
        if "GEMINI_API_KEY" in k:
            old_keys[k] = v
            del os.environ[k]
            
    # Set a dummy invalid key
    os.environ["GEMINI_API_KEY"] = "AIzaSy_dummy_invalid_key"
    
    try:
        path = generate_indian_voiceover(
            text="मैया, मैं यहाँ हूँ।",
            output_path=failover_out,
            voice="Puck"
        )
        print(f"Success (Edge-TTS Fallback)! Output path: {path}")
        if path.exists() and path.stat().st_size > 1000:
            print(f"Fallback file generated successfully, size: {path.stat().st_size} bytes")
        else:
            print("ERROR: Fallback file is empty or does not exist!")
    except Exception as e:
        print(f"Failed Test 2 (Failover failed to execute): {e}")
    finally:
        # Restore env keys
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        for k, v in old_keys.items():
            os.environ[k] = v

    print("\nVerification complete.")

if __name__ == "__main__":
    test_audio_pipeline()
