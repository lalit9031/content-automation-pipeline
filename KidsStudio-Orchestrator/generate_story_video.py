import json
import os
import sys
import shutil
import urllib.parse
import subprocess
import requests
from pathlib import Path
from PIL import Image
from pydub import AudioSegment
from google import genai
from google.genai import types

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrate_production import load_dotenv, convert_to_wav
from src.components.text_sanitizer import sanitize_script_for_tts, preprocess_storytelling_pacing
from src.components.vocal_dsp import apply_vocal_dsp_chain
from src.components.dynamic_ducking import mix_vocal_and_music_with_ducking
from src.animate.lip_sync_generator import generate_rhubarb_lip_sync
from src.animate.video_renderer import parse_rhubarb_timings, get_mouth_shape_for_timestamp
from scripts.generate_animation_assets import create_mock_animation_assets

def get_gemini_api_keys() -> list[str]:
    """
    Collects all unique Gemini API keys configured in the environment.
    """
    keys = []
    slots = ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6"]
    for slot in slots:
        val = os.environ.get(slot)
        if val and val.strip() and val not in keys:
            keys.append(val.strip())
    return keys

def generate_story_json() -> list[dict[str, str]]:
    """
    Asks Gemini to write a short Hindi story about a hot summer day in a village
    featuring Kalu (a bird) and Nandu (a boy) in structured JSON format.
    Fails over to alternative keys if one is exhausted.
    """
    keys = get_gemini_api_keys()
    if not keys:
        raise ValueError("❌ No Gemini API keys found in environment variables.")
        
    prompt = (
        "Write a short, engaging story for kids in Hindi (using Devanagari script) about a hot summer day in a village.\n"
        "The story must feature exactly three parts:\n"
        "1. Narrator (who sets the scene and concludes)\n"
        "2. Kalu (a thirsty little bird who speaks)\n"
        "3. Nandu (a kind village boy who helps Kalu find water)\n\n"
        "You must output the story in a strict JSON format matching this schema:\n"
        "{\n"
        "  \"story\": [\n"
        "    { \"speaker\": \"Narrator\", \"text\": \"...\" },\n"
        "    { \"speaker\": \"Kalu\", \"text\": \"...\" },\n"
        "    { \"speaker\": \"Nandu\", \"text\": \"...\" },\n"
        "    ...\n"
        "  ]\n"
        "}\n"
        "Keep the text short (about 4 to 5 sentences total) so it builds quickly. Output ONLY the JSON block."
    )
    
    last_err = None
    for idx, key in enumerate(keys):
        try:
            print(f"🤖 Gemini LLM: Composing structured script using key slot {idx+1}/{len(keys)}...")
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.8
                )
            )
            
            data = json.loads(response.text)
            story_list = data.get("story", [])
            if not story_list:
                raise ValueError("Empty story list returned.")
            print(f"📖 Story composed successfully with {len(story_list)} parts.")
            return story_list
        except Exception as e:
            last_err = e
            print(f"⚠️ Warning: Key slot {idx+1} failed: {e}. Trying next...")
            
    # Fallback if all keys fail
    print("👉 Falling back to default pre-written village story due to API failures.")
    return [
        {"speaker": "Narrator", "text": "गर्मियों का एक बहुत ही गर्म दिन था। गाँव के सभी कुएं सूख चुके थे।"},
        {"speaker": "Kalu", "text": "अरे भाई! मुझे बहुत प्यास लगी है, कहीं पानी नहीं दिख रहा।"},
        {"speaker": "Nandu", "text": "कालू भैया, घबराओ मत! चलो पीपल के पेड़ के पास बने पुराने घड़े को देखते हैं।"},
        {"speaker": "Narrator", "text": "दोनों ने मिलकर पुराने घड़े में कंकड़ डाले, पानी ऊपर आया और कालू ने अपनी प्यास बुझाई।"}
    ]

