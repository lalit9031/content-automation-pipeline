import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.video_pipeline.motion_engine import calculate_frame_transform

def main():
    timeline_path = PROJECT_ROOT / "timeline.json"
    print(f"📖 Reading timeline from: {timeline_path}")
    
    with open(timeline_path, "r") as f:
        config = json.load(f)
        
    fps = config.get("fps", 24)
    scenes = config.get("scenes", [])
    
    # Let's test Nandu's motion path in scene_01_intro
    intro_scene = scenes[0]
    nandu_config = next(char for char in intro_scene["characters"] if char["id"] == "nandu")
    motion_config = nandu_config["motion_path"]
    
    print("\n🏃 Motion Interpolation Log: Tracing Nandu in [scene_01_intro] (Frame 0 to 60)")
    print("-" * 75)
    print(f"{'Frame':<8}{'Time (s)':<12}{'Position (X, Y)':<25}{'Scale Factor':<15}")
    print("-" * 75)
    
    for f in range(61):
        pos, scale = calculate_frame_transform(frame_index=f, fps=fps, motion_config=motion_config)
        time_s = f / fps
        print(f"{f:<8}{time_s:<12.3f}{str(pos):<25}{scale:<15.3f}")
        
    print("-" * 75)
    print("✅ Motion verification test complete!")

if __name__ == "__main__":
    main()
