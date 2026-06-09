import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
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
from src.video_pipeline.composer import stitch_scene_segments_procedurally
from src.video_pipeline.motion_engine import calculate_frame_transform
from src.video_pipeline.frame_renderer import render_dynamic_character_frame

def get_gemini_api_keys() -> list[str]:
    keys = []
    slots = ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6"]
    for slot in slots:
        val = os.environ.get(slot)
        if val and val.strip() and val not in keys:
            keys.append(val.strip())
    return keys

def synthesize_vocal_line(text: str, voice: str, output_wav_path: Path) -> bool:
    """
    Queries Gemini Neural TTS with fallback key pooling to generate a single vocal line.
    """
    keys = get_gemini_api_keys()
    if not keys:
        raise ValueError("❌ No Gemini API keys found in environment.")
        
    pacing_text = preprocess_storytelling_pacing(text)
    clean_text = sanitize_script_for_tts(pacing_text)
    
    # Setup speech config
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
    
    models = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
    
    for key_idx, key in enumerate(keys):
        try:
            client = genai.Client(api_key=key)
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
                        output_wav_path.write_bytes(wav_bytes)
                        return True
                except Exception:
                    pass
        except Exception as e:
            print(f"⚠️ Key slot {key_idx+1} failed: {e}. Trying next...")
            
    return False

def apply_camera_effect(frame_img: Image.Image, camera_effect: str, progress: float) -> Image.Image:
    w, h = frame_img.size
    if camera_effect == "zoom_in":
        max_zoom = 1.12
        zoom = 1.0 + (max_zoom - 1.0) * progress
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        x1 = (w - crop_w) // 2
        y1 = (h - crop_h) // 2
        x2 = x1 + crop_w
        y2 = y1 + crop_h
        cropped = frame_img.crop((x1, y1, x2, y2))
        return cropped.resize((w, h), Image.Resampling.LANCZOS)
        
    elif camera_effect == "zoom_out":
        max_zoom = 1.12
        zoom = max_zoom - (max_zoom - 1.0) * progress
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        x1 = (w - crop_w) // 2
        y1 = (h - crop_h) // 2
        x2 = x1 + crop_w
        y2 = y1 + crop_h
        cropped = frame_img.crop((x1, y1, x2, y2))
        return cropped.resize((w, h), Image.Resampling.LANCZOS)
        
    elif camera_effect == "pan_right":
        zoom = 1.12
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        max_x_shift = w - crop_w
        x1 = int(progress * max_x_shift)
        y1 = (h - crop_h) // 2
        x2 = x1 + crop_w
        y2 = y1 + crop_h
        cropped = frame_img.crop((x1, y1, x2, y2))
        return cropped.resize((w, h), Image.Resampling.LANCZOS)
        
    elif camera_effect == "pan_left":
        zoom = 1.12
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        max_x_shift = w - crop_w
        x1 = int((1.0 - progress) * max_x_shift)
        y1 = (h - crop_h) // 2
        x2 = x1 + crop_w
        y2 = y1 + crop_h
        cropped = frame_img.crop((x1, y1, x2, y2))
        return cropped.resize((w, h), Image.Resampling.LANCZOS)
        
    return frame_img

def draw_subtitles(frame_img: Image.Image, text: str, font_path: str):
    if not text or not text.strip():
        return
    draw = ImageDraw.Draw(frame_img)
    w, h = frame_img.size
    
    try:
        font = ImageFont.truetype(font_path, 28)
    except Exception:
        font = ImageFont.load_default()
        
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        lw = bbox[2] - bbox[0]
        if lw < w - 160:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
        
    line_height = font.getbbox("Tg")[3] - font.getbbox("Tg")[1] + 12
    total_h = len(lines) * line_height + 20
    
    box_y1 = h - 90 - total_h
    box_y2 = h - 90
    
    max_w = 0
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        line_widths.append(lw)
        if lw > max_w:
            max_w = lw
            
    box_x1 = (w - max_w) // 2 - 20
    box_x2 = (w + max_w) // 2 + 20
    
    draw.rounded_rectangle([box_x1, box_y1, box_x2, box_y2], radius=12, fill=(0, 0, 0, 155))
    
    for idx, line in enumerate(lines):
        lw = line_widths[idx]
        tx = (w - lw) // 2
        ty = box_y1 + 10 + idx * line_height
        draw.text((tx, ty), line, font=font, fill=(255, 255, 255, 255))

