import urllib.parse
import requests
from pathlib import Path

def test_gen():
    style = (
        "A premium, highly attractive 3D Pixar claymation character illustration, "
        "warm expressive characters, friendly and approachable software developer, "
        "beautifully rounded shapes, smooth modern tech surfaces with tactile glassmorphism textures, "
        "soft pastel purple and cyan highlights, subtle orange/gold glow, warm volumetric studio lighting, "
        "gentle depth of field, subtle glowing particles, high-detail textures, 8k resolution, "
        "cinematic composition, zero text, zero logos, no watermark. "
    )
    prompt = style + "A clean, modern 3D atmospheric layout featuring a deep dark-blue gradient background. Centered in the frame is a single, glowing neon-green button shaped like a rocket ship lifting off, surrounded by soft pastel light halos. Perfect, clean negative space."
    
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&private=true&model=flux"
    print(f"Querying: {url[:100]}...")
    
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        output_path = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/test_flux.png")
        output_path.write_bytes(r.content)
        print(f"Saved to {output_path}, size: {output_path.stat().st_size / 1024:.1f} KB")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_gen()
