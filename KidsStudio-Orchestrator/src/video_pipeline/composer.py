import os
import subprocess
from pathlib import Path

def stitch_scene_segments_procedurally(segment_directory: str, final_output_path: str) -> str:
    """
    Finds all compiled scene mp4 segments, creates a sequence manifest,
    and uses FFmpeg to merge them without consuming system RAM.
    """
    print("🎬 Video Engine: Collecting compiled animation scene segments...")
    segment_dir = Path(segment_directory)
    
    # Gather and sort segments by name (e.g. scene_01_intro.mp4, scene_02_dialogue.mp4)
    segments = sorted([f.name for f in segment_dir.glob("*.mp4") if f.name != "final_output.mp4" and f.name != Path(final_output_path).name])
    
    if not segments:
        raise ValueError(f"❌ No compiled scene segments found in: {segment_directory}")
        
    print(f"   Found {len(segments)} segments: {', '.join(segments)}")
    
    # Generate the sequential concatenation map text file for FFmpeg
    list_file_path = segment_dir / "concat_list.txt"
    with open(list_file_path, "w") as f:
        for segment in segments:
            # We escape single quotes for FFmpeg file paths
            escaped_segment = segment.replace("'", "'\\''")
            f.write(f"file '{escaped_segment}'\n")
            
    print(f"⚡ Video Engine: Merging scenes seamlessly using concat demuxer...")
    
    # Output file path path parent directory check
    Path(final_output_path).parent.mkdir(parents=True, exist_ok=True)
    
    ffmpeg_command = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file_path), "-c", "copy", final_output_path
    ]
    
    try:
        result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=True)
        print(f"🏆 Production Complete: Gold Master exported to [{final_output_path}]")
    except subprocess.CalledProcessError as err:
        error_msg = err.stderr if err.stderr else err.stdout
        print(f"❌ FFmpeg stitching failed: {error_msg}")
        raise RuntimeError(f"FFmpeg stitching failed: {error_msg}")
    finally:
        # Cleanup the temporary manifest file
        if list_file_path.exists():
            os.remove(list_file_path)
            
    return final_output_path