def prepare_layered_assets(assets_dir: Path) -> dict:
    """
    Slices the generated flat character sheets into body and feathers/wing layers.
    Also preloads all phonetic mouth shapes.
    """
    peacock_path = assets_dir / "peacock_body.png"
    kalu_path = assets_dir / "kalu_body.png"
    
    if not peacock_path.exists() or not kalu_path.exists():
        raise FileNotFoundError("Missing Kalu or Peacock raw character body files.")
        
    # 1. Peacock Layer Slicing
    peacock_img = Image.open(peacock_path).convert("RGBA")
    pw, ph = peacock_img.size
    
    peacock_feathers = peacock_img.copy()
    pf_data = list(peacock_feathers.getdata())
    pf_new = []
    for idx, pix in enumerate(pf_data):
        x = idx % pw
        if x >= 560:
            pf_new.append((0, 0, 0, 0)) # erase peacock body/head from feathers layer
        else:
            pf_new.append(pix)
    peacock_feathers.putdata(pf_new)
    
    peacock_body = peacock_img.copy()
    pb_data = list(peacock_body.getdata())
    pb_new = []
    for idx, pix in enumerate(pb_data):
        x = idx % pw
        if x < 400:
            pb_new.append((0, 0, 0, 0)) # erase background feathers from body layer
        else:
            pb_new.append(pix)
    peacock_body.putdata(pb_new)
    
    # 2. Kalu Crow Layer Slicing
    kalu_img = Image.open(kalu_path).convert("RGBA")
    kw, kh = kalu_img.size
    
    kalu_wing = kalu_img.copy()
    kw_data = list(kalu_wing.getdata())
    kw_new = []
    for idx, pix in enumerate(kw_data):
        x = idx % kw
        y = idx // kw
        # Bounding box of Kalu's side wing
        if 360 <= x < 680 and 320 <= y < 550:
            kw_new.append(pix)
        else:
            kw_new.append((0, 0, 0, 0))
    kalu_wing.putdata(kw_new)
    
    # Body layer keeps the torso and head static
    kalu_body = kalu_img.copy()
    
    # 3. Load mouth shape assets
    mouths_dir = assets_dir / "mouths"
    mouth_shapes = ["A", "B", "C", "D", "E", "F", "G", "H", "X"]
    mouth_assets = {}
    for shape in mouth_shapes:
        p = mouths_dir / f"{shape}.png"
        if p.exists():
            mouth_assets[shape] = Image.open(p).convert("RGBA")
            
    return {
        "peacock": {
            "body": peacock_body,
            "feathers": peacock_feathers,
            "feather_pivot": (300, ph - 100),
            "mouth_anchor_coordinates": (730 - 100, 230 - 100), # Center mouth 200x200
            "mouths": mouth_assets
        },
        "kalu": {
            "body": kalu_body,
            "feathers": kalu_wing,
            "feather_pivot": (450, 360),
            "mouth_anchor_coordinates": (180 - 100, 200 - 100),
            "mouths": mouth_assets
        }
    }

