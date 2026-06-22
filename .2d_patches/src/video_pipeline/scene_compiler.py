import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pydub import AudioSegment
from google import genai
from google.genai import types

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrate_production import load_dotenv, convert_to_wav
from src.components.text_sanitizer import sanitize_script_for_tts, preprocess_storytelling_pacing
from src.components.vocal_dsp import apply_vocal_dsp_chain
from src.components.dynamic_ducking import mix_vocal_and_music_with_ducking
from src.animate.lip_sync_generator import generate_rhubarb_lip_sync
from src.animate.video_renderer import parse_rhubarb_timings, get_mouth_shape_for_timestamp
from src.video_pipeline.composer import stitch_scene_segments_procedurally
from src.video_pipeline.motion_engine import calculate_frame_transform, calculate_walk_transform
from src.video_pipeline.frame_renderer import render_dynamic_character_frame
from src.video_pipeline.asset_loader import load_dynamic_character_bundle
from src.utils.janitor import archive_and_purge_project, run_global_housekeeping_if_due


def _infer_actor_height_ratio(folder_name: str) -> float:
    name = folder_name.lower()
    if any(token in name for token in ("crow", "peacock", "bird", "squirrel")):
        return 0.25
    if any(token in name for token in ("rabbit", "deer")):
        return 0.40
    if any(token in name for token in ("nandu", "boy", "girl", "child", "kid", "human")):
        return 0.46
    return 0.38


def _resolve_actor_size(bundle: dict, char_spec: dict, canvas_h: int, motion_scale: float) -> tuple[int, int]:
    body_w, body_h = bundle["body_dimensions"]
    ratio = char_spec.get("target_screen_height_ratio")
    if ratio is None:
        ratio = _infer_actor_height_ratio(char_spec.get("folder_name", ""))
    try:
        ratio_f = max(0.08, min(float(ratio), 0.90))
    except Exception:
        ratio_f = _infer_actor_height_ratio(char_spec.get("folder_name", ""))
    folder_name = str(char_spec.get("folder_name", "")).lower()
    if any(token in folder_name for token in ("crow", "bird", "peacock", "squirrel")):
        if "crow" in folder_name:
            bird_cap = 0.10
        elif "peacock" in folder_name:
            bird_cap = 0.16
        elif "squirrel" in folder_name:
            bird_cap = 0.18
        else:
            bird_cap = 0.14
        ratio_f = min(ratio_f, bird_cap)
    target_h = max(1, int(canvas_h * ratio_f * motion_scale))
    target_w = max(1, int(target_h * (body_w / body_h)))
    return target_w, target_h


def _resolve_actor_draw_position(char_spec: dict, current_coords: tuple[float, float], current_size: tuple[int, int]) -> tuple[int, int]:
    placement_mode = char_spec.get("placement_mode", "top_left")
    x, y = current_coords
    width, height = current_size
    if placement_mode == "ground":
        return int(round(x - (width / 2))), int(round(y - height))
    if placement_mode == "center":
        return int(round(x - (width / 2))), int(round(y - (height / 2)))
    return int(round(x)), int(round(y))


def _load_optional_foreground_overlay(bg_asset_path: Path, manifest: dict, scene: dict, resolution: tuple[int, int]) -> Image.Image | None:
    candidates = []
    explicit = scene.get("foreground_asset") or scene.get("foreground_overlay") or manifest.get("foreground_asset") or manifest.get("foreground_overlay")
    if explicit:
        candidates.append(PROJECT_ROOT / explicit)
    stem = bg_asset_path.stem
    candidates.extend([
        bg_asset_path.with_name(f"{stem}_foreground.png"),
        bg_asset_path.with_name(f"{stem}_fg.png"),
        bg_asset_path.with_name(f"{stem}_overlay.png"),
    ])
    for candidate in candidates:
        if candidate.exists():
            return Image.open(candidate).convert("RGBA").resize(resolution, Image.Resampling.BICUBIC)
    return None


