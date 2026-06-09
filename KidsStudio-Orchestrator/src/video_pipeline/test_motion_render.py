import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generate_timeline_story import prepare_layered_assets
from src.video_pipeline.frame_renderer import render_dynamic_character_frame

def run_character_layer_verification():
    """
    Renders 48 frames (2 seconds @ 24 fps) of character rendering.
    Validates:
    1. Feather fan/wing layer rotation (sine-wave sway).
    2. Swapping mouth shapes (A, B, C, D, X).
    """
    assets_dir = PROJECT_ROOT / "assets" / "character"
    output_dir = PROJECT_ROOT / "scratch" / "test_frames"
    
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("🎬 Layer verification: Preparing sliced layers on startup...")
    layered_assets = prepare_layered_assets(assets_dir)
    
    fps = 24
    total_frames = 48
    
    # Test mouth cycle shapes to cycle over the 48 frames
    mouth_cycle = ["X", "A", "B", "C", "D", "E", "F", "X", "X"]
    
    print(f"🖼️ Rendering {total_frames} frames to [{output_dir}]...")
    
    # Simple background canvas (1280x720)
    bg = Image.new("RGBA", (1280, 720), (135, 206, 235, 255))
    draw_bg = ImageDraw.Draw(bg)
    draw_bg.rectangle([(0, 480), (1280, 720)], fill=(34, 139, 34, 255)) # Green ground
    
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        canvas = bg.copy()
        
        # Determine current test mouth shape
        mouth_shape = mouth_cycle[(frame_idx // 6) % len(mouth_cycle)]
        
        # 1. Render Peacock (Original size 811x876, scaled to width 350)
        peacock_puppet = layered_assets["peacock"]
        peacock_frame = render_dynamic_character_frame(
            frame_index=frame_idx,
            fps=fps,
            character_assets=peacock_puppet,
            active_mouth_shape=mouth_shape
        )
        p_w, p_h = peacock_frame.size
        target_pw = 350
        target_ph = int(p_h * (target_pw / p_w))
        peacock_resized = peacock_frame.resize((target_pw, target_ph), Image.Resampling.LANCZOS)
        
        # Paste Peacock at (200, 200)
        canvas.paste(peacock_resized, box=(200, 200), mask=peacock_resized)
        
        # 2. Render Crow Kalu (Original size 746x694, scaled to width 250)
        kalu_puppet = layered_assets["kalu"]
        kalu_frame = render_dynamic_character_frame(
            frame_index=frame_idx,
            fps=fps,
            character_assets=kalu_puppet,
            active_mouth_shape=mouth_shape
        )
        k_w, k_h = kalu_frame.size
        target_kw = 250
        target_kh = int(k_h * (target_kw / k_w))
        kalu_resized = kalu_frame.resize((target_kw, target_kh), Image.Resampling.LANCZOS)
        
        # Paste Kalu at (750, 300)
        canvas.paste(kalu_resized, box=(750, 300), mask=kalu_resized)
        
        # Overlay telemetry print details on canvas
        draw_tel = ImageDraw.Draw(canvas)
        draw_tel.text(
            (50, 50), 
            f"Frame: {frame_idx:02d} / 47 | t: {t:.2f}s | Active Mouth: {mouth_shape}", 
            fill=(255, 255, 255, 255)
        )
        
        # Save output
        frame_path = output_dir / f"frame_{frame_idx:03d}.png"
        canvas.save(frame_path, "PNG")
        
    print(f"🏆 Verification complete! 48 frames successfully generated in: {output_dir}")

if __name__ == "__main__":
    run_character_layer_verification()