def generate_village_background() -> Path:
    """
    Attempts to generate a beautiful village scene.
    First tries Pollinations.ai (100% free, Flux model, no keys required),
    then tries Gemini Imagen, and finally falls back to mock_village_background.png.
    """
    assets_dir = PROJECT_ROOT / "assets" / "character"
    bg_path = assets_dir / "village_background.png"
    fallback_path = assets_dir / "mock_village_background.png"
    
    # Clean old generated background if re-running
    if bg_path.exists():
        return bg_path
        
    prompt = (
        "A beautiful 2D cartoon background of a hot sunny day in an Indian village, "
        "with a dusty path, traditional clay huts, green neem trees, and a blazing sun shining bright "
        "in the clear blue sky, vibrant colors, kids storybook illustration style, 16:9 aspect ratio"
    )
    
    # 1. Try Free Pollinations AI (100% Free, no keys required, excellent quality)
    print("🎨 Free AI Artist: Requesting free Pollinations (Flux) image generation...")
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/p/{encoded_prompt}?width=1280&height=720&nologo=true"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        image_bytes = response.content
        if image_bytes:
            bg_path.write_bytes(image_bytes)
            # Ensure proper format resize
            img = Image.open(bg_path)
            img = img.resize((1280, 720), Image.Resampling.LANCZOS)
            img.save(bg_path, "PNG")
            print(f"✨ Free Image Success: Saved background to [{bg_path}]")
            return bg_path
    except Exception as e:
        print(f"⚠️ Free Pollinations generation failed: {e}. Trying Gemini Imagen...")
            
    # 2. Try Gemini Imagen as fallback
    keys = get_gemini_api_keys()
    for idx, key in enumerate(keys):
        try:
            print(f"🖼️ Imagen: Requesting image using key slot {idx+1}/{len(keys)}...")
            client = genai.Client(api_key=key)
            response = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                    output_mime_type="image/png"
                )
            )
            
            image_bytes = None
            if response.generated_images:
                image_bytes = response.generated_images[0].image.image_bytes
                
            if image_bytes:
                bg_path.write_bytes(image_bytes)
                img = Image.open(bg_path)
                img = img.resize((1280, 720), Image.Resampling.LANCZOS)
                img.save(bg_path, "PNG")
                print(f"✨ AI Image Success: Generated village background at [{bg_path}]")
                return bg_path
        except Exception as e:
            print(f"⚠️ Warning: Image key slot {idx+1} failed: {e}. Trying next...")
            
    # 3. Fallback to mock background
    print("👉 Falling back to pre-drawn village background.")
    if not fallback_path.exists():
        create_mock_animation_assets()
    return fallback_path

def compile_audio_and_lipsync(story_list: list[dict[str, str]]) -> tuple[Path, list[tuple[float, float, str]], Path]:
    """
    Generates vocal segments using distinct speaker voices, applies vocal DSP warmth,
    stitches them together, and runs the Rhubarb lipsync timing sheet.
    """
    scratch_dir = PROJECT_ROOT / "scratch"
    output_dir = PROJECT_ROOT / "output"
    scratch_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    speaker_voices = {
        "Narrator": "Rasalgethi",  # Deep, wise narrator
        "Kalu": "Puck",            # Energetic bird
        "Nandu": "Charon"          # Clear kid voice
    }
    
    combined_audio = AudioSegment.empty()
    speaker_timelines = []
    
    print("\n🎙️ Starting Segment Audio Synthesis...")
    
    for idx, part in enumerate(story_list):
        speaker = part["speaker"]
        text = part["text"]
        voice = speaker_voices.get(speaker, "Rasalgethi")
        
        print(f"\n--- Part {idx+1}/{len(story_list)}: [{speaker}] speaks ---")
        
        # 1. Clean script
        pacing_text = preprocess_storytelling_pacing(text)
        clean_text = sanitize_script_for_tts(pacing_text)
        
        seg_raw_path = scratch_dir / f"seg_raw_{idx}.wav"
        seg_dsp_path = scratch_dir / f"seg_dsp_{idx}.wav"
        
        # 2. Generate vocal stem with failover key pooling
        keys = get_gemini_api_keys()
        audio_generated = False
        
        for key_idx, key in enumerate(keys):
            try:
                print(f"🎙️ Querying Gemini TTS (Key slot {key_idx+1}) using preset [{voice}]...")
                client = genai.Client(api_key=key)
                
                speech_config = types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice
                        )
                    )
                )
                
                generate_content_config = types.GenerateContentConfig(
                    temperature=1.0,
                    response_modalities=["audio"],
                    speech_config=speech_config
                )
                
                # Check models
                models = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
                for model in models:
                    try:
                        audio_buffer = bytearray()
                        for chunk in client.models.generate_content_stream(
                            model=model,
                            contents=clean_text,
                            config=generate_content_config
                        ):
                            if chunk.parts:
                                for part in chunk.parts:
                                    if part.inline_data and part.inline_data.data:
                                        audio_buffer.extend(part.inline_data.data)
                                        
                        if audio_buffer:
                            wav_bytes = convert_to_wav(bytes(audio_buffer))
                            seg_raw_path.write_bytes(wav_bytes)
                            audio_generated = True
                            break
                    except Exception:
                        pass
                        
                if audio_generated:
                    break
            except Exception as e:
                print(f"⚠️ Key slot {key_idx+1} failed: {e}. Trying next...")
                
        if not audio_generated:
            raise RuntimeError(f"❌ All Gemini API keys failed to generate audio for part {idx+1}")
            
        # 3. Apply vocal DSP EQ chain
        apply_vocal_dsp_chain(
            input_wav_path=str(seg_raw_path),
            output_wav_path=str(seg_dsp_path),
            hpf_cutoff=85.0,
            warmth_boost_db=3.0,
            warmth_cutoff=200.0
        )
        
        # Load segment
        segment = AudioSegment.from_file(seg_dsp_path)
        
        # Track timeline timestamps
        start_time = len(combined_audio) / 1000.0
        combined_audio += segment
        end_time = len(combined_audio) / 1000.0
        
        speaker_timelines.append((start_time, end_time, speaker))
        print(f"⏱️ Timeline: Segment spans {start_time:.2f}s to {end_time:.2f}s")
            
    # Save the master vocal file
    vocals_master_path = scratch_dir / "story_vocals_master.wav"
    combined_audio.export(vocals_master_path, format="wav")
    print(f"\n🏆 Compiled Vocal Stems -> [{vocals_master_path}]")
    
    # 4. Mix with dynamic ducking (vocals-only export if no background music)
    final_audio_out = output_dir / "village_story_vocals.mp3"
    mix_vocal_and_music_with_ducking(
        vocal_wav_path=str(vocals_master_path),
        music_wav_path=None,
        output_mp3_path=str(final_audio_out)
    )
    
    # 5. Compile Rhubarb Lip-Sync mapping sheet
    lip_sync_out = output_dir / "village_story_lipsync_map.txt"
    generate_rhubarb_lip_sync(
        audio_input_path=str(vocals_master_path),
        output_txt_path=str(lip_sync_out),
        binary_path=str(PROJECT_ROOT / "bin" / "rhubarb")
    )
    
    return vocals_master_path, speaker_timelines, lip_sync_out