def _apply_foreground_depth_overlay(frame_canvas: Image.Image, overlay: Image.Image | None, scene: dict) -> Image.Image:
    if overlay is None:
        return frame_canvas
    result = frame_canvas.copy()
    # Respect a simple depth order: the overlay sits in front of the characters.
    alpha = overlay.getchannel("A")
    if alpha.getbbox() is None:
        return result
    result.alpha_composite(overlay)
    return result


def _apply_walk_pose(character_img: Image.Image, tilt_degrees: float, placement_mode: str) -> Image.Image:
    if abs(tilt_degrees) < 0.25:
        return character_img
    pivot_center = (character_img.width / 2.0, character_img.height * 0.93)
    rotated = character_img.rotate(
        tilt_degrees,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        center=pivot_center,
    )
    return rotated


def _flatten_frame_for_export(frame_canvas: Image.Image) -> Image.Image:
    """
    Export frames as opaque RGB images so ffmpeg does not inherit any alpha
    channel from the layered compositor.
    """
    if frame_canvas.mode == "RGB":
        return frame_canvas
    return frame_canvas.convert("RGB")


def _apply_speaker_focus_crop(
    frame_canvas: Image.Image,
    focus_xy: tuple[int, int] | None,
    scene: dict,
    canvas_w: int,
    canvas_h: int,
    progress: float,
) -> Image.Image:
    if not focus_xy:
        return frame_canvas

    effect = str(scene.get("camera_effect", "static")).lower()
    crop_ratio = float(scene.get("speaker_focus_crop_ratio", 0.86))
    if effect in {"zoom_in", "zoom_out"}:
        crop_ratio = min(crop_ratio, 0.82)
    elif effect in {"pan_left", "pan_right"}:
        crop_ratio = min(crop_ratio, 0.88)
    crop_ratio = max(0.72, min(crop_ratio, 0.95))

    crop_w = max(1, int(canvas_w * crop_ratio))
    crop_h = max(1, int(canvas_h * crop_ratio))
    focus_x, focus_y = focus_xy
    y_bias = int(round(canvas_h * float(scene.get("speaker_focus_y_bias", 0.05))))
    x1 = max(0, min(int(focus_x - (crop_w / 2.0)), canvas_w - crop_w))
    y1 = max(0, min(int(focus_y - (crop_h / 2.0) - y_bias), canvas_h - crop_h))
    cropped_view = frame_canvas.crop((x1, y1, x1 + crop_w, y1 + crop_h))
    return cropped_view.resize((canvas_w, canvas_h), Image.Resampling.BICUBIC)


def clean_vowels_and_transliterate(name: str) -> str:
    # basic mapping of devanagari letters to english sounds
    mapping = {
        'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri',
        'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
        'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'n',
        'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'n',
        'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
        'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
        'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
        'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
        'ा': 'a', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri',
        'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'n', 'ः': 'h',
        'ॉ': 'o', '्': '', '़': ''
    }
    translit = "".join(mapping.get(char, char) for char in name).lower()
    vowels = {'a', 'e', 'i', 'o', 'u', 'y'}
    return "".join(c for c in translit if c.isalpha() and c not in vowels)

def find_matching_character_folder(speaker: str, characters: list) -> str | None:
    speaker_clean = speaker.lower().strip()
    if not speaker_clean or speaker_clean == "narrator":
        return None
        
    for char_spec in characters:
        folder = char_spec["folder_name"]
        if speaker_clean in folder.lower() or folder.lower() in speaker_clean:
            return folder
            
    s_norm = clean_vowels_and_transliterate(speaker)
    if s_norm:
        for char_spec in characters:
            folder = char_spec["folder_name"]
            f_norm = clean_vowels_and_transliterate(folder)
            if s_norm in f_norm or f_norm in s_norm:
                return folder
                
    non_prop_chars = []
    for char_spec in characters:
        folder = char_spec["folder_name"]
        if "prop" not in folder.lower() and "carrot" not in folder.lower() and "background" not in folder.lower():
            non_prop_chars.append(folder)
            
    if len(non_prop_chars) == 1:
        return non_prop_chars[0]
        
    if characters:
        return characters[0]["folder_name"]
        
    return None