def render_scene_segment(
    scene_config: dict,
    fps: int,
    resolution: tuple[int, int],
    cache_scenes_dir: Path
) -> Path:
    scene_id = scene_config["scene_id"]
    print(f"\n🎬 Scene Pipeline: Processing Scene [{scene_id}]...")
    
    scratch_dir = PROJECT_ROOT / "scratch" / scene_id
    scratch_dir.mkdir(parents=True, exist_ok=True)
    
    voice_presets = {
        "Narrator": "Rasalgethi",
        "Peacock": "Charon",
        "Kalu": "Puck"
    }
    
    dialogue = scene_config.get("dialogue", [])
    characters = scene_config.get("characters", [])
    bg_asset_path = PROJECT_ROOT / scene_config["background_asset"]
    
    # 1. Synthesize all dialogue lines
    segment_wavs = []
    segment_durations = []
    
    for idx, line in enumerate(dialogue):
        speaker = line["speaker"]
        text = line["text"]
        voice = voice_presets.get(speaker, "Rasalgethi")
        
        seg_raw = scratch_dir / f"line_{idx}_raw.wav"
        seg_dsp = scratch_dir / f"line_{idx}_dsp.wav"
        
        print(f"🎙️ Synthesizing line {idx+1}/{len(dialogue)}: [{speaker}] speaks...")
        success = synthesize_vocal_line(text, voice, seg_raw)
        if not success:
            raise RuntimeError(f"❌ Failed to synthesize audio for speaker: {speaker}")
            
        # Apply DSP filter
        apply_vocal_dsp_chain(
            input_wav_path=str(seg_raw),
            output_wav_path=str(seg_dsp),
            hpf_cutoff=85.0,
            warmth_boost_db=3.0,
            warmth_cutoff=200.0
        )
        
        audio_segment = AudioSegment.from_file(seg_dsp)
        segment_wavs.append(audio_segment)
        segment_durations.append(len(audio_segment))
        
    if not segment_wavs:
        raise ValueError(f"❌ No dialogue lines synthesized for scene: {scene_id}")
        
    # 2. Build master vocal track
    master_vocal = AudioSegment.empty()
    for seg in segment_wavs:
        master_vocal += seg
        
    scene_master_wav = scratch_dir / "scene_master_vocals.wav"
    master_vocal.export(scene_master_wav, format="wav")
    
    # Total duration of the scene
    total_duration_ms = len(master_vocal)
    total_duration_sec = total_duration_ms / 1000.0
    total_frames = int(total_duration_sec * fps)
    
    # Compile dialogue subtitles timeline mapping
    dialogue_timelines = []
    curr_time_ms = 0
    for idx, line in enumerate(dialogue):
        dur_ms = segment_durations[idx]
        start_s = curr_time_ms / 1000.0
        end_s = (curr_time_ms + dur_ms) / 1000.0
        dialogue_timelines.append((start_s, end_s, line["text"]))
        curr_time_ms += dur_ms
        
    # 3. Build character-specific vocal tracks with padding
    character_lipsync_maps = {}
    speakers_in_scene = set(line["speaker"] for line in dialogue)
    
    for speaker in speakers_in_scene:
        if speaker.lower() not in ["kalu", "peacock"]:
            continue
            
        char_vocal = AudioSegment.empty()
        for idx, line in enumerate(dialogue):
            seg_len = segment_durations[idx]
            if line["speaker"] == speaker:
                char_vocal += segment_wavs[idx]
            else:
                char_vocal += AudioSegment.silent(duration=seg_len)
                
        char_wav_path = scratch_dir / f"vocal_{speaker.lower()}.wav"
        char_vocal.export(char_wav_path, format="wav")
        
        # Run Rhubarb
        sync_txt_path = scratch_dir / f"lipsync_{speaker.lower()}.txt"
        generate_rhubarb_lip_sync(
            audio_input_path=str(char_wav_path),
            output_txt_path=str(sync_txt_path),
            binary_path=str(PROJECT_ROOT / "bin" / "rhubarb")
        )
        
        character_lipsync_maps[speaker.lower()] = parse_rhubarb_timings(str(sync_txt_path))
        print(f"🎬 Rhubarb Sync: Generated separate timing sheet for [{speaker}]")
        
    # 4. Prepare layered puppet assets
    assets_dir = PROJECT_ROOT / "assets" / "character"
    layered_puppets = prepare_layered_assets(assets_dir)
    
    # Load and scale background
    if not bg_asset_path.exists():
        raise FileNotFoundError(f"Missing background asset: {bg_asset_path}")
    bg_img = Image.open(bg_asset_path).convert("RGBA")
    bg_img = bg_img.resize(resolution, Image.Resampling.LANCZOS)
    
    # Temp frame workspace
    temp_frames_dir = scratch_dir / "temp_frames"
    if temp_frames_dir.exists():
        shutil.rmtree(temp_frames_dir)
    temp_frames_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🖼️ Layout Renderer: Rendering {total_frames} frames ({total_duration_sec:.2f}s) @ {fps} FPS...")
    
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        frame_canvas = bg_img.copy()
        
        # Composite all characters in scene
        for char_entry in characters:
            char_id = char_entry["id"]
            baseline_scale_w = char_entry["scale"]
            
            motion_config = char_entry.get("motion_path", {
                "enabled": False,
                "start_position": [100, 100],
                "start_scale": 1.0
            })
            if "start_position" not in motion_config:
                motion_config["start_position"] = char_entry.get("position", [100, 100])
            if "start_scale" not in motion_config:
                motion_config["start_scale"] = 1.0
                
            # Determine active mouth shape based on timestamps
            active_state = "idle"
            for state_entry in char_entry.get("states", []):
                start_tr, end_tr = state_entry["time_range"]
                if start_tr <= t < end_tr:
                    active_state = state_entry["animation_state"]
                    break
                    
            active_shape = "X"
            if active_state == "talking_lip_sync" and char_id in character_lipsync_maps:
                active_shape = get_mouth_shape_for_timestamp(t, character_lipsync_maps[char_id])
                
            # Get character puppet layers
            puppet = layered_puppets[char_id]
            
            # Render character puppet frame at base resolution (retains smooth edges)
            char_puppet_frame = render_dynamic_character_frame(
                frame_index=frame_idx,
                fps=fps,
                character_assets=puppet,
                active_mouth_shape=active_shape
            )
            
            # Calculate transform scale and positions
            (curr_x, curr_y), curr_scale = calculate_frame_transform(
                frame_index=frame_idx,
                fps=fps,
                motion_config=motion_config
            )
            
            orig_w, orig_h = char_puppet_frame.size
            current_w = int(baseline_scale_w * curr_scale)
            current_h = int(orig_h * (current_w / orig_w))
            
            # Scale puppet frame on the fly
            char_resized = char_puppet_frame.resize((current_w, current_h), Image.Resampling.LANCZOS)
            
            # Paste character onto the scene canvas
            char_pos = (int(curr_x), int(curr_y))
            frame_canvas.paste(char_resized, box=char_pos, mask=char_resized)
            
        # 5. Apply Camera zoom/pan effect to full composited frame
        camera_effect = scene_config.get("camera_effect", "static")
        frame_canvas = apply_camera_effect(frame_canvas, camera_effect, frame_idx / total_frames)
        
        # 6. Overlay Hindi Subtitles static on top of camera transformed frame
        active_subtitle = ""
        for s_t, e_t, txt in dialogue_timelines:
            if s_t <= t < e_t:
                active_subtitle = txt
                break
        draw_subtitles(frame_canvas, active_subtitle, "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        
        # Save frame
        frame_path = temp_frames_dir / f"frame_{frame_idx:05d}.png"
        frame_canvas.save(frame_path, "PNG")
        
    # 7. Compile segment MP4 using FFmpeg
    output_mp4 = cache_scenes_dir / f"{scene_id}.mp4"
    print(f"🎥 FFmpeg: Assembling segment video -> [{output_mp4}]")
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-r", str(fps),
        "-i", str(temp_frames_dir / "frame_%05d.png"),
        "-i", str(scene_master_wav),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_mp4)
    ]
    
    try:
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        print(f"✨ Scene compile completed successfully: {output_mp4.name}")
    except subprocess.CalledProcessError as err:
        error_msg = err.stderr if err.stderr else err.stdout
        raise RuntimeError(f"❌ FFmpeg segment compilation failed: {error_msg}")
    finally:
        # Cleanup
        if temp_frames_dir.exists():
            shutil.rmtree(temp_frames_dir)
            
    return output_mp4