def render_story_video(
    bg_path: Path,
    vocals_wav_path: Path,
    speaker_timelines: list[tuple[float, float, str]],
    lip_sync_txt_path: Path,
    output_mp4_path: str,
    fps: int = 24
):
    """
    Composites two talking characters (Kalu and Nandu) onto the village background
    and dynamically animates the correct character's mouth shapes frame-by-frame.
    """
    print("\n🎬 Video Layout Renderer: Initiating frame rendering loop...")
    
    # Assets directory
    assets_dir = PROJECT_ROOT / "assets" / "character"
    kalu_body_path = assets_dir / "kalu_body.png"
    nandu_body_path = assets_dir / "nandu_body.png"
    mouths_dir = assets_dir / "mouths"
    
    # Verify characters exist
    if not kalu_body_path.exists() or not nandu_body_path.exists():
        create_mock_animation_assets()
        
    # Load assets
    bg_img = Image.open(bg_path).convert("RGBA")
    kalu_raw = Image.open(kalu_body_path).convert("RGBA")
    k_w, k_h = kalu_raw.size
    kalu_scaled_w = 250
    kalu_scaled_h = int(k_h * (kalu_scaled_w / k_w))
    kalu_img = kalu_raw.resize((kalu_scaled_w, kalu_scaled_h), Image.Resampling.LANCZOS)
    
    nandu_raw = Image.open(nandu_body_path).convert("RGBA")
    n_w, n_h = nandu_raw.size
    nandu_scaled_w = 160
    nandu_scaled_h = int(n_h * (nandu_scaled_w / n_w))
    nandu_img = nandu_raw.resize((nandu_scaled_w, nandu_scaled_h), Image.Resampling.LANCZOS)
    
    # Parse mouth shapes
    timings = parse_rhubarb_timings(str(lip_sync_txt_path))
    
    # Cache mouth shapes
    mouth_cache = {}
    
    # Audio duration
    sound = AudioSegment.from_file(vocals_wav_path)
    duration_sec = len(sound) / 1000.0
    total_frames = int(duration_sec * fps)
    
    # Temporary frame workspace
    temp_frames_dir = PROJECT_ROOT / "scratch" / "temp_story_frames"
    if temp_frames_dir.exists():
        shutil.rmtree(temp_frames_dir)
    temp_frames_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"   Duration: {duration_sec:.2f}s | Framecount: {total_frames} @ {fps} FPS")
    
    # Layout placements on a 1280x720 canvas
    # Kalu (bird) on left: placed at (150, 380)
    kalu_pos = (150, 380)
    # Nandu (boy) on right: placed at (920, 210)
    nandu_pos = (920, 210)
    
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        
        # 1. Determine active speaker at this timestamp
        active_speaker = "None"
        for start_t, end_t, speaker in speaker_timelines:
            if start_t <= t < end_t:
                active_speaker = speaker
                break
                
        # 2. Get active mouth shape from Rhubarb map
        active_shape = get_mouth_shape_for_timestamp(t, timings)
        
        # Load mouth shapes to cache
        if active_shape not in mouth_cache:
            mouth_file = mouths_dir / f"{active_shape}.png"
            if not mouth_file.exists():
                mouth_file = mouths_dir / "X.png"
            mouth_cache[active_shape] = Image.open(mouth_file).convert("RGBA")
            
        mouth_img = mouth_cache[active_shape]
        closed_mouth = Image.open(mouths_dir / "X.png").convert("RGBA")
        
        # 3. Composite layers
        frame_canvas = bg_img.copy()
        
        # Draw Kalu (bird) on left
        frame_canvas.paste(kalu_img, box=kalu_pos, mask=kalu_img)
        
        # Draw Nandu (boy) on right
        frame_canvas.paste(nandu_img, box=nandu_pos, mask=nandu_img)
        
        # Overlay mouth shapes based on speaker state
        if active_speaker == "Kalu":
            # Animate Kalu (bird), Nandu closed
            k_mouth = mouth_img.resize((45, 45), Image.Resampling.LANCZOS)
            n_mouth = closed_mouth.resize((30, 30), Image.Resampling.LANCZOS)
        elif active_speaker == "Nandu":
            # Animate Nandu (boy), Kalu closed
            k_mouth = closed_mouth.resize((45, 45), Image.Resampling.LANCZOS)
            n_mouth = mouth_img.resize((30, 30), Image.Resampling.LANCZOS)
        else:
            # Narrator speaking or pause: both closed mouth
            k_mouth = closed_mouth.resize((45, 45), Image.Resampling.LANCZOS)
            n_mouth = closed_mouth.resize((30, 30), Image.Resampling.LANCZOS)
            
        # Paste mouths relative to positions of Kalu and Nandu
        # Beak center is at (210, 85) relative to Kalu body
        kalu_mouth_x = kalu_pos[0] + 210 - (k_mouth.width // 2)
        kalu_mouth_y = kalu_pos[1] + 85 - (k_mouth.height // 2)
        
        # Mouth center is at (76, 122) relative to Nandu body
        nandu_mouth_x = nandu_pos[0] + 76 - (n_mouth.width // 2)
        nandu_mouth_y = nandu_pos[1] + 122 - (n_mouth.height // 2)
        
        frame_canvas.paste(k_mouth, box=(kalu_mouth_x, kalu_mouth_y), mask=k_mouth)
        frame_canvas.paste(n_mouth, box=(nandu_mouth_x, nandu_mouth_y), mask=n_mouth)
        
        # Save frame
        frame_path = temp_frames_dir / f"frame_{frame_idx:05d}.png"
        frame_canvas.save(frame_path, "PNG")
        
    # 4. Invoke FFmpeg to compile final video
    print(f"🎥 FFmpeg Core: Merging frames and audio into video [{output_mp4_path}]...")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-r", str(fps),
        "-i", str(temp_frames_dir / "frame_%05d.png"),
        "-i", str(vocals_wav_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        output_mp4_path
    ]
    
    try:
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        print("🏆 Master Video Ready!")
    except subprocess.CalledProcessError as err:
        error_msg = err.stderr if err.stderr else err.stdout
        raise RuntimeError(f"❌ FFmpeg compilation failed: {error_msg}")
    finally:
        # Cleanup
        if temp_frames_dir.exists():
            shutil.rmtree(temp_frames_dir)

def main():
    load_dotenv()
    
    # 1. Clean old background image only if we want to force regeneration
    assets_dir = PROJECT_ROOT / "assets" / "character"
    bg_path = assets_dir / "village_background.png"
    # if bg_path.exists():
    #     os.remove(bg_path)
        
    # 2. Generate script
    story_list = generate_story_json()
    
    # 3. Get background (will use free Pollinations)
    bg_path = generate_village_background()
    
    # 4. Create audio files and timing maps
    vocals_wav_path, speaker_timelines, lip_sync_txt_path = compile_audio_and_lipsync(story_list)
    
    # 5. Render video frames and compile MP4
    output_mp4 = PROJECT_ROOT / "output" / "village_summer_story.mp4"
    render_story_video(
        bg_path=bg_path,
        vocals_wav_path=vocals_wav_path,
        speaker_timelines=speaker_timelines,
        lip_sync_txt_path=lip_sync_txt_path,
        output_mp4_path=str(output_mp4),
        fps=24
    )
    
    print("\n🎉 Complete Story Video Compiled Successfully!")
    print(f"👉 final output: {output_mp4}")

if __name__ == "__main__":
    main()
