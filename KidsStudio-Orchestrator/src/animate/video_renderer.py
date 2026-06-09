import os
import shutil
import subprocess
from pathlib import Path
from pydub import AudioSegment
from PIL import Image

def parse_rhubarb_timings(timing_txt_path: str) -> list[tuple[float, str]]:
    """
    Parses Rhubarb's TSV mapping file into a list of (start_time, mouth_shape) tuples.
    """
    timings = []
    if not os.path.exists(timing_txt_path):
        raise FileNotFoundError(f"Rhubarb timings file not found: {timing_txt_path}")
        
    with open(timing_txt_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or "\t" not in line:
                continue
            time_str, shape = line.split("\t", 1)
            timings.append((float(time_str), shape.strip()))
            
    # Sort timings just in case
    timings.sort(key=lambda x: x[0])
    return timings

def get_mouth_shape_for_timestamp(t: float, timings: list[tuple[float, str]]) -> str:
    """
    Resolves the active mouth shape for a given timestamp based on the parsed intervals.
    """
    if not timings:
        return "X"
        
    # If the requested time is before the first timestamp, default to rest/closed
    if t < timings[0][0]:
        return "X"
        
    # Find the active interval
    for i in range(len(timings) - 1):
        if timings[i][0] <= t < timings[i+1][0]:
            return timings[i][1]
            
    # If it is past the last timestamp, use the last mouth shape
    return timings[-1][1]

def render_talking_avatar_video(
    body_png_path: str,
    mouths_dir_path: str,
    mouth_pos_xy: tuple[int, int],
    timing_txt_path: str,
    audio_wav_path: str,
    output_mp4_path: str,
    fps: int = 24
) -> str:
    """
    Composites the active mouth shape on top of the character body frame-by-frame
    based on audio timestamps, then compiles it into an MP4 video with sound.
    """
    if not os.path.exists(body_png_path):
        raise FileNotFoundError(f"Character body asset not found: {body_png_path}")
    if not os.path.exists(mouths_dir_path):
        raise FileNotFoundError(f"Mouth assets folder not found: {mouths_dir_path}")
    if not os.path.exists(audio_wav_path):
        raise FileNotFoundError(f"Voice track file not found: {audio_wav_path}")
        
    print(f"🎬 Animation Renderer: Generating frames at {fps} FPS using Pillow & FFmpeg...")
    
    # 1. Load audio details to calculate duration
    sound = AudioSegment.from_file(audio_wav_path)
    duration_sec = len(sound) / 1000.0
    print(f"   Audio Duration: {duration_sec:.2f} seconds")
    
    # 2. Parse lip sync intervals
    timings = parse_rhubarb_timings(timing_txt_path)
    
    # 3. Setup temporary frame directory
    project_root = Path(body_png_path).resolve().parents[2]
    temp_frames_dir = project_root / "scratch" / "temp_frames"
    if temp_frames_dir.exists():
        shutil.rmtree(temp_frames_dir)
    temp_frames_dir.mkdir(parents=True, exist_ok=True)
    
    # Load character body image
    body_img = Image.open(body_png_path).convert("RGBA")
    
    # Cache open mouth images to avoid repeatedly reading disk
    mouth_cache = {}
    
    total_frames = int(duration_sec * fps)
    print(f"   Rendering {total_frames} frames to temporary workspace...")
    
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        active_shape = get_mouth_shape_for_timestamp(t, timings)
        
        # Load active mouth shape image from cache or file
        if active_shape not in mouth_cache:
            mouth_file = Path(mouths_dir_path) / f"{active_shape}.png"
            if not mouth_file.exists():
                # Fallback to rest closed shape if a shape is missing
                mouth_file = Path(mouths_dir_path) / "X.png"
            
            # Load and keep in cache
            mouth_cache[active_shape] = Image.open(mouth_file).convert("RGBA")
            
        active_mouth_img = mouth_cache[active_shape]
        
        # Composite mouth on top of body (using mouth alpha channel as mask)
        frame_canvas = body_img.copy()
        frame_canvas.paste(active_mouth_img, box=mouth_pos_xy, mask=active_mouth_img)
        
        # Save temp frame file
        frame_file_path = temp_frames_dir / f"frame_{frame_idx:05d}.png"
        frame_canvas.save(frame_file_path, "PNG")
        
    # 4. Invoke FFmpeg subprocess to stitch the frames and add the audio track
    print(f"🎥 FFmpeg Core: Compiling MP4 video container -> [{output_mp4_path}]...")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-r", str(fps),
        "-i", str(temp_frames_dir / "frame_%05d.png"),
        "-i", audio_wav_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        output_mp4_path
    ]
    
    try:
        # Run FFmpeg process
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        print(f"🏆 Video Success: Rendered H.264 MP4 talking avatar to [{output_mp4_path}]")
        
    except subprocess.CalledProcessError as err:
        error_msg = err.stderr if err.stderr else err.stdout
        raise RuntimeError(f"❌ FFmpeg stitching failed: {error_msg}")
        
    finally:
        # 5. Cleanup temporary frames
        print("🧹 Cleaning up temporary rendering workspace...")
        if temp_frames_dir.exists():
            shutil.rmtree(temp_frames_dir)
            
    return output_mp4_path
