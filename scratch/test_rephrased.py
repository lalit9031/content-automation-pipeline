import urllib.parse
import requests
import time
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
    
    prompts = {
        34: "An elegant 3D scene, modern minimalist background. Beautiful glossy floating bubbles representing Instagram, LinkedIn, and Twitter hover gracefully in a neat composition over a dark abstract mesh background.",
        35: "A premium 3D outro endcard, beautiful tech pattern background. Colorful shiny 3D models representing a red Subscribe button, a blue thumbs-up Like icon, and a golden notification Bell float gracefully in a stylish row. Studio lighting, soft glowing particles, cinematic composition, zero text."
    }
    
    for num, prompt in prompts.items():
        full_prompt = style + prompt
        encoded = urllib.parse.quote(full_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&private=true"
        
        print(f"Generating Scene {num} with rephrased prompt...")
        try:
            time.sleep(4)
            r = requests.get(url, timeout=60)
            print(f"Status: {r.status_code}")
            r.raise_for_status()
            out_path = Path(f"/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/test_{num}.png")
            out_path.write_bytes(r.content)
            print(f"Saved to {out_path}, size: {out_path.stat().st_size / 1024:.1f} KB")
        except Exception as e:
            print(f"Failed for Scene {num}: {e}")

if __name__ == "__main__":
    main()
