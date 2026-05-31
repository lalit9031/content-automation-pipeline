import sys
import os
import json
from pathlib import Path

# Insert src directory to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from content_pipeline.config import Settings
from content_pipeline.models import VideoEpisode, VideoClip
from content_pipeline.bots.image import image_provider
from content_pipeline.bots.video_engine import create_episode_workspace, generate_auto_2_5d_clips, assemble_episode

def main():
    print("Initializing settings...")
    # Load settings from environment, force image_provider to free-ai
    os.environ["IMAGE_PROVIDER"] = "free-ai"
    settings = Settings.from_environment(PROJECT_ROOT)
    
    # Clear previous cached workspace to force re-generation of AI images
    workspace_dir = settings.output_dir / "video_episodes" / "fresher_in_ai_world_explainer"
    # if workspace_dir.exists():
    #     import shutil
    #     shutil.rmtree(workspace_dir)
    #     print("Cleared previous workspace cache.")
    
    # 5 Key Scenes representing the story arc
    scenes_data = [
        {
            "id": "scene_01",
            "title": "Introduction to AI World",
            "duration_seconds": 6,
            "narration": "Welcome to the AI world! A fresh, vibrant space full of glowing modular elements and endless possibilities.",
            "on_screen_text": "Fresher in the AI World",
            "visual_mode": "2_5d_image",
            "prompt": (
                "A vibrant, cinematic 3D character illustration of a young male software developer (fresher) "
                "sitting at a sleek, minimalist desk in a futuristic workspace. He is looking with a warm, inspired "
                "smile at a floating, semi-transparent holographic UI dashboard in front of him displaying glowing "
                "colorful charts, 3D flowchart nodes, and clean tech blocks in pastel purple and cyan highlights. "
                "A friendly little robotic AI assistant with glowing yellow eyes floats beside the desk, holding a "
                "glowing digital checkmark. Clean modern tech surfaces, premium 3D render style, rounded shapes, "
                "high-detail textures, and zero text or watermarks, optimized for professional tech audiences."
            ),
            "source_type": "auto_2_5d",
            "expected_file": "scene_01.mp4"
        },
        {
            "id": "scene_02",
            "title": "Traditional Setup",
            "duration_seconds": 6,
            "narration": "Previously, starting out in tech meant staring at cluttered grey codebases and messy terminal windows.",
            "on_screen_text": "The Old Workspace",
            "visual_mode": "2_5d_image",
            "prompt": (
                "A cinematic 3D character illustration of a frustrated young male software developer sitting "
                "at a dark, cluttered wooden desk. The workspace is filled with old glowing CRT monitor screens "
                "displaying messy terminal windows and complex code lines, stacks of thick manuals, and an "
                "intricate maze of cables. Warm amber lighting, soft volumetric shadows, high-contrast, "
                "professional learning-video style, premium 3D rounded shapes, zero text or watermarks."
            ),
            "source_type": "auto_2_5d",
            "expected_file": "scene_02.mp4"
        },
        {
            "id": "scene_03",
            "title": "Core Idea",
            "duration_seconds": 6,
            "narration": "But AI fundamentally changes the core idea: turning abstract logic into beautiful visual, modular, and interactive building blocks.",
            "on_screen_text": "The Core Shift",
            "visual_mode": "2_5d_image",
            "prompt": (
                "A premium 3D process workflow scene, cinematic illustration. Luminous semi-transparent glassmorphic "
                "flowchart blocks in pastel purple and cyan highlights stack together dynamically to form a beautiful "
                "pipeline on a sleek minimalist table. A friendly robotic AI companion with glowing yellow eyes "
                "points at the flow with a cyan laser pointer. Soft volumetric studio lighting, gentle depth of field, "
                "subtle glowing particles, zero text or watermarks."
            ),
            "source_type": "auto_2_5d",
            "expected_file": "scene_03.mp4"
        },
        {
            "id": "scene_04",
            "title": "AI Enters",
            "duration_seconds": 6,
            "narration": "Now, a friendly AI assistant is always by your side, lighting up your workspace and simplifying complex structures.",
            "on_screen_text": "Your AI Companion",
            "visual_mode": "2_5d_image",
            "prompt": (
                "A vibrant cinematic 3D illustration. A friendly floating robotic AI assistant companion with glowing "
                "yellow eyes points a cyan laser scanner at a large, semi-transparent holographic glass checklist "
                "showing bright green checkmarks. A software developer sits at a sleek minimalist glass desk, looking up "
                "at the companion with a warm, inspired smile. Soft volumetric studio lighting, gentle depth of field, "
                "pastel purple highlights, zero text or watermarks."
            ),
            "source_type": "auto_2_5d",
            "expected_file": "scene_04.mp4"
        },
        {
            "id": "scene_05",
            "title": "Success Moment",
            "duration_seconds": 6,
            "narration": "With your AI assistant, you reach new heights, mastering the tech and confidently stepping into the future.",
            "on_screen_text": "Mastering the AI World",
            "visual_mode": "2_5d_image",
            "prompt": (
                "A premium, cinematic 3D character illustration. A software developer and his friendly floating "
                "robotic AI companion stand proudly on a summit looking at a large, glowing golden trophy cup and "
                "a shiny star. Floating modular glass cards with upward-trending growth arrows surround them in a "
                "futuristic sky. Pastel purple and cyan highlights, warm volumetric dusk lighting, gentle depth "
                "of field, zero text or watermarks."
            ),
            "source_type": "auto_2_5d",
            "expected_file": "scene_05.mp4"
        }
    ]

    episode = VideoEpisode(
        episode_id="fresher_in_ai_world_explainer",
        title="Fresher in the AI World",
        description="A premium 3D automated explainer video generated completely using free AI tools.",
        aspect="landscape",
        width=1280,
        height=720,
        clips=[VideoClip.from_dict(c) for c in scenes_data],
        youtube_title="Fresher in the AI World",
        youtube_description="A 3D explainer generated using Pollinations.ai and local FFmpeg automation.",
        hashtags=["#AIWorld", "#Fresher", "#ArtificialIntelligence"]
    )

    print("Creating episode workspace...")
    create_episode_workspace(settings.output_dir, episode)
    
    print("Generating AI scene images using Pollinations (free-ai)...")
    provider = image_provider(settings)
    auto_clips = generate_auto_2_5d_clips(episode, provider, settings.output_dir)
    print(f"Generated {len(auto_clips)} 2.5D Ken Burns clips.")

    print("Assembling final video...")
    workspace_dir = settings.output_dir / "video_episodes" / episode.episode_id
    final_video_path = assemble_episode(workspace_dir)
    print(f"\nSUCCESS! Video generated completely for free!")
    print(f"Final MP4 Video: {final_video_path}")
    print(f"Subtitles (SRT): {workspace_dir / 'video' / 'subtitles.srt'}")

if __name__ == "__main__":
    main()
