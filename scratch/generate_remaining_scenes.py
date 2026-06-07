import urllib.parse
import requests
import time
import shutil
from pathlib import Path

def main():
    style = (
        "A premium, highly attractive 3D Pixar claymation character illustration, "
        "warm expressive characters, friendly and approachable software developer, "
        "beautifully rounded shapes, smooth modern tech surfaces with tactile glassmorphism textures, "
        "soft pastel purple and cyan highlights, subtle orange/gold glow, warm volumetric studio lighting, "
        "gentle depth of field, subtle glowing particles, high-detail textures, 8k resolution, "
        "cinematic composition, zero text, zero logos, no watermark. "
    )
    
    scenes = {
        32: "A clean, modern 3D atmospheric layout featuring a deep dark-blue gradient background. Centered in the frame is a single, glowing neon-green button shaped like a rocket ship lifting off, surrounded by soft pastel light halos. Perfect, clean negative space.",
        33: "A beautiful, premium 3D studio background layout featuring colorful, floating geometric glassmorphic shapes. Soft, professional studio lights cast elegant shadows across the frame. Two large, perfectly balanced blank spaces designed for embedding video annotations.",
        34: "An attractive, high-end 3D composition featuring floating, glossy social media engagement bubbles (Instagram, LinkedIn, Twitter) hovering gracefully over an abstract dark mesh pattern. Minimalist, and vibrant.",
        35: "A beautiful, highly stylized YouTube outro screen endcard. Vibrantly modeled 3D glossy icons representing a bright red 'SUBSCRIBE' play button, a neon glowing thumbs-up 'LIKE' icon, and a golden ringing 'BELL' notification symbol float side-by-side over a rich, cinematic tech pattern background filled with soft colorful particles."
    }
    
    cache_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/output/video_episodes/fresher_in_ai_world_explainer/clips/auto_2_5d")
    desktop_images_dir = Path("/Users/lalitprasadsingh/Desktop/fresher_ai_world_folder/images")
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    desktop_images_dir.mkdir(parents=True, exist_ok=True)
    
    for num, prompt in scenes.items():
        full_prompt = style + prompt
        encoded = urllib.parse.quote(full_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&private=true"
        
        print(f"Generating Scene {num}...")
        try:
            time.sleep(3)  # Anti-rate-limiting delay
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            
            # Save to cache
            cache_path = cache_dir / f"scene_{num}.png"
            cache_path.write_bytes(r.content)
            
            # Save to desktop
            desktop_path = desktop_images_dir / f"scene_{num}.png"
            shutil.copyfile(cache_path, desktop_path)
            
            print(f"-> Saved Scene {num} (Size: {cache_path.stat().st_size / 1024:.1f} KB)")
        except Exception as e:
            print(f"Failed for Scene {num}: {e}")

if __name__ == "__main__":
    main()