def get_gemini_api_keys() -> list[str]:
    keys = []
    slots = ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6"]
    for slot in slots:
        val = os.environ.get(slot)
        if val and val.strip() and val not in keys:
            keys.append(val.strip())
    return keys

def synthesize_vocal_line(text: str, voice: str, output_wav_path: Path) -> bool:
    # Reuse existing synthesized WAV to avoid hitting API rate limits during retries
    if output_wav_path.exists() and output_wav_path.stat().st_size > 0:
        print(f"👉 Reusing cached vocal track: {output_wav_path.name}")
        return True

    keys = get_gemini_api_keys()
    if not keys:
        raise ValueError("❌ No Gemini API keys found in environment.")
        
    pacing_text = preprocess_storytelling_pacing(text)
    clean_text = sanitize_script_for_tts(pacing_text)
    
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
                for attempt in range(4):
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
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            import time
                            print(f"⚠️ Rate limited (429) on key slot {key_idx+1}. Retrying in 60 seconds (attempt {attempt+1}/4)...")
                            time.sleep(60)
                        else:
                            print(f"⚠️ Model {model} failed on key slot {key_idx+1}: {e}")
                            break
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
        return cropped.resize((w, h), Image.Resampling.BICUBIC)
        
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
        return cropped.resize((w, h), Image.Resampling.BICUBIC)
        
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
        return cropped.resize((w, h), Image.Resampling.BICUBIC)
        
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
        return cropped.resize((w, h), Image.Resampling.BICUBIC)
        
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

