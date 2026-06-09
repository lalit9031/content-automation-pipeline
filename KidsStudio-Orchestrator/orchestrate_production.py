import os
import struct
import sys
from pathlib import Path
from google import genai
from google.genai import types

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.studio_manifest import KIDS_STUDIO_MASTER_REGISTRY
from src.components.text_sanitizer import sanitize_script_for_tts, preprocess_storytelling_pacing
from src.components.vocal_dsp import apply_vocal_dsp_chain
from src.components.dynamic_ducking import mix_vocal_and_music_with_ducking
from src.animate.lip_sync_generator import generate_rhubarb_lip_sync
from src.animate.video_renderer import render_talking_avatar_video
from scripts.generate_animation_assets import create_mock_animation_assets

def load_dotenv():
    """
    Manually loads key API configs from the pipeline project .env file if available.
    """
    env_paths = [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT.parent / "content-automation-pipeline" / ".env",
        Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/.env")
    ]
    for env_path in env_paths:
        if env_path.exists():
            print(f"🔑 Loading active API keys from environment: {env_path}")
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
            break

def convert_to_wav(audio_data: bytes, sample_rate: int = 24000) -> bytes:
    """
    Packs raw PCM L16 audio bytes into a standard WAVE container.
    """
    num_channels = 1
    bits_per_sample = 16
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size
    
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size
    )
    return header + audio_data

def generate_gemini_voiceover(text: str, voice_name: str, output_path: Path) -> Path:
    """
    Fetches the speech generation stem from Gemini Neural TTS API.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Check alternative slots
        for key_slot in ["GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6"]:
            if os.environ.get(key_slot):
                api_key = os.environ.get(key_slot)
                break
                
    if not api_key:
        raise ValueError(
            "❌ GEMINI_API_KEY not found in environment.\n"
            "👉 Please write your key in a .env file at the project root."
        )
        
    client = genai.Client(api_key=api_key)
    
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=voice_name
            )
        )
    )
    
    generate_content_config = types.GenerateContentConfig(
        temperature=1.0,
        response_modalities=["audio"],
        speech_config=speech_config
    )
    
    models = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
    last_err = None
    
    for model in models:
        try:
            print(f"🎙️ Querying Gemini TTS [{model}] using voice preset [{voice_name}]...")
            audio_buffer = bytearray()
            
            # Stream audio blocks
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=text,
                config=generate_content_config
            ):
                if chunk.parts:
                    for part in chunk.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_buffer.extend(part.inline_data.data)
                            
            if audio_buffer:
                wav_bytes = convert_to_wav(bytes(audio_buffer))
                output_path.write_bytes(wav_bytes)
                print(f"✨ TTS generation complete: Saved vocal stem to [{output_path}]")
                return output_path
                
        except Exception as e:
            last_err = e
            print(f"⚠️ Warning: Model {model} failed: {e}. Trying next...")
            
    if last_err:
        raise last_err
    raise RuntimeError("Gemini TTS failed to generate audio.")

def run_master_studio_pipeline(script_text: str, profile_mode: str, music_path: str = None):
    """
    Executes the entire Kids Studio content orchestrator pass.
    """
    print(f"\n🚀 Starting Kids Studio production run for: [{profile_mode}]")
    
    # 1. Fetch parameters from manifest config
    config = KIDS_STUDIO_MASTER_REGISTRY.get(profile_mode)
    if not config:
        raise ValueError(f"❌ Invalid preset key: {profile_mode}")
        
    # Directories layout setup
    scratch_dir = PROJECT_ROOT / "scratch"
    output_dir = PROJECT_ROOT / "output"
    scratch_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    # Static character asset locations
    body_png_path = PROJECT_ROOT / "assets" / "character" / "character_body.png"
    mouths_dir_path = PROJECT_ROOT / "assets" / "character" / "mouths"
    
    # Auto-generate character assets if they are missing
    if not body_png_path.exists() or not mouths_dir_path.exists():
        print("🎨 Character assets not found. Auto-generating default mock face and mouth shapes...")
        create_mock_animation_assets()
    
    raw_tts_stem = scratch_dir / "raw_tts_stem.wav"
    dsp_vocal_stem = scratch_dir / "dsp_vocal_stem.wav"
    final_master_out = output_dir / f"master_track_{profile_mode}.mp3"
    lip_sync_out = output_dir / f"lip_sync_map_{profile_mode}.txt"
    final_video_out = output_dir / f"animated_story_{profile_mode}.mp4"
    
    # 2. Text Pacing and Sanitization
    print("📝 Sanitizing script and pre-processing storytelling punctuation...")
    pacing_script = preprocess_storytelling_pacing(script_text)
    clean_speech_text = sanitize_script_for_tts(pacing_script)
    print(f"   Cleaned Input: \"{clean_speech_text}\"")
    
    # 3. Gemini Neural TTS Stem Generation
    generate_gemini_voiceover(
        text=clean_speech_text,
        voice_name=config["gemini_voice"],
        output_path=raw_tts_stem
    )
    
    # 4. Vocal DSP Warmth Filter Chain
    apply_vocal_dsp_chain(
        input_wav_path=str(raw_tts_stem),
        output_wav_path=str(dsp_vocal_stem),
        hpf_cutoff=85.0,
        warmth_boost_db=3.0,
        warmth_cutoff=200.0
    )
    
    # 5. Background Dynamic Ducking mixdown
    # If no music_path is provided, we can pass None, and it will export clean voice master
    mix_vocal_and_music_with_ducking(
        vocal_wav_path=str(dsp_vocal_stem),
        music_wav_path=music_path,
        output_mp3_path=str(final_master_out)
    )
    
    # 6. Automated 2D Lip Sync timing mapping
    try:
        generate_rhubarb_lip_sync(
            audio_input_path=str(dsp_vocal_stem),
            output_txt_path=str(lip_sync_out),
            binary_path=str(PROJECT_ROOT / "bin" / "rhubarb")
        )
    except Exception as e:
        print(f"⚠️ Lip sync timing script skipped or failed: {e}")
        return
        
    # 7. Generate talking avatar video
    try:
        render_talking_avatar_video(
            body_png_path=str(body_png_path),
            mouths_dir_path=str(mouths_dir_path),
            mouth_pos_xy=(300, 430), # Center coordinates for mouth overlay
            timing_txt_path=str(lip_sync_out),
            audio_wav_path=str(dsp_vocal_stem),
            output_mp4_path=str(final_video_out),
            fps=24
        )
    except Exception as e:
        print(f"⚠️ Video rendering pass failed: {e}")
        
    print("\n🎉 Orchestration Pass Complete!")
    print(f"👉 Master mixed audio: {final_master_out}")
    print(f"👉 2D mouth timings: {lip_sync_out}")
    print(f"👉 Final Talking Video: {final_video_out}")

if __name__ == "__main__":
    # Load API keys from env
    load_dotenv()
    
    # Run test pipeline with Madhur voice profile
    story_script = "[Narrator] एक बहुत ही प्यारे छोटे से गांव में, एक नन्हा पिल्ला रहता था [pause]। वह बहुत नटखट था।"
    
    run_master_studio_pipeline(
        script_text=story_script,
        profile_mode="STORY_MALE_PREMIUM"
    )
