import sys
import os
import json
import shutil
import subprocess
from pathlib import Path

# Add src directory to sys path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.image import image_provider, ImageVariant, MockImageProvider
import re
from content_pipeline.bots.audio import generate_indian_voiceover

from PIL import Image, ImageDraw, ImageFont
import urllib.parse
import requests
import time
from io import BytesIO

def _audio_duration(path: Path) -> float:
    executable = shutil.which("ffprobe")
    if not executable:
        return 0
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return 0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0

def overlay_lower_third_text(image_path: Path, output_path: Path, text: str):
    """
    Overlays a professional, semi-transparent lower-third text banner onto the image.
    Uses Pillow to ensure compatibility without depending on FFmpeg's drawtext filter.
    """
    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    try:
        font = ImageFont.truetype("Arial.ttf", 36)
    except IOError:
        font = ImageFont.load_default()
        
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    pad_x = 24
    pad_y = 14
    
    banner_w = text_w + (pad_x * 2)
    banner_h = text_h + (pad_y * 2)
    
    banner_x1 = (w - banner_w) // 2
    banner_y1 = h - 100 - (banner_h // 2)
    banner_x2 = banner_x1 + banner_w
    banner_y2 = banner_y1 + banner_h
    
    draw.rounded_rectangle(
        [banner_x1, banner_y1, banner_x2, banner_y2],
        radius=12,
        fill=(17, 24, 39, 180),  # Sleek dark gray #111827 with alpha 180 (70% opacity)
        outline=(56, 189, 248, 150),  # Cyan outline #38bdf8 with alpha 150
        width=2
    )
    
    text_x = banner_x1 + pad_x
    text_y = banner_y1 + pad_y - bbox[1]
    
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))
    
    final_img = img.convert("RGB")
    final_img.save(output_path, "PNG")


def generate_premium_fallback_background(output_path: Path):
    """
    Generates a sleek, high-fidelity dark-blue-to-charcoal gradient background
    with cybernetic glowing grids using Pillow. Used as a fail-safe fallback.
    """
    img = Image.new("RGBA", (1280, 720))
    draw = ImageDraw.Draw(img)
    
    # Sleek linear gradient: dark blue/indigo #030712 to charcoal #081125
    for y in range(720):
        r = int(3 + (y / 720) * 5)
        g = int(7 + (y / 720) * 10)
        b = int(18 + (y / 720) * 20)
        draw.line([(0, y), (1280, y)], fill=(r, g, b, 255))
        
    # Draw subtle cybernetic grids (opacity 0.05)
    grid_color = (56, 189, 248, 12)  # Cyan #38bdf8 with very low alpha
    for x in range(0, 1280, 64):
        draw.line([(x, 0), (x, 720)], fill=grid_color, width=1)
    for y in range(0, 720, 64):
        draw.line([(0, y), (1280, y)], fill=grid_color, width=1)
        
    # Draw an abstract glowing decorative arc or circle in background
    draw.ellipse([800, -100, 1400, 500], fill=(56, 189, 248, 8), outline=(56, 189, 248, 16), width=2)
    draw.ellipse([950, 50, 1250, 350], fill=(56, 189, 248, 12), outline=(56, 189, 248, 24), width=3)
    
    final_img = img.convert("RGB")
    final_img.save(output_path, "PNG")
    print(f"-> Sleek cybernetic fallback background generated at {output_path}")

