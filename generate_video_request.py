import sys
from pathlib import Path

# Add src folder to PYTHONPATH programmatically
src_dir = Path(__file__).resolve().parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from content_pipeline.config import Settings
from content_pipeline.bots.motion import ComfyUIMotionProvider, MotionClip, MotionPlan


def main():
    settings = Settings.from_environment()
    
    # Paths
    base_dir = Path(r"C:\Users\user\Desktop\Output file")
    img_file = base_dir / "image" / "girl_in_rain_aligned.png"
    vid_dir = base_dir / "video"
    
    vid_dir.mkdir(parents=True, exist_ok=True)
    
    if not img_file.exists():
        print(f"ERROR: Reference image not found at {img_file.resolve()}")
        print("Please run image generation first.")
        return

    print(f"Found reference image: {img_file.resolve()}")
    print(f"ComfyUI URL: {settings.comfyui_url}")
    print(f"Video workflow template: {settings.comfyui_video_workflow}")
    
    # Initialize Multi-Agent Video Orchestrator
    from content_pipeline.bots.video_agent_orchestrator import VideoAgentOrchestrator
    orchestrator = VideoAgentOrchestrator(settings)
    
    clip = MotionClip(
        id="girl_walking_to_river",
        title="Girl walking to river bank",
        duration_seconds=5,
        prompt=(
            "Pixar 3D animated style video of a cute girl with a colorful umbrella "
            "walking slowly towards the river bank in the rain, highly detailed, "
            "realistic footsteps, ripples in the water, highly detailed eyes and face"
        ),
        output_file="girl_walking_to_river.mp4",
        reference_image_file=str(img_file)
    )
    
    plan = MotionPlan(
        project_id="user_video_request",
        title="Girl in rain motion",
        provider="comfyui",
        model="ltxv-13b-0.9.8-dev-fp8.safetensors",
        size="768x512",
        clips=[clip],
        provider_rules=[]
    )
    
    output_path = vid_dir / "girl_walking_to_river.mp4"
    
    print("\nTriggering Multi-Agent Video Audit-Correction Loop...")
    print("Uploading reference image and running LTXV 13B pipeline on your local GPU...")
    
    try:
        result = orchestrator.run_video_generation_loop(clip, plan, output_path, max_attempts=3)
        print("\n" + "="*50)
        print(f"PIPELINE STATUS: {result['status']}")
        print(f"Attempts needed: {result['attempts_needed']}")
        print(f"Motion Bucket used: {result['motion_bucket']}")
        print(f"CFG scale used: {result['cfg']:.1f}")
        print("Video successfully generated and saved to:")
        print(f"  {output_path.resolve()}")
        print("="*50)
    except Exception as exc:
        print("\n" + "="*50)
        print(f"ERROR: Multi-Agent Video loop failed!")
        print(f"Details: {exc}")
        print("="*50)
        print("Please verify that:")
        print("1. Your ComfyUI server is running locally at http://127.0.0.1:8188")
        print("2. You have loaded the Stable Video Diffusion model (e.g. 'svd_xt_1_1.safetensors')")
        print(f"3. Your video workflow exists at {settings.comfyui_video_workflow}")


if __name__ == "__main__":
    main()