def main():
    load_dotenv()
    
    timeline_path = PROJECT_ROOT / "timeline.json"
    if not timeline_path.exists():
        raise FileNotFoundError(f"❌ Manifest timeline.json not found at {timeline_path}")
        
    with open(timeline_path, "r") as f:
        config = json.load(f)
        
    resolution_str = config.get("resolution", "1280x720")
    res_w, res_h = map(int, resolution_str.lower().split("x"))
    resolution = (res_w, res_h)
    
    fps = config.get("fps", 24)
    scenes = config.get("scenes", [])
    
    cache_scenes_dir = PROJECT_ROOT / "scratch" / "cache_scenes"
    if cache_scenes_dir.exists():
        shutil.rmtree(cache_scenes_dir)
    cache_scenes_dir.mkdir(parents=True, exist_ok=True)
    
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    
    compiled_clips = []
    
    for scene in scenes:
        clip_path = render_scene_segment(
            scene_config=scene,
            fps=fps,
            resolution=resolution,
            cache_scenes_dir=cache_scenes_dir
        )
        compiled_clips.append(clip_path)
        
    # Stitch the segments procedurally
    temp_stitched_path = output_dir / "ghamandi_mor_stitched_temp.mp4"
    stitch_scene_segments_procedurally(
        segment_directory=str(cache_scenes_dir),
        final_output_path=str(temp_stitched_path)
    )
    
    print("\n🔊 Audio Post-Processing: Mastering background music with ducking...")
    
    temp_vocals_wav = PROJECT_ROOT / "scratch" / "combined_master_vocals.wav"
    # Extract audio stream from stitched video
    ffmpeg_extract_cmd = [
        "ffmpeg", "-y", "-i", str(temp_stitched_path),
        "-vn", "-c:a", "pcm_s16le", str(temp_vocals_wav)
    ]
    try:
        subprocess.run(ffmpeg_extract_cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as err:
        print(f"⚠️ Failed to extract vocals track: {err}")
        temp_vocals_wav = None
        
    final_output = output_dir / "ghamandi_mor_final.mp4"
    bg_music_path = PROJECT_ROOT / "assets" / "character" / "bg_music.mp3"
    
    if temp_vocals_wav and bg_music_path.exists():
        temp_mixed_audio = PROJECT_ROOT / "scratch" / "combined_vocals_music.mp3"
        # Run sidechain ducking mixdown
        mix_vocal_and_music_with_ducking(
            vocal_wav_path=str(temp_vocals_wav),
            music_wav_path=str(bg_music_path),
            output_mp3_path=str(temp_mixed_audio),
            duck_gain_db=-18.0,
            idle_gain_db=-6.0
        )
        
        # Combine stitched video with the ducked master audio track
        print("🎥 Injecting mastered soundtrack into final Gold Master video...")
        ffmpeg_merge_cmd = [
            "ffmpeg", "-y", "-i", str(temp_stitched_path), "-i", str(temp_mixed_audio),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(final_output)
        ]
        try:
            subprocess.run(ffmpeg_merge_cmd, capture_output=True, check=True)
            print("✨ Injection successful.")
        except subprocess.CalledProcessError as err:
            print(f"⚠️ Audio injection failed: {err.stderr.decode() if err.stderr else str(err)}. Copying temp video as master.")
            shutil.copy(temp_stitched_path, final_output)
    else:
        print("⚠️ Background music asset or vocals extraction failed. Keeping default vocals audio track.")
        shutil.copy(temp_stitched_path, final_output)
        
    if temp_stitched_path.exists():
        os.remove(temp_stitched_path)
    
    print("\n🎉 Gold Master Moral Story Video Produced Successfully!")
    print(f"👉 Final Video Path: {final_output}")

if __name__ == "__main__":
    main()