def fetch_ai_image_with_retry(prompt: str, variant: ImageVariant, output_path: Path):
    """
    Fetches image from Pollinations.ai with exponential backoff retries,
    verifying it's a valid openable image. Enforces premium 3D volumetric character
    visual consistency by stripping conflicting cartoon elements and appending our
    high-fidelity visual style parameters.
    """
    # Clean up conflicting child-cartoonish terms that degrade SD quality
    cleaned_prompt = prompt.replace("3D Pixar style", "").replace("3D Pixar-style", "")
    cleaned_prompt = cleaned_prompt.replace("claymation style", "").replace("clay textures", "")
    cleaned_prompt = cleaned_prompt.replace("claymation textures", "").replace("3D cartoon style", "")
    cleaned_prompt = cleaned_prompt.replace("child-friendly", "").replace("toy-like", "")
    
    # Premium visual style string inspired by our first 5 premium renders
    master_style = (
        ", premium 3D character illustration, warm expressive characters, friendly and approachable, "
        "beautifully rounded shapes, smooth modern tech surfaces with tactile glassmorphism textures, "
        "pastel purple and cyan highlights, subtle orange and gold glow, soft volumetric studio lighting, "
        "gentle depth of field, subtle glowing particles, high-detail textures, 8k resolution, "
        "cinematic composition, zero text, zero logos, no watermark."
    )
    
    full_prompt = cleaned_prompt.strip() + master_style
    encoded_prompt = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={variant.width}&height={variant.height}&nologo=true&private=true"
    
    max_retries = 4
    delay = 6
    
    for attempt in range(1, max_retries + 1):
        print(f"   (Attempt {attempt}/{max_retries}) Querying Pollinations.ai...")
        try:
            # 60s timeout for safety
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # Verify the image bytes can be opened by Pillow
            img = Image.open(BytesIO(response.content))
            img.verify()  # Verify image integrity
            
            # Save the valid image
            output_path.write_bytes(response.content)
            print(f"   -> Successfully fetched and verified AI image!")
            return
        except Exception as e:
            print(f"   -> Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                print(f"   -> Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
                
    # If we exhausted all retries, generate the premium fallback background!
    print("   -> WARNING: All Pollinations.ai retries failed. Using premium fallback background.")
    generate_premium_fallback_background(output_path)


def get_scene_concepts(index: int) -> list[str]:
    concepts_map = {
        1: ["Mindset Shift", "AI Enablement", "Survival Guide"],
        2: ["Boilerplate Stress", "Manual Debugging", "Legacy Stack"],
        3: ["Core Logic Shift", "Visual Pipelines", "Modular Stacking"],
        4: ["AI Copilot", "Admin Efficiency", "High Fidelity Partner"],
        5: ["Skill Summit", "Tech Stack Mastery", "Career Growth"],
        6: ["Solution Architect", "System Design", "Flow Mastery"],
        7: ["Syntax Commodity", "Value Creation", "Strategic Logic"],
        8: ["Tech Fundamentals", "Error Spotting", "Database Core"],
        9: ["Hallucination Shield", "Code Security", "API Resilience"],
        10: ["Human Creativity", "API Integration", "Superpower Stitching"],
        11: ["Prompt Engineering", "Exact Context", "Constraint Mastery"],
        12: ["Data Privacy", "IP Protection", "Security Priority"],
        13: ["Code Review", "Strict Audit", "Understanding First"],
        14: ["Backlog Cleansing", "Clear Acceptance", "Sprint Efficiency"],
        15: ["AI Debugging", "Bug Isolation", "Rapid Resolution"],
        16: ["Continuous Learning", "Rapid Upskilling", "Micro Learning"],
        17: ["Automated Testing", "Test Orchestration", "Quality Assurance"],
        18: ["Tech Documentation", "AI Generation", "Accurate Context"],
        19: ["UI/UX Design", "Component Library", "Fast Prototyping"],
        20: ["Clean Code", "Refactoring AI", "Maintainability"],
        21: ["Performance Tuning", "Resource Check", "Latency Control"],
        22: ["Version Control", "PR Explanations", "Clean Merges"],
        23: ["CI/CD Pipelines", "Automated Deploy", "Seamless Delivery"],
        24: ["Tech Networking", "LinkedIn Outreach", "Community Building"],
        25: ["Mock Interviews", "AI Preparation", "Confidence Boost"],
        26: ["Portfolio Building", "Showcase Projects", "Real-world Proof"],
        27: ["Problem Solving", "Root Cause Analysis", "Logical Thinking"],
        28: ["Collaboration", "Dev-to-PM Flow", "Team Synergy"],
        29: ["Product Sense", "User Centric", "Business Value"],
        30: ["Agile Adaptability", "Scrum Master", "Continuous Pivot"],
        31: ["AI Tooling", "Copilot & ChatGPT", "IDE Integration"],
        32: ["Domain Expertise", "Industry Focus", "Specialization"],
        33: ["Mentorship", "Knowledge Sharing", "Guidance"],
        34: ["Resilience", "Career Longevity", "Adapting Fast"],
        35: ["Survival Complete", "Future Ready", "Unstoppable Developer"],
    }
    return concepts_map.get(index, ["Survival Guide", "AI Skills", "Tech Stack"])

def split_narration_into_lines(narration: str, max_chars: int = 40) -> tuple[str, str]:
    words = narration.split()
    line1 = []
    line2 = []
    curr_len = 0
    
    # Split narration cleanly across two lines up to max_chars each
    for word in words:
        if curr_len + len(word) + 1 <= max_chars:
            line1.append(word)
            curr_len += len(word) + 1
        elif len(line2) == 0 or len(" ".join(line2)) + len(word) + 1 <= max_chars:
            line2.append(word)
        else:
            break
            
    l1 = " ".join(line1)
    l2 = " ".join(line2)
    if len(words) > len(line1) + len(line2):
        l2 = l2.rstrip(".,;:!?-") + "..."
    return l1, l2

def _ensure_png_bytes(image_bytes: bytes, png_path: Path) -> Path:
    import cairosvg
    stripped = image_bytes.lstrip()
    if stripped.startswith(b"<") and (b"<svg" in stripped[:200] or b"<?xml" in stripped[:200]):
        cairosvg.svg2png(bytestring=image_bytes, write_to=str(png_path))
    else:
        png_path.write_bytes(image_bytes)
    return png_path


def main():
    print("Initializing 5-minute premium explainer video generation...")
    os.environ["IMAGE_PROVIDER"] = "free-ai"
    settings = Settings.from_environment(PROJECT_ROOT)

    desktop_dir = Path("/Users/lalitprasadsingh/Desktop/fresher_ai_world_folder")
    desktop_dir.mkdir(parents=True, exist_ok=True)
    images_dest_dir = desktop_dir / "images"
    images_dest_dir.mkdir(parents=True, exist_ok=True)
    audio_dest_dir = desktop_dir / "audio"
    audio_dest_dir.mkdir(parents=True, exist_ok=True)
    clips_dest_dir = desktop_dir / "rendered_clips"
    clips_dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"Desktop deliverables folder created at: {desktop_dir}")

    # Load 35 high-quality, comprehensive scenes dynamically from JSON data file
    json_path = PROJECT_ROOT / "scratch" / "fresher_scenes_data.json"
    with open(json_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)

    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required. Install it once with: brew install ffmpeg")

    # Image Provider
    provider = MockImageProvider()
    variant = ImageVariant("16:9", 1280, 720, "unused")

    # 1. Generate / Copy Images and Narration Audio
    list_of_compiled_files = []
    
    for index, data in enumerate(scenes_data, start=1):
        scene_id = data["id"]
        title = data["title"]
        narration = data["narration"]
        on_screen = data["on_screen_text"]
        prompt = data["prompt"]

        print(f"\n[Scene {index}/35] - {title}")

        # Still PNG Image
        still_filename = f"scene_{index:02d}.png"
        still_path = images_dest_dir / still_filename

        # For scenes 1 to 5, restore the premium cached illustrations the user loved!
        local_src_path = settings.output_dir / "video_episodes" / "fresher_in_ai_world_explainer" / "clips" / "auto_2_5d" / f"scene_{index:02d}.png"
        if index <= 5 and local_src_path.exists():
            shutil.copyfile(local_src_path, still_path)
            print(f"-> Preserved premium 3D character illustration copied for Scene {index} (Size: {still_path.stat().st_size / 1024:.1f} KB)")
        else:
            # Generate the high-quality SVG slide using MockImageProvider
            print(f"-> Rendering premium infographic slide via MockImageProvider...")
            scene_concepts = get_scene_concepts(index)
            concepts_str = ", ".join(scene_concepts)
            
            # Split narration into readable lines for the center description box
            l1, l2 = split_narration_into_lines(narration, max_chars=40)
            
            # Build structured mock prompt that MockImageProvider parses
            mock_prompt = (
                f"Renderer-only headline: \"{title}\"\n"
                f"Renderer-only hook: \"{on_screen}\"\n"
                f"Renderer-only desc title: \"Scene {index} Insight\"\n"
                f"Renderer-only desc line1: \"{l1}\"\n"
                f"Renderer-only desc line2: \"{l2}\"\n"
                f"Renderer-only concepts: \"{concepts_str}\"\n"
                f"Topic: {title}\n"
                f"Prompt: {prompt}"
            )
            
            # Create the SVG bytes
            image_bytes = provider.create(mock_prompt, variant)
            # Convert SVG to lossless PNG via CairoSVG
            _ensure_png_bytes(image_bytes, still_path)
            print(f"-> Slide image generated and saved to {still_path} (Size: {still_path.stat().st_size / 1024:.1f} KB)")

        # Narration Audio (Indian Teacher Voice: en-IN-PrabhatNeural)
        audio_filename = f"scene_{index:02d}.mp3"
        audio_path = audio_dest_dir / audio_filename
        print("-> Rendering Edge TTS audio...")
        generate_indian_voiceover(narration, audio_path, voice="en-IN-PrabhatNeural")
        
        # Sync Duration
        duration = _audio_duration(audio_path)
        if duration <= 0:
            # Fallback based on word count if duration check failed
            duration = max(6, int(len(narration.split()) / 2.35) + 1)
        print(f"-> Audio duration: {duration:.2f} seconds")

        # Compile Silent Video Clip with beautiful Lower-Third overlay via Pillow
        silent_clip_path = clips_dest_dir / f"scene_{index:02d}_silent.mp4"
        frames = int(duration * 25)
        
        # Overlay the on_screen_text onto a captioned copy of the still image
        captioned_still_path = clips_dest_dir / f"scene_{index:02d}_captioned.png"
        clean_text = on_screen.strip()
        if clean_text:
            print(f"-> Drawing text overlay: '{clean_text}'")
            overlay_lower_third_text(still_path, captioned_still_path, clean_text)
        else:
            shutil.copyfile(still_path, captioned_still_path)

        subprocess.run(
            [
                executable,
                "-y",
                "-loop",
                "1",
                "-i",
                str(captioned_still_path),
                "-vf",
                (
                    f"scale=1280:720:force_original_aspect_ratio=decrease,"
                    f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                    f"format=yuv420p"
                ),
                "-frames:v",
                str(frames),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(silent_clip_path),
            ],
            check=True,
            capture_output=True
        )

        # Mix Audio & Video into a single synchronized clip
        final_clip_path = clips_dest_dir / f"scene_{index:02d}.mp4"
        subprocess.run(
            [
                executable,
                "-y",
                "-i",
                str(silent_clip_path),
                "-i",
                str(audio_path),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(final_clip_path)
            ],
            check=True,
            capture_output=True
        )

        list_of_compiled_files.append(final_clip_path)
        print(f"-> Fully synchronized clip built: {final_clip_path}")

    # 2. Concatenate all 35 clips into a final 5-minute video!
    concat_txt_path = desktop_dir / "clips_list.txt"
    concat_txt_path.write_text(
        "\n".join(f"file '{path}'" for path in list_of_compiled_files) + "\n",
        encoding="utf-8"
    )

    final_video_dest = desktop_dir / "fresher_survive_ai_world.mp4"
    print("\nConcatenating all clips into final video...")
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(final_video_dest)
        ],
        check=True,
        capture_output=True
    )

    print(f"\nSUCCESS! Complete 5-minute explainer video built completely for free!")
    print(f"Final MP4 Video: {final_video_dest}")
    print(f"Subtitles and materials saved in Desktop Folder: {desktop_dir}")

if __name__ == "__main__":
    main()