def compile_dynamic_scene_sequence(project_manifest_path: str, output_scratch_dir: str = "./scratch/render_output"):
    """
    Decoupled rendering compiler. Reads manifest JSON, loads resources on the fly,
    runs speech synthesis, Rhubarb lip-sync, camera effects, subtitles, and outputsGold Master.
    """
    # Auto-run 3-day housekeeping cycle on our parent scratch workspace
    try:
        run_global_housekeeping_if_due(scratch_dir_path=str(PROJECT_ROOT.parent))
    except Exception as e:
        print(f"⚠️ Janitor Warning: Auto-housekeeping failed: {e}")

    manifest_file = Path(project_manifest_path)
    if not manifest_file.exists():
        raise FileNotFoundError(f"❌ Project Manifest not found at: {project_manifest_path}")

    project_dir = manifest_file.parent
    
    # 1. Parse layout design config
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    canvas_w, canvas_h = tuple(manifest["canvas_dimensions"])
    resolution = (canvas_w, canvas_h)
    fps = manifest.get("fps", 24)
    
    project_dir = manifest_file.parent
    render_output_dir = project_dir / "render_output"
    
    cache_scenes_dir = render_output_dir / "cache_scenes"
    cache_scenes_dir.mkdir(parents=True, exist_ok=True)
    
    voice_presets = manifest.get("voice_presets", {
        "Narrator": "Rasalgethi",
        "Peacock": "Charon",
        "Kalu": "Puck"
    })
    
    print(f"🎬 Video Engine: Initializing production loop for project master ID: [{manifest['video_id']}]")
    
    # 2. Iterate through manifest scenes
    for scene in manifest["timeline_scenes"]:
        seq = scene["scene_sequence"]
        scene_id = f"scene_{seq:02d}"
        output_mp4 = cache_scenes_dir / f"{scene_id}.mp4"
        if output_mp4.exists() and output_mp4.stat().st_size > 0:
            print(f"\n👉 Reusing cached scene video: {output_mp4.name} (skipping render)")
            continue
            
        print(f"\n🎞️ Rendering Sequence Block {seq} [{scene_id}]...")
        
        scene_scratch = render_output_dir / scene_id
        scene_scratch.mkdir(parents=True, exist_ok=True)
        
        dialogue = scene.get("dialogue", [])
        characters = scene.get("scene_characters", [])
        bg_asset_path = PROJECT_ROOT / scene["background_asset"]
        
        # A. Synthesize vocals
        segment_wavs = []
        segment_durations = []
        for idx, line in enumerate(dialogue):
            speaker = line["speaker"]
            text = line["text"]
            voice = voice_presets.get(speaker, "Rasalgethi")
            
            seg_raw = scene_scratch / f"line_{idx}_raw.wav"
            seg_dsp = scene_scratch / f"line_{idx}_dsp.wav"
            
            print(f"🎙️ Synthesizing line {idx+1}/{len(dialogue)}: [{speaker}] speaks...")
            success = synthesize_vocal_line(text, voice, seg_raw)
            if not success:
                raise RuntimeError(f"❌ Failed to synthesize audio for speaker: {speaker}")
                
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
            
        # Build scene master vocals
        master_vocal = AudioSegment.empty()
        for seg in segment_wavs:
            master_vocal += seg
        scene_master_wav = scene_scratch / "scene_master_vocals.wav"
        master_vocal.export(scene_master_wav, format="wav")
        
        total_duration_ms = len(master_vocal)
        total_duration_sec = total_duration_ms / 1000.0
        total_frames = int(total_duration_sec * fps)
        
        # Dialogue subtitles timelines
        dialogue_timelines = []
        curr_time_ms = 0
        for idx, line in enumerate(dialogue):
            dur_ms = segment_durations[idx]
            start_s = curr_time_ms / 1000.0
            end_s = (curr_time_ms + dur_ms) / 1000.0
            dialogue_timelines.append((start_s, end_s, line["text"]))
            curr_time_ms += dur_ms
            
        # B. Character Rhubarb Lip-Sync
        character_lipsync_maps = {}
        speakers_in_scene = set(line["speaker"] for line in dialogue)
        
        for speaker in speakers_in_scene:
            # Look up speaker folder name dynamically
            speaker_folder = find_matching_character_folder(speaker, characters)
            if not speaker_folder:
                continue
                
            char_vocal = AudioSegment.empty()
            for idx, line in enumerate(dialogue):
                seg_len = segment_durations[idx]
                if line["speaker"] == speaker:
                    char_vocal += segment_wavs[idx]
                else:
                    char_vocal += AudioSegment.silent(duration=seg_len)
                    
            char_wav_path = scene_scratch / f"vocal_{speaker.lower()}.wav"
            char_vocal.export(char_wav_path, format="wav")
            
            sync_txt_path = scene_scratch / f"lipsync_{speaker.lower()}.txt"
            generate_rhubarb_lip_sync(
                audio_input_path=str(char_wav_path),
                output_txt_path=str(sync_txt_path),
                binary_path=str(PROJECT_ROOT / "bin" / "rhubarb")
            )
            character_lipsync_maps[speaker_folder] = parse_rhubarb_timings(str(sync_txt_path))
            print(f"🎬 Rhubarb Sync: Generated timing sheet for [{speaker}] -> folder: [{speaker_folder}]")
            
        # C. Load dynamic character bundles from directories
        active_puppets = []
        for char_spec in characters:
            folder = char_spec["folder_name"]
            bundle = load_dynamic_character_bundle(folder)
            
            active_puppets.append({
                "bundle": bundle,
                "folder": folder,
                "scale_factor": char_spec["scale_factor"],
                "motion_path": char_spec["motion_path"],
                "states": char_spec["states"],
                "placement_mode": char_spec.get("placement_mode", "top_left"),
                "target_screen_height_ratio": char_spec.get("target_screen_height_ratio"),
                "mouth_pos": bundle["mouth_anchor_xy"],
                "pivot": bundle["feather_pivot_xy"]
            })
            
        # Load background
        bg_img = Image.open(bg_asset_path).convert("RGBA").resize(resolution, Image.Resampling.LANCZOS)
        
        # Temp frame workspace
        temp_frames_dir = scene_scratch / "temp_frames"
        if temp_frames_dir.exists():
            shutil.rmtree(temp_frames_dir)
        temp_frames_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"🖼️ Layout Renderer: Rendering {total_frames} frames ({total_duration_sec:.2f}s) @ {fps} FPS...")
        
        # Render frame loop
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            frame_canvas = bg_img.copy()
            
            # Layer character puppets
            for puppet in active_puppets:
                char_key = puppet["bundle"]["character_key"]
                
                # Determine state
                active_state = "idle"
                for state_entry in puppet["states"]:
                    start_tr, end_tr = state_entry["time_range"]
                    if start_tr <= t < end_tr:
                        active_state = state_entry["animation_state"]
                        break
                        
                # Determine mouth shape
                active_shape = "X"
                speaker_id = puppet["folder"]
                if active_state == "talking_lip_sync" and speaker_id in character_lipsync_maps:
                    active_shape = get_mouth_shape_for_timestamp(t, character_lipsync_maps[speaker_id])
                    
                # Package puppet dictionary structure matching frame_renderer requirements
                character_assets = {
                    **puppet["bundle"],
                    "feather_pivot": puppet["pivot"],
                    "placement_mode": puppet["placement_mode"],
                }
                
                # Dynamic rendering compositing sequence
                char_frame = render_dynamic_character_frame(
                    frame_index=frame_idx,
                    fps=fps,
                    character_assets=character_assets,
                    active_mouth_shape=active_shape
                )
                
                # Calculate movement coordinate interpolation and a subtle walk pose
                if puppet["motion_path"].get("enabled", False) and str(puppet.get("placement_mode", "")).lower() in {"ground", "grounded", "bottom", "bottom_center"}:
                    walk_transform = calculate_walk_transform(
                        frame_index=frame_idx,
                        fps=fps,
                        motion_config=puppet["motion_path"],
                    )
                    (curr_x, curr_y) = walk_transform["coords"]
                    curr_scale = walk_transform["scale"]
                    tilt_degrees = walk_transform["tilt"]
                else:
                    (curr_x, curr_y), curr_scale = calculate_frame_transform(
                        frame_index=frame_idx,
                        fps=fps,
                        motion_config=puppet["motion_path"]
                    )
                    tilt_degrees = 0.0
                
                current_w, current_h = _resolve_actor_size(
                    bundle=puppet["bundle"],
                    char_spec={
                        "folder_name": puppet["folder"],
                        "target_screen_height_ratio": puppet.get("target_screen_height_ratio"),
                    },
                    canvas_h=canvas_h,
                    motion_scale=curr_scale,
                )
                
                char_resized = char_frame.resize((current_w, current_h), Image.Resampling.BICUBIC)
                char_resized = _apply_walk_pose(char_resized, tilt_degrees, puppet["placement_mode"])
                
                # Paste
                draw_x, draw_y = _resolve_actor_draw_position(
                    char_spec={"placement_mode": puppet["placement_mode"]},
                    current_coords=(curr_x, curr_y),
                    current_size=(current_w, current_h),
                )
                frame_canvas.paste(char_resized, box=(draw_x, draw_y), mask=char_resized)
                
            # D. Apply Camera zoom/pan effect to full composited frame
            camera_effect = scene.get("camera_effect", "static")
            frame_canvas = apply_camera_effect(frame_canvas, camera_effect, frame_idx / total_frames)

            # E. Focus gently on the active speaker when the scene has dialogue.
            frame_canvas = _apply_speaker_focus_crop(
                frame_canvas=frame_canvas,
                focus_xy=scene.get("camera_focus_target_xy"),
                scene=scene,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                progress=frame_idx / max(1, total_frames),
            )

            # F. Optional foreground depth overlay (fences, branches, porches, etc.)
            foreground_overlay = _load_optional_foreground_overlay(bg_asset_path, manifest, scene, resolution)
            frame_canvas = _apply_foreground_depth_overlay(frame_canvas, foreground_overlay, scene)
            
            # G. Overlay Hindi Subtitles
            active_subtitle = ""
            for s_t, e_t, txt in dialogue_timelines:
                if s_t <= t < e_t:
                    active_subtitle = txt
                    break
            draw_subtitles(frame_canvas, active_subtitle, "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
            
            # Save frame
            frame_path = temp_frames_dir / f"frame_{frame_idx:05d}.png"
            _flatten_frame_for_export(frame_canvas).save(frame_path, "PNG")
            
        # Compile segment clip
        output_mp4 = cache_scenes_dir / f"{scene_id}.mp4"
        print(f"🎥 FFmpeg: Assembling segment video -> [{output_mp4}]")
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-r", str(fps),
            "-i", str(temp_frames_dir / "frame_%05d.png"),
            "-i", str(scene_master_wav),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(output_mp4)
        ]
        try:
            subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
            print(f"✨ Scene compile completed successfully: {output_mp4.name}")
        except subprocess.CalledProcessError as err:
            raise RuntimeError(f"❌ FFmpeg segment compilation failed: {err.stderr}")
        finally:
            if temp_frames_dir.exists():
                shutil.rmtree(temp_frames_dir)
                
    # 3. Stitch and post-process music
    output_final_dir = project_dir / "output"
    output_final_dir.mkdir(exist_ok=True)
    
    temp_stitched = output_final_dir / "stitched_temp.mp4"
    stitch_scene_segments_procedurally(str(cache_scenes_dir), str(temp_stitched))
    
    # BGM Mastering
    print("\n🔊 Audio Post-Processing: Mastering background music with ducking...")
    vocals_dir = project_dir / "vocals"
    vocals_dir.mkdir(parents=True, exist_ok=True)
    temp_vocals_wav = vocals_dir / "combined_master_vocals.wav"
    ffmpeg_extract_cmd = [
        "ffmpeg", "-y", "-i", str(temp_stitched),
        "-vn", "-c:a", "pcm_s16le", str(temp_vocals_wav)
    ]
    try:
        subprocess.run(ffmpeg_extract_cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as err:
        print(f"⚠️ Failed to extract vocals track: {err}")
        temp_vocals_wav = None
        
    video_id = manifest.get("video_id", "ghamandi_mor")
    final_output = output_final_dir / f"{video_id}_final.mp4"
    bg_music_path = PROJECT_ROOT / manifest.get("global_bgm", "assets/character/bg_music.mp3")
    
    if temp_vocals_wav and bg_music_path.exists():
        temp_mixed_audio = vocals_dir / "combined_vocals_music.mp3"
        mix_vocal_and_music_with_ducking(
            vocal_wav_path=str(temp_vocals_wav),
            music_wav_path=str(bg_music_path),
            output_mp3_path=str(temp_mixed_audio),
            duck_gain_db=-18.0,
            idle_gain_db=-6.0
        )
        
        print("🎥 Injecting mastered soundtrack into final Gold Master video...")
        ffmpeg_merge_cmd = [
            "ffmpeg", "-y", "-i", str(temp_stitched), "-i", str(temp_mixed_audio),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(final_output)
        ]
        try:
            subprocess.run(ffmpeg_merge_cmd, capture_output=True, check=True)
            print("✨ Injection successful.")
        except subprocess.CalledProcessError as err:
            print(f"⚠️ Audio injection failed: {err.stderr.decode()}. Copying temp video.")
            shutil.copy(temp_stitched, final_output)
    else:
        print("⚠️ BGM or vocals extraction failed. Copying raw stiched video.")
        shutil.copy(temp_stitched, final_output)
        
    if temp_stitched.exists():
        os.remove(temp_stitched)
        
    print(f"\n🏆 Universal compiler Concluded: Gold Master exported to [{final_output}]")
    
    # 4. Storage cleanup lifecycle
    archive_and_purge_project(project_dir.name, str(project_dir.parent))

if __name__ == "__main__":
    load_dotenv()
    manifest_path = "projects/ghamandi_mor/scene_manifest.json"
    if len(sys.argv) > 1:
        manifest_path = sys.argv[1]
    compile_dynamic_scene_sequence(manifest_path)
